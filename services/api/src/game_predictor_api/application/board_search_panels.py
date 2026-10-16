"""Capability links grouping immutable single-game search sessions."""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from secrets import token_bytes
from typing import Protocol
from uuid import UUID, uuid4

from game_predictor_api.application.access_credentials import (
    generate_access_token,
    generate_code_salt,
    hash_access_token,
)
from game_predictor_api.application.board_search_share_access import (
    BoardSearchShareReadiness,
    BoardSearchShareRecord,
    BoardSearchShareRepository,
)
from game_predictor_api.domain.board_search_shares import (
    BOARD_SEARCH_SHARE_MAX_ACTIVE_SESSIONS,
    BoardSearchShareAuditEventType,
    BoardSearchShareAuthenticationError,
    BoardSearchShareConflictError,
    BoardSearchShareError,
    BoardSearchShareNotFoundError,
    BoardSearchShareUnavailableError,
    normalize_board_search_share_label,
    validate_board_search_share_lifetime,
)

PANEL_COOKIE = "gp_board_search_panel"
PANEL_COOKIE_PATH = "/board-search-panel-api"
PANEL_PROXY_HEADER = "X-Board-Search-Panel-Proxy"
PANEL_PROXY_INTENT = "reviewer-board-search-panel-v1"


def panel_child_token(secret: str, panel_id: UUID, session_id: UUID) -> str:
    message = f"board-search-panel-v1\n{panel_id}\n{session_id}".encode("ascii")
    return hmac.new(secret.encode("ascii"), message, hashlib.sha256).hexdigest()


@dataclass(frozen=True, slots=True)
class BoardSearchPanelRecord:
    id: UUID
    label: str | None
    secret_hash: bytes
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class BoardSearchPanelGame:
    game_id: UUID
    game_name: str
    session_id: UUID


@dataclass(frozen=True, slots=True)
class BoardSearchPanelView:
    panel_id: UUID
    label: str | None
    created_at: datetime
    expires_at: datetime
    status: str
    games: tuple[BoardSearchPanelGame, ...]


@dataclass(frozen=True, slots=True)
class CreatedBoardSearchPanel:
    panel: BoardSearchPanelView
    link_key: str


class BoardSearchPanelRepository(Protocol):
    def add(self, record: BoardSearchPanelRecord) -> None: ...
    def get(self, panel_id: UUID, *, lock: bool = False) -> BoardSearchPanelRecord | None: ...
    def save(self, record: BoardSearchPanelRecord) -> None: ...
    def list(self, limit: int) -> Sequence[BoardSearchPanelRecord]: ...
    def games(self, panel_id: UUID) -> Sequence[BoardSearchPanelGame]: ...


