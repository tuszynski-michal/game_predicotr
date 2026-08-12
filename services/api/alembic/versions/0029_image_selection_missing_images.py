"""Allow image-selection ranges to continue without a representative JPEG.

Revision ID: 0029_image_selection_missing_images
Revises: 0028_image_selection_versioned_reruns
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_image_selection_missing_images"
down_revision: str | Sequence[str] | None = "0028_image_selection_versioned_reruns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(
        "uq_image_selection_groups_selected_range",
        table_name="image_selection_groups",
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
    op.add_column(
        "image_selection_manual_decisions",
        sa.Column(
            "resolution",
            sa.String(length=32),
            nullable=False,
            server_default="selected_image",
        ),
    )
    op.alter_column(
        "image_selection_manual_decisions",
        "candidate_id",
        existing_type=sa.Uuid(),
        nullable=True,
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
    op.alter_column(
        "image_selection_manual_decisions",
        "resolution",
        server_default=None,
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM image_selection_manual_decisions "
        "WHERE resolution = 'missing_image'"
    )
    op.execute(
        "UPDATE image_selection_groups SET status = 'manual_required' "
        "WHERE status = 'missing_image'"
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
    op.alter_column(
        "image_selection_manual_decisions",
        "candidate_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.drop_column("image_selection_manual_decisions", "resolution")
    op.drop_index(
        "uq_image_selection_groups_selected_range",
        table_name="image_selection_groups",
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
        "'manually_selected', 'skipped_existing_range')",
    )
    op.create_index(
        "uq_image_selection_groups_selected_range",
        "image_selection_groups",
        ["run_id", "range_start", "range_end"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('auto_selected', 'manually_selected') "
            "AND range_start IS NOT NULL"
        ),
    )
