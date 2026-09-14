"""Add v2 manual qualification for separate partial-grid training.

Revision ID: 0111_partial_grid_training_qualification
Revises: 0110_game_partition_lifecycle
"""

from __future__ import annotations

from alembic import op

revision = "0111_partial_grid_training_qualification"
down_revision = "0110_game_partition_lifecycle"
branch_labels = None
depends_on = None


def _qualification_expression(*, guard: bool) -> str:
    status = "'pending_partial'" if not guard else "'partial'"
    complete = "'complete'" if not guard else "'corrected_full'"
    status_column = "completeness_status" if not guard else "disposition"
    status_match = (
        "geometry_qualification->>'completenessStatus' = completeness_status AND "
        if not guard
        else ""
    )
    return (
        "geometry_qualification IS NULL OR ((jsonb_typeof(geometry_qualification) = 'object' AND "
        "((geometry_qualification->>'version' = 'manual-geometry-qualification-v1' AND "
        "NOT (geometry_qualification ? 'includeInPartialGridTraining')) OR "
        "(geometry_qualification->>'version' = 'manual-geometry-qualification-v2' AND "
        "jsonb_typeof(geometry_qualification->'includeInPartialGridTraining') = 'boolean')) AND "
        + status_match
        + "geometry_qualification->'unavailableCellIndices' = "
        "to_jsonb(unavailable_cell_indices) AND " + f"(({status_column} = {status} AND "
        "geometry_qualification->>'completenessStatus' = 'pending_partial' AND "
        "geometry_qualification->'excludeFromGeometryTraining' = 'true'::jsonb AND "
        "geometry_qualification->>'exclusionReason' = 'missing_pixels') OR "
        + f"({status_column} = {complete} AND "
        "geometry_qualification->>'completenessStatus' = 'complete' AND "
        "COALESCE(geometry_qualification->'includeInPartialGridTraining', 'false'::jsonb) = "
        "'false'::jsonb AND ((geometry_qualification->'excludeFromGeometryTraining' = "
        "'true'::jsonb AND geometry_qualification->>'exclusionReason' = 'manual_exclusion') OR "
        "(geometry_qualification->'excludeFromGeometryTraining' = 'false'::jsonb AND "
        "geometry_qualification->'exclusionReason' = 'null'::jsonb))))) IS TRUE)"
    )


def _v1_expression(*, guard: bool) -> str:
    status = "'pending_partial'" if not guard else "'partial'"
    complete = "'complete'" if not guard else "'corrected_full'"
    status_column = "completeness_status" if not guard else "disposition"
    status_match = (
        "geometry_qualification->>'completenessStatus' = completeness_status AND "
        if not guard
        else ""
    )
    return (
        "geometry_qualification IS NULL OR ((jsonb_typeof(geometry_qualification) = 'object' AND "
        "geometry_qualification->>'version' = 'manual-geometry-qualification-v1' AND "
        + status_match
        + "geometry_qualification->'unavailableCellIndices' = "
        "to_jsonb(unavailable_cell_indices) AND "
        + f"(({status_column} = {status} AND geometry_qualification->>'completenessStatus' = "
        "'pending_partial' AND geometry_qualification->'excludeFromGeometryTraining' = "
        "'true'::jsonb AND geometry_qualification->>'exclusionReason' = 'missing_pixels') OR "
        + f"({status_column} = {complete} AND geometry_qualification->>'completenessStatus' = "
        "'complete' AND ((geometry_qualification->'excludeFromGeometryTraining' = 'true'::jsonb "
        "AND geometry_qualification->>'exclusionReason' = 'manual_exclusion') OR "
        "(geometry_qualification->'excludeFromGeometryTraining' = 'false'::jsonb AND "
        "geometry_qualification->'exclusionReason' = 'null'::jsonb))))) IS TRUE)"
    )


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    for table, name, guard in (
        ("recognized_boards", "ck_recognized_boards_qualification", False),
        ("image_import_geometry_guard_decisions", "ck_guard_decisions_qualification", True),
    ):
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(
            name, table, _qualification_expression(guard=guard), postgresql_not_valid=True
        )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM image_page_geometry_overrides
            WHERE slot_qualifications @?
              '$[*] ? (@.version == "manual-geometry-qualification-v2")'
          )
             OR EXISTS (SELECT 1 FROM recognized_boards
                        WHERE geometry_qualification->>'version' =
                          'manual-geometry-qualification-v2')
             OR EXISTS (SELECT 1 FROM image_import_geometry_guard_decisions
                        WHERE geometry_qualification->>'version' =
                          'manual-geometry-qualification-v2') THEN
            RAISE EXCEPTION 'PARTIAL_GRID_TRAINING_QUALIFICATION_DOWNGRADE_HAS_DATA';
          END IF;
        END $$;
        """
    )
    for table, name, guard in (
        ("recognized_boards", "ck_recognized_boards_qualification", False),
        ("image_import_geometry_guard_decisions", "ck_guard_decisions_qualification", True),
    ):
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, _v1_expression(guard=guard))
