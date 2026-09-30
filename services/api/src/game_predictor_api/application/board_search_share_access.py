"""Lifecycle of online board-search share sessions (D-471, TASK-0766).

Create, list, revoke, unlock and authenticate one purpose-scoped share
session. The access code and token primitives are the shared ones from
`access_credentials`; only hashes are stored.
"""

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
from game_predictor_api.application.board_search_approximate_win import (
    BoardSearchApproximateWinRepository,
)
from game_predictor_api.domain.board_search import BoardSearchError
from game_predictor_api.domain.board_search_shares import (
    BOARD_SEARCH_SHARE_MAX_ACTIVE_SESSIONS,
    BOARD_SEARCH_SHARE_MAX_FAILED_ATTEMPTS,
    BoardSearchShareAuditEventType,
    BoardSearchShareAuthenticationError,
    BoardSearchShareConflictError,
    BoardSearchShareError,
    BoardSearchShareNotFoundError,
    BoardSearchShareStatus,
    BoardSearchShareUnavailableError,
    normalize_board_search_share_label,
    validate_board_search_share_lifetime,
)

SESSION_LIST_LIMIT_MAX = 100


@dataclass(frozen=True, slots=True)
class BoardSearchShareRecord:
    """Persistence record with credential hashes; never an HTTP DTO."""

    id: UUID
    game_id: UUID
    label: str | None
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


@dataclass(frozen=True, slots=True)
class BoardSearchShareView:
    """What the local owner sees about a session: no secrets."""

    session_id: UUID
    game_id: UUID
    label: str | None
    status: BoardSearchShareStatus
    failed_attempts: int
    created_at: datetime
    expires_at: datetime
    locked_at: datetime | None
    revoked_at: datetime | None
    last_unlocked_at: datetime | None


@dataclass(frozen=True, slots=True)
class BoardSearchShareContext:
    """The authenticated recipient's scope: always exactly one game."""

    session_id: UUID
    game_id: UUID
    label: str | None
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class CreatedBoardSearchShare:
    session: BoardSearchShareView
    access_code: str


@dataclass(frozen=True, slots=True)
class UnlockedBoardSearchShare:
    context: BoardSearchShareContext
    access_token: str


class BoardSearchShareRepository(Protocol):
    def add_session(self, record: BoardSearchShareRecord) -> BoardSearchShareRecord: ...

    def get_session(self, session_id: UUID) -> BoardSearchShareRecord | None: ...

    def get_session_for_update(self, session_id: UUID) -> BoardSearchShareRecord | None: ...

    def find_session_by_token_hash(self, token_hash: bytes) -> BoardSearchShareRecord | None: ...

    def save_session(self, record: BoardSearchShareRecord) -> BoardSearchShareRecord: ...

    def list_sessions(
        self,
        *,
        game_id: UUID | None,
        limit: int,
    ) -> Sequence[BoardSearchShareRecord]: ...

    def count_active_sessions(self, now: datetime) -> int:
        """Count unexpired, unrevoked, unlocked sessions without locking."""
        ...

    def count_active_sessions_locked(self, now: datetime) -> int:
        """Count unexpired, unrevoked, unlocked sessions while holding a
        transaction-scoped lock that serialises concurrent creates."""
        ...

    def append_audit_event(
        self,
        *,
        session_id: UUID,
        event_type: BoardSearchShareAuditEventType,
        outcome_code: str,
        payload: dict[str, object],
        created_at: datetime,
    ) -> None: ...


class BoardSearchShareReadiness(Protocol):
    def __call__(self, game_id: UUID) -> None:
        """Raise when the game cannot serve a useful share (no game, board
        search not ready or no published rules)."""
        ...


def assert_board_search_share_ready(
    repository: BoardSearchApproximateWinRepository,
    game_id: UUID,
) -> None:
    """A share opens the whole board search section, so it needs the same
    data as the Admin section: a ready projection or archive (the empty
    range read raises the same readiness errors as a search) and published
    rules for the approximate win."""

    repository.range_documents(game_id=game_id, first_sequence_number=1, last_sequence_number=0)
    if repository.latest_published_rules(game_id) is None:
        raise BoardSearchError(
            "APPROXIMATE_WIN_RULES_NOT_PUBLISHED",
            "The game has no published rules version to calculate payout against.",
        )


