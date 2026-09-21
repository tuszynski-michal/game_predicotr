"""Ownership policy for post-v1 public control-plane tables.

The game partition list remains frozen from manifest v1.  This version only
classifies later public tables so they cannot be mistaken for game-owned data.
"""

from __future__ import annotations

from game_predictor_api.storage.game_data_v2_manifest_v1 import (
    CATALOG,
    CONTROL_TABLES,
    GAME_TABLES,
)
from game_predictor_api.storage.game_data_v2_manifest_v1 import CREATE_TABLES as _CREATE_TABLES
from game_predictor_api.storage.game_data_v2_manifest_v1 import DELETE_TABLES as _DELETE_TABLES
from game_predictor_api.storage.game_data_v2_manifest_v1 import DUAL_SCOPE as _DUAL_SCOPE
from game_predictor_api.storage.game_data_v2_manifest_v1 import MIGRATE_TABLES as _MIGRATE_TABLES
from game_predictor_api.storage.game_data_v2_manifest_v1 import (
    PARTITIONED_TABLES as _PARTITIONED_TABLES,
)
from game_predictor_api.storage.game_data_v2_manifest_v1 import SCHEMA as _SCHEMA

VERSION = "game-data-v2-manifest-v2"

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
        "semi_automatic_selection_v7_activation_gate",
        "remote_manual_selection_sessions",
        "remote_manual_selection_collections",
        "remote_manual_selection_batches",
        "remote_manual_selection_files",
        "remote_manual_selection_operations",
        "remote_manual_selection_transfers",
        "remote_manual_selection_host_actions",
        "remote_manual_selection_audit_events",
        "global_geometry_profile_versions",
        "global_geometry_evidence_samples",
        "global_geometry_profile_write_receipts",
    }
)

SCHEMA = _SCHEMA
PARTITIONED_TABLES = _PARTITIONED_TABLES
CREATE_TABLES = _CREATE_TABLES
MIGRATE_TABLES = _MIGRATE_TABLES
DELETE_TABLES = _DELETE_TABLES
DUAL_SCOPE = _DUAL_SCOPE


def ownership(table: str) -> str:
    if table in CATALOG:
        return "catalog"
    if table in GAME_TABLES:
        return "game"
    if table in SHARED or table in CONTROL_TABLES:
        return "shared"
    raise ValueError(f"GAME_STORAGE_UNKNOWN_TABLE: {table}")
