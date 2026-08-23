"""Purpose-scoped access lifecycle for remote manual image selection."""

from __future__ import annotations

import hmac
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from game_predictor_api.application.access_credentials import (
    generate_access_code,
    generate_access_token,
    generate_code_salt,
    hash_access_code,
    hash_access_token,
)
from game_predictor_api.application.remote_manual_selection_host import (
    ConsumedRemoteManualSelectionBase,
)
from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionError,
    RemoteManualSelectionSessionStatus,
    RemoteManualSelectionSessionV1,
)

MIN_SESSION_LIFETIME_MINUTES = 5
MAX_SESSION_LIFETIME_MINUTES = 24 * 60
MAX_FAILED_ACCESS_ATTEMPTS = 5
WRITER_LEASE_DURATION = timedelta(seconds=45)
REMOTE_SELECTION_COOKIE_NAME = "remote_manual_selection_access"
REMOTE_SELECTION_COOKIE_PATH = "/selection-api"
REMOTE_SELECTION_PROXY_INTENT = "reviewer-v1"


class RemoteManualSelectionAccessError(RemoteManualSelectionError):
    """Base error for the purpose-scoped access boundary."""


class RemoteManualSelectionAccessNotFoundError(RemoteManualSelectionAccessError):
    pass


class RemoteManualSelectionAuthenticationError(RemoteManualSelectionAccessError):
    pass


class RemoteManualSelectionAuthorizationError(RemoteManualSelectionAccessError):
    pass


class RemoteManualSelectionLeaseConflictError(RemoteManualSelectionAccessError):
    pass


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionAccessRecord:
    """Host-internal persistence record; never use as an HTTP response DTO."""

    session: RemoteManualSelectionSessionV1
    base_binding_id: UUID
    host_base_path: str
    display_name: str
    code_salt: bytes
    code_hash: bytes
    failed_attempts: int
    locked_at: datetime | None
    revoked_at: datetime | None
    token_hash: bytes | None
    token_expires_at: datetime | None
    writer_client_instance_id: UUID | None
    writer_lease_token: UUID | None
    writer_lease_expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionAccessView:
    session_id: UUID
    status: RemoteManualSelectionSessionStatus
    revision: int
    display_name: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    locked_at: datetime | None
    revoked_at: datetime | None
    writer_active: bool
    writer_lease_expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionContext:
    session_id: UUID
    status: RemoteManualSelectionSessionStatus
    revision: int
    expires_at: datetime
    is_writer: bool
    writer_active: bool
    writer_lease_expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class CreatedRemoteManualSelectionAccess:
    session: RemoteManualSelectionAccessView
    access_code: str


@dataclass(frozen=True, slots=True)
class UnlockedRemoteManualSelectionAccess:
    context: RemoteManualSelectionContext
    access_token: str


class RemoteManualSelectionAccessRepository(Protocol):
    def add_access_session(
        self,
        record: RemoteManualSelectionAccessRecord,
    ) -> RemoteManualSelectionAccessRecord: ...

    def get_access_session(
        self,
        session_id: UUID,
    ) -> RemoteManualSelectionAccessRecord | None: ...

    def get_access_session_for_update(
        self,
        session_id: UUID,
    ) -> RemoteManualSelectionAccessRecord | None: ...

    def find_access_session_by_token_hash(
        self,
        token_hash: bytes,
    ) -> RemoteManualSelectionAccessRecord | None: ...

    def save_access_session(
        self,
        record: RemoteManualSelectionAccessRecord,
    ) -> RemoteManualSelectionAccessRecord: ...

    def list_access_sessions(
        self,
        *,
        limit: int,
    ) -> Sequence[RemoteManualSelectionAccessRecord]: ...

    def append_access_audit(
        self,
        *,
        session_id: UUID,
        event_type: str,
        actor: str,
        outcome_code: str,
        payload: dict[str, object],
        created_at: datetime,
    ) -> None: ...


