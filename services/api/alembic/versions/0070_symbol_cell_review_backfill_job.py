"""Add the durable symbol-cell review backfill job type.

Revision ID: 0070_symbol_cell_review_backfill_job
Revises: 0069_pending_sequence_ownership
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0070_symbol_cell_review_backfill_job"
down_revision: str | Sequence[str] | None = "0069_pending_sequence_ownership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'image_symbol_review_backfill'"
    )


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely. Keeping the unused value
    # preserves historical jobs and makes downgrade non-destructive.
    pass
