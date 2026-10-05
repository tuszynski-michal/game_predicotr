"""Isolated PostgreSQL coverage for board-search share sessions (TASK-0766).

Migrates a throwaway `*_test`-style database to head and exercises the
share repository and service against it: persistence round trip, the
partial unique token index, check constraints, the active-session count
under its advisory lock, secret-free audit rows, the query-log table
constraints (D-472) and the real readiness check for a game without data.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.application.board_search_share_access import (
    BoardSearchShareAccessService,
    assert_board_search_share_ready,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_search import BoardSearchError
from game_predictor_api.storage.board_search_approximate_win_repository import (
    SqlAlchemyBoardSearchApproximateWinRepository,
)
from game_predictor_api.storage.board_search_share_repository import (
    SqlAlchemyBoardSearchShareRepository,
)
from game_predictor_api.storage.game_storage_routing import GameStorageRoutingError
from game_predictor_api.storage.models import (
    BoardSearchShareAuditEventModel,
    BoardSearchShareQueryEventModel,
    BoardSearchShareSessionModel,
    GameModel,
)
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)

NOW = datetime(2099, 9, 30, 10, 0, tzinfo=UTC)


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


@pytest.fixture(scope="module")
def database() -> Iterator[Engine]:
    name = "game_predictor_task0766_" + uuid4().hex[:12] + "_test"
    url = make_url(ApiSettings.from_environment().owner_database_url)
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5},
    )
    engine = create_engine(url.set(database=name), connect_args={"connect_timeout": 5})
    with maintenance.connect() as connection:
        connection.execute(text("SET statement_timeout='10s'"))
        connection.execute(text(f"CREATE DATABASE {_quote(name)}"))
    try:
        config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url",
            url.set(database=name).render_as_string(hide_password=False).replace("%", "%%"),
        )
        command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            connection.execute(text(f"DROP DATABASE {_quote(name)}"))
        maintenance.dispose()


def _game(engine: Engine) -> UUID:
    game_id = uuid4()
    with Session(engine) as session:
        session.add(
            GameModel(
                id=game_id,
                code="share-" + game_id.hex[:8],
                name="Share test",
                expected_layout_count=50,
            )
        )
        session.commit()
    return game_id


def _service(session: Session, *, now: datetime = NOW) -> BoardSearchShareAccessService:
    return BoardSearchShareAccessService(
        SqlAlchemyBoardSearchShareRepository(session),
        readiness=lambda _game_id: None,
        enabled=True,
        now=lambda: now,
    )


def test_session_lifecycle_round_trips_through_postgres(database: Engine) -> None:
    game_id = _game(database)
    with Session(database) as session:
        created = _service(session).create(game_id=game_id, lifetime_minutes=60, label="Ania")
        session.commit()
    session_id = created.session.session_id

    with Session(database) as session:
        unlocked = _service(session).unlock(session_id=session_id, access_code=created.access_code)
        session.commit()
    with Session(database) as session:
        context = _service(session).authenticate(unlocked.access_token)
        assert context.game_id == game_id
        stored = session.get(BoardSearchShareSessionModel, session_id)
        assert stored is not None
        assert stored.label == "Ania"
        assert stored.token_hash is not None and len(stored.token_hash) == 32
        assert stored.token_expires_at == NOW + timedelta(minutes=60)
        assert stored.last_unlocked_at == NOW

    with Session(database) as session:
        _service(session).revoke(session_id)
        session.commit()
    with Session(database) as session:
        stored = session.get(BoardSearchShareSessionModel, session_id)
        assert stored is not None
        assert stored.revoked_at == NOW and stored.token_hash is None
        events = session.scalars(
            select(BoardSearchShareAuditEventModel)
            .where(BoardSearchShareAuditEventModel.session_id == session_id)
            .order_by(
                BoardSearchShareAuditEventModel.created_at, BoardSearchShareAuditEventModel.id
            )
        ).all()
        assert sorted(event.event_type for event in events) == ["created", "revoked", "unlocked"]
        payload_text = " ".join(str(event.payload) for event in events)
        assert created.access_code not in payload_text
        assert unlocked.access_token not in payload_text


def test_active_count_ignores_revoked_locked_and_expired_sessions(database: Engine) -> None:
    game_id = _game(database)
    with Session(database) as session:
        repository = SqlAlchemyBoardSearchShareRepository(session)
        before = repository.count_active_sessions_locked(NOW)
        service = _service(session)
        kept = service.create(game_id=game_id, lifetime_minutes=60, label=None)
        revoked = service.create(game_id=game_id, lifetime_minutes=60, label=None)
        service.create(game_id=game_id, lifetime_minutes=5, label=None)
        service.revoke(revoked.session.session_id)
        session.commit()
    with Session(database) as session:
        repository = SqlAlchemyBoardSearchShareRepository(session)
        assert repository.count_active_sessions_locked(NOW) == before + 2
        assert repository.count_active_sessions(NOW + timedelta(minutes=6)) == before + 1
        assert kept.session.session_id in {
            record.id for record in repository.list_sessions(game_id=game_id, limit=10)
        }


def test_constraints_reject_invalid_rows(database: Engine) -> None:
    game_id = _game(database)

    def insert(**overrides: object) -> None:
        values: dict[str, object] = {
            "id": uuid4(),
            "game_id": game_id,
            "code_salt": b"s" * 16,
            "code_hash": b"h" * 32,
            "created_at": NOW,
            "expires_at": NOW + timedelta(hours=1),
        }
        values.update(overrides)
        with Session(database) as session:
            session.add(BoardSearchShareSessionModel(**values))
            session.commit()

    insert(token_hash=b"t" * 32, token_expires_at=NOW + timedelta(hours=1))
    for overrides in (
        {"failed_attempts": 6},
        {"expires_at": NOW},
        {"code_hash": b"h" * 31},
        {"token_hash": b"u" * 32},  # token without its expiry
        {"label": "   "},
        {"token_hash": b"t" * 32, "token_expires_at": NOW + timedelta(hours=1)},  # duplicate
        {"game_id": uuid4()},  # unknown game
    ):
        with pytest.raises(IntegrityError):
            insert(**overrides)


def test_query_log_table_enforces_kind_shape_and_size(database: Engine) -> None:
    game_id = _game(database)
    with Session(database) as session:
        created = _service(session).create(game_id=game_id, lifetime_minutes=60, label=None)
        session.commit()

    def insert(**overrides: object) -> None:
        values: dict[str, object] = {
            "id": uuid4(),
            "session_id": created.session.session_id,
            "game_id": game_id,
            "kind": "search",
            "request": {"cells": ["0:cherry"], "scope": "all_searchable", "limit": 5},
            "result_summary": {"resultCount": 0},
            "outcome_code": "ok",
        }
        values.update(overrides)
        with Session(database) as session:
            session.add(BoardSearchShareQueryEventModel(**values))
            session.commit()

    insert()
    for overrides in (
        {"kind": "unlock"},
        {"request": {"blob": "x" * 5000}},
        {"result_summary": {"blob": "x" * 3000}},
        {"outcome_code": " "},
    ):
        with pytest.raises(IntegrityError):
            insert(**overrides)
    # A game with share history cannot be deleted from under its log.
    with Session(database) as session, pytest.raises(IntegrityError):
        session.execute(text("DELETE FROM public.games WHERE id = :id"), {"id": game_id})
        session.commit()


def test_real_readiness_refuses_a_game_without_board_search_data(database: Engine) -> None:
    # A game without provisioned data storage has no board search to share:
    # the routing error (409 through the API) stops the link.
    game_id = _game(database)
    with Session(database) as session, pytest.raises(GameStorageRoutingError) as error:
        assert_board_search_share_ready(
            SqlAlchemyBoardSearchApproximateWinRepository(session), game_id
        )
    assert error.value.code == "GAME_STORAGE_LOCATION_MISSING"
    with Session(database) as session, pytest.raises(BoardSearchError) as missing:
        assert_board_search_share_ready(
            SqlAlchemyBoardSearchApproximateWinRepository(session), uuid4()
        )
    assert missing.value.code == "GAME_NOT_FOUND"


def test_query_log_writes_commit_under_the_game_storage_route(database: Engine) -> None:
    """The entry carries `game_id`, so the routed session binds the game's
    store before the flush; the public table must still receive the row."""

    from game_predictor_api.domain.board_search_share_queries import (
        BoardSearchShareQueryKind,
        build_board_search_share_query_entry,
        search_query_request,
        search_query_summary,
    )
    from game_predictor_api.storage.board_search_share_query_repository import (
        SqlAlchemyBoardSearchShareQueryLog,
    )
    from game_predictor_api.storage.database import create_session_factory
    from game_predictor_api.storage.game_data_v2_manifest_v5 import VERSION

    game_id = _game(database)
    with Session(database) as session:
        session.execute(
            text(
                "INSERT INTO public.game_storage_locations "
                "(game_id, store_schema, generation, manifest_version, status, revision) "
                "VALUES (:game_id, 'game_data_v2', 2, :version, 'active', 0)"
            ),
            {"game_id": game_id, "version": VERSION},
        )
        created = _service(session).create(game_id=game_id, lifetime_minutes=60, label=None)
        session.commit()

    log = SqlAlchemyBoardSearchShareQueryLog(create_session_factory(database))
    log.record(
        session_id=created.session.session_id,
        game_id=game_id,
        entry=build_board_search_share_query_entry(
            kind=BoardSearchShareQueryKind.SEARCH,
            request=search_query_request(cells=[(0, "cherry"), (4, None)], scope="all", limit=5),
            result_summary=search_query_summary([3, 9]),
            outcome_code="ok",
        ),
        occurred_at=NOW,
    )
    with Session(database) as session:
        rows = session.scalars(
            select(BoardSearchShareQueryEventModel).where(
                BoardSearchShareQueryEventModel.session_id == created.session.session_id
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].request == {"cells": ["0:cherry", "4:?"], "scope": "all", "limit": 5}
        assert rows[0].result_summary == {"resultCount": 2, "firstSequenceNumbers": [3, 9]}
        assert rows[0].game_id == game_id


def test_query_log_reads_page_by_key_and_replays_from_postgres(database: Engine) -> None:
    from game_predictor_api.application.board_search_share_queries import (
        BoardSearchShareQueryLogService,
    )
    from game_predictor_api.storage.board_search_share_query_repository import (
        SqlAlchemyBoardSearchShareQueryRepository,
    )

    game_id = _game(database)
    # Later than every other test's sessions, so the active limit is free.
    later = NOW + timedelta(days=2)
    with Session(database) as session:
        mine = _service(session, now=later).create(game_id=game_id, lifetime_minutes=60, label=None)
        other = _service(session, now=later).create(
            game_id=game_id, lifetime_minutes=60, label=None
        )
        session.commit()
    same_time = NOW + timedelta(minutes=5)
    ids = [UUID(int=1000 + index) for index in range(4)]
    with Session(database) as session:
        for index, event_id in enumerate(ids):
            session.add(
                BoardSearchShareQueryEventModel(
                    id=event_id,
                    session_id=mine.session.session_id,
                    game_id=game_id,
                    occurred_at=same_time,
                    kind="search" if index < 3 else "approximate_win",
                    request={"cells": [f"{index}:A"], "scope": "all_searchable", "limit": 5}
                    if index < 3
                    else {"startSequenceNumber": 3, "spinCount": 10},
                    result_summary={"resultCount": 1} if index != 2 else {},
                    outcome_code="ok" if index != 2 else "BOARD_SEARCH_QUERY_EMPTY",
                )
            )
        session.add(
            BoardSearchShareQueryEventModel(
                id=uuid4(),
                session_id=other.session.session_id,
                game_id=game_id,
                occurred_at=same_time,
                kind="search",
                request={"cells": ["0:B"], "scope": "all_searchable", "limit": 5},
                result_summary={"resultCount": 0},
                outcome_code="ok",
            )
        )
        session.commit()
        columns = {column.name for column in BoardSearchShareQueryEventModel.__table__.columns}
        assert columns == {
            "id",
            "session_id",
            "game_id",
            "occurred_at",
            "kind",
            "request",
            "result_summary",
            "outcome_code",
        }

    with Session(database) as session:
        service = BoardSearchShareQueryLogService(
            SqlAlchemyBoardSearchShareQueryRepository(session)
        )
        seen: list[UUID] = []
        cursor = None
        while True:
            page = service.list(session_id=mine.session.session_id, before_cursor=cursor, limit=3)
            seen.extend(entry.id for entry in page.entries)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        assert seen == list(reversed(ids))
        replay = service.replay(ids[3])
        # The nearest earlier successful search skips the failed one (id 1002).
        assert replay.search is not None and replay.search.id == ids[1]
        assert replay.approximate_win is not None and replay.approximate_win.id == ids[3]
