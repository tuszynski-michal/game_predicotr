"""Add append-only cleanup operation receipts.

Revision ID: 0024_cleanup_operations
Revises: 0023_symbol_bootstrap
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_cleanup_operations"
down_revision: str | Sequence[str] | None = "0023_symbol_bootstrap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cleanup_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_type", sa.String(length=30), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("preview_token", sa.String(length=64), nullable=False),
        sa.Column(
            "result_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "operation_type IN ('mobile_release', 'game_layout_data')",
            name="ck_cleanup_operations_type",
        ),
        sa.CheckConstraint(
            "preview_token ~ '^[0-9a-f]{64}$'",
            name="ck_cleanup_operations_preview_token",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_cleanup_operations"),
        sa.UniqueConstraint(
            "operation_type",
            "target_id",
            "preview_token",
            name="uq_cleanup_operations_target_preview",
        ),
    )
    op.create_index(
        "ix_cleanup_operations_target_created",
        "cleanup_operations",
        ["operation_type", "target_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cleanup_operations_target_created",
        table_name="cleanup_operations",
    )
    op.drop_table("cleanup_operations")
