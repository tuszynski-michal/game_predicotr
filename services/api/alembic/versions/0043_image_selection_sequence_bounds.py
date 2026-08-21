"""Persist complete image-selection sequence bounds.

Revision ID: 0043_image_selection_sequence_bounds
Revises: 0042_image_selection_derived_recovery
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043_image_selection_sequence_bounds"
down_revision: str | Sequence[str] | None = "0042_image_selection_derived_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "image_selection_runs",
        sa.Column(
            "last_sequence_number",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "ck_image_selection_runs_last_sequence_positive",
        "image_selection_runs",
        "last_sequence_number >= 0",
    )
    op.create_check_constraint(
        "ck_image_selection_runs_sequence_bounds",
        "image_selection_runs",
        "last_sequence_number = 0 OR "
        "(first_sequence_number > 0 AND "
        "((sequence_direction = 'ascending' AND "
        "last_sequence_number >= first_sequence_number) OR "
        "(sequence_direction = 'descending' AND "
        "last_sequence_number <= first_sequence_number)))",
    )
    op.drop_index(
        "uq_image_selection_runs_full_identity",
        table_name="image_selection_runs",
    )
    op.drop_index(
        "uq_image_selection_runs_recovery_identity",
        table_name="image_selection_runs",
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
            "last_sequence_number",
        ],
        unique=True,
        postgresql_where=sa.text("execution_mode = 'full'"),
    )
    op.create_index(
        "uq_image_selection_runs_recovery_identity",
        "image_selection_runs",
        [
            "source_run_id",
            "selector_fingerprint",
            "source_snapshot_sha256",
            "last_sequence_number",
        ],
        unique=True,
        postgresql_where=sa.text("execution_mode = 'range_recovery'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_image_selection_runs_recovery_identity",
        table_name="image_selection_runs",
    )
    op.drop_index(
        "uq_image_selection_runs_full_identity",
        table_name="image_selection_runs",
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
    op.drop_constraint(
        "ck_image_selection_runs_sequence_bounds",
        "image_selection_runs",
        type_="check",
    )
    op.drop_constraint(
        "ck_image_selection_runs_last_sequence_positive",
        "image_selection_runs",
        type_="check",
    )
    op.drop_column("image_selection_runs", "last_sequence_number")
