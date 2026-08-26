"""Persist the current checksum-bound review state of every symbol crop.

Revision ID: 0066_image_symbol_review_cells
Revises: 0065_remove_symbol_bootstrap
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0066_image_symbol_review_cells"
down_revision: str | Sequence[str] | None = "0065_remove_symbol_bootstrap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "image_symbol_review_states",
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "processed_review_item_count", sa.BigInteger(), server_default="0", nullable=False
        ),
        sa.Column("cell_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("missing_sequence_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("invalid_crop_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("invalid_geometry_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("last_review_item_id", sa.Uuid(), nullable=True),
        sa.Column("failure_message", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('rebuilding', 'ready', 'failed')",
            name="ck_image_symbol_review_states_status",
        ),
        sa.CheckConstraint(
            "processed_review_item_count >= 0 AND cell_count >= 0 "
            "AND missing_sequence_count >= 0 AND invalid_crop_count >= 0 "
            "AND invalid_geometry_count >= 0",
            name="ck_image_symbol_review_states_counts",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("game_id", name="pk_image_symbol_review_states"),
    )
    op.create_table(
        "image_symbol_review_cells",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("import_job_id", sa.Uuid(), nullable=False),
        sa.Column("review_item_id", sa.Uuid(), nullable=False),
        sa.Column("recognized_board_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("cell_index", sa.SmallInteger(), nullable=False),
        sa.Column("row_index", sa.SmallInteger(), nullable=False),
        sa.Column("column_index", sa.SmallInteger(), nullable=False),
        sa.Column("crop_sample_id", sa.String(length=64), nullable=False),
        sa.Column("crop_relative_path", sa.String(length=1000), nullable=False),
        sa.Column("crop_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("geometry_revision", sa.Integer(), nullable=False),
        sa.Column("cropper_version", sa.String(length=150), nullable=False),
        sa.Column("prediction_symbol_code", sa.String(length=64), nullable=True),
        sa.Column("prediction_revision_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_symbol_id", sa.Uuid(), nullable=True),
        sa.Column("review_state", sa.String(length=20), nullable=False),
        sa.Column("has_grid_issue", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("assignment_source", sa.String(length=30), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_reviewed_by", sa.String(length=200), nullable=False),
        sa.Column(
            "last_reviewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "sequence_number > 0 AND cell_index BETWEEN 0 AND 14 "
            "AND row_index BETWEEN 0 AND 2 AND column_index BETWEEN 0 AND 4 "
            "AND cell_index = row_index * 5 + column_index",
            name="ck_image_symbol_review_cells_position",
        ),
        sa.CheckConstraint(
            "crop_sample_id ~ '^[0-9a-f]{64}$' AND crop_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_symbol_review_cells_checksums",
        ),
        sa.CheckConstraint(
            r"length(btrim(crop_relative_path)) > 0 "
            r"AND crop_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'",
            name="ck_image_symbol_review_cells_relative_path",
        ),
        sa.CheckConstraint(
            "geometry_revision >= 0 AND revision >= 0",
            name="ck_image_symbol_review_cells_revisions",
        ),
        sa.CheckConstraint(
            "review_state IN ('pending', 'approved')",
            name="ck_image_symbol_review_cells_state",
        ),
        sa.CheckConstraint(
            "assignment_source IN ('model', 'human', 'board_decision', 'backfill')",
            name="ck_image_symbol_review_cells_source",
        ),
        sa.CheckConstraint(
            "NOT has_grid_issue OR review_state = 'pending'",
            name="ck_image_symbol_review_cells_grid_issue_state",
        ),
        sa.CheckConstraint(
            "review_state <> 'approved' OR assigned_symbol_id IS NOT NULL",
            name="ck_image_symbol_review_cells_approved_symbol",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["import_job_id"], ["jobs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["review_item_id"], ["image_review_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["recognized_board_id"], ["recognized_boards.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["prediction_revision_id"],
            ["image_symbol_prediction_revisions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["assigned_symbol_id"], ["symbols.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_image_symbol_review_cells"),
        sa.UniqueConstraint(
            "review_item_id", "cell_index", name="uq_image_symbol_review_cells_item_cell"
        ),
    )
    op.create_index(
        "ix_image_symbol_review_cells_game_symbol_sequence",
        "image_symbol_review_cells",
        ["game_id", "assigned_symbol_id", "sequence_number", "cell_index", "review_item_id"],
    )
    op.create_index(
        "ix_image_symbol_review_cells_game_symbol_state_sequence",
        "image_symbol_review_cells",
        [
            "game_id",
            "assigned_symbol_id",
            "review_state",
            "sequence_number",
            "cell_index",
            "review_item_id",
        ],
    )
    op.create_index(
        "ix_image_symbol_review_cells_grid_issue",
        "image_symbol_review_cells",
        ["review_item_id"],
        postgresql_where=sa.text("has_grid_issue"),
    )
    op.create_table(
        "image_symbol_review_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cell_review_id", sa.Uuid(), nullable=False),
        sa.Column("review_item_id", sa.Uuid(), nullable=False),
        sa.Column("crop_sample_id", sa.String(length=64), nullable=False),
        sa.Column("crop_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("geometry_revision", sa.Integer(), nullable=False),
        sa.Column("cell_revision", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("previous_assigned_symbol_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_symbol_id", sa.Uuid(), nullable=True),
        sa.Column("previous_review_state", sa.String(length=20), nullable=False),
        sa.Column("review_state", sa.String(length=20), nullable=False),
        sa.Column("previous_has_grid_issue", sa.Boolean(), nullable=False),
        sa.Column("has_grid_issue", sa.Boolean(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=True),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "crop_sample_id ~ '^[0-9a-f]{64}$' AND crop_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_symbol_review_events_checksums",
        ),
        sa.CheckConstraint(
            "geometry_revision >= 0 AND cell_revision >= 0",
            name="ck_image_symbol_review_events_revisions",
        ),
        sa.CheckConstraint(
            "action IN ('approve', 'reassign', 'mark_grid_issue', "
            "'board_synchronized', 'geometry_invalidated')",
            name="ck_image_symbol_review_events_action",
        ),
        sa.CheckConstraint(
            "previous_review_state IN ('pending', 'approved') "
            "AND review_state IN ('pending', 'approved')",
            name="ck_image_symbol_review_events_states",
        ),
        sa.ForeignKeyConstraint(
            ["cell_review_id"], ["image_symbol_review_cells.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["review_item_id"], ["image_review_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["previous_assigned_symbol_id"], ["symbols.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["assigned_symbol_id"], ["symbols.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_image_symbol_review_events"),
    )
    op.create_index(
        "ix_image_symbol_review_events_cell_created",
        "image_symbol_review_events",
        ["cell_review_id", "created_at"],
    )
    op.create_index(
        "ix_image_symbol_review_events_review_item_created",
        "image_symbol_review_events",
        ["review_item_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_image_symbol_review_events_review_item_created", table_name="image_symbol_review_events"
    )
    op.drop_index(
        "ix_image_symbol_review_events_cell_created", table_name="image_symbol_review_events"
    )
    op.drop_table("image_symbol_review_events")
    op.drop_index("ix_image_symbol_review_cells_grid_issue", table_name="image_symbol_review_cells")
    op.drop_index(
        "ix_image_symbol_review_cells_game_symbol_state_sequence",
        table_name="image_symbol_review_cells",
    )
    op.drop_index(
        "ix_image_symbol_review_cells_game_symbol_sequence",
        table_name="image_symbol_review_cells",
    )
    op.drop_table("image_symbol_review_cells")
    op.drop_table("image_symbol_review_states")
