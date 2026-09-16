"""Add durable receipts for the pinned legacy-game operational cleanup.

Revision ID: 0099_legacy_game_operational_cleanup
Revises: 0098_legacy_board_search_archive
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0099_legacy_game_operational_cleanup"
down_revision: str | Sequence[str] | None = "0098_legacy_board_search_archive"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "legacy_game_operational_cleanup_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("legacy_game_id", sa.Uuid(), nullable=False),
        sa.Column("protected_game_id", sa.Uuid(), nullable=False),
        sa.Column("preview_fingerprint", sa.String(64), nullable=False),
        sa.Column("schema_fingerprint", sa.String(64), nullable=False),
        sa.Column("archive_fingerprint", sa.String(64), nullable=False),
        sa.Column("confirmation_target", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("initial_counts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("deleted_counts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "managed_artifact_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("failure_code", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('executing', 'completed', 'failed')",
            name="ck_legacy_game_operational_cleanup_receipts_status",
        ),
        sa.CheckConstraint(
            "preview_fingerprint ~ '^[0-9a-f]{64}$' "
            "AND schema_fingerprint ~ '^[0-9a-f]{64}$' "
            "AND archive_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_legacy_game_operational_cleanup_receipts_fingerprints",
        ),
        sa.ForeignKeyConstraint(["legacy_game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["protected_game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "legacy_game_id",
            name="uq_legacy_game_operational_cleanup_receipts_game",
        ),
    )


def downgrade() -> None:
    op.drop_table("legacy_game_operational_cleanup_receipts")
