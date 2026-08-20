from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from game_predictor_api.application.reviewer_work_assignments import (
    InMemoryReviewerWorkAssignmentRepository,
    ReviewerWorkAssignmentService,
)
from game_predictor_api.domain.reviewer_work_assignments import (
    ReviewerWorkAssignment,
    ReviewerWorkAssignmentConflictError,
    ReviewerWorkAssignmentError,
    ReviewerWorkAssignmentType,
    close_reviewer_work_assignment,
    create_reviewer_work_assignment,
    expire_reviewer_work_assignment,
    renew_reviewer_work_assignment,
)


def _now() -> datetime:
    return datetime(2026, 8, 20, 12, tzinfo=UTC)


def _assignment() -> ReviewerWorkAssignment:
    now = _now()
    return create_reviewer_work_assignment(
        game_id=uuid4(),
        import_job_id=uuid4(),
        assignment_type=ReviewerWorkAssignmentType.LOCAL,
        lease_owner="api-instance-a",
        lease_expires_at=now + timedelta(seconds=30),
        created_at=now,
    )


def test_assignment_lease_is_fenced_and_heartbeat_is_monotonic() -> None:
    assignment = _assignment()
    heartbeat_at = _now() + timedelta(seconds=10)
    renewed = renew_reviewer_work_assignment(
        assignment,
        lease_token=assignment.lease_token,
        heartbeat_at=heartbeat_at,
        lease_expires_at=heartbeat_at + timedelta(seconds=30),
    )

    assert renewed.heartbeat_at == heartbeat_at
    assert renewed.lease_expires_at == heartbeat_at + timedelta(seconds=30)
    with pytest.raises(ReviewerWorkAssignmentConflictError) as wrong_token:
        renew_reviewer_work_assignment(
            renewed,
            lease_token=uuid4(),
            heartbeat_at=heartbeat_at + timedelta(seconds=1),
            lease_expires_at=heartbeat_at + timedelta(seconds=31),
        )
    assert wrong_token.value.code == "REVIEWER_ASSIGNMENT_LEASE_LOST"

    with pytest.raises(ReviewerWorkAssignmentError) as regressed:
        renew_reviewer_work_assignment(
            renewed,
            lease_token=renewed.lease_token,
            heartbeat_at=heartbeat_at - timedelta(seconds=1),
            lease_expires_at=heartbeat_at + timedelta(seconds=31),
        )
    assert regressed.value.code == "REVIEWER_ASSIGNMENT_HEARTBEAT_REGRESSION"


def test_closed_assignment_keeps_scope_lease_and_closure_history() -> None:
    assignment = _assignment()
    closed_at = _now() + timedelta(seconds=5)
    closed = close_reviewer_work_assignment(
        assignment,
        lease_token=assignment.lease_token,
        reason="owner_stopped",
        actor="local-admin",
        closed_at=closed_at,
    )

    assert closed.is_active is False
    assert closed.game_id == assignment.game_id
    assert closed.import_job_id == assignment.import_job_id
    assert closed.lease_token == assignment.lease_token
    assert closed.closed_at == closed_at
    assert closed.close_reason == "owner_stopped"
    assert closed.closed_by == "local-admin"
    assert (
        close_reviewer_work_assignment(
            closed,
            lease_token=assignment.lease_token,
            reason="owner_stopped",
            actor="local-admin",
            closed_at=closed_at + timedelta(seconds=1),
        )
        == closed
    )


def test_expiration_is_fail_closed_until_the_lease_really_expires() -> None:
    assignment = _assignment()
    with pytest.raises(ReviewerWorkAssignmentConflictError) as not_expired:
        expire_reviewer_work_assignment(
            assignment,
            actor="recovery",
            expired_at=_now() + timedelta(seconds=29),
        )
    assert not_expired.value.code == "REVIEWER_ASSIGNMENT_LEASE_NOT_EXPIRED"

    expired = expire_reviewer_work_assignment(
        assignment,
        actor="recovery",
        expired_at=_now() + timedelta(seconds=30),
    )
    assert expired.close_reason == "lease_expired"
    assert expired.closed_by == "recovery"


