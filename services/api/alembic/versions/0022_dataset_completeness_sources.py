"""Add expected dataset size and auditable image source overrides.

Revision ID: 0022_dataset_quality
Revises: 0021_reviewer_access
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_dataset_quality"
down_revision: str | Sequence[str] | None = "0021_reviewer_access"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "games",
        sa.Column(
            "expected_layout_count",
            sa.BigInteger(),
            server_default="500000",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_games_expected_layout_count_range",
        "games",
        "expected_layout_count BETWEEN 1 AND 10000000",
    )
    op.add_column(
        "dataset_versions",
        sa.Column("expected_layout_count", sa.BigInteger(), nullable=True),
    )
    op.execute(
        "UPDATE dataset_versions SET expected_layout_count = layout_count "
        "WHERE expected_layout_count IS NULL"
    )
    op.alter_column(
        "dataset_versions",
        "expected_layout_count",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.create_check_constraint(
        "ck_dataset_versions_expected_layout_count_range",
        "dataset_versions",
        "expected_layout_count BETWEEN 1 AND 10000000",
    )
    op.create_table(
        "image_sequence_source_override_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "selected_review_item_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("selected_by", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "sequence_number > 0",
            name="ck_image_sequence_source_override_sequence_positive",
        ),
        sa.CheckConstraint(
            "revision > 0",
            name="ck_image_sequence_source_override_revision_positive",
        ),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
            name="fk_image_sequence_source_override_game",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["selected_review_item_id"],
            ["image_review_items.id"],
            name="fk_image_sequence_source_override_review_item",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_image_sequence_source_override_events"),
        sa.UniqueConstraint(
            "game_id",
            "sequence_number",
            "revision",
            name="uq_image_sequence_source_override_revision",
        ),
    )
    op.create_index(
        "ix_image_sequence_source_override_current",
        "image_sequence_source_override_events",
        ["game_id", "sequence_number", "revision"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_image_sequence_source_override_current",
        table_name="image_sequence_source_override_events",
    )
    op.drop_table("image_sequence_source_override_events")
    op.drop_constraint(
        "ck_dataset_versions_expected_layout_count_range",
        "dataset_versions",
        type_="check",
    )
    op.drop_column("dataset_versions", "expected_layout_count")
    op.drop_constraint(
        "ck_games_expected_layout_count_range",
        "games",
        type_="check",
    )
    op.drop_column("games", "expected_layout_count")
