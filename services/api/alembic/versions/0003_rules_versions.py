"""Create versioned game dimensions and spin cost.

Revision ID: 0003_rules_versions
Revises: 0002_games_symbols
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_rules_versions"
down_revision: str | Sequence[str] | None = "0002_games_symbols"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

rules_version_status = postgresql.ENUM(
    "draft",
    "published",
    "archived",
    name="rules_version_status",
    create_type=False,
)


def upgrade() -> None:
    rules_version_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "rules_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("rows", sa.SmallInteger(), nullable=False),
        sa.Column("columns", sa.SmallInteger(), nullable=False),
        sa.Column("spin_cost", sa.Integer(), nullable=False),
        sa.Column("status", rules_version_status, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "version > 0",
            name="ck_rules_versions_version_positive",
        ),
        sa.CheckConstraint(
            "rows BETWEEN 1 AND 32767",
            name="ck_rules_versions_rows_range",
        ),
        sa.CheckConstraint(
            "columns BETWEEN 1 AND 32767",
            name="ck_rules_versions_columns_range",
        ),
        sa.CheckConstraint(
            "spin_cost >= 0",
            name="ck_rules_versions_spin_cost_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
            name="fk_rules_versions_game_id_games",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rules_versions"),
        sa.UniqueConstraint(
            "game_id",
            "version",
            name="uq_rules_versions_game_version",
        ),
    )
    op.create_index(
        "ix_rules_versions_game_id",
        "rules_versions",
        ["game_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_rules_versions_game_id", table_name="rules_versions")
    op.drop_table("rules_versions")
    rules_version_status.drop(op.get_bind(), checkfirst=True)
