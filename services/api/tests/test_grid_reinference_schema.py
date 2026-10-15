"""Frozen v12, migration SQL, central registration and runtime manifest agreement."""

import importlib
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from game_predictor_api.storage import (
    catalog_repository,
    game_partition_lifecycle,
    game_storage_routing,
)
from game_predictor_api.storage import (
    game_data_v2_manifest_v11 as previous,
)
from game_predictor_api.storage import (
    game_data_v2_manifest_v12 as current,
)
from game_predictor_api.storage import game_data_v2_manifest_v14 as runtime

ROOT = Path(__file__).resolve().parents[3]
REVISION = "0159_grid_reinference"
PREVIOUS = "0158_new_game_v3_bootstrap"


def _sql(*, downgrade: bool = False) -> str:
    output = StringIO()
    config = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg://unused:unused@localhost/unused")
    if downgrade:
        command.downgrade(config, f"{REVISION}:{PREVIOUS}", sql=True)
    else:
        command.upgrade(config, f"{PREVIOUS}:{REVISION}", sql=True)
    return output.getvalue()


def test_v12_adds_only_three_game_tables_and_runtime_consumers_agree() -> None:
    assert set(current.GAME_TABLES) - set(previous.GAME_TABLES) == set(current.ADDED_GAME_TABLES)
    assert len(current.GAME_TABLES) == 76
    for name in ("CATALOG", "SHARED", "CONTROL_TABLES", "DUAL_SCOPE", "POST_V5_SHARED"):
        assert getattr(current, name) == getattr(previous, name)
    assert current.CREATE_TABLES == current.DELETE_TABLES == current.MIGRATE_TABLES
    assert current.PARTITIONED_TABLES == current.GAME_TABLES
    for module in (catalog_repository, game_storage_routing, game_partition_lifecycle):
        assert module.VERSION == runtime.VERSION
    for module in (catalog_repository, game_partition_lifecycle):
        assert vars(module)["CREATE_TABLES"] == runtime.GAME_TABLES
    for table in current.ADDED_GAME_TABLES:
        assert current.ownership(table) == "game"
        assert table not in previous.GAME_TABLES


def test_migration_adds_composite_relations_force_rls_and_existing_partitions() -> None:
    sql = _sql()
    assert sql.count("PARTITION BY LIST(game_id)") == 3
    assert "REFERENCES public.jobs(game_id,id)" in sql
    assert "REFERENCES game_data_v2.source_images(game_id,id)" in sql
    assert "FOREIGN KEY(game_id,live_source_image_id)" in sql
    assert "FOREIGN KEY(game_id,source_image_id)" not in sql
    assert "live_source_image_id IS NULL OR live_source_image_id = source_image_id" in sql
    assert "FOREIGN KEY(game_id,operation_id,source_ordinal,source_image_id)" in sql
    assert "ordinal = source_ordinal * 10 + position_index + 1" in sql
    assert "WHERE manifest_version='game-data-v2-manifest-v11'" in sql
    for table in current.ADDED_GAME_TABLES:
        assert f"ALTER TABLE game_data_v2.{table} FORCE ROW LEVEL SECURITY" in sql
        assert f"PARTITION OF game_data_v2.{table}" in sql
    assert "current_game_id_v1()" in sql
    assert "GRANT %s" in sql
    assert "CREATE ROLE" not in sql
    assert "DEFAULT PARTITION" not in sql
    assert "DELETE FROM" not in sql


def test_only_live_source_identity_has_a_foreign_key() -> None:
    from game_predictor_api.storage.grid_reinference_models import GridReinferenceSourceModel

    table = GridReinferenceSourceModel.__table__
    assert not table.c.source_image_id.foreign_keys
    assert table.c.live_source_image_id.nullable
    assert {key.target_fullname for key in table.c.live_source_image_id.foreign_keys} == {
        "source_images.id"
    }


def test_downgrade_checks_all_history_before_dropping_in_dependency_order() -> None:
    sql = _sql(downgrade=True)
    assert sql.index("SET LOCAL row_security=off") < sql.index(
        "GRID_REINFERENCE_DOWNGRADE_HAS_HISTORY"
    )
    assert sql.count("GRID_REINFERENCE_DOWNGRADE_HAS_HISTORY") == 3
    assert sql.rindex("GRID_REINFERENCE_DOWNGRADE_HAS_HISTORY") < sql.index("DROP TABLE")
    positions = [
        sql.index(f"DROP TABLE game_data_v2.{name}") for name in reversed(current.ADDED_GAME_TABLES)
    ]
    assert positions == sorted(positions)
    assert "CASCADE" not in sql


def test_models_register_in_both_import_orders() -> None:
    script = """
import importlib, sys
importlib.import_module('game_predictor_api.storage.' + sys.argv[1])
from game_predictor_api.storage import models
from game_predictor_api.storage.game_data_v2_manifest_v12 import ADDED_GAME_TABLES
assert set(ADDED_GAME_TABLES) <= models.Base.metadata.tables.keys()
for name in ADDED_GAME_TABLES:
    assert models.Base.metadata.tables[name].c.game_id.primary_key
"""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        str(ROOT / path)
        for path in ("services/api/src", "services/worker/src", "services/test_support")
    )
    for first in ("models", "grid_reinference_models"):
        result = subprocess.run(
            [sys.executable, "-c", script, first],
            env=environment,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr


def test_previous_frozen_manifest_membership_remains_unchanged() -> None:
    expected_counts = {
        1: 65,
        2: 65,
        3: 66,
        4: 63,
        5: 64,
        6: 68,
        7: 70,
        8: 73,
        9: 73,
        10: 73,
        11: 73,
    }
    for version, count in expected_counts.items():
        module = importlib.import_module(
            f"game_predictor_api.storage.game_data_v2_manifest_v{version}"
        )
        assert len(module.GAME_TABLES) == count
        assert not set(current.ADDED_GAME_TABLES) & set(module.GAME_TABLES)
