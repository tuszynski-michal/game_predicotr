"""General-lane worker for durable bulk symbol-cell review operations."""

from __future__ import annotations

from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewError
from game_predictor_api.domain.jobs import Job, JobType
from game_predictor_api.storage.image_symbol_review_bulk_operation_repository import (
    SqlAlchemySymbolCellReviewBulkOperationWorker,
)
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError


class SymbolCellReviewBulkHandler:
    """Apply frozen targets in bounded, board-atomic batches.

    The general lane remains the sole execution lane.  A crash can roll back at
    most the board currently being written; already checkpointed target rows
    remain applied and pending rows are selected again after job retry.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._worker = SqlAlchemySymbolCellReviewBulkOperationWorker(session_factory)

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        if job.job_type is not JobType.IMAGE_SYMBOL_REVIEW_BULK:
            raise JobHandlerError(
                "SYMBOL_CELL_REVIEW_BULK_JOB_INVALID",
                "The bulk symbol review handler received another job type.",
            )
        try:
            self._worker.operation_for_job(job)
            while True:
                progress = self._worker.process_next_batch(job=job)
                operation = progress.operation
                context.checkpoint(
                    checkpoint_payload={
                        "schema_version": 1,
                        "workflow": "image_symbol_review_bulk",
                        "operation_id": str(operation.id),
                        "applied_count": operation.applied_count,
                        "conflict_count": operation.conflict_count,
                        "failed_count": operation.failed_count,
                        "pending_count": operation.pending_count,
                    },
                    stage="symbol_cell_review_bulk",
                    current=(
                        operation.applied_count
                        + operation.conflict_count
                        + operation.failed_count
                    ),
                    total=operation.target_count,
                    success_count=operation.applied_count,
                    failure_count=operation.failed_count,
                    review_count=operation.conflict_count,
                )
                if not progress.has_pending_targets:
                    return
        except SymbolCellReviewError as error:
            raise JobHandlerError(error.code, error.message) from error


__all__ = ["SymbolCellReviewBulkHandler"]
