"""Persist review resolution audit and immutable feedback exports.

Revision ID: 0015_review_feedback
Revises: 0014_review_batches
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_review_feedback"
down_revision: str | Sequence[str] | None = "0014_review_batches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

review_resolution_action = postgresql.ENUM(
    "accepted",
    "corrected",
    "rejected",
    name="review_resolution_action",
    create_type=False,
)


def upgrade() -> None:
    review_resolution_action.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "review_items",
        sa.Column(
            "resolution_revision",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.drop_constraint(
        "ck_review_items_resolution_state",
        "review_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_review_items_resolution_state",
        "review_items",
        "(status = 'pending' AND resolved_value IS NULL "
        "AND resolved_by IS NULL AND resolved_at IS NULL "
        "AND resolution_revision = 0) "
        "OR (status <> 'pending' AND resolved_by IS NOT NULL "
        "AND resolved_at IS NOT NULL AND resolution_revision > 0)",
    )
    op.create_table(
        "review_resolutions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "action",
            review_resolution_action,
            nullable=False,
        ),
        sa.Column("command_sha256", sa.String(length=64), nullable=False),
        sa.Column("resolved_value", postgresql.JSONB(), nullable=False),
        sa.Column("resolved_by", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "revision > 0",
            name="ck_review_resolutions_revision_positive",
        ),
        sa.CheckConstraint(
            "command_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_review_resolutions_command_sha256",
        ),
        sa.ForeignKeyConstraint(
            ["review_item_id"],
            ["review_items.id"],
            name="fk_review_resolutions_review_item_id_review_items",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_resolutions"),
        sa.UniqueConstraint(
            "review_item_id",
            "revision",
            name="uq_review_resolutions_item_revision",
        ),
        sa.UniqueConstraint(
            "review_item_id",
            "idempotency_key",
            name="uq_review_resolutions_item_idempotency",
        ),
    )
    op.create_index(
        "ix_review_resolutions_item_created",
        "review_resolutions",
        ["review_item_id", "revision"],
        unique=False,
    )
    op.create_table(
        "review_feedback_exports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_state_sha256", sa.String(length=64), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("rejected_item_count", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "version > 0",
            name="ck_review_feedback_exports_version_positive",
        ),
        sa.CheckConstraint(
            "source_state_sha256 ~ '^[0-9a-f]{64}$' "
            "AND payload_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_review_feedback_exports_sha256",
        ),
        sa.CheckConstraint(
            "sample_count >= 0 AND rejected_item_count >= 0",
            name="ck_review_feedback_exports_counts",
        ),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
            name="fk_review_feedback_exports_game_id_games",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["review_batch_id"],
            ["review_batches.id"],
            name="fk_review_feedback_exports_review_batch_id_review_batches",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_feedback_exports"),
        sa.UniqueConstraint(
            "game_id",
            "version",
            name="uq_review_feedback_exports_game_version",
        ),
        sa.UniqueConstraint(
            "review_batch_id",
            "source_state_sha256",
            name="uq_review_feedback_exports_batch_state",
        ),
    )


def downgrade() -> None:
    op.drop_table("review_feedback_exports")
    op.drop_index(
        "ix_review_resolutions_item_created",
        table_name="review_resolutions",
    )
    op.drop_table("review_resolutions")
    op.drop_constraint(
        "ck_review_items_resolution_state",
        "review_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_review_items_resolution_state",
        "review_items",
        "(status = 'pending' AND resolved_value IS NULL "
        "AND resolved_by IS NULL AND resolved_at IS NULL) "
        "OR (status <> 'pending' AND resolved_by IS NOT NULL "
        "AND resolved_at IS NOT NULL)",
    )
    op.drop_column("review_items", "resolution_revision")
    review_resolution_action.drop(op.get_bind(), checkfirst=True)
