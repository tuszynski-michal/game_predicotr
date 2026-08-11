"""Audit manual image-selection duplicate-range decisions.

Revision ID: 0040_image_selection_duplicate_range_decisions
Revises: 0039_grid_calibration_profiles
Create Date: 2026-08-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0040_image_selection_duplicate_range_decisions"
down_revision: str | Sequence[str] | None = "0039_grid_calibration_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_image_selection_manual_decisions_candidate_resolution",
        "image_selection_manual_decisions",
        type_="check",
    )
    op.drop_constraint(
        "ck_image_selection_manual_decisions_resolution",
        "image_selection_manual_decisions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_selection_manual_decisions_resolution",
        "image_selection_manual_decisions",
        "resolution IN ('selected_image', 'missing_image', 'duplicate_range')",
    )
    op.create_check_constraint(
        "ck_image_selection_manual_decisions_candidate_resolution",
        "image_selection_manual_decisions",
        "(resolution = 'selected_image' AND candidate_id IS NOT NULL) OR "
        "(resolution IN ('missing_image', 'duplicate_range') AND candidate_id IS NULL)",
    )


def downgrade() -> None:
    op.execute("DELETE FROM image_selection_manual_decisions WHERE resolution = 'duplicate_range'")
    op.drop_constraint(
        "ck_image_selection_manual_decisions_candidate_resolution",
        "image_selection_manual_decisions",
        type_="check",
    )
    op.drop_constraint(
        "ck_image_selection_manual_decisions_resolution",
        "image_selection_manual_decisions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_selection_manual_decisions_resolution",
        "image_selection_manual_decisions",
        "resolution IN ('selected_image', 'missing_image')",
    )
    op.create_check_constraint(
        "ck_image_selection_manual_decisions_candidate_resolution",
        "image_selection_manual_decisions",
        "(resolution = 'selected_image' AND candidate_id IS NOT NULL) OR "
        "(resolution = 'missing_image' AND candidate_id IS NULL)",
    )
