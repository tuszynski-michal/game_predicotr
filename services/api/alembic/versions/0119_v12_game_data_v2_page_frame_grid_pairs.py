"""Add V1.2 frame/grid pairs to the partitioned per-game override store.

Revision ID: 0119_v12_game_data_v2_page_frame_grid_pairs
Revises: 0118_v12_page_frame_grid_pairs
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0119_v12_game_data_v2_page_frame_grid_pairs"
down_revision: str | Sequence[str] | None = "0118_v12_page_frame_grid_pairs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA = "game_data_v2"
_TABLE = "image_page_geometry_overrides"
_PAIR_CONSTRAINT = "ck_image_page_geometry_overrides_v12_pairs"


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.add_column(
        _TABLE,
        sa.Column("board_frame_quads", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        _TABLE,
        sa.Column("symbol_grid_quads", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema=_SCHEMA,
    )
    op.create_check_constraint(
        _PAIR_CONSTRAINT,
        _TABLE,
        "(board_frame_quads IS NULL AND symbol_grid_quads IS NULL) OR "
        "(board_frame_quads IS NOT NULL AND symbol_grid_quads IS NOT NULL "
        "AND jsonb_typeof(board_frame_quads) = 'array' "
        "AND jsonb_typeof(symbol_grid_quads) = 'array' "
        "AND jsonb_array_length(board_frame_quads) = jsonb_array_length(final_quads) "
        "AND jsonb_array_length(symbol_grid_quads) = jsonb_array_length(final_quads))",
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.execute(f"LOCK TABLE {_SCHEMA}.{_TABLE} IN ACCESS EXCLUSIVE MODE")
    op.execute(
        f"""
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM {_SCHEMA}.{_TABLE}
            WHERE board_frame_quads IS NOT NULL OR symbol_grid_quads IS NOT NULL
          ) THEN
            RAISE EXCEPTION 'V12_GAME_DATA_V2_PAGE_FRAME_GRID_PAIRS_DOWNGRADE_HAS_DATA';
          END IF;
        END $$;
        """
    )
    op.drop_constraint(_PAIR_CONSTRAINT, _TABLE, schema=_SCHEMA, type_="check")
    op.drop_column(_TABLE, "symbol_grid_quads", schema=_SCHEMA)
    op.drop_column(_TABLE, "board_frame_quads", schema=_SCHEMA)
