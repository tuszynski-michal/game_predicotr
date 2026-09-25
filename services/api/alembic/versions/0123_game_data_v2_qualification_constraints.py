"""Align game_data_v2 qualification checks with the public v3 contract.

Revision ID: 0123_game_data_v2_qualification_constraints
Revises: 0122_board_import_coverage_indexes
"""

from __future__ import annotations

from alembic import op

revision = "0123_game_data_v2_qualification_constraints"
down_revision = "0122_board_import_coverage_indexes"
branch_labels = None
depends_on = None

_SCHEMA = "game_data_v2"

# game_data_v2 was created before 0111 and 0120.  Those migrations updated
# only public.*, leaving the partitioned V2 parents (and their partitions)
# with the v1-only checks.  Keep this migration self-contained: Alembic must
# be able to apply it to any database that has reached 0122.
_VERSION_CLAUSE = (
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

_RECOGNIZED_BOARDS_EXPRESSION = (
    "geometry_qualification IS NULL OR ((jsonb_typeof(geometry_qualification) = "
    "'object' AND "
    + _VERSION_CLAUSE
    + " AND geometry_qualification->>'completenessStatus' = completeness_status AND "
    "geometry_qualification->'unavailableCellIndices' = to_jsonb(unavailable_cell_indices) "
    "AND ((completeness_status = 'pending_partial' AND "
    "geometry_qualification->'excludeFromGeometryTraining' = 'true'::jsonb AND "
    "geometry_qualification->>'exclusionReason' = 'missing_pixels') OR "
    "(completeness_status = 'complete' AND "
    "COALESCE(geometry_qualification->'includeInPartialGridTraining', 'false'::jsonb) = "
    "'false'::jsonb AND ((geometry_qualification->'excludeFromGeometryTraining' = "
    "'true'::jsonb AND geometry_qualification->>'exclusionReason' = 'manual_exclusion') OR "
    "(geometry_qualification->'excludeFromGeometryTraining' = 'false'::jsonb AND "
    "geometry_qualification->'exclusionReason' = 'null'::jsonb))))) IS TRUE)"
)

_GUARD_DECISIONS_EXPRESSION = (
    "geometry_qualification IS NULL OR ((jsonb_typeof(geometry_qualification) = "
    "'object' AND "
    + _VERSION_CLAUSE
    + " AND geometry_qualification->'unavailableCellIndices' = "
    "to_jsonb(unavailable_cell_indices) AND ((disposition = 'partial' AND "
    "geometry_qualification->>'completenessStatus' = 'pending_partial' AND "
    "geometry_qualification->'excludeFromGeometryTraining' = 'true'::jsonb AND "
    "geometry_qualification->>'exclusionReason' = 'missing_pixels') OR "
    "(disposition = 'corrected_full' AND "
    "geometry_qualification->>'completenessStatus' = 'complete' AND "
    "COALESCE(geometry_qualification->'includeInPartialGridTraining', 'false'::jsonb) = "
    "'false'::jsonb AND ((geometry_qualification->'excludeFromGeometryTraining' = "
    "'true'::jsonb AND geometry_qualification->>'exclusionReason' = 'manual_exclusion') OR "
    "(geometry_qualification->'excludeFromGeometryTraining' = 'false'::jsonb AND "
    "geometry_qualification->'exclusionReason' = 'null'::jsonb))))) IS TRUE)"
)

_CONSTRAINTS = (
    ("recognized_boards", "ck_recognized_boards_qualification", _RECOGNIZED_BOARDS_EXPRESSION),
    (
        "image_import_geometry_guard_decisions",
        "ck_guard_decisions_qualification",
        _GUARD_DECISIONS_EXPRESSION,
    ),
)


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    for table, name, expression in _CONSTRAINTS:
        # These are partitioned parents. PostgreSQL propagates a parent CHECK
        # replacement to every existing partition and to partitions created
        # later, so do not apply untracked DDL to individual game tables.
        op.drop_constraint(name, table, schema=_SCHEMA, type_="check")
        op.create_check_constraint(
            name, table, expression, schema=_SCHEMA, postgresql_not_valid=True
        )


def downgrade() -> None:
    raise RuntimeError(
        "GAME_DATA_V2_QUALIFICATION_CONSTRAINTS_DOWNGRADE_UNSUPPORTED: "
        "the database may contain v2 or v3 qualification rows"
    )
