"""Add append-only manual image-selection decisions.

Revision ID: 0027_image_selection_manual_decisions
Revises: 0026_merge_v03_v04_heads
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_image_selection_manual_decisions"
down_revision: str | Sequence[str] | None = "0026_merge_v03_v04_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Alembic creates version_num as VARCHAR(32) by default. This revision ID is
    # longer, so widen the bookkeeping column before Alembic records the new
    # head at the end of this transaction.
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=128),
        existing_nullable=False,
    )
    op.create_table(
        "image_selection_manual_decisions",
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("range_start", sa.BigInteger(), nullable=False),
        sa.Column("range_end", sa.BigInteger(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "range_start >= 1 AND range_end >= range_start",
            name="ck_image_selection_manual_decisions_range",
        ),
        sa.CheckConstraint(
            "revision >= 1",
            name="ck_image_selection_manual_decisions_revision",
        ),
        sa.CheckConstraint(
            "payload_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_selection_manual_decisions_payload_sha256",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["image_selection_runs.id"],
            name="fk_image_selection_manual_decisions_run",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "group_id"],
            ["image_selection_groups.run_id", "image_selection_groups.id"],
            name="fk_image_selection_manual_decisions_group",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["image_selection_candidates.id"],
            name="fk_image_selection_manual_decisions_candidate",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "idempotency_key",
            name="pk_image_selection_manual_decisions",
        ),
        sa.UniqueConstraint(
            "run_id",
            "group_id",
            "revision",
            name="uq_image_selection_manual_decisions_revision",
        ),
    )
    op.create_index(
        "ix_image_selection_manual_decisions_group_revision",
        "image_selection_manual_decisions",
        ["run_id", "group_id", "revision"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_image_selection_manual_decisions_group_revision",
        table_name="image_selection_manual_decisions",
    )
    op.drop_table("image_selection_manual_decisions")