class BoardSearchShareAccessService:
    def __init__(
        self,
        repository: BoardSearchShareRepository,
        *,
        readiness: BoardSearchShareReadiness,
        enabled: bool,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._readiness = readiness
        self._enabled = enabled
        self._now = now or (lambda: datetime.now(UTC))

    def assert_can_create(
        self,
        *,
        game_id: UUID,
        lifetime_minutes: int,
        label: str | None,
    ) -> None:
        """Every check `create` repeats, without writing anything, so a
        caller can run it before starting the public ingress."""

        self._require_enabled()
        validate_board_search_share_lifetime(lifetime_minutes)
        normalize_board_search_share_label(label)
        self._readiness(game_id)
        # No lock here: the caller may start the ingress next, which can take
        # seconds; `create` re-checks under the lock.
        if self._repository.count_active_sessions(self._now()) >= (
            BOARD_SEARCH_SHARE_MAX_ACTIVE_SESSIONS
        ):
            raise _active_limit_reached()

    def create(
        self,
        *,
        game_id: UUID,
        lifetime_minutes: int,
        label: str | None,
    ) -> CreatedBoardSearchShare:
        self._require_enabled()
        validate_board_search_share_lifetime(lifetime_minutes)
        normalized_label = normalize_board_search_share_label(label)
        self._readiness(game_id)
        now = self._now()
        if self._repository.count_active_sessions_locked(now) >= (
            BOARD_SEARCH_SHARE_MAX_ACTIVE_SESSIONS
        ):
            raise _active_limit_reached()
        code = generate_access_code()
        salt = generate_code_salt()
        record = self._repository.add_session(
            BoardSearchShareRecord(
                id=uuid4(),
                game_id=game_id,
                label=normalized_label,
                code_salt=salt,
                code_hash=hash_access_code(code, salt),
                failed_attempts=0,
                locked_at=None,
                revoked_at=None,
                token_hash=None,
                token_expires_at=None,
                last_unlocked_at=None,
                created_at=now,
                expires_at=now + timedelta(minutes=lifetime_minutes),
            )
        )
        self._audit(
            record,
            BoardSearchShareAuditEventType.CREATED,
            "BOARD_SEARCH_SHARE_CREATED",
            {"lifetimeMinutes": lifetime_minutes},
            now,
        )
        return CreatedBoardSearchShare(_view(record, now), code)

    def list_sessions(
        self,
        *,
        game_id: UUID | None = None,
        limit: int = SESSION_LIST_LIMIT_MAX,
    ) -> tuple[BoardSearchShareView, ...]:
        if not 1 <= limit <= SESSION_LIST_LIMIT_MAX:
            raise BoardSearchShareError(
                "BOARD_SEARCH_SHARE_LIST_LIMIT_INVALID",
                "Share session list limit must be between 1 and 100.",
            )
        now = self._now()
        return tuple(
            _view(record, now)
            for record in self._repository.list_sessions(game_id=game_id, limit=limit)
        )

    def revoke(self, session_id: UUID) -> BoardSearchShareView:
        """Always available, also when sharing is disabled: a safety stop."""

        now = self._now()
        record = self._repository.get_session_for_update(session_id)
        if record is None:
            raise _not_found()
        if record.revoked_at is not None:
            return _view(record, now)
        revoked = self._repository.save_session(
            replace(record, revoked_at=now, token_hash=None, token_expires_at=None)
        )
        self._audit(
            revoked,
            BoardSearchShareAuditEventType.REVOKED,
            "BOARD_SEARCH_SHARE_REVOKED",
            {},
            now,
        )
        return _view(revoked, now)

    def unlock(self, *, session_id: UUID, access_code: str) -> UnlockedBoardSearchShare:
        """Exchange the code for a new token. A new unlock rotates the token,
        so only the most recent unlock stays signed in (R4)."""

        self._require_enabled()
        now = self._now()
        record = self._repository.get_session_for_update(session_id)
        if record is None or record.expires_at <= now:
            raise _not_found()
        if record.revoked_at is not None:
            raise BoardSearchShareAuthenticationError(
                "BOARD_SEARCH_SHARE_REVOKED", "This share link has been stopped."
            )
        if record.locked_at is not None:
            raise _locked()
        if not hmac.compare_digest(
            record.code_hash, hash_access_code(access_code, record.code_salt)
        ):
            attempts = record.failed_attempts + 1
            locked = attempts >= BOARD_SEARCH_SHARE_MAX_FAILED_ATTEMPTS
            updated = self._repository.save_session(
                replace(
                    record,
                    failed_attempts=attempts,
                    locked_at=now if locked else None,
                    token_hash=None if locked else record.token_hash,
                    token_expires_at=None if locked else record.token_expires_at,
                )
            )
            self._audit(
                updated,
                (
                    BoardSearchShareAuditEventType.LOCKED
                    if locked
                    else BoardSearchShareAuditEventType.UNLOCK_FAILED
                ),
                "BOARD_SEARCH_SHARE_LOCKED" if locked else "BOARD_SEARCH_SHARE_CODE_INVALID",
                {"failedAttempts": attempts},
                now,
            )
            if locked:
                raise _locked()
            raise BoardSearchShareAuthenticationError(
                "BOARD_SEARCH_SHARE_CODE_INVALID", "The access code is invalid."
            )
        access_token = generate_access_token()
        unlocked = self._repository.save_session(
            replace(
                record,
                failed_attempts=0,
                token_hash=hash_access_token(access_token),
                token_expires_at=record.expires_at,
                last_unlocked_at=now,
            )
        )
        self._audit(
            unlocked,
            BoardSearchShareAuditEventType.UNLOCKED,
            "BOARD_SEARCH_SHARE_UNLOCKED",
            {},
            now,
        )
        return UnlockedBoardSearchShare(_context(unlocked), access_token)

    def authenticate(self, access_token: str) -> BoardSearchShareContext:
        """Resolve a recipient's token to its one-game scope, or fail."""

        self._require_enabled()
        now = self._now()
        record = self._repository.find_session_by_token_hash(hash_access_token(access_token))
        if (
            record is None
            or record.revoked_at is not None
            or record.locked_at is not None
            or record.expires_at <= now
            or record.token_hash is None
            or record.token_expires_at is None
            or record.token_expires_at <= now
            or not hmac.compare_digest(record.token_hash, hash_access_token(access_token))
        ):
            raise BoardSearchShareAuthenticationError(
                "BOARD_SEARCH_SHARE_TOKEN_INVALID",
                "The share access has expired or is invalid; enter the code again.",
            )
        return _context(record)

    def _require_enabled(self) -> None:
        if not self._enabled:
            raise BoardSearchShareUnavailableError(
                "BOARD_SEARCH_SHARE_DISABLED",
                "Online board-search sharing is disabled on this host.",
            )

    def _audit(
        self,
        record: BoardSearchShareRecord,
        event_type: BoardSearchShareAuditEventType,
        outcome_code: str,
        payload: dict[str, object],
        now: datetime,
    ) -> None:
        self._repository.append_audit_event(
            session_id=record.id,
            event_type=event_type,
            outcome_code=outcome_code,
            payload=payload,
            created_at=now,
        )


def board_search_share_status(
    record: BoardSearchShareRecord, now: datetime
) -> BoardSearchShareStatus:
    if record.revoked_at is not None:
        return BoardSearchShareStatus.REVOKED
    if record.expires_at <= now:
        return BoardSearchShareStatus.EXPIRED
    if record.locked_at is not None:
        return BoardSearchShareStatus.LOCKED
    return BoardSearchShareStatus.ACTIVE


def _view(record: BoardSearchShareRecord, now: datetime) -> BoardSearchShareView:
    return BoardSearchShareView(
        session_id=record.id,
        game_id=record.game_id,
        label=record.label,
        status=board_search_share_status(record, now),
        failed_attempts=record.failed_attempts,
        created_at=record.created_at,
        expires_at=record.expires_at,
        locked_at=record.locked_at,
        revoked_at=record.revoked_at,
        last_unlocked_at=record.last_unlocked_at,
    )


def _context(record: BoardSearchShareRecord) -> BoardSearchShareContext:
    return BoardSearchShareContext(
        session_id=record.id,
        game_id=record.game_id,
        label=record.label,
        expires_at=record.expires_at,
    )


def _not_found() -> BoardSearchShareNotFoundError:
    return BoardSearchShareNotFoundError(
        "BOARD_SEARCH_SHARE_NOT_FOUND", "This share link does not exist or has expired."
    )


def _locked() -> BoardSearchShareAuthenticationError:
    return BoardSearchShareAuthenticationError(
        "BOARD_SEARCH_SHARE_LOCKED",
        "This share link is locked after too many wrong codes; ask for a new link.",
    )


def _active_limit_reached() -> BoardSearchShareConflictError:
    return BoardSearchShareConflictError(
        "BOARD_SEARCH_SHARE_ACTIVE_LIMIT",
        "At most 5 share links can be active at once; stop one first.",
    )


__all__ = [
    "BoardSearchShareAccessService",
    "BoardSearchShareContext",
    "BoardSearchShareReadiness",
    "BoardSearchShareRecord",
    "BoardSearchShareRepository",
    "BoardSearchShareView",
    "CreatedBoardSearchShare",
    "SESSION_LIST_LIMIT_MAX",
    "UnlockedBoardSearchShare",
    "assert_board_search_share_ready",
    "board_search_share_status",
]
