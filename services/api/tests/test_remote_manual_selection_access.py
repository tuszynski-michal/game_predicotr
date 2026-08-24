from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.access_credentials import (
    PBKDF2_SHA256_ITERATIONS,
    hash_access_code,
    hash_access_token,
)
from game_predictor_api.application.remote_manual_selection_access import (
    RemoteManualSelectionAccessError,
    RemoteManualSelectionAccessService,
    RemoteManualSelectionAuthenticationError,
    RemoteManualSelectionLeaseConflictError,
)
from game_predictor_api.application.remote_manual_selection_host import (
    ConsumedRemoteManualSelectionBase,
)
from game_predictor_api.storage.remote_manual_selection_access_repository import (
    InMemoryRemoteManualSelectionAccessRepository,
)


class FakeHostService:
    def __init__(self) -> None:
        self.capability = "base-capability"
        self.consumed = False

    def consume_base_capability(self, capability: str) -> ConsumedRemoteManualSelectionBase:
        if self.consumed or capability != self.capability:
            raise RemoteManualSelectionAccessError("INVALID_CAPABILITY", "Invalid capability.")
        self.consumed = True
        return ConsumedRemoteManualSelectionBase(
            base_binding_id=UUID(int=99),
            host_base_path=Path(r"C:\Users\owner\Documents"),
            display_name="Documents",
        )


def _service(
    *,
    now: datetime | None = None,
) -> tuple[
    RemoteManualSelectionAccessService,
    InMemoryRemoteManualSelectionAccessRepository,
    FakeHostService,
    list[datetime],
]:
    repository = InMemoryRemoteManualSelectionAccessRepository()
    host = FakeHostService()
    clock = [now or datetime(2026, 8, 24, 10, 0, tzinfo=UTC)]
    return (
        RemoteManualSelectionAccessService(repository, host, now=lambda: clock[0]),
        repository,
        host,
        clock,
    )


def _created(
    service: RemoteManualSelectionAccessService,
    host: FakeHostService,
    *,
    lifetime_minutes: int = 60,
):
    return service.create(
        base_capability=host.capability,
        lifetime_minutes=lifetime_minutes,
    )


def test_create_consumes_capability_once_and_persists_only_hashes() -> None:
    service, repository, host, _clock = _service()

    created = _created(service, host)
    record = repository.records[created.session.session_id]

    assert len(created.access_code) == 9
    assert created.access_code.encode() != record.code_hash
    assert record.code_hash == hash_access_code(created.access_code, record.code_salt)
    assert record.host_base_path == r"C:\Users\owner\Documents"
    assert "host_base_path" not in created.session.__dataclass_fields__
    assert PBKDF2_SHA256_ITERATIONS == 210_000
    with pytest.raises(RemoteManualSelectionAccessError):
        _created(service, host)


@pytest.mark.parametrize("lifetime_minutes", [4, 1441])
def test_create_rejects_lifetime_outside_five_minutes_to_twenty_four_hours(
    lifetime_minutes: int,
) -> None:
    service, _repository, host, _clock = _service()

    with pytest.raises(RemoteManualSelectionAccessError) as captured:
        _created(service, host, lifetime_minutes=lifetime_minutes)

    assert captured.value.code == "REMOTE_SELECTION_SESSION_LIFETIME_INVALID"
    assert host.consumed is False


def test_fifth_failed_attempt_locks_and_clears_token_and_writer_lease() -> None:
    service, repository, host, _clock = _service()
    created = _created(service, host)
    client_id = uuid4()
    unlocked = service.unlock(
        session_id=created.session.session_id,
        access_code=created.access_code,
        client_instance_id=client_id,
    )

    for _attempt in range(4):
        with pytest.raises(RemoteManualSelectionAuthenticationError) as captured:
            service.unlock(
                session_id=created.session.session_id,
                access_code="WRONG-CODE",
                client_instance_id=client_id,
            )
        assert captured.value.code == "REMOTE_SELECTION_ACCESS_CODE_INVALID"
    with pytest.raises(RemoteManualSelectionAuthenticationError) as locked:
        service.unlock(
            session_id=created.session.session_id,
            access_code="WRONG-CODE",
            client_instance_id=client_id,
        )
    assert locked.value.code == "REMOTE_SELECTION_SESSION_LOCKED"
    record = repository.records[created.session.session_id]
    assert record.failed_attempts == 5
    assert record.token_hash is None
    assert record.writer_client_instance_id is None
    with pytest.raises(RemoteManualSelectionAuthenticationError):
        service.context(access_token=unlocked.access_token, client_instance_id=client_id)


def test_unlock_rotates_token_and_does_not_expose_game_or_import_scope() -> None:
    service, _repository, host, _clock = _service()
    created = _created(service, host)
    first_client = uuid4()
    second_client = uuid4()
    first = service.unlock(
        session_id=created.session.session_id,
        access_code=created.access_code,
        client_instance_id=first_client,
    )
    second = service.unlock(
        session_id=created.session.session_id,
        access_code=created.access_code,
        client_instance_id=second_client,
    )

    assert first.access_token != second.access_token
    with pytest.raises(RemoteManualSelectionAuthenticationError):
        service.context(access_token=first.access_token, client_instance_id=first_client)
    context = service.context(
        access_token=second.access_token,
        client_instance_id=second_client,
    )
    assert context.session_id == created.session.session_id
    assert context.is_writer is False
    assert "game_id" not in context.__dataclass_fields__
    assert "import_job_id" not in context.__dataclass_fields__


