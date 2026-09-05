"""Add the game-wide symbol-review seek index.

Revision ID: 0088_symbol_review_game_sequence_index
Revises: 0087_semi_automatic_image_selection
Create Date: 2026-09-01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0088_symbol_review_game_sequence_index"
down_revision: str | None = "0087_semi_automatic_image_selection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_image_symbol_review_cells_game_sequence",
        "image_symbol_review_cells",
        ["game_id", "sequence_number", "cell_index", "review_item_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_image_symbol_review_cells_game_sequence",
        table_name="image_symbol_review_cells",
    )
