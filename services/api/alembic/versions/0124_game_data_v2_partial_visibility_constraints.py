"""Align game_data_v2 partial-visibility checks with the public contract.

Revision ID: 0124_game_data_v2_partial_visibility_constraints
Revises: 0123_game_data_v2_qualification_constraints
"""

from __future__ import annotations

from alembic import op

revision = "0124_game_data_v2_partial_visibility_constraints"
down_revision = "0123_game_data_v2_qualification_constraints"
branch_labels = None
depends_on = None

_SCHEMA = "game_data_v2"
_CONSTRAINTS = (
    (
        "image_symbol_review_cells",
        "ck_image_symbol_review_cells_source",
        "assignment_source IN "
        "('model', 'human', 'board_decision', 'backfill', 'geometry_partial')",
    ),
    (
        "image_symbol_review_cells",
        "ck_image_symbol_review_cells_quality_issue",
        "quality_issue IS NULL OR quality_issue IN "
        "('grid_issue', 'blurry', 'unreadable', 'partial_visibility')",
    ),
    (
        "image_symbol_review_events",
        "ck_image_symbol_review_events_quality_issue",
        "(previous_quality_issue IS NULL OR previous_quality_issue IN "
        "('grid_issue', 'blurry', 'unreadable', 'partial_visibility')) AND "
        "(quality_issue IS NULL OR quality_issue IN "
        "('grid_issue', 'blurry', 'unreadable', 'partial_visibility'))",
    ),
)


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    for table, name, expression in _CONSTRAINTS:
        # Keep the contract on the partitioned parents. PostgreSQL propagates
        # it to every current and future game partition.
        op.drop_constraint(name, table, schema=_SCHEMA, type_="check")
        op.create_check_constraint(
            name, table, expression, schema=_SCHEMA, postgresql_not_valid=True
        )


def downgrade() -> None:
    raise RuntimeError(
        "GAME_DATA_V2_PARTIAL_VISIBILITY_CONSTRAINTS_DOWNGRADE_UNSUPPORTED: "
        "the database may contain partial-visibility review rows"
    )
