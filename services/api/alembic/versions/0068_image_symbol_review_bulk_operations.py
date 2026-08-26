"""Persist durable, resumable symbol-cell review bulk operations.

Revision ID: 0068_image_symbol_review_bulk_operations
Revises: 0067_symbol_cell_review_catalog_revision
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0068_image_symbol_review_bulk_operations"
down_revision: str | Sequence[str] | None = "0067_symbol_cell_review_catalog_revision"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'image_symbol_review_bulk'")
    op.create_table(
        "image_symbol_review_bulk_operations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("target_symbol_id", sa.Uuid(), nullable=True),
        sa.Column("selection_kind", sa.String(length=20), nullable=False),
        sa.Column("filter_symbol_id", sa.Uuid(), nullable=True),
        sa.Column("filter_state", sa.String(length=20), nullable=True),
        sa.Column("catalog_revision", sa.BigInteger(), nullable=True),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("command_sha256", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("target_count", sa.BigInteger(), nullable=False),
        sa.Column("applied_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("conflict_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("failed_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "action IN ('approve', 'reassign', 'mark_grid_issue')",
            name="ck_image_symbol_review_bulk_operations_action",
        ),
        sa.CheckConstraint(
            "selection_kind IN ('explicit', 'filter')",
            name="ck_image_symbol_review_bulk_operations_selection_kind",
        ),
        sa.CheckConstraint(
            "status IN ('created', 'processing', 'completed', 'failed', 'cancelled')",
            name="ck_image_symbol_review_bulk_operations_status",
        ),
        sa.CheckConstraint(
            "target_count >= 0 AND applied_count >= 0 AND conflict_count >= 0 "
            "AND failed_count >= 0 AND applied_count + conflict_count + failed_count "
            "<= target_count",
            name="ck_image_symbol_review_bulk_operations_counts",
        ),
        sa.CheckConstraint(
            "command_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_symbol_review_bulk_operations_command",
        ),
        sa.CheckConstraint(
            "(selection_kind = 'filter' AND catalog_revision IS NOT NULL) OR "
            "(selection_kind = 'explicit' AND catalog_revision IS NULL)",
            name="ck_image_symbol_review_bulk_operations_catalog_revision",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["target_symbol_id"], ["symbols.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["filter_symbol_id"], ["symbols.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_image_symbol_review_bulk_operations"),
        sa.UniqueConstraint(
            "game_id",
            "idempotency_key",
            name="uq_image_symbol_review_bulk_operations_game_idempotency",
        ),
        sa.UniqueConstraint("job_id", name="uq_image_symbol_review_bulk_operations_job"),
    )
    op.create_index(
        "ix_image_symbol_review_bulk_operations_game_status_created",
        "image_symbol_review_bulk_operations",
        ["game_id", "status", "created_at", "id"],
    )
    op.create_table(
        "image_symbol_review_bulk_targets",
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("cell_review_id", sa.Uuid(), nullable=False),
        sa.Column("review_item_id", sa.Uuid(), nullable=False),
        sa.Column("recognized_board_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("cell_index", sa.SmallInteger(), nullable=False),
        sa.Column("expected_revision", sa.Integer(), nullable=False),
        sa.Column("expected_geometry_revision", sa.Integer(), nullable=False),
        sa.Column("expected_crop_sample_id", sa.String(length=64), nullable=False),
        sa.Column("expected_crop_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("applied_cell_revision", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "sequence_number > 0 AND cell_index BETWEEN 0 AND 14 AND "
            "expected_revision >= 0 AND expected_geometry_revision >= 0",
            name="ck_image_symbol_review_bulk_targets_revisions",
        ),
        sa.CheckConstraint(
            "expected_crop_sample_id ~ '^[0-9a-f]{64}$' AND "
            "expected_crop_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_symbol_review_bulk_targets_checksums",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'applied', 'conflict', 'failed')",
            name="ck_image_symbol_review_bulk_targets_status",
        ),
        sa.ForeignKeyConstraint(
            ["operation_id"], ["image_symbol_review_bulk_operations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["cell_review_id"],
            ["image_symbol_review_cells.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["review_item_id"], ["image_review_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["recognized_board_id"],
            ["recognized_boards.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "operation_id",
            "cell_review_id",
            name="pk_image_symbol_review_bulk_targets",
        ),
    )
    op.create_index(
        "ix_image_symbol_review_bulk_targets_operation_status_review",
        "image_symbol_review_bulk_targets",
        ["operation_id", "status", "review_item_id"],
    )
    op.create_index(
        "ix_image_symbol_review_bulk_targets_operation_sequence",
        "image_symbol_review_bulk_targets",
        ["operation_id", "sequence_number", "review_item_id", "cell_index"],
    )
    op.create_foreign_key(
        "fk_image_symbol_review_events_operation",
        "image_symbol_review_events",
        "image_symbol_review_bulk_operations",
        ["operation_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_image_symbol_review_events_operation",
        "image_symbol_review_events",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_image_symbol_review_bulk_targets_operation_sequence",
        table_name="image_symbol_review_bulk_targets",
    )
    op.drop_index(
        "ix_image_symbol_review_bulk_targets_operation_status_review",
        table_name="image_symbol_review_bulk_targets",
    )
    op.drop_table("image_symbol_review_bulk_targets")
    op.drop_index(
        "ix_image_symbol_review_bulk_operations_game_status_created",
        table_name="image_symbol_review_bulk_operations",
    )
    op.drop_table("image_symbol_review_bulk_operations")
    # PostgreSQL enum values cannot be removed safely. The harmless job_type
    # value remains so historical job records and downgrade paths stay valid.
