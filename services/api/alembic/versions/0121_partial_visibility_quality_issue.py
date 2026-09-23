"""Allow the new partial_visibility quality issue and geometry_partial source.

Revision ID: 0121_partial_visibility_quality_issue
Revises: 0120_fully_unavailable_cell_qualification
"""

from __future__ import annotations

from alembic import op

revision = "0121_partial_visibility_quality_issue"
down_revision = "0120_fully_unavailable_cell_qualification"
branch_labels = None
depends_on = None

_TABLE = "image_symbol_review_cells"
_EVENTS_TABLE = "image_symbol_review_events"
_SOURCE_CONSTRAINT = "ck_image_symbol_review_cells_source"
_QUALITY_CONSTRAINT = "ck_image_symbol_review_cells_quality_issue"
_EVENTS_QUALITY_CONSTRAINT = "ck_image_symbol_review_events_quality_issue"

_OLD_SOURCE_EXPRESSION = "assignment_source IN ('model', 'human', 'board_decision', 'backfill')"
_NEW_SOURCE_EXPRESSION = (
    "assignment_source IN ('model', 'human', 'board_decision', 'backfill', 'geometry_partial')"
)
_OLD_QUALITY_EXPRESSION = (
    "quality_issue IS NULL OR quality_issue IN ('grid_issue', 'blurry', 'unreadable')"
)
_NEW_QUALITY_EXPRESSION = (
    "quality_issue IS NULL OR quality_issue IN "
    "('grid_issue', 'blurry', 'unreadable', 'partial_visibility')"
)
_OLD_EVENTS_QUALITY_EXPRESSION = (
    "(previous_quality_issue IS NULL OR "
    "previous_quality_issue IN ('grid_issue', 'blurry', 'unreadable')) AND "
    "(quality_issue IS NULL OR quality_issue IN ('grid_issue', 'blurry', 'unreadable'))"
)
_NEW_EVENTS_QUALITY_EXPRESSION = (
    "(previous_quality_issue IS NULL OR previous_quality_issue IN "
    "('grid_issue', 'blurry', 'unreadable', 'partial_visibility')) AND "
    "(quality_issue IS NULL OR quality_issue IN "
    "('grid_issue', 'blurry', 'unreadable', 'partial_visibility'))"
)


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.drop_constraint(_SOURCE_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_SOURCE_CONSTRAINT, _TABLE, _NEW_SOURCE_EXPRESSION)
    op.drop_constraint(_QUALITY_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_QUALITY_CONSTRAINT, _TABLE, _NEW_QUALITY_EXPRESSION)
    op.drop_constraint(_EVENTS_QUALITY_CONSTRAINT, _EVENTS_TABLE, type_="check")
    op.create_check_constraint(
        _EVENTS_QUALITY_CONSTRAINT, _EVENTS_TABLE, _NEW_EVENTS_QUALITY_EXPRESSION
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM image_symbol_review_cells
                     WHERE assignment_source = 'geometry_partial'
                        OR quality_issue = 'partial_visibility')
             OR EXISTS (SELECT 1 FROM image_symbol_review_events
                        WHERE quality_issue = 'partial_visibility'
                           OR previous_quality_issue = 'partial_visibility') THEN
            RAISE EXCEPTION 'PARTIAL_VISIBILITY_QUALITY_ISSUE_DOWNGRADE_HAS_DATA';
          END IF;
        END $$;
        """
    )
    op.drop_constraint(_EVENTS_QUALITY_CONSTRAINT, _EVENTS_TABLE, type_="check")
    op.create_check_constraint(
        _EVENTS_QUALITY_CONSTRAINT, _EVENTS_TABLE, _OLD_EVENTS_QUALITY_EXPRESSION
    )
    op.drop_constraint(_QUALITY_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_QUALITY_CONSTRAINT, _TABLE, _OLD_QUALITY_EXPRESSION)
    op.drop_constraint(_SOURCE_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_SOURCE_CONSTRAINT, _TABLE, _OLD_SOURCE_EXPRESSION)
