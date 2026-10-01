"""Query log writes and request limits for the public share surface
(D-471, D-472, TASK-0767)."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from threading import Lock
from typing import Protocol
from uuid import UUID

from game_predictor_api.application.board_search_share_access import BoardSearchShareContext
from game_predictor_api.domain.board_search_share_queries import (
    QUERY_LOG_PAGE_SIZE_MAX,
    BoardSearchShareQueryEntry,
    BoardSearchShareQueryKind,
    decode_query_log_cursor,
    encode_query_log_cursor,
)
from game_predictor_api.domain.board_search_shares import (
    BoardSearchShareError,
    BoardSearchShareNotFoundError,
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


@dataclass(frozen=True, slots=True)
class BoardSearchShareQueryEvent:
    """One stored query log entry as the local owner reads it."""

    id: UUID
    session_id: UUID
    game_id: UUID
    occurred_at: datetime
    kind: BoardSearchShareQueryKind
    request: dict[str, object]
    result_summary: dict[str, object]
    outcome_code: str


@dataclass(frozen=True, slots=True)
class BoardSearchShareQueryPage:
    entries: tuple[BoardSearchShareQueryEvent, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class BoardSearchShareQueryReplay:
    """What the Admin needs to reproduce an entry (R5): the entry itself,
    the pattern of the nearest earlier successful search of the same link
    and, for a board detail, the nearest earlier successful range."""

    event: BoardSearchShareQueryEvent
    search: BoardSearchShareQueryEvent | None
    approximate_win: BoardSearchShareQueryEvent | None


class BoardSearchShareQueryRepository(Protocol):
    def session_exists(self, session_id: UUID) -> bool: ...

    def list_events(
        self,
        *,
        session_id: UUID,
        before: tuple[datetime, UUID] | None,
        limit: int,
    ) -> Sequence[BoardSearchShareQueryEvent]:
        """Newest first by `(occurred_at, id)`, strictly before `before`."""
        ...

    def get_event(self, event_id: UUID) -> BoardSearchShareQueryEvent | None: ...

    def latest_successful_event(
        self,
        *,
        session_id: UUID,
        kind: BoardSearchShareQueryKind,
        at_or_before: tuple[datetime, UUID],
    ) -> BoardSearchShareQueryEvent | None:
        """The newest `ok` entry of `kind` at or before the given key."""
        ...


class BoardSearchShareQueryLogService:
    def __init__(self, repository: BoardSearchShareQueryRepository) -> None:
        self._repository = repository

    def list(
        self,
        *,
        session_id: UUID,
        before_cursor: str | None = None,
        limit: int = QUERY_LOG_PAGE_SIZE_MAX,
    ) -> BoardSearchShareQueryPage:
        if not 1 <= limit <= QUERY_LOG_PAGE_SIZE_MAX:
            raise BoardSearchShareError(
                "BOARD_SEARCH_SHARE_QUERY_LIMIT_INVALID",
                "The query log page size must be between 1 and 50.",
            )
        if not self._repository.session_exists(session_id):
            raise BoardSearchShareNotFoundError(
                "BOARD_SEARCH_SHARE_NOT_FOUND", "This share link does not exist."
            )
        before = None if before_cursor is None else decode_query_log_cursor(before_cursor)
        rows = tuple(
            self._repository.list_events(session_id=session_id, before=before, limit=limit + 1)
        )
        entries = rows[:limit]
        last = entries[-1] if len(rows) > limit else None
        return BoardSearchShareQueryPage(
            entries=entries,
            next_cursor=None
            if last is None
            else encode_query_log_cursor(last.occurred_at, last.id),
        )

    def replay(self, event_id: UUID) -> BoardSearchShareQueryReplay:
        event = self._repository.get_event(event_id)
        if event is None:
            raise BoardSearchShareNotFoundError(
                "BOARD_SEARCH_SHARE_QUERY_NOT_FOUND", "This query log entry does not exist."
            )
        key = (event.occurred_at, event.id)
        search = (
            event
            if event.kind is BoardSearchShareQueryKind.SEARCH
            else self._repository.latest_successful_event(
                session_id=event.session_id,
                kind=BoardSearchShareQueryKind.SEARCH,
                at_or_before=key,
            )
        )
        approximate_win: BoardSearchShareQueryEvent | None = None
        if event.kind is BoardSearchShareQueryKind.APPROXIMATE_WIN:
            approximate_win = event
        elif event.kind is BoardSearchShareQueryKind.BOARD_DETAIL:
            approximate_win = self._repository.latest_successful_event(
                session_id=event.session_id,
                kind=BoardSearchShareQueryKind.APPROXIMATE_WIN,
                at_or_before=key,
            )
        return BoardSearchShareQueryReplay(
            event=event, search=search, approximate_win=approximate_win
        )


def _rate_limited() -> BoardSearchShareRateLimitError:
    return BoardSearchShareRateLimitError(
        "BOARD_SEARCH_SHARE_RATE_LIMITED",
        "Too many requests through this share link; wait a moment and try again.",
    )


__all__ = [
    "BoardSearchShareQueryEvent",
    "BoardSearchShareQueryLog",
    "BoardSearchShareQueryLogService",
    "BoardSearchShareQueryPage",
    "BoardSearchShareQueryReplay",
    "BoardSearchShareQueryRepository",
    "BoardSearchShareRateLimiter",
    "BoardSearchShareRequestKind",
    "record_board_search_share_query",
]
