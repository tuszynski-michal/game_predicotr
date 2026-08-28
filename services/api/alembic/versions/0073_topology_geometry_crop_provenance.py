"""Persist board topology, geometry approval and crop provenance.

Revision ID: 0073_topology_geometry_crop_provenance
Revises: 0072_verified_training_cohort_cells
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0073_topology_geometry_crop_provenance"
down_revision: str | Sequence[str] | None = "0072_verified_training_cohort_cells"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_image_symbol_review_bulk_operations_action",
        "image_symbol_review_bulk_operations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_symbol_review_bulk_operations_action",
        "image_symbol_review_bulk_operations",
        "action IN ('approve', 'reassign', 'mark_grid_issue', 'mark_unreadable')",
    )
    op.drop_constraint(
        "ck_image_symbol_review_events_action",
        "image_symbol_review_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_symbol_review_events_action",
        "image_symbol_review_events",
        "action IN ('approve', 'reassign', 'mark_grid_issue', 'mark_unreadable', "
        "'board_synchronized', 'geometry_invalidated')",
    )
    op.add_column("games", sa.Column("board_topology_rules_version_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_games_board_topology_rules_version",
        "games",
        "rules_versions",
        ["board_topology_rules_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_games_board_topology_rules_version",
        "games",
        ["board_topology_rules_version_id"],
    )

    op.add_column("recognized_boards", sa.Column("grid_rows", sa.SmallInteger(), nullable=True))
    op.add_column("recognized_boards", sa.Column("grid_columns", sa.SmallInteger(), nullable=True))
    op.add_column(
        "recognized_boards", sa.Column("approved_geometry_revision", sa.Integer(), nullable=True)
    )
    op.add_column(
        "recognized_boards",
        sa.Column("geometry_approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "recognized_boards", sa.Column("geometry_approved_by", sa.String(length=200), nullable=True)
    )
    op.create_check_constraint(
        "ck_recognized_boards_grid_topology",
        "recognized_boards",
        "(grid_rows IS NULL AND grid_columns IS NULL) OR "
        "(grid_rows IS NOT NULL AND grid_columns IS NOT NULL "
        "AND grid_rows > 0 AND grid_columns > 0)",
    )
    op.create_check_constraint(
        "ck_recognized_boards_geometry_approval_revision",
        "recognized_boards",
        "approved_geometry_revision IS NULL OR "
        "(approved_geometry_revision >= 0 AND approved_geometry_revision <= geometry_revision)",
    )
    op.create_check_constraint(
        "ck_recognized_boards_geometry_approval_metadata",
        "recognized_boards",
        "(approved_geometry_revision IS NULL AND geometry_approved_at IS NULL "
        "AND geometry_approved_by IS NULL) OR "
        "(approved_geometry_revision IS NOT NULL AND geometry_approved_at IS NOT NULL "
        "AND geometry_approved_by IS NOT NULL AND length(btrim(geometry_approved_by)) > 0)",
    )
    op.create_index(
        "ix_recognized_boards_geometry_review",
        "recognized_boards",
        ["geometry_revision", "approved_geometry_revision", "id"],
    )

    op.add_column(
        "image_symbol_review_cells",
        sa.Column("quality_issue", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "image_symbol_review_cells",
        sa.Column("approved_crop_sample_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "image_symbol_review_cells",
        sa.Column("approved_crop_checksum_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "image_symbol_review_cells",
        sa.Column("approved_geometry_revision", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_image_symbol_review_cells_quality_issue",
        "image_symbol_review_cells",
        "quality_issue IS NULL OR quality_issue IN ('grid_issue', 'unreadable')",
    )
    op.create_check_constraint(
        "ck_image_symbol_review_cells_grid_quality_state",
        "image_symbol_review_cells",
        "quality_issue <> 'grid_issue' OR review_state = 'pending'",
    )
    op.create_check_constraint(
        "ck_image_symbol_review_cells_approved_crop_identity",
        "image_symbol_review_cells",
        "(approved_crop_sample_id IS NULL AND approved_crop_checksum_sha256 IS NULL "
        "AND approved_geometry_revision IS NULL) OR "
        "(approved_crop_sample_id IS NOT NULL "
        "AND approved_crop_checksum_sha256 IS NOT NULL "
        "AND approved_geometry_revision IS NOT NULL "
        "AND approved_crop_sample_id ~ '^[0-9a-f]{64}$' "
        "AND approved_crop_checksum_sha256 ~ '^[0-9a-f]{64}$' "
        "AND approved_geometry_revision >= 0)",
    )
    op.drop_constraint(
        "ck_image_symbol_review_cells_approved_symbol",
        "image_symbol_review_cells",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_symbol_review_cells_approved_symbol",
        "image_symbol_review_cells",
        "review_state <> 'approved' OR assigned_symbol_id IS NOT NULL "
        "OR (quality_issue IS NOT NULL AND quality_issue = 'unreadable')",
    )
    op.create_index(
        "ix_image_symbol_review_cells_grid_quality_issue",
        "image_symbol_review_cells",
        ["game_id", "review_item_id", "cell_index"],
        postgresql_where=sa.text("quality_issue = 'grid_issue'"),
    )
    op.create_index(
        "ix_image_symbol_review_cells_unreadable_quality_issue",
        "image_symbol_review_cells",
        ["game_id", "review_item_id", "cell_index"],
        postgresql_where=sa.text("quality_issue = 'unreadable'"),
    )

    for column in (
        sa.Column("previous_quality_issue", sa.String(length=20), nullable=True),
        sa.Column("quality_issue", sa.String(length=20), nullable=True),
        sa.Column("previous_approved_crop_sample_id", sa.String(length=64), nullable=True),
        sa.Column("approved_crop_sample_id", sa.String(length=64), nullable=True),
        sa.Column("previous_approved_crop_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("approved_crop_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("previous_approved_geometry_revision", sa.Integer(), nullable=True),
        sa.Column("approved_geometry_revision", sa.Integer(), nullable=True),
    ):
        op.add_column("image_symbol_review_events", column)
    op.create_check_constraint(
        "ck_image_symbol_review_events_quality_issue",
        "image_symbol_review_events",
        "(previous_quality_issue IS NULL OR "
        "previous_quality_issue IN ('grid_issue', 'unreadable')) AND "
        "(quality_issue IS NULL OR quality_issue IN ('grid_issue', 'unreadable'))",
    )
    op.create_check_constraint(
        "ck_image_symbol_review_events_approved_crop_identity",
        "image_symbol_review_events",
        "(previous_approved_crop_sample_id IS NULL "
        "AND previous_approved_crop_checksum_sha256 IS NULL "
        "AND previous_approved_geometry_revision IS NULL) OR "
        "(previous_approved_crop_sample_id IS NOT NULL "
        "AND previous_approved_crop_checksum_sha256 IS NOT NULL "
        "AND previous_approved_geometry_revision IS NOT NULL "
        "AND previous_approved_crop_sample_id ~ '^[0-9a-f]{64}$' "
        "AND previous_approved_crop_checksum_sha256 ~ '^[0-9a-f]{64}$' "
        "AND previous_approved_geometry_revision >= 0)",
    )
    op.create_check_constraint(
        "ck_image_symbol_review_events_current_approved_crop_identity",
        "image_symbol_review_events",
        "(approved_crop_sample_id IS NULL AND approved_crop_checksum_sha256 IS NULL "
        "AND approved_geometry_revision IS NULL) OR "
        "(approved_crop_sample_id IS NOT NULL "
        "AND approved_crop_checksum_sha256 IS NOT NULL "
        "AND approved_geometry_revision IS NOT NULL "
        "AND approved_crop_sample_id ~ '^[0-9a-f]{64}$' "
        "AND approved_crop_checksum_sha256 ~ '^[0-9a-f]{64}$' "
        "AND approved_geometry_revision >= 0)",
    )

    op.create_table(
        "image_board_geometry_review_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("review_item_id", sa.Uuid(), nullable=False),
        sa.Column("recognized_board_id", sa.Uuid(), nullable=False),
        sa.Column("geometry_revision", sa.Integer(), nullable=False),
        sa.Column("grid_rows", sa.SmallInteger(), nullable=False),
        sa.Column("grid_columns", sa.SmallInteger(), nullable=False),
        sa.Column("board_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("previous_approved_geometry_revision", sa.Integer(), nullable=True),
        sa.Column("approved_geometry_revision", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "geometry_revision >= 0 AND approved_geometry_revision >= 0 "
            "AND approved_geometry_revision <= geometry_revision",
            name="ck_image_board_geometry_review_events_revisions",
        ),
        sa.CheckConstraint(
            "grid_rows > 0 AND grid_columns > 0",
            name="ck_image_board_geometry_review_events_topology",
        ),
        sa.CheckConstraint(
            "board_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_board_geometry_review_events_checksum",
        ),
        sa.CheckConstraint(
            "action IN ('approved', 'geometry_saved', 'backfilled')",
            name="ck_image_board_geometry_review_events_action",
        ),
        sa.ForeignKeyConstraint(["review_item_id"], ["image_review_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["recognized_board_id"], ["recognized_boards.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_image_board_geometry_review_events"),
    )
    op.create_index(
        "ix_image_board_geometry_review_events_board_created",
        "image_board_geometry_review_events",
        ["recognized_board_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_image_board_geometry_review_events_board_created",
        table_name="image_board_geometry_review_events",
    )
    op.drop_table("image_board_geometry_review_events")

    op.drop_constraint(
        "ck_image_symbol_review_events_action",
        "image_symbol_review_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_symbol_review_events_action",
        "image_symbol_review_events",
        "action IN ('approve', 'reassign', 'mark_grid_issue', "
        "'board_synchronized', 'geometry_invalidated')",
    )
    op.drop_constraint(
        "ck_image_symbol_review_bulk_operations_action",
        "image_symbol_review_bulk_operations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_symbol_review_bulk_operations_action",
        "image_symbol_review_bulk_operations",
        "action IN ('approve', 'reassign', 'mark_grid_issue')",
    )

    op.drop_constraint(
        "ck_image_symbol_review_events_current_approved_crop_identity",
        "image_symbol_review_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_image_symbol_review_events_approved_crop_identity",
        "image_symbol_review_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_image_symbol_review_events_quality_issue",
        "image_symbol_review_events",
        type_="check",
    )
    for column_name in (
        "approved_geometry_revision",
        "previous_approved_geometry_revision",
        "approved_crop_checksum_sha256",
        "previous_approved_crop_checksum_sha256",
        "approved_crop_sample_id",
        "previous_approved_crop_sample_id",
        "quality_issue",
        "previous_quality_issue",
    ):
        op.drop_column("image_symbol_review_events", column_name)

    op.drop_index(
        "ix_image_symbol_review_cells_unreadable_quality_issue",
        table_name="image_symbol_review_cells",
    )
    op.drop_index(
        "ix_image_symbol_review_cells_grid_quality_issue",
        table_name="image_symbol_review_cells",
    )
    op.drop_constraint(
        "ck_image_symbol_review_cells_approved_symbol",
        "image_symbol_review_cells",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_symbol_review_cells_approved_symbol",
        "image_symbol_review_cells",
        "review_state <> 'approved' OR assigned_symbol_id IS NOT NULL",
    )
    op.drop_constraint(
        "ck_image_symbol_review_cells_approved_crop_identity",
        "image_symbol_review_cells",
        type_="check",
    )
    op.drop_constraint(
        "ck_image_symbol_review_cells_grid_quality_state",
        "image_symbol_review_cells",
        type_="check",
    )
    op.drop_constraint(
        "ck_image_symbol_review_cells_quality_issue",
        "image_symbol_review_cells",
        type_="check",
    )
    for column_name in (
        "approved_geometry_revision",
        "approved_crop_checksum_sha256",
        "approved_crop_sample_id",
        "quality_issue",
    ):
        op.drop_column("image_symbol_review_cells", column_name)

    op.drop_index("ix_recognized_boards_geometry_review", table_name="recognized_boards")
    op.drop_constraint(
        "ck_recognized_boards_geometry_approval_metadata", "recognized_boards", type_="check"
    )
    op.drop_constraint(
        "ck_recognized_boards_geometry_approval_revision", "recognized_boards", type_="check"
    )
    op.drop_constraint("ck_recognized_boards_grid_topology", "recognized_boards", type_="check")
    for column_name in (
        "geometry_approved_by",
        "geometry_approved_at",
        "approved_geometry_revision",
        "grid_columns",
        "grid_rows",
    ):
        op.drop_column("recognized_boards", column_name)

    op.drop_index("ix_games_board_topology_rules_version", table_name="games")
    op.drop_constraint("fk_games_board_topology_rules_version", "games", type_="foreignkey")
    op.drop_column("games", "board_topology_rules_version_id")
