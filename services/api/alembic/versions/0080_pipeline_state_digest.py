"""Enable server-side SHA-256 for bounded pipeline-state previews.

Revision ID: 0080_pipeline_state_digest
Revises: 0079_pipeline_state_compaction
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0080_pipeline_state_digest"
down_revision: str | Sequence[str] | None = "0079_pipeline_state_compaction"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")


def downgrade() -> None:
    # Keeping the extension avoids breaking later consumers that may share it.
    pass
