"""TASK-0759 (D-467 S5): offline SQL contract of migration 0134."""

from __future__ import annotations

import importlib.util
from io import StringIO
from pathlib import Path
from types import ModuleType

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from game_predictor_api.storage.game_data_v2_manifest_v4 import GAME_TABLES, REMOVED_GAME_TABLES

ROOT = Path(__file__).resolve().parents[3]
REVISION = "0134_drop_cell_observations_and_legacy_archive"
PREVIOUS = "0133_virtual_only_import_policies"


def _config(output: StringIO) -> Config:
    result = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    result.set_main_option("sqlalchemy.url", "postgresql+psycopg://unused:unused@localhost/unused")
    return result


def _migration_module() -> ModuleType:
    path = ROOT / "services" / "api" / "alembic" / "versions" / f"{REVISION}.py"
    spec = importlib.util.spec_from_file_location("migration_0134", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_0134_freezes_exactly_the_tables_manifest_v4_removes() -> None:
    module = _migration_module()
    assert module.DROPPED_TABLES == REMOVED_GAME_TABLES
    assert not set(module.DROPPED_TABLES) & set(GAME_TABLES)
    revision = ScriptDirectory.from_config(_config(StringIO())).get_revision(REVISION)
    assert revision is not None and revision.down_revision == PREVIOUS


def test_migration_0134_preflights_then_moves_the_registry_and_drops_in_order() -> None:
    output = StringIO()
    command.upgrade(_config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()
    assert "SET LOCAL lock_timeout = '5s'" in sql
    assert "SET LOCAL statement_timeout = '120s'" in sql
    ordered = [
        "LOCK TABLE public.game_storage_locations IN ACCESS EXCLUSIVE MODE",
        "GAME_STORAGE_LIFECYCLE_IN_PROGRESS",
        "GAME_STORAGE_LOCATION_BUSY",
        "GAME_STORAGE_MANIFEST_UNEXPECTED",
        "GAME_STORAGE_DROP_TABLE_UNEXPECTED",
        "GAME_STORAGE_DROP_FOREIGN_KEY_PRESENT",
        "LOCK TABLE game_data_v2.cell_observations, "
        "game_data_v2.legacy_board_search_archive_documents, "
        "game_data_v2.legacy_board_search_archive_states IN ACCESS EXCLUSIVE MODE",
        "LOCK TABLE game_data_v2.recognized_boards, game_data_v2.board_render_manifests "
        "IN SHARE MODE",
        "CELL_OBSERVATIONS_LEGACY_REVISION_ZERO_PRESENT",
        "BOARD_RENDER_MANIFEST_MISSING",
        "LEGACY_BOARD_SEARCH_ARCHIVE_NOT_EMPTY",
        "INSERT INTO public.game_storage_table_manifest",
        "DROP CONSTRAINT ck_game_storage_locations_manifest_version_v3",
        "SET manifest_version = 'game-data-v2-manifest-v4'",
        "CHECK (manifest_version = 'game-data-v2-manifest-v4')",
        "DO $drop$",
    ]
    positions = [sql.index(fragment) for fragment in ordered]
    assert positions == sorted(positions)
    # The registry rows list v4 tables only; every dropped name is absent.
    registry = sql[sql.index("INSERT INTO public.game_storage_table_manifest") :]
    registry = registry[: registry.index("ALTER TABLE public.game_storage_locations")]
    assert "'game-data-v2-manifest-v4'" in registry
    for table in REMOVED_GAME_TABLES:
        assert f"'{table}'" not in registry
    assert "'board_render_manifests'" in registry
    # Partitions first, then the parent; never CASCADE, never touch other data.
    drop = sql[sql.index("DO $drop$") :]
    assert drop.index("FOR partition IN") < drop.index(
        "EXECUTE format('DROP TABLE %I.%I', 'game_data_v2', parent)"
    )
    assert "CASCADE" not in sql
    assert "DELETE FROM" not in sql


def test_migration_0134_downgrade_refuses() -> None:
    output = StringIO()
    command.downgrade(_config(output), f"{REVISION}:{PREVIOUS}", sql=True)
    sql = output.getvalue()
    assert "CELL_OBSERVATIONS_DROP_IRREVERSIBLE" in sql
    assert "CREATE TABLE" not in sql
    assert "game-data-v2-manifest-v3'" not in sql
