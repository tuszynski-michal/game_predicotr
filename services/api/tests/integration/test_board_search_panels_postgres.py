"""TASK-0991: fresh PostgreSQL migration, legacy preservation and durable access."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from _recording_capability_fixture import OwnedRecordingCapability
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from game_predictor_api.application.board_search_panels import (
    BoardSearchPanelService,
    panel_child_token,
)
from game_predictor_api.application.board_search_share_access import BoardSearchShareAccessService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_search_shares import BoardSearchShareAuthenticationError
from game_predictor_api.main import create_app
from game_predictor_api.storage.board_search_panels import SqlAlchemyBoardSearchPanelRepository
from game_predictor_api.storage.board_search_share_repository import (
    SqlAlchemyBoardSearchShareRepository,
)
from game_predictor_api.storage.database import GameStorageSession
from game_predictor_api.storage.game_storage_routing import GameStorageRouter
from game_predictor_api.storage.models import BoardSearchShareSessionModel, GameModel
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Isolated PostgreSQL tests are opt-in.",
)
NOW = datetime(2099, 1, 1, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[4]


def test_upgrade_preserves_legacy_and_new_process_authenticates_then_revoke_blocks():
    name = "game_predictor_task0991_" + uuid4().hex[:12] + "_test"
    url = make_url(ApiSettings.from_environment().owner_database_url)
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5},
    )
    engine = create_engine(
        url.set(database=name),
        connect_args={
            "connect_timeout": 5,
            "options": "-c statement_timeout=15000 -c lock_timeout=5000",
        },
    )
    # The upgrade to head crosses 0161, which needs the explicitly owned capability (D-554).
    capability = OwnedRecordingCapability.for_engine(engine)
    with maintenance.connect() as connection:
        capability.create_database(connection)
    try:
        config = Config(str(ROOT / "alembic.ini"))
        test_url = url.set(database=name).render_as_string(hide_password=False)
        config.set_main_option("sqlalchemy.url", test_url.replace("%", "%%"))
        command.upgrade(config, "0154_geometry_correction_revert")
        ids = [uuid4(), uuid4(), uuid4()]
        legacy = uuid4()
        with Session(engine) as session:
            for index, game_id in enumerate(ids):
                session.add(
                    GameModel(
                        id=game_id,
                        code=f"panel-{index}",
                        name=f"Panel {index}",
                        expected_layout_count=50,
                    )
                )
            session.flush()
            session.execute(
                text("""INSERT INTO board_search_share_sessions
                (id,game_id,label,code_salt,code_hash,failed_attempts,created_at,expires_at)
                VALUES (:id,:game,'Legacy',:salt,:hash,0,:now,:expires)"""),
                {
                    "id": legacy,
                    "game": ids[0],
                    "salt": b"a" * 16,
                    "hash": b"b" * 32,
                    "now": NOW,
                    "expires": datetime(2099, 1, 2, tzinfo=UTC),
                },
            )
            session.commit()
        capability.provision(config=config)
        command.upgrade(config, "head")

        class NeverIngress:
            def status(self):
                raise AssertionError("Unready games must not touch the ingress")

        app = create_app(
            ApiSettings(
                host="127.0.0.1",
                port=8000,
                admin_origin="http://127.0.0.1:3000",
                database_url=test_url,
                configured_owner_database_url=test_url,
            ),
            catalog_service_dependency=lambda: object(),
            reviewer_ingress_service_dependency=lambda: NeverIngress(),
        )
        with TestClient(app) as client:
            unready = client.post(
                "/api/v1/admin/board-search-panels", json={"gameIds": [str(ids[0])]}
            )
            assert unready.status_code == 409, unready.text
            assert unready.json()["code"] == "BOARD_SEARCH_PANEL_GAME_NOT_READY"
            assert unready.json()["details"]["gameName"] == "Panel 0"
            assert unready.json()["details"]["reasonCode"] == "GAME_STORAGE_LOCATION_MISSING"
        app.state.database_engine.dispose()
        with GameStorageSession(engine) as session:
            old = session.get(BoardSearchShareSessionModel, legacy)
            assert old is not None and old.panel_id is None and old.code_hash == b"b" * 32
            shares = SqlAlchemyBoardSearchShareRepository(session)
            service = BoardSearchPanelService(
                SqlAlchemyBoardSearchPanelRepository(session),
                shares,
                readiness=lambda _id: None,
                enabled=True,
                now=lambda: NOW,
            )
            created = service.create(game_ids=ids, lifetime_minutes=4320, label="Three games")
            assert GameStorageRouter.bound_game_id(session) is None
            assert shares.count_active_sessions(NOW) == 2
            session.commit()
        # A fresh interpreter and database session use the persisted hash, not an in-memory service.
        child = created.panel.games[0]
        token = panel_child_token(created.link_key, created.panel.panel_id, child.session_id)
        env = {
            **os.environ,
            "TASK0991_TEST_URL": test_url,
            "TASK0991_TOKEN": token,
            "TASK0991_GAME": str(child.game_id),
            "TASK0991_MEMBERS": json.dumps(
                [
                    {
                        "game": str(member.game_id),
                        "token": panel_child_token(
                            created.link_key, created.panel.panel_id, member.session_id
                        ),
                    }
                    for member in created.panel.games
                ]
            ),
        }
        code = """import os, json
from uuid import UUID
from sqlalchemy import create_engine
from game_predictor_api.application.board_search_share_access import BoardSearchShareAccessService
from game_predictor_api.storage.board_search_share_repository import (
    SqlAlchemyBoardSearchShareRepository,
)
from game_predictor_api.storage.database import GameStorageSession
engine=create_engine(os.environ['TASK0991_TEST_URL'],connect_args={'connect_timeout':5})
with GameStorageSession(engine) as session:
    service=BoardSearchShareAccessService(
        SqlAlchemyBoardSearchShareRepository(session),readiness=lambda _:None,enabled=True
    )
    members=json.loads(os.environ['TASK0991_MEMBERS'])
    assert len(members)==3
    for member in members:
        actual=service.authenticate(member['token']).game_id
        assert actual==UUID(member['game'])
engine.dispose()
print('fresh-process-auth PASS')
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=ROOT,
        )
        assert result.returncode == 0, result.stderr
        assert "fresh-process-auth PASS" in result.stdout
        with GameStorageSession(engine) as session:
            shares = SqlAlchemyBoardSearchShareRepository(session)
            service = BoardSearchPanelService(
                SqlAlchemyBoardSearchPanelRepository(session),
                shares,
                readiness=lambda _id: None,
                enabled=True,
                now=lambda: NOW,
            )
            assert (
                service.authenticate(created.panel.panel_id, created.link_key).games
                == created.panel.games
            )
            service.revoke(created.panel.panel_id)
            session.commit()
        with Session(engine) as session:
            access = BoardSearchShareAccessService(
                SqlAlchemyBoardSearchShareRepository(session),
                readiness=lambda _id: None,
                enabled=True,
                now=lambda: NOW,
            )
            with pytest.raises(BoardSearchShareAuthenticationError):
                access.authenticate(token)
            assert (
                len(
                    tuple(
                        session.scalars(
                            select(BoardSearchShareSessionModel).where(
                                BoardSearchShareSessionModel.panel_id == created.panel.panel_id
                            )
                        )
                    )
                )
                == 3
            )
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            connection.execute(text("SET statement_timeout='10s'"))
            capability.drop_database(connection)
        maintenance.dispose()
