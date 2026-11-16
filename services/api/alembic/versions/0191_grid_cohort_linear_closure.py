"""Batch registry contexts while preserving every cohort admission proof."""

from alembic import op
from game_predictor_api.storage.source_recording_closure_performance import (
    rewrite_closure_functions,
)

revision = "0191_grid_cohort_linear_closure"
down_revision = "0190_grid_gate_improvement"
branch_labels = depends_on = None


def _rewrite(*, restore: bool) -> None:
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.execute("SELECT pg_advisory_xact_lock(9910994)")
    op.execute("SELECT pg_advisory_xact_lock(9921002)")
    rewrite_closure_functions(op.get_bind(), restore=restore)


def upgrade() -> None:
    _rewrite(restore=False)


def downgrade() -> None:
    _rewrite(restore=True)
