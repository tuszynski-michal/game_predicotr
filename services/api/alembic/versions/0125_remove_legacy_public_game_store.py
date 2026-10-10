"""Remove the empty, legacy public copies of game-owned relations.

The drop set and order are deliberately frozen here.  Runtime catalog data is
used only for fail-closed guards; it never supplies a DDL identifier.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0125_remove_legacy_public_game_store"
down_revision: str | Sequence[str] | None = "0124_game_data_v2_partial_visibility_constraints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Snapshot of game-data-v2-manifest-v1.GAME_TABLES at the time of removal.
# Do not replace this with an import: the production DDL contract is frozen.
LEGACY_GAME_TABLES = (
    "browser_selection_retention_states",
    "cell_observations",
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
    "legacy_board_search_archive_documents",
    "legacy_board_search_archive_states",
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

# Child-before-parent order from the public-schema FK graph captured at T05.
# Self-references are table-owned and therefore do not constrain DROP TABLE.
DROP_ORDER = (
    "curated_image_import_batches",
    "curated_image_import_sources",
    "game_grid_profile_activations",
    "game_symbol_model_activations",
    "grid_calibration_profiles",
    "grid_geometry_cohorts",
    "image_board_geometry_pending",
    "image_board_geometry_review_events",
    "image_board_geometry_revisions",
    "image_board_search_fast_documents",
    "image_board_search_candidates",
    "image_board_search_projection_states",
    "image_geometry_rollout_states",
    "image_import_geometry_guard_decisions",
    "image_import_geometry_guard_resolution_manifests",
    "image_import_job_files",
    "image_layout_staging_rows",
    "image_page_geometry_overrides",
    "image_page_source_exclusions",
    "browser_selection_retention_states",
    "image_review_queue_items",
    "image_review_queue_states",
    "image_review_resolution_events",
    "image_selection_manual_decisions",
    "image_selection_candidates",
    "image_selection_groups",
    "image_selection_runs",
    "image_sequence_alternatives",
    "image_sequence_canonical",
    "image_sequence_source_override_events",
    "image_symbol_review_bulk_targets",
    "image_symbol_review_events",
    "image_symbol_review_bulk_operations",
    "image_symbol_review_states",
    "image_verified_cohort_exports",
    "layout_import_normalized_rows",
    "layout_import_rows",
    "layout_payouts",
    "layouts",
    "legacy_board_search_archive_documents",
    "legacy_board_search_archive_states",
    "mobile_release_games",
    "dataset_versions",
    "representative_ranking_activations",
    "representative_ranking_iterations",
    "representative_ranking_cohorts",
    "review_feedback_exports",
    "review_resolutions",
    "review_items",
    "review_batches",
    "reviewer_access_audit_events",
    "reviewer_work_assignments",
    "reviewer_access_sessions",
    "symbol_reference_images",
    "cell_observations",
    "verified_training_cohort_cells",
    "image_symbol_review_cells",
    "image_symbol_prediction_revisions",
    "symbol_model_iterations",
    "verified_training_cohort_items",
    "image_review_items",
    "recognized_boards",
    "image_source_geometry_revisions",
    "source_images",
    "verified_training_cohorts",
)


def _qualified(table_name: str) -> str:
    if table_name not in LEGACY_GAME_TABLES:
        raise RuntimeError(f"LEGACY_PUBLIC_STORE_UNKNOWN_STATIC_TABLE: {table_name}")
    return f'public."{table_name}"'


def _assert_static_definition() -> None:
    if (
        len(LEGACY_GAME_TABLES) != 65
        or len(set(LEGACY_GAME_TABLES)) != 65
        or len(DROP_ORDER) != 65
        or set(DROP_ORDER) != set(LEGACY_GAME_TABLES)
    ):
        raise RuntimeError("LEGACY_PUBLIC_STORE_STATIC_DEFINITION_INVALID")


def _assert_expected_relations(connection: sa.Connection) -> None:
    rows = connection.execute(
        sa.text(
            """
            SELECT relation.relname, relation.relkind
            FROM pg_class AS relation
            JOIN pg_namespace AS namespace_row ON namespace_row.oid = relation.relnamespace
            WHERE namespace_row.nspname = 'public'
              AND relation.relname = ANY(CAST(:tables AS text[]))
            """
        ),
        {"tables": list(LEGACY_GAME_TABLES)},
    ).all()
    kinds = {str(name): str(kind) for name, kind in rows}
    missing = sorted(set(LEGACY_GAME_TABLES) - set(kinds))
    if missing:
        raise RuntimeError(f"LEGACY_PUBLIC_STORE_TABLE_MISSING: {', '.join(missing)}")
    invalid = sorted(name for name, kind in kinds.items() if kind != "r")
    if invalid:
        raise RuntimeError(f"LEGACY_PUBLIC_STORE_RELATION_KIND_INVALID: {', '.join(invalid)}")


def _lock_expected_relations(connection: sa.Connection) -> None:
    connection.exec_driver_sql(
        "LOCK TABLE "
        + ", ".join(_qualified(table_name) for table_name in LEGACY_GAME_TABLES)
        + " IN ACCESS EXCLUSIVE MODE"
    )


def _assert_empty(connection: sa.Connection) -> None:
    for table_name in LEGACY_GAME_TABLES:
        exists = connection.scalar(
            sa.text(f"SELECT EXISTS (SELECT 1 FROM {_qualified(table_name)} LIMIT 1)")
        )
        if exists:
            raise RuntimeError(f"LEGACY_PUBLIC_STORE_TABLE_NOT_EMPTY: {table_name}")


def _assert_no_external_dependencies(connection: sa.Connection) -> None:
    external_fk = connection.scalar(
        sa.text(
            """
            SELECT 1
            FROM pg_constraint AS constraint_row
            JOIN pg_class AS target ON target.oid = constraint_row.confrelid
            JOIN pg_namespace AS target_namespace ON target_namespace.oid = target.relnamespace
            JOIN pg_class AS source ON source.oid = constraint_row.conrelid
            JOIN pg_namespace AS source_namespace ON source_namespace.oid = source.relnamespace
            WHERE constraint_row.contype = 'f'
              AND target_namespace.nspname = 'public'
              AND target.relname = ANY(CAST(:tables AS text[]))
              AND (source_namespace.nspname <> 'public'
                   OR NOT (source.relname = ANY(CAST(:tables AS text[]))))
            LIMIT 1
            """
        ),
        {"tables": list(LEGACY_GAME_TABLES)},
    )
    if external_fk is not None:
        raise RuntimeError("LEGACY_PUBLIC_STORE_EXTERNAL_FK")

    external_relation = connection.scalar(
        sa.text(
            """
            SELECT 1
            FROM pg_depend AS dependency
            JOIN pg_class AS target ON target.oid = dependency.refobjid
            JOIN pg_namespace AS target_namespace ON target_namespace.oid = target.relnamespace
            JOIN pg_class AS dependent ON dependent.oid = dependency.objid
            JOIN pg_namespace AS dependent_namespace
              ON dependent_namespace.oid = dependent.relnamespace
            WHERE dependency.classid = 'pg_class'::regclass
              AND dependency.refclassid = 'pg_class'::regclass
              AND target_namespace.nspname = 'public'
              AND target.relname = ANY(CAST(:tables AS text[]))
              AND dependent.relkind IN ('r', 'p', 'v', 'm', 'f')
              AND (dependent_namespace.nspname <> 'public'
                   OR NOT (dependent.relname = ANY(CAST(:tables AS text[]))))
            UNION ALL
            SELECT 1
            FROM pg_depend AS dependency
            JOIN pg_class AS target ON target.oid = dependency.refobjid
            JOIN pg_namespace AS target_namespace ON target_namespace.oid = target.relnamespace
            JOIN pg_rewrite AS rewrite_rule ON rewrite_rule.oid = dependency.objid
            JOIN pg_class AS dependent ON dependent.oid = rewrite_rule.ev_class
            JOIN pg_namespace AS dependent_namespace
              ON dependent_namespace.oid = dependent.relnamespace
            WHERE dependency.classid = 'pg_rewrite'::regclass
              AND dependency.refclassid = 'pg_class'::regclass
              AND target_namespace.nspname = 'public'
              AND target.relname = ANY(CAST(:tables AS text[]))
              AND dependent.relkind IN ('v', 'm')
              AND (dependent_namespace.nspname <> 'public'
                   OR NOT (dependent.relname = ANY(CAST(:tables AS text[]))))
            LIMIT 1
            """
        ),
        {"tables": list(LEGACY_GAME_TABLES)},
    )
    if external_relation is not None:
        raise RuntimeError("LEGACY_PUBLIC_STORE_EXTERNAL_RELATION_DEPENDENCY")


def upgrade() -> None:
    if op.get_context().as_sql:
        raise RuntimeError("LEGACY_PUBLIC_STORE_REMOVAL_REQUIRES_ONLINE_PREFLIGHT")
    _assert_static_definition()
    connection = op.get_bind()
    connection.exec_driver_sql("SET LOCAL lock_timeout = '2s'")
    connection.exec_driver_sql("SET LOCAL statement_timeout = '30s'")
    connection.exec_driver_sql("SET LOCAL search_path = pg_catalog, public")
    _assert_expected_relations(connection)
    _lock_expected_relations(connection)
    _assert_expected_relations(connection)
    _assert_empty(connection)
    _assert_no_external_dependencies(connection)
    for table_name in DROP_ORDER:
        op.execute(f"DROP TABLE {_qualified(table_name)} RESTRICT")


def downgrade() -> None:
    raise RuntimeError(
        "LEGACY_PUBLIC_STORE_REMOVAL_DOWNGRADE_UNSUPPORTED: "
        "dropped legacy tables cannot be reconstructed safely"
    )
