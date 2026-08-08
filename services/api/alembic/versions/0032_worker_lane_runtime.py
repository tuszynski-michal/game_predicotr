"""Persist diagnostic runtime state for local worker lanes.

Revision ID: 0032_worker_lane_runtime
Revises: 0031_job_execution_lanes
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032_worker_lane_runtime"
down_revision: str | Sequence[str] | None = "0031_job_execution_lanes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_lane_runtime",
        sa.Column("lane", sa.String(length=32), nullable=False),
        sa.Column("instance_token", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", sa.String(length=200), nullable=False),
        sa.Column("worker_version", sa.String(length=100), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("thread_budget", sa.SmallInteger(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "lane IN ('general', 'image_selection')",
            name="ck_worker_lane_runtime_lane",
        ),
        sa.CheckConstraint(
            "process_id > 0",
            name="ck_worker_lane_runtime_process_id_positive",
        ),
        sa.CheckConstraint(
            "thread_budget BETWEEN 1 AND 64",
            name="ck_worker_lane_runtime_thread_budget",
        ),
        sa.CheckConstraint(
            "heartbeat_at >= started_at",
            name="ck_worker_lane_runtime_heartbeat_order",
        ),
        sa.CheckConstraint(
            "stopped_at IS NULL OR stopped_at >= started_at",
            name="ck_worker_lane_runtime_stopped_order",
        ),
        sa.PrimaryKeyConstraint("lane", name="pk_worker_lane_runtime"),
    )


def downgrade() -> None:
    op.drop_table("worker_lane_runtime")
