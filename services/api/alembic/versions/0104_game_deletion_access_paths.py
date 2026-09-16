"""Indexed ownership cursors and incoming FK checks for bounded deletion.

Concurrent builds commit independently. A retry repairs only an invalid index
with our exact expected definition. No domain rows or existing indexes change.
Apply explicitly during a supervised maintenance window, not on API startup.
"""

import hashlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0104_game_deletion_access_paths"
down_revision: str | Sequence[str] | None = "0103_resumable_game_deletion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen catalog assessment at 0102. Each semicolon separates index key lists.
SPEC = """
browser_selection_retention_states game_id,upload_id;import_job_id
cell_observations recognized_board_id,id;source_geometry_revision_id
cleanup_operations target_id,id
curated_image_import_batches source_id,id
curated_image_import_sources game_id,id
dataset_versions game_id,id;source_job_id
game_grid_profile_activations game_id,id;previous_profile_id;profile_id
game_symbol_model_activations game_id,id;model_iteration_id;previous_model_iteration_id
grid_calibration_profiles game_id,id
grid_geometry_cohorts game_id,id
image_board_geometry_pending game_id,id;recognized_board_id;review_item_id;source_image_id
image_board_geometry_review_events recognized_board_id,id;review_item_id
image_board_geometry_revisions recognized_board_id,id;source_geometry_revision_id
image_board_search_candidates game_id,review_item_id;import_job_id;recognized_board_id
image_geometry_rollout_states last_source_image_id;validation_job_id
image_import_geometry_guard_decisions browser_selection_id;game_id,id
image_import_geometry_guard_resolution_manifests browser_selection_id;game_id,id
image_layout_staging_rows recognized_board_id
image_page_geometry_overrides game_id,id
image_page_source_exclusions game_id,id
image_review_items game_id,id
image_review_queue_items import_job_id,review_item_id
image_review_resolution_events review_item_id,id
image_selection_candidates run_id,id
image_selection_manual_decisions candidate_id;run_id,idempotency_key
image_selection_runs game_id,id
image_sequence_alternatives game_id,id;import_job_id
image_sequence_canonical import_job_id;recognized_board_id;review_item_id;source_image_id
image_sequence_source_override_events game_id,id;selected_review_item_id
image_source_geometry_revisions game_id,id;topology_rules_version_id
image_symbol_prediction_revisions game_id,id;model_iteration_id;recognized_board_id;source_job_id
image_symbol_review_bulk_operations filter_symbol_id;game_id,id;target_symbol_id
image_symbol_review_bulk_targets cell_review_id;recognized_board_id;review_item_id
image_symbol_review_cells approved_source_geometry_revision_id;assigned_symbol_id;game_id,id
image_symbol_review_cells import_job_id;recognized_board_id;source_geometry_revision_id
image_symbol_review_cells verified_symbol_id_v2
image_symbol_review_events approved_source_geometry_revision_id;assigned_symbol_id;cell_review_id,id
image_symbol_review_events operation_id;previous_approved_source_geometry_revision_id
image_symbol_review_events previous_assigned_symbol_id;previous_source_geometry_revision_id
image_symbol_review_events previous_verified_symbol_id_v2;source_geometry_revision_id
image_symbol_review_events verified_symbol_id_v2
image_verified_cohort_exports game_id,id;import_job_id
jobs game_id,id
layout_import_normalized_rows import_job_id,line_number;import_job_id,validation_job_id,line_number
layout_import_normalized_rows rules_version_id
layout_payouts dataset_version_id,sequence_number
layouts dataset_version_id,id
legacy_game_operational_cleanup_receipts legacy_game_id,id;protected_game_id
mobile_release_games dataset_version_id;game_id,mobile_release_id;rules_version_id
mobile_releases build_job_id,id
paylines rules_version_id,id
payout_rules rules_version_id,id
recognized_boards source_image_id,id
representative_ranking_activations game_id,id;iteration_id;previous_iteration_id
representative_ranking_cohorts game_id,id
representative_ranking_iterations cohort_id,id
review_batches game_id,id
review_feedback_exports game_id,id
review_items review_batch_id,id
review_resolutions review_item_id,id
reviewer_access_audit_events session_id,id
reviewer_access_sessions game_id,id
reviewer_work_assignments game_id,id;import_job_id;reviewer_access_session_id,game_id,import_job_id
rules_versions game_id,id
semi_automatic_image_selection_ranges run_id,id
semi_automatic_image_selection_runs job_id,id
source_images import_job_id,id
storage_gc_runs job_id,id
symbol_model_iterations cohort_id;game_id,id
symbol_reference_images game_id,symbol_id;source_observation_id;source_recognized_board_id
symbol_reference_images source_review_item_id
symbols game_id,id
verified_training_cohort_cells cell_review_id;cohort_id,id;recognized_board_id;review_item_id
verified_training_cohort_cells source_geometry_revision_id;source_image_id
verified_training_cohort_items cohort_id,id;import_job_id;recognized_board_id;review_item_id
verified_training_cohort_items source_image_id
verified_training_cohorts game_id,id
"""


