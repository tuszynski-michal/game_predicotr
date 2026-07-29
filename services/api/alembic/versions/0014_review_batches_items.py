"""Persist immutable whole-layout manual-review batches and items.

Revision ID: 0014_review_batches
Revises: 0013_layout_import_publication
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_review_batches"
down_revision: str | Sequence[str] | None = "0013_layout_import_publication"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

review_item_status = postgresql.ENUM(
    "pending",
    "accepted",
    "corrected",
    "rejected",
    name="review_item_status",
    create_type=False,
)


def upgrade() -> None:
    review_item_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "review_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_report_sha256", sa.String(length=64), nullable=False),
        sa.Column("active_learning_version", sa.String(length=100), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=False),
        sa.Column("model_artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("calibration_report_sha256", sa.String(length=64), nullable=False),
        sa.Column("dataset_sha256", sa.String(length=64), nullable=False),
        sa.Column("split_sha256", sa.String(length=64), nullable=False),
        sa.Column("inventory_sha256", sa.String(length=64), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("item_count", sa.SmallInteger(), nullable=False),
        sa.Column("source_report", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_report_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_review_batches_source_report_sha256",
        ),
        sa.CheckConstraint(
            "model_artifact_sha256 ~ '^[0-9a-f]{64}$' "
            "AND calibration_report_sha256 ~ '^[0-9a-f]{64}$' "
            "AND dataset_sha256 ~ '^[0-9a-f]{64}$' "
            "AND split_sha256 ~ '^[0-9a-f]{64}$' "
            "AND inventory_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_review_batches_provenance_sha256",
        ),
        sa.CheckConstraint(
            "temperature > 0",
            name="ck_review_batches_temperature_positive",
        ),
        sa.CheckConstraint(
            "item_count BETWEEN 1 AND 100",
            name="ck_review_batches_item_count",
        ),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
            name="fk_review_batches_game_id_games",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_batches"),
        sa.UniqueConstraint(
            "source_report_sha256",
            name="uq_review_batches_source_report_sha256",
        ),
    )
    op.create_table(
        "review_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("board_id", sa.String(length=64), nullable=False),
        sa.Column("selection_rank", sa.SmallInteger(), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("source_image_id", sa.String(length=200), nullable=False),
        sa.Column("source_image_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_group", sa.String(length=200), nullable=False),
        sa.Column("board_relative_path", sa.String(length=1000), nullable=False),
        sa.Column(
            "status",
            review_item_status,
            server_default="pending",
            nullable=False,
        ),
        sa.Column("prediction_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("resolved_value", postgresql.JSONB(), nullable=True),
        sa.Column("resolved_by", sa.String(length=200), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "board_id ~ '^[0-9a-f]{64}$' AND source_image_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_review_items_identity_sha256",
        ),
        sa.CheckConstraint(
            "selection_rank BETWEEN 1 AND 100",
            name="ck_review_items_selection_rank",
        ),
        sa.CheckConstraint(
            "sequence_number > 0",
            name="ck_review_items_sequence_positive",
        ),
        sa.CheckConstraint(
            r"length(btrim(board_relative_path)) > 0 "
            r"AND board_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'",
            name="ck_review_items_board_path_safe",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND resolved_value IS NULL "
            "AND resolved_by IS NULL AND resolved_at IS NULL) "
            "OR (status <> 'pending' AND resolved_by IS NOT NULL "
            "AND resolved_at IS NOT NULL)",
            name="ck_review_items_resolution_state",
        ),
        sa.ForeignKeyConstraint(
            ["review_batch_id"],
            ["review_batches.id"],
            name="fk_review_items_batch_id_review_batches",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_items"),
        sa.UniqueConstraint(
            "review_batch_id",
            "board_id",
            name="uq_review_items_batch_board",
        ),
        sa.UniqueConstraint(
            "review_batch_id",
            "selection_rank",
            name="uq_review_items_batch_rank",
        ),
        sa.UniqueConstraint(
            "review_batch_id",
            "sequence_number",
            name="uq_review_items_batch_sequence",
        ),
    )
    op.create_index(
        "ix_review_items_batch_status_rank",
        "review_items",
        ["review_batch_id", "status", "selection_rank"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_review_items_batch_status_rank",
        table_name="review_items",
    )
    op.drop_table("review_items")
    op.drop_table("review_batches")
    review_item_status.drop(op.get_bind(), checkfirst=True)
