"""Prioritize one automatic storage cleanup run.

Revision ID: 0077_storage_capacity_guard
Revises: 0076_storage_retention_and_gc
"""

from alembic import op

revision = "0077_storage_capacity_guard"
down_revision = "0076_storage_retention_and_gc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_storage_gc_runs_active_automatic",
        "storage_gc_runs",
        ["mode"],
        unique=True,
        postgresql_where=(
            "mode = 'automatic' AND status IN ('previewed', 'created', 'processing')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_storage_gc_runs_active_automatic",
        table_name="storage_gc_runs",
    )
