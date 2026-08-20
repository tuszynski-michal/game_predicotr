from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
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
        self.instance_id = None
        self.start_count = 0

    def status(self) -> ReviewerIngressStatus:
        self.calls.append("status")
        return self._status()

    def start(self) -> ReviewerIngressStatus:
        self.calls.append("start")
        self.start_count += 1
        self.online = True
        self.reviewer_ready = True
        self.instance_id = uuid4()
        return self._status()

    def start_local(self) -> ReviewerIngressStatus:
        self.calls.append("start_local")
        self.reviewer_ready = True
        return self._status()

    def stop(self) -> ReviewerIngressStatus:
        self.stop_calls += 1
        self.online = False
        self.instance_id = None
        return self._status()

    def stop_if_current(self, instance_id) -> ReviewerIngressStatus:
        self.calls.append("stop_if_current")
        if instance_id == self.instance_id:
            return self.stop()
        return self._status()

    def _status(self) -> ReviewerIngressStatus:
        return ReviewerIngressStatus(
            state="running" if self.online else "stopped",
            public_origin=(
                "https://shared-reviewer.trycloudflare.com"
                if self.online and self.start_count == 1
                else (
                    f"https://shared-reviewer-{self.start_count}.trycloudflare.com"
                    if self.online
                    else None
                )
            ),
            target="http://127.0.0.1:3001",
            started_at=_now() if self.reviewer_ready else None,
            reviewer_ready=self.reviewer_ready,
            instance_id=self.instance_id,
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


def test_reopening_same_online_scope_is_idempotent_without_revealing_code_again() -> None:
    lifecycle, access_repository, ingress, _clock = _services()
    game_id = uuid4()
    import_job_id = uuid4()
    first = lifecycle.open_online(
        game_id=game_id,
        import_job_id=import_job_id,
        lease_owner="api-instance-a",
        lease_expires_at=_now() + timedelta(minutes=10),
        session_lifetime_minutes=60,
    )

    reopened = lifecycle.open_online(
        game_id=game_id,
        import_job_id=import_job_id,
        lease_owner="api-instance-b",
        lease_expires_at=_now() + timedelta(minutes=10),
        session_lifetime_minutes=60,
    )

    assert first.created is True
    assert reopened.created is False
    assert reopened.assignment.id == first.assignment.id
    assert reopened.access is None
    assert reopened.review_url == first.review_url
    assert len(access_repository._sessions) == 1  # noqa: SLF001
    assert ingress.start_count == 1


def test_reopening_same_local_scope_is_idempotent() -> None:
    lifecycle, _access_repository, ingress, _clock = _services()
    game_id = uuid4()
    import_job_id = uuid4()

    first = lifecycle.open_local(
        game_id=game_id,
        import_job_id=import_job_id,
        lease_owner="api-instance-a",
        lease_expires_at=_now() + timedelta(minutes=10),
    )
    reopened = lifecycle.open_local(
        game_id=game_id,
        import_job_id=import_job_id,
        lease_owner="api-instance-b",
        lease_expires_at=_now() + timedelta(minutes=10),
    )

    assert first.created is True
    assert reopened.created is False
    assert reopened.assignment.id == first.assignment.id
    assert reopened.review_url == first.review_url
    assert ingress.start_count == 0


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


def test_occupied_import_is_rejected_before_creating_an_online_session() -> None:
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

    assert access_repository._sessions == {}  # noqa: SLF001
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


def test_online_limit_is_three_and_fourth_scope_creates_no_session() -> None:
    lifecycle, access_repository, ingress, _clock = _services()
    opened = [
        lifecycle.open_online(
            game_id=uuid4(),
            import_job_id=uuid4(),
            lease_owner=f"api-instance-{index}",
            lease_expires_at=_now() + timedelta(minutes=10),
            session_lifetime_minutes=60,
        )
        for index in range(3)
    ]

    with pytest.raises(ReviewerWorkAssignmentConflictError) as limit:
        lifecycle.open_online(
            game_id=uuid4(),
            import_job_id=uuid4(),
            lease_owner="api-instance-four",
            lease_expires_at=_now() + timedelta(minutes=10),
            session_lifetime_minutes=60,
        )

    assert limit.value.code == "REVIEWER_ASSIGNMENT_ONLINE_LIMIT_REACHED"
    assert limit.value.details == {
        "activeOnlineCount": 3,
        "maximumOnlineCount": 3,
    }
    assert len(access_repository._sessions) == 3  # noqa: SLF001
    assert all(item.access is not None for item in opened)
    assert ingress.calls == ["status", "start", "status", "status"]


def test_local_assignment_does_not_consume_online_capacity() -> None:
    lifecycle, access_repository, ingress, _clock = _services()
    local = lifecycle.open_local(
        game_id=uuid4(),
        import_job_id=uuid4(),
        lease_owner="local-owner",
        lease_expires_at=_now() + timedelta(minutes=10),
    )
    online = [
        lifecycle.open_online(
            game_id=uuid4(),
            import_job_id=uuid4(),
            lease_owner=f"online-owner-{index}",
            lease_expires_at=_now() + timedelta(minutes=10),
            session_lifetime_minutes=60,
        )
        for index in range(3)
    ]

    assert local.assignment.assignment_type is ReviewerWorkAssignmentType.LOCAL
    assert len(online) == 3
    assert len(access_repository._sessions) == 3  # noqa: SLF001
    assert ingress.start_count == 1


def test_only_closing_the_last_online_assignment_stops_its_ingress_instance() -> None:
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
        lease_owner="api-instance-b",
        lease_expires_at=_now() + timedelta(minutes=10),
        session_lifetime_minutes=60,
    )
    first_instance = first.ingress.instance_id

    lifecycle.close(
        first.assignment.id,
        lease_token=first.assignment.lease_token,
        reason="owner_stopped",
        actor="local-admin",
    )
    assert ingress.stop_calls == 0

    lifecycle.close(
        second.assignment.id,
        lease_token=second.assignment.lease_token,
        reason="owner_stopped",
        actor="local-admin",
    )

    assert ingress.stop_calls == 1
    assert ingress.online is False
    assert first_instance is not None
    assert all(
        session.revoked_at == _now()
        for session in access_repository._sessions.values()  # noqa: SLF001
    )


