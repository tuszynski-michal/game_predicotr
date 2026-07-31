"""Durable, revocable access sessions for the standalone Reviewer app."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import string
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Protocol
from uuid import UUID, uuid4

_CODE_ALPHABET = string.ascii_uppercase.replace("I", "").replace("O", "") + "23456789"
_MAX_FAILED_ATTEMPTS = 5


class ReviewerAccessError(ValueError):
    """Raised when a reviewer access session cannot be used."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class ReviewerAccessSession:
    id: UUID
    game_id: UUID
    import_job_id: UUID
    created_at: datetime
    expires_at: datetime
    code_salt: bytes
    code_hash: bytes
    failed_attempts: int = 0
    locked_at: datetime | None = None
    revoked_at: datetime | None = None
    token_hash: bytes | None = None
    token_expires_at: datetime | None = None
    last_unlocked_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CreatedReviewerAccess:
    session: ReviewerAccessSession
    code: str
    review_url: str


@dataclass(frozen=True, slots=True)
class UnlockedReviewerAccess:
    session: ReviewerAccessSession
    access_token: str


@dataclass(frozen=True, slots=True)
class ReviewerAccessAuditEvent:
    id: UUID
    session_id: UUID
    event_type: str
    created_at: datetime


class ReviewerAccessRepository(Protocol):
    def scope_exists(self, game_id: UUID, import_job_id: UUID) -> bool: ...

    def add(self, session: ReviewerAccessSession) -> ReviewerAccessSession: ...

    def get_for_update(self, session_id: UUID) -> ReviewerAccessSession | None: ...

    def find_by_token_hash(self, token_hash: bytes) -> ReviewerAccessSession | None: ...

    def save(self, session: ReviewerAccessSession) -> ReviewerAccessSession: ...

    def append_audit(
        self,
        session_id: UUID,
        event_type: str,
        created_at: datetime,
    ) -> None: ...

    def list_audit(self, session_id: UUID) -> Sequence[ReviewerAccessAuditEvent]: ...


class InMemoryReviewerAccessRepository:
    """Deterministic repository used by focused unit tests."""

    def __init__(self) -> None:
        self._sessions: dict[UUID, ReviewerAccessSession] = {}
        self._events: list[ReviewerAccessAuditEvent] = []
        self._lock = Lock()

    def scope_exists(self, _game_id: UUID, _import_job_id: UUID) -> bool:
        return True

    def add(self, session: ReviewerAccessSession) -> ReviewerAccessSession:
        with self._lock:
            self._sessions[session.id] = session
        return session

    def get_for_update(self, session_id: UUID) -> ReviewerAccessSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def find_by_token_hash(self, token_hash: bytes) -> ReviewerAccessSession | None:
        with self._lock:
            return next(
                (
                    session
                    for session in self._sessions.values()
                    if session.token_hash is not None
                    and hmac.compare_digest(session.token_hash, token_hash)
                ),
                None,
            )

    def save(self, session: ReviewerAccessSession) -> ReviewerAccessSession:
        with self._lock:
            self._sessions[session.id] = session
        return session

    def append_audit(
        self,
        session_id: UUID,
        event_type: str,
        created_at: datetime,
    ) -> None:
        with self._lock:
            self._events.append(
                ReviewerAccessAuditEvent(
                    id=uuid4(),
                    session_id=session_id,
                    event_type=event_type,
                    created_at=created_at,
                )
            )

    def list_audit(self, session_id: UUID) -> Sequence[ReviewerAccessAuditEvent]:
        with self._lock:
            return tuple(event for event in self._events if event.session_id == session_id)