def test_writer_lease_is_exclusive_and_takeover_waits_for_expiry() -> None:
    service, _repository, host, clock = _service()
    created = _created(service, host)
    first_client = uuid4()
    second_client = uuid4()
    first = service.unlock(
        session_id=created.session.session_id,
        access_code=created.access_code,
        client_instance_id=first_client,
    )
    second = service.unlock(
        session_id=created.session.session_id,
        access_code=created.access_code,
        client_instance_id=second_client,
    )
    assert first.context.is_writer is True
    assert second.context.is_writer is False

    with pytest.raises(RemoteManualSelectionLeaseConflictError) as active:
        service.takeover(
            session_id=created.session.session_id,
            access_token=second.access_token,
            client_instance_id=second_client,
        )
    assert active.value.code == "REMOTE_SELECTION_WRITER_LEASE_ACTIVE"

    clock[0] += timedelta(seconds=46)
    taken = service.takeover(
        session_id=created.session.session_id,
        access_token=second.access_token,
        client_instance_id=second_client,
    )
    assert taken.is_writer is True


def test_writer_heartbeat_is_idempotent_at_same_clock_and_preserves_fencing_token() -> None:
    service, repository, host, clock = _service()
    created = _created(service, host)
    client_id = uuid4()
    unlocked = service.unlock(
        session_id=created.session.session_id,
        access_code=created.access_code,
        client_instance_id=client_id,
    )
    initial = repository.records[created.session.session_id]
    initial_token = initial.writer_lease_token
    initial_revision = initial.session.revision

    first = service.heartbeat(
        session_id=created.session.session_id,
        access_token=unlocked.access_token,
        client_instance_id=client_id,
    )
    second = service.heartbeat(
        session_id=created.session.session_id,
        access_token=unlocked.access_token,
        client_instance_id=client_id,
    )

    assert first == second
    current = repository.records[created.session.session_id]
    assert current.writer_lease_token == initial_token
    assert current.session.revision == initial_revision
    clock[0] += timedelta(seconds=10)
    renewed = service.heartbeat(
        session_id=created.session.session_id,
        access_token=unlocked.access_token,
        client_instance_id=client_id,
    )
    assert renewed.writer_lease_expires_at > first.writer_lease_expires_at
    assert repository.records[created.session.session_id].writer_lease_token == initial_token


def test_control_authorization_requires_the_current_unexpired_writer() -> None:
    service, _repository, host, clock = _service()
    created = _created(service, host)
    client_id = uuid4()
    unlocked = service.unlock(
        session_id=created.session.session_id,
        access_code=created.access_code,
        client_instance_id=client_id,
    )

    authorized = service.authorize_writer(
        session_id=created.session.session_id,
        access_token=unlocked.access_token,
        client_instance_id=client_id,
    )
    assert authorized.is_writer is True

    clock[0] += timedelta(seconds=46)
    with pytest.raises(RemoteManualSelectionLeaseConflictError) as expired:
        service.authorize_writer(
            session_id=created.session.session_id,
            access_token=unlocked.access_token,
            client_instance_id=client_id,
        )
    assert expired.value.code == "REMOTE_SELECTION_WRITER_LEASE_LOST"


def test_revoke_is_immediate_idempotent_and_redacted() -> None:
    service, repository, host, _clock = _service()
    created = _created(service, host)
    client_id = uuid4()
    unlocked = service.unlock(
        session_id=created.session.session_id,
        access_code=created.access_code,
        client_instance_id=client_id,
    )

    revoked = service.revoke(created.session.session_id)
    replay = service.revoke(created.session.session_id)

    assert revoked == replay
    with pytest.raises(RemoteManualSelectionAuthenticationError):
        service.context(access_token=unlocked.access_token, client_instance_id=client_id)
    record = repository.records[created.session.session_id]
    assert record.token_hash is None
    assert record.writer_lease_token is None
    serialized_audit = repr(repository.audit_events)
    assert created.access_code not in serialized_audit
    assert unlocked.access_token not in serialized_audit
    assert record.host_base_path not in serialized_audit


def test_expired_session_fails_closed_and_admin_projection_reports_expired() -> None:
    service, _repository, host, clock = _service()
    created = _created(service, host, lifetime_minutes=5)
    clock[0] += timedelta(minutes=6)

    with pytest.raises(RemoteManualSelectionAccessError) as expired:
        service.unlock(
            session_id=created.session.session_id,
            access_code=created.access_code,
            client_instance_id=uuid4(),
        )

    assert expired.value.code == "REMOTE_SELECTION_SESSION_NOT_FOUND"
    assert service.get_session(created.session.session_id).status.value == "expired"


def test_access_token_is_persisted_only_as_sha256() -> None:
    service, repository, host, _clock = _service()
    created = _created(service, host)
    unlocked = service.unlock(
        session_id=created.session.session_id,
        access_code=created.access_code,
        client_instance_id=uuid4(),
    )

    record = repository.records[created.session.session_id]
    assert record.token_hash == hash_access_token(unlocked.access_token)
    assert unlocked.access_token.encode() != record.token_hash
