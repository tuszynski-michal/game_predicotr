"""Persist checksum-bound, human-approved symbol reference images.

Revision ID: 0064_symbol_reference_images
Revises: 0063_symbol_reference_candidate_index
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0064_symbol_reference_images"
down_revision: str | Sequence[str] | None = "0063_symbol_reference_candidate_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "symbol_reference_images",
        sa.Column("symbol_id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("source_review_item_id", sa.Uuid(), nullable=False),
        sa.Column("source_recognized_board_id", sa.Uuid(), nullable=False),
        sa.Column("source_observation_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("cell_index", sa.SmallInteger(), nullable=False),
        sa.Column("resolution_revision", sa.Integer(), nullable=False),
        sa.Column("geometry_revision", sa.Integer(), nullable=False),
        sa.Column("image_relative_path", sa.String(length=1000), nullable=False),
        sa.Column("image_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("selected_by", sa.String(length=200), nullable=False),
        sa.Column(
            "selected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "sequence_number > 0 AND cell_index BETWEEN 0 AND 14 "
            "AND resolution_revision > 0 AND geometry_revision >= 0",
            name="ck_symbol_reference_images_position",
        ),
        sa.CheckConstraint(
            "image_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_symbol_reference_images_checksum",
        ),
        sa.CheckConstraint(
            r"length(btrim(image_relative_path)) > 0 "
            r"AND image_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'",
            name="ck_symbol_reference_images_relative_path",
        ),
        sa.ForeignKeyConstraint(
            ["symbol_id"], ["symbols.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_review_item_id"], ["image_review_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_recognized_board_id"], ["recognized_boards.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_observation_id"], ["cell_observations.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("symbol_id"),
    )
    op.create_index(
        "ix_symbol_reference_images_game",
        "symbol_reference_images",
        ["game_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_symbol_reference_images_game", table_name="symbol_reference_images")
    op.drop_table("symbol_reference_images")
