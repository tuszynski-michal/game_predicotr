"""Process-local access sessions for the standalone reviewer application."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import string
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from uuid import UUID, uuid4

_CODE_ALPHABET = string.ascii_uppercase.replace("I", "").replace("O", "") + "23456789"


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


@dataclass(frozen=True, slots=True)
class CreatedReviewerAccess:
    session: ReviewerAccessSession
    code: str
    review_url: str


class ReviewerAccessService:
    """Create and unlock short-lived sessions without persisting plaintext codes."""

    def __init__(
        self,
        reviewer_origin: str,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._reviewer_origin = reviewer_origin.rstrip("/")
        self._now = now or (lambda: datetime.now(UTC))
        self._sessions: dict[UUID, ReviewerAccessSession] = {}
        self._lock = Lock()

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
        now = self._now()
        code = "-".join(
            "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4))
            for _ in range(2)
        )
        salt = secrets.token_bytes(16)
        session = ReviewerAccessSession(
            id=uuid4(),
            game_id=game_id,
            import_job_id=import_job_id,
            created_at=now,
            expires_at=now + timedelta(minutes=lifetime_minutes),
            code_salt=salt,
            code_hash=_hash_code(code, salt),
        )
        with self._lock:
            self._remove_expired(now)
            self._sessions[session.id] = session
        return CreatedReviewerAccess(
            session=session,
            code=code,
            review_url=f"{self._reviewer_origin}/?session={session.id}",
        )

    def unlock(self, session_id: UUID, code: str) -> ReviewerAccessSession:
        now = self._now()
        with self._lock:
            self._remove_expired(now)
            session = self._sessions.get(session_id)
        if session is None:
            raise ReviewerAccessError(
                "REVIEWER_SESSION_NOT_FOUND",
                "Reviewer session does not exist or has expired.",
            )
        normalized = code.strip().upper()
        if not hmac.compare_digest(
            session.code_hash,
            _hash_code(normalized, session.code_salt),
        ):
            raise ReviewerAccessError(
                "REVIEWER_ACCESS_CODE_INVALID",
                "Reviewer access code is invalid.",
            )
        return session

    def _remove_expired(self, now: datetime) -> None:
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if session.expires_at <= now
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)


def _hash_code(code: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        code.encode("ascii", errors="ignore"),
        salt,
        120_000,
    )


__all__ = [
    "CreatedReviewerAccess",
    "ReviewerAccessError",
    "ReviewerAccessService",
    "ReviewerAccessSession",
]
