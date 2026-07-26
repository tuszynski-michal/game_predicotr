"""Create canonical games and symbols.

Revision ID: 0002_games_symbols
Revises: 0001_empty_baseline
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_games_symbols"
down_revision: str | Sequence[str] | None = "0001_empty_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

game_status = postgresql.ENUM(
    "draft",
    "active",
    "archived",
    name="game_status",
    create_type=False,
)
symbol_status = postgresql.ENUM(
    "active",
    "archived",
    name="symbol_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    game_status.create(bind, checkfirst=True)
    symbol_status.create(bind, checkfirst=True)

    op.create_table(
        "games",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", game_status, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_games"),
        sa.UniqueConstraint("code", name="uq_games_code"),
    )
    op.create_table(
        "symbols",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mobile_code", sa.SmallInteger(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("image_path", sa.String(length=500), nullable=True),
        sa.Column(
            "is_wildcard",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("status", symbol_status, nullable=False),
        sa.CheckConstraint(
            "display_order >= 0",
            name="ck_symbols_display_order_nonnegative",
        ),
        sa.CheckConstraint(
            "mobile_code BETWEEN 1 AND 32767",
            name="ck_symbols_mobile_code_range",
        ),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
            name="fk_symbols_game_id_games",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_symbols"),
        sa.UniqueConstraint(
            "game_id",
            "code",
            name="uq_symbols_game_code",
        ),
        sa.UniqueConstraint(
            "game_id",
            "mobile_code",
            name="uq_symbols_game_mobile_code",
        ),
    )
    op.create_index(
        "ix_symbols_game_id",
        "symbols",
        ["game_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_symbols_game_id", table_name="symbols")
    op.drop_table("symbols")
    op.drop_table("games")
    symbol_status.drop(op.get_bind(), checkfirst=True)
    game_status.drop(op.get_bind(), checkfirst=True)
