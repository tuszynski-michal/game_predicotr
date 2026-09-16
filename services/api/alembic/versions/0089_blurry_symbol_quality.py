"""Allow recognized blurry crops to remain approved but non-training.

Revision ID: 0089_blurry_symbol_quality
Revises: 0088_symbol_review_game_sequence_index
Create Date: 2026-09-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0089_blurry_symbol_quality"
down_revision: str | None = "0088_symbol_review_game_sequence_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_check_constraint_without_table_scan(
    table: str,
    name: str,
    condition: str,
) -> None:
    replacement = f"{name}_replacement"
    op.create_check_constraint(
        replacement,
        table,
        condition,
        postgresql_not_valid=True,
    )
    op.drop_constraint(name, table, type_="check")
    op.execute(f'ALTER TABLE "{table}" RENAME CONSTRAINT "{replacement}" TO "{name}"')


def upgrade() -> None:
    _replace_check_constraint_without_table_scan(
        "image_symbol_review_cells",
        "ck_image_symbol_review_cells_quality_issue",
        "quality_issue IS NULL OR quality_issue IN ('grid_issue', 'blurry', 'unreadable')",
    )

    _replace_check_constraint_without_table_scan(
        "image_symbol_review_events",
        "ck_image_symbol_review_events_action",
        "action IN ('approve', 'reassign', 'mark_grid_issue', 'mark_blurry', "
        "'mark_unreadable', 'board_synchronized', 'geometry_invalidated')",
    )
    _replace_check_constraint_without_table_scan(
        "image_symbol_review_events",
        "ck_image_symbol_review_events_quality_issue",
        "(previous_quality_issue IS NULL OR previous_quality_issue IN "
        "('grid_issue', 'blurry', 'unreadable')) AND "
        "(quality_issue IS NULL OR quality_issue IN "
        "('grid_issue', 'blurry', 'unreadable'))",
    )

    _replace_check_constraint_without_table_scan(
        "image_symbol_review_bulk_operations",
        "ck_image_symbol_review_bulk_operations_action",
        "action IN ('approve', 'reassign', 'mark_grid_issue', 'mark_blurry', "
        "'mark_unreadable')",
    )


def downgrade() -> None:
    op.execute("LOCK TABLE image_symbol_review_cells IN SHARE ROW EXCLUSIVE MODE")
    op.execute("LOCK TABLE image_symbol_review_events IN SHARE ROW EXCLUSIVE MODE")
    op.execute("LOCK TABLE image_symbol_review_bulk_operations IN SHARE ROW EXCLUSIVE MODE")
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM image_symbol_review_cells WHERE quality_issue = 'blurry'
          ) OR EXISTS (
            SELECT 1 FROM image_symbol_review_events
            WHERE quality_issue = 'blurry'
               OR previous_quality_issue = 'blurry'
               OR action = 'mark_blurry'
          ) OR EXISTS (
            SELECT 1 FROM image_symbol_review_bulk_operations WHERE action = 'mark_blurry'
          ) THEN
            RAISE EXCEPTION 'Cannot downgrade while blurry symbol-review data exists';
          END IF;
        END $$;
        """
    )

    _replace_check_constraint_without_table_scan(
        "image_symbol_review_bulk_operations",
        "ck_image_symbol_review_bulk_operations_action",
        "action IN ('approve', 'reassign', 'mark_grid_issue', 'mark_unreadable')",
    )

    _replace_check_constraint_without_table_scan(
        "image_symbol_review_events",
        "ck_image_symbol_review_events_quality_issue",
        "(previous_quality_issue IS NULL OR previous_quality_issue IN "
        "('grid_issue', 'unreadable')) AND "
        "(quality_issue IS NULL OR quality_issue IN ('grid_issue', 'unreadable'))",
    )
    _replace_check_constraint_without_table_scan(
        "image_symbol_review_events",
        "ck_image_symbol_review_events_action",
        "action IN ('approve', 'reassign', 'mark_grid_issue', 'mark_unreadable', "
        "'board_synchronized', 'geometry_invalidated')",
    )

    _replace_check_constraint_without_table_scan(
        "image_symbol_review_cells",
        "ck_image_symbol_review_cells_quality_issue",
        "quality_issue IS NULL OR quality_issue IN ('grid_issue', 'unreadable')",
    )
