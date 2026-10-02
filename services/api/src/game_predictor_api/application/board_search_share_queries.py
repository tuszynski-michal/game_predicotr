"""Query log writes and request limits for the public share surface
(D-471, D-472, TASK-0767)."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
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
    BoardSearchShareRequestKind.APPROXIMATE_WIN: 30,
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
    # For a search: the request of the newest successful range calculation
    # the recipient made before their next search (D-478).
    follow_up_approximate_win: dict[str, object] | None = None
    # For a grouped search (TASK-0816): when the same pattern was searched
    # through this link, newest first; the entry itself is the newest one.
    occurrence_times: tuple[datetime, ...] = ()


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
        kind: BoardSearchShareQueryKind | None = None,
    ) -> Sequence[BoardSearchShareQueryEvent]:
        """Newest first by `(occurred_at, id)`, strictly before `before`."""
        ...

    def next_event_key(
        self,
        *,
        session_id: UUID,
        kind: BoardSearchShareQueryKind | None,
        after: tuple[datetime, UUID],
    ) -> tuple[datetime, UUID] | None:
        """The key of the oldest entry of `kind` (any kind for `None`)
        strictly after `after`."""
        ...

    def latest_successful_event_between(
        self,
        *,
        session_id: UUID,
        kind: BoardSearchShareQueryKind,
        after: tuple[datetime, UUID],
        before: tuple[datetime, UUID] | None,
    ) -> BoardSearchShareQueryEvent | None:
        """The newest `ok` entry of `kind` strictly between the keys."""
        ...

    def delete_events(
        self,
        *,
        session_id: UUID,
        start: tuple[datetime, UUID],
        end: tuple[datetime, UUID] | None,
    ) -> int:
        """Durably delete entries with `start <= key < end`; returns the count."""
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


# A link's searches are grouped in memory; one recipient's log stays far
# below this bound, and older searches beyond it are simply not grouped in.
_GROUPED_SEARCH_SCAN_MAX = 10_000


def _pattern_key(event: BoardSearchShareQueryEvent) -> str:
    return json.dumps(event.request.get("cells"), ensure_ascii=False)


class BoardSearchShareQueryLogService:
    def __init__(self, repository: BoardSearchShareQueryRepository) -> None:
        self._repository = repository

    def list(
        self,
        *,
        session_id: UUID,
        before_cursor: str | None = None,
        limit: int = QUERY_LOG_PAGE_SIZE_MAX,
        kind: BoardSearchShareQueryKind | None = None,
        group_by_pattern: bool = False,
    ) -> BoardSearchShareQueryPage:
        """`group_by_pattern` (TASK-0816) lists every searched pattern once,
        at its newest search, with the times of all its searches."""

        if group_by_pattern and kind is not BoardSearchShareQueryKind.SEARCH:
            raise BoardSearchShareError(
                "BOARD_SEARCH_SHARE_QUERY_GROUP_INVALID",
                "Only searches can be grouped by their pattern.",
            )
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
        if group_by_pattern:
            return self._grouped_page(session_id=session_id, before=before, limit=limit)
        rows = tuple(
            self._repository.list_events(
                session_id=session_id, before=before, limit=limit + 1, kind=kind
            )
        )
        entries = rows[:limit]
        last = entries[-1] if len(rows) > limit else None
        return BoardSearchShareQueryPage(
            entries=tuple(self._with_follow_up(entry) for entry in entries),
            next_cursor=None
            if last is None
            else encode_query_log_cursor(last.occurred_at, last.id),
        )

    def _grouped_page(
        self,
        *,
        session_id: UUID,
        before: tuple[datetime, UUID] | None,
        limit: int,
    ) -> BoardSearchShareQueryPage:
        heads = [
            group
            for group in self._pattern_groups(session_id)
            if before is None or (group[0].occurred_at, group[0].id) < before
        ]
        page = heads[:limit]
        last = page[-1][0] if len(heads) > limit else None
        return BoardSearchShareQueryPage(
            entries=tuple(self._group_entry(group) for group in page),
            next_cursor=None
            if last is None
            else encode_query_log_cursor(last.occurred_at, last.id),
        )

    def _pattern_groups(self, session_id: UUID) -> list[list[BoardSearchShareQueryEvent]]:
        """The link's searches by pattern; groups and members newest first."""

        groups: dict[str, list[BoardSearchShareQueryEvent]] = {}
        for event in self._repository.list_events(
            session_id=session_id,
            before=None,
            limit=_GROUPED_SEARCH_SCAN_MAX,
            kind=BoardSearchShareQueryKind.SEARCH,
        ):
            groups.setdefault(_pattern_key(event), []).append(event)
        return list(groups.values())

    def _group_entry(self, group: list[BoardSearchShareQueryEvent]) -> BoardSearchShareQueryEvent:
        # The chart is the range of the newest search of this pattern that
        # was followed by one.
        follow_up = next(
            (
                member.follow_up_approximate_win
                for member in map(self._with_follow_up, group)
                if member.follow_up_approximate_win is not None
            ),
            None,
        )
        return replace(
            group[0],
            follow_up_approximate_win=follow_up,
            occurrence_times=tuple(member.occurred_at for member in group),
        )

    def delete(self, event_id: UUID, *, whole_pattern: bool = False) -> int:
        """Remove one entry from the owner's log (D-478). A search takes its
        follow-up entries (ranges, board details) up to the next search with
        it, so nothing of that search stays behind unseen. `whole_pattern`
        (TASK-0816) removes every search of the same pattern that way."""

        event = self._repository.get_event(event_id)
        if event is None:
            raise BoardSearchShareNotFoundError(
                "BOARD_SEARCH_SHARE_QUERY_NOT_FOUND", "This query log entry does not exist."
            )
        if whole_pattern and event.kind is BoardSearchShareQueryKind.SEARCH:
            pattern = _pattern_key(event)
            return sum(
                self._delete_event(member)
                for group in self._pattern_groups(event.session_id)
                if _pattern_key(group[0]) == pattern
                for member in group
            )
        return self._delete_event(event)

    def _delete_event(self, event: BoardSearchShareQueryEvent) -> int:
        key = (event.occurred_at, event.id)
        # Any other entry ends at its direct successor: only itself goes.
        end = self._repository.next_event_key(
            session_id=event.session_id,
            kind=BoardSearchShareQueryKind.SEARCH
            if event.kind is BoardSearchShareQueryKind.SEARCH
            else None,
            after=key,
        )
        return self._repository.delete_events(session_id=event.session_id, start=key, end=end)

    def _with_follow_up(self, event: BoardSearchShareQueryEvent) -> BoardSearchShareQueryEvent:
        if event.kind is not BoardSearchShareQueryKind.SEARCH:
            return event
        key = (event.occurred_at, event.id)
        follow_up = self._repository.latest_successful_event_between(
            session_id=event.session_id,
            kind=BoardSearchShareQueryKind.APPROXIMATE_WIN,
            after=key,
            before=self._repository.next_event_key(
                session_id=event.session_id, kind=BoardSearchShareQueryKind.SEARCH, after=key
            ),
        )
        if follow_up is None:
            return event
        return replace(event, follow_up_approximate_win=dict(follow_up.request))

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