def test_service_allows_only_one_active_assignment_and_preserves_reopen_history() -> None:
    clock = [_now()]
    repository = InMemoryReviewerWorkAssignmentRepository()
    service = ReviewerWorkAssignmentService(repository, now=lambda: clock[0])
    game_id = uuid4()
    import_job_id = uuid4()
    first = service.open(
        game_id=game_id,
        import_job_id=import_job_id,
        assignment_type=ReviewerWorkAssignmentType.ONLINE,
        lease_owner="api-instance-a",
        lease_expires_at=clock[0] + timedelta(seconds=30),
    )

    with pytest.raises(ReviewerWorkAssignmentConflictError) as active:
        service.open(
            game_id=game_id,
            import_job_id=import_job_id,
            assignment_type=ReviewerWorkAssignmentType.LOCAL,
            lease_owner="api-instance-b",
            lease_expires_at=clock[0] + timedelta(seconds=30),
        )
    assert active.value.code == "REVIEWER_ASSIGNMENT_ALREADY_ACTIVE"

    clock[0] += timedelta(seconds=5)
    closed = service.close(
        first.id,
        lease_token=first.lease_token,
        reason="owner_stopped",
        actor="local-admin",
    )
    clock[0] += timedelta(seconds=1)
    second = service.open(
        game_id=game_id,
        import_job_id=import_job_id,
        assignment_type=ReviewerWorkAssignmentType.LOCAL,
        lease_owner="api-instance-b",
        lease_expires_at=clock[0] + timedelta(seconds=30),
    )

    assert closed.is_active is False
    assert second.is_active is True
    assert [item.id for item in service.list_history(import_job_id)] == [
        first.id,
        second.id,
    ]


def test_open_recovers_an_expired_assignment_before_creating_its_successor() -> None:
    clock = [_now()]
    repository = InMemoryReviewerWorkAssignmentRepository()
    service = ReviewerWorkAssignmentService(repository, now=lambda: clock[0])
    game_id = uuid4()
    import_job_id = uuid4()
    first = service.open(
        game_id=game_id,
        import_job_id=import_job_id,
        assignment_type=ReviewerWorkAssignmentType.ONLINE,
        lease_owner="api-instance-a",
        lease_expires_at=clock[0] + timedelta(seconds=10),
    )

    clock[0] += timedelta(seconds=10)
    second = service.open(
        game_id=game_id,
        import_job_id=import_job_id,
        assignment_type=ReviewerWorkAssignmentType.ONLINE,
        lease_owner="api-instance-b",
        lease_expires_at=clock[0] + timedelta(seconds=10),
    )
    history = service.list_history(import_job_id)

    assert second.id != first.id
    assert history[0].close_reason == "lease_expired"
    assert history[0].closed_by == "reviewer-assignment-recovery"
    assert history[1] == second


def test_assignment_rejects_naive_timestamps_and_blank_lease_owner() -> None:
    with pytest.raises(ReviewerWorkAssignmentError) as naive:
        create_reviewer_work_assignment(
            game_id=uuid4(),
            import_job_id=uuid4(),
            assignment_type=ReviewerWorkAssignmentType.LOCAL,
            lease_owner="api-instance-a",
            lease_expires_at=datetime(2026, 8, 20, 12, 1),
            created_at=datetime(2026, 8, 20, 12),
        )
    assert naive.value.code == "REVIEWER_ASSIGNMENT_TIMESTAMP_INVALID"

    with pytest.raises(ReviewerWorkAssignmentError) as blank_owner:
        create_reviewer_work_assignment(
            game_id=uuid4(),
            import_job_id=uuid4(),
            assignment_type=ReviewerWorkAssignmentType.LOCAL,
            lease_owner="  ",
            lease_expires_at=_now() + timedelta(seconds=30),
            created_at=_now(),
        )
    assert blank_owner.value.code == "REVIEWER_ASSIGNMENT_VALUE_INVALID"


def test_service_rejects_a_scope_that_is_not_a_ready_image_import() -> None:
    class RejectingScopeRepository(InMemoryReviewerWorkAssignmentRepository):
        def lock_scope(self, _game_id, _import_job_id) -> bool:
            return False

    service = ReviewerWorkAssignmentService(RejectingScopeRepository(), now=_now)
    with pytest.raises(ReviewerWorkAssignmentError) as invalid_scope:
        service.open(
            game_id=uuid4(),
            import_job_id=uuid4(),
            assignment_type=ReviewerWorkAssignmentType.LOCAL,
            lease_owner="api-instance-a",
            lease_expires_at=_now() + timedelta(seconds=30),
        )
    assert invalid_scope.value.code == "REVIEWER_ASSIGNMENT_SCOPE_INVALID"
