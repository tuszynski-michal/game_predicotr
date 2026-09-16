"""Persist global semi-automatic image-selection runs and expected ranges.

Revision ID: 0087_semi_automatic_image_selection
Revises: 0086_partial_page_geometry_overrides
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0087_semi_automatic_image_selection"
down_revision: str | Sequence[str] | None = "0086_partial_page_geometry_overrides"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PostgreSQL cannot safely use a new enum label in a constraint until the
    # ALTER TYPE transaction is committed. Alembic's autocommit block keeps the
    # following additive DDL valid on both fresh and upgraded databases.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'semi_automatic_image_selection'")
    op.drop_constraint("ck_jobs_processing_lease_fields", "jobs", type_="check")
    op.create_check_constraint(
        "ck_jobs_processing_lease_fields",
        "jobs",
        "(status = 'processing' AND "
        "((job_type IN ('image_selection', 'semi_automatic_image_selection') "
        "AND execution_slot = 2) OR "
        "(job_type NOT IN ('image_selection', 'semi_automatic_image_selection') "
        "AND execution_slot = 1)) AND "
        "lease_owner IS NOT NULL AND lease_token IS NOT NULL AND "
        "lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL) OR "
        "(status <> 'processing' AND execution_slot IS NULL AND lease_owner IS NULL AND "
        "lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL)",
    )

    op.create_table(
        "semi_automatic_image_selection_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("source_upload_id", sa.Uuid(), nullable=False),
        sa.Column("source_display_name", sa.String(length=200), nullable=False),
        sa.Column("source_manifest_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("source_count", sa.BigInteger(), nullable=False),
        sa.Column("source_total_bytes", sa.BigInteger(), nullable=False),
        sa.Column("first_sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("last_sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("range_convention", sa.String(length=40), nullable=False),
        sa.Column("full_range_size", sa.SmallInteger(), nullable=False),
        sa.Column("expected_ranges_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("recognizer_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("grouping_policy_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("identity_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "checkpoint",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "counters",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("diagnostics_relative_path", sa.String(length=1000), nullable=True),
        sa.Column("diagnostics_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("revision", sa.Integer(), server_default=sa.text("0"), nullable=False),
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
            "source_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$' AND "
            "source_fingerprint ~ '^[0-9a-f]{64}$' AND "
            "expected_ranges_fingerprint ~ '^[0-9a-f]{64}$' AND "
            "recognizer_fingerprint ~ '^[0-9a-f]{64}$' AND "
            "grouping_policy_fingerprint ~ '^[0-9a-f]{64}$' AND "
            "identity_key ~ '^[0-9a-f]{64}$' AND "
            "(diagnostics_checksum_sha256 IS NULL OR "
            "diagnostics_checksum_sha256 ~ '^[0-9a-f]{64}$')",
            name="ck_semi_automatic_selection_runs_checksums",
        ),
        sa.CheckConstraint(
            "source_count > 0 AND source_total_bytes > 0 AND "
            "first_sequence_number > 0 AND last_sequence_number >= first_sequence_number AND "
            "full_range_size = 9 AND revision >= 0",
            name="ck_semi_automatic_selection_runs_bounds",
        ),
        sa.CheckConstraint(
            "direction IN ('ascending', 'descending') AND "
            "range_convention = 'seq-inclusive-v1'",
            name="ck_semi_automatic_selection_runs_contract",
        ),
        sa.CheckConstraint(
            "status IN ('ready', 'running', 'paused', 'analysis_complete', "
            "'syncing_output', 'review_mode', 'edit_source_mode', 'completed', "
            "'failed', 'cancelled')",
            name="ck_semi_automatic_selection_runs_status",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(checkpoint) = 'object' AND jsonb_typeof(counters) = 'object'",
            name="ck_semi_automatic_selection_runs_json",
        ),
        sa.CheckConstraint(
            "length(btrim(source_display_name)) > 0 AND "
            "(diagnostics_relative_path IS NULL OR "
            "(diagnostics_relative_path !~ '(^|/)\\.\\.(/|$)' AND "
            "diagnostics_relative_path !~ '^[A-Za-z]:' AND "
            "diagnostics_relative_path NOT LIKE '/%' AND "
            "diagnostics_relative_path NOT LIKE '%\\\\%'))",
            name="ck_semi_automatic_selection_runs_paths",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", name="uq_semi_automatic_selection_runs_job"),
        sa.UniqueConstraint("identity_key", name="uq_semi_automatic_selection_runs_identity"),
    )
    op.create_index(
        "ix_semi_automatic_selection_runs_status_created",
        "semi_automatic_image_selection_runs",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_semi_automatic_selection_runs_source_upload",
        "semi_automatic_image_selection_runs",
        ["source_upload_id"],
    )

    op.create_table(
        "semi_automatic_image_selection_ranges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("expected_index", sa.BigInteger(), nullable=False),
        sa.Column("range_start", sa.BigInteger(), nullable=False),
        sa.Column("range_end", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("source_index", sa.BigInteger(), nullable=True),
        sa.Column("source_relative_path", sa.String(length=1000), nullable=True),
        sa.Column("source_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("source_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("group_first_source_index", sa.BigInteger(), nullable=True),
        sa.Column("group_last_source_index", sa.BigInteger(), nullable=True),
        sa.Column("range_confidence", sa.Float(), nullable=True),
        sa.Column("selection_method", sa.String(length=80), nullable=True),
        sa.Column("output_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("revision", sa.Integer(), server_default=sa.text("0"), nullable=False),
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
            "expected_index >= 0 AND range_start > 0 AND range_end >= range_start AND "
            "range_end - range_start + 1 BETWEEN 1 AND 9 AND revision >= 0",
            name="ck_semi_automatic_selection_ranges_bounds",
        ),
        sa.CheckConstraint(
            "status IN ('missing', 'auto_selected', 'output_synced', 'conflict')",
            name="ck_semi_automatic_selection_ranges_status",
        ),
        sa.CheckConstraint(
            "(source_index IS NULL AND source_relative_path IS NULL AND "
            "source_size_bytes IS NULL AND source_checksum_sha256 IS NULL) OR "
            "(source_index >= 0 AND source_relative_path IS NOT NULL AND "
            "source_size_bytes > 0 AND source_checksum_sha256 ~ '^[0-9a-f]{64}$')",
            name="ck_semi_automatic_selection_ranges_source",
        ),
        sa.CheckConstraint(
            "(group_first_source_index IS NULL AND group_last_source_index IS NULL) OR "
            "(group_first_source_index >= 0 AND "
            "group_last_source_index >= group_first_source_index)",
            name="ck_semi_automatic_selection_ranges_group",
        ),
        sa.CheckConstraint(
            "range_confidence IS NULL OR range_confidence BETWEEN 0 AND 1",
            name="ck_semi_automatic_selection_ranges_confidence",
        ),
        sa.CheckConstraint(
            "output_checksum_sha256 IS NULL OR output_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_semi_automatic_selection_ranges_output_checksum",
        ),
        sa.CheckConstraint(
            "source_relative_path IS NULL OR "
            "(source_relative_path !~ '(^|/)\\.\\.(/|$)' AND "
            "source_relative_path !~ '^[A-Za-z]:' AND "
            "source_relative_path NOT LIKE '/%' AND "
            "source_relative_path NOT LIKE '%\\\\%')",
            name="ck_semi_automatic_selection_ranges_path",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["semi_automatic_image_selection_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id", "expected_index", name="uq_semi_automatic_selection_ranges_index"
        ),
        sa.UniqueConstraint(
            "run_id", "range_start", "range_end", name="uq_semi_automatic_selection_ranges_range"
        ),
    )
    op.create_index(
        "ix_semi_automatic_selection_ranges_run_status_index",
        "semi_automatic_image_selection_ranges",
        ["run_id", "status", "expected_index"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_semi_automatic_selection_ranges_run_status_index",
        table_name="semi_automatic_image_selection_ranges",
    )
    op.drop_table("semi_automatic_image_selection_ranges")
    op.drop_index(
        "ix_semi_automatic_selection_runs_source_upload",
        table_name="semi_automatic_image_selection_runs",
    )
    op.drop_index(
        "ix_semi_automatic_selection_runs_status_created",
        table_name="semi_automatic_image_selection_runs",
    )
    op.drop_table("semi_automatic_image_selection_runs")
    op.drop_constraint("ck_jobs_processing_lease_fields", "jobs", type_="check")
    op.create_check_constraint(
        "ck_jobs_processing_lease_fields",
        "jobs",
        "(status = 'processing' AND "
        "((job_type = 'image_selection' AND execution_slot = 2) OR "
        "(job_type <> 'image_selection' AND execution_slot = 1)) AND "
        "lease_owner IS NOT NULL AND lease_token IS NOT NULL AND "
        "lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL) OR "
        "(status <> 'processing' AND execution_slot IS NULL AND lease_owner IS NULL AND "
        "lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL)",
    )
    # PostgreSQL enum labels are retained to preserve historical job payloads.
