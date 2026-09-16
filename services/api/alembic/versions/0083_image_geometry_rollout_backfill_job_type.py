"""Restore PostgreSQL enum compatibility for the geometry rollout worker.

Revision ID: 0083_image_geometry_rollout_backfill_job_type
Revises: 0082_virtual_geometry_foundation
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0083_image_geometry_rollout_backfill_job_type"
down_revision: str | Sequence[str] | None = "0082_virtual_geometry_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ``GENERAL_JOB_TYPES`` is built from the full domain enum.  PostgreSQL
    # rejects the worker's claim query until this value exists in ``job_type``.
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'image_geometry_rollout_backfill'")


def downgrade() -> None:
    # PostgreSQL enums do not support safe removal of a value.  Keeping the
    # unused label is harmless and avoids a destructive type/table rewrite.
    pass
