"""Add checksum-bound symbol catalog bootstrap runs.

Revision ID: 0023_symbol_bootstrap
Revises: 0022_dataset_quality
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_symbol_bootstrap"
down_revision: str | Sequence[str] | None = "0022_dataset_quality"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "symbol_bootstrap_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expected_symbol_count", sa.SmallInteger(), nullable=False),
        sa.Column("detected_cluster_count", sa.SmallInteger(), nullable=False),
        sa.Column("source_state_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("candidates", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("resolution", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "expected_symbol_count BETWEEN 1 AND 32767",
            name="ck_symbol_bootstrap_expected_count_range",
        ),
        sa.CheckConstraint(
            "detected_cluster_count > 0",
            name="ck_symbol_bootstrap_detected_count_positive",
        ),
        sa.CheckConstraint(
            "source_state_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_symbol_bootstrap_source_sha256",
        ),
        sa.CheckConstraint(
            "status IN ('ready', 'conflict', 'applied')",
            name="ck_symbol_bootstrap_status",
        ),
        sa.CheckConstraint(
            "(status = 'applied' AND resolution IS NOT NULL AND applied_at IS NOT NULL) "
            "OR (status <> 'applied' AND resolution IS NULL AND applied_at IS NULL)",
            name="ck_symbol_bootstrap_applied_state",
        ),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
            name="fk_symbol_bootstrap_game",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_symbol_bootstrap_runs"),
        sa.UniqueConstraint(
            "game_id",
            "source_state_sha256",
            "expected_symbol_count",
            name="uq_symbol_bootstrap_source_expectation",
        ),
    )
    op.create_index(
        "ix_symbol_bootstrap_game_created",
        "symbol_bootstrap_runs",
        ["game_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_symbol_bootstrap_game_created",
        table_name="symbol_bootstrap_runs",
    )
    op.drop_table("symbol_bootstrap_runs")
