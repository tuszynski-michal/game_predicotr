"""Create durable administrative jobs.

Revision ID: 0007_jobs
Revises: 0006_dataset_staging
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_jobs"
down_revision: str | Sequence[str] | None = "0006_dataset_staging"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    job_type = postgresql.ENUM(
        "import",
        "validate",
        "payout",
        "snapshot",
        "android_build",
        name="job_type",
        create_type=False,
    )
    job_status = postgresql.ENUM(
        "created",
        "processing",
        "waiting_for_review",
        "completed",
        "failed",
        "cancelled",
        name="job_status",
        create_type=False,
    )
    job_type.create(op.get_bind(), checkfirst=True)
    job_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_type", job_type, nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            job_status,
            server_default="created",
            nullable=False,
        ),
        sa.Column("input_payload", postgresql.JSONB(), nullable=False),
        sa.Column("input_key", sa.String(length=64), nullable=False),
        sa.Column("stage", sa.String(length=100), nullable=True),
        sa.Column(
            "progress_current",
            sa.BigInteger(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("progress_total", sa.BigInteger(), nullable=True),
        sa.Column(
            "success_count",
            sa.BigInteger(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "failure_count",
            sa.BigInteger(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "review_count",
            sa.BigInteger(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("worker_version", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cancel_requested_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            "progress_current >= 0",
            name="ck_jobs_progress_current_nonnegative",
        ),
        sa.CheckConstraint(
            "progress_total IS NULL OR progress_total >= 0",
            name="ck_jobs_progress_total_nonnegative",
        ),
        sa.CheckConstraint(
            "progress_total IS NULL OR progress_current <= progress_total",
            name="ck_jobs_progress_within_total",
        ),
        sa.CheckConstraint(
            "success_count >= 0 AND failure_count >= 0 AND review_count >= 0",
            name="ck_jobs_outcome_counts_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
            name="fk_jobs_game_id_games",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
        sa.UniqueConstraint("input_key", name="uq_jobs_input_key"),
    )
    op.create_index("ix_jobs_game_id", "jobs", ["game_id"], unique=False)
    op.create_index(
        "ix_jobs_status_created_at",
        "jobs",
        ["status", "created_at"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_dataset_versions_source_job_id_jobs",
        "dataset_versions",
        "jobs",
        ["source_job_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_dataset_versions_source_job_id_jobs",
        "dataset_versions",
        type_="foreignkey",
    )
    op.drop_index("ix_jobs_status_created_at", table_name="jobs")
    op.drop_index("ix_jobs_game_id", table_name="jobs")
    op.drop_table("jobs")
    postgresql.ENUM(name="job_status", create_type=False).drop(
        op.get_bind(),
        checkfirst=True,
    )
    postgresql.ENUM(name="job_type", create_type=False).drop(
        op.get_bind(),
        checkfirst=True,
    )
