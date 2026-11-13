"""Raise the grid-learning population limit to 20 000 sources (D-610)."""

from alembic import op
from game_predictor_api.storage.source_recording_source_limit import (
    raise_source_limit,
    restore_source_limit,
)

revision = "0188_grid_learning_source_limit"
down_revision = "0187_grid_gate_cell_cut"
branch_labels = depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    raise_source_limit(op.get_bind())


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    restore_source_limit(op.get_bind())
