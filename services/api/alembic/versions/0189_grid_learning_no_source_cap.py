"""Remove arbitrary source cardinality limits from correction learning."""

from alembic import op
from game_predictor_api.storage.source_recording_unlimited_sources import (
    remove_source_cap,
    restore_source_cap,
)

revision = "0189_grid_learning_no_source_cap"
down_revision = "0188_grid_learning_source_limit"
branch_labels = depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    remove_source_cap(op.get_bind())


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    restore_source_cap(op.get_bind())
