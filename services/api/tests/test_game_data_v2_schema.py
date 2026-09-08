from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from game_predictor_api.storage import models  # noqa: F401
from game_predictor_api.storage.game_data_v2_manifest_v1 import (
    CATALOG,
    CONTROL_TABLES,
    CREATE_TABLES,
    DELETE_TABLES,
    GAME_TABLES,
    MIGRATE_TABLES,
    PARTITIONED_TABLES,
    SHARED,
    ownership,
)
from game_predictor_api.storage.metadata import Base

ROOT = Path(__file__).resolve().parents[3]
REVISION = "0105_partitioned_game_storage"
PREVIOUS = "0104_game_deletion_access_paths"


def config(output: StringIO) -> Config:
    result = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    result.set_main_option("sqlalchemy.url", "postgresql+psycopg://unused:unused@localhost/unused")
    return result


def test_manifest_is_exhaustive_disjoint_and_fail_closed() -> None:
    known = CATALOG | SHARED | set(GAME_TABLES)
    assert not (CATALOG & SHARED or CATALOG & set(GAME_TABLES) or SHARED & set(GAME_TABLES))
    assert set(Base.metadata.tables) <= known
    assert known - set(Base.metadata.tables) == {
        "alembic_version",
        "game_deletion_operations",
        "game_deletion_batches",
    }
    assert CREATE_TABLES == MIGRATE_TABLES == DELETE_TABLES == PARTITIONED_TABLES == GAME_TABLES
    assert len(GAME_TABLES) == 65
    assert {ownership(name) for name in CONTROL_TABLES} == {"shared"}
    with pytest.raises(ValueError, match="GAME_STORAGE_UNKNOWN_TABLE"):
        ownership("future_unreviewed_table")


def test_large_history_and_samples_are_in_same_partitioned_store() -> None:
    assert {
        "cell_observations",
        "recognized_boards",
        "source_images",
        "image_review_items",
        "image_review_resolution_events",
        "image_symbol_review_cells",
        "image_symbol_review_events",
        "image_symbol_review_bulk_targets",
        "verified_training_cohort_cells",
        "verified_training_cohort_items",
        "verified_training_cohorts",
        "symbol_model_iterations",
    } <= set(GAME_TABLES)
    assert "jobs" in CATALOG and "jobs" not in GAME_TABLES


def test_offline_upgrade_is_additive_and_has_no_default_partition() -> None:
    output = StringIO()
    command.upgrade(config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()
    assert sql.count("PARTITION BY LIST (game_id)") == len(GAME_TABLES)
    assert "PARTITION OF" not in sql
    assert "DELETE FROM" not in sql
    assert "UPDATE public." not in sql
    assert "CREATE TRIGGER" not in sql
    for table in ("symbols", "rules_versions", "jobs"):
        assert (
            f"ALTER TABLE public.{table} ADD CONSTRAINT "
            f"uq_v2_{table}_game_id_id UNIQUE (game_id, id)" in sql
        )
    assert "REFERENCES public.jobs (id)" not in sql
    assert ScriptDirectory.from_config(config(StringIO())).get_current_head() == REVISION


def test_downgrade_locks_checks_and_never_cascades() -> None:
    output = StringIO()
    command.downgrade(config(output), f"{REVISION}:{PREVIOUS}", sql=True)
    sql = output.getvalue()
    assert (
        sql.index("LOCK TABLE")
        < sql.index("GAME_STORAGE_DOWNGRADE_NOT_EMPTY")
        < sql.index("DROP TABLE")
    )
    assert "CASCADE" not in sql
    assert "DROP SCHEMA game_data_v2" in sql
