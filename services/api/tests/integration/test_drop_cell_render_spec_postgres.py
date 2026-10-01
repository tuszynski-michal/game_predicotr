"""TASK-0793: migration 0136 drops ``image_symbol_review_cells.render_spec``.

Runs on a dedicated ``*_test`` database only (fixture from the TASK-0790
test).  The schema is built up to ``0135`` on a fresh database, a full and a
partial board are resolved through the Reviewer endpoint, then:

- the preflight refuses (``CELL_RENDER_MANIFEST_MISSING``) while a virtual
  cell has no board render manifest for its revision and changes nothing;
- the upgrade drops the column from the parent and every partition, replaces
  both CHECK constraints by versions without it (``NOT VALID``, validated
  afterwards like the runbook does) and keeps every other cell value;
- the downgrade refuses (``CELL_RENDER_SPEC_DROP_IRREVERSIBLE``);
- a game provisioned after ``0136`` has no such column and its deferred board
  is resolved and previewed through the current writers and readers.

The current writers no longer set the column, which the ``0135`` CHECK still
requires for virtual cells: on this test database a ``BEFORE INSERT`` trigger
stands in for the former writer value until the upgrade.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from alembic import command
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemySymbolCellReviewQueryRepository,
)
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from test_cell_render_specs_postgres import _boards, _managed_source, _resolve_full_and_partial
from test_virtual_deferred_resolution_postgres import (
    _Database,
    _factory,
    _provision_game,
    _seed,
    database,  # noqa: F401
)

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)

_BEFORE = "0135_virtual_only_asset_modes"
_HEAD = "0136_drop_cell_render_spec"
_CELLS = "game_data_v2.image_symbol_review_cells"
_MANIFESTS = "game_data_v2.board_render_manifests"
_CHECKS = (
    "ck_image_symbol_review_cells_asset_provenance",
    "ck_image_symbol_review_cells_source_asset",
)
_SHIM = f"""
CREATE FUNCTION public.task0793_render_spec_shim() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.asset_mode = 'virtual_source' AND NEW.render_spec IS NULL THEN
        NEW.render_spec := '{{}}'::jsonb;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER task0793_render_spec_shim BEFORE INSERT ON {_CELLS}
    FOR EACH ROW EXECUTE FUNCTION public.task0793_render_spec_shim();
