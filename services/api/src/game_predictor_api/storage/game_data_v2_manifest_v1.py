"""Frozen ownership policy for Alembic 0105 and later lifecycle consumers.

Do not edit version 1 to add tables. Add a migration and a new manifest version.
The shared job coordinator retains its global execution-slot uniqueness.
"""

from __future__ import annotations

from game_predictor_api.storage.game_deletion_policy_v1 import DIRECT, INDIRECT

VERSION = "game-data-v2-manifest-v1"
SCHEMA = "game_data_v2"

CATALOG = frozenset(
    {
        "games",
        "symbols",
        "rules_versions",
        "rules_version_symbols",
        "paylines",
        "payout_rules",
        "jobs",
    }
)
SHARED = frozenset(
    {
        "alembic_version",
        "cleanup_operations",
        "legacy_game_operational_cleanup_receipts",
        "game_deletion_operations",
        "game_deletion_batches",
        "worker_lane_runtime",
        "image_file_executions",
        "image_pipeline_stage_results",
        "image_pipeline_terminal_manifests",
        "storage_usage_snapshots",
        "storage_gc_runs",
        "mobile_releases",
        "semi_automatic_image_selection_runs",
        "semi_automatic_filename_verification_reviews",
        "semi_automatic_image_selection_ranges",
        "remote_manual_selection_sessions",
        "remote_manual_selection_collections",
        "remote_manual_selection_batches",
        "remote_manual_selection_files",
        "remote_manual_selection_operations",
        "remote_manual_selection_transfers",
        "remote_manual_selection_host_actions",
        "remote_manual_selection_audit_events",
    }
)
# The imported policy is itself frozen migration input, not runtime ORM metadata.
GAME_TABLES = tuple(sorted((DIRECT | INDIRECT.keys()) - CATALOG - SHARED))

# Partition every game-owned relation, including small dependent metadata. This
# avoids alternate legacy/v2 FK targets and gives create/delete one closed set.
PARTITIONED_TABLES = GAME_TABLES
CREATE_TABLES = GAME_TABLES
MIGRATE_TABLES = GAME_TABLES
DELETE_TABLES = GAME_TABLES
CONTROL_TABLES = (
    "game_storage_table_manifest",
    "game_storage_locations",
    "game_storage_migrations",
    "game_storage_table_progress",
)
DUAL_SCOPE = frozenset({"browser_selection_retention_states"})


def ownership(table: str) -> str:
    if table in CATALOG:
        return "catalog"
    if table in GAME_TABLES:
        return "game"
    if table in SHARED or table in CONTROL_TABLES:
        return "shared"
    raise ValueError(f"GAME_STORAGE_UNKNOWN_TABLE: {table}")
