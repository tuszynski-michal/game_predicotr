"""Add revisioned full-page geometry overrides for image layout imports."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0048_image_page_geometry_overrides"
down_revision: str | Sequence[str] | None = "0047_pending_symbol_reinference_job"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "image_page_geometry_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("image_width", sa.Integer(), nullable=False),
        sa.Column("image_height", sa.Integer(), nullable=False),
        sa.Column("final_quads", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("decision_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "image_width > 0 AND image_height > 0 AND revision > 0",
            name="ck_image_page_geometry_overrides_values",
        ),
        sa.CheckConstraint(
            "source_checksum_sha256 ~ '^[0-9a-f]{64}$' "
            "AND decision_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_page_geometry_overrides_checksums",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(final_quads) = 'array' AND jsonb_array_length(final_quads) = 9",
            name="ck_image_page_geometry_overrides_quads",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "game_id",
            "source_checksum_sha256",
            "revision",
            name="uq_image_page_geometry_overrides_revision",
        ),
    )
    op.create_index(
        "ix_image_page_geometry_overrides_current",
        "image_page_geometry_overrides",
        ["game_id", "source_checksum_sha256", "revision"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_image_page_geometry_overrides_current",
        table_name="image_page_geometry_overrides",
    )
    op.drop_table("image_page_geometry_overrides")