def indexes() -> list[tuple[str, str, tuple[str, ...]]]:
    result = []
    for line in SPEC.strip().splitlines():
        table, definitions = line.split()
        for definition in definitions.split(";"):
            name = "ix_gd_0104_" + hashlib.sha256(f"{table}:{definition}".encode()).hexdigest()[:16]
            result.append((name, table, tuple(definition.split(","))))
    return result


def upgrade() -> None:
    if op.get_context().as_sql:
        raise RuntimeError("0104 requires online catalog validation; no offline SQL")
    connection = op.get_bind()
    # Alembic commits the preceding DDL before a concurrent index operation.
    with op.get_context().autocommit_block():
        previous = connection.execute(
            sa.text("SELECT current_setting('statement_timeout'),current_setting('lock_timeout')")
        ).one()
        try:
            connection.execute(sa.text("SET statement_timeout='120s'"))
            connection.execute(sa.text("SET lock_timeout='2s'"))
            for name, table, fields in indexes():
                expected = (
                    f"CREATE INDEX {name} ON public.{table} USING btree ({', '.join(fields)})"
                )
                existing = connection.execute(
                    sa.text(
                        "SELECT pg_get_indexdef(c.oid),i.indisvalid,i.indisready "
                        "FROM pg_class c LEFT JOIN pg_index i ON i.indexrelid=c.oid "
                        "JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE n.nspname='public' AND c.relname=:name"
                    ),
                    {"name": name},
                ).one_or_none()
                if existing:
                    if existing[0] != expected:
                        raise RuntimeError(f"GAME_DELETE_INDEX_NAME_CONFLICT: {name}")
                    if existing[1] and existing[2]:
                        continue
                    connection.execute(sa.text(f"DROP INDEX CONCURRENTLY public.{name}"))
                connection.execute(
                    sa.text(
                        f"CREATE INDEX CONCURRENTLY {name} ON public.{table} ({','.join(fields)})"
                    )
                )
        finally:
            connection.execute(
                sa.text("SELECT set_config('statement_timeout',:value,false)"),
                {"value": previous[0]},
            )
            connection.execute(
                sa.text("SELECT set_config('lock_timeout',:value,false)"), {"value": previous[1]}
            )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM public.game_deletion_operations)")):
        raise RuntimeError("GAME_DELETE_RECEIPTS_PREVENT_DOWNGRADE")
    with op.get_context().autocommit_block():
        previous = connection.execute(
            sa.text("SELECT current_setting('statement_timeout'),current_setting('lock_timeout')")
        ).one()
        try:
            connection.execute(sa.text("SET statement_timeout='120s'"))
            connection.execute(sa.text("SET lock_timeout='2s'"))
            for name, table, fields in reversed(indexes()):
                existing = connection.execute(
                    sa.text(
                        "SELECT pg_get_indexdef(c.oid) FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE n.nspname='public' AND c.relname=:name"
                    ),
                    {"name": name},
                ).one_or_none()
                expected = (
                    f"CREATE INDEX {name} ON public.{table} USING btree ({', '.join(fields)})"
                )
                if existing and existing[0] != expected:
                    raise RuntimeError(f"GAME_DELETE_INDEX_NAME_CONFLICT: {name}")
                connection.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS public.{name}"))
        finally:
            connection.execute(
                sa.text("SELECT set_config('statement_timeout',:v,false)"), {"v": previous[0]}
            )
            connection.execute(
                sa.text("SELECT set_config('lock_timeout',:v,false)"), {"v": previous[1]}
            )
