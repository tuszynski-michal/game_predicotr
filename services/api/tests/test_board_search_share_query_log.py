"""Query log reading and replay for the local owner (TASK-0771, D-472)."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.board_search_share_queries import (
    BoardSearchShareQueryEvent,
    BoardSearchShareQueryLogService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_search_share_queries import (
    BoardSearchShareQueryKind,
    decode_query_log_cursor,
    encode_query_log_cursor,
)
from game_predictor_api.domain.board_search_shares import (
    BoardSearchShareError,
    BoardSearchShareNotFoundError,
)
from game_predictor_api.main import create_app

SESSION = UUID(int=1)
OTHER_SESSION = UUID(int=2)
GAME = UUID(int=7)
T0 = datetime(2099, 9, 30, 10, 0, tzinfo=UTC)


class MemoryQueryRepository:
    def __init__(self, events: Sequence[BoardSearchShareQueryEvent]) -> None:
        self.events = list(events)

    def session_exists(self, session_id: UUID) -> bool:
        return session_id in {SESSION, OTHER_SESSION}

    def list_events(
        self, *, session_id: UUID, before: tuple[datetime, UUID] | None, limit: int
    ) -> Sequence[BoardSearchShareQueryEvent]:
        rows = sorted(
            (event for event in self.events if event.session_id == session_id),
            key=lambda event: (event.occurred_at, event.id),
            reverse=True,
        )
        if before is not None:
            rows = [row for row in rows if (row.occurred_at, row.id) < before]
        return rows[:limit]

    def get_event(self, event_id: UUID) -> BoardSearchShareQueryEvent | None:
        return next((event for event in self.events if event.id == event_id), None)

    def latest_successful_event(
        self,
        *,
        session_id: UUID,
        kind: BoardSearchShareQueryKind,
        at_or_before: tuple[datetime, UUID],
    ) -> BoardSearchShareQueryEvent | None:
        rows = [
            event
            for event in self.events
            if event.session_id == session_id
            and event.kind is kind
            and event.outcome_code == "ok"
            and (event.occurred_at, event.id) <= at_or_before
        ]
        return max(rows, key=lambda event: (event.occurred_at, event.id), default=None)


def _event(
    kind: BoardSearchShareQueryKind,
    minute: int,
    *,
    session_id: UUID = SESSION,
    outcome: str = "ok",
    event_id: UUID | None = None,
    request: dict[str, object] | None = None,
) -> BoardSearchShareQueryEvent:
    return BoardSearchShareQueryEvent(
        id=event_id or uuid4(),
        session_id=session_id,
        game_id=GAME,
        occurred_at=T0 + timedelta(minutes=minute),
        kind=kind,
        request=request or {},
        result_summary={} if outcome != "ok" else {"resultCount": 1},
        outcome_code=outcome,
    )


def test_pages_are_newest_first_without_duplicates_at_equal_times() -> None:
    same_time = [
        _event(BoardSearchShareQueryKind.SEARCH, 5, event_id=UUID(int=100 + index))
        for index in range(5)
    ]
    older = [_event(BoardSearchShareQueryKind.SEARCH, minute) for minute in range(3)]
    other = [_event(BoardSearchShareQueryKind.SEARCH, 9, session_id=OTHER_SESSION)]
    service = BoardSearchShareQueryLogService(MemoryQueryRepository(same_time + older + other))

    seen: list[UUID] = []
    cursor: str | None = None
    pages = 0
    while True:
        page = service.list(session_id=SESSION, before_cursor=cursor, limit=3)
        seen.extend(entry.id for entry in page.entries)
        pages += 1
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    assert pages == 3
    assert len(seen) == len(set(seen)) == 8
    assert seen[:5] == [UUID(int=104), UUID(int=103), UUID(int=102), UUID(int=101), UUID(int=100)]
    assert other[0].id not in seen


def test_page_limits_and_unknown_sessions() -> None:
    service = BoardSearchShareQueryLogService(MemoryQueryRepository([]))
    for limit in (0, 51):
        with pytest.raises(BoardSearchShareError) as error:
            service.list(session_id=SESSION, limit=limit)
        assert error.value.code == "BOARD_SEARCH_SHARE_QUERY_LIMIT_INVALID"
    with pytest.raises(BoardSearchShareNotFoundError):
        service.list(session_id=UUID(int=99))
    assert service.list(session_id=SESSION).entries == ()
    with pytest.raises(BoardSearchShareError) as error:
        service.list(session_id=SESSION, before_cursor="not-a-cursor")
    assert error.value.code == "BOARD_SEARCH_SHARE_QUERY_CURSOR_INVALID"


def test_cursor_round_trip() -> None:
    event_id = uuid4()
    assert decode_query_log_cursor(encode_query_log_cursor(T0, event_id)) == (T0, event_id)


def test_replay_of_a_search_is_the_search_itself() -> None:
    search = _event(BoardSearchShareQueryKind.SEARCH, 1, request={"cells": ["0:A"]})
    replay = BoardSearchShareQueryLogService(MemoryQueryRepository([search])).replay(search.id)
    assert replay.search == search
    assert replay.approximate_win is None


def test_replay_of_a_range_uses_the_nearest_earlier_successful_search() -> None:
    first = _event(BoardSearchShareQueryKind.SEARCH, 1)
    failed = _event(BoardSearchShareQueryKind.SEARCH, 2, outcome="BOARD_SEARCH_QUERY_EMPTY")
    nearest = _event(BoardSearchShareQueryKind.SEARCH, 3)
    later = _event(BoardSearchShareQueryKind.SEARCH, 9)
    foreign = _event(BoardSearchShareQueryKind.SEARCH, 4, session_id=OTHER_SESSION)
    rng = _event(BoardSearchShareQueryKind.APPROXIMATE_WIN, 5)
    service = BoardSearchShareQueryLogService(
        MemoryQueryRepository([first, failed, nearest, later, foreign, rng])
    )
    replay = service.replay(rng.id)
    assert replay.search == nearest
    assert replay.approximate_win == rng


def test_replay_of_a_board_detail_brings_search_and_range_or_nothing() -> None:
    search = _event(BoardSearchShareQueryKind.SEARCH, 1)
    rng = _event(BoardSearchShareQueryKind.APPROXIMATE_WIN, 2)
    detail = _event(BoardSearchShareQueryKind.BOARD_DETAIL, 3)
    replay = BoardSearchShareQueryLogService(MemoryQueryRepository([search, rng, detail])).replay(
        detail.id
    )
    assert (replay.search, replay.approximate_win) == (search, rng)

    lonely = _event(BoardSearchShareQueryKind.BOARD_DETAIL, 1)
    replay = BoardSearchShareQueryLogService(MemoryQueryRepository([lonely])).replay(lonely.id)
    assert replay.search is None and replay.approximate_win is None
    with pytest.raises(BoardSearchShareNotFoundError) as error:
        BoardSearchShareQueryLogService(MemoryQueryRepository([])).replay(uuid4())
    assert error.value.code == "BOARD_SEARCH_SHARE_QUERY_NOT_FOUND"


def _client(events: Sequence[BoardSearchShareQueryEvent]) -> TestClient:
    service = BoardSearchShareQueryLogService(MemoryQueryRepository(events))
    app = create_app(
        ApiSettings(host="127.0.0.1", port=8000, admin_origin="http://127.0.0.1:3000"),
        board_search_share_query_log_service_dependency=lambda: service,
    )
    return TestClient(app, base_url="https://testserver")


def test_http_query_log_pages_and_replay() -> None:
    search = _event(
        BoardSearchShareQueryKind.SEARCH,
        1,
        request={"cells": ["0:A", "3:?"], "scope": "all_searchable", "limit": 5},
    )
    rng = _event(
        BoardSearchShareQueryKind.APPROXIMATE_WIN,
        2,
        request={"startSequenceNumber": 7, "spinCount": 100},
    )
    older = [_event(BoardSearchShareQueryKind.SEARCH, -minute) for minute in range(1, 3)]
    with _client([search, rng, *older]) as client:
        base = f"/api/v1/admin/board-search-shares/sessions/{SESSION}/queries"
        first = client.get(base, params={"limit": 2})
        assert first.status_code == 200, first.text
        body = first.json()
        assert [entry["id"] for entry in body["entries"]] == [str(rng.id), str(search.id)]
        assert body["entries"][1]["request"]["cells"] == ["0:A", "3:?"]
        assert body["nextCursor"] is not None
        for entry in body["entries"]:
            assert set(entry) == {
                "id",
                "sessionId",
                "gameId",
                "occurredAt",
                "kind",
                "request",
                "resultSummary",
                "outcomeCode",
            }
        second = client.get(base, params={"limit": 2, "before": body["nextCursor"]})
        assert [entry["id"] for entry in second.json()["entries"]] == [
            str(older[0].id),
            str(older[1].id),
        ]
        assert second.json()["nextCursor"] is None
        assert (
            client.get(
                f"/api/v1/admin/board-search-shares/sessions/{UUID(int=9)}/queries"
            ).status_code
            == 404
        )
        assert client.get(base, params={"before": "bad"}).status_code == 422
        replay = client.get(f"/api/v1/admin/board-search-shares/queries/{rng.id}")
        assert replay.status_code == 200, replay.text
        assert replay.json()["search"]["id"] == str(search.id)
        assert replay.json()["approximateWin"]["id"] == str(rng.id)
        assert client.get(f"/api/v1/admin/board-search-shares/queries/{uuid4()}").status_code == 404
