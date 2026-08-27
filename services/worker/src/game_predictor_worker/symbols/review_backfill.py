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
_MAX_RECONCILIATION_PASSES = 3


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
            current = int(job.progress_current)
            success_count = int(job.success_count)
            failure_count = int(job.failure_count)
            while True:
                with self._session_factory.begin() as session:
                    step = SqlAlchemyImageSymbolReviewRepository(session).backfill_next_batch(
                        job.game_id,
                        batch_size=_BATCH_SIZE,
                        finalize_when_exhausted=False,
                    )
                report = step.report
                current = max(current, report.processed_review_item_count)
                success_count = max(success_count, report.cell_count)
                failure_count = max(
                    failure_count,
                    report.missing_sequence_count
                    + report.invalid_crop_count
                    + report.invalid_geometry_count,
                )
                context.checkpoint(
                    checkpoint_payload={
                        "schema_version": 1,
                        "workflow": "image_symbol_review_backfill",
                        "phase": "scan",
                        "processed_board_count": report.processed_review_item_count,
                        "persisted_cell_count": report.cell_count,
                    },
                    stage="symbol_cell_review_backfill",
                    current=current,
                    total=None,
                    success_count=success_count,
                    failure_count=failure_count,
                    review_count=0,
                )
                if report.status == "failed":
                    raise JobHandlerError(
                        "SYMBOL_CELL_REVIEW_BACKFILL_FAILED",
                        report.failure_message or "The symbol-cell backfill failed.",
                    )
                if not step.has_more:
                    break

            last_report = report
            for pass_number in range(1, _MAX_RECONCILIATION_PASSES + 1):
                with self._session_factory.begin() as session:
                    SqlAlchemyImageSymbolReviewRepository(
                        session
                    ).begin_reconciliation_pass(job.game_id)
                while True:
                    with self._session_factory.begin() as session:
                        reconciliation = SqlAlchemyImageSymbolReviewRepository(
                            session
                        ).reconcile_next_batch(job.game_id, batch_size=_BATCH_SIZE)
                    last_report = reconciliation.report
                    current = max(current, last_report.processed_review_item_count)
                    success_count = max(success_count, last_report.cell_count)
                    failure_count = max(
                        failure_count,
                        last_report.missing_sequence_count
                        + last_report.invalid_crop_count
                        + last_report.invalid_geometry_count,
                    )
                    context.checkpoint(
                        checkpoint_payload={
                            "schema_version": 1,
                            "workflow": "image_symbol_review_backfill",
                            "phase": "reconciliation",
                            "reconciliation_pass": pass_number,
                            "processed_board_count": last_report.processed_review_item_count,
                            "persisted_cell_count": last_report.cell_count,
                            "problem_review_item_ids": [
                                str(value)
                                for value in last_report.sample_problem_review_item_ids
                            ],
                        },
                        stage="symbol_cell_review_reconciliation",
                        current=current,
                        total=None,
                        success_count=success_count,
                        failure_count=failure_count,
                        review_count=0,
                    )
                    if last_report.status == "failed" or not reconciliation.has_more:
                        break

                if last_report.status != "failed":
                    with self._session_factory.begin() as session:
                        last_report = SqlAlchemyImageSymbolReviewRepository(
                            session
                        ).finalize_backfill(job.game_id)
                    success_count = max(success_count, last_report.cell_count)
                    failure_count = max(
                        failure_count,
                        last_report.missing_sequence_count
                        + last_report.invalid_crop_count
                        + last_report.invalid_geometry_count,
                    )
                    context.checkpoint(
                        checkpoint_payload={
                            "schema_version": 1,
                            "workflow": "image_symbol_review_backfill",
                            "phase": "finalization",
                            "reconciliation_pass": pass_number,
                            "processed_board_count": last_report.processed_review_item_count,
                            "persisted_cell_count": last_report.cell_count,
                            "problem_review_item_ids": [
                                str(value)
                                for value in last_report.sample_problem_review_item_ids
                            ],
                        },
                        stage="symbol_cell_review_finalization",
                        current=current,
                        total=None,
                        success_count=success_count,
                        failure_count=failure_count,
                        review_count=0,
                    )
                    if last_report.status == "ready":
                        return

            raise JobHandlerError(
                "SYMBOL_CELL_REVIEW_BACKFILL_FAILED",
                last_report.failure_message
                or "The symbol-cell projection did not stabilize after three "
                "reconciliation passes.",
            )
        except (SymbolCellReviewError, SymbolCellReviewBackfillError) as error:
            raise JobHandlerError(error.code, error.message) from error


__all__ = ["SymbolCellReviewBackfillHandler"]
