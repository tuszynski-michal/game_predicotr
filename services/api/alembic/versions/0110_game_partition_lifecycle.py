"""Durable checkpoint for per-game partition lifecycle operations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0110_game_partition_lifecycle"
down_revision: str | Sequence[str] | None = "0109_exact_symbol_review_counts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.create_table(
        "game_storage_lifecycle_operations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("operation_kind", sa.String(length=20), nullable=False),
        sa.Column("manifest_version", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("next_table_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "completed_tables",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("failure_message", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("operation_kind IN ('provision', 'delete')"),
        sa.CheckConstraint("status IN ('running', 'blocked', 'done')"),
        sa.CheckConstraint("next_table_index >= 0"),
        schema="public",
    )
    op.create_index(
        "uq_game_storage_lifecycle_active",
        "game_storage_lifecycle_operations",
        ["game_id", "operation_kind"],
        unique=True,
        schema="public",
        postgresql_where=sa.text("status <> 'done'"),
    )
    op.create_index(
        "ix_game_storage_lifecycle_game_created",
        "game_storage_lifecycle_operations",
        ["game_id", "created_at"],
        schema="public",
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.execute("LOCK TABLE public.game_storage_lifecycle_operations IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM public.game_storage_lifecycle_operations LIMIT 1) THEN
            RAISE EXCEPTION 'GAME_STORAGE_LIFECYCLE_DOWNGRADE_NOT_EMPTY';
        END IF;
    END $guard$""")
    op.drop_table("game_storage_lifecycle_operations", schema="public")
