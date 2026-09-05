"""General-lane handler for bounded virtual-geometry rollout validation."""

from __future__ import annotations

from game_predictor_api.domain.jobs import Job, JobType
from game_predictor_api.storage.image_geometry_rollout_backfill_repository import (
    ImageGeometryRolloutBackfillError,
    SqlAlchemyImageGeometryRolloutBackfillRepository,
)
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError

_BATCH_SIZE = 100


class ImageGeometryRolloutBackfillHandler:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        if job.job_type is not JobType.IMAGE_GEOMETRY_ROLLOUT_BACKFILL or job.game_id is None:
            raise JobHandlerError(
                "IMAGE_GEOMETRY_ROLLOUT_JOB_INVALID",
                "The geometry rollout handler received another job type.",
            )
        processed = int(job.progress_current)
        virtual_sources = int(job.success_count)
        persisted_checkpoint = job.checkpoint_payload or {}
        source_revision_backfills = _counter(
            persisted_checkpoint.get("source_revision_backfill_count")
        )
        observation_backfills = _counter(persisted_checkpoint.get("observation_backfill_count"))
        review_cell_backfills = _counter(persisted_checkpoint.get("review_cell_backfill_count"))
        training_cell_backfills = _counter(persisted_checkpoint.get("training_cell_backfill_count"))
        try:
            with self._session_factory() as session:
                persisted_status = SqlAlchemyImageGeometryRolloutBackfillRepository(session).status(
                    job.game_id
                )
                source_count = persisted_status.source_count
                processed = max(processed, persisted_status.processed_source_count)
            while True:
                with self._session_factory.begin() as session:
                    step = SqlAlchemyImageGeometryRolloutBackfillRepository(
                        session
                    ).validate_next_batch(job.game_id, limit=_BATCH_SIZE)
                processed += step.processed_source_count
                virtual_sources += step.virtual_source_count
                source_revision_backfills += step.source_revision_backfill_count
                observation_backfills += step.observation_backfill_count
                review_cell_backfills += step.review_cell_backfill_count
                training_cell_backfills += step.training_cell_backfill_count
                context.checkpoint(
                    checkpoint_payload={
                        "schema_version": 2,
                        "workflow": "image_geometry_rollout_backfill",
                        "phase": "contract_backfill_and_validation",
                        "last_source_image_id": (
                            None
                            if step.last_source_image_id is None
                            else str(step.last_source_image_id)
                        ),
                        "processed_source_count": processed,
                        "virtual_source_count": virtual_sources,
                        "source_revision_backfill_count": source_revision_backfills,
                        "observation_backfill_count": observation_backfills,
                        "review_cell_backfill_count": review_cell_backfills,
                        "training_cell_backfill_count": training_cell_backfills,
                    },
                    stage="image_geometry_rollout_v2_backfill",
                    current=processed,
                    total=source_count,
                    success_count=virtual_sources,
                    failure_count=0,
                    review_count=0,
                )
                if not step.has_more:
                    break
            with self._session_factory.begin() as session:
                status = SqlAlchemyImageGeometryRolloutBackfillRepository(session).finalize(
                    job.game_id
                )
            context.checkpoint(
                checkpoint_payload={
                    "schema_version": 2,
                    "workflow": "image_geometry_rollout_backfill",
                    "phase": "ready",
                    "last_source_image_id": (
                        None
                        if status.last_source_image_id is None
                        else str(status.last_source_image_id)
                    ),
                    "processed_source_count": status.processed_source_count,
                    "virtual_source_count": status.virtual_source_count,
                    "source_revision_backfill_count": source_revision_backfills,
                    "observation_backfill_count": observation_backfills,
                    "review_cell_backfill_count": review_cell_backfills,
                    "training_cell_backfill_count": training_cell_backfills,
                },
                stage="image_geometry_rollout_ready",
                current=status.processed_source_count,
                total=status.source_count,
                success_count=status.virtual_source_count,
                failure_count=0,
                review_count=0,
            )
        except ImageGeometryRolloutBackfillError as error:
            with self._session_factory.begin() as session:
                SqlAlchemyImageGeometryRolloutBackfillRepository(session).fail(
                    job.game_id,
                    error=error,
                )
            raise JobHandlerError(error.code, error.message) from error


def _counter(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


__all__ = ["ImageGeometryRolloutBackfillHandler"]
