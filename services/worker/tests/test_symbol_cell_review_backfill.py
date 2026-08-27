from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID, uuid4

import game_predictor_worker.symbols.review_backfill as backfill_module
import pytest
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_api.storage.image_symbol_review_repository import (
    SymbolCellReviewBackfillReport,
    SymbolCellReviewBackfillStep,
    SymbolCellReviewReconciliationStep,
)
from game_predictor_worker.jobs.runtime import JobHandlerError
from game_predictor_worker.symbols.review_backfill import SymbolCellReviewBackfillHandler


class _Context:
    def __init__(self) -> None:
        self.checkpoints: list[dict[str, object]] = []

    def checkpoint(self, **values: object) -> None:
        self.checkpoints.append(values)


class _SessionFactory:
    @contextmanager
    def begin(self) -> Iterator[object]:
        yield object()


def _report(
    game_id: UUID,
    *,
    status: str,
    processed: int,
    cells: int,
    failure_message: str | None = None,
) -> SymbolCellReviewBackfillReport:
    return SymbolCellReviewBackfillReport(
        game_id=game_id,
        status=status,
        catalog_revision=0,
        processed_review_item_count=processed,
        cell_count=cells,
        missing_sequence_count=0,
        invalid_crop_count=0 if failure_message is None else 1,
        invalid_geometry_count=0,
        failure_message=failure_message,
        sample_problem_review_item_ids=(),
    )


def test_handler_processes_bounded_batches_and_persists_progress(monkeypatch: Any) -> None:
    game_id = uuid4()
    steps = iter(
        (
            SymbolCellReviewBackfillStep(
                report=_report(game_id, status="rebuilding", processed=200, cells=3000),
                processed_review_item_count=200,
                has_more=True,
            ),
            SymbolCellReviewBackfillStep(
                report=_report(game_id, status="ready", processed=250, cells=3750),
                processed_review_item_count=50,
                has_more=False,
            ),
        )
    )
    batch_sizes: list[int] = []

    class _Repository:
        def __init__(self, _session: object) -> None:
            pass

        def backfill_next_batch(
            self,
            _game_id: UUID,
            *,
            batch_size: int,
            finalize_when_exhausted: bool,
        ):
            assert _game_id == game_id
            assert finalize_when_exhausted is False
            batch_sizes.append(batch_size)
            return next(steps)

        def begin_reconciliation_pass(self, _game_id: UUID):
            return _report(game_id, status="rebuilding", processed=250, cells=3750)

        def reconcile_next_batch(self, _game_id: UUID, *, batch_size: int):
            assert batch_size == 200
            return SymbolCellReviewReconciliationStep(
                report=_report(game_id, status="rebuilding", processed=250, cells=3750),
                processed_review_item_count=0,
                has_more=False,
            )

        def finalize_backfill(self, _game_id: UUID):
            return _report(game_id, status="ready", processed=250, cells=3750)

    monkeypatch.setattr(backfill_module, "SqlAlchemyImageSymbolReviewRepository", _Repository)
    context = _Context()
    job = create_job(
        JobType.IMAGE_SYMBOL_REVIEW_BACKFILL,
        game_id=game_id,
        input_payload={
            "schema_version": 1,
            "workflow": "image_symbol_review_backfill",
            "generation": 1,
        },
    )

    SymbolCellReviewBackfillHandler(_SessionFactory())(context, job)  # type: ignore[arg-type]

    assert batch_sizes == [200, 200]
    assert [checkpoint["current"] for checkpoint in context.checkpoints] == [
        200,
        250,
        250,
        250,
    ]
    assert context.checkpoints[-1]["success_count"] == 3750
    assert context.checkpoints[-1]["stage"] == "symbol_cell_review_finalization"


def test_handler_reports_controlled_integrity_failure(monkeypatch: Any) -> None:
    game_id = uuid4()

    class _Repository:
        def __init__(self, _session: object) -> None:
            pass

        def backfill_next_batch(
            self,
            _game_id: UUID,
            *,
            batch_size: int,
            finalize_when_exhausted: bool,
        ):
            assert batch_size == 200
            assert finalize_when_exhausted is False
            return SymbolCellReviewBackfillStep(
                report=_report(
                    game_id,
                    status="failed",
                    processed=10,
                    cells=149,
                    failure_message="One crop is missing.",
                ),
                processed_review_item_count=0,
                has_more=False,
            )

    monkeypatch.setattr(backfill_module, "SqlAlchemyImageSymbolReviewRepository", _Repository)
    job = create_job(
        JobType.IMAGE_SYMBOL_REVIEW_BACKFILL,
        game_id=game_id,
        input_payload={
            "schema_version": 1,
            "workflow": "image_symbol_review_backfill",
            "generation": 1,
        },
    )

    with pytest.raises(JobHandlerError, match="One crop is missing") as error:
        SymbolCellReviewBackfillHandler(_SessionFactory())(_Context(), job)  # type: ignore[arg-type]

    assert error.value.code == "SYMBOL_CELL_REVIEW_BACKFILL_FAILED"


def test_handler_stops_after_three_failed_reconciliation_passes(monkeypatch: Any) -> None:
    game_id = uuid4()
    pass_count = 0

    class _Repository:
        def __init__(self, _session: object) -> None:
            pass

        def backfill_next_batch(
            self,
            _game_id: UUID,
            *,
            batch_size: int,
            finalize_when_exhausted: bool,
        ):
            return SymbolCellReviewBackfillStep(
                report=_report(game_id, status="rebuilding", processed=2, cells=30),
                processed_review_item_count=0,
                has_more=False,
            )

        def begin_reconciliation_pass(self, _game_id: UUID):
            nonlocal pass_count
            pass_count += 1
            return _report(game_id, status="rebuilding", processed=2, cells=30)

        def reconcile_next_batch(self, _game_id: UUID, *, batch_size: int):
            return SymbolCellReviewReconciliationStep(
                report=_report(
                    game_id,
                    status="failed",
                    processed=2,
                    cells=29,
                    failure_message="A current crop is unavailable.",
                ),
                processed_review_item_count=1,
                has_more=False,
            )

    monkeypatch.setattr(backfill_module, "SqlAlchemyImageSymbolReviewRepository", _Repository)
    job = create_job(
        JobType.IMAGE_SYMBOL_REVIEW_BACKFILL,
        game_id=game_id,
        input_payload={
            "schema_version": 1,
            "workflow": "image_symbol_review_backfill",
            "generation": 1,
        },
    )

    with pytest.raises(JobHandlerError, match="current crop is unavailable"):
        SymbolCellReviewBackfillHandler(_SessionFactory())(_Context(), job)  # type: ignore[arg-type]

    assert pass_count == 3
