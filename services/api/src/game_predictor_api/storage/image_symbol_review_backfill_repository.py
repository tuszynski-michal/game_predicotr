"""Persistence boundary for the durable symbol-cell projection backfill."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from game_predictor_api.application.image_symbol_review_backfill import (
    SymbolCellReviewProjectionStart,
    SymbolCellReviewProjectionState,
    SymbolCellReviewProjectionStatus,
)
from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewError
from game_predictor_api.domain.jobs import Job, JobStatus, JobType, create_job
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemyImageSymbolReviewRepository,
    SymbolCellReviewBackfillError,
)
from game_predictor_api.storage.job_repository import (
    job_from_record,
    job_record_from_domain,
)
from game_predictor_api.storage.models import (
    GameModel,
    ImageBoardSearchFastDocumentModel,
    ImageSymbolReviewCellModel,
    ImageSymbolReviewStateModel,
    JobModel,
)

_WORKFLOW = "image_symbol_review_backfill"
_ACTIVE_JOB_STATUSES = (JobStatus.CREATED, JobStatus.PROCESSING)


class SqlAlchemySymbolCellReviewBackfillRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def status(self, game_id: UUID) -> SymbolCellReviewProjectionStatus:
        self._require_game(game_id, lock=False)
        return self._status(game_id)

    def start(self, game_id: UUID) -> SymbolCellReviewProjectionStart:
        self._require_game(game_id, lock=True)
        active = self._active_job(game_id)
        if active is not None:
            return SymbolCellReviewProjectionStart(
                status=self._status(game_id),
                job=job_from_record(active),
                created=False,
            )

        try:
            report = SqlAlchemyImageSymbolReviewRepository(
                self._session
            ).start_or_resume_backfill(game_id)
        except SymbolCellReviewBackfillError as error:
            raise SymbolCellReviewError(error.code, str(error)) from error
        if report.status == "failed":
            return SymbolCellReviewProjectionStart(
                status=self._status(game_id),
                job=None,
                created=False,
            )
        if report.status == "ready":
            return SymbolCellReviewProjectionStart(
                status=self._status(game_id),
                job=self._latest_job(game_id),
                created=False,
            )

        generation = int(
            self._session.scalar(
                select(func.count(JobModel.id)).where(
                    JobModel.game_id == game_id,
                    JobModel.job_type == JobType.IMAGE_SYMBOL_REVIEW_BACKFILL,
                )
            )
            or 0
        ) + 1
        job = create_job(
            JobType.IMAGE_SYMBOL_REVIEW_BACKFILL,
            game_id=game_id,
            input_payload={
                "schema_version": 1,
                "workflow": _WORKFLOW,
                "generation": generation,
            },
        )
        record = job_record_from_domain(job)
        self._session.add(record)
        self._session.flush()
        return SymbolCellReviewProjectionStart(
            status=self._status(game_id),
            job=job_from_record(record),
            created=True,
        )

    def _status(self, game_id: UUID) -> SymbolCellReviewProjectionStatus:
        expected_board_count = int(
            self._session.scalar(
                select(func.count(ImageBoardSearchFastDocumentModel.game_id)).where(
                    ImageBoardSearchFastDocumentModel.game_id == game_id
                )
            )
            or 0
        )
        state = self._session.get(ImageSymbolReviewStateModel, game_id)
        persisted_cell_count = int(
            self._session.scalar(
                select(func.count(ImageSymbolReviewCellModel.id)).where(
                    ImageSymbolReviewCellModel.game_id == game_id
                )
            )
            or 0
        )
        active = self._active_job(game_id)
        return SymbolCellReviewProjectionStatus(
            game_id=game_id,
            status=(
                "not_started"
                if state is None
                else cast(SymbolCellReviewProjectionState, state.status)
            ),
            expected_board_count=expected_board_count,
            expected_cell_count=expected_board_count * 15,
            processed_board_count=(
                0 if state is None else int(state.processed_review_item_count)
            ),
            persisted_cell_count=persisted_cell_count,
            missing_sequence_count=(0 if state is None else int(state.missing_sequence_count)),
            invalid_crop_count=(0 if state is None else int(state.invalid_crop_count)),
            invalid_geometry_count=(0 if state is None else int(state.invalid_geometry_count)),
            failure_message=None if state is None else state.failure_message,
            sample_problem_review_item_ids=(),
            active_job_id=None if active is None else active.id,
        )

    def _active_job(self, game_id: UUID) -> JobModel | None:
        return self._session.scalar(
            select(JobModel)
            .where(
                JobModel.game_id == game_id,
                JobModel.job_type == JobType.IMAGE_SYMBOL_REVIEW_BACKFILL,
                JobModel.status.in_(_ACTIVE_JOB_STATUSES),
            )
            .order_by(JobModel.created_at.desc(), JobModel.id.desc())
            .limit(1)
        )

    def _latest_job(self, game_id: UUID) -> Job | None:
        record = self._session.scalar(
            select(JobModel)
            .where(
                JobModel.game_id == game_id,
                JobModel.job_type == JobType.IMAGE_SYMBOL_REVIEW_BACKFILL,
            )
            .order_by(JobModel.created_at.desc(), JobModel.id.desc())
            .limit(1)
        )
        return None if record is None else job_from_record(record)

    def _require_game(self, game_id: UUID, *, lock: bool) -> None:
        statement = select(GameModel.id).where(GameModel.id == game_id)
        if lock:
            statement = statement.with_for_update()
        if self._session.scalar(statement) is None:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_GAME_NOT_FOUND",
                "The selected game does not exist.",
            )


__all__ = ["SqlAlchemySymbolCellReviewBackfillRepository"]
