"""Persist the declared shared shape-geometry family for newly created games.

Revision ID: 0116_game_shape_geometry_configuration
Revises: 0115_shape_geometry_v2_global_library
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0116_game_shape_geometry_configuration"
down_revision: str | Sequence[str] | None = "0115_shape_geometry_v2_global_library"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.add_column(
        "games",
        sa.Column("shape_geometry_configuration", sa.String(length=64), nullable=True),
        schema="public",
    )
    op.create_check_constraint(
        "ck_games_shape_geometry_configuration",
        "games",
        "shape_geometry_configuration IS NULL OR shape_geometry_configuration IN "
        "('framed_full_page_v2', 'requires_clarification')",
        schema="public",
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.drop_constraint("ck_games_shape_geometry_configuration", "games", schema="public")
    op.drop_column("games", "shape_geometry_configuration", schema="public")
