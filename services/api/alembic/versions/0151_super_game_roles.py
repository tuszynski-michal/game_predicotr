"""Symbol super game trigger role and per-game super game kind (TASK-0931, D-535).

Revision ID: 0151_super_game_roles
Revises: 0150_management_sessions

Additive only: ``symbols.super_game_trigger_count`` is nullable (``null`` means
the symbol does not start a super game) and ``games.super_game_kind`` defaults
to ``'none'``, so every existing game, including 777, keeps its behavior. The
kind values themselves come from the code registry
``game_predictor_worker.domain.super_games``; the database only guards the
code format so that a new kind never requires a migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0151_super_game_roles"
down_revision: str | Sequence[str] | None = "0150_management_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.add_column(
        "symbols",
        sa.Column("super_game_trigger_count", sa.SmallInteger(), nullable=True),
        schema="public",
    )
    op.create_check_constraint(
        "ck_symbols_super_game_trigger_count",
        "symbols",
        "super_game_trigger_count IS NULL OR super_game_trigger_count IN (3, 4, 5)",
        schema="public",
    )
    op.add_column(
        "games",
        sa.Column(
            "super_game_kind",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'none'"),
        ),
        schema="public",
    )
    op.create_check_constraint(
        "ck_games_super_game_kind_format",
        "games",
        "super_game_kind ~ '^[a-z][a-z0-9_]{0,63}$'",
        schema="public",
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.drop_constraint("ck_games_super_game_kind_format", "games", type_="check", schema="public")
    op.drop_column("games", "super_game_kind", schema="public")
    op.drop_constraint(
        "ck_symbols_super_game_trigger_count", "symbols", type_="check", schema="public"
    )
    op.drop_column("symbols", "super_game_trigger_count", schema="public")
