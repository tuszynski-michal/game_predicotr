"""Add v3 manual qualification tracking fully-unavailable cells.

Revision ID: 0120_fully_unavailable_cell_qualification
Revises: 0119_v12_game_data_v2_page_frame_grid_pairs
"""

from __future__ import annotations

from alembic import op

revision = "0120_fully_unavailable_cell_qualification"
down_revision = "0119_v12_game_data_v2_page_frame_grid_pairs"
branch_labels = None
depends_on = None

# The literal v1/v2-only version clause exactly as it exists today in both
# ck_recognized_boards_qualification and ck_guard_decisions_qualification
# (see models.py). Reusing it verbatim -- rather than re-deriving it from a
# parameterized template -- guarantees the "before" half of this migration
# matches the real, currently-applied constraint byte for byte.
_V1_V2_VERSION_CLAUSE = (
    "((geometry_qualification->>'version' = 'manual-geometry-qualification-v1' AND "
    "NOT (geometry_qualification ? 'includeInPartialGridTraining')) OR "
    "(geometry_qualification->>'version' = 'manual-geometry-qualification-v2' AND "
    "jsonb_typeof(geometry_qualification->'includeInPartialGridTraining') = 'boolean'))"
)
_V1_V2_V3_VERSION_CLAUSE = (
    "((geometry_qualification->>'version' = 'manual-geometry-qualification-v1' AND "
    "NOT (geometry_qualification ? 'includeInPartialGridTraining') AND "
    "NOT (geometry_qualification ? 'fullyUnavailableCellIndices')) OR "
    "(geometry_qualification->>'version' = 'manual-geometry-qualification-v2' AND "
    "jsonb_typeof(geometry_qualification->'includeInPartialGridTraining') = 'boolean' AND "
    "NOT (geometry_qualification ? 'fullyUnavailableCellIndices')) OR "
    "(geometry_qualification->>'version' = 'manual-geometry-qualification-v3' AND "
    "jsonb_typeof(geometry_qualification->'includeInPartialGridTraining') = 'boolean' AND "
    "jsonb_typeof(geometry_qualification->'fullyUnavailableCellIndices') = 'array'))"
)

_RECOGNIZED_BOARDS_V1_V2 = (
    "geometry_qualification IS NULL OR ((jsonb_typeof(geometry_qualification) = "
    "'object' AND " + _V1_V2_VERSION_CLAUSE + " AND "
    "geometry_qualification->>'completenessStatus' = completeness_status AND "
    "geometry_qualification->'unavailableCellIndices' = "
    "to_jsonb(unavailable_cell_indices) AND ((completeness_status = "
    "'pending_partial' AND geometry_qualification->'excludeFromGeometryTraining' "
    "= 'true'::jsonb AND geometry_qualification->>'exclusionReason' = "
    "'missing_pixels') OR (completeness_status = 'complete' AND "
    "COALESCE(geometry_qualification->'includeInPartialGridTraining', "
    "'false'::jsonb) = 'false'::jsonb AND "
    "((geometry_qualification->'excludeFromGeometryTraining' = 'true'::jsonb AND "
    "geometry_qualification->>'exclusionReason' = 'manual_exclusion') OR "
    "(geometry_qualification->'excludeFromGeometryTraining' = 'false'::jsonb AND "
    "geometry_qualification->'exclusionReason' = 'null'::jsonb))))) IS TRUE)"
)
_GUARD_DECISIONS_V1_V2 = (
    "geometry_qualification IS NULL OR ((jsonb_typeof(geometry_qualification) = "
    "'object' AND " + _V1_V2_VERSION_CLAUSE + " AND "
    "geometry_qualification->'unavailableCellIndices' = "
    "to_jsonb(unavailable_cell_indices) AND ((disposition = 'partial' AND "
    "geometry_qualification->>'completenessStatus' = 'pending_partial' AND "
    "geometry_qualification->'excludeFromGeometryTraining' = 'true'::jsonb AND "
    "geometry_qualification->>'exclusionReason' = 'missing_pixels') OR "
    "(disposition = 'corrected_full' AND "
    "geometry_qualification->>'completenessStatus' = 'complete' AND "
    "COALESCE(geometry_qualification->'includeInPartialGridTraining', "
    "'false'::jsonb) = 'false'::jsonb AND "
    "((geometry_qualification->'excludeFromGeometryTraining' = 'true'::jsonb AND "
    "geometry_qualification->>'exclusionReason' = 'manual_exclusion') OR "
    "(geometry_qualification->'excludeFromGeometryTraining' = 'false'::jsonb AND "
    "geometry_qualification->'exclusionReason' = 'null'::jsonb))))) IS TRUE)"
)

_RECOGNIZED_BOARDS_V1_V2_V3 = _RECOGNIZED_BOARDS_V1_V2.replace(
    _V1_V2_VERSION_CLAUSE, _V1_V2_V3_VERSION_CLAUSE
)
_GUARD_DECISIONS_V1_V2_V3 = _GUARD_DECISIONS_V1_V2.replace(
    _V1_V2_VERSION_CLAUSE, _V1_V2_V3_VERSION_CLAUSE
)

_TABLES = (
    ("recognized_boards", "ck_recognized_boards_qualification"),
    ("image_import_geometry_guard_decisions", "ck_guard_decisions_qualification"),
)


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    for (table, name), expression in zip(
        _TABLES,
        (_RECOGNIZED_BOARDS_V1_V2_V3, _GUARD_DECISIONS_V1_V2_V3),
        strict=True,
    ):
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, expression, postgresql_not_valid=True)


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM recognized_boards
                     WHERE geometry_qualification->>'version' =
                       'manual-geometry-qualification-v3')
             OR EXISTS (SELECT 1 FROM image_import_geometry_guard_decisions
                        WHERE geometry_qualification->>'version' =
                          'manual-geometry-qualification-v3') THEN
            RAISE EXCEPTION 'FULLY_UNAVAILABLE_CELL_QUALIFICATION_DOWNGRADE_HAS_DATA';
          END IF;
        END $$;
        """
    )
    for (table, name), expression in zip(
        _TABLES,
        (_RECOGNIZED_BOARDS_V1_V2, _GUARD_DECISIONS_V1_V2),
        strict=True,
    ):
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, expression)
