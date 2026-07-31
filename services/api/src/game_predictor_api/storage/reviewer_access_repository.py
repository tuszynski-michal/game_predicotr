"""SQLAlchemy persistence for scoped Reviewer access sessions."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from game_predictor_api.application.reviewer_access import (
    ReviewerAccessAuditEvent,
    ReviewerAccessRepository,
    ReviewerAccessSession,
)
from game_predictor_api.domain.jobs import JobStatus, JobType
from game_predictor_api.storage.models import (
    ImageReviewItemModel,
    JobModel,
    RecognizedBoardModel,
    ReviewerAccessAuditEventModel,
    ReviewerAccessSessionModel,
    SourceImageModel,
)


class SqlAlchemyReviewerAccessRepository(ReviewerAccessRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def scope_exists(self, game_id: UUID, import_job_id: UUID) -> bool:
        record = self._session.scalar(
            select(JobModel.id).where(
                JobModel.id == import_job_id,
                JobModel.game_id == game_id,
                JobModel.job_type == JobType.IMPORT,
            )
        )
        if record is None:
            return False
        job = self._session.get(JobModel, import_job_id)
        if (
            job is None
            or (job.input_payload.get("importKind") or job.input_payload.get("import_kind"))
            != "image_directory"
            or job.status not in {JobStatus.WAITING_FOR_REVIEW, JobStatus.COMPLETED}
        ):
            return False
        review_item = self._session.scalar(
            select(ImageReviewItemModel.id)
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .join(
                SourceImageModel,
                SourceImageModel.id == RecognizedBoardModel.source_image_id,
            )
            .where(SourceImageModel.import_job_id == import_job_id)
            .limit(1)
        )
        return review_item is not None

    def add(self, session: ReviewerAccessSession) -> ReviewerAccessSession:
        record = ReviewerAccessSessionModel(
            id=session.id,
            game_id=session.game_id,
            import_job_id=session.import_job_id,
            code_salt=session.code_salt,
            code_hash=session.code_hash,
            failed_attempts=session.failed_attempts,
            created_at=session.created_at,
            expires_at=session.expires_at,
        )
        self._session.add(record)
        self._session.flush()
        return _to_session(record)

    def get_for_update(self, session_id: UUID) -> ReviewerAccessSession | None:
        record = self._session.scalar(
            select(ReviewerAccessSessionModel)
            .where(ReviewerAccessSessionModel.id == session_id)
            .with_for_update()
        )
        return None if record is None else _to_session(record)

    def find_by_token_hash(self, token_hash: bytes) -> ReviewerAccessSession | None:
        record = self._session.scalar(
            select(ReviewerAccessSessionModel).where(
                ReviewerAccessSessionModel.token_hash == token_hash
            )
        )
        return None if record is None else _to_session(record)

    def save(self, session: ReviewerAccessSession) -> ReviewerAccessSession:
        record = self._session.get(ReviewerAccessSessionModel, session.id)
        if record is None:
            raise RuntimeError("Reviewer access session disappeared.")
        record.failed_attempts = session.failed_attempts
        record.locked_at = session.locked_at
        record.revoked_at = session.revoked_at
        record.token_hash = session.token_hash
        record.token_expires_at = session.token_expires_at
        record.last_unlocked_at = session.last_unlocked_at
        self._session.flush()
        return _to_session(record)

    def append_audit(
        self,
        session_id: UUID,
        event_type: str,
        created_at: datetime,
    ) -> None:
        self._session.add(
            ReviewerAccessAuditEventModel(
                session_id=session_id,
                event_type=event_type,
                created_at=created_at,
            )
        )
        self._session.flush()

    def list_audit(self, session_id: UUID) -> Sequence[ReviewerAccessAuditEvent]:
        return tuple(
            ReviewerAccessAuditEvent(
                id=record.id,
                session_id=record.session_id,
                event_type=record.event_type,
                created_at=record.created_at,
            )
            for record in self._session.scalars(
                select(ReviewerAccessAuditEventModel)
                .where(ReviewerAccessAuditEventModel.session_id == session_id)
                .order_by(
                    ReviewerAccessAuditEventModel.created_at,
                    ReviewerAccessAuditEventModel.id,
                )
            )
        )


def _to_session(record: ReviewerAccessSessionModel) -> ReviewerAccessSession:
    return ReviewerAccessSession(
        id=record.id,
        game_id=record.game_id,
        import_job_id=record.import_job_id,
        created_at=record.created_at,
        expires_at=record.expires_at,
        code_salt=record.code_salt,
        code_hash=record.code_hash,
        failed_attempts=record.failed_attempts,
        locked_at=record.locked_at,
        revoked_at=record.revoked_at,
        token_hash=record.token_hash,
        token_expires_at=record.token_expires_at,
        last_unlocked_at=record.last_unlocked_at,
    )


__all__ = ["SqlAlchemyReviewerAccessRepository"]
