"""Add compact terminal image-pipeline manifests.

Revision ID: 0079_pipeline_state_compaction
Revises: 0078_storage_inventory_job
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0079_pipeline_state_compaction"
down_revision: str | Sequence[str] | None = "0078_storage_inventory_job"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'storage_pipeline_compaction'"
    )
    op.create_table(
        "image_pipeline_terminal_manifests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("file_execution_key", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("manifest_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "manifest_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("stage_result_count", sa.Integer(), nullable=False),
        sa.Column("stage_result_bytes", sa.BigInteger(), nullable=False),
        sa.Column("compacted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "schema_version = 1",
            name="ck_image_pipeline_terminal_manifest_schema",
        ),
        sa.CheckConstraint(
            "manifest_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_pipeline_terminal_manifest_checksum",
        ),
        sa.CheckConstraint(
            "stage_result_count > 0 AND stage_result_bytes >= 0",
            name="ck_image_pipeline_terminal_manifest_counters",
        ),
        sa.ForeignKeyConstraint(
            ["file_execution_key"],
            ["image_file_executions.file_execution_key"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "file_execution_key",
            "manifest_checksum_sha256",
            name="uq_image_pipeline_terminal_manifest_version",
        ),
    )
    op.create_index(
        "ix_image_pipeline_terminal_manifests_compacted",
        "image_pipeline_terminal_manifests",
        ["compacted_at", "file_execution_key"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_image_pipeline_terminal_manifests_compacted",
        table_name="image_pipeline_terminal_manifests",
    )
    op.drop_table("image_pipeline_terminal_manifests")
    # Historical jobs may retain the enum value, so PostgreSQL downgrade keeps it.