"""


def _version(engine: Engine) -> str:
    with engine.connect() as connection:
        return str(connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one())


def _render_spec_relations(engine: Engine) -> set[str]:
    """Cell parent and partitions that still have a live ``render_spec`` column."""

    with engine.connect() as connection:
        return {
            str(row[0])
            for row in connection.execute(
                text(
                    f"""SELECT a.attrelid::regclass::text FROM pg_attribute a
                    WHERE a.attname = 'render_spec' AND NOT a.attisdropped
                      AND (a.attrelid = '{_CELLS}'::regclass OR a.attrelid IN (
                        SELECT inhrelid FROM pg_inherits
                        WHERE inhparent = '{_CELLS}'::regclass))"""
                )
            )
        }


def _cell_partitions(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        return {
            str(row[0])
            for row in connection.execute(
                text(
                    f"""SELECT inhrelid::regclass::text FROM pg_inherits
                    WHERE inhparent = '{_CELLS}'::regclass"""
                )
            )
        }


def _checks(engine: Engine) -> dict[str, tuple[bool, str]]:
    with engine.connect() as connection:
        return {
            str(row.conname): (bool(row.convalidated), str(row.definition))
            for row in connection.execute(
                text(
                    f"""SELECT conname, convalidated, pg_get_constraintdef(oid) AS definition
                    FROM pg_constraint
                    WHERE conrelid = '{_CELLS}'::regclass AND conname = ANY(:names)"""
                ),
                {"names": list(_CHECKS)},
            )
        }


def _cell_rows(engine: Engine, game_id: UUID) -> list[tuple[Any, ...]]:
    with engine.connect() as connection:
        return [
            tuple(row)
            for row in connection.execute(
                text(
                    f"""SELECT id, recognized_board_id, cell_index, asset_mode, source_visibility,
                        geometry_revision, crop_sample_id, crop_checksum_sha256,
                        render_spec_checksum_sha256, rendered_pixel_checksum_sha256,
                        logical_cell_key, logical_cell_key_v2, render_identity_v2_sha256,
                        extractor_version, review_state, revision
                    FROM {_CELLS} WHERE game_id = :game_id
                    ORDER BY recognized_board_id, cell_index"""
                ),
                {"game_id": game_id},
            )
        ]


def test_migration_0136_drops_the_cell_render_spec(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    engine = database.engine
    artifact_root = tmp_path / "artifacts"
    # 0136 refuses to downgrade: build the 0135 schema on a fresh database.
    engine.dispose()
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA IF EXISTS game_data_v2 CASCADE")
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
    command.upgrade(database.config, _BEFORE)
    with engine.begin() as connection:
        connection.exec_driver_sql(_SHIM)
        # The current ORM maps legacy_predictions_sha256 (migration 0137,
        # TASK-0794); this pre-0137 schema gets the column on the test
        # database only.
        connection.exec_driver_sql(
            "ALTER TABLE game_data_v2.image_symbol_prediction_revisions "
            "ADD COLUMN legacy_predictions_sha256 varchar(64)"
        )
    game_id = _provision_game(engine, "task0793-drop")
    factory = _factory(engine)
    seed = _seed(factory, game_id, artifact_root, label="task0793-source", slot_count=2)
    _resolve_full_and_partial(database, artifact_root, seed)
    with game_storage_scope(game_id), factory() as session:
        boards = _boards(session, game_id)
    full_board = boards[0][0]
    before = _cell_rows(engine, game_id)
    assert len(before) == 30
    assert {row[3] for row in before} == {"virtual_source", "none"}
    assert _render_spec_relations(engine) == {_CELLS} | _cell_partitions(engine)

    # Preflight: a virtual cell without a manifest of its revision blocks the drop.
    with engine.begin() as connection:
        saved = (
            connection.execute(
                text(f"SELECT * FROM {_MANIFESTS} WHERE game_id = :g AND recognized_board_id = :b"),
                {"g": game_id, "b": full_board},
            )
            .mappings()
            .one()
        )
        connection.execute(
            text(f"DELETE FROM {_MANIFESTS} WHERE game_id = :g AND recognized_board_id = :b"),
            {"g": game_id, "b": full_board},
        )
    with pytest.raises(DBAPIError, match="CELL_RENDER_MANIFEST_MISSING: 15 virtual review cells"):
        command.upgrade(database.config, _HEAD)
    assert _version(engine) == _BEFORE
    assert _render_spec_relations(engine) == {_CELLS} | _cell_partitions(engine)
    with engine.begin() as connection:
        columns = ", ".join(saved.keys())
        values = ", ".join(
            f"CAST(:{key} AS jsonb)" if key == "cells" else f":{key}" for key in saved
        )
        connection.execute(
            text(f"INSERT INTO {_MANIFESTS} ({columns}) VALUES ({values})"),
            {**saved, "cells": json.dumps(saved["cells"])},
        )
        connection.exec_driver_sql(f"DROP TRIGGER task0793_render_spec_shim ON {_CELLS}")
        connection.exec_driver_sql("DROP FUNCTION public.task0793_render_spec_shim()")

    # Upgrade: the column is gone everywhere, the CHECKs no longer mention it.
    command.upgrade(database.config, _HEAD)
    assert _version(engine) == _HEAD
    assert _render_spec_relations(engine) == set()
    checks = _checks(engine)
    assert set(checks) == set(_CHECKS)
    for validated, definition in checks.values():
        assert validated is False
        assert "render_spec IS" not in definition and "jsonb_typeof" not in definition
        assert "render_spec_checksum_sha256" in definition
    assert _cell_rows(engine, game_id) == before
    # Runbook step: validation scans the rows without blocking writes.
    with engine.begin() as connection:
        for name in _CHECKS:
            connection.exec_driver_sql(f"ALTER TABLE {_CELLS} VALIDATE CONSTRAINT {name}")
    assert all(validated for validated, _definition in _checks(engine).values())

    # Downgrade refuses and leaves the schema at 0136.
    with pytest.raises(Exception, match="CELL_RENDER_SPEC_DROP_IRREVERSIBLE"):
        command.downgrade(database.config, _BEFORE)
    assert _version(engine) == _HEAD

    # A game provisioned after 0136 has no column; current writers and readers work.
    later = _provision_game(engine, "task0793-later")
    assert _render_spec_relations(engine) == set()
    later_root = tmp_path / "later"
    later_seed = _seed(factory, later, later_root, label="task0793-later", slot_count=2)
    _resolve_full_and_partial(database, later_root, later_seed)
    later_rows = _cell_rows(engine, later)
    assert len(later_rows) == 30
    assert sum(1 for row in later_rows if row[3] == "virtual_source") == 15 + 9
    with game_storage_scope(later), factory() as session:
        _managed_source(later_root, later, session)
        virtual_ids = tuple(row[0] for row in later_rows if row[3] == "virtual_source")
        assets = SqlAlchemySymbolCellReviewQueryRepository(session).get_assets(
            game_id=later, cell_review_ids=virtual_ids
        )
    assert {asset.cell_review_id for asset in assets} == set(virtual_ids)
    assert all(asset.render_spec is not None for asset in assets)
