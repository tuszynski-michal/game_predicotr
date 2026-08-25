"""Index known evidence positions for partial-board mismatch ranking.

Revision ID: 0059_board_search_known_evidence_positions
Revises: 0058_board_search_projection_state
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0059_board_search_known_evidence_positions"
down_revision: str | Sequence[str] | None = "0058_board_search_projection_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "image_board_search_candidates",
        sa.Column(
            "known_evidence_positions",
            postgresql.ARRAY(sa.String(length=2)),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE image_board_search_candidates AS candidate
        SET known_evidence_positions = ARRAY(
            SELECT position::text
            FROM generate_series(0, 14) AS generated(position)
            WHERE
                COALESCE(candidate.primary_symbol_codes ->> position, '') NOT IN ('', '?')
                OR (
                    candidate.status = 'pending'
                    AND (
                        COALESCE(
                            candidate.alternative_symbol_codes -> position ->> 0,
                            ''
                        ) NOT IN ('', '?')
                        OR COALESCE(
                            candidate.alternative_symbol_codes -> position ->> 1,
                            ''
                        ) NOT IN ('', '?')
                        OR COALESCE(
                            candidate.alternative_symbol_codes -> position ->> 2,
                            ''
                        ) NOT IN ('', '?')
                        OR COALESCE(
                            candidate.alternative_symbol_codes -> position ->> 3,
                            ''
                        ) NOT IN ('', '?')
                    )
                )
            ORDER BY position
        )
        """
    )
    op.alter_column(
        "image_board_search_candidates",
        "known_evidence_positions",
        nullable=False,
    )
    op.create_index(
        "ix_ibsc_known_evidence_positions_gin",
        "image_board_search_candidates",
        ["known_evidence_positions"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ibsc_known_evidence_positions_gin",
        table_name="image_board_search_candidates",
    )
    op.drop_column("image_board_search_candidates", "known_evidence_positions")
