"""Add durable symbol model training iterations.

Revision ID: 0035_symbol_model_training_jobs
Revises: 0034_verified_training_cohorts
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035_symbol_model_training_jobs"
down_revision: str | Sequence[str] | None = "0034_verified_training_cohorts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PostgreSQL enum values cannot be removed safely. The downgrade therefore
    # drops the feature table but deliberately keeps this harmless value.
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'symbol_training'")
    op.create_table(
        "symbol_model_iterations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("iteration_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("configuration_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("configuration_payload", postgresql.JSONB(), nullable=False),
        sa.Column("dataset_manifest_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("dataset_manifest_relative_path", sa.String(length=1000), nullable=True),
        sa.Column("checkpoint_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("checkpoint_relative_path", sa.String(length=1000), nullable=True),
        sa.Column("last_completed_epoch", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("partial_metrics", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "iteration_number > 0 AND last_completed_epoch >= 0",
            name="ck_symbol_model_iterations_numbers",
        ),
        sa.CheckConstraint(
            "status IN ('created','dataset_build','training','trained','failed','cancelled')",
            name="ck_symbol_model_iterations_status",
        ),
        sa.CheckConstraint(
            "configuration_fingerprint ~ '^[0-9a-f]{64}$' "
            "AND (dataset_manifest_checksum_sha256 IS NULL OR dataset_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$') "
            "AND (checkpoint_checksum_sha256 IS NULL OR checkpoint_checksum_sha256 ~ '^[0-9a-f]{64}$')",
            name="ck_symbol_model_iterations_sha256",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cohort_id"], ["verified_training_cohorts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "iteration_number", name="uq_symbol_model_iterations_number"),
        sa.UniqueConstraint("job_id", name="uq_symbol_model_iterations_job"),
        sa.UniqueConstraint(
            "game_id", "cohort_id", "configuration_fingerprint",
            name="uq_symbol_model_iterations_input",
        ),
    )
    op.create_index(
        "ix_symbol_model_iterations_game_status",
        "symbol_model_iterations",
        ["game_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_symbol_model_iterations_game_status", table_name="symbol_model_iterations")
    op.drop_table("symbol_model_iterations")
