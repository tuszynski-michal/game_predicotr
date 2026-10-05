"""Offline Alembic SQL: no connection or operator data writes."""

from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from game_predictor_api.storage.game_data_v2_manifest_v4 import GAME_TABLES as V4_TABLES
from game_predictor_api.storage.game_data_v2_manifest_v5 import CREATE_TABLES, GAME_TABLES, VERSION
from game_predictor_api.storage.game_partition_lifecycle import partition_name

ROOT = Path(__file__).resolve().parents[3]
HEAD = "0142_grid_geometry_shadow_results"
PREVIOUS = "0140_grid_engine_profiles"


def config(output: StringIO) -> Config:
    value = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    value.set_main_option("sqlalchemy.url", "postgresql+psycopg://unused:unused@localhost/unused")
    return value


def test_upgrade_is_empty_additive_scoped_and_covers_direct_child_rls() -> None:
    output = StringIO()
    command.upgrade(config(output), f"{PREVIOUS}:{HEAD}", sql=True)
    sql = output.getvalue()
    assert VERSION == "game-data-v2-manifest-v5"
    assert set(GAME_TABLES) - set(V4_TABLES) == {"image_geometry_shadow_results"}
    assert CREATE_TABLES == GAME_TABLES
    assert "PARTITION BY LIST(game_id)" in sql
    assert sql.index("GAME_STORAGE_MANIFEST_UNEXPECTED") < sql.index(
        "CREATE TABLE game_data_v2.image_geometry_shadow_results"
    )
    assert "REFERENCES game_data_v2.source_images(game_id,id)" in sql
    assert "REFERENCES game_data_v2.image_source_geometry_revisions(game_id,id)" in sql
    assert "REFERENCES public.jobs(game_id,id)" in sql
    assert "ALTER TABLE game_data_v2.%I ENABLE ROW LEVEL SECURITY" in sql
    assert "ALTER TABLE game_data_v2.%I FORCE ROW LEVEL SECURITY" in sql
    assert "CREATE POLICY game_scope_v1 ON game_data_v2.%I" in sql
    assert "uq_jobs_grid_shadow_request" in sql
    assert "UPDATE game_data_v2." not in sql and "DELETE FROM" not in sql
    assert "INSERT INTO game_data_v2." not in sql


def test_downgrade_refuses_data_loss_before_drop() -> None:
    output = StringIO()
    command.downgrade(config(output), f"{HEAD}:{PREVIOUS}", sql=True)
    sql = output.getvalue()
    assert sql.index("GRID_SHADOW_DOWNGRADE_NOT_EMPTY") < sql.index("DROP TABLE")
    assert sql.index("SET LOCAL row_security = off") < sql.index("GRID_SHADOW_DOWNGRADE_NOT_EMPTY")
    assert "CASCADE" not in sql


def test_partition_name_is_short_and_bound_to_manifest() -> None:
    from uuid import UUID

    assert len(partition_name(UUID(int=1), "image_geometry_shadow_results")) <= 63
