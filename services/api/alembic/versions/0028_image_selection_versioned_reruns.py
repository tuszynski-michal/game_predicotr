"""Allow one immutable browser selection to be processed by selector versions.

Revision ID: 0028_image_selection_versioned_reruns
Revises: 0027_image_selection_manual_decisions
Create Date: 2026-08-03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0028_image_selection_versioned_reruns"
down_revision: str | Sequence[str] | None = "0027_image_selection_manual_decisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_image_selection_runs_source_selection_id",
        "image_selection_runs",
        type_="unique",
    )
    op.create_index(
        "ix_image_selection_runs_source_selection_id",
        "image_selection_runs",
        ["source_selection_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_image_selection_runs_source_selection_id",
        table_name="image_selection_runs",
    )
    op.create_unique_constraint(
        "uq_image_selection_runs_source_selection_id",
        "image_selection_runs",
        ["source_selection_id"],
    )
