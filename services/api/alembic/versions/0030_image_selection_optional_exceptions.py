"""Allow unresolved image-selection groups to be skipped without a range.

Revision ID: 0030_image_selection_optional_exceptions
Revises: 0029_image_selection_missing_images
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_image_selection_optional_exceptions"
down_revision: str | Sequence[str] | None = "0029_image_selection_missing_images"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_image_selection_manual_decisions_range",
        "image_selection_manual_decisions",
        type_="check",
    )
    op.alter_column(
        "image_selection_manual_decisions",
        "range_start",
        existing_type=sa.BigInteger(),
        nullable=True,
    )
    op.alter_column(
        "image_selection_manual_decisions",
        "range_end",
        existing_type=sa.BigInteger(),
        nullable=True,
    )
    op.create_check_constraint(
        "ck_image_selection_manual_decisions_range",
        "image_selection_manual_decisions",
        "(range_start IS NULL AND range_end IS NULL) OR "
        "(range_start >= 1 AND range_end >= range_start)",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE image_selection_groups AS groups "
        "SET status = 'manual_required' "
        "FROM image_selection_manual_decisions AS decisions "
        "WHERE decisions.run_id = groups.run_id "
        "AND decisions.group_id = groups.id "
        "AND decisions.range_start IS NULL"
    )
    op.execute("DELETE FROM image_selection_manual_decisions WHERE range_start IS NULL")
    op.drop_constraint(
        "ck_image_selection_manual_decisions_range",
        "image_selection_manual_decisions",
        type_="check",
    )
    op.alter_column(
        "image_selection_manual_decisions",
        "range_start",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.alter_column(
        "image_selection_manual_decisions",
        "range_end",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.create_check_constraint(
        "ck_image_selection_manual_decisions_range",
        "image_selection_manual_decisions",
        "range_start >= 1 AND range_end >= range_start",
    )
