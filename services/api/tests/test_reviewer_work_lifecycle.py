from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from game_predictor_api.application.reviewer_access import (
    InMemoryReviewerAccessRepository,
    ReviewerAccessService,
)
from game_predictor_api.application.reviewer_ingress import (
    ReviewerIngressError,
    ReviewerIngressStatus,
)
from game_predictor_api.application.reviewer_work_assignments import (
    InMemoryReviewerWorkAssignmentRepository,
    ReviewerWorkAssignmentService,
)
from game_predictor_api.application.reviewer_work_lifecycle import (
    ReviewerWorkLifecycleService,
)
from game_predictor_api.domain.reviewer_work_assignments import (
    ReviewerWorkAssignmentConflictError,
    ReviewerWorkAssignmentType,
)


def _now() -> datetime:
    return datetime(2026, 8, 20, 12, tzinfo=UTC)


class FakeSharedIngress:
    def __init__(self) -> None:
        self.online = False
        self.reviewer_ready = False
        self.calls: list[str] = []
        self.stop_calls = 0

    def status(self) -> ReviewerIngressStatus:
        self.calls.append("status")
        return self._status()

    def start(self) -> ReviewerIngressStatus:
        self.calls.append("start")
        self.online = True
        self.reviewer_ready = True
        return self._status()

    def start_local(self) -> ReviewerIngressStatus:
        self.calls.append("start_local")
        self.reviewer_ready = True
        return self._status()

    def stop(self) -> ReviewerIngressStatus:
        self.stop_calls += 1
        self.online = False
        self.reviewer_ready = False
        return self._status()

    def _status(self) -> ReviewerIngressStatus:
        return ReviewerIngressStatus(
            state="running" if self.online else "stopped",
            public_origin=("https://shared-reviewer.trycloudflare.com" if self.online else None),
            target="http://127.0.0.1:3001",
            started_at=_now() if self.reviewer_ready else None,
            reviewer_ready=self.reviewer_ready,
        )


def _services():
    clock = [_now()]
    assignment_repository = InMemoryReviewerWorkAssignmentRepository()
    access_repository = InMemoryReviewerAccessRepository()
    ingress = FakeSharedIngress()
    lifecycle = ReviewerWorkLifecycleService(
        ReviewerWorkAssignmentService(
            assignment_repository,
            now=lambda: clock[0],
        ),
        ReviewerAccessService(
            "http://127.0.0.1:3001",
            access_repository,
            now=lambda: clock[0],
        ),
        ingress,
    )
    return lifecycle, access_repository, ingress, clock


def test_online_scopes_share_one_ready_process_and_public_origin() -> None:
    lifecycle, _access_repository, ingress, _clock = _services()
    first = lifecycle.open_online(
        game_id=uuid4(),
        import_job_id=uuid4(),
        lease_owner="api-instance-a",
        lease_expires_at=_now() + timedelta(minutes=10),
        session_lifetime_minutes=60,
    )
    second = lifecycle.open_online(
        game_id=uuid4(),
        import_job_id=uuid4(),
        lease_owner="api-instance-a",
        lease_expires_at=_now() + timedelta(minutes=10),
        session_lifetime_minutes=60,
    )

    assert first.assignment.assignment_type is ReviewerWorkAssignmentType.ONLINE
    assert second.assignment.assignment_type is ReviewerWorkAssignmentType.ONLINE
    assert first.assignment.reviewer_access_session_id == first.access.session.id
    assert second.assignment.reviewer_access_session_id == second.access.session.id
    assert first.access.session.id != second.access.session.id
    assert first.review_url.startswith("https://shared-reviewer.trycloudflare.com/")
    assert second.review_url.startswith("https://shared-reviewer.trycloudflare.com/")
    assert ingress.calls == ["status", "start", "status"]


