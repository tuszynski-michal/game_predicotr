"""Add immutable manual geometry revisions for operational review.

Revision ID: 0019_review_geometry
Revises: 0018_image_failure_retry
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_review_geometry"
down_revision: str | Sequence[str] | None = "0018_image_failure_retry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "recognized_boards",
        sa.Column(
            "geometry_revision",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_recognized_boards_geometry_revision",
        "recognized_boards",
        "geometry_revision >= 0",
    )
    op.create_table(
        "image_board_geometry_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recognized_board_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_sha256", sa.String(length=64), nullable=False),
        sa.Column("corners", postgresql.JSONB(), nullable=False),
        sa.Column("geometry", postgresql.JSONB(), nullable=False),
        sa.Column("board_relative_path", sa.String(length=1000), nullable=False),
        sa.Column("board_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("cropper_version", sa.String(length=150), nullable=False),
        sa.Column("crop_artifacts", postgresql.JSONB(), nullable=False),
        sa.Column("corrected_by", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "revision > 0",
            name="ck_image_board_geometry_revisions_revision",
        ),
        sa.CheckConstraint(
            "command_sha256 ~ '^[0-9a-f]{64}$' AND board_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_board_geometry_revisions_sha256",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(corners) = 'array' AND jsonb_array_length(corners) = 4",
            name="ck_image_board_geometry_revisions_corners",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(crop_artifacts) = 'array' AND jsonb_array_length(crop_artifacts) = 15",
            name="ck_image_board_geometry_revisions_crops",
        ),
        sa.CheckConstraint(
            r"length(btrim(board_relative_path)) > 0 "
            r"AND board_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'",
            name="ck_image_board_geometry_revisions_relative_path",
        ),
        sa.ForeignKeyConstraint(
            ["review_item_id"],
            ["image_review_items.id"],
            name="fk_image_board_geometry_revisions_review_item",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recognized_board_id"],
            ["recognized_boards.id"],
            name="fk_image_board_geometry_revisions_board",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_image_board_geometry_revisions"),
        sa.UniqueConstraint(
            "recognized_board_id",
            "revision",
            name="uq_image_board_geometry_revisions_board_revision",
        ),
        sa.UniqueConstraint(
            "review_item_id",
            "idempotency_key",
            name="uq_image_board_geometry_revisions_item_idempotency",
        ),
    )


def downgrade() -> None:
    op.drop_table("image_board_geometry_revisions")
    op.drop_constraint(
        "ck_recognized_boards_geometry_revision",
        "recognized_boards",
        type_="check",
    )
    op.drop_column("recognized_boards", "geometry_revision")
