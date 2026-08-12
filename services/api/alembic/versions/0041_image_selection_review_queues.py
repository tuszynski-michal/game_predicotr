"""Add explicit range review and reversible group rejection states.

Revision ID: 0041_image_selection_review_queues
Revises: 0040_image_selection_duplicate_range_decisions
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041_image_selection_review_queues"
down_revision: str | Sequence[str] | None = "0040_image_selection_duplicate_range_decisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "image_selection_groups",
        sa.Column("rejection_origin_status", sa.String(length=40), nullable=True),
    )
    op.drop_constraint(
        "ck_image_selection_groups_status",
        "image_selection_groups",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_selection_groups_status",
        "image_selection_groups",
        "status IN ('collecting', 'auto_selected', 'manual_required', "
        "'manually_selected', 'missing_image', 'skipped_existing_range', "
        "'range_required', 'range_confirmed', 'skipped_unreadable', "
        "'rejected_by_user')",
    )
    op.create_check_constraint(
        "ck_image_selection_groups_rejection_origin",
        "image_selection_groups",
        "(status = 'rejected_by_user' AND rejection_origin_status IN "
        "('manual_required', 'range_required')) OR "
        "(status <> 'rejected_by_user' AND rejection_origin_status IS NULL)",
    )
    op.drop_index(
        "uq_image_selection_groups_selected_range",
        table_name="image_selection_groups",
    )
    op.create_index(
        "uq_image_selection_groups_selected_range",
        "image_selection_groups",
        ["run_id", "range_start", "range_end"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('auto_selected', 'manually_selected', 'missing_image', "
            "'range_confirmed') AND range_start IS NOT NULL"
        ),
    )
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
        "resolution IN ('selected_image', 'missing_image', 'duplicate_range', "
        "'range_confirmed', 'rejected_group', 'restored_group')",
    )
    op.create_check_constraint(
        "ck_image_selection_manual_decisions_candidate_resolution",
        "image_selection_manual_decisions",
        "(resolution IN ('selected_image', 'range_confirmed') "
        "AND candidate_id IS NOT NULL) OR "
        "(resolution IN ('missing_image', 'duplicate_range', 'rejected_group', "
        "'restored_group') AND candidate_id IS NULL)",
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM image_selection_manual_decisions WHERE resolution IN "
        "('range_confirmed', 'rejected_group', 'restored_group')"
    )
    op.execute(
        "UPDATE image_selection_groups SET status = CASE "
        "WHEN status = 'range_confirmed' THEN 'auto_selected' "
        "WHEN status IN ('range_required', 'rejected_by_user') THEN 'manual_required' "
        "WHEN status = 'skipped_unreadable' THEN 'skipped_existing_range' "
        "ELSE status END"
    )
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
    op.drop_index(
        "uq_image_selection_groups_selected_range",
        table_name="image_selection_groups",
    )
    op.create_index(
        "uq_image_selection_groups_selected_range",
        "image_selection_groups",
        ["run_id", "range_start", "range_end"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('auto_selected', 'manually_selected', 'missing_image') "
            "AND range_start IS NOT NULL"
        ),
    )
    op.drop_constraint(
        "ck_image_selection_groups_rejection_origin",
        "image_selection_groups",
        type_="check",
    )
    op.drop_constraint(
        "ck_image_selection_groups_status",
        "image_selection_groups",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_selection_groups_status",
        "image_selection_groups",
        "status IN ('collecting', 'auto_selected', 'manual_required', "
        "'manually_selected', 'missing_image', 'skipped_existing_range')",
    )
    op.drop_column("image_selection_groups", "rejection_origin_status")