class BoardSearchPanelService:
    def __init__(
        self,
        panels: BoardSearchPanelRepository,
        shares: BoardSearchShareRepository,
        *,
        readiness: BoardSearchShareReadiness,
        enabled: bool,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._panels = panels
        self._shares = shares
        self._readiness = readiness
        self._enabled = enabled
        self._now = now or (lambda: datetime.now(UTC))

    def assert_can_create(
        self, *, game_ids: Sequence[UUID], lifetime_minutes: int, label: str | None
    ) -> tuple[UUID, ...]:
        self._require_enabled()
        validate_board_search_share_lifetime(lifetime_minutes)
        normalize_board_search_share_label(label)
        ids = tuple(sorted(game_ids))
        if not ids or len(ids) > 100 or len(set(ids)) != len(ids):
            raise BoardSearchShareError(
                "BOARD_SEARCH_PANEL_GAMES_INVALID", "Select 1..100 distinct available games."
            )
        for game_id in ids:
            self._readiness(game_id)
        if (
            self._shares.count_active_sessions(self._now())
            >= BOARD_SEARCH_SHARE_MAX_ACTIVE_SESSIONS
        ):
            raise _limit()
        return ids

    def create(
        self, *, game_ids: Sequence[UUID], lifetime_minutes: int, label: str | None
    ) -> CreatedBoardSearchPanel:
        ids = self.assert_can_create(
            game_ids=game_ids, lifetime_minutes=lifetime_minutes, label=label
        )
        now = self._now()
        if self._shares.count_active_sessions_locked(now) >= BOARD_SEARCH_SHARE_MAX_ACTIVE_SESSIONS:
            raise _limit()
        panel_id, secret = uuid4(), generate_access_token()
        record = BoardSearchPanelRecord(
            id=panel_id,
            label=normalize_board_search_share_label(label),
            secret_hash=hash_access_token(secret),
            created_at=now,
            expires_at=now + timedelta(minutes=lifetime_minutes),
        )
        self._panels.add(record)
        for game_id in ids:
            session_id, salt = uuid4(), generate_code_salt()
            self._shares.add_session(
                BoardSearchShareRecord(
                    id=session_id,
                    game_id=game_id,
                    panel_id=panel_id,
                    label=record.label,
                    code_salt=salt,
                    # Legacy columns remain structurally valid, but code unlock
                    # is forbidden for these children. No unused PBKDF2 work.
                    code_hash=token_bytes(32),
                    failed_attempts=0,
                    locked_at=None,
                    revoked_at=None,
                    token_hash=hash_access_token(panel_child_token(secret, panel_id, session_id)),
                    token_expires_at=record.expires_at,
                    last_unlocked_at=None,
                    created_at=now,
                    expires_at=record.expires_at,
                )
            )
            self._shares.append_audit_event(
                session_id=session_id,
                event_type=BoardSearchShareAuditEventType.CREATED,
                outcome_code="BOARD_SEARCH_PANEL_CREATED",
                payload={"panelId": str(panel_id), "lifetimeMinutes": lifetime_minutes},
                created_at=now,
            )
        return CreatedBoardSearchPanel(self._view(record), secret)

    def list(self, limit: int = 100) -> tuple[BoardSearchPanelView, ...]:
        if not 1 <= limit <= 100:
            raise BoardSearchShareError("BOARD_SEARCH_PANEL_LIMIT_INVALID", "Invalid list limit.")
        return tuple(self._view(record) for record in self._panels.list(limit))

    def authenticate(self, panel_id: UUID, secret: str) -> BoardSearchPanelView:
        self._require_enabled()
        record = self._panels.get(panel_id)
        if (
            not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", secret)
            or record is None
            or record.revoked_at is not None
            or record.expires_at <= self._now()
            or not hmac.compare_digest(record.secret_hash, hash_access_token(secret))
        ):
            raise BoardSearchShareAuthenticationError(
                "BOARD_SEARCH_PANEL_ACCESS_INVALID", "The link has expired or was stopped."
            )
        return self._view(record)

    def revoke(self, panel_id: UUID) -> BoardSearchPanelView:
        record = self._panels.get(panel_id, lock=True)
        if record is None:
            raise BoardSearchShareNotFoundError("BOARD_SEARCH_PANEL_NOT_FOUND", "Panel not found.")
        if record.revoked_at is None:
            now = self._now()
            # Child row locks also serialize all existing symbol corrections.
            for game in sorted(self._panels.games(panel_id), key=lambda item: item.session_id):
                child = self._shares.get_session_for_update(game.session_id)
                if child is None or child.panel_id != panel_id:
                    raise RuntimeError("Panel membership changed.")
                self._shares.save_session(
                    replace(child, revoked_at=now, token_hash=None, token_expires_at=None)
                )
                self._shares.append_audit_event(
                    session_id=child.id,
                    event_type=BoardSearchShareAuditEventType.REVOKED,
                    outcome_code="BOARD_SEARCH_PANEL_REVOKED",
                    payload={},
                    created_at=now,
                )
            record = replace(record, revoked_at=now)
            self._panels.save(record)
        return self._view(record)

    def _view(self, record: BoardSearchPanelRecord) -> BoardSearchPanelView:
        return BoardSearchPanelView(
            panel_id=record.id,
            label=record.label,
            created_at=record.created_at,
            expires_at=record.expires_at,
            status="revoked"
            if record.revoked_at
            else ("expired" if record.expires_at <= self._now() else "active"),
            games=tuple(self._panels.games(record.id)),
        )

    def _require_enabled(self) -> None:
        if not self._enabled:
            raise BoardSearchShareUnavailableError(
                "BOARD_SEARCH_SHARE_DISABLED", "Online search sharing is disabled."
            )


def _limit() -> BoardSearchShareConflictError:
    return BoardSearchShareConflictError(
        "BOARD_SEARCH_SHARE_ACTIVE_LIMIT", "At most 5 search links can be active."
    )
