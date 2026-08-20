"""Framework-independent lifecycle for scoped Reviewer work assignments."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


class ReviewerWorkAssignmentType(StrEnum):
    LOCAL = "local"
    ONLINE = "online"


class ReviewerWorkAssignmentError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class ReviewerWorkAssignmentConflictError(ReviewerWorkAssignmentError):
    """The requested operation conflicts with a durable assignment lease."""


@dataclass(frozen=True, slots=True)
class ReviewerWorkAssignment:
    id: UUID
    game_id: UUID
    import_job_id: UUID
    assignment_type: ReviewerWorkAssignmentType
    reviewer_access_session_id: UUID | None
    lease_owner: str
    lease_token: UUID
    heartbeat_at: datetime
    lease_expires_at: datetime
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    close_reason: str | None = None
    closed_by: str | None = None

    @property
    def is_active(self) -> bool:
        return self.closed_at is None


def create_reviewer_work_assignment(
    *,
    game_id: UUID,
    import_job_id: UUID,
    assignment_type: ReviewerWorkAssignmentType,
    reviewer_access_session_id: UUID | None = None,
    lease_owner: str,
    lease_token: UUID | None = None,
    lease_expires_at: datetime,
    created_at: datetime | None = None,
) -> ReviewerWorkAssignment:
    now = created_at or datetime.now(UTC)
    owner = _normalized_text(lease_owner, field="leaseOwner", maximum=200)
    _require_aware(now, field="createdAt")
    _require_aware(lease_expires_at, field="leaseExpiresAt")
    if lease_expires_at <= now:
        raise ReviewerWorkAssignmentError(
            "REVIEWER_ASSIGNMENT_LEASE_EXPIRY_INVALID",
            "Assignment lease expiry must be later than its creation time.",
        )
    if (assignment_type is ReviewerWorkAssignmentType.LOCAL) != (
        reviewer_access_session_id is None
    ):
        raise ReviewerWorkAssignmentError(
            "REVIEWER_ASSIGNMENT_SESSION_INVALID",
            "A local assignment cannot have an access session and an online "
            "assignment must have exactly one access session.",
        )
    return ReviewerWorkAssignment(
        id=uuid4(),
        game_id=game_id,
        import_job_id=import_job_id,
        assignment_type=assignment_type,
        reviewer_access_session_id=reviewer_access_session_id,
        lease_owner=owner,
        lease_token=lease_token or uuid4(),
        heartbeat_at=now,
        lease_expires_at=lease_expires_at,
        created_at=now,
        updated_at=now,
    )


def renew_reviewer_work_assignment(
    assignment: ReviewerWorkAssignment,
    *,
    lease_token: UUID,
    lease_expires_at: datetime,
    heartbeat_at: datetime | None = None,
) -> ReviewerWorkAssignment:
    now = heartbeat_at or datetime.now(UTC)
    _require_aware(now, field="heartbeatAt")
    _require_aware(lease_expires_at, field="leaseExpiresAt")
    require_active_reviewer_work_assignment(
        assignment,
        lease_token=lease_token,
        checked_at=now,
    )
    if now < assignment.heartbeat_at:
        raise ReviewerWorkAssignmentError(
            "REVIEWER_ASSIGNMENT_HEARTBEAT_REGRESSION",
            "Assignment heartbeat cannot move backwards.",
        )
    if lease_expires_at <= now:
        raise ReviewerWorkAssignmentError(
            "REVIEWER_ASSIGNMENT_LEASE_EXPIRY_INVALID",
            "Assignment lease expiry must be later than its heartbeat.",
        )
    return replace(
        assignment,
        heartbeat_at=now,
        lease_expires_at=lease_expires_at,
        updated_at=now,
    )


def close_reviewer_work_assignment(
    assignment: ReviewerWorkAssignment,
    *,
    lease_token: UUID,
    reason: str,
    actor: str,
    closed_at: datetime | None = None,
) -> ReviewerWorkAssignment:
    now = closed_at or datetime.now(UTC)
    _require_aware(now, field="closedAt")
    normalized_reason = _normalized_text(reason, field="reason", maximum=100)
    normalized_actor = _normalized_text(actor, field="actor", maximum=200)
    if assignment.closed_at is not None:
        if (
            assignment.lease_token == lease_token
            and assignment.close_reason == normalized_reason
            and assignment.closed_by == normalized_actor
        ):
            return assignment
        raise ReviewerWorkAssignmentConflictError(
            "REVIEWER_ASSIGNMENT_ALREADY_CLOSED",
            "Reviewer work assignment has already been closed.",
            details={"assignmentId": str(assignment.id)},
        )
    if assignment.lease_token != lease_token:
        _raise_lease_lost(assignment)
    if now < assignment.created_at or now < assignment.heartbeat_at:
        raise ReviewerWorkAssignmentError(
            "REVIEWER_ASSIGNMENT_CLOSURE_TIME_INVALID",
            "Assignment closure cannot predate its creation or last heartbeat.",
        )
    return replace(
        assignment,
        closed_at=now,
        close_reason=normalized_reason,
        closed_by=normalized_actor,
        updated_at=now,
    )


def expire_reviewer_work_assignment(
    assignment: ReviewerWorkAssignment,
    *,
    actor: str,
    expired_at: datetime | None = None,
) -> ReviewerWorkAssignment:
    now = expired_at or datetime.now(UTC)
    _require_aware(now, field="expiredAt")
    if assignment.closed_at is not None:
        return assignment
    if assignment.lease_expires_at > now:
        raise ReviewerWorkAssignmentConflictError(
            "REVIEWER_ASSIGNMENT_LEASE_NOT_EXPIRED",
            "Only an assignment with an expired lease can be recovered.",
            details={"assignmentId": str(assignment.id)},
        )
    return close_reviewer_work_assignment(
        assignment,
        lease_token=assignment.lease_token,
        reason="lease_expired",
        actor=actor,
        closed_at=now,
    )


def require_active_reviewer_work_assignment(
    assignment: ReviewerWorkAssignment,
    *,
    lease_token: UUID,
    checked_at: datetime | None = None,
) -> None:
    now = checked_at or datetime.now(UTC)
    _require_aware(now, field="checkedAt")
    if (
        assignment.closed_at is not None
        or assignment.lease_token != lease_token
        or assignment.lease_expires_at <= now
    ):
        _raise_lease_lost(assignment)


def _normalized_text(value: str, *, field: str, maximum: int) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ReviewerWorkAssignmentError(
            "REVIEWER_ASSIGNMENT_VALUE_INVALID",
            f"{field} must contain 1-{maximum} non-whitespace characters.",
            details={"field": field},
        )
    return normalized


def _require_aware(value: datetime, *, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReviewerWorkAssignmentError(
            "REVIEWER_ASSIGNMENT_TIMESTAMP_INVALID",
            f"{field} must include a timezone.",
            details={"field": field},
        )


def _raise_lease_lost(assignment: ReviewerWorkAssignment) -> None:
    raise ReviewerWorkAssignmentConflictError(
        "REVIEWER_ASSIGNMENT_LEASE_LOST",
        "The caller no longer owns an active lease for this assignment.",
        details={"assignmentId": str(assignment.id)},
    )


__all__ = [
    "ReviewerWorkAssignment",
    "ReviewerWorkAssignmentConflictError",
    "ReviewerWorkAssignmentError",
    "ReviewerWorkAssignmentType",
    "close_reviewer_work_assignment",
    "create_reviewer_work_assignment",
    "expire_reviewer_work_assignment",
    "renew_reviewer_work_assignment",
    "require_active_reviewer_work_assignment",
]
