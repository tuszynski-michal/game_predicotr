"""Track whether a board-search projection is ready for a game.

Revision ID: 0058_board_search_projection_state
Revises: 0057_board_search_projection
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0058_board_search_projection_state"
down_revision: str | Sequence[str] | None = "0057_board_search_projection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "image_board_search_projection_states",
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("candidate_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("document_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("skipped_review_item_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("failure_message", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('rebuilding', 'ready', 'failed')",
            name="ck_image_board_search_projection_states_status",
        ),
        sa.CheckConstraint(
            "candidate_count >= 0 AND document_count >= 0 AND skipped_review_item_count >= 0",
            name="ck_image_board_search_projection_states_counts",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("game_id", name="pk_image_board_search_projection_states"),
    )


def downgrade() -> None:
    op.drop_table("image_board_search_projection_states")