def test_local_scope_reuses_the_online_reviewer_without_creating_a_session() -> None:
    lifecycle, _access_repository, ingress, _clock = _services()
    lifecycle.open_online(
        game_id=uuid4(),
        import_job_id=uuid4(),
        lease_owner="api-instance-a",
        lease_expires_at=_now() + timedelta(minutes=10),
        session_lifetime_minutes=60,
    )
    game_id = uuid4()
    import_job_id = uuid4()

    local = lifecycle.open_local(
        game_id=game_id,
        import_job_id=import_job_id,
        lease_owner="api-instance-a",
        lease_expires_at=_now() + timedelta(minutes=10),
    )

    assert local.assignment.assignment_type is ReviewerWorkAssignmentType.LOCAL
    assert local.assignment.reviewer_access_session_id is None
    assert local.access is None
    assert local.review_url == (
        f"http://127.0.0.1:3001/?mode=local&gameId={game_id}&importJobId={import_job_id}"
    )
    assert ingress.calls == ["status", "start", "status"]


def test_closing_one_online_assignment_revokes_only_its_session() -> None:
    lifecycle, access_repository, ingress, _clock = _services()
    first = lifecycle.open_online(
        game_id=uuid4(),
        import_job_id=uuid4(),
        lease_owner="api-instance-a",
        lease_expires_at=_now() + timedelta(minutes=10),
        session_lifetime_minutes=60,
    )
    second = lifecycle.open_online(
        game_id=uuid4(),
        import_job_id=uuid4(),
        lease_owner="api-instance-a",
        lease_expires_at=_now() + timedelta(minutes=10),
        session_lifetime_minutes=60,
    )

    closed = lifecycle.close(
        first.assignment.id,
        lease_token=first.assignment.lease_token,
        reason="owner_stopped",
        actor="local-admin",
    )

    first_session = access_repository.get_for_update(first.access.session.id)
    second_session = access_repository.get_for_update(second.access.session.id)
    assert closed.is_active is False
    assert first_session is not None and first_session.revoked_at == _now()
    assert second_session is not None and second_session.revoked_at is None
    assert ingress.stop_calls == 0


def test_failed_second_assignment_revokes_its_new_session_without_stopping_ingress() -> None:
    lifecycle, access_repository, ingress, _clock = _services()
    game_id = uuid4()
    import_job_id = uuid4()
    lifecycle.open_local(
        game_id=game_id,
        import_job_id=import_job_id,
        lease_owner="api-instance-a",
        lease_expires_at=_now() + timedelta(minutes=10),
    )

    with pytest.raises(ReviewerWorkAssignmentConflictError):
        lifecycle.open_online(
            game_id=game_id,
            import_job_id=import_job_id,
            lease_owner="api-instance-b",
            lease_expires_at=_now() + timedelta(minutes=10),
            session_lifetime_minutes=60,
        )

    created_events = [
        event
        for session_id in tuple(access_repository._sessions)  # noqa: SLF001
        for event in access_repository.list_audit(session_id)
        if event.event_type == "created"
    ]
    assert len(created_events) == 1
    session = access_repository.get_for_update(created_events[0].session_id)
    assert session is not None and session.revoked_at == _now()
    assert ingress.stop_calls == 0


def test_invalid_online_ingress_fails_before_session_or_assignment_creation() -> None:
    lifecycle, access_repository, ingress, _clock = _services()

    def invalid_start() -> ReviewerIngressStatus:
        ingress.calls.append("start")
        return ReviewerIngressStatus(
            state="running",
            public_origin="https://example.invalid",
            target="http://127.0.0.1:3001",
            started_at=_now(),
            reviewer_ready=True,
        )

    ingress.start = invalid_start  # type: ignore[method-assign]
    with pytest.raises(ReviewerIngressError) as raised:
        lifecycle.open_online(
            game_id=uuid4(),
            import_job_id=uuid4(),
            lease_owner="api-instance-a",
            lease_expires_at=_now() + timedelta(minutes=10),
            session_lifetime_minutes=60,
        )

    assert raised.value.code == "REVIEWER_INGRESS_NOT_READY"
    assert access_repository._sessions == {}  # noqa: SLF001
    assert ingress.stop_calls == 0
