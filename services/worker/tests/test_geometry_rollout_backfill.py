from __future__ import annotations

import importlib
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.image_geometry_rollout import ImageGeometryRolloutStatus
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_api.storage.image_geometry_rollout_backfill_repository import (
    ImageGeometryRolloutBackfillError,
    ImageGeometryRolloutBackfillStep,
)
from game_predictor_worker.images.geometry_rollout_backfill import (
    ImageGeometryRolloutBackfillHandler,
)
from game_predictor_worker.jobs.runtime import JobHandlerError

backfill_module = importlib.import_module("game_predictor_worker.images.geometry_rollout_backfill")


class _Context:
    def __init__(self) -> None:
        self.checkpoints: list[dict[str, object]] = []

    def checkpoint(self, **values: object) -> None:
        self.checkpoints.append(values)


class _SessionFactory:
    def __call__(self) -> _SessionFactory:
        return self

    def __enter__(self) -> object:
        return object()

    def __exit__(self, *_args: object) -> None:
        return None

    @contextmanager
    def begin(self) -> Iterator[object]:
        yield object()


def _status(
    game_id: UUID,
    *,
    total: int,
    processed: int,
    status: str,
) -> ImageGeometryRolloutStatus:
    return ImageGeometryRolloutStatus(
        game_id=game_id,
        geometry_mode="structured_review",
        cell_asset_mode="virtual_source",
        rollout_revision=1,
        backfill_status=status,  # type: ignore[arg-type]
        source_count=total,
        processed_source_count=processed,
        virtual_source_count=processed,
        active_job_id=None,
        last_source_image_id=(uuid4() if processed else None),
        failure_code=None,
        failure_message=None,
    )


@pytest.mark.parametrize("source_count", [10, 100])
def test_handler_processes_small_and_full_bounded_batches(
    monkeypatch: Any,
    source_count: int,
) -> None:
    game_id = uuid4()
    calls: list[int] = []

    class _Repository:
        def __init__(self, _session: object) -> None:
            pass

        def status(self, _game_id: UUID) -> ImageGeometryRolloutStatus:
            return _status(game_id, total=source_count, processed=0, status="processing")

        def validate_next_batch(
            self,
            _game_id: UUID,
            *,
            limit: int,
        ) -> ImageGeometryRolloutBackfillStep:
            calls.append(limit)
            return ImageGeometryRolloutBackfillStep(
                processed_source_count=source_count,
                virtual_source_count=source_count,
                last_source_image_id=uuid4(),
                has_more=False,
            )

        def finalize(self, _game_id: UUID) -> ImageGeometryRolloutStatus:
            return _status(
                game_id,
                total=source_count,
                processed=source_count,
                status="ready",
            )

    monkeypatch.setattr(
        backfill_module,
        "SqlAlchemyImageGeometryRolloutBackfillRepository",
        _Repository,
    )
    context = _Context()
    job = create_job(
        JobType.IMAGE_GEOMETRY_ROLLOUT_BACKFILL,
        game_id=game_id,
        input_payload={"schema_version": 1, "workflow": "image_geometry_rollout_backfill"},
    )

    ImageGeometryRolloutBackfillHandler(_SessionFactory())(context, job)  # type: ignore[arg-type]

    assert calls == [100]
    assert context.checkpoints[-1]["stage"] == "image_geometry_rollout_ready"
    assert context.checkpoints[-1]["current"] == source_count
    assert context.checkpoints[-1]["total"] == source_count


def test_handler_resumes_from_persisted_job_progress(monkeypatch: Any) -> None:
    game_id = uuid4()

    class _Repository:
        def __init__(self, _session: object) -> None:
            pass

        def status(self, _game_id: UUID) -> ImageGeometryRolloutStatus:
            return _status(game_id, total=100, processed=10, status="processing")

        def validate_next_batch(
            self,
            _game_id: UUID,
            *,
            limit: int,
        ) -> ImageGeometryRolloutBackfillStep:
            assert limit == 100
            return ImageGeometryRolloutBackfillStep(90, 90, uuid4(), False)

        def finalize(self, _game_id: UUID) -> ImageGeometryRolloutStatus:
            return _status(game_id, total=100, processed=100, status="ready")

    monkeypatch.setattr(
        backfill_module,
        "SqlAlchemyImageGeometryRolloutBackfillRepository",
        _Repository,
    )
    context = _Context()
    job = create_job(
        JobType.IMAGE_GEOMETRY_ROLLOUT_BACKFILL,
        game_id=game_id,
        input_payload={"schema_version": 1, "workflow": "image_geometry_rollout_backfill"},
    )
    ImageGeometryRolloutBackfillHandler(_SessionFactory())(context, job)  # type: ignore[arg-type]

    assert context.checkpoints[0]["current"] == 100
    assert context.checkpoints[0]["success_count"] == 90


def test_handler_persists_controlled_failure(monkeypatch: Any) -> None:
    game_id = uuid4()
    failures: list[str] = []

    class _Repository:
        def __init__(self, _session: object) -> None:
            pass

        def status(self, _game_id: UUID) -> ImageGeometryRolloutStatus:
            return _status(game_id, total=1, processed=0, status="processing")

        def validate_next_batch(
            self,
            _game_id: UUID,
            *,
            limit: int,
        ) -> ImageGeometryRolloutBackfillStep:
            raise ImageGeometryRolloutBackfillError(
                "IMAGE_GEOMETRY_ROLLOUT_CELL_PROVENANCE_INVALID",
                "Virtual cells are incomplete.",
                source_image_id=uuid4(),
            )

        def fail(
            self,
            _game_id: UUID,
            *,
            error: ImageGeometryRolloutBackfillError,
        ) -> None:
            failures.append(error.code)

    monkeypatch.setattr(
        backfill_module,
        "SqlAlchemyImageGeometryRolloutBackfillRepository",
        _Repository,
    )
    job = create_job(
        JobType.IMAGE_GEOMETRY_ROLLOUT_BACKFILL,
        game_id=game_id,
        input_payload={"schema_version": 1, "workflow": "image_geometry_rollout_backfill"},
    )

    with pytest.raises(JobHandlerError) as error:
        ImageGeometryRolloutBackfillHandler(_SessionFactory())(_Context(), job)  # type: ignore[arg-type]

    assert error.value.code == "IMAGE_GEOMETRY_ROLLOUT_CELL_PROVENANCE_INVALID"
    assert failures == ["IMAGE_GEOMETRY_ROLLOUT_CELL_PROVENANCE_INVALID"]
