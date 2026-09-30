"""Query log writes and request limits for the public share surface
(D-471, D-472, TASK-0767)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from threading import Lock
from typing import Protocol
from uuid import UUID

from game_predictor_api.application.board_search_share_access import BoardSearchShareContext
from game_predictor_api.domain.board_search_share_queries import BoardSearchShareQueryEntry
from game_predictor_api.domain.board_search_shares import (
    BoardSearchShareRateLimitError,
    BoardSearchShareUnavailableError,
)


class BoardSearchShareQueryLog(Protocol):
    def record(
        self,
        *,
        session_id: UUID,
        game_id: UUID,
        entry: BoardSearchShareQueryEntry,
        occurred_at: datetime,
    ) -> None:
        """Durably store one entry (committed before returning)."""
        ...


def record_board_search_share_query(
    log: BoardSearchShareQueryLog,
    *,
    context: BoardSearchShareContext,
    entry: BoardSearchShareQueryEntry,
    now: datetime | None = None,
) -> None:
    """Fail closed (R5): a query whose entry cannot be stored returns no
    data, only `503 BOARD_SEARCH_SHARE_QUERY_LOG_UNAVAILABLE`."""

    try:
        log.record(
            session_id=context.session_id,
            game_id=context.game_id,
            entry=entry,
            occurred_at=now or datetime.now(UTC),
        )
    except Exception as error:
        raise BoardSearchShareUnavailableError(
            "BOARD_SEARCH_SHARE_QUERY_LOG_UNAVAILABLE",
            "The query could not be recorded, so no data is returned; try again later.",
        ) from error


class BoardSearchShareRequestKind(StrEnum):
    JSON = "json"
    IMAGE = "image"
    APPROXIMATE_WIN = "approximate_win"


_DEFAULT_LIMITS_PER_MINUTE = {
    BoardSearchShareRequestKind.JSON: 120,
    BoardSearchShareRequestKind.IMAGE: 600,
    BoardSearchShareRequestKind.APPROXIMATE_WIN: 10,
}


class BoardSearchShareRateLimiter:
    """Per-session fixed-window limits and one range calculation at a time.

    In-process state: the local API is a single process, and the limits only
    protect this host from one recipient's burst."""

    def __init__(
        self,
        *,
        limits_per_minute: dict[BoardSearchShareRequestKind, int] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._limits = dict(limits_per_minute or _DEFAULT_LIMITS_PER_MINUTE)
        self._window = timedelta(minutes=1)
        self._now = now or (lambda: datetime.now(UTC))
        self._entries: dict[tuple[UUID, BoardSearchShareRequestKind], tuple[datetime, int]] = {}
        self._running_calculations: set[UUID] = set()
        self._lock = Lock()

    def consume(self, session_id: UUID, kind: BoardSearchShareRequestKind) -> None:
        now = self._now()
        key = (session_id, kind)
        with self._lock:
            started_at, count = self._entries.get(key, (now, 0))
            if now - started_at >= self._window:
                started_at, count = now, 0
            if count >= self._limits[kind]:
                raise _rate_limited()
            self._entries[key] = (started_at, count + 1)
            self._forget_stale_entries(now)

    @contextmanager
    def calculation_slot(self, session_id: UUID) -> Iterator[None]:
        with self._lock:
            if session_id in self._running_calculations:
                raise _rate_limited()
            self._running_calculations.add(session_id)
        try:
            yield
        finally:
            with self._lock:
                self._running_calculations.discard(session_id)

    def _forget_stale_entries(self, now: datetime) -> None:
        if len(self._entries) < 1_000:
            return
        for key, (started_at, _count) in tuple(self._entries.items()):
            if now - started_at >= self._window:
                del self._entries[key]


def _rate_limited() -> BoardSearchShareRateLimitError:
    return BoardSearchShareRateLimitError(
        "BOARD_SEARCH_SHARE_RATE_LIMITED",
        "Too many requests through this share link; wait a moment and try again.",
    )


__all__ = [
    "BoardSearchShareQueryLog",
    "BoardSearchShareRateLimiter",
    "BoardSearchShareRequestKind",
    "record_board_search_share_query",
]
