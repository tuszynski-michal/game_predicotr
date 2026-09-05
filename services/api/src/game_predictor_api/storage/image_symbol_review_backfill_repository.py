"""Persistence boundary for the durable symbol-cell projection backfill."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import cast
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
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


def _optional_non_negative_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


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

        projection_repository = SqlAlchemyImageSymbolReviewRepository(self._session)
        current_state = self._session.get(
            ImageSymbolReviewStateModel,
            game_id,
            with_for_update=True,
        )
        preserve_ready_projection = (
            current_state is not None and current_state.status == "ready"
        )
        try:
            report = (
                projection_repository.state_for_game(game_id)
                if current_state is not None and current_state.status == "ready"
                else projection_repository.start_or_resume_backfill(game_id)
            )
        except SymbolCellReviewBackfillError as error:
            raise SymbolCellReviewError(error.code, str(error)) from error
        if report is None:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_BACKFILL_STATE_INVALID",
                "The symbol-cell review projection state is unavailable.",
            )
        if report.status == "failed":
            return SymbolCellReviewProjectionStart(
                status=self._status(game_id),
                job=None,
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
        table_bytes, index_bytes, database_free_bytes = self._storage_metrics()
        job = create_job(
            JobType.IMAGE_SYMBOL_REVIEW_BACKFILL,
            game_id=game_id,
            input_payload={
                "schema_version": 1,
                "workflow": _WORKFLOW,
                "generation": generation,
                "preserve_ready_projection": preserve_ready_projection,
                "table_bytes_before": table_bytes,
                "index_bytes_before": index_bytes,
                "database_free_bytes_before": database_free_bytes,
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
        latest = active if active is not None else self._latest_job_record(game_id)
        baseline = {} if latest is None else latest.input_payload
        checkpoint = (
            {}
            if latest is None or latest.checkpoint_payload is None
            else latest.checkpoint_payload
        )
        processed_board_count = (
            0
            if state is None
            else (
                expected_board_count
                if state.status == "ready"
                else int(state.processed_review_item_count)
            )
        )
        problem_ids: list[UUID] = []
        raw_problem_ids = checkpoint.get("problem_review_item_ids")
        if isinstance(raw_problem_ids, list):
            for value in raw_problem_ids[:100]:
                try:
                    problem_ids.append(UUID(str(value)))
                except (TypeError, ValueError):
                    continue
        table_bytes, index_bytes, database_free_bytes = self._storage_metrics()
        return SymbolCellReviewProjectionStatus(
            game_id=game_id,
            status=(
                "not_started"
                if state is None
                else cast(SymbolCellReviewProjectionState, state.status)
            ),
            expected_board_count=expected_board_count,
            expected_cell_count=expected_board_count * 15,
            processed_board_count=processed_board_count,
            persisted_cell_count=persisted_cell_count,
            missing_sequence_count=(0 if state is None else int(state.missing_sequence_count)),
            invalid_crop_count=(0 if state is None else int(state.invalid_crop_count)),
            invalid_geometry_count=(0 if state is None else int(state.invalid_geometry_count)),
            failure_message=None if state is None else state.failure_message,
            sample_problem_review_item_ids=tuple(problem_ids),
            active_job_id=None if active is None else active.id,
            table_bytes_before=_optional_non_negative_int(
                baseline.get("table_bytes_before")
            ),
            index_bytes_before=_optional_non_negative_int(
                baseline.get("index_bytes_before")
            ),
            table_bytes_current=table_bytes,
            index_bytes_current=index_bytes,
            database_free_bytes_current=database_free_bytes,
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
        record = self._latest_job_record(game_id)
        return None if record is None else job_from_record(record)

    def _latest_job_record(self, game_id: UUID) -> JobModel | None:
        return self._session.scalar(
            select(JobModel)
            .where(
                JobModel.game_id == game_id,
                JobModel.job_type == JobType.IMAGE_SYMBOL_REVIEW_BACKFILL,
            )
            .order_by(JobModel.created_at.desc(), JobModel.id.desc())
            .limit(1)
        )

    def _storage_metrics(self) -> tuple[int | None, int | None, int | None]:
        if self._session.bind is None or self._session.bind.dialect.name != "postgresql":
            return None, None, None
        try:
            table_bytes = int(
                self._session.scalar(
                    text("SELECT pg_relation_size('image_symbol_review_cells')")
                )
                or 0
            )
            index_bytes = int(
                self._session.scalar(
                    text("SELECT pg_indexes_size('image_symbol_review_cells')")
                )
                or 0
            )
            data_directory = self._session.scalar(text("SHOW data_directory"))
        except (SQLAlchemyError, ValueError):
            return None, None, None
        try:
            free_bytes = (
                None
                if not isinstance(data_directory, str) or not data_directory
                else int(shutil.disk_usage(Path(data_directory)).free)
            )
        except OSError:
            free_bytes = None
        return table_bytes, index_bytes, free_bytes

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
