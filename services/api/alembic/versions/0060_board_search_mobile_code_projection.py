"""Materialize compact mobile-code arrays for fast partial-board scoring.

Revision ID: 0060_board_search_mobile_code_projection
Revises: 0059_board_search_known_evidence_positions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0060_board_search_mobile_code_projection"
down_revision: str | Sequence[str] | None = "0059_board_search_known_evidence_positions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MOBILE_CODE_COLUMNS = (
    "primary_symbol_mobile_codes",
    "alternative_rank_1_mobile_codes",
    "alternative_rank_2_mobile_codes",
    "alternative_rank_3_mobile_codes",
    "alternative_rank_4_mobile_codes",
)


def upgrade() -> None:
    for column_name in _MOBILE_CODE_COLUMNS:
        op.add_column(
            "image_board_search_candidates",
            sa.Column(column_name, postgresql.ARRAY(sa.SmallInteger()), nullable=True),
        )
    _backfill_mobile_codes(
        "primary_symbol_mobile_codes", "candidate.primary_symbol_codes ->> position"
    )
    for rank, column_name in enumerate(_MOBILE_CODE_COLUMNS[1:]):
        _backfill_mobile_codes(
            column_name,
            f"candidate.alternative_symbol_codes -> position ->> {rank}",
        )
    for column_name in _MOBILE_CODE_COLUMNS:
        op.alter_column("image_board_search_candidates", column_name, nullable=False)


def downgrade() -> None:
    for column_name in reversed(_MOBILE_CODE_COLUMNS):
        op.drop_column("image_board_search_candidates", column_name)


def _backfill_mobile_codes(column_name: str, symbol_code_expression: str) -> None:
    op.execute(
        f"""
        UPDATE image_board_search_candidates AS candidate
        SET {column_name} = ARRAY(
            SELECT symbol.mobile_code
            FROM generate_series(0, 14) AS generated(position)
            LEFT JOIN symbols AS symbol
              ON symbol.game_id = candidate.game_id
             AND symbol.code = {symbol_code_expression}
            ORDER BY position
        )
        """
    )
