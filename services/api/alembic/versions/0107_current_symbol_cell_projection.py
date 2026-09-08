"""Make the V2 symbol-cell table the unique current logical projection."""

from collections.abc import Sequence

from alembic import op

revision: str = "0107_current_symbol_cell_projection"
down_revision: str | Sequence[str] | None = "0106_game_storage_routing_fence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.execute(
        "ALTER TABLE game_data_v2.image_symbol_review_cells "
        "ADD CONSTRAINT uq_v2_symbol_cell_current_logical_position "
        "UNIQUE (game_id, sequence_number, cell_index)"
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.execute(
        "ALTER TABLE game_data_v2.image_symbol_review_cells "
        "DROP CONSTRAINT uq_v2_symbol_cell_current_logical_position"
    )
