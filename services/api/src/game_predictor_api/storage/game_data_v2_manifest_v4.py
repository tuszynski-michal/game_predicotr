"""Frozen ownership policy for Alembic 0134 and later lifecycle consumers.

Version 4 removes three game-owned partitioned tables from the v3 game set
(D-467 S5, TASK-0759): the V1-era per-cell import records, replaced by
``board_render_manifests``, and the two never-populated tables of the frozen
board-search archive.  Migration 0134 drops exactly ``REMOVED_GAME_TABLES``.
The game set is an explicit frozen list; do not edit this version to add or
remove tables: add a migration and a new manifest version, as for v1 and v3.
"""

from __future__ import annotations

from game_predictor_api.storage.game_data_v2_manifest_v3 import (
    CATALOG,
    CONTROL_TABLES,
)
from game_predictor_api.storage.game_data_v2_manifest_v3 import DUAL_SCOPE as _DUAL_SCOPE
from game_predictor_api.storage.game_data_v2_manifest_v3 import GAME_TABLES as _V3_GAME_TABLES
from game_predictor_api.storage.game_data_v2_manifest_v3 import SCHEMA as _SCHEMA
from game_predictor_api.storage.game_data_v2_manifest_v3 import SHARED as _V3_SHARED
from game_predictor_api.storage.game_data_v2_manifest_v3 import VERSION as V3_VERSION

VERSION = "game-data-v2-manifest-v4"
PREVIOUS_VERSION = V3_VERSION
SCHEMA = _SCHEMA

SHARED = _V3_SHARED
GAME_TABLES: tuple[str, ...] = (
    "board_render_manifests",
    "browser_selection_retention_states",
    "curated_image_import_batches",
    "curated_image_import_sources",
    "dataset_versions",
    "game_grid_profile_activations",
    "game_symbol_model_activations",
    "grid_calibration_profiles",
    "grid_geometry_cohorts",
    "image_board_geometry_pending",
    "image_board_geometry_review_events",
    "image_board_geometry_revisions",
    "image_board_search_candidates",
    "image_board_search_fast_documents",
    "image_board_search_projection_states",
    "image_geometry_rollout_states",
    "image_import_geometry_guard_decisions",
    "image_import_geometry_guard_resolution_manifests",
    "image_import_job_files",
    "image_layout_staging_rows",
    "image_page_geometry_overrides",
    "image_page_source_exclusions",
    "image_review_items",
    "image_review_queue_items",
    "image_review_queue_states",
    "image_review_resolution_events",
    "image_selection_candidates",
    "image_selection_groups",
    "image_selection_manual_decisions",
    "image_selection_runs",
    "image_sequence_alternatives",
    "image_sequence_canonical",
    "image_sequence_source_override_events",
    "image_source_geometry_revisions",
    "image_symbol_prediction_revisions",
    "image_symbol_review_bulk_operations",
    "image_symbol_review_bulk_targets",
    "image_symbol_review_cells",
    "image_symbol_review_events",
    "image_symbol_review_states",
    "image_verified_cohort_exports",
    "layout_import_normalized_rows",
    "layout_import_rows",
    "layout_payouts",
    "layouts",
    "mobile_release_games",
    "recognized_boards",
    "representative_ranking_activations",
    "representative_ranking_cohorts",
    "representative_ranking_iterations",
    "review_batches",
    "review_feedback_exports",
    "review_items",
    "review_resolutions",
    "reviewer_access_audit_events",
    "reviewer_access_sessions",
    "reviewer_work_assignments",
    "source_images",
    "symbol_model_iterations",
    "symbol_reference_images",
    "verified_training_cohort_cells",
    "verified_training_cohort_items",
    "verified_training_cohorts",
)
# The v3 game tables that v4 no longer owns (dropped by migration 0134).
REMOVED_GAME_TABLES: tuple[str, ...] = tuple(sorted(set(_V3_GAME_TABLES) - set(GAME_TABLES)))

PARTITIONED_TABLES = GAME_TABLES
CREATE_TABLES = GAME_TABLES
MIGRATE_TABLES = GAME_TABLES
DELETE_TABLES = GAME_TABLES
DUAL_SCOPE = _DUAL_SCOPE

__all__ = [
    "CATALOG",
    "CONTROL_TABLES",
    "CREATE_TABLES",
    "DELETE_TABLES",
    "DUAL_SCOPE",
    "GAME_TABLES",
    "MIGRATE_TABLES",
    "PARTITIONED_TABLES",
    "PREVIOUS_VERSION",
    "REMOVED_GAME_TABLES",
    "SCHEMA",
    "SHARED",
    "VERSION",
    "ownership",
]


def ownership(table: str) -> str:
    if table in CATALOG:
        return "catalog"
    if table in GAME_TABLES:
        return "game"
    if table in SHARED or table in CONTROL_TABLES:
        return "shared"
    raise ValueError(f"GAME_STORAGE_UNKNOWN_TABLE: {table}")
