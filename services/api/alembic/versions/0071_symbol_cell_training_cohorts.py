"""Allow immutable training cohorts made from approved individual symbol cells.

Revision ID: 0071_symbol_cell_training_cohorts
Revises: 0070_symbol_cell_review_backfill_job
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0071_symbol_cell_training_cohorts"
down_revision: str | Sequence[str] | None = "0070_symbol_cell_review_backfill_job"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE verified_training_cohorts "
        "ADD COLUMN dataset_kind varchar(100) NOT NULL "
        "DEFAULT 'verified-training-cohort-v1'"
    )
    op.drop_constraint(
        "ck_verified_training_cohorts_counts",
        "verified_training_cohorts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_verified_training_cohorts_counts",
        "verified_training_cohorts",
        "resolved_layout_count > 0 AND cell_sample_count > 0 "
        "AND source_image_count > 0 AND pending_item_count >= 0 "
        "AND rejected_item_count >= 0 AND incomplete_item_count >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_verified_training_cohorts_counts",
        "verified_training_cohorts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_verified_training_cohorts_counts",
        "verified_training_cohorts",
        "resolved_layout_count > 0 "
        "AND cell_sample_count = resolved_layout_count * 15 "
        "AND source_image_count > 0 AND pending_item_count >= 0 "
        "AND rejected_item_count >= 0 AND incomplete_item_count >= 0",
    )
    op.drop_column("verified_training_cohorts", "dataset_kind")