class RemoteManualSelectionBaseConsumer(Protocol):
    def consume_base_capability(
        self,
        capability: str,
    ) -> ConsumedRemoteManualSelectionBase: ...


class RemoteManualSelectionAccessService:
    """Create, unlock, authenticate, lease and revoke one purpose-scoped session."""

    def __init__(
        self,
        repository: RemoteManualSelectionAccessRepository,
        host_service: RemoteManualSelectionBaseConsumer,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._host_service = host_service
        self._now = now or (lambda: datetime.now(UTC))

    def create(
        self,
        *,
        base_capability: str,
        lifetime_minutes: int,
    ) -> CreatedRemoteManualSelectionAccess:
        if not MIN_SESSION_LIFETIME_MINUTES <= lifetime_minutes <= MAX_SESSION_LIFETIME_MINUTES:
            raise RemoteManualSelectionAccessError(
                "REMOTE_SELECTION_SESSION_LIFETIME_INVALID",
                "Remote selection session lifetime must be between 5 minutes and 24 hours.",
            )
        bound = self._host_service.consume_base_capability(base_capability)
        now = self._now()
        code = generate_access_code()
        salt = generate_code_salt()
        session = RemoteManualSelectionSessionV1(
            id=uuid4(),
            status=RemoteManualSelectionSessionStatus.ACTIVE,
            revision=0,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(minutes=lifetime_minutes),
        )
        record = self._repository.add_access_session(
            RemoteManualSelectionAccessRecord(
                session=session,
                base_binding_id=bound.base_binding_id,
                host_base_path=str(bound.host_base_path),
                display_name=bound.display_name,
                code_salt=salt,
                code_hash=hash_access_code(code, salt),
                failed_attempts=0,
                locked_at=None,
                revoked_at=None,
                token_hash=None,
                token_expires_at=None,
                writer_client_instance_id=None,
                writer_lease_token=None,
                writer_lease_expires_at=None,
            )
        )
        self._audit(
            record,
            event_type="created",
            actor="local-owner",
            outcome_code="REMOTE_SELECTION_SESSION_CREATED",
            payload={"lifetimeMinutes": lifetime_minutes},
            now=now,
        )
        return CreatedRemoteManualSelectionAccess(self._view(record, now), code)

    def list_sessions(self, *, limit: int = 100) -> tuple[RemoteManualSelectionAccessView, ...]:
        if not 1 <= limit <= 100:
            raise RemoteManualSelectionAccessError(
                "REMOTE_SELECTION_LIST_LIMIT_INVALID",
                "Remote selection session list limit must be between 1 and 100.",
            )
        now = self._now()
        return tuple(
            self._view(record, now) for record in self._repository.list_access_sessions(limit=limit)
        )

    def get_session(self, session_id: UUID) -> RemoteManualSelectionAccessView:
        record = self._repository.get_access_session(session_id)
        if record is None:
            raise _not_found()
        return self._view(record, self._now())

    def unlock(
        self,
        *,
        session_id: UUID,
        access_code: str,
        client_instance_id: UUID,
    ) -> UnlockedRemoteManualSelectionAccess:
        now = self._now()
        record = self._repository.get_access_session_for_update(session_id)
        self._assert_unlockable(record, now)
        assert record is not None
        if not hmac.compare_digest(
            record.code_hash,
            hash_access_code(access_code, record.code_salt),
        ):
            attempts = record.failed_attempts + 1
            locked = attempts >= MAX_FAILED_ACCESS_ATTEMPTS
            updated = replace(
                record,
                session=_touch(record.session, now),
                failed_attempts=attempts,
                locked_at=now if locked else None,
                token_hash=None if locked else record.token_hash,
                token_expires_at=None if locked else record.token_expires_at,
                writer_client_instance_id=(None if locked else record.writer_client_instance_id),
                writer_lease_token=None if locked else record.writer_lease_token,
                writer_lease_expires_at=None if locked else record.writer_lease_expires_at,
            )
            updated = self._repository.save_access_session(updated)
            self._audit(
                updated,
                event_type="locked" if locked else "unlock_failed",
                actor=f"remote-session:{session_id}",
                outcome_code=(
                    "REMOTE_SELECTION_SESSION_LOCKED"
                    if locked
                    else "REMOTE_SELECTION_ACCESS_CODE_INVALID"
                ),
                payload={"failedAttempts": attempts},
                now=now,
            )
            raise RemoteManualSelectionAuthenticationError(
                "REMOTE_SELECTION_SESSION_LOCKED"
                if locked
                else "REMOTE_SELECTION_ACCESS_CODE_INVALID",
                "Remote selection session is locked."
                if locked
                else "Remote selection access code is invalid.",
            )

        access_token = generate_access_token()
        lease_owner = record.writer_client_instance_id
        lease_token = record.writer_lease_token
        lease_expires_at = record.writer_lease_expires_at
        lease_available = lease_expires_at is None or lease_expires_at <= now
        same_writer = lease_owner == client_instance_id
        acquired = lease_available or same_writer
        if acquired:
            lease_owner = client_instance_id
            lease_token = lease_token if same_writer and lease_token is not None else uuid4()
            lease_expires_at = _lease_expiry(now, record.session.expires_at)
        unlocked = self._repository.save_access_session(
            replace(
                record,
                session=_touch(record.session, now),
                failed_attempts=0,
                token_hash=hash_access_token(access_token),
                token_expires_at=record.session.expires_at,
                writer_client_instance_id=lease_owner,
                writer_lease_token=lease_token,
                writer_lease_expires_at=lease_expires_at,
            )
        )
        self._audit(
            unlocked,
            event_type="unlocked",
            actor=f"remote-session:{session_id}",
            outcome_code="REMOTE_SELECTION_SESSION_UNLOCKED",
            payload={"writerLeaseAcquired": acquired},
            now=now,
        )
        return UnlockedRemoteManualSelectionAccess(
            self._context(unlocked, client_instance_id, now),
            access_token,
        )

    def context(
        self,
        *,
        access_token: str,
        client_instance_id: UUID,
    ) -> RemoteManualSelectionContext:
        now = self._now()
        record = self._authenticate(access_token, now=now)
        return self._context(record, client_instance_id, now)

    def heartbeat(
        self,
        *,
        session_id: UUID,
        access_token: str,
        client_instance_id: UUID,
    ) -> RemoteManualSelectionContext:
        now = self._now()
        record = self._authenticated_for_update(session_id, access_token, now)
        if (
            record.writer_client_instance_id != client_instance_id
            or record.writer_lease_token is None
            or record.writer_lease_expires_at is None
            or record.writer_lease_expires_at <= now
        ):
            raise RemoteManualSelectionLeaseConflictError(
                "REMOTE_SELECTION_WRITER_LEASE_NOT_OWNED",
                "The client does not own an active writer lease.",
            )
        expires_at = _lease_expiry(now, record.session.expires_at)
        if expires_at <= record.writer_lease_expires_at:
            return self._context(record, client_instance_id, now)
        updated = self._repository.save_access_session(
            replace(
                record,
                session=_touch(record.session, now),
                writer_lease_expires_at=expires_at,
            )
        )
        self._audit(
            updated,
            event_type="writer_heartbeat",
            actor=f"remote-session:{session_id}",
            outcome_code="REMOTE_SELECTION_WRITER_LEASE_RENEWED",
            payload={},
            now=now,
        )
        return self._context(updated, client_instance_id, now)

    def takeover(
        self,
        *,
        session_id: UUID,
        access_token: str,
        client_instance_id: UUID,
    ) -> RemoteManualSelectionContext:
        now = self._now()
        record = self._authenticated_for_update(session_id, access_token, now)
        if (
            record.writer_client_instance_id not in {None, client_instance_id}
            and record.writer_lease_expires_at is not None
            and record.writer_lease_expires_at > now
        ):
            raise RemoteManualSelectionLeaseConflictError(
                "REMOTE_SELECTION_WRITER_LEASE_ACTIVE",
                "Another client still owns the active writer lease.",
            )
        if (
            record.writer_client_instance_id == client_instance_id
            and record.writer_lease_expires_at is not None
            and record.writer_lease_expires_at > now
        ):
            return self.heartbeat(
                session_id=session_id,
                access_token=access_token,
                client_instance_id=client_instance_id,
            )
        updated = self._repository.save_access_session(
            replace(
                record,
                session=_touch(record.session, now),
                writer_client_instance_id=client_instance_id,
                writer_lease_token=uuid4(),
                writer_lease_expires_at=_lease_expiry(now, record.session.expires_at),
            )
        )
        self._audit(
            updated,
            event_type="writer_takeover",
            actor=f"remote-session:{session_id}",
            outcome_code="REMOTE_SELECTION_WRITER_LEASE_ACQUIRED",
            payload={},
            now=now,
        )
        return self._context(updated, client_instance_id, now)

    def revoke(self, session_id: UUID) -> RemoteManualSelectionAccessView:
        now = self._now()
        record = self._repository.get_access_session_for_update(session_id)
        if record is None:
            raise _not_found()
        if record.session.status is RemoteManualSelectionSessionStatus.REVOKED:
            return self._view(record, now)
        revoked = self._repository.save_access_session(
            replace(
                record,
                session=replace(
                    record.session,
                    status=RemoteManualSelectionSessionStatus.REVOKED,
                    revision=record.session.revision + 1,
                    updated_at=now,
                ),
                revoked_at=now,
                token_hash=None,
                token_expires_at=None,
                writer_client_instance_id=None,
                writer_lease_token=None,
                writer_lease_expires_at=None,
            )
        )
        self._audit(
            revoked,
            event_type="revoked",
            actor="local-owner",
            outcome_code="REMOTE_SELECTION_SESSION_REVOKED",
            payload={},
            now=now,
        )
        return self._view(revoked, now)

    def _authenticated_for_update(
        self,
        session_id: UUID,
        access_token: str,
        now: datetime,
    ) -> RemoteManualSelectionAccessRecord:
        record = self._repository.get_access_session_for_update(session_id)
        self._assert_token(record, access_token, now)
        assert record is not None
        return record

    def _authenticate(
        self,
        access_token: str,
        *,
        now: datetime,
    ) -> RemoteManualSelectionAccessRecord:
        token_hash = hash_access_token(access_token)
        record = self._repository.find_access_session_by_token_hash(token_hash)
        self._assert_token(record, access_token, now)
        assert record is not None
        return record

    def _assert_unlockable(
        self,
        record: RemoteManualSelectionAccessRecord | None,
        now: datetime,
    ) -> None:
        if record is None or record.session.expires_at <= now:
            raise _not_found()
        if record.session.status is RemoteManualSelectionSessionStatus.REVOKED:
            raise RemoteManualSelectionAuthenticationError(
                "REMOTE_SELECTION_SESSION_REVOKED",
                "Remote selection session has been revoked.",
            )
        if record.session.status is not RemoteManualSelectionSessionStatus.ACTIVE:
            raise _not_found()
        if record.locked_at is not None:
            raise RemoteManualSelectionAuthenticationError(
                "REMOTE_SELECTION_SESSION_LOCKED",
                "Remote selection session is locked.",
            )

    def _assert_token(
        self,
        record: RemoteManualSelectionAccessRecord | None,
        access_token: str,
        now: datetime,
    ) -> None:
        if (
            record is None
            or record.session.status is not RemoteManualSelectionSessionStatus.ACTIVE
            or record.session.expires_at <= now
            or record.revoked_at is not None
            or record.locked_at is not None
            or record.token_hash is None
            or record.token_expires_at is None
            or record.token_expires_at <= now
            or not hmac.compare_digest(record.token_hash, hash_access_token(access_token))
        ):
            raise RemoteManualSelectionAuthenticationError(
                "REMOTE_SELECTION_TOKEN_INVALID",
                "Remote selection access token is invalid or has expired.",
            )

    def _view(
        self,
        record: RemoteManualSelectionAccessRecord,
        now: datetime,
    ) -> RemoteManualSelectionAccessView:
        status = record.session.status
        if status is RemoteManualSelectionSessionStatus.ACTIVE and record.session.expires_at <= now:
            status = RemoteManualSelectionSessionStatus.EXPIRED
        writer_active = (
            status is RemoteManualSelectionSessionStatus.ACTIVE
            and record.writer_lease_expires_at is not None
            and record.writer_lease_expires_at > now
        )
        return RemoteManualSelectionAccessView(
            session_id=record.session.id,
            status=status,
            revision=record.session.revision,
            display_name=record.display_name,
            created_at=record.session.created_at,
            updated_at=record.session.updated_at,
            expires_at=record.session.expires_at,
            locked_at=record.locked_at,
            revoked_at=record.revoked_at,
            writer_active=writer_active,
            writer_lease_expires_at=(record.writer_lease_expires_at if writer_active else None),
        )

    def _context(
        self,
        record: RemoteManualSelectionAccessRecord,
        client_instance_id: UUID,
        now: datetime,
    ) -> RemoteManualSelectionContext:
        writer_active = (
            record.writer_lease_expires_at is not None and record.writer_lease_expires_at > now
        )
        return RemoteManualSelectionContext(
            session_id=record.session.id,
            status=record.session.status,
            revision=record.session.revision,
            expires_at=record.session.expires_at,
            is_writer=(writer_active and record.writer_client_instance_id == client_instance_id),
            writer_active=writer_active,
            writer_lease_expires_at=(record.writer_lease_expires_at if writer_active else None),
        )

    def _audit(
        self,
        record: RemoteManualSelectionAccessRecord,
        *,
        event_type: str,
        actor: str,
        outcome_code: str,
        payload: dict[str, object],
        now: datetime,
    ) -> None:
        self._repository.append_access_audit(
            session_id=record.session.id,
            event_type=event_type,
            actor=actor,
            outcome_code=outcome_code,
            payload=payload,
            created_at=now,
        )


def _touch(
    session: RemoteManualSelectionSessionV1,
    now: datetime,
) -> RemoteManualSelectionSessionV1:
    return replace(session, revision=session.revision + 1, updated_at=now)


def _lease_expiry(now: datetime, session_expires_at: datetime) -> datetime:
    return min(now + WRITER_LEASE_DURATION, session_expires_at)


def _not_found() -> RemoteManualSelectionAccessNotFoundError:
    return RemoteManualSelectionAccessNotFoundError(
        "REMOTE_SELECTION_SESSION_NOT_FOUND",
        "Remote selection session does not exist or has expired.",
    )


__all__ = [
    "CreatedRemoteManualSelectionAccess",
    "MAX_FAILED_ACCESS_ATTEMPTS",
    "MAX_SESSION_LIFETIME_MINUTES",
    "MIN_SESSION_LIFETIME_MINUTES",
    "REMOTE_SELECTION_COOKIE_NAME",
    "REMOTE_SELECTION_COOKIE_PATH",
    "REMOTE_SELECTION_PROXY_INTENT",
    "RemoteManualSelectionAccessError",
    "RemoteManualSelectionAccessNotFoundError",
    "RemoteManualSelectionAccessRecord",
    "RemoteManualSelectionAccessRepository",
    "RemoteManualSelectionAccessService",
    "RemoteManualSelectionAccessView",
    "RemoteManualSelectionAuthenticationError",
    "RemoteManualSelectionAuthorizationError",
    "RemoteManualSelectionBaseConsumer",
    "RemoteManualSelectionContext",
    "RemoteManualSelectionLeaseConflictError",
    "UnlockedRemoteManualSelectionAccess",
    "WRITER_LEASE_DURATION",
]
