"""Add durable per-file image batch orchestration.

Revision ID: 0016_image_orchestration
Revises: 0015_review_feedback
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_image_orchestration"
down_revision: str | Sequence[str] | None = "0015_review_feedback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "image_file_executions",
        sa.Column("file_execution_key", sa.String(length=64), nullable=False),
        sa.Column("source_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("pipeline_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("checkpoint_payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "review_required",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
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
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "file_execution_key ~ '^[0-9a-f]{64}$'",
            name="ck_image_file_executions_key",
        ),
        sa.CheckConstraint(
            "source_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_file_executions_source_checksum",
        ),
        sa.CheckConstraint(
            "pipeline_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_image_file_executions_pipeline_fingerprint",
        ),
        sa.CheckConstraint(
            "status IN ('processing', 'waiting_for_review', 'completed', 'failed')",
            name="ck_image_file_executions_status",
        ),
        sa.PrimaryKeyConstraint(
            "file_execution_key",
            name="pk_image_file_executions",
        ),
        sa.UniqueConstraint(
            "source_checksum_sha256",
            "pipeline_fingerprint",
            name="uq_image_file_executions_source_pipeline",
        ),
    )
    op.create_index(
        "ix_image_file_executions_pipeline_status",
        "image_file_executions",
        ["pipeline_fingerprint", "status"],
        unique=False,
    )
    op.create_table(
        "image_import_job_files",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_execution_key", sa.String(length=64), nullable=False),
        sa.Column("order_index", sa.BigInteger(), nullable=False),
        sa.Column("source_relative_path", sa.String(length=1000), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "order_index >= 0",
            name="ck_image_import_job_files_order_nonnegative",
        ),
        sa.CheckConstraint(
            "source_relative_path <> '' "
            "AND source_relative_path !~ '(^|/)\\.\\.(/|$)' "
            "AND source_relative_path !~ '^/' "
            "AND source_relative_path !~ '\\\\'",
            name="ck_image_import_job_files_relative_path",
        ),
        sa.ForeignKeyConstraint(
            ["file_execution_key"],
            ["image_file_executions.file_execution_key"],
            name="fk_image_import_job_files_execution",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name="fk_image_import_job_files_job_id_jobs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "job_id",
            "file_execution_key",
            name="pk_image_import_job_files",
        ),
        sa.UniqueConstraint(
            "job_id",
            "order_index",
            name="uq_image_import_job_files_job_order",
        ),
    )
    op.create_index(
        "ix_image_import_job_files_execution",
        "image_import_job_files",
        ["file_execution_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_image_import_job_files_execution",
        table_name="image_import_job_files",
    )
    op.drop_table("image_import_job_files")
    op.drop_index(
        "ix_image_file_executions_pipeline_status",
        table_name="image_file_executions",
    )
    op.drop_table("image_file_executions")
