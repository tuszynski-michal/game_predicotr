"""Add immutable multi-game search panels without changing legacy sessions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0155_board_search_panels"
down_revision = "0154_geometry_correction_revert"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "board_search_panels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("label", sa.String(100)),
        sa.Column("secret_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("octet_length(secret_hash) = 32", name="ck_bsp_secret_hash"),
        sa.CheckConstraint("expires_at > created_at", name="ck_bsp_timestamps"),
        sa.CheckConstraint(
            "label IS NULL OR length(btrim(label)) BETWEEN 1 AND 100", name="ck_bsp_label"
        ),
        schema="public",
    )
    op.create_index("ix_bsp_created", "board_search_panels", ["created_at", "id"], schema="public")
    op.add_column(
        "board_search_share_sessions",
        sa.Column("panel_id", postgresql.UUID(as_uuid=True)),
        schema="public",
    )
    op.create_foreign_key(
        "fk_bss_panel",
        "board_search_share_sessions",
        "board_search_panels",
        ["panel_id"],
        ["id"],
        ondelete="RESTRICT",
        source_schema="public",
        referent_schema="public",
    )
    op.create_index(
        "uq_bss_panel_game",
        "board_search_share_sessions",
        ["panel_id", "game_id"],
        unique=True,
        postgresql_where=sa.text("panel_id IS NOT NULL"),
        schema="public",
    )


def downgrade() -> None:
    # Never discard a capability link or its durable query/correction provenance.
    raise RuntimeError("0155 holds access history; restore a verified backup instead of downgrade.")
