from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

# TASK-0940: `models` registers only some management mappings; the session
# mappings (migration 0150) are imported explicitly so that the exhaustiveness
# check below also covers their tables against `management_manifest`.
from game_predictor_api.storage import (
    management_session_models,  # noqa: F401
    models,  # noqa: F401
)
from game_predictor_api.storage.game_data_v2_manifest_v1 import GAME_TABLES as V1_GAME_TABLES
from game_predictor_api.storage.game_data_v2_manifest_v3 import GAME_TABLES as V3_GAME_TABLES
from game_predictor_api.storage.game_data_v2_manifest_v4 import (
    GAME_TABLES as V4_GAME_TABLES,
)
from game_predictor_api.storage.game_data_v2_manifest_v4 import REMOVED_GAME_TABLES
from game_predictor_api.storage.game_data_v2_manifest_v5 import (
    GAME_TABLES as V5_GAME_TABLES,
)
from game_predictor_api.storage.game_data_v2_manifest_v6 import (
    GAME_TABLES as V6_GAME_TABLES,
)
from game_predictor_api.storage.game_data_v2_manifest_v7 import (
    ADDED_GAME_TABLES,
    CATALOG,
    CONTROL_TABLES,
    CREATE_TABLES,
    DELETE_TABLES,
    GAME_TABLES,
    MIGRATE_TABLES,
    PARTITIONED_TABLES,
    POST_V5_SHARED,
    SHARED,
    VERSION,
    ownership,
)
from game_predictor_api.storage.management_manifest import SHARED_TABLES as MANAGEMENT_SHARED
from game_predictor_api.storage.metadata import Base

ROOT = Path(__file__).resolve().parents[3]
REVISION = "0105_partitioned_game_storage"
PREVIOUS = "0104_game_deletion_access_paths"


def config(output: StringIO) -> Config:
    result = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    result.set_main_option("sqlalchemy.url", "postgresql+psycopg://unused:unused@localhost/unused")
    return result


def test_manifest_is_exhaustive_disjoint_and_fail_closed() -> None:
    known = CATALOG | SHARED | POST_V5_SHARED | set(GAME_TABLES) | MANAGEMENT_SHARED
    assert not (CATALOG & SHARED or CATALOG & set(GAME_TABLES) or SHARED & set(GAME_TABLES))
    assert set(Base.metadata.tables) <= known
    assert known - set(Base.metadata.tables) == {
        "alembic_version",
        "game_deletion_operations",
        "game_deletion_batches",
    }
    assert CREATE_TABLES == MIGRATE_TABLES == DELETE_TABLES == PARTITIONED_TABLES == GAME_TABLES
    assert VERSION == "game-data-v2-manifest-v7"
    assert len(V3_GAME_TABLES) == 66
    assert len(V4_GAME_TABLES) == 63
    assert len(V5_GAME_TABLES) == 64
    assert len(V6_GAME_TABLES) == 68
    assert len(GAME_TABLES) == 70
    assert set(GAME_TABLES) - set(V1_GAME_TABLES) == {
        "board_render_manifests",
        "image_geometry_shadow_results",
        "super_game_derivation_state",
        "super_game_series",
        "super_game_series_audit_events",
        "super_game_series_generation_rows",
        *ADDED_GAME_TABLES,
    }
    # TASK-0933: v6 is v5 plus exactly the four super game series tables.
    assert set(V6_GAME_TABLES) - set(V5_GAME_TABLES) == {
        "super_game_derivation_state",
        "super_game_series",
        "super_game_series_audit_events",
        "super_game_series_generation_rows",
    }
    # TASK-0966/0970: v7 is v6 plus exactly the geometry correction revert audit
    # and the durable events of deferred-slot rejections.
    assert set(GAME_TABLES) - set(V6_GAME_TABLES) == {
        "image_board_geometry_pending_events",
        "image_geometry_correction_reverts",
    }
    assert {ownership(name) for name in ADDED_GAME_TABLES} == {"game"}
    # D-467 S5 (TASK-0759): v4 is v3 without exactly the three dropped tables.
    assert tuple(sorted(set(GAME_TABLES))) == GAME_TABLES
    assert set(V4_GAME_TABLES).issubset(V3_GAME_TABLES)
    assert set(V3_GAME_TABLES) - set(V4_GAME_TABLES) == set(REMOVED_GAME_TABLES)
    assert set(V5_GAME_TABLES) - set(V4_GAME_TABLES) == {"image_geometry_shadow_results"}
    assert set(REMOVED_GAME_TABLES) == {
        "cell_observations",
        "legacy_board_search_archive_documents",
        "legacy_board_search_archive_states",
    }
    assert not set(REMOVED_GAME_TABLES) & set(Base.metadata.tables)
    for table in REMOVED_GAME_TABLES:
        with pytest.raises(ValueError, match="GAME_STORAGE_UNKNOWN_TABLE"):
            ownership(table)
    assert {ownership(name) for name in CONTROL_TABLES} == {"shared"}
    assert {
        "semi_automatic_selection_v7_activation_gate",
        "global_geometry_profile_versions",
        "global_geometry_evidence_samples",
        "global_geometry_profile_write_receipts",
        "global_geometry_profile_qualification_results",
        "global_geometry_profile_qualification_receipts",
        "board_search_share_sessions",
        "board_search_share_audit_events",
        "board_search_share_query_events",
    } <= SHARED
    with pytest.raises(ValueError, match="GAME_STORAGE_UNKNOWN_TABLE"):
        ownership("future_unreviewed_table")


def test_large_history_and_samples_are_in_same_partitioned_store() -> None:
    assert {
        "board_render_manifests",
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


def test_reconciliation_receipt_is_shared_and_follows_catalog_game_deletion() -> None:
    name = "partial_board_reconciliation_receipts"
    assert ownership(name) == "shared"
    assert name not in PARTITIONED_TABLES
    table = Base.metadata.tables[name]
    assert tuple(column.name for column in table.primary_key.columns) == (
        "game_id",
        "preview_sha256",
        "sequence_number",
    )
    foreign_key = next(iter(table.foreign_keys))
    assert foreign_key.target_fullname == "games.id"
    assert foreign_key.ondelete == "CASCADE"


def test_offline_upgrade_is_additive_and_has_no_default_partition() -> None:
    output = StringIO()
    command.upgrade(config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()
    assert sql.count("PARTITION BY LIST (game_id)") == len(V1_GAME_TABLES)
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
    script = ScriptDirectory.from_config(config(StringIO()))
    revision = script.get_revision(REVISION)
    assert revision is not None
    assert revision.down_revision == PREVIOUS


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
