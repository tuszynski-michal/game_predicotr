"""General-lane handler for the resumable symbol-cell projection backfill."""

from __future__ import annotations

from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewError
from game_predictor_api.domain.jobs import Job, JobType
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemyImageSymbolReviewRepository,
    SymbolCellReviewBackfillError,
)
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError

_BATCH_SIZE = 200


class SymbolCellReviewBackfillHandler:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        if job.job_type is not JobType.IMAGE_SYMBOL_REVIEW_BACKFILL or job.game_id is None:
            raise JobHandlerError(
                "SYMBOL_CELL_REVIEW_BACKFILL_JOB_INVALID",
                "The symbol-cell backfill handler received another job type.",
            )
        try:
            while True:
                with self._session_factory.begin() as session:
                    step = SqlAlchemyImageSymbolReviewRepository(session).backfill_next_batch(
                        job.game_id,
                        batch_size=_BATCH_SIZE,
                    )
                report = step.report
                context.checkpoint(
                    checkpoint_payload={
                        "schema_version": 1,
                        "workflow": "image_symbol_review_backfill",
                        "processed_board_count": report.processed_review_item_count,
                        "persisted_cell_count": report.cell_count,
                    },
                    stage="symbol_cell_review_backfill",
                    current=report.processed_review_item_count,
                    total=None,
                    success_count=report.cell_count,
                    failure_count=(
                        report.missing_sequence_count
                        + report.invalid_crop_count
                        + report.invalid_geometry_count
                    ),
                    review_count=0,
                )
                if report.status == "failed":
                    raise JobHandlerError(
                        "SYMBOL_CELL_REVIEW_BACKFILL_FAILED",
                        report.failure_message or "The symbol-cell backfill failed.",
                    )
                if not step.has_more:
                    return
        except (SymbolCellReviewError, SymbolCellReviewBackfillError) as error:
            raise JobHandlerError(error.code, error.message) from error


__all__ = ["SymbolCellReviewBackfillHandler"]
