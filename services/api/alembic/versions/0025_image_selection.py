"""Add durable image selection runs, groups and candidates.

Revision ID: 0025_image_selection
Revises: 0024_cleanup_operations
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025_image_selection"
down_revision: str | Sequence[str] | None = "0024_cleanup_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JOB_TYPES_WITHOUT_IMAGE_SELECTION = (
    "import",
    "validate",
    "payout",
    "snapshot",
    "android_build",
)


def upgrade() -> None:
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'image_selection'")

    op.create_table(
        "image_selection_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_selection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("input_manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("selector_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("ordering_policy", sa.String(length=100), nullable=False),
        sa.Column(
            "contract_version",
            sa.SmallInteger(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("output_manifest_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "output_manifest_relative_path",
            sa.String(length=1000),
            nullable=True,
        ),
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
        sa.CheckConstraint(
            "input_manifest_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_selection_runs_input_manifest_sha256",
        ),
        sa.CheckConstraint(
            "selector_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_image_selection_runs_selector_fingerprint",
        ),
        sa.CheckConstraint(
            "contract_version = 1",
            name="ck_image_selection_runs_contract_version",
        ),
        sa.CheckConstraint(
            "ordering_policy = 'natural_relative_path_v1'",
            name="ck_image_selection_runs_ordering_policy",
        ),
        sa.CheckConstraint(
            "(output_manifest_sha256 IS NULL AND "
            "output_manifest_relative_path IS NULL) OR "
            "(output_manifest_sha256 ~ '^[0-9a-f]{64}$' AND "
            "output_manifest_relative_path IS NOT NULL)",
            name="ck_image_selection_runs_output_manifest_state",
        ),
        sa.CheckConstraint(
            "output_manifest_relative_path IS NULL OR "
            "(output_manifest_relative_path !~ '(^|/)\\.\\.(/|$)' AND "
            "output_manifest_relative_path !~ '^[A-Za-z]:' AND "
            "output_manifest_relative_path NOT LIKE '/%' AND "
            "output_manifest_relative_path NOT LIKE '%\\\\%')",
            name="ck_image_selection_runs_output_path_safe",
        ),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
            name="fk_image_selection_runs_game_id_games",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name="fk_image_selection_runs_job_id_jobs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_image_selection_runs"),
        sa.UniqueConstraint("job_id", name="uq_image_selection_runs_job_id"),
        sa.UniqueConstraint(
            "source_selection_id",
            name="uq_image_selection_runs_source_selection_id",
        ),
        sa.UniqueConstraint(
            "game_id",
            "input_manifest_sha256",
            "selector_fingerprint",
            name="uq_image_selection_runs_identity",
        ),
    )
    op.create_index(
        "ix_image_selection_runs_game_created",
        "image_selection_runs",
        ["game_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "image_selection_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group_order", sa.BigInteger(), nullable=False),
        sa.Column("range_start", sa.BigInteger(), nullable=True),
        sa.Column("range_end", sa.BigInteger(), nullable=True),
        sa.Column("fingerprint_sha256", sa.String(length=64), nullable=True),
        sa.Column("board_count_consensus", sa.SmallInteger(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=40),
            server_default=sa.text("'collecting'"),
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "group_order >= 0",
            name="ck_image_selection_groups_order_nonnegative",
        ),
        sa.CheckConstraint(
            "(range_start IS NULL AND range_end IS NULL) OR "
            "(range_start >= 1 AND range_end >= range_start)",
            name="ck_image_selection_groups_range",
        ),
        sa.CheckConstraint(
            "fingerprint_sha256 IS NULL OR fingerprint_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_selection_groups_fingerprint_sha256",
        ),
        sa.CheckConstraint(
            "board_count_consensus IS NULL OR board_count_consensus BETWEEN 1 AND 9",
            name="ck_image_selection_groups_board_count",
        ),
        sa.CheckConstraint(
            "status IN ('collecting', 'auto_selected', 'manual_required', "
            "'manually_selected', 'skipped_existing_range')",
            name="ck_image_selection_groups_status",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["image_selection_runs.id"],
            name="fk_image_selection_groups_run_id_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_image_selection_groups"),
        sa.UniqueConstraint(
            "run_id",
            "group_order",
            name="uq_image_selection_groups_run_order",
        ),
        sa.UniqueConstraint(
            "run_id",
            "id",
            name="uq_image_selection_groups_run_id_id",
        ),
    )
    op.create_index(
        "uq_image_selection_groups_selected_range",
        "image_selection_groups",
        ["run_id", "range_start", "range_end"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('auto_selected', 'manually_selected') AND range_start IS NOT NULL"
        ),
    )

    op.create_table(
        "image_selection_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("order_index", sa.BigInteger(), nullable=False),
        sa.Column("source_relative_path", sa.String(length=1000), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column(
            "quality_metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("range_confidence", sa.Float(), nullable=True),
        sa.Column(
            "reason_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("decision", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "order_index >= 0",
            name="ck_image_selection_candidates_order_nonnegative",
        ),
        sa.CheckConstraint(
            "source_relative_path !~ '(^|/)\\.\\.(/|$)' AND "
            "source_relative_path !~ '^[A-Za-z]:' AND "
            "source_relative_path NOT LIKE '/%' AND "
            "source_relative_path NOT LIKE '%\\\\%'",
            name="ck_image_selection_candidates_source_path_safe",
        ),
        sa.CheckConstraint(
            "checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_selection_candidates_checksum_sha256",
        ),
        sa.CheckConstraint(
            "width >= 1 AND height >= 1",
            name="ck_image_selection_candidates_dimensions",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(quality_metrics) = 'object'",
            name="ck_image_selection_candidates_quality_metrics",
        ),
        sa.CheckConstraint(
            "range_confidence IS NULL OR range_confidence BETWEEN 0 AND 1",
            name="ck_image_selection_candidates_range_confidence",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(reason_codes) = 'array'",
            name="ck_image_selection_candidates_reason_codes",
        ),
        sa.CheckConstraint(
            "decision IN ('eligible', 'rejected', 'selected_automatic', 'selected_manual')",
            name="ck_image_selection_candidates_decision",
        ),
        sa.CheckConstraint(
            "decision NOT IN ('selected_automatic', 'selected_manual') OR group_id IS NOT NULL",
            name="ck_image_selection_candidates_selected_group",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["image_selection_runs.id"],
            name="fk_image_selection_candidates_run_id_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "group_id"],
            ["image_selection_groups.run_id", "image_selection_groups.id"],
            name="fk_image_selection_candidates_run_group",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_image_selection_candidates"),
        sa.UniqueConstraint(
            "run_id",
            "order_index",
            name="uq_image_selection_candidates_run_order",
        ),
        sa.UniqueConstraint(
            "run_id",
            "source_relative_path",
            name="uq_image_selection_candidates_run_path",
        ),
    )
    op.create_index(
        "ix_image_selection_candidates_group_order",
        "image_selection_candidates",
        ["run_id", "group_id", "order_index"],
        unique=False,
    )
    op.create_index(
        "uq_image_selection_candidates_selected_group",
        "image_selection_candidates",
        ["run_id", "group_id"],
        unique=True,
        postgresql_where=sa.text("decision IN ('selected_automatic', 'selected_manual')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_image_selection_candidates_selected_group",
        table_name="image_selection_candidates",
    )
    op.drop_index(
        "ix_image_selection_candidates_group_order",
        table_name="image_selection_candidates",
    )
    op.drop_table("image_selection_candidates")
    op.drop_index(
        "uq_image_selection_groups_selected_range",
        table_name="image_selection_groups",
    )
    op.drop_table("image_selection_groups")
    op.drop_index(
        "ix_image_selection_runs_game_created",
        table_name="image_selection_runs",
    )
    op.drop_table("image_selection_runs")

    op.execute("DELETE FROM jobs WHERE job_type = 'image_selection'")
    op.execute("ALTER TYPE job_type RENAME TO job_type_with_image_selection")
    postgresql.ENUM(
        *_JOB_TYPES_WITHOUT_IMAGE_SELECTION,
        name="job_type",
    ).create(op.get_bind(), checkfirst=False)
    op.execute(
        "ALTER TABLE jobs ALTER COLUMN job_type TYPE job_type USING job_type::text::job_type"
    )
    op.execute("DROP TYPE job_type_with_image_selection")
