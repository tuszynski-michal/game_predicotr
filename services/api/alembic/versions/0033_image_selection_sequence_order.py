"""Persist image-selection sequence order configuration.

Revision ID: 0033_image_selection_sequence_order
Revises: 0032_worker_lane_runtime
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_image_selection_sequence_order"
down_revision: str | Sequence[str] | None = "0032_worker_lane_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "image_selection_runs",
        sa.Column(
            "sequence_direction",
            sa.String(length=16),
            nullable=False,
            server_default="ascending",
        ),
    )
    op.add_column(
        "image_selection_runs",
        sa.Column(
            "first_sequence_number",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "ck_image_selection_runs_sequence_direction",
        "image_selection_runs",
        "sequence_direction IN ('ascending', 'descending')",
    )
    op.create_check_constraint(
        "ck_image_selection_runs_first_sequence_positive",
        "image_selection_runs",
        "first_sequence_number >= 0",
    )
    op.drop_constraint(
        "uq_image_selection_runs_identity",
        "image_selection_runs",
        type_="unique",
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


def downgrade() -> None:
    op.drop_constraint(
        "uq_image_selection_runs_identity",
        "image_selection_runs",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_image_selection_runs_identity",
        "image_selection_runs",
        ("game_id", "input_manifest_sha256", "selector_fingerprint"),
    )
    op.drop_constraint(
        "ck_image_selection_runs_first_sequence_positive",
        "image_selection_runs",
        type_="check",
    )
    op.drop_constraint(
        "ck_image_selection_runs_sequence_direction",
        "image_selection_runs",
        type_="check",
    )
    op.drop_column("image_selection_runs", "first_sequence_number")
    op.drop_column("image_selection_runs", "sequence_direction")
