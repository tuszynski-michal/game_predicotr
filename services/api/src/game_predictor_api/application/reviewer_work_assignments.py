"""Application lifecycle for durable, scoped Reviewer work assignments."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime
from threading import Lock, RLock
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.reviewer_work_assignments import (
    ReviewerWorkAssignment,
    ReviewerWorkAssignmentConflictError,
    ReviewerWorkAssignmentError,
    ReviewerWorkAssignmentType,
    close_reviewer_work_assignment,
    create_reviewer_work_assignment,
    expire_reviewer_work_assignment,
    renew_reviewer_work_assignment,
    require_active_reviewer_work_assignment,
)


class ReviewerWorkAssignmentRepository(Protocol):
    def lock_scope(self, game_id: UUID, import_job_id: UUID) -> bool: ...

    def add(self, assignment: ReviewerWorkAssignment) -> ReviewerWorkAssignment: ...

    def get_for_update(self, assignment_id: UUID) -> ReviewerWorkAssignment | None: ...

    def find_active_for_import(
        self,
        import_job_id: UUID,
    ) -> ReviewerWorkAssignment | None: ...

    def save_active(
        self,
        assignment: ReviewerWorkAssignment,
        *,
        expected_lease_token: UUID,
    ) -> ReviewerWorkAssignment: ...

    def list_for_import(self, import_job_id: UUID) -> Sequence[ReviewerWorkAssignment]: ...

    def lock_online_capacity(self) -> AbstractContextManager[None]: ...

    def list_active_online(self) -> Sequence[ReviewerWorkAssignment]: ...


class InMemoryReviewerWorkAssignmentRepository:
    """Deterministic assignment store used by focused lifecycle tests."""

    def __init__(self) -> None:
        self._assignments: dict[UUID, ReviewerWorkAssignment] = {}
        self._lock = Lock()
        self._online_capacity_lock = RLock()

    def lock_scope(self, _game_id: UUID, _import_job_id: UUID) -> bool:
        return True

    def add(self, assignment: ReviewerWorkAssignment) -> ReviewerWorkAssignment:
        with self._lock:
            if any(
                item.import_job_id == assignment.import_job_id and item.is_active
                for item in self._assignments.values()
            ):
                raise ReviewerWorkAssignmentConflictError(
                    "REVIEWER_ASSIGNMENT_ALREADY_ACTIVE",
                    "The selected import already has an active work assignment.",
                    details={"importJobId": str(assignment.import_job_id)},
                )
            self._assignments[assignment.id] = assignment
        return assignment

    def get_for_update(self, assignment_id: UUID) -> ReviewerWorkAssignment | None:
        with self._lock:
            return self._assignments.get(assignment_id)

    def find_active_for_import(
        self,
        import_job_id: UUID,
    ) -> ReviewerWorkAssignment | None:
        with self._lock:
            return next(
                (
                    item
                    for item in self._assignments.values()
                    if item.import_job_id == import_job_id and item.is_active
                ),
                None,
            )

    def save_active(
        self,
        assignment: ReviewerWorkAssignment,
        *,
        expected_lease_token: UUID,
    ) -> ReviewerWorkAssignment:
        with self._lock:
            persisted = self._assignments.get(assignment.id)
            if (
                persisted is None
                or not persisted.is_active
                or persisted.lease_token != expected_lease_token
            ):
                raise ReviewerWorkAssignmentConflictError(
                    "REVIEWER_ASSIGNMENT_LEASE_LOST",
                    "The caller no longer owns an active lease for this assignment.",
                    details={"assignmentId": str(assignment.id)},
                )
            self._assignments[assignment.id] = assignment
        return assignment

    def list_for_import(self, import_job_id: UUID) -> Sequence[ReviewerWorkAssignment]:
        with self._lock:
            return tuple(
                sorted(
                    (
                        item
                        for item in self._assignments.values()
                        if item.import_job_id == import_job_id
                    ),
                    key=lambda item: (item.created_at, item.id),
                )
            )

    @contextmanager
    def lock_online_capacity(self) -> Iterator[None]:
        with self._online_capacity_lock:
            yield

    def list_active_online(self) -> Sequence[ReviewerWorkAssignment]:
        with self._lock:
            return tuple(
                sorted(
                    (
                        item
                        for item in self._assignments.values()
                        if item.assignment_type is ReviewerWorkAssignmentType.ONLINE
                        and item.is_active
                    ),
                    key=lambda item: (item.created_at, item.id),
                )
            )


MAX_ACTIVE_ONLINE_REVIEWER_ASSIGNMENTS = 3


class ReviewerWorkAssignmentService:
    """Open, heartbeat and close one durable assignment per import."""

    def __init__(
        self,
        repository: ReviewerWorkAssignmentRepository | None = None,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository or InMemoryReviewerWorkAssignmentRepository()
        self._now = now or (lambda: datetime.now(UTC))

    def open(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        assignment_type: ReviewerWorkAssignmentType,
        reviewer_access_session_id: UUID | None = None,
        online_session_factory: Callable[[], UUID] | None = None,
        lease_owner: str,
        lease_expires_at: datetime,
        before_expire: Callable[[ReviewerWorkAssignment], None] | None = None,
        after_last_online_close: Callable[[], None] | None = None,
    ) -> ReviewerWorkAssignment:
        now = self._now()
        if not self._repository.lock_scope(game_id, import_job_id):
            raise ReviewerWorkAssignmentError(
                "REVIEWER_ASSIGNMENT_SCOPE_INVALID",
                "The import must belong to the selected game and be ready for review.",
                details={
                    "gameId": str(game_id),
                    "importJobId": str(import_job_id),
                },
            )
        if online_session_factory is not None and (
            assignment_type is not ReviewerWorkAssignmentType.ONLINE
            or reviewer_access_session_id is not None
        ):
            raise ReviewerWorkAssignmentError(
                "REVIEWER_ASSIGNMENT_SESSION_INVALID",
                "An online session factory can only prepare an online assignment "
                "without a pre-existing access session.",
            )
        with self._repository.lock_online_capacity():
            self._recover_expired_online(
                now=now,
                before_expire=before_expire,
            )
            self._reject_or_recover_active_import(
                import_job_id=import_job_id,
                now=now,
                before_expire=before_expire,
            )
            if assignment_type is ReviewerWorkAssignmentType.ONLINE:
                active_online = self._repository.list_active_online()
                if len(active_online) >= MAX_ACTIVE_ONLINE_REVIEWER_ASSIGNMENTS:
                    raise ReviewerWorkAssignmentConflictError(
                        "REVIEWER_ASSIGNMENT_ONLINE_LIMIT_REACHED",
                        "At most three different imports can be shared online at once.",
                        details={
                            "activeOnlineCount": len(active_online),
                            "maximumOnlineCount": MAX_ACTIVE_ONLINE_REVIEWER_ASSIGNMENTS,
                        },
                    )
                session_id = reviewer_access_session_id
                if online_session_factory is not None:
                    session_id = online_session_factory()
                candidate = create_reviewer_work_assignment(
                    game_id=game_id,
                    import_job_id=import_job_id,
                    assignment_type=assignment_type,
                    reviewer_access_session_id=session_id,
                    lease_owner=lease_owner,
                    lease_expires_at=lease_expires_at,
                    created_at=now,
                )
                return self._repository.add(candidate)
            if not self._repository.list_active_online() and after_last_online_close is not None:
                after_last_online_close()
            candidate = create_reviewer_work_assignment(
                game_id=game_id,
                import_job_id=import_job_id,
                assignment_type=assignment_type,
                reviewer_access_session_id=reviewer_access_session_id,
                lease_owner=lease_owner,
                lease_expires_at=lease_expires_at,
                created_at=now,
            )
            return self._repository.add(candidate)

    def _reject_or_recover_active_import(
        self,
        *,
        import_job_id: UUID,
        now: datetime,
        before_expire: Callable[[ReviewerWorkAssignment], None] | None,
    ) -> None:
        active = self._repository.find_active_for_import(import_job_id)
        if active is not None:
            if active.lease_expires_at > now:
                raise ReviewerWorkAssignmentConflictError(
                    "REVIEWER_ASSIGNMENT_ALREADY_ACTIVE",
                    "The selected import already has an active work assignment.",
                    details={
                        "assignmentId": str(active.id),
                        "importJobId": str(import_job_id),
                    },
                )
            expired = expire_reviewer_work_assignment(
                active,
                actor="reviewer-assignment-recovery",
                expired_at=now,
            )
            if before_expire is not None:
                before_expire(active)
            self._repository.save_active(
                expired,
                expected_lease_token=active.lease_token,
            )

    def _recover_expired_online(
        self,
        *,
        now: datetime,
        before_expire: Callable[[ReviewerWorkAssignment], None] | None,
    ) -> tuple[ReviewerWorkAssignment, ...]:
        expired_assignments: list[ReviewerWorkAssignment] = []
        for active in self._repository.list_active_online():
            if active.lease_expires_at > now:
                continue
            expired = expire_reviewer_work_assignment(
                active,
                actor="reviewer-assignment-recovery",
                expired_at=now,
            )
            if before_expire is not None:
                before_expire(active)
            expired_assignments.append(
                self._repository.save_active(
                    expired,
                    expected_lease_token=active.lease_token,
                )
            )
        return tuple(expired_assignments)

    def get(self, assignment_id: UUID) -> ReviewerWorkAssignment:
        return self._get_for_update(assignment_id)

    def require_active(
        self,
        assignment_id: UUID,
        *,
        lease_token: UUID,
    ) -> ReviewerWorkAssignment:
        assignment = self._get_for_update(assignment_id)
        require_active_reviewer_work_assignment(
            assignment,
            lease_token=lease_token,
            checked_at=self._now(),
        )
        return assignment

    def heartbeat(
        self,
        assignment_id: UUID,
        *,
        lease_token: UUID,
        lease_expires_at: datetime,
    ) -> ReviewerWorkAssignment:
        assignment = self._get_for_update(assignment_id)
        renewed = renew_reviewer_work_assignment(
            assignment,
            lease_token=lease_token,
            lease_expires_at=lease_expires_at,
            heartbeat_at=self._now(),
        )
        return self._repository.save_active(
            renewed,
            expected_lease_token=lease_token,
        )

    def close(
        self,
        assignment_id: UUID,
        *,
        lease_token: UUID,
        reason: str,
        actor: str,
        before_close: Callable[[ReviewerWorkAssignment], None] | None = None,
        before_expire: Callable[[ReviewerWorkAssignment], None] | None = None,
        after_last_online_close: Callable[[], None] | None = None,
    ) -> ReviewerWorkAssignment:
        now = self._now()
        with self._repository.lock_online_capacity():
            assignment = self._get_for_update(assignment_id)
            if not assignment.is_active:
                return close_reviewer_work_assignment(
                    assignment,
                    lease_token=lease_token,
                    reason=reason,
                    actor=actor,
                    closed_at=now,
                )
            require_active_reviewer_work_assignment(
                assignment,
                lease_token=lease_token,
                checked_at=now,
            )
            if before_close is not None:
                before_close(assignment)
            closed = close_reviewer_work_assignment(
                assignment,
                lease_token=lease_token,
                reason=reason,
                actor=actor,
                closed_at=now,
            )
            persisted = self._repository.save_active(
                closed,
                expected_lease_token=lease_token,
            )
            if assignment.assignment_type is ReviewerWorkAssignmentType.ONLINE:
                self._recover_expired_online(now=now, before_expire=before_expire)
                if (
                    not self._repository.list_active_online()
                    and after_last_online_close is not None
                ):
                    after_last_online_close()
            return persisted

    def recover_expired_online(
        self,
        *,
        before_expire: Callable[[ReviewerWorkAssignment], None] | None = None,
        after_last_online_close: Callable[[], None] | None = None,
    ) -> Sequence[ReviewerWorkAssignment]:
        with self._repository.lock_online_capacity():
            expired = self._recover_expired_online(
                now=self._now(),
                before_expire=before_expire,
            )
            if not self._repository.list_active_online() and after_last_online_close is not None:
                after_last_online_close()
            return expired

    def list_history(self, import_job_id: UUID) -> Sequence[ReviewerWorkAssignment]:
        return self._repository.list_for_import(import_job_id)

    def _get_for_update(self, assignment_id: UUID) -> ReviewerWorkAssignment:
        assignment = self._repository.get_for_update(assignment_id)
        if assignment is None:
            raise ReviewerWorkAssignmentError(
                "REVIEWER_ASSIGNMENT_NOT_FOUND",
                "Reviewer work assignment does not exist.",
                details={"assignmentId": str(assignment_id)},
            )
        return assignment


__all__ = [
    "InMemoryReviewerWorkAssignmentRepository",
    "MAX_ACTIVE_ONLINE_REVIEWER_ASSIGNMENTS",
    "ReviewerWorkAssignmentRepository",
    "ReviewerWorkAssignmentService",
]
