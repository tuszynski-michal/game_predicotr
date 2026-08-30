from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import game_predictor_api.storage.image_symbol_review_backfill_repository as backfill_storage
import pytest
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_api.schemas.jobs import (
    SymbolCellReviewBackfillJobPayload,
    _payload_from_domain,
)
from game_predictor_api.storage.image_symbol_review_backfill_repository import (
    SqlAlchemySymbolCellReviewBackfillRepository,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    _iter_cell_insert_chunks,
)


def test_backfill_splits_two_hundred_boards_below_postgresql_parameter_limit() -> None:
    values = [{"cell_index": index} for index in range(200 * 15)]

    chunks = tuple(_iter_cell_insert_chunks(values))

    assert [len(chunk) for chunk in chunks] == [1_000, 1_000, 1_000]
    assert [value for chunk in chunks for value in chunk] == values


def test_storage_metrics_keep_database_sizes_when_data_directory_is_inaccessible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock()
    session.bind.dialect.name = "postgresql"
    session.scalar.side_effect = [12_345, 6_789, "/unavailable/postgresql/data"]
    monkeypatch.setattr(
        backfill_storage.shutil,
        "disk_usage",
        MagicMock(side_effect=OSError("directory is owned by another host")),
    )

    metrics = SqlAlchemySymbolCellReviewBackfillRepository(session)._storage_metrics()

    assert metrics == (12_345, 6_789, None)


def test_start_marks_reconciliation_of_ready_projection_as_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock()
    session.get.return_value = SimpleNamespace(status="ready")
    session.scalar.return_value = 0
    repository = SqlAlchemySymbolCellReviewBackfillRepository(session)
    monkeypatch.setattr(repository, "_require_game", MagicMock())
    monkeypatch.setattr(repository, "_active_job", MagicMock(return_value=None))
    monkeypatch.setattr(repository, "_storage_metrics", MagicMock(return_value=(1, 2, 3)))
    monkeypatch.setattr(repository, "_status", MagicMock(return_value=MagicMock()))
    projection = MagicMock()
    projection.state_for_game.return_value = SimpleNamespace(status="ready")
    monkeypatch.setattr(
        backfill_storage,
        "SqlAlchemyImageSymbolReviewRepository",
        MagicMock(return_value=projection),
    )

    result = repository.start(uuid4())

    assert result.created is True
    record = session.add.call_args.args[0]
    assert record.input_payload["preserve_ready_projection"] is True


def test_backfill_job_payload_accepts_preserved_ready_projection() -> None:
    payload = SymbolCellReviewBackfillJobPayload.model_validate(
        {
            "schema_version": 1,
            "workflow": "image_symbol_review_backfill",
            "generation": 2,
            "preserve_ready_projection": True,
        }
    )

    assert payload.preserve_ready_projection is True


def test_job_response_serializes_preserved_ready_projection() -> None:
    job = create_job(
        JobType.IMAGE_SYMBOL_REVIEW_BACKFILL,
        game_id=uuid4(),
        input_payload={
            "schema_version": 1,
            "workflow": "image_symbol_review_backfill",
            "generation": 2,
            "preserve_ready_projection": True,
        },
    )

    payload = _payload_from_domain(job)

    assert payload.preserve_ready_projection is True
