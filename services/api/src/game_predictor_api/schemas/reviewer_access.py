"""OpenAPI schemas for the local standalone reviewer access gate."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from game_predictor_api.application.reviewer_access import (
    CreatedReviewerAccess,
    ReviewerAccessSession,
    UnlockedReviewerAccess,
)
from game_predictor_api.schemas.catalog import ApiModel


class ReviewerSessionCreate(ApiModel):
    game_id: UUID
    import_job_id: UUID
    lifetime_minutes: int = Field(default=480, ge=5, le=1440)


class ReviewerSessionCreatedResponse(ApiModel):
    session_id: UUID
    game_id: UUID
    import_job_id: UUID
    review_url: str
    access_code: str
    expires_at: datetime

    @classmethod
    def from_created(cls, created: CreatedReviewerAccess) -> ReviewerSessionCreatedResponse:
        return cls(
            session_id=created.session.id,
            game_id=created.session.game_id,
            import_job_id=created.session.import_job_id,
            review_url=created.review_url,
            access_code=created.code,
            expires_at=created.session.expires_at,
        )


class ReviewerSessionUnlock(ApiModel):
    access_code: str = Field(min_length=1, max_length=32)


class ReviewerSessionScopeResponse(ApiModel):
    session_id: UUID
    game_id: UUID
    import_job_id: UUID
    expires_at: datetime

    @classmethod
    def from_session(cls, session: ReviewerAccessSession) -> ReviewerSessionScopeResponse:
        return cls(
            session_id=session.id,
            game_id=session.game_id,
            import_job_id=session.import_job_id,
            expires_at=session.expires_at,
        )


class ReviewerSessionUnlockResponse(ReviewerSessionScopeResponse):
    access_token: str

    @classmethod
    def from_unlocked(
        cls,
        unlocked: UnlockedReviewerAccess,
    ) -> ReviewerSessionUnlockResponse:
        session = unlocked.session
        return cls(
            session_id=session.id,
            game_id=session.game_id,
            import_job_id=session.import_job_id,
            expires_at=session.expires_at,
            access_token=unlocked.access_token,
        )


__all__ = [
    "ReviewerSessionCreate",
    "ReviewerSessionCreatedResponse",
    "ReviewerSessionScopeResponse",
    "ReviewerSessionUnlock",
    "ReviewerSessionUnlockResponse",
]
