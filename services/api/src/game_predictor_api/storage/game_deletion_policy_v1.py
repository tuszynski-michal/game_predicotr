"""Frozen ownership contract for the TASK-0516 maintenance migration.

Do not broaden this version in place: a new table/ownership rule needs a new
migration and policy. References to a board are not ownership of a cohort.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter

POLICY = "resumable-legacy-game-deletion-v1"
LEGACY_ID = "80f3c7ec-6110-4e20-a263-2675ee5b15d6"
PROTECTED_ID = "03d64bfe-4d29-47dd-9153-76bd99b3b5d9"
LOCK_KEY = 516777
CONFIRMATION = f"DELETE 777 v0.1 {LEGACY_ID}; PRESERVE new-siedem"
DEFAULT_ARCHIVE = "artifacts/legacy-chat-search/777-v0.1-layouts.sqlite3"
MAX_BATCH_ROWS = 2000
MAX_BATCH_BYTES = 8 * 1024 * 1024

# Roots with an explicit immutable game owner. Nullable game_id means global,
# not permission to infer ownership from a different reference.
DIRECT = frozenset(
    [
        "symbols",
        "symbol_reference_images",
        "rules_versions",
        "jobs",
        "image_selection_runs",
        "curated_image_import_sources",
        "image_source_geometry_revisions",
        "image_geometry_rollout_states",
        "image_review_items",
        "image_symbol_review_states",
        "image_symbol_review_cells",
        "image_symbol_review_bulk_operations",
        "image_sequence_source_override_events",
        "image_page_geometry_overrides",
        "image_page_source_exclusions",
        "image_board_geometry_pending",
        "reviewer_access_sessions",
        "reviewer_work_assignments",
        "image_verified_cohort_exports",
        "verified_training_cohorts",
        "symbol_model_iterations",
        "game_symbol_model_activations",
        "grid_geometry_cohorts",
        "grid_calibration_profiles",
        "game_grid_profile_activations",
        "dataset_versions",
        "mobile_release_games",
        "review_batches",
        "review_feedback_exports",
        "image_symbol_prediction_revisions",
        "image_sequence_canonical",
        "image_board_search_candidates",
        "image_board_search_fast_documents",
        "image_board_search_projection_states",
        "legacy_board_search_archive_documents",
        "legacy_board_search_archive_states",
        "image_sequence_alternatives",
        "representative_ranking_cohorts",
        "representative_ranking_activations",
        "browser_selection_retention_states",
        "image_import_geometry_guard_decisions",
        "image_import_geometry_guard_resolution_manifests",
    ]
)

# Child column, parent table, parent column. One reviewed ownership path only.
INDIRECT = {
    "paylines": ("rules_version_id", "rules_versions", "id"),
    "rules_version_symbols": ("rules_version_id", "rules_versions", "id"),
    "payout_rules": ("rules_version_id", "rules_versions", "id"),
    "semi_automatic_image_selection_runs": ("job_id", "jobs", "id"),
    "semi_automatic_filename_verification_reviews": (
        "run_id",
        "semi_automatic_image_selection_runs",
        "id",
    ),
    "semi_automatic_image_selection_ranges": (
        "run_id",
        "semi_automatic_image_selection_runs",
        "id",
    ),
    "curated_image_import_batches": ("source_id", "curated_image_import_sources", "id"),
    "image_selection_groups": ("run_id", "image_selection_runs", "id"),
    "image_selection_candidates": ("run_id", "image_selection_runs", "id"),
    "image_selection_manual_decisions": ("run_id", "image_selection_runs", "id"),
    "image_import_job_files": ("job_id", "jobs", "id"),
    "source_images": ("import_job_id", "jobs", "id"),
    "recognized_boards": ("source_image_id", "source_images", "id"),
    "cell_observations": ("recognized_board_id", "recognized_boards", "id"),
    "image_review_queue_states": ("import_job_id", "jobs", "id"),
    "image_review_queue_items": ("import_job_id", "jobs", "id"),
    "image_review_resolution_events": ("review_item_id", "image_review_items", "id"),
    "image_symbol_review_events": ("cell_review_id", "image_symbol_review_cells", "id"),
    "image_symbol_review_bulk_targets": (
        "operation_id",
        "image_symbol_review_bulk_operations",
        "id",
    ),
    "image_board_geometry_revisions": ("recognized_board_id", "recognized_boards", "id"),
    "image_board_geometry_review_events": ("recognized_board_id", "recognized_boards", "id"),
    "reviewer_access_audit_events": ("session_id", "reviewer_access_sessions", "id"),
    "verified_training_cohort_items": ("cohort_id", "verified_training_cohorts", "id"),
    "verified_training_cohort_cells": ("cohort_id", "verified_training_cohorts", "id"),
    "image_layout_staging_rows": ("import_job_id", "jobs", "id"),
    "layout_import_rows": ("job_id", "jobs", "id"),
    "layout_import_normalized_rows": ("import_job_id", "jobs", "id"),
    "layouts": ("dataset_version_id", "dataset_versions", "id"),
    "layout_payouts": ("dataset_version_id", "dataset_versions", "id"),
    "mobile_releases": ("build_job_id", "jobs", "id"),
    "review_items": ("review_batch_id", "review_batches", "id"),
    "review_resolutions": ("review_item_id", "review_items", "id"),
    "representative_ranking_iterations": ("cohort_id", "representative_ranking_cohorts", "id"),
    "storage_gc_runs": ("job_id", "jobs", "id"),
}
SPECIAL = {
    "games": "id",
    "legacy_game_operational_cleanup_receipts": "legacy_game_id",
    "cleanup_operations": "target_id",
}
OWNED = DIRECT | INDIRECT.keys() | SPECIAL.keys()
PRESERVED = frozenset(
    [
        "alembic_version",
        "worker_lane_runtime",
        "image_file_executions",
        "image_pipeline_stage_results",
        "image_pipeline_terminal_manifests",
        "storage_usage_snapshots",
        "remote_manual_selection_sessions",
        "remote_manual_selection_collections",
        "remote_manual_selection_batches",
        "remote_manual_selection_files",
        "remote_manual_selection_operations",
        "remote_manual_selection_transfers",
        "remote_manual_selection_host_actions",
        "remote_manual_selection_audit_events",
        "game_deletion_operations",
        "game_deletion_batches",
    ]
)
SELF_LINKS = {
    "image_selection_runs": "source_run_id",
    "image_selection_groups": "origin_group_id",
}


class DeletionError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def quote(value: str) -> str:
    if re.fullmatch(r"[a-z_][a-z0-9_]*", value) is None:
        raise DeletionError("GAME_DELETE_SCHEMA_INVALID", value)
    return f'"{value}"'


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def owner_chain(table: str) -> tuple[str, ...]:
    if table in INDIRECT:
        return owner_chain(INDIRECT[table][1]) + (table,)
    return (table,)


def policy_digest() -> str:
    return digest(
        {
            "policy": POLICY,
            "direct": sorted(DIRECT),
            "indirect": INDIRECT,
            "special": SPECIAL,
            "self": SELF_LINKS,
            "queue": "trigger-owned-review-before-queue-state-v1",
            "owners": {table: owner_sql(table) for table in sorted(OWNED)},
        }
    )


def owner_sql(table: str, alias: str = "r", depth: int = 0, *, lock_parents: bool = False) -> str:
    """Scalar SQL expression; no graph-wide row markers or multiple owners."""
    if table in DIRECT:
        return f'{alias}."game_id"'
    if table in SPECIAL:
        return f"{alias}.{quote(SPECIAL[table])}"
    column, parent, parent_column = INDIRECT[table]
    parent_alias = f"owner_{depth}"
    return (
        f"(SELECT {owner_sql(parent, parent_alias, depth + 1, lock_parents=lock_parents)} "
        f"FROM public.{quote(parent)} {parent_alias} "
        f"WHERE {parent_alias}.{quote(parent_column)} = {alias}.{quote(column)}"
        + (" FOR SHARE" if lock_parents else "")
        + ")"
    )


@dataclass(frozen=True)
class ForeignKey:
    name: str
    child: str
    columns: tuple[str, ...]
    parent: str
    parent_columns: tuple[str, ...]
    action: str = "a"


def deletion_order(foreign_keys: tuple[ForeignKey, ...]) -> tuple[str, ...]:
    """Review projection is removed by its BEFORE DELETE trigger, not first."""
    tables = OWNED - {"image_review_queue_items"}
    children: dict[str, set[str]] = {table: set() for table in tables}
    for fk in foreign_keys:
        if fk.parent not in tables or fk.child == "image_review_queue_items":
            continue
        if fk.child not in OWNED:
            raise DeletionError("GAME_DELETE_FOREIGN_REFERENCE", fk.name)
        if fk.child == fk.parent:
            if SELF_LINKS.get(fk.child) != fk.columns[0]:
                raise DeletionError("GAME_DELETE_SELF_REFERENCE", fk.name)
            continue
        if fk.child == "games" and fk.columns == ("board_topology_rules_version_id",):
            continue
        children[fk.parent].add(fk.child)
    # These dependencies are implemented by triggers rather than FK constraints.
    children["image_review_queue_states"].add("image_review_items")
    children["games"].update(tables - {"games"})
    try:
        return tuple(
            TopologicalSorter({k: sorted(v) for k, v in sorted(children.items())}).static_order()
        )
    except CycleError as error:
        raise DeletionError("GAME_DELETE_DEPENDENCY_CYCLE", str(error)) from error
