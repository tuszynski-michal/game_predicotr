"""Add immutable geometry cohorts and grid profile registry.

Revision ID: 0039_grid_calibration_profiles
Revises: 0038_curated_image_import_batches
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0039_grid_calibration_profiles"
down_revision: str | Sequence[str] | None = "0038_curated_image_import_batches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "grid_geometry_cohorts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cohort_number", sa.Integer(), nullable=False),
        sa.Column("manifest_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("manifest_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("source_image_count", sa.Integer(), nullable=False),
        sa.Column("training_count", sa.Integer(), nullable=False),
        sa.Column("validation_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "cohort_number > 0 AND sample_count > 0 AND source_image_count > 0 "
            "AND training_count >= 0 AND validation_count >= 0 "
            "AND training_count + validation_count = sample_count",
            name="ck_grid_geometry_cohorts_counts",
        ),
        sa.CheckConstraint(
            "manifest_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_grid_geometry_cohorts_manifest_checksum",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "cohort_number", name="uq_grid_geometry_cohorts_number"),
        sa.UniqueConstraint(
            "game_id",
            "manifest_checksum_sha256",
            name="uq_grid_geometry_cohorts_manifest",
        ),
    )
    op.create_index(
        "ix_grid_geometry_cohorts_game_created",
        "grid_geometry_cohorts",
        ["game_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "grid_calibration_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("profile_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("profile_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("gate_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rejection_reasons", postgresql.ARRAY(sa.String(length=100)), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "profile_number > 0 AND status IN ('candidate_ready','rejected')",
            name="ck_grid_calibration_profiles_values",
        ),
        sa.CheckConstraint(
            "profile_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_grid_calibration_profiles_checksum",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cohort_id"], ["grid_geometry_cohorts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "game_id", "profile_number", name="uq_grid_calibration_profiles_number"
        ),
        sa.UniqueConstraint("cohort_id", name="uq_grid_calibration_profiles_cohort"),
    )
    op.create_index(
        "ix_grid_calibration_profiles_game_status",
        "grid_calibration_profiles",
        ["game_id", "status"],
        unique=False,
    )
    op.create_table(
        "game_grid_profile_activations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("previous_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("activation_number", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('activate','rollback')",
            name="ck_game_grid_profile_activations_action",
        ),
        sa.CheckConstraint(
            "activation_number > 0 AND btrim(actor) <> '' AND command_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_game_grid_profile_activations_values",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["grid_calibration_profiles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["previous_profile_id"],
            ["grid_calibration_profiles.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "game_id",
            "idempotency_key",
            name="uq_game_grid_profile_activations_idempotency",
        ),
        sa.UniqueConstraint(
            "game_id",
            "activation_number",
            name="uq_game_grid_profile_activations_number",
        ),
    )
    op.create_index(
        "ix_game_grid_profile_activations_current",
        "game_grid_profile_activations",
        ["game_id", "activation_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_game_grid_profile_activations_current",
        table_name="game_grid_profile_activations",
    )
    op.drop_table("game_grid_profile_activations")
    op.drop_index(
        "ix_grid_calibration_profiles_game_status",
        table_name="grid_calibration_profiles",
    )
    op.drop_table("grid_calibration_profiles")
    op.drop_index(
        "ix_grid_geometry_cohorts_game_created",
        table_name="grid_geometry_cohorts",
    )
    op.drop_table("grid_geometry_cohorts")
