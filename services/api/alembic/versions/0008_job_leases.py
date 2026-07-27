"""Add fenced leases and resumable checkpoints to jobs.

Revision ID: 0008_job_leases
Revises: 0007_jobs
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_job_leases"
down_revision: str | Sequence[str] | None = "0007_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("checkpoint_payload", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column("execution_slot", sa.SmallInteger(), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("lease_owner", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "lease_token",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "lease_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_jobs_attempt_count_nonnegative",
        "jobs",
        "attempt_count >= 0",
    )
    op.create_check_constraint(
        "ck_jobs_processing_lease_fields",
        "jobs",
        "(status = 'processing' AND execution_slot = 1 "
        "AND lease_owner IS NOT NULL AND lease_token IS NOT NULL "
        "AND lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL) "
        "OR (status <> 'processing' AND execution_slot IS NULL "
        "AND lease_owner IS NULL AND lease_token IS NULL "
        "AND lease_expires_at IS NULL AND heartbeat_at IS NULL)",
    )
    op.create_unique_constraint(
        "uq_jobs_execution_slot",
        "jobs",
        ["execution_slot"],
    )
    op.create_index(
        "ix_jobs_status_lease_expires",
        "jobs",
        ["status", "lease_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_status_lease_expires", table_name="jobs")
    op.drop_constraint("uq_jobs_execution_slot", "jobs", type_="unique")
    op.drop_constraint(
        "ck_jobs_processing_lease_fields",
        "jobs",
        type_="check",
    )
    op.drop_constraint(
        "ck_jobs_attempt_count_nonnegative",
        "jobs",
        type_="check",
    )
    op.drop_column("jobs", "heartbeat_at")
    op.drop_column("jobs", "lease_expires_at")
    op.drop_column("jobs", "lease_token")
    op.drop_column("jobs", "lease_owner")
    op.drop_column("jobs", "execution_slot")
    op.drop_column("jobs", "attempt_count")
    op.drop_column("jobs", "checkpoint_payload")
