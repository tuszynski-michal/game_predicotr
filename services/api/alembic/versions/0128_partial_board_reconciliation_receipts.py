"""Durable per-board receipts for explicitly scoped reconciliation."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0128_partial_board_reconciliation_receipts"
down_revision = "0127_symbol_review_bulk_filter_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.create_table(
        "partial_board_reconciliation_receipts",
        sa.Column(
            "game_id",
            sa.Uuid(),
            sa.ForeignKey("public.games.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("preview_sha256", sa.String(64), primary_key=True),
        sa.Column("sequence_number", sa.BigInteger(), primary_key=True),
        sa.Column("guard_sha256", sa.String(64), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "preview_sha256 ~ '^[0-9a-f]{64}$' AND guard_sha256 ~ '^[0-9a-f]{64}$' "
            "AND sequence_number > 0",
            name="ck_partial_board_reconciliation_receipt_identity",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(result) = 'object'", name="ck_partial_board_reconciliation_receipt_result"
        ),
        schema="public",
    )


def downgrade() -> None:
    raise RuntimeError("RECONCILIATION_RECEIPTS_DOWNGRADE_UNSUPPORTED: durable results may exist")
