"""Actual promotion SELECT and row locks on a guarded disposable PostgreSQL DB."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from _application_role_database import (
    application_role_database as guarded_application_role_database,
)
from game_predictor_api.domain.board_search import (
    BoardSearchCandidate,
    BoardSearchProjectionPayload,
)
from game_predictor_api.domain.protected_control_truth import ControlTruth, compare_control_truth
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.models import ImageReviewItemModel, ImageSymbolReviewCellModel
from game_predictor_api.storage.protected_control_truth import (
    _CURRENT_QUERY,
    current_control_decisions,
)
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_image_geometry_completeness_repository import _Builder, _import_job

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit guarded disposable PostgreSQL test only.",
)


def test_actual_current_owner_select_locks_pending_control_and_returns_no_conflict(
    tmp_path: Path,
) -> None:
    with guarded_application_role_database("t0883truth", ("truth-guard",)) as database:
        assert database.owner_url.database.endswith("_test")
        assert database.owner_url.database != "game_predictor"
        assert database.app_url.database == database.owner_url.database
        game_id = database.games["truth-guard"]
        with Session(database.owner_engine) as session, session.begin():
            GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)
            build = _Builder(session, game_id)
            job = _import_job(session, game_id=game_id)
            source = build.source(job, "truth-fixture.jpg")
            geometry = build.revision(source, revision=0, range_start=101, slots=1)
            board = build.board(source, geometry, 0)
            build.cells(board, geometry, job, specs=[(0.5, "pending", True)])
            item = session.scalars(
                select(ImageReviewItemModel).where(
                    ImageReviewItemModel.recognized_board_id == board.id
                )
            ).one()
            projection = SqlAlchemyBoardSearchProjectionRepository(session)
            projection.upsert_candidate(
                BoardSearchProjectionPayload(
                    game_id=game_id,
                    import_job_id=job.id,
                    recognized_board_id=board.id,
                    candidate=BoardSearchCandidate(
                        review_item_id=item.id,
                        sequence_number=101,
                        status="pending",
                        primary_symbol_codes=(None,) * 15,
                        alternative_symbol_codes=((),) * 15,
                    ),
                    board_checksum_sha256="a" * 64,
                    board_confidence=0.5,
                    sequence_confidence=1.0,
                    source_pixel_count=1080 * 652,
                )
            )
            projection.reconcile_sequence(game_id, 101)
            cell = session.scalars(
                select(ImageSymbolReviewCellModel).where(
                    ImageSymbolReviewCellModel.recognized_board_id == board.id
                )
            ).one()
            cell_id, original_revision = cell.id, cell.revision
            truth = ControlTruth(
                "a" * 64,
                source.checksum_sha256,
                source.normalized_pixel_checksum_sha256,
                1080,
                652,
                0,
                0,
                ((1.0, 20.0), (9.0, 20.0), (9.0, 60.0), (1.0, 60.0)),
                cell.rendered_pixel_checksum_sha256,
                str(uuid4()),
                "10",
                "lab_human_approved",
                "e" * 64,
                "f" * 64,
            )

        with Session(database.app_engine) as reader, reader.begin():
            GameStorageRouter().bind(reader, game_id, intent=GameStorageIntent.READ)
            identity = reader.execute(text("SELECT current_database(), current_user")).one()
            assert identity == (database.app_url.database, database.role)
            reader.execute(text("SET LOCAL statement_timeout = '5s'"))
            unrelated = replace(truth, source_byte_sha256="0" * 64, source_pixel_sha256="0" * 64)
            assert (
                current_control_decisions(reader, tmp_path, game_id, (unrelated,), lock=True) == ()
            )
            rows = (
                reader.execute(
                    text(_CURRENT_QUERY + " FOR SHARE OF c, rb, src, sgr, d"),
                    {
                        "game_id": game_id,
                        "byte_checksums": [truth.source_byte_sha256],
                        "pixel_checksums": [truth.source_pixel_sha256],
                    },
                )
                .mappings()
                .all()
            )
            assert len(rows) == 1
            assert rows[0]["id"] == cell_id
            assert rows[0]["review_state"] == "pending"
            assert rows[0]["assigned_symbol_code"] is None  # Catalog LEFT JOIN retains pending.
            decisions = current_control_decisions(reader, tmp_path, game_id, (truth,), lock=True)
            report = compare_control_truth((truth,), decisions)
            assert report["status"] == "NO_CONFLICT" and report["comparisons"] == 0

            # Separate real LOGIN connection cannot revise even a pending
            # control while promotion owns FOR SHARE. The timeout is bounded.
            with Session(database.app_engine) as writer:
                with pytest.raises(DBAPIError) as error, writer.begin():
                    GameStorageRouter().bind(writer, game_id, intent=GameStorageIntent.WRITE)
                    writer.execute(text("SET LOCAL lock_timeout = '250ms'"))
                    writer.execute(text("SET LOCAL statement_timeout = '2s'"))
                    writer.execute(
                        text(
                            "UPDATE image_symbol_review_cells SET revision = revision + 1 "
                            "WHERE game_id = :game AND id = :cell"
                        ),
                        {"game": game_id, "cell": cell_id},
                    )
                assert error.value.orig.sqlstate == "55P03"

        # Promotion transaction closed: the same update succeeds, proving that
        # the earlier timeout was the actual control-row lock.
        with Session(database.app_engine) as writer, writer.begin():
            GameStorageRouter().bind(writer, game_id, intent=GameStorageIntent.WRITE)
            writer.execute(text("SET LOCAL lock_timeout = '1s'"))
            revision = writer.execute(
                text(
                    "UPDATE image_symbol_review_cells SET revision = revision + 1 "
                    "WHERE game_id = :game AND id = :cell RETURNING revision"
                ),
                {"game": game_id, "cell": cell_id},
            ).scalar_one()
            assert revision == original_revision + 1

    # Verify teardown through a new maintenance connection, never the operator
    # database. Only the exact disposable database/role names are inspected.
    maintenance = create_engine(
        database.owner_url.set(database="postgres"),
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=5000"},
    )
    try:
        with maintenance.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM pg_database WHERE datname = :name"),
                    {"name": database.owner_url.database},
                ).scalar_one()
                == 0
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM pg_roles WHERE rolname = :role"),
                    {"role": database.role},
                ).scalar_one()
                == 0
            )
    finally:
        maintenance.dispose()
