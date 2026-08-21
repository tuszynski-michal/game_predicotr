"""Add the explicit pending-only symbol recalculation job type."""

from collections.abc import Sequence

from alembic import op

revision: str = "0047_pending_symbol_reinference_job"
down_revision: str | Sequence[str] | None = "0046_image_symbol_prediction_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'image_symbol_reinference'")
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'image_grid_reinference'")


def downgrade() -> None:
    # PostgreSQL enums cannot remove a value safely while jobs may reference it.
    # The application stops emitting this type after downgrade; the value is
    # intentionally retained for historical rows.
    pass
