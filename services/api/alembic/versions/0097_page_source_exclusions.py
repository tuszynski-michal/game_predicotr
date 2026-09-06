"""Add checksum-bound browser page source exclusions.

Revision ID: 0097_page_source_exclusions
Revises: 0096_preimport_geometry_guard_decisions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0097_page_source_exclusions"
down_revision: str | Sequence[str] | None = "0096_preimport_geometry_guard_decisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "image_page_source_exclusions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("browser_selection_id", sa.Uuid(), nullable=False),
        sa.Column("geometry_preflight_job_id", sa.Uuid(), nullable=False),
        sa.Column("source_manifest_checksum_sha256", sa.String(64), nullable=False),
        sa.Column("geometry_manifest_checksum_sha256", sa.String(64), nullable=False),
        sa.Column("source_checksum_sha256", sa.String(64), nullable=False),
        sa.Column("source_relative_path", sa.String(1000), nullable=False),
        sa.Column("actor", sa.String(200), nullable=False),
        sa.Column("decision_checksum_sha256", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "source_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$' AND "
            "geometry_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$' AND "
            "source_checksum_sha256 ~ '^[0-9a-f]{64}$' AND "
            "decision_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_page_source_exclusions_checksums",
        ),
        sa.CheckConstraint(
            "length(btrim(source_relative_path)) > 0 "
            "AND source_relative_path !~ '(^/|(^|/)\\.\\.(/|$)|\\\\)' "
            "AND length(btrim(actor)) > 0",
            name="ck_image_page_source_exclusions_text",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["browser_selection_id"],
            ["browser_selection_retention_states.upload_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "browser_selection_id",
            "source_checksum_sha256",
            name="uq_image_page_source_exclusions_source",
        ),
    )
    op.create_index(
        "ix_image_page_source_exclusions_selection",
        "image_page_source_exclusions",
        ["browser_selection_id", "source_checksum_sha256"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_image_page_source_exclusions_selection",
        table_name="image_page_source_exclusions",
    )
    op.drop_table("image_page_source_exclusions")
