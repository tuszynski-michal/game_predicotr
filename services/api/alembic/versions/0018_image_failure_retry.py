"""Add job-local image workflow, retry metadata and review events.

Revision ID: 0018_image_failure_retry
Revises: 0017_image_processing
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_image_failure_retry"
down_revision: str | Sequence[str] | None = "0017_image_processing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "image_file_executions",
        sa.Column("failed_stage", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "image_file_executions",
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "image_file_executions",
        sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE image_file_executions
        SET failed_stage = COALESCE(checkpoint_payload ->> 'nextStage', 'discovery'),
            error_code = COALESCE(error_code, 'IMAGE_FILE_LEGACY_FAILURE'),
            error_message = COALESCE(
                error_message,
                'Legacy image execution failed before structured failure metadata.'
            ),
            last_failed_at = updated_at
        WHERE status = 'failed'
        """
    )
    op.create_check_constraint(
        "ck_image_file_executions_retry_nonnegative",
        "image_file_executions",
        "retry_count >= 0",
    )
    op.create_check_constraint(
        "ck_image_file_executions_failure_state",
        "image_file_executions",
        "(status = 'failed' AND failed_stage IS NOT NULL "
        "AND error_code IS NOT NULL AND error_message IS NOT NULL "
        "AND last_failed_at IS NOT NULL) OR "
        "(status <> 'failed' AND failed_stage IS NULL "
        "AND error_code IS NULL AND error_message IS NULL "
        "AND last_failed_at IS NULL)",
    )

    op.add_column(
        "image_import_job_files",
        sa.Column("workflow_checkpoint_payload", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "image_import_job_files",
        sa.Column("workflow_status", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "image_import_job_files",
        sa.Column(
            "review_required",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "image_import_job_files",
        sa.Column("failed_stage", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "image_import_job_files",
        sa.Column("error_code", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "image_import_job_files",
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "image_import_job_files",
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "image_import_job_files",
        sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "image_import_job_files",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE image_import_job_files AS job_file
        SET workflow_checkpoint_payload = execution.checkpoint_payload,
            workflow_status = execution.status,
            review_required = execution.review_required,
            failed_stage = execution.failed_stage,
            error_code = execution.error_code,
            error_message = execution.error_message,
            retry_count = execution.retry_count,
            last_failed_at = execution.last_failed_at,
            updated_at = execution.updated_at
        FROM image_file_executions AS execution
        WHERE execution.file_execution_key = job_file.file_execution_key
        """
    )
    op.alter_column(
        "image_import_job_files",
        "workflow_checkpoint_payload",
        existing_type=postgresql.JSONB(),
        nullable=False,
    )
    op.alter_column(
        "image_import_job_files",
        "workflow_status",
        existing_type=sa.String(length=30),
        nullable=False,
    )
    op.create_check_constraint(
        "ck_image_import_job_files_workflow_status",
        "image_import_job_files",
        "workflow_status IN ('processing', 'waiting_for_review', 'completed', 'failed')",
    )
    op.create_check_constraint(
        "ck_image_import_job_files_retry_nonnegative",
        "image_import_job_files",
        "retry_count >= 0",
    )
    op.create_check_constraint(
        "ck_image_import_job_files_failure_state",
        "image_import_job_files",
        "(workflow_status = 'failed' AND failed_stage IS NOT NULL "
        "AND error_code IS NOT NULL AND error_message IS NOT NULL "
        "AND last_failed_at IS NOT NULL) OR "
        "(workflow_status <> 'failed' AND failed_stage IS NULL "
        "AND error_code IS NULL AND error_message IS NULL "
        "AND last_failed_at IS NULL)",
    )
    op.create_index(
        "ix_image_import_job_files_job_workflow",
        "image_import_job_files",
        ["job_id", "workflow_status", "order_index"],
        unique=False,
    )

    op.drop_constraint(
        "ck_image_review_items_resolution_state",
        "image_review_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_review_items_resolution_state",
        "image_review_items",
        "(status = 'pending' AND resolved_value IS NULL "
        "AND resolved_by IS NULL AND resolved_at IS NULL "
        "AND resolution_revision >= 0) OR "
        "(status <> 'pending' AND resolved_value IS NOT NULL "
        "AND resolved_by IS NOT NULL AND resolved_at IS NOT NULL "
        "AND resolution_revision > 0)",
    )
    op.create_table(
        "image_review_resolution_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("command_sha256", sa.String(length=64), nullable=False),
        sa.Column("resolved_value", postgresql.JSONB(), nullable=False),
        sa.Column("resolved_by", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "revision > 0",
            name="ck_image_review_resolution_events_revision",
        ),
        sa.CheckConstraint(
            "action IN ('accepted', 'corrected', 'rejected', 'reopened')",
            name="ck_image_review_resolution_events_action",
        ),
        sa.CheckConstraint(
            "command_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_review_resolution_events_command",
        ),
        sa.ForeignKeyConstraint(
            ["review_item_id"],
            ["image_review_items.id"],
            name="fk_image_review_resolution_events_item",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_image_review_resolution_events"),
        sa.UniqueConstraint(
            "review_item_id",
            "revision",
            name="uq_image_review_resolution_events_item_revision",
        ),
        sa.UniqueConstraint(
            "review_item_id",
            "idempotency_key",
            name="uq_image_review_resolution_events_item_idempotency",
        ),
    )


def downgrade() -> None:
    op.drop_table("image_review_resolution_events")
    op.drop_constraint(
        "ck_image_review_items_resolution_state",
        "image_review_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_review_items_resolution_state",
        "image_review_items",
        "(status = 'pending' AND resolved_value IS NULL "
        "AND resolved_by IS NULL AND resolved_at IS NULL "
        "AND resolution_revision = 0) OR "
        "(status <> 'pending' AND resolved_value IS NOT NULL "
        "AND resolved_by IS NOT NULL AND resolved_at IS NOT NULL "
        "AND resolution_revision > 0)",
    )

    op.drop_index(
        "ix_image_import_job_files_job_workflow",
        table_name="image_import_job_files",
    )
    op.drop_constraint(
        "ck_image_import_job_files_failure_state",
        "image_import_job_files",
        type_="check",
    )
    op.drop_constraint(
        "ck_image_import_job_files_retry_nonnegative",
        "image_import_job_files",
        type_="check",
    )
    op.drop_constraint(
        "ck_image_import_job_files_workflow_status",
        "image_import_job_files",
        type_="check",
    )
    for column in (
        "updated_at",
        "last_failed_at",
        "retry_count",
        "error_message",
        "error_code",
        "failed_stage",
        "review_required",
        "workflow_status",
        "workflow_checkpoint_payload",
    ):
        op.drop_column("image_import_job_files", column)

    op.drop_constraint(
        "ck_image_file_executions_failure_state",
        "image_file_executions",
        type_="check",
    )
    op.drop_constraint(
        "ck_image_file_executions_retry_nonnegative",
        "image_file_executions",
        type_="check",
    )
    op.drop_column("image_file_executions", "last_failed_at")
    op.drop_column("image_file_executions", "retry_count")
    op.drop_column("image_file_executions", "failed_stage")
