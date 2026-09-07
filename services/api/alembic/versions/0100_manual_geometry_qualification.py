"""Persist versioned manual completeness decisions without rewriting old revisions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0100_manual_geometry_qualification"
down_revision: str | Sequence[str] | None = "0099_legacy_game_operational_cleanup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

QUALIFICATION_CONSTRAINTS = (
    (
        "image_page_geometry_overrides",
        "ck_page_override_slot_qualifications",
        "slot_qualifications IS NULL OR (CASE WHEN jsonb_typeof(slot_qualifications) "
        "= 'array' THEN jsonb_array_length(slot_qualifications) = "
        "jsonb_array_length(final_quads) ELSE false END)",
    ),
    (
        "recognized_boards",
        "ck_recognized_boards_qualification",
        "geometry_qualification IS NULL OR ((jsonb_typeof(geometry_qualification) = "
        "'object' AND geometry_qualification->>'version' = "
        "'manual-geometry-qualification-v1' AND "
        "geometry_qualification->>'completenessStatus' = completeness_status AND "
        "geometry_qualification->'unavailableCellIndices' = "
        "to_jsonb(unavailable_cell_indices) AND ((completeness_status = "
        "'pending_partial' AND geometry_qualification->'excludeFromGeometryTraining' "
        "= 'true'::jsonb AND geometry_qualification->>'exclusionReason' = "
        "'missing_pixels') OR (completeness_status = 'complete' AND "
        "((geometry_qualification->'excludeFromGeometryTraining' = 'true'::jsonb AND "
        "geometry_qualification->>'exclusionReason' = 'manual_exclusion') OR "
        "(geometry_qualification->'excludeFromGeometryTraining' = 'false'::jsonb AND "
        "geometry_qualification->'exclusionReason' = 'null'::jsonb))))) IS TRUE)",
    ),
    (
        "image_import_geometry_guard_decisions",
        "ck_guard_decisions_qualification",
        "geometry_qualification IS NULL OR ((jsonb_typeof(geometry_qualification) = "
        "'object' AND geometry_qualification->>'version' = "
        "'manual-geometry-qualification-v1' AND "
        "geometry_qualification->'unavailableCellIndices' = "
        "to_jsonb(unavailable_cell_indices) AND ((disposition = 'partial' AND "
        "geometry_qualification->>'completenessStatus' = 'pending_partial' AND "
        "geometry_qualification->'excludeFromGeometryTraining' = 'true'::jsonb AND "
        "geometry_qualification->>'exclusionReason' = 'missing_pixels') OR "
        "(disposition = 'corrected_full' AND "
        "geometry_qualification->>'completenessStatus' = 'complete' AND "
        "((geometry_qualification->'excludeFromGeometryTraining' = 'true'::jsonb AND "
        "geometry_qualification->>'exclusionReason' = 'manual_exclusion') OR "
        "(geometry_qualification->'excludeFromGeometryTraining' = 'false'::jsonb AND "
        "geometry_qualification->'exclusionReason' = 'null'::jsonb))))) IS TRUE)",
    ),
)


def _completeness(maximum: int) -> str:
    return (
        "(completeness_status = 'complete' AND cardinality(unavailable_cell_indices) = 0) "
        "OR (completeness_status = 'pending_partial' "
        f"AND cardinality(unavailable_cell_indices) BETWEEN 1 AND {maximum} "
        "AND unavailable_cell_indices <@ "
        "ARRAY[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14]::smallint[])"
    )


def _disposition(maximum: int) -> str:
    return (
        "(disposition = 'corrected_full' AND symbol_grid_quad IS NOT NULL "
        "AND jsonb_typeof(symbol_grid_quad) = 'array' "
        "AND jsonb_array_length(symbol_grid_quad) = 4 "
        "AND cardinality(unavailable_cell_indices) = 0) OR "
        "(disposition = 'partial' AND symbol_grid_quad IS NOT NULL "
        "AND jsonb_typeof(symbol_grid_quad) = 'array' "
        "AND jsonb_array_length(symbol_grid_quad) = 4 "
        f"AND cardinality(unavailable_cell_indices) BETWEEN 1 AND {maximum} "
        "AND unavailable_cell_indices <@ "
        "ARRAY[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14]::smallint[]) OR "
        "(disposition = 'rejected' AND symbol_grid_quad IS NULL "
        "AND cardinality(unavailable_cell_indices) = 0 AND length(btrim(reason)) > 0)"
    )


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    # Nullable additive columns: historical decisions and checksums stay untouched.
    op.add_column(
        "image_page_geometry_overrides",
        sa.Column("slot_qualifications", postgresql.JSONB(none_as_null=True), nullable=True),
    )
    for table in ("recognized_boards", "image_import_geometry_guard_decisions"):
        op.add_column(
            table,
            sa.Column("geometry_qualification", postgresql.JSONB(none_as_null=True), nullable=True),
        )
    op.drop_constraint("ck_recognized_boards_completeness", "recognized_boards", type_="check")
    op.create_check_constraint(
        "ck_recognized_boards_completeness",
        "recognized_boards",
        _completeness(15),
        postgresql_not_valid=True,
    )
    op.drop_constraint(
        "ck_image_import_guard_decisions_disposition",
        "image_import_geometry_guard_decisions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_import_guard_decisions_disposition",
        "image_import_geometry_guard_decisions",
        _disposition(15),
        postgresql_not_valid=True,
    )
    for table, name, expression in QUALIFICATION_CONSTRAINTS:
        op.create_check_constraint(name, table, expression, postgresql_not_valid=True)


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    # Prevent a concurrent writer from adding protected decisions after the check.
    op.execute(
        "LOCK TABLE image_page_geometry_overrides, recognized_boards, "
        "image_import_geometry_guard_decisions, image_source_geometry_revisions "
        "IN ACCESS EXCLUSIVE MODE"
    )
    # Fail before dropping metadata: operator must explicitly resolve new decisions first.
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM image_page_geometry_overrides
                     WHERE slot_qualifications IS NOT NULL)
             OR EXISTS (SELECT 1 FROM recognized_boards WHERE geometry_qualification IS NOT NULL
                        OR cardinality(unavailable_cell_indices) = 15)
             OR EXISTS (SELECT 1 FROM image_import_geometry_guard_decisions
                        WHERE geometry_qualification IS NOT NULL
                        OR cardinality(unavailable_cell_indices) = 15)
             OR EXISTS (SELECT 1 FROM image_source_geometry_revisions
                        WHERE board_geometries @? '$[*].geometryQualification') THEN
            RAISE EXCEPTION 'MANUAL_GEOMETRY_QUALIFICATION_DOWNGRADE_HAS_DATA';
          END IF;
        END $$;
    """)
    op.drop_constraint("ck_recognized_boards_completeness", "recognized_boards", type_="check")
    op.create_check_constraint(
        "ck_recognized_boards_completeness", "recognized_boards", _completeness(14)
    )
    op.drop_constraint(
        "ck_image_import_guard_decisions_disposition",
        "image_import_geometry_guard_decisions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_import_guard_decisions_disposition",
        "image_import_geometry_guard_decisions",
        _disposition(14),
    )
    for table, name, _expression in QUALIFICATION_CONSTRAINTS:
        op.drop_constraint(name, table, type_="check")
    op.drop_column("image_import_geometry_guard_decisions", "geometry_qualification")
    op.drop_column("recognized_boards", "geometry_qualification")
    op.drop_column("image_page_geometry_overrides", "slot_qualifications")
