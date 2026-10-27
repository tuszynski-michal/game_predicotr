"""Actual PostgreSQL parity/migration checks in an owned disposable *_test database."""

import importlib
import os
from uuid import uuid4

import pytest
from game_predictor_api.domain.board_search import (
    BoardSearchCandidate,
    BoardSearchQueryCell,
    BoardSearchScope,
)
from game_predictor_api.domain.board_search_sequence import (
    BoardSearchSequenceError,
    rank_board_search_sequences,
)
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.board_search_sequence import _rank_with_timeout
from game_predictor_api.storage.database import GameStorageSession
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.models import (
    GameModel,
    ImageBoardSearchFastDocumentModel,
    SymbolModel,
)
from game_predictor_api.storage.schema_readiness import require_alembic_head
from sqlalchemy import text, update
from sqlalchemy.orm import Session
from test_board_search_approximate_win_repository import (
    _import_job,
    _provision_v2_storage_location,
    _resolved_review_item,
    _source,
)
from test_board_search_share_repository import database as _database_fixture

database = _database_fixture

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Opt in to isolated PostgreSQL tests.",
)


def test_migrated_database_passes_startup_readiness(database):
    assert database.url.database.endswith("_test")
    require_alembic_head(database)


@pytest.fixture(scope="module")
def seeded(database):
    assert database.url.database.endswith("_test")
    game_id = uuid4()
    documents = []
    with Session(database) as session, session.begin():
        session.add(
            GameModel(
                id=game_id,
                code="sequence-" + game_id.hex[:8],
                name="Sequence test",
                expected_layout_count=8,
            )
        )
        session.flush()
        _provision_v2_storage_location(session, game_id=game_id)
        for index, code in enumerate(("A", "B", "C"), 1):
            session.add(
                SymbolModel(
                    game_id=game_id,
                    code=code,
                    name=code,
                    mobile_code=index,
                    is_wildcard=False,
                    display_order=index,
                    status="active",
                )
            )
        session.flush()
        job = _import_job(session, game_id=game_id)
        source = _source(session, job=job, relative_path="sequence_1-8.jpg")
        for position, code in [(1, "A"), (2, "B"), (3, "C"), (5, "A"), (6, None), (8, "A")]:
            item = _resolved_review_item(
                session,
                game_id=game_id,
                job=job,
                source=source,
                position=position - 1,
                sequence_number=position,
                symbol_codes=(code,) * 15,
            )
            documents.append(
                BoardSearchCandidate(item.id, position, "accepted", (code,) * 15, ((),) * 15)
            )
        SqlAlchemyBoardSearchProjectionRepository(session).rebuild_game(game_id)
    return game_id, documents


@pytest.mark.parametrize(
    "patterns",
    [
        (("A",), ("B",)),
        (("A",), ("A",)),
        (("A",), ("B", "C")),
        (("A",), ("B",), ("C",)),
        (("A",), ("B",), ("C",), ("A",)),
    ],
)
def test_sql_matches_pure_ranking_including_wrap_and_gaps(database, seeded, patterns):
    game_id, documents = seeded
    queries = tuple(
        tuple(BoardSearchQueryCell(i, code) for i, code in enumerate(codes)) for codes in patterns
    )
    expected = rank_board_search_sequences(
        queries, documents, sequence_length=8, scope=BoardSearchScope.ALL_SEARCHABLE
    )
    with GameStorageSession(database) as session:
        actual = SqlAlchemyBoardSearchProjectionRepository(session).search_sequence(
            game_id=game_id, patterns=queries, scope=BoardSearchScope.ALL_SEARCHABLE, limit=100
        )
        assert [(item.start_sequence_number, item.score) for item in actual] == [
            (item.boards[0].sequence_number, item.score) for item in expected
        ]
        assert all(
            tuple(board.sequence_number for board in a.boards)
            == tuple(board.sequence_number for board in e.boards)
            for a, e in zip(actual, expected, strict=True)
        )
        assert [tuple(board.score for board in item.boards) for item in actual] == [
            item.scores for item in expected
        ]


