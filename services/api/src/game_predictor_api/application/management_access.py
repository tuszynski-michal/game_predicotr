"""Capability lifecycle using shared credentials and independent persistence."""

import hmac
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from uuid import UUID, uuid4

from game_predictor_api.application.access_credentials import (
    generate_access_code,
    generate_access_token,
    generate_code_salt,
    hash_access_code,
    hash_access_token,
)
from game_predictor_api.domain.management_sessions import (
    MANAGEMENT_LIFETIMES,
    ManagementAccessError,
    invalid_access,
)


@dataclass(frozen=True)
class ManagementSessionRecord:
    id: UUID
    label: str
    code_salt: bytes
    code_hash: bytes
    failed_attempts: int
    locked_at: datetime | None
    revoked_at: datetime | None
    token_hash: bytes | None
    token_expires_at: datetime | None
    last_unlocked_at: datetime | None
    created_at: datetime
    expires_at: datetime

    @property
    def actor(self) -> str:
        return f"management-share:{self.id}:{self.label}"


class ManagementSessionRepository(Protocol):
    def lock_ingress(self) -> None: ...
    def get(self, session_id: UUID, *, lock: bool = False) -> ManagementSessionRecord | None: ...
    def find_token(self, token_hash: bytes) -> ManagementSessionRecord | None: ...
    def save(self, record: ManagementSessionRecord) -> None: ...
    def list(self, limit: int) -> Sequence[ManagementSessionRecord]: ...
    def audit(self, record: ManagementSessionRecord, event: str, at: datetime) -> None: ...


class ManagementAccessService:
    def __init__(
        self,
        repository: ManagementSessionRepository,
        *,
        enabled: bool = True,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.enabled = enabled
        self.now = now or (lambda: datetime.now(UTC))

    def lock_ingress(self) -> None:
        self.repository.lock_ingress()

    def validate_create(self, label: str, lifetime_minutes: int) -> str:
        self.require_enabled()
        normalized = " ".join(label.split())
        if not 1 <= len(normalized) <= 100:
            raise ManagementAccessError("MANAGEMENT_LABEL_INVALID", "Name the recipient.", 422)
        if lifetime_minutes not in MANAGEMENT_LIFETIMES:
            raise ManagementAccessError(
                "MANAGEMENT_LIFETIME_INVALID", "Choose 1, 4, 8, 24, 48 or 72 hours.", 422
            )
        return normalized

    def create(self, label: str, lifetime_minutes: int) -> tuple[ManagementSessionRecord, str]:
        label = self.validate_create(label, lifetime_minutes)
        now = self.now()
        code, salt = generate_access_code(), generate_code_salt()
        record = ManagementSessionRecord(
            uuid4(),
            label,
            salt,
            hash_access_code(code, salt),
            0,
            None,
            None,
            None,
            None,
            None,
            now,
            now + timedelta(minutes=lifetime_minutes),
        )
        self.repository.save(record)
        self.repository.audit(record, "created", now)
        return record, code

    def list(self, limit: int = 100) -> Sequence[ManagementSessionRecord]:
        return self.repository.list(limit)

    def revoke(self, session_id: UUID) -> ManagementSessionRecord:
        record = self.repository.get(session_id, lock=True)
        if record is None:
            raise ManagementAccessError("MANAGEMENT_SESSION_NOT_FOUND", "Link not found.", 404)
        if record.revoked_at is None:
            record = replace(record, revoked_at=self.now(), token_hash=None, token_expires_at=None)
            self.repository.save(record)
            self.repository.audit(record, "revoked", self.now())
        return record

    def unlock(self, session_id: UUID, code: str) -> tuple[ManagementSessionRecord, str]:
        self.require_enabled()
        record = self.repository.get(session_id, lock=True)
        now = self.now()
        if record is None or record.expires_at <= now:
            raise ManagementAccessError("MANAGEMENT_SESSION_NOT_FOUND", "Link not found.", 404)
        if record.revoked_at is not None or record.locked_at is not None:
            raise invalid_access()
        if not hmac.compare_digest(record.code_hash, hash_access_code(code, record.code_salt)):
            attempts = record.failed_attempts + 1
            record = replace(
                record,
                failed_attempts=attempts,
                locked_at=now if attempts >= 5 else None,
                token_hash=None if attempts >= 5 else record.token_hash,
                token_expires_at=None if attempts >= 5 else record.token_expires_at,
            )
            self.repository.save(record)
            self.repository.audit(record, "locked" if attempts >= 5 else "unlock_failed", now)
            raise ManagementAccessError(
                "MANAGEMENT_CODE_LOCKED" if attempts >= 5 else "MANAGEMENT_CODE_INVALID",
                "The access code is invalid or locked.",
            )
        token = generate_access_token()
        record = replace(
            record,
            failed_attempts=0,
            token_hash=hash_access_token(token),
            token_expires_at=record.expires_at,
            last_unlocked_at=now,
        )
        self.repository.save(record)
        self.repository.audit(record, "unlocked", now)
        return record, token

    def authenticate(
        self, token: str, expected_session: UUID, *, lock: bool = False
    ) -> ManagementSessionRecord:
        self.require_enabled()
        record = (
            self.repository.get(expected_session, lock=True)
            if lock
            else self.repository.find_token(hash_access_token(token))
        )
        now = self.now()
        if (
            record is None
            or record.id != expected_session
            or record.token_hash is None
            or not hmac.compare_digest(record.token_hash, hash_access_token(token))
            or record.revoked_at is not None
            or record.locked_at is not None
            or record.expires_at <= now
            or record.token_expires_at is None
            or record.token_expires_at <= now
        ):
            raise invalid_access()
        return record

    def require_enabled(self) -> None:
        if not self.enabled:
            raise ManagementAccessError(
                "MANAGEMENT_SHARE_DISABLED", "Panel sharing is disabled.", 503
            )


def session_status(
    record: ManagementSessionRecord, now: datetime
) -> Literal["active", "locked", "expired", "revoked"]:
    if record.revoked_at is not None:
        return "revoked"
    if record.expires_at <= now:
        return "expired"
    return "locked" if record.locked_at is not None else "active"
