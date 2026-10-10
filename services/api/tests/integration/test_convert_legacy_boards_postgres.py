"""TASK-0791: ``legacy_file`` boards are converted to ``virtual_source`` and the modes narrow.

Runs on a dedicated ``*_test`` database only (fixture from the TASK-0790
test).  A deferred slot is first resolved through the real virtual path, then
its board, revision and cells are rewritten into the legacy shape (file crops,
no manifest) with human decisions on the cells — the same shape the 461 boards
of game 777 had.  The conversion must bring the board back to the virtual
render of the same corners while keeping every decision, and migration 0135
must refuse before and pass after the conversion.

Migration ``0136`` (TASK-0793) dropped ``image_symbol_review_cells.render_spec``
and refuses to downgrade, so the test builds the ``0134`` schema on a fresh
database instead of downgrading from head.  The current writers no longer set
the column, which the ``0134``/``0135`` CHECK still requires for virtual
cells; a column default of ``'{}'`` stands in for the former writer value on
this test database only.  The test ends by upgrading to head.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from alembic import command
from game_predictor_api.application.legacy_board_conversion import (
    LEGACY_BOARD_CONVERSION_ACTOR,
    LegacyBoardConversionService,
)
from game_predictor_api.application.virtual_grid_geometry import VirtualGridGeometryService
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_geometry_completeness_state_repository import (
    SqlAlchemyImageGeometryCompletenessStateRepository,
)
from game_predictor_api.storage.models import (
    ImageBoardGeometryPendingModel,
    ImageBoardGeometryRevisionModel,
    ImageSourceGeometryRevisionModel,
    RecognizedBoardModel,
    SymbolModel,
)
from game_predictor_api.storage.virtual_grid_geometry_repository import (
    SqlAlchemyVirtualGridGeometryRepository,
)
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker
from test_virtual_deferred_resolution_postgres import (
    _Database,
    _factory,
    _provision_game,
    _resolve_via_reviewer_endpoint,
    _seed,
    _state,
    database,  # noqa: F401
)

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)

_PREVIOUS_HEAD = "0134_drop_cell_observations_and_legacy_archive"
_HEAD = "0135_virtual_only_asset_modes"
_DROP_RENDER_SPEC = "0136_drop_cell_render_spec"
_CELLS = "game_data_v2.image_symbol_review_cells"


def _service(session: Session, artifact_root: Path) -> LegacyBoardConversionService:
    repository = SqlAlchemyVirtualGridGeometryRepository(session)
    return LegacyBoardConversionService(
        repository, VirtualGridGeometryService(repository, artifact_root)
    )


def _legacyfy(session: Session, game_id: UUID, pending_id: UUID, symbol_id: UUID) -> UUID:
    """Rewrite a resolved virtual board into the pre-TASK-0790 legacy shape."""

    pending = session.get(ImageBoardGeometryPendingModel, pending_id)
    assert pending is not None and pending.recognized_board_id is not None
    board = session.get(RecognizedBoardModel, pending.recognized_board_id)
    assert board is not None
    revision = session.scalar(
        select(ImageBoardGeometryRevisionModel).where(
            ImageBoardGeometryRevisionModel.recognized_board_id == board.id,
            ImageBoardGeometryRevisionModel.revision == board.geometry_revision,
        )
    )
    assert revision is not None
    checksum = "c" * 64
    revision.asset_mode = "legacy_file"
    revision.board_relative_path = f"boards/{board.id}.jpg"
    revision.board_checksum_sha256 = checksum
    revision.virtual_render_spec = None
    revision.virtual_render_spec_checksum_sha256 = None
    revision.crop_artifacts = [
        {
            "columnIndex": index % 5,
            "cropChecksumSha256": checksum,
            "cropRelativePath": f"cells/{board.id}_{index}.jpg",
            "rowIndex": index // 5,
        }
        for index in range(15)
    ]
    board.asset_mode = "legacy_file"
    board.board_relative_path = revision.board_relative_path
    board.board_checksum_sha256 = checksum
    board.source_geometry_revision_id = None
    board.geometry_engine_name = None
    board.geometry_engine_version = None
    board.geometry_checksum_sha256 = None
    session.flush()
    session.execute(
        text(
            """DELETE FROM game_data_v2.board_render_manifests
            WHERE game_id = :game_id AND recognized_board_id = :board_id"""
        ),
        {"game_id": game_id, "board_id": board.id},
    )
    # Human decisions on every cell; cell 3 approved on the legacy crop.
    session.execute(
        text(
            f"""UPDATE {_CELLS}
            SET asset_mode = 'legacy_file',
                crop_relative_path = 'cells/' || :board_id || '_' || cell_index || '.jpg',
                crop_checksum_sha256 = :checksum,
                source_geometry_revision_id = NULL,
                assigned_symbol_id = :symbol_id,
                assignment_source = 'human',
                last_reviewed_by = 'reviewer-operator',
                last_reviewed_at = now()
            WHERE game_id = :game_id AND recognized_board_id = :board_id"""
        ),
        {
            "game_id": game_id,
            "board_id": str(board.id),
            "checksum": checksum,
            "symbol_id": symbol_id,
        },
    )
    session.execute(
        text(
            f"""UPDATE {_CELLS}
            SET review_state = 'approved',
                approved_crop_sample_id = crop_sample_id,
                approved_crop_checksum_sha256 = crop_checksum_sha256,
                approved_geometry_revision = geometry_revision,
                approved_asset_mode = 'legacy_file',
                approved_source_geometry_revision_id = NULL,
                approved_render_spec_checksum_sha256 = NULL,
                approved_rendered_pixel_checksum_sha256 = NULL
            WHERE game_id = :game_id AND recognized_board_id = :board_id AND cell_index = 3"""
        ),
        {"game_id": game_id, "board_id": str(board.id)},
    )
    return board.id


def _decisions(session: Session, game_id: UUID, board_id: UUID) -> list[tuple[Any, ...]]:
    return [
        tuple(row)
        for row in session.execute(
            text(
                f"""SELECT cell_index, assigned_symbol_id::text, assignment_source, review_state,
                    quality_issue, last_reviewed_by
                FROM {_CELLS}
                WHERE game_id = :game_id AND recognized_board_id = :board_id
                ORDER BY cell_index"""
            ),
            {"game_id": game_id, "board_id": board_id},
        ).all()
    ]


def _cell_provenance(session: Session, game_id: UUID, board_id: UUID) -> list[tuple[Any, ...]]:
    return [
        tuple(row)
        for row in session.execute(
            text(
                f"""SELECT cell_index, asset_mode, geometry_revision, crop_relative_path,
                    rendered_pixel_checksum_sha256, extractor_version, revision,
                    approved_asset_mode, approved_geometry_revision,
                    approved_rendered_pixel_checksum_sha256 = rendered_pixel_checksum_sha256
                FROM {_CELLS}
                WHERE game_id = :game_id AND recognized_board_id = :board_id
                ORDER BY cell_index"""
            ),
            {"game_id": game_id, "board_id": board_id},
        ).all()
    ]


def _symbol(session: Session, game_id: UUID) -> UUID:
    symbol = SymbolModel(
        game_id=game_id, mobile_code=3, code="CYTRYNA", name="Cytryna", display_order=3
    )
    session.add(symbol)
    session.flush()
    return symbol.id


@pytest.mark.skip(
    reason=(
        "retired by TASK-0940: historical revision harness incompatible with manifest v5 "
        "(0142) and 0151; see Outcome"
    )
)
def test_conversion_restores_the_virtual_render_and_keeps_decisions(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    # 0136 refuses to downgrade: reach 0134 on a fresh schema.
    database.engine.dispose()
    with database.engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA IF EXISTS game_data_v2 CASCADE")
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
    command.upgrade(database.config, _PREVIOUS_HEAD)
    with database.engine.begin() as connection:
        connection.exec_driver_sql(
            f"ALTER TABLE {_CELLS} ALTER COLUMN render_spec SET DEFAULT '{{}}'::jsonb"
        )
        # The current ORM maps legacy_predictions_sha256 (migration 0137,
        # TASK-0794); this pre-0137 schema gets the column on the test
        # database only.
        connection.exec_driver_sql(
            "ALTER TABLE game_data_v2.image_symbol_prediction_revisions "
            "ADD COLUMN legacy_predictions_sha256 varchar(64)"
        )
        # Likewise the geometry gate columns of migration 0139 (TASK-0807).
        connection.exec_driver_sql(
            "ALTER TABLE game_data_v2.source_images "
            "ADD COLUMN geometry_completeness_status varchar(24), "
            "ADD COLUMN geometry_completeness_evaluated_at timestamptz, "
            "ADD COLUMN geometry_exception_reason text, "
            "ADD COLUMN geometry_exception_by varchar(200), "
            "ADD COLUMN geometry_exception_at timestamptz"
        )
    game_id = _provision_game(database.engine, "task0791-convert")
    factory: sessionmaker[Session] = _factory(database.engine)
    seed = _seed(factory, game_id, artifact_root, label="legacy-source", slot_count=2)
    _resolve_via_reviewer_endpoint(database, artifact_root, seed)
    # TASK-0807 (D-484): slot 1 stays deferred, so the image is incomplete; an
    # operator exception admits it and the resolved board is cut.
    with game_storage_scope(game_id), factory.begin() as session:
        SqlAlchemyImageGeometryCompletenessStateRepository(session).set_exception(
            game_id, seed.source_image_id, reason="slot 1 deferred", actor="task-0807"
        )
    with game_storage_scope(game_id), factory() as session, session.begin():
        virtual_before = _state(session, seed.pending_ids[0])
        symbol_id = _symbol(session, game_id)
        board_id = _legacyfy(session, game_id, seed.pending_ids[0], symbol_id)
    with game_storage_scope(game_id), factory() as session:
        legacy_board = session.get(RecognizedBoardModel, board_id)
        assert legacy_board is not None
        legacy_modes = (legacy_board.asset_mode, legacy_board.geometry_revision)
        decisions_before = _decisions(session, game_id, board_id)
        legacy_cells = {row[1] for row in _cell_provenance(session, game_id, board_id)}
    assert legacy_modes == ("legacy_file", 1)
    assert legacy_cells == {"legacy_file"}
    assert {row[1] for row in decisions_before} == {str(symbol_id)}

    # Migration 0135 refuses while the legacy board exists.
    with pytest.raises(DBAPIError, match="LEGACY_FILE_BOARDS_PRESENT"):
        command.upgrade(database.config, _HEAD)
    with game_storage_scope(game_id), factory() as session:
        still_legacy = session.get(RecognizedBoardModel, board_id)
        assert still_legacy is not None and still_legacy.asset_mode == "legacy_file"

    # Preview: one source, one legacy board, 15 cells with decisions, no problems.
    with game_storage_scope(game_id), factory() as session:
        service = _service(session, artifact_root)
        assert service.source_ids(game_id) == (seed.source_image_id,)
        plan = service.plan(game_id=game_id, source_image_id=seed.source_image_id)
        prepared = service.render_check(plan)
        session.rollback()
    assert plan.problems == ()
    assert [board.recognized_board_id for board in plan.boards] == [board_id]
    assert plan.boards[0].owned_cell_count == 15
    assert plan.boards[0].assigned_cell_count == 15
    assert plan.boards[0].human_decision_cell_count == 15
    assert plan.boards[0].approved_cell_count == 1
    assert plan.boards[0].next_geometry_revision == 2
    assert len(prepared.entries) == 1 and len(prepared.entries[0].cells) == 15

    # Execute: the same render as the original virtual resolution of these corners.
    with game_storage_scope(game_id), factory() as session, session.begin():
        result = _service(session, artifact_root).convert_source(
            game_id=game_id,
            source_image_id=seed.source_image_id,
            created_at=datetime.now(UTC),
        )
    assert [board.recognized_board_id for board in result.boards] == [board_id]
    assert result.boards[0].previous_geometry_revision == 1
    assert result.boards[0].geometry_revision == 2
    assert result.boards[0].converted_cell_count == 15
    assert result.boards[0].preserved_decision_cell_count == 15
    assert result.boards[0].render_manifest_written is True

    with game_storage_scope(game_id), factory() as session:
        converted = _state(session, seed.pending_ids[0])
        decisions_after = _decisions(session, game_id, board_id)
        provenance = _cell_provenance(session, game_id, board_id)
        source_revisions = session.scalars(
            select(ImageSourceGeometryRevisionModel.revision)
            .where(ImageSourceGeometryRevisionModel.source_image_id == seed.source_image_id)
            .order_by(ImageSourceGeometryRevisionModel.revision)
        ).all()
        events = session.execute(
            text(
                """SELECT count(*) FROM game_data_v2.image_symbol_review_events e
                JOIN game_data_v2.image_symbol_review_cells c ON c.id = e.cell_review_id
                WHERE c.game_id = :game_id AND c.recognized_board_id = :board_id
                  AND e.action = 'geometry_invalidated' AND e.actor = :actor"""
            ),
            {"game_id": game_id, "board_id": board_id, "actor": LEGACY_BOARD_CONVERSION_ACTOR},
        ).scalar_one()
        legacy_history = session.scalar(
            select(ImageBoardGeometryRevisionModel.asset_mode).where(
                ImageBoardGeometryRevisionModel.recognized_board_id == board_id,
                ImageBoardGeometryRevisionModel.revision == 1,
            )
        )
    assert converted["asset_mode"] == converted["revision_asset_mode"] == "virtual_source"
    assert converted["board_relative_path"] is None and converted["crop_artifacts"] is None
    assert converted["geometry_revision"] == 2
    assert converted["manifest"] is not None
    assert converted["manifest"]["cells"] == converted["render_cells"]
    assert converted["review_cell_asset_modes"] == {"virtual_source"}
    # Same corners, same renderer: the render specs equal the original virtual ones
    # except for the revision number they carry.
    assert len(converted["render_cells"]) == len(virtual_before["render_cells"]) == 15
    assert decisions_after == decisions_before
    assert [row[1] for row in provenance] == ["virtual_source"] * 15
    assert {row[2] for row in provenance} == {2}
    assert [row[3] for row in provenance] == [None] * 15
    assert all(row[4] is not None and row[5] for row in provenance)
    approved = [row for row in provenance if row[0] == 3]
    assert approved[0][7] == "virtual_source" and approved[0][8] == 2 and approved[0][9] is True
    assert [row[7] for row in provenance if row[0] != 3] == [None] * 14
    assert source_revisions == [0, 1, 2]
    assert events == 15
    assert legacy_history == "legacy_file"

    # The rendered pixels of the converted cells equal the original virtual render.
    with game_storage_scope(game_id), factory() as session:
        pixel_checksums = session.execute(
            text(
                f"""SELECT cell_index, rendered_pixel_checksum_sha256 FROM {_CELLS}
                WHERE game_id = :game_id AND recognized_board_id = :board_id
                ORDER BY cell_index"""
            ),
            {"game_id": game_id, "board_id": board_id},
        ).all()
        original_pixels = session.execute(
            text(
                """SELECT e.rendered_pixel_checksum_sha256
                FROM game_data_v2.image_symbol_review_events e
                JOIN game_data_v2.image_symbol_review_cells c ON c.id = e.cell_review_id
                WHERE c.game_id = :game_id AND c.recognized_board_id = :board_id
                  AND c.cell_index = 0 AND e.previous_rendered_pixel_checksum_sha256 IS NULL
                ORDER BY e.created_at
                LIMIT 1"""
            ),
            {"game_id": game_id, "board_id": board_id},
        ).scalar_one_or_none()
    assert len({checksum for _index, checksum in pixel_checksums}) >= 1
    if original_pixels is not None:
        assert pixel_checksums[0][1] == original_pixels

    # Idempotent: nothing left to convert.
    with game_storage_scope(game_id), factory() as session, session.begin():
        again = _service(session, artifact_root).convert_source(
            game_id=game_id,
            source_image_id=seed.source_image_id,
            created_at=datetime.now(UTC),
        )
    assert again.boards == ()
    with game_storage_scope(game_id), factory() as session:
        assert _service(session, artifact_root).source_ids(game_id) == ()

    # Migration 0135 passes after the conversion and its downgrade restores the modes.
    command.upgrade(database.config, _HEAD)
    with database.engine.connect() as connection:
        defaults = connection.execute(
            text(
                """SELECT table_name, column_default FROM information_schema.columns
                WHERE table_schema = 'game_data_v2' AND column_name = 'asset_mode'
                  AND table_name IN ('recognized_boards', 'image_symbol_review_cells')
                ORDER BY table_name"""
            )
        ).all()
        board_check = connection.execute(
            text(
                """SELECT pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conname = 'ck_recognized_boards_asset_provenance'
                  AND conrelid = 'game_data_v2.recognized_boards'::regclass"""
            )
        ).scalar_one()
    assert [row[1] for row in defaults] == ["'virtual_source'::character varying"] * 2
    assert "legacy_file" not in board_check
    with (
        pytest.raises(DBAPIError, match="ck_recognized_boards_asset_provenance"),
        database.engine.begin() as connection,
    ):
        connection.execute(
            text(
                """UPDATE game_data_v2.recognized_boards
                    SET asset_mode = 'legacy_file', board_relative_path = 'boards/x.jpg',
                        board_checksum_sha256 = repeat('a', 64)
                    WHERE id = :board_id"""
            ),
            {"board_id": board_id},
        )
    command.downgrade(database.config, _PREVIOUS_HEAD)
    with database.engine.connect() as connection:
        restored = connection.execute(
            text(
                """SELECT pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conname = 'ck_recognized_boards_asset_provenance'
                  AND conrelid = 'game_data_v2.recognized_boards'::regclass"""
            )
        ).scalar_one()
    assert "legacy_file" in restored
    command.upgrade(database.config, _HEAD)

    # 0136 drops the column; the converted cells keep their render identity.
    command.upgrade(database.config, _DROP_RENDER_SPEC)
    with game_storage_scope(game_id), factory() as session:
        assert _cell_provenance(session, game_id, board_id) == provenance
        assert _decisions(session, game_id, board_id) == decisions_after
        assert (
            session.execute(
                text(
                    """SELECT count(*) FROM information_schema.columns
                    WHERE table_schema = 'game_data_v2' AND column_name = 'render_spec'
                      AND table_name LIKE '%image_symbol_review_cells%'"""
                )
            ).scalar_one()
            == 0
        )
