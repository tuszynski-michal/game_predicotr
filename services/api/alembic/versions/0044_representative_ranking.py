"""Persist manual representative-ranking cohorts and activation history.

Revision ID: 0044_representative_ranking
Revises: 0043_image_selection_sequence_bounds
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0044_representative_ranking"
down_revision: str | Sequence[str] | None = "0043_image_selection_sequence_bounds"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "representative_ranking_cohorts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("iteration_number", sa.Integer(), nullable=False),
        sa.Column("manifest_schema_version", sa.Integer(), nullable=False),
        sa.Column("manifest_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("positive_count", sa.Integer(), nullable=False),
        sa.Column("pair_count", sa.Integer(), nullable=False),
        sa.Column("excluded_ambiguous_count", sa.Integer(), nullable=False),
        sa.Column("folder_count", sa.Integer(), nullable=False),
        sa.Column("group_count", sa.Integer(), nullable=False),
        sa.Column("artifact_relative_path", sa.String(length=1000), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "iteration_number > 0 AND manifest_schema_version > 0",
            name="ck_representative_ranking_cohorts_versions",
        ),
        sa.CheckConstraint(
            "manifest_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_representative_ranking_cohorts_checksum",
        ),
        sa.CheckConstraint(
            "positive_count >= 0 AND pair_count >= 0 AND excluded_ambiguous_count >= 0 "
            "AND folder_count >= 0 AND group_count >= 0",
            name="ck_representative_ranking_cohorts_counts",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_representative_ranking_cohorts"),
        sa.UniqueConstraint(
            "game_id", "iteration_number", name="uq_representative_ranking_cohorts_iteration"
        ),
        sa.UniqueConstraint(
            "game_id", "manifest_checksum_sha256",
            name="uq_representative_ranking_cohorts_manifest",
        ),
    )
    op.create_index(
        "ix_representative_ranking_cohorts_game_created",
        "representative_ranking_cohorts",
        ["game_id", "created_at"],
    )
    op.create_table(
        "representative_ranking_iterations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_version", sa.String(length=100), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=False),
        sa.Column("model_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("model_artifact_relative_path", sa.String(length=1000), nullable=False),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "model_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_representative_ranking_iterations_checksum",
        ),
        sa.CheckConstraint(
            "feature_version <> '' AND model_version <> '' AND btrim(status) <> ''",
            name="ck_representative_ranking_iterations_values",
        ),
        sa.ForeignKeyConstraint(
            ["cohort_id"], ["representative_ranking_cohorts.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_representative_ranking_iterations"),
        sa.UniqueConstraint(
            "cohort_id", "model_checksum_sha256",
            name="uq_representative_ranking_iterations_model",
        ),
    )
    op.create_index(
        "ix_representative_ranking_iterations_cohort_created",
        "representative_ranking_iterations",
        ["cohort_id", "created_at"],
    )
    op.create_table(
        "representative_ranking_activations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("iteration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("previous_iteration_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("activation_number", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "action IN ('activate','rollback') AND activation_number > 0",
            name="ck_representative_ranking_activations_values",
        ),
        sa.CheckConstraint(
            "command_sha256 ~ '^[0-9a-f]{64}$' AND btrim(actor) <> ''",
            name="ck_representative_ranking_activations_checksum",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["iteration_id"], ["representative_ranking_iterations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["previous_iteration_id"],
            ["representative_ranking_iterations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_representative_ranking_activations"),
        sa.UniqueConstraint(
            "game_id", "activation_number",
            name="uq_representative_ranking_activations_number",
        ),
        sa.UniqueConstraint(
            "game_id", "idempotency_key",
            name="uq_representative_ranking_activations_idempotency",
        ),
    )
    op.create_index(
        "ix_representative_ranking_activations_game_created",
        "representative_ranking_activations",
        ["game_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_representative_ranking_activations_game_created",
        table_name="representative_ranking_activations",
    )
    op.drop_table("representative_ranking_activations")
    op.drop_index(
        "ix_representative_ranking_iterations_cohort_created",
        table_name="representative_ranking_iterations",
    )
    op.drop_table("representative_ranking_iterations")
    op.drop_index(
        "ix_representative_ranking_cohorts_game_created",
        table_name="representative_ranking_cohorts",
    )
    op.drop_table("representative_ranking_cohorts")