@pytest.mark.parametrize("wildcard", [False, True])
@pytest.mark.parametrize("scope", list(BoardSearchScope))
@pytest.mark.parametrize("count,limit", [(2, 1), (2, 40), (3, 100), (4, 40)])
@pytest.mark.parametrize("evidence_kind", ["mixed", "unknown", "alternatives_only"])
def test_materialized_ranking_preserves_all_evidence_and_ties(
    database, seeded, wildcard, scope, count, limit, evidence_kind
):
    game_id, original = seeded
    codes = {"A": 1, "B": 2, "C": 3}
    # Exercise each alternative rank, exact matches, mismatches and unknowns;
    # duplicate alternatives must count only their first matching rank.
    primary = ("A", "A", "A", "A", "B", "C", None) + (None,) * 8
    alternatives = (("B",), ("C", "B"), ("C", "A", "B"), ("C", "A", "C", "B"), ("B",), (), ()) + (
        (),
    ) * 8
    if evidence_kind != "mixed":
        primary = (None,) * 15
        if evidence_kind == "unknown":
            alternatives = ((),) * 15
    patterns = tuple(
        tuple(BoardSearchQueryCell(i, "B" if index % 2 == 0 else "A") for i in range(size))
        for index, size in enumerate((15, 7, 3, 11)[:count])
    )
    documents = []
    with GameStorageSession(database) as session, session.begin():
        GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)
        if wildcard:
            session.execute(update(GameModel).where(GameModel.id == game_id).values(code="777a2"))
        for index, board in enumerate(original):
            status = ("pending", "accepted", "corrected")[index % 3]
            # Repeat the same evidence to produce ties resolved by approval and position.
            candidate = BoardSearchCandidate(
                board.review_item_id, board.sequence_number, status, primary, alternatives
            )
            documents.append(candidate)
            session.execute(
                update(ImageBoardSearchFastDocumentModel)
                .where(
                    ImageBoardSearchFastDocumentModel.game_id == game_id,
                    ImageBoardSearchFastDocumentModel.sequence_number == board.sequence_number,
                )
                .values(
                    status=status,
                    primary_symbol_mobile_codes=[codes.get(code) for code in primary],
                    known_evidence_positions=[
                        str(cell)
                        for cell in range(15)
                        if primary[cell] is not None or (status == "pending" and alternatives[cell])
                    ],
                    **{
                        f"alternative_rank_{rank + 1}_mobile_codes": [
                            codes.get(values[rank]) if len(values) > rank else None
                            for values in alternatives
                        ]
                        for rank in range(4)
                    },
                )
            )
        expected = rank_board_search_sequences(
            patterns, documents, sequence_length=8, scope=scope, unknown_matches_all=wildcard
        )[:limit]
        actual = SqlAlchemyBoardSearchProjectionRepository(session).search_sequence(
            game_id=game_id, patterns=patterns, scope=scope, limit=limit
        )
        assert [item.start_sequence_number for item in actual] == [
            item.boards[0].sequence_number for item in expected
        ]
        for found, reference in zip(actual, expected, strict=True):
            assert found.score == reference.score
            assert tuple(board.score for board in found.boards) == reference.scores
            assert tuple(
                (board.review_item_id, board.status, board.sequence_number)
                for board in found.boards
            ) == tuple(
                (board.review_item_id, board.status, board.sequence_number)
                for board in reference.boards
            )
        # Roll back fixture mutations so each parameter set starts with the same projection.
        session.rollback()


def test_timeout_rolls_back_savepoint_and_preserves_lower_limit(database):
    with Session(database) as session:
        session.execute(text("SET LOCAL jit='on'"))
        session.execute(text("SET LOCAL statement_timeout='5ms'"))
        with pytest.raises(BoardSearchSequenceError) as caught:
            _rank_with_timeout(session, text("SELECT pg_sleep(0.05)"))
        assert caught.value.code == "BOARD_SEARCH_SEQUENCE_TIMEOUT"
        assert session.execute(text("SELECT 1")).scalar_one() == 1
        assert session.execute(text("SHOW statement_timeout")).scalar_one() == "5ms"
        assert session.execute(text("SHOW jit")).scalar_one() == "on"
        assert _rank_with_timeout(session, text("SELECT 42 AS answer"))[0]["answer"] == 42
        assert session.execute(text("SHOW statement_timeout")).scalar_one() == "5ms"
        assert session.execute(text("SHOW jit")).scalar_one() == "on"


@pytest.mark.parametrize("jit", ["on", "off"])
def test_ranking_disables_jit_only_inside_savepoint(database, jit):
    with Session(database) as session:
        session.execute(text("SELECT set_config('jit', :jit, true)"), {"jit": jit})
        rows = _rank_with_timeout(session, text("SELECT current_setting('jit') AS jit"))
        assert rows == [{"jit": "off"}]
        assert session.execute(text("SHOW jit")).scalar_one() == jit


