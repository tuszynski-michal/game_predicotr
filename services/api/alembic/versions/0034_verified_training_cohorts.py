"""Add cumulative immutable verified training cohorts.

Revision ID: 0034_verified_training_cohorts
Revises: 0033_image_selection_sequence_order
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034_verified_training_cohorts"
down_revision: str | Sequence[str] | None = "0033_image_selection_sequence_order"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "verified_training_cohorts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("iteration_number", sa.Integer(), nullable=False),
        sa.Column("manifest_schema_version", sa.Integer(), nullable=False),
        sa.Column("manifest_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_sha256", sa.String(length=64), nullable=False),
        sa.Column("resolved_layout_count", sa.Integer(), nullable=False),
        sa.Column("cell_sample_count", sa.Integer(), nullable=False),
        sa.Column("source_image_count", sa.Integer(), nullable=False),
        sa.Column("pending_item_count", sa.Integer(), nullable=False),
        sa.Column("rejected_item_count", sa.Integer(), nullable=False),
        sa.Column("incomplete_item_count", sa.Integer(), nullable=False),
        sa.Column("artifact_relative_path", sa.String(length=1000), nullable=False),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "iteration_number > 0 AND manifest_schema_version > 0",
            name="ck_verified_training_cohorts_versions",
        ),
        sa.CheckConstraint(
            "manifest_checksum_sha256 ~ '^[0-9a-f]{64}$' AND command_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_verified_training_cohorts_sha256",
        ),
        sa.CheckConstraint(
            "resolved_layout_count > 0 "
            "AND cell_sample_count = resolved_layout_count * 15 "
            "AND source_image_count > 0 "
            "AND pending_item_count >= 0 "
            "AND rejected_item_count >= 0 "
            "AND incomplete_item_count >= 0",
            name="ck_verified_training_cohorts_counts",
        ),
        sa.CheckConstraint(
            r"length(btrim(artifact_relative_path)) > 0 "
            r"AND artifact_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'",
            name="ck_verified_training_cohorts_relative_path",
        ),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
            name="fk_verified_training_cohorts_game",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_verified_training_cohorts"),
        sa.UniqueConstraint(
            "game_id",
            "iteration_number",
            name="uq_verified_training_cohorts_iteration",
        ),
        sa.UniqueConstraint(
            "game_id",
            "manifest_checksum_sha256",
            name="uq_verified_training_cohorts_manifest",
        ),
        sa.UniqueConstraint(
            "game_id",
            "idempotency_key",
            name="uq_verified_training_cohorts_idempotency",
        ),
    )
    op.create_table(
        "verified_training_cohort_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_order", sa.Integer(), nullable=False),
        sa.Column("review_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recognized_board_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_image_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("decision_status", sa.String(length=20), nullable=False),
        sa.Column("resolution_revision", sa.Integer(), nullable=False),
        sa.Column("geometry_revision", sa.Integer(), nullable=False),
        sa.Column("source_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("board_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("pipeline_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("item_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("board_manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "item_order >= 0 AND sequence_number > 0 "
            "AND resolution_revision > 0 AND geometry_revision >= 0",
            name="ck_verified_training_cohort_items_values",
        ),
        sa.CheckConstraint(
            "decision_status IN ('accepted', 'corrected')",
            name="ck_verified_training_cohort_items_status",
        ),
        sa.CheckConstraint(
            "item_checksum_sha256 ~ '^[0-9a-f]{64}$' "
            "AND source_checksum_sha256 ~ '^[0-9a-f]{64}$' "
            "AND board_checksum_sha256 ~ '^[0-9a-f]{64}$' "
            "AND pipeline_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_verified_training_cohort_items_sha256",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(board_manifest) = 'object' "
            "AND jsonb_array_length(board_manifest -> 'cells') = 15",
            name="ck_verified_training_cohort_items_manifest",
        ),
        sa.ForeignKeyConstraint(
            ["cohort_id"],
            ["verified_training_cohorts.id"],
            name="fk_verified_training_cohort_items_cohort",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["review_item_id"],
            ["image_review_items.id"],
            name="fk_verified_training_cohort_items_review",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recognized_board_id"],
            ["recognized_boards.id"],
            name="fk_verified_training_cohort_items_board",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_image_id"],
            ["source_images.id"],
            name="fk_verified_training_cohort_items_source",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_job_id"],
            ["jobs.id"],
            name="fk_verified_training_cohort_items_job",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_verified_training_cohort_items"),
        sa.UniqueConstraint(
            "cohort_id",
            "item_order",
            name="uq_verified_training_cohort_items_order",
        ),
        sa.UniqueConstraint(
            "cohort_id",
            "review_item_id",
            name="uq_verified_training_cohort_items_review",
        ),
    )


def downgrade() -> None:
    op.drop_table("verified_training_cohort_items")
    op.drop_table("verified_training_cohorts")
