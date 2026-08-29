"""Add durable storage inventory job type.

Revision ID: 0078_storage_inventory_job
Revises: 0077_storage_capacity_guard
"""

from alembic import op

revision = "0078_storage_inventory_job"
down_revision = "0077_storage_capacity_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'storage_inventory'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely while historical jobs exist.
    pass
