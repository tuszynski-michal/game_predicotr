"""Coordinate scoped Reviewer work without owning the shared ingress lifecycle."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib.parse import urlencode, urlparse, urlunparse
from uuid import UUID

from game_predictor_api.application.reviewer_access import (
    CreatedReviewerAccess,
    ReviewerAccessService,
)
from game_predictor_api.application.reviewer_ingress import (
    ReviewerIngressError,
    ReviewerIngressService,
    ReviewerIngressStatus,
)
from game_predictor_api.application.reviewer_work_assignments import (
    ReviewerWorkAssignmentService,
)
from game_predictor_api.domain.reviewer_work_assignments import (
    ReviewerWorkAssignment,
    ReviewerWorkAssignmentType,
)

_LOCAL_REVIEWER_ORIGIN = "http://127.0.0.1:3001"


class ReviewerProcessLifecycle(Protocol):
    """The deliberately small shared-process surface needed by this coordinator."""

    def status(self) -> ReviewerIngressStatus: ...

    def start(self) -> ReviewerIngressStatus: ...

    def start_local(self) -> ReviewerIngressStatus: ...

    def stop_if_current(self, instance_id: UUID) -> ReviewerIngressStatus: ...


@dataclass(frozen=True, slots=True)
class OpenedReviewerWork:
    assignment: ReviewerWorkAssignment
    ingress: ReviewerIngressStatus
    review_url: str
    access: CreatedReviewerAccess | None


class ReviewerWorkLifecycleService:
    """Open or close one scoped assignment while reusing one shared Reviewer."""

    def __init__(
        self,
        assignments: ReviewerWorkAssignmentService,
        access: ReviewerAccessService,
        ingress: ReviewerProcessLifecycle | ReviewerIngressService,
    ) -> None:
        self._assignments = assignments
        self._access = access
        self._ingress = ingress

    def open_local(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        lease_owner: str,
        lease_expires_at: datetime,
    ) -> OpenedReviewerWork:
        ingress = self._ensure_local_reviewer()
        assignment = self._assignments.open(
            game_id=game_id,
            import_job_id=import_job_id,
            assignment_type=ReviewerWorkAssignmentType.LOCAL,
            lease_owner=lease_owner,
            lease_expires_at=lease_expires_at,
            before_expire=self._revoke_assignment_session,
            after_last_online_close=self._stop_shared_ingress_if_current,
        )
        return OpenedReviewerWork(
            assignment=assignment,
            ingress=ingress,
            review_url=_local_review_url(game_id=game_id, import_job_id=import_job_id),
            access=None,
        )

    def open_online(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        lease_owner: str,
        lease_expires_at: datetime,
        session_lifetime_minutes: int,
    ) -> OpenedReviewerWork:
        ingress: ReviewerIngressStatus | None = None
        access: CreatedReviewerAccess | None = None

        def prepare_online_session() -> UUID:
            nonlocal access, ingress
            ingress = self._ensure_online_reviewer()
            assert ingress.public_origin is not None
            access = self._access.create(
                game_id=game_id,
                import_job_id=import_job_id,
                lifetime_minutes=session_lifetime_minutes,
                reviewer_origin=ingress.public_origin,
            )
            return UUID(str(access.session.id))

        try:
            assignment = self._assignments.open(
                game_id=game_id,
                import_job_id=import_job_id,
                assignment_type=ReviewerWorkAssignmentType.ONLINE,
                online_session_factory=prepare_online_session,
                lease_owner=lease_owner,
                lease_expires_at=lease_expires_at,
                before_expire=self._revoke_assignment_session,
            )
        except Exception:
            if access is not None:
                self._access.revoke(access.session.id)
            raise
        assert access is not None
        assert ingress is not None
        return OpenedReviewerWork(
            assignment=assignment,
            ingress=ingress,
            review_url=access.review_url,
            access=access,
        )

    def close(
        self,
        assignment_id: UUID,
        *,
        lease_token: UUID,
        reason: str,
        actor: str,
    ) -> ReviewerWorkAssignment:
        return self._assignments.close(
            assignment_id,
            lease_token=lease_token,
            reason=reason,
            actor=actor,
            before_close=self._revoke_assignment_session,
            before_expire=self._revoke_assignment_session,
            after_last_online_close=self._stop_shared_ingress_if_current,
        )

    def stop_if_unused(self) -> Sequence[ReviewerWorkAssignment]:
        return self._assignments.recover_expired_online(
            before_expire=self._revoke_assignment_session,
            after_last_online_close=self._stop_shared_ingress_if_current,
        )

    def _ensure_local_reviewer(self) -> ReviewerIngressStatus:
        status = self._ingress.status()
        if status.reviewer_ready is True and _is_local_target(status.target):
            return status
        started = self._ingress.start_local()
        if started.reviewer_ready is not True or not _is_local_target(started.target):
            raise ReviewerIngressError(
                "REVIEWER_INGRESS_NOT_READY",
                "Shared local Reviewer did not reach a ready loopback state.",
            )
        return started

    def _ensure_online_reviewer(self) -> ReviewerIngressStatus:
        status = self._ingress.status()
        if _is_ready_online(status):
            return status
        started = self._ingress.start()
        if not _is_ready_online(started):
            raise ReviewerIngressError(
                "REVIEWER_INGRESS_NOT_READY",
                "Shared Reviewer ingress did not reach a ready online state.",
            )
        return started

    def _revoke_assignment_session(self, assignment: ReviewerWorkAssignment) -> None:
        if assignment.reviewer_access_session_id is not None:
            self._access.revoke(assignment.reviewer_access_session_id)

    def _stop_shared_ingress_if_current(self) -> None:
        status = self._ingress.status()
        if status.instance_id is None:
            return
        self._ingress.stop_if_current(status.instance_id)


def _is_local_target(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "http"
        and parsed.hostname == "127.0.0.1"
        and parsed.port == 3001
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )


def _is_ready_online(status: ReviewerIngressStatus) -> bool:
    if (
        status.state != "running"
        or status.reviewer_ready is not True
        or not _is_local_target(status.target)
        or status.public_origin is None
    ):
        return False
    parsed = urlparse(status.public_origin)
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.hostname.endswith(".trycloudflare.com")
        and parsed.port is None
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )


def _local_review_url(*, game_id: UUID, import_job_id: UUID) -> str:
    parsed = urlparse(_LOCAL_REVIEWER_ORIGIN)
    query = urlencode(
        {
            "mode": "local",
            "gameId": str(game_id),
            "importJobId": str(import_job_id),
        }
    )
    return urlunparse(parsed._replace(path="/", query=query))


__all__ = [
    "OpenedReviewerWork",
    "ReviewerProcessLifecycle",
    "ReviewerWorkLifecycleService",
]