def test_log_constraint_upgrade_and_guarded_downgrade(database, seeded, monkeypatch):
    migration = importlib.import_module(
        "services.api.alembic.versions.0169_board_search_sequence_logs"
    )
    # The migration owns no data. Exercise its real DDL using a rolled-back test transaction.
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with database.connect() as connection:
        transaction = connection.begin()
        try:
            monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
            migration.downgrade()
            constraint = connection.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conname='ck_bss_query_request'"
                )
            ).scalar_one()
            assert "4096" in constraint
            migration.upgrade()
            constraint = connection.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conname='ck_bss_query_request'"
                )
            ).scalar_one()
            assert "32768" in constraint
            from game_predictor_api.storage.models import BoardSearchShareQueryEventModel
            from test_board_search_share_repository import _service

            with Session(connection) as session:
                created = _service(session).create(
                    game_id=seeded[0], lifetime_minutes=60, label="Sequence migration test"
                )
                cells = [f"{i}:" + "🌟" * 64 for i in range(15)]
                snapshot = {
                    "version": 2,
                    "patterns": [{"cells": cells}] * 4,
                    "scope": "all_searchable",
                    "limit": 15,
                }
                entry = BoardSearchShareQueryEventModel(
                    session_id=created.session.session_id,
                    game_id=seeded[0],
                    kind="symbol_correction",
                    request={"searchSnapshot": snapshot, "operationId": str(uuid4())},
                    result_summary={},
                    outcome_code="ok",
                )
                session.add(entry)
                session.flush()
                size = connection.execute(
                    text(
                        "SELECT octet_length(request::text) "
                        "FROM public.board_search_share_query_events "
                        "WHERE id=:id"
                    ),
                    {"id": entry.id},
                ).scalar_one()
                assert 4096 < size <= 32768
                with pytest.raises(RuntimeError, match="larger than 4096"):
                    migration.downgrade()
                assert (
                    connection.execute(
                        text(
                            "SELECT count(*) FROM public.board_search_share_query_events "
                            "WHERE id=:id"
                        ),
                        {"id": entry.id},
                    ).scalar_one()
                    == 1
                )
        finally:
            transaction.rollback()


def test_correction_filter_uses_full_event_pattern_and_same_session(database, seeded):
    from game_predictor_api.application.board_search_share_corrections import (
        BoardSearchShareCorrectionService,
    )
    from game_predictor_api.domain.board_search_pattern_identity import search_pattern_fingerprint
    from game_predictor_api.domain.board_search_share_queries import sequence_search_query_request
    from game_predictor_api.domain.board_search_shares import BoardSearchShareError
    from game_predictor_api.storage.board_search_share_correction_repository import (
        SqlAlchemyBoardSearchShareCorrectionRepository,
    )
    from game_predictor_api.storage.models import BoardSearchShareQueryEventModel
    from test_board_search_share_repository import _service

    with Session(database) as session, session.begin():
        mine = _service(session).create(game_id=seeded[0], lifetime_minutes=60, label="Filter test")
        other = _service(session).create(
            game_id=seeded[0], lifetime_minutes=60, label="Other filter"
        )
        events = []
        for position, codes in enumerate([("A", "B"), ("B", "A")], 1):
            request = sequence_search_query_request(
                patterns=[[(0, code)] for code in codes], scope="all_searchable", limit=15
            )
            event = BoardSearchShareQueryEventModel(
                session_id=mine.session.session_id,
                game_id=seeded[0],
                kind="search",
                request=request,
                result_summary={},
                outcome_code="ok",
            )
            session.add(event)
            session.flush()
            events.append(event)
            session.add(
                BoardSearchShareQueryEventModel(
                    session_id=mine.session.session_id,
                    game_id=seeded[0],
                    kind="symbol_correction",
                    outcome_code="ok",
                    request={
                        "sequenceNumber": position,
                        "boardRevision": 1,
                        "cellIndex": 0,
                        "searchSnapshot": request,
                        "patternFingerprint": search_pattern_fingerprint(request),
                        "startSequenceNumber": position,
                    },
                    result_summary={"changed": True},
                )
            )
        session.flush()
        service = BoardSearchShareCorrectionService(
            SqlAlchemyBoardSearchShareCorrectionRepository(session)
        )
        page = service.list_boards(
            mine.session.session_id, status="all", search_event_id=events[0].id
        )
        assert [item.sequence_number for item in page.entries] == [1]
        assert page.entries[0].pattern_count == 2
        with pytest.raises(BoardSearchShareError):
            service.list_boards(other.session.session_id, search_event_id=events[0].id)
        with pytest.raises(BoardSearchShareError, match="not both"):
            service.list_boards(
                mine.session.session_id, pattern=["0:A"], search_event_id=events[0].id
            )