class ReviewerAccessService:
    """Create, unlock, authenticate and revoke scoped Reviewer sessions."""

    def __init__(
        self,
        reviewer_origin: str | Callable[[], str],
        repository: ReviewerAccessRepository | None = None,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._reviewer_origin = reviewer_origin
        self._repository = repository or InMemoryReviewerAccessRepository()
        self._now = now or (lambda: datetime.now(UTC))

    def create(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        lifetime_minutes: int,
    ) -> CreatedReviewerAccess:
        if not 5 <= lifetime_minutes <= 24 * 60:
            raise ReviewerAccessError(
                "REVIEWER_SESSION_LIFETIME_INVALID",
                "Reviewer session lifetime must be between 5 minutes and 24 hours.",
            )
        if not self._repository.scope_exists(game_id, import_job_id):
            raise ReviewerAccessError(
                "REVIEWER_SCOPE_INVALID",
                "The import job does not belong to the selected game.",
            )
        now = self._now()
        code = "-".join("".join(secrets.choice(_CODE_ALPHABET) for _ in range(4)) for _ in range(2))
        salt = secrets.token_bytes(16)
        session = self._repository.add(
            ReviewerAccessSession(
                id=uuid4(),
                game_id=game_id,
                import_job_id=import_job_id,
                created_at=now,
                expires_at=now + timedelta(minutes=lifetime_minutes),
                code_salt=salt,
                code_hash=_hash_code(code, salt),
            )
        )
        self._repository.append_audit(session.id, "created", now)
        return CreatedReviewerAccess(
            session=session,
            code=code,
            review_url=f"{self._resolve_reviewer_origin()}/?session={session.id}",
        )

    def unlock(self, session_id: UUID, code: str) -> UnlockedReviewerAccess:
        now = self._now()
        session = self._repository.get_for_update(session_id)
        self._assert_available(session, now, hide_missing=True)
        assert session is not None
        if not hmac.compare_digest(
            session.code_hash,
            _hash_code(code.strip().upper(), session.code_salt),
        ):
            failed_attempts = session.failed_attempts + 1
            locked_at = now if failed_attempts >= _MAX_FAILED_ATTEMPTS else None
            self._repository.save(
                replace(
                    session,
                    failed_attempts=failed_attempts,
                    locked_at=locked_at,
                    token_hash=None if locked_at is not None else session.token_hash,
                    token_expires_at=None if locked_at is not None else session.token_expires_at,
                )
            )
            self._repository.append_audit(
                session.id,
                "locked" if locked_at is not None else "unlock_failed",
                now,
            )
            raise ReviewerAccessError(
                "REVIEWER_SESSION_LOCKED"
                if locked_at is not None
                else "REVIEWER_ACCESS_CODE_INVALID",
                "Reviewer session is locked."
                if locked_at is not None
                else "Reviewer access code is invalid.",
            )
        access_token = secrets.token_urlsafe(32)
        unlocked = self._repository.save(
            replace(
                session,
                failed_attempts=0,
                token_hash=_hash_token(access_token),
                token_expires_at=session.expires_at,
                last_unlocked_at=now,
            )
        )
        self._repository.append_audit(session.id, "unlocked", now)
        return UnlockedReviewerAccess(unlocked, access_token)

    def authenticate(self, access_token: str) -> ReviewerAccessSession:
        now = self._now()
        token_hash = _hash_token(access_token)
        session = self._repository.find_by_token_hash(token_hash)
        self._assert_available(session, now, hide_missing=False)
        assert session is not None
        if (
            session.token_hash is None
            or session.token_expires_at is None
            or session.token_expires_at <= now
            or not hmac.compare_digest(session.token_hash, token_hash)
        ):
            raise ReviewerAccessError(
                "REVIEWER_TOKEN_INVALID",
                "Reviewer access token is invalid or has expired.",
            )
        return session

    def authorize_scope(
        self,
        session: ReviewerAccessSession,
        *,
        game_id: UUID,
        import_job_id: UUID,
    ) -> None:
        if session.game_id != game_id or session.import_job_id != import_job_id:
            raise ReviewerAccessError(
                "REVIEWER_SCOPE_FORBIDDEN",
                "Reviewer session does not allow this game or import.",
            )

    def revoke(self, session_id: UUID) -> ReviewerAccessSession:
        now = self._now()
        session = self._repository.get_for_update(session_id)
        if session is None:
            raise ReviewerAccessError(
                "REVIEWER_SESSION_NOT_FOUND",
                "Reviewer session does not exist.",
            )
        if session.revoked_at is None:
            session = self._repository.save(
                replace(
                    session,
                    revoked_at=now,
                    token_hash=None,
                    token_expires_at=None,
                )
            )
            self._repository.append_audit(session.id, "revoked", now)
        return session

    def _assert_available(
        self,
        session: ReviewerAccessSession | None,
        now: datetime,
        *,
        hide_missing: bool,
    ) -> None:
        if session is None or session.expires_at <= now:
            raise ReviewerAccessError(
                "REVIEWER_SESSION_NOT_FOUND" if hide_missing else "REVIEWER_TOKEN_INVALID",
                "Reviewer session does not exist or has expired."
                if hide_missing
                else "Reviewer access token is invalid or has expired.",
            )
        if session.revoked_at is not None:
            raise ReviewerAccessError(
                "REVIEWER_SESSION_REVOKED",
                "Reviewer session has been revoked.",
            )
        if session.locked_at is not None:
            raise ReviewerAccessError(
                "REVIEWER_SESSION_LOCKED",
                "Reviewer session is locked.",
            )

    def _resolve_reviewer_origin(self) -> str:
        origin = (
            self._reviewer_origin() if callable(self._reviewer_origin) else self._reviewer_origin
        )
        return origin.rstrip("/")


def _hash_code(code: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        code.encode("ascii", errors="ignore"),
        salt,
        210_000,
    )


def _hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("ascii", errors="ignore")).digest()


__all__ = [
    "CreatedReviewerAccess",
    "InMemoryReviewerAccessRepository",
    "ReviewerAccessAuditEvent",
    "ReviewerAccessError",
    "ReviewerAccessRepository",
    "ReviewerAccessService",
    "ReviewerAccessSession",
    "UnlockedReviewerAccess",
]
