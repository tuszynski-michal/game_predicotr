"""Add immutable derived image-selection recovery runs.

Revision ID: 0042_image_selection_derived_recovery
Revises: 0041_image_selection_review_queues
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0042_image_selection_derived_recovery"
down_revision: str | Sequence[str] | None = "0041_image_selection_review_queues"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "image_selection_runs",
        sa.Column(
            "execution_mode",
            sa.String(length=32),
            nullable=False,
            server_default="full",
        ),
    )
    op.add_column(
        "image_selection_runs",
        sa.Column("source_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "image_selection_runs",
        sa.Column("source_snapshot_sha256", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_image_selection_runs_source_run_id",
        "image_selection_runs",
        "image_selection_runs",
        ["source_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_image_selection_runs_execution_mode",
        "image_selection_runs",
        "execution_mode IN ('full', 'range_recovery')",
    )
    op.create_check_constraint(
        "ck_image_selection_runs_recovery_source",
        "image_selection_runs",
        "(execution_mode = 'full' AND source_run_id IS NULL AND "
        "source_snapshot_sha256 IS NULL) OR "
        "(execution_mode = 'range_recovery' AND source_run_id IS NOT NULL AND "
        "source_run_id <> id AND source_snapshot_sha256 ~ '^[0-9a-f]{64}$')",
    )
    op.drop_constraint(
        "uq_image_selection_runs_identity",
        "image_selection_runs",
        type_="unique",
    )
    op.create_index(
        "uq_image_selection_runs_full_identity",
        "image_selection_runs",
        [
            "game_id",
            "input_manifest_sha256",
            "selector_fingerprint",
            "sequence_direction",
            "first_sequence_number",
        ],
        unique=True,
        postgresql_where=sa.text("execution_mode = 'full'"),
    )
    op.create_index(
        "uq_image_selection_runs_recovery_identity",
        "image_selection_runs",
        ["source_run_id", "selector_fingerprint", "source_snapshot_sha256"],
        unique=True,
        postgresql_where=sa.text("execution_mode = 'range_recovery'"),
    )
    op.create_index(
        "ix_image_selection_runs_source_run_id",
        "image_selection_runs",
        ["source_run_id"],
        unique=False,
    )
    op.add_column(
        "image_selection_groups",
        sa.Column("origin_group_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_image_selection_groups_origin_group_id",
        "image_selection_groups",
        "image_selection_groups",
        ["origin_group_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_image_selection_groups_origin_group_id",
        "image_selection_groups",
        ["origin_group_id"],
        unique=False,
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM image_selection_runs WHERE execution_mode = 'range_recovery'"
    )
    op.drop_index(
        "ix_image_selection_groups_origin_group_id",
        table_name="image_selection_groups",
    )
    op.drop_constraint(
        "fk_image_selection_groups_origin_group_id",
        "image_selection_groups",
        type_="foreignkey",
    )
    op.drop_column("image_selection_groups", "origin_group_id")
    op.drop_index(
        "ix_image_selection_runs_source_run_id",
        table_name="image_selection_runs",
    )
    op.drop_index(
        "uq_image_selection_runs_recovery_identity",
        table_name="image_selection_runs",
    )
    op.drop_index(
        "uq_image_selection_runs_full_identity",
        table_name="image_selection_runs",
    )
    op.create_unique_constraint(
        "uq_image_selection_runs_identity",
        "image_selection_runs",
        (
            "game_id",
            "input_manifest_sha256",
            "selector_fingerprint",
            "sequence_direction",
            "first_sequence_number",
        ),
    )
    op.drop_constraint(
        "ck_image_selection_runs_recovery_source",
        "image_selection_runs",
        type_="check",
    )
    op.drop_constraint(
        "ck_image_selection_runs_execution_mode",
        "image_selection_runs",
        type_="check",
    )
    op.drop_constraint(
        "fk_image_selection_runs_source_run_id",
        "image_selection_runs",
        type_="foreignkey",
    )
    op.drop_column("image_selection_runs", "source_snapshot_sha256")
    op.drop_column("image_selection_runs", "source_run_id")
    op.drop_column("image_selection_runs", "execution_mode")