def test_expired_online_assignments_are_revoked_and_last_one_stops_ingress() -> None:
    lifecycle, access_repository, ingress, clock = _services()
    for index in range(3):
        lifecycle.open_online(
            game_id=uuid4(),
            import_job_id=uuid4(),
            lease_owner=f"api-instance-{index}",
            lease_expires_at=_now() + timedelta(seconds=10),
            session_lifetime_minutes=60,
        )
    clock[0] += timedelta(seconds=10)

    expired = lifecycle.stop_if_unused()

    assert len(expired) == 3
    assert {item.close_reason for item in expired} == {"lease_expired"}
    assert ingress.stop_calls == 1
    assert all(
        session.revoked_at == clock[0]
        for session in access_repository._sessions.values()  # noqa: SLF001
    )


def test_new_online_scope_reclaims_expired_capacity_without_stopping_shared_ingress() -> None:
    lifecycle, access_repository, ingress, clock = _services()
    expired = [
        lifecycle.open_online(
            game_id=uuid4(),
            import_job_id=uuid4(),
            lease_owner=f"api-instance-{index}",
            lease_expires_at=_now() + timedelta(seconds=10),
            session_lifetime_minutes=60,
        )
        for index in range(3)
    ]
    clock[0] += timedelta(seconds=10)

    replacement = lifecycle.open_online(
        game_id=uuid4(),
        import_job_id=uuid4(),
        lease_owner="replacement-owner",
        lease_expires_at=clock[0] + timedelta(minutes=10),
        session_lifetime_minutes=60,
    )

    assert replacement.assignment.is_active is True
    assert ingress.stop_calls == 0
    assert ingress.start_count == 1
    for item in expired:
        session = access_repository.get_for_update(item.access.session.id)
        assert session is not None and session.revoked_at == clock[0]
    replacement_session = access_repository.get_for_update(replacement.access.session.id)
    assert replacement_session is not None and replacement_session.revoked_at is None


def test_concurrent_open_waits_for_last_close_and_uses_the_new_ingress() -> None:
    lifecycle, _access_repository, ingress, _clock = _services()
    first = lifecycle.open_online(
        game_id=uuid4(),
        import_job_id=uuid4(),
        lease_owner="api-instance-a",
        lease_expires_at=_now() + timedelta(minutes=10),
        session_lifetime_minutes=60,
    )
    stop_entered = Event()
    allow_stop = Event()
    original_stop_if_current = ingress.stop_if_current

    def blocking_stop_if_current(instance_id):
        stop_entered.set()
        assert allow_stop.wait(timeout=3)
        return original_stop_if_current(instance_id)

    ingress.stop_if_current = blocking_stop_if_current  # type: ignore[method-assign]

    with ThreadPoolExecutor(max_workers=2) as executor:
        closing = executor.submit(
            lifecycle.close,
            first.assignment.id,
            lease_token=first.assignment.lease_token,
            reason="owner_stopped",
            actor="local-admin",
        )
        assert stop_entered.wait(timeout=3)
        opening = executor.submit(
            lifecycle.open_online,
            game_id=uuid4(),
            import_job_id=uuid4(),
            lease_owner="api-instance-b",
            lease_expires_at=_now() + timedelta(minutes=10),
            session_lifetime_minutes=60,
        )
        assert opening.done() is False
        allow_stop.set()
        closed = closing.result(timeout=3)
        reopened = opening.result(timeout=3)

    assert closed.is_active is False
    assert reopened.assignment.is_active is True
    assert reopened.ingress.instance_id != first.ingress.instance_id
    assert reopened.review_url.startswith("https://shared-reviewer-2.trycloudflare.com/")
    assert ingress.stop_calls == 1
