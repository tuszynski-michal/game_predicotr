"""D-492: real writer, durable receipts, review boundaries and audit rollback."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import replace
from datetime import UTC, datetime
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.board_search_share_access import BoardSearchShareAccessService
from game_predictor_api.application.board_search_share_corrections import (
    ShareCellCorrectionCommand,
    share_cell_version,
)
from game_predictor_api.application.board_search_share_queries import (
    BoardSearchShareQueryLogService,
)
from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_search_shares import (
    BoardSearchShareAuthenticationError,
    BoardSearchShareConflictError,
    BoardSearchShareNotFoundError,
)
from game_predictor_api.main import create_app
from game_predictor_api.storage.board_search_share_correction_repository import (
    SqlAlchemyBoardSearchShareCorrectionRepository,
)
from game_predictor_api.storage.board_search_share_query_repository import (
    SqlAlchemyBoardSearchShareQueryRepository,
)
from game_predictor_api.storage.board_search_share_repository import (
    SqlAlchemyBoardSearchShareRepository,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemySymbolCellReviewMutationRepository,
)
from game_predictor_api.storage.models import (
    BoardSearchShareQueryEventModel,
    GameModel,
    ImageReviewItemModel,
)
from sqlalchemy import Engine, event, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from test_board_search_share_repository import database as correction_database  # noqa: F401
from test_verified_cell_search_projection import _cells, _seed_pending_board

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Requires the isolated PostgreSQL test database.",
)
NOW = datetime(2099, 9, 30, tzinfo=UTC)
BASE = "/api/v1/board-search-shares"
PROXY = {"X-Board-Search-Share-Proxy": "reviewer-board-search-v1"}


def test_public_write_retry_review_and_rollback(
    correction_database: Engine,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = create_session_factory(correction_database)
    seed = _seed_pending_board(factory, NOW, sibling_positions=(1, 2))
    game_id = seed.game_id
    with factory() as session:
        game = session.get(GameModel, game_id)
        assert game is not None
        game.expected_layout_count = 100_001
        access = BoardSearchShareAccessService(
            SqlAlchemyBoardSearchShareRepository(session),
            readiness=lambda _id: None,
            enabled=True,
            now=lambda: NOW,
        )
        created = access.create(game_id=game_id, lifetime_minutes=60, label="Remote tester")
        unlocked = access.unlock(
            session_id=created.session.session_id, access_code=created.access_code
        )
        context = access.authenticate(unlocked.access_token)
        session.commit()
    sid = context.session_id
    with factory.begin() as session:
        query_id = uuid4()
        session.add(
            BoardSearchShareQueryEventModel(
                id=query_id,
                session_id=sid,
                game_id=game_id,
                kind="search",
                occurred_at=datetime.now(UTC),
                request={"cells": ["0:first"], "scope": "all_searchable", "limit": 100},
                result_summary={},
                outcome_code="ok",
            )
        )
        # A later search in another tab must not steal the first tab's correction.
        session.add(
            BoardSearchShareQueryEventModel(
                id=uuid4(),
                session_id=sid,
                game_id=game_id,
                kind="search",
                occurred_at=datetime.now(UTC),
                request={"cells": ["1:second"], "scope": "all_searchable", "limit": 100},
                result_summary={},
                outcome_code="ok",
            )
        )

    def access_dependency():
        with factory.begin() as session:
            yield BoardSearchShareAccessService(
                SqlAlchemyBoardSearchShareRepository(session),
                readiness=lambda _id: None,
                enabled=True,
                now=lambda: NOW,
            )

    monkeypatch.setattr(
        "game_predictor_api.main.create_database_engine", lambda _settings: correction_database
    )
    app = create_app(
        replace(
            ApiSettings.from_environment({}),
            database_url=correction_database.url.render_as_string(hide_password=False),
            configured_owner_database_url=None,
        ),
        board_search_share_access_service_dependency=access_dependency,
    )
    with game_storage_scope(game_id), factory() as session:
        repo = SqlAlchemyBoardSearchShareCorrectionRepository(session)
        original = repo._cells(game_id, 2)[0]
        command = ShareCellCorrectionCommand(
            uuid4(),
            2,
            0,
            share_cell_version(game_id, 2, original),
            "reassign",
            "second",
            query_id,
            3,
            100_000,
            500,
        )
    payload = {
        "operationId": str(command.operation_id),
        "expectedCellVersion": command.expected_cell_version,
        "action": "reassign",
        "targetSymbolCode": "second",
        "searchContextId": str(query_id),
        "startSequenceNumber": 3,
        "spinCount": 100_000,
        "stakeGrosze": 500,
    }
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("gp_board_search_token", unlocked.access_token)
        response = client.post(f"{BASE}/boards/2/cells/0/decision", json=payload, headers=PROXY)
        assert response.status_code == 200, response.text
        receipt = response.json()
        assert receipt["changed"] is True
        # Simulates a committed write whose response was lost, with fresh dependencies.
        assert (
            client.post(f"{BASE}/boards/2/cells/0/decision", json=payload, headers=PROXY).json()
            == receipt
        )
        assert (
            client.post(
                f"{BASE}/boards/2/cells/0/decision",
                json={**payload, "targetSymbolCode": "first"},
                headers=PROXY,
            ).status_code
            == 409
        )
        assert (
            client.post(
                f"{BASE}/boards/2/cells/15/decision", json=payload, headers=PROXY
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"{BASE}/boards/2/cells/0/decision",
                json={**payload, "gameId": str(uuid4())},
                headers=PROXY,
            ).status_code
            == 422
        )

    # Exact HTTP replay also survives a genuinely new Python/API process.
    assert correction_database.url.database.startswith("game_predictor_task0766_")
    restarted = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import json, os
from fastapi.testclient import TestClient
from game_predictor_api.config import ApiSettings
from game_predictor_api.main import create_app
settings = ApiSettings(host='127.0.0.1', port=8000,
    admin_origin='http://127.0.0.1:3000',
    database_url=os.environ['TEST_CORRECTION_DATABASE_URL'],
    remote_selection_recovery_enabled=False)
with TestClient(create_app(settings), base_url='https://testserver') as client:
    client.cookies.set('gp_board_search_token', os.environ['TEST_CORRECTION_TOKEN'])
    response=client.post('/api/v1/board-search-shares/boards/2/cells/0/decision',
        headers={'X-Board-Search-Share-Proxy':'reviewer-board-search-v1'},
        json=json.loads(os.environ['TEST_CORRECTION_PAYLOAD']))
    assert response.status_code == 200, response.text
    print(json.dumps(response.json()))
""",
        ],
        env={
            **os.environ,
            "TEST_CORRECTION_DATABASE_URL": correction_database.url.render_as_string(
                hide_password=False
            ),
            "TEST_CORRECTION_TOKEN": unlocked.access_token,
            "TEST_CORRECTION_PAYLOAD": json.dumps(payload),
        },
        capture_output=True,
        text=True,
        timeout=35,
        check=True,
    )
    assert json.loads(restarted.stdout) == receipt

    with game_storage_scope(game_id), factory() as session:
        repo = SqlAlchemyBoardSearchShareCorrectionRepository(session)
        assert repo._cells(game_id, 2)[0].assigned_symbol_code == "second"
        page = repo.list_boards(sid, status="pending", before=None, limit=1, pattern=["0:first"])
        assert page.total_count == page.pending_count == 1
        assert page.entries[0].sequence_number == 2 and page.entries[0].stake_grosze == 500
        assert not repo.list_boards(
            sid, status="all", before=None, limit=25, pattern=["1:second"]
        ).entries
        detail = repo.detail(sid, 2, before=None, limit=50)
        assert [(item.before_symbol_code, item.after_symbol_code) for item in detail.changes] == [
            ("first", "second")
        ]
        assert (
            session.scalar(
                select(func.count())
                .select_from(BoardSearchShareQueryEventModel)
                .where(BoardSearchShareQueryEventModel.kind == "symbol_correction")
            )
            == 1
        )
        with pytest.raises(BoardSearchShareConflictError):
            repo.correct(context, unlocked.access_token, replace(command, operation_id=uuid4()))
        with pytest.raises(BoardSearchShareNotFoundError):
            repo.correct(
                context,
                unlocked.access_token,
                replace(command, operation_id=uuid4(), search_context_id=uuid4()),
            )
        with pytest.raises(BoardSearchShareConflictError):
            repo.correct(
                context,
                unlocked.access_token,
                replace(command, operation_id=uuid4(), spin_count=99_999),
            )
        with pytest.raises(BoardSearchShareAuthenticationError):
            repo.correct(context, "x" * 40, command)

    with game_storage_scope(game_id), factory.begin() as session:
        repo = SqlAlchemyBoardSearchShareCorrectionRepository(session)
        reviewed = repo.review(
            sid,
            2,
            expected_revision=detail.board.revision,
            expected_board_version=detail.board_version,
        )
        assert not reviewed.pending
    with game_storage_scope(game_id), factory.begin() as session:
        repo = SqlAlchemyBoardSearchShareCorrectionRepository(session)
        cell = repo._cells(game_id, 2)[0]
        second = replace(
            command,
            operation_id=uuid4(),
            target_symbol_code="first",
            expected_cell_version=share_cell_version(game_id, 2, cell),
        )
        assert repo.correct(context, unlocked.access_token, second).changed
    with game_storage_scope(game_id), factory() as session:
        repo = SqlAlchemyBoardSearchShareCorrectionRepository(session)
        with pytest.raises(BoardSearchShareConflictError):
            repo.review(
                sid,
                2,
                expected_revision=detail.board.revision,
                expected_board_version=detail.board_version,
            )
        current = repo.detail(sid, 2, before=None, limit=50)
        assert current.board.pending and current.board.revision == 2
        assert len(current.changes) == 1  # Only changes since the previous review.

    # Approving 15 cells closes a board; remote reassignment still uses canonical write-through.
    with game_storage_scope(game_id), factory.begin() as session:
        mutator = SymbolCellReviewMutationService(
            SqlAlchemySymbolCellReviewMutationRepository(session)
        )
        for cell in _cells(session, seed.review_item_id):
            mutator.approve(
                game_id=game_id,
                cell_review_id=cell.id,
                expected_revision=cell.revision,
                expected_geometry_revision=cell.geometry_revision,
                expected_crop_sample_id=cell.crop_sample_id,
                expected_crop_checksum_sha256=cell.crop_checksum_sha256,
                actor="owner",
            )
        assert session.get(ImageReviewItemModel, seed.review_item_id).status == "accepted"
    with game_storage_scope(game_id), factory.begin() as session:
        repo = SqlAlchemyBoardSearchShareCorrectionRepository(session)
        cell = repo._cells(game_id, 1)[0]
        approved_command = replace(
            command,
            operation_id=uuid4(),
            sequence_number=1,
            expected_cell_version=share_cell_version(game_id, 1, cell),
            start_sequence_number=1,
            target_symbol_code="second",
        )
        assert repo.correct(context, unlocked.access_token, approved_command).changed

    # Approved confirmation is a durable receipt without new operator work.
    with game_storage_scope(game_id), factory.begin() as session:
        repo = SqlAlchemyBoardSearchShareCorrectionRepository(session)
        cell = repo._cells(game_id, 1)[0]
        unchanged = replace(
            approved_command,
            operation_id=uuid4(),
            action="approve",
            target_symbol_code=None,
            expected_cell_version=share_cell_version(game_id, 1, cell),
        )
        assert not repo.correct(context, unlocked.access_token, unchanged).changed
        assert repo.detail(sid, 1, before=None, limit=50).board.revision == 1

    # A backwards wall clock cannot hide a newer correction behind an acknowledgment.
    with factory.begin() as session:
        model = session.scalar(
            select(BoardSearchShareQueryEventModel).where(
                BoardSearchShareQueryEventModel.kind == "symbol_correction",
                BoardSearchShareQueryEventModel.request["boardRevision"].as_integer() == 2,
                BoardSearchShareQueryEventModel.request["sequenceNumber"].as_integer() == 2,
            )
        )
        assert model is not None
        model.occurred_at = datetime(2000, 1, 1, tzinfo=UTC)
    with game_storage_scope(game_id), factory() as session:
        current = SqlAlchemyBoardSearchShareCorrectionRepository(session).detail(
            sid, 2, before=None, limit=50
        )
        assert current.board.pending and current.board.revision == 2
        assert len(current.changes) == 1

    # Quality actions use the same writer, remain readable and can be repaired.
    for action in ("mark_unreadable", "mark_grid_issue", "reassign"):
        with game_storage_scope(game_id), factory.begin() as session:
            repo = SqlAlchemyBoardSearchShareCorrectionRepository(session)
            cell = repo._cells(game_id, 1)[0]
            quality = replace(
                approved_command,
                operation_id=uuid4(),
                action=action,
                target_symbol_code="first" if action == "reassign" else None,
                expected_cell_version=share_cell_version(game_id, 1, cell),
            )
            assert repo.correct(context, unlocked.access_token, quality).changed
            assert repo.detail(sid, 1, before=None, limit=50).board.pending

    def fail_audit(_mapper, _connection, target):
        if target.kind == "symbol_correction":
            raise SQLAlchemyError("Synthetic audit failure")

    with game_storage_scope(game_id), factory() as session:
        repo = SqlAlchemyBoardSearchShareCorrectionRepository(session)
        before = repo._cells(game_id, 1)[1]
    event.listen(BoardSearchShareQueryEventModel, "before_insert", fail_audit)
    try:
        with (
            pytest.raises(SQLAlchemyError, match="Synthetic audit failure"),
            game_storage_scope(game_id),
            factory.begin() as session,
        ):
            SqlAlchemyBoardSearchShareCorrectionRepository(session).correct(
                context,
                unlocked.access_token,
                replace(
                    approved_command,
                    operation_id=uuid4(),
                    cell_index=1,
                    expected_cell_version=share_cell_version(game_id, 1, before),
                ),
            )
        with TestClient(app, base_url="https://testserver") as client:
            client.cookies.set("gp_board_search_token", unlocked.access_token)
            failed = client.post(
                f"{BASE}/boards/1/cells/1/decision",
                headers=PROXY,
                json={
                    **payload,
                    "operationId": str(uuid4()),
                    "expectedCellVersion": share_cell_version(game_id, 1, before),
                    "startSequenceNumber": 1,
                },
            )
            assert failed.status_code == 503, failed.text
            assert failed.json()["code"] == "BOARD_SEARCH_SHARE_CORRECTION_UNAVAILABLE"
    finally:
        event.remove(BoardSearchShareQueryEventModel, "before_insert", fail_audit)
    with game_storage_scope(game_id), factory() as session:
        repo = SqlAlchemyBoardSearchShareCorrectionRepository(session)
        assert repo._cells(game_id, 1)[1] == before
        first_page = repo.list_boards(sid, status="all", before=None, limit=1, pattern=None)
        assert first_page.total_count == 2 and first_page.next_cursor
        assert (
            len(
                repo.list_boards(
                    sid, status="all", before=first_page.next_cursor, limit=1, pattern=None
                ).entries
            )
            == 1
        )
    with factory() as session:
        service = BoardSearchShareQueryLogService(
            SqlAlchemyBoardSearchShareQueryRepository(session)
        )
        service.delete(query_id, whole_pattern=True)
    with game_storage_scope(game_id), factory() as session:
        assert (
            SqlAlchemyBoardSearchShareCorrectionRepository(session)
            .correct(context, unlocked.access_token, command)
            .changed
        )

    # A writer that authenticated before revoke waits for its row lock,
    # then rechecks the committed revocation instead of writing with old access.
    waiting = Event()

    def waiting_writer():
        with game_storage_scope(game_id), factory.begin() as session:
            session.execute(text("SET LOCAL lock_timeout='3s'"))
            waiting.set()
            return SqlAlchemyBoardSearchShareCorrectionRepository(session).correct(
                context, unlocked.access_token, command
            )

    with ThreadPoolExecutor(max_workers=1) as executor, factory() as session:
        BoardSearchShareAccessService(
            SqlAlchemyBoardSearchShareRepository(session),
            readiness=lambda _id: None,
            enabled=True,
            now=lambda: NOW,
        ).revoke(sid)
        future = executor.submit(waiting_writer)
        assert waiting.wait(timeout=3)
        with pytest.raises(FutureTimeoutError):
            future.result(timeout=0.15)
        session.commit()
        with pytest.raises(BoardSearchShareAuthenticationError):
            future.result(timeout=5)
    with factory() as session:
        repo = SqlAlchemyBoardSearchShareCorrectionRepository(session)
        assert (
            repo.list_boards(sid, status="pending", before=None, limit=25, pattern=None).total_count
            == 2
        )
        with pytest.raises(BoardSearchShareAuthenticationError):
            repo.correct(context, unlocked.access_token, command)
