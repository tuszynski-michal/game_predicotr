"""Actual additive Alembic/RLS/append-only/CAS/replay and a cold reader; no operator DB."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.domain.grid_cell_content import ContentError
from game_predictor_api.domain.grid_visibility_contract import CellContentReference
from game_predictor_api.schemas.grid_cell_content import ContentWriteCommand
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_cell_content import SqlAlchemyGridCellContentRepository
from game_predictor_api.storage.models import SymbolModel
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_grid_training_cohort_e2e_postgres import _install_base, _nodes, _save_source

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit task-owned disposable PostgreSQL only",
)


def test_content_revision_replays_after_restart_and_is_independent_retained_rls_history(tmp_path):
    with application_role_database("t1165", ("content-a", "content-b")) as db:
        print("T1165 disposable database migrated", flush=True)
        game, other = db.games.values()
        _install_base(db, game)
        with Session(db.owner_engine) as session, session.begin():
            session.add(
                SymbolModel(
                    game_id=game,
                    code="FIXTURE",
                    name="Fixture",
                    mobile_code=1,
                    display_order=1,
                    status="active",
                )
            )
        source_id, _, import_id = _save_source(db, tmp_path, game, 1, 1, {})
        print("T1165 guarded source ready", flush=True)
        factory = create_session_factory(db.app_engine)
        with game_storage_scope(game), factory() as session:
            repo = SqlAlchemyGridCellContentRepository(session, tmp_path)
            repo.bind(game)
            source = repo.current_source(game, source_id)
        cells = []
        nodes = _nodes(0)
        for index in range(15):
            row, col = divmod(index, 5)
            p = nodes[row * 6 + col]
            cells.append(
                CellContentReference(
                    state="visible",
                    quad=(
                        (p.x + 5, p.y + 5),
                        (p.x + 25, p.y + 5),
                        (p.x + 25, p.y + 25),
                        (p.x + 5, p.y + 25),
                    ),
                )
            )
        body = ContentWriteCommand(
            idempotencyKey=uuid4(),
            sourceId=source_id,
            expectedSourceSha256=source.sourceSha256,
            expectedPixelSha256=source.sourceRepresentativeSha256,
            positionIndex=0,
            sequenceNumber=110,
            expectedRevision=0,
            cells=tuple(cells),
            humanApproval=True,
        )
        with game_storage_scope(game), factory.begin() as session:
            first = SqlAlchemyGridCellContentRepository(session, tmp_path).write(
                game, body, "local-owner"
            )
        with game_storage_scope(game), factory.begin() as session:
            replay = SqlAlchemyGridCellContentRepository(session, tmp_path).write(
                game, body, "local-owner"
            )
            assert replay == first
        print("T1165 write and replay committed", flush=True)
        from game_predictor_api.storage.grid_content_sampling import ContentSamplingPreparationError
        from game_predictor_api.storage.grid_correction_split import prepare_split
        from game_predictor_api.storage.grid_training_cohort_repository import (
            CohortDeadline,
            SqlAlchemyGridTrainingCohortRepository,
        )

        with game_storage_scope(game), factory() as session:
            split_repo = SqlAlchemyGridTrainingCohortRepository(session, tmp_path)
            split_repo.bind(game)
            with pytest.raises(ContentSamplingPreparationError) as shortage:
                prepare_split(
                    split_repo,
                    game,
                    [str(import_id)],
                    CohortDeadline(),
                    policy="application-grid-corrections-v4",
                    mode="grid-only",
                    content_sampling={
                        "policy": "full-symbol-content-sampling-v1",
                        "ancestrySha256": None,
                        "ancestorGroups": [],
                    },
                )
            assert shortage.value.report["state"] == "not_evaluable"
            assert shortage.value.report["missingFullPhotos"] == 5
            assert shortage.value.report["reasonCounts"]["CONTENT_REG_ANCESTRY_UNRESOLVED"] > 0
        with (
            pytest.raises(ContentError, match="different command"),
            game_storage_scope(game),
            factory.begin() as session,
        ):
            SqlAlchemyGridCellContentRepository(session, tmp_path).write(
                game, body.model_copy(update={"humanApproval": False}), "local-owner"
            )
        with (
            pytest.raises(ContentError, match="newer independent"),
            game_storage_scope(game),
            factory.begin() as session,
        ):
            SqlAlchemyGridCellContentRepository(session, tmp_path).write(
                game, body.model_copy(update={"idempotencyKey": uuid4()}), "local-owner"
            )
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("_grid_content_cold_reader.py"))],
            env=db.subprocess_environment(
                CONTENT_TEST_DATABASE_URL=db.app_url.render_as_string(hide_password=False),
                CONTENT_TEST_GAME=str(game),
                CONTENT_TEST_SOURCE=str(source_id),
                CONTENT_TEST_ROOT=str(tmp_path),
                CONTENT_TEST_REFERENCE_SHA=first["contentReferenceSha256"],
            ),
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "COLD_CONTENT_READ_PASS" in result.stdout
        for query in (
            "UPDATE grid_cell_content_revisions "
            "SET document=document || jsonb_build_object('changed',true)",
            "DELETE FROM grid_cell_content_revisions",
            "UPDATE grid_cell_content_commands SET document='{}'::jsonb",
        ):
            with (
                pytest.raises(DBAPIError, match="CONTENT_IMMUTABLE_HISTORY"),
                game_storage_scope(game),
                factory.begin() as session,
            ):
                SqlAlchemyGridCellContentRepository(session, tmp_path).bind(game, write=True)
                session.execute(text(query))
        with game_storage_scope(other), factory() as session:
            SqlAlchemyGridCellContentRepository(session, tmp_path).bind(other)
            assert session.scalar(text("SELECT count(*) FROM grid_cell_content_revisions")) == 0
        with game_storage_scope(game), factory() as session:
            repo = SqlAlchemyGridCellContentRepository(session, tmp_path)
            repo.bind(game)
            assert session.scalar(text("SELECT count(*) FROM grid_cell_content_revisions")) == 1
            assert repo.get(game, source_id, 0) == {
                k: v for k, v in first.items() if k != "idempotencyKey"
            }
        with db.owner_engine.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM public.recording_photo_uses WHERE game_id=:g"),
                    {"g": game},
                )
                == 0
            )
        print(
            "T1165 RLS, immutable history and cold-process read passed; owned cleanup follows",
            flush=True,
        )
