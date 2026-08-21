"""OpenAPI schemas for the local standalone reviewer access gate."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from game_predictor_api.application.reviewer_access import (
    CreatedReviewerAccess,
    ReviewerAccessSession,
    UnlockedReviewerAccess,
)
from game_predictor_api.application.reviewer_ingress import ReviewerIngressStatus
from game_predictor_api.application.reviewer_work_lifecycle import (
    OpenedReviewerWork,
    ReviewerWorkOverview,
)
from game_predictor_api.domain.reviewer_work_assignments import ReviewerWorkAssignment
from game_predictor_api.schemas.catalog import ApiModel


class ReviewerSessionCreate(ApiModel):
    game_id: UUID
    import_job_id: UUID
    lifetime_minutes: int = Field(default=480, ge=5, le=1440)


class ReviewerIngressCommand(ApiModel):
    confirmed: Literal[True]
    target: Literal["remote-reviewer"]


class ReviewerLocalCommand(ApiModel):
    confirmed: Literal[True]
    target: Literal["local-reviewer"]


class ReviewerWorkOpenCommand(ApiModel):
    lifetime_minutes: int = Field(default=480, ge=5, le=1440)


class ReviewerWorkActionCommand(ApiModel):
    confirmed: Literal[True]


class ReviewerWorkAssignmentResponse(ApiModel):
    assignment_id: UUID
    game_id: UUID
    import_job_id: UUID
    assignment_type: Literal["local", "online"]
    review_url: str | None
    ready: bool
    heartbeat_at: datetime
    lease_expires_at: datetime
    created_at: datetime

    @classmethod
    def from_assignment(
        cls,
        assignment: ReviewerWorkAssignment,
        ingress: ReviewerIngressStatus,
    ) -> ReviewerWorkAssignmentResponse:
        reviewer_ready = ingress.reviewer_ready is True
        ready = reviewer_ready and (
            assignment.assignment_type.value == "local"
            or (ingress.state == "running" and ingress.public_origin is not None)
        )
        review_url: str | None = None
        if assignment.assignment_type.value == "local":
            review_url = (
                "http://127.0.0.1:3001/?mode=local"
                f"&gameId={assignment.game_id}&importJobId={assignment.import_job_id}"
            )
        elif ready and ingress.public_origin is not None:
            review_url = (
                f"{ingress.public_origin.rstrip('/')}/?session="
                f"{assignment.reviewer_access_session_id}"
            )
        return cls(
            assignment_id=assignment.id,
            game_id=assignment.game_id,
            import_job_id=assignment.import_job_id,
            assignment_type=assignment.assignment_type.value,
            review_url=review_url,
            ready=ready,
            heartbeat_at=assignment.heartbeat_at,
            lease_expires_at=assignment.lease_expires_at,
            created_at=assignment.created_at,
        )


class ReviewerWorkOverviewResponse(ApiModel):
    assignments: list[ReviewerWorkAssignmentResponse]
    active_online_count: int
    maximum_online_count: Literal[3] = 3
    ingress: ReviewerIngressStatusResponse

    @classmethod
    def from_overview(cls, overview: ReviewerWorkOverview) -> ReviewerWorkOverviewResponse:
        assignments = [
            ReviewerWorkAssignmentResponse.from_assignment(item, overview.ingress)
            for item in overview.assignments
        ]
        return cls(
            assignments=assignments,
            active_online_count=sum(item.assignment_type == "online" for item in assignments),
            ingress=ReviewerIngressStatusResponse.from_domain(overview.ingress),
        )


class ReviewerWorkOpenedResponse(ApiModel):
    assignment: ReviewerWorkAssignmentResponse
    created: bool
    access_code: str | None
    access_expires_at: datetime | None

    @classmethod
    def from_opened(cls, opened: OpenedReviewerWork) -> ReviewerWorkOpenedResponse:
        return cls(
            assignment=ReviewerWorkAssignmentResponse.from_assignment(
                opened.assignment,
                opened.ingress,
            ),
            created=opened.created,
            access_code=None if opened.access is None else opened.access.code,
            access_expires_at=(None if opened.access is None else opened.access.session.expires_at),
        )


class ReviewerWorkHeartbeatResponse(ApiModel):
    assignment_id: UUID
    heartbeat_at: datetime
    lease_expires_at: datetime

    @classmethod
    def from_assignment(
        cls,
        assignment: ReviewerWorkAssignment,
    ) -> ReviewerWorkHeartbeatResponse:
        return cls(
            assignment_id=assignment.id,
            heartbeat_at=assignment.heartbeat_at,
            lease_expires_at=assignment.lease_expires_at,
        )


class ReviewerWorkClosedResponse(ApiModel):
    assignment_id: UUID
    closed_at: datetime
    close_reason: str

    @classmethod
    def from_assignment(
        cls,
        assignment: ReviewerWorkAssignment,
    ) -> ReviewerWorkClosedResponse:
        assert assignment.closed_at is not None
        assert assignment.close_reason is not None
        return cls(
            assignment_id=assignment.id,
            closed_at=assignment.closed_at,
            close_reason=assignment.close_reason,
        )


class ReviewerIngressStatusResponse(ApiModel):
    state: Literal["running", "stopped", "stale", "degraded"]
    public_origin: str | None
    target: str
    started_at: datetime | None
    reviewer_ready: bool | None

    @classmethod
    def from_domain(
        cls,
        status: ReviewerIngressStatus,
    ) -> ReviewerIngressStatusResponse:
        return cls(
            state=status.state,
            public_origin=status.public_origin,
            target=status.target,
            started_at=status.started_at,
            reviewer_ready=status.reviewer_ready,
        )


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
    "ReviewerIngressCommand",
    "ReviewerIngressStatusResponse",
    "ReviewerLocalCommand",
    "ReviewerSessionCreate",
    "ReviewerSessionCreatedResponse",
    "ReviewerSessionScopeResponse",
    "ReviewerSessionUnlock",
    "ReviewerSessionUnlockResponse",
    "ReviewerWorkActionCommand",
    "ReviewerWorkAssignmentResponse",
    "ReviewerWorkClosedResponse",
    "ReviewerWorkHeartbeatResponse",
    "ReviewerWorkOpenCommand",
    "ReviewerWorkOpenedResponse",
    "ReviewerWorkOverviewResponse",
]
