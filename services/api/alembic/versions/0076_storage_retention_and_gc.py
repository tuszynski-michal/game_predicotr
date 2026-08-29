"""Persist storage retention previews, inventory and staging lifecycle.

Revision ID: 0076_storage_retention_and_gc
Revises: 0075_remove_obsolete_board_search_storage
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0076_storage_retention_and_gc"
down_revision: str | Sequence[str] | None = "0075_remove_obsolete_board_search_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'storage_gc'")

    op.create_table(
        "storage_gc_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("retention_hours", sa.Integer(), nullable=False),
        sa.Column("manifest_relative_path", sa.Text(), nullable=False),
        sa.Column("manifest_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("preview_token", sa.String(length=64), nullable=False),
        sa.Column("candidate_count", sa.BigInteger(), nullable=False),
        sa.Column("candidate_bytes", sa.BigInteger(), nullable=False),
        sa.Column("protected_count", sa.BigInteger(), nullable=False),
        sa.Column("protected_bytes", sa.BigInteger(), nullable=False),
        sa.Column("deleted_count", sa.BigInteger(), nullable=False),
        sa.Column("deleted_bytes", sa.BigInteger(), nullable=False),
        sa.Column("conflict_count", sa.BigInteger(), nullable=False),
        sa.Column("failed_count", sa.BigInteger(), nullable=False),
        sa.Column("checkpoint_index", sa.BigInteger(), nullable=False),
        sa.Column("inventory_before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("inventory_after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("mode IN ('manual', 'automatic')", name="ck_storage_gc_runs_mode"),
        sa.CheckConstraint(
            "status IN ('previewed', 'created', 'processing', 'completed', 'failed', 'cancelled')",
            name="ck_storage_gc_runs_status",
        ),
        sa.CheckConstraint(
            "retention_hours > 0 AND candidate_count >= 0 AND candidate_bytes >= 0 "
            "AND protected_count >= 0 AND protected_bytes >= 0 "
            "AND deleted_count >= 0 AND deleted_bytes >= 0 "
            "AND conflict_count >= 0 AND failed_count >= 0 AND checkpoint_index >= 0",
            name="ck_storage_gc_runs_counters",
        ),
        sa.CheckConstraint(
            "manifest_checksum_sha256 ~ '^[0-9a-f]{64}$' AND preview_token ~ '^[0-9a-f]{64}$'",
            name="ck_storage_gc_runs_checksums",
        ),
        sa.CheckConstraint(
            "length(btrim(policy_version)) > 0 AND length(btrim(manifest_relative_path)) > 0",
            name="ck_storage_gc_runs_required_text",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", name="uq_storage_gc_runs_job"),
    )
    op.create_index(
        "ix_storage_gc_runs_status_created",
        "storage_gc_runs",
        ["status", "created_at"],
    )

    op.create_table(
        "storage_usage_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("root_kind", sa.String(length=16), nullable=False),
        sa.Column("namespace", sa.String(length=100), nullable=True),
        sa.Column("volume_id", sa.String(length=255), nullable=False),
        sa.Column("measurement_source", sa.String(length=20), nullable=False),
        sa.Column("file_count", sa.BigInteger(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("free_bytes", sa.BigInteger(), nullable=True),
        sa.Column("total_bytes", sa.BigInteger(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "root_kind IN ('artifact', 'import', 'database', 'docker')",
            name="ck_storage_usage_snapshots_root_kind",
        ),
        sa.CheckConstraint(
            "measurement_source IN ('scan', 'accounting', 'database', 'filesystem')",
            name="ck_storage_usage_snapshots_measurement_source",
        ),
        sa.CheckConstraint(
            "file_count >= 0 AND size_bytes >= 0 "
            "AND (free_bytes IS NULL OR free_bytes >= 0) "
            "AND (total_bytes IS NULL OR total_bytes >= 0)",
            name="ck_storage_usage_snapshots_counters",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_storage_usage_snapshots_root_measured",
        "storage_usage_snapshots",
        ["root_kind", "measured_at"],
    )

    op.create_table(
        "browser_selection_retention_states",
        sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=True),
        sa.Column("import_job_id", sa.Uuid(), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("manifest_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("managed_manifest_relative_path", sa.Text(), nullable=True),
        sa.Column("managed_manifest_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_dependency_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("eligible_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("blocked_reason", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('ready', 'in_use', 'ingested', 'cleanup_eligible', 'blocked')",
            name="ck_browser_selection_retention_state",
        ),
        sa.CheckConstraint(
            "manifest_checksum_sha256 ~ '^[0-9a-f]{64}$' "
            "AND (managed_manifest_checksum_sha256 IS NULL OR "
            "managed_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$')",
            name="ck_browser_selection_retention_checksums",
        ),
        sa.CheckConstraint(
            "(managed_manifest_relative_path IS NULL) = (managed_manifest_checksum_sha256 IS NULL)",
            name="ck_browser_selection_retention_managed_manifest",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["import_job_id"], ["jobs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("upload_id"),
    )
    op.create_index(
        "ix_browser_selection_retention_state_eligible",
        "browser_selection_retention_states",
        ["state", "eligible_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_browser_selection_retention_state_eligible",
        table_name="browser_selection_retention_states",
    )
    op.drop_table("browser_selection_retention_states")
    op.drop_index(
        "ix_storage_usage_snapshots_root_measured",
        table_name="storage_usage_snapshots",
    )
    op.drop_table("storage_usage_snapshots")
    op.drop_index("ix_storage_gc_runs_status_created", table_name="storage_gc_runs")
    op.drop_table("storage_gc_runs")
    # PostgreSQL enum values cannot be removed safely. Keeping storage_gc makes
    # downgrade non-destructive for historical job rows.
