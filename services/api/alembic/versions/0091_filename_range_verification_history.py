"""Persist filename verification workflow history and review decisions.

Revision ID: 0091_filename_range_verification_history
Revises: 0090_symbol_reference_individual_cell_provenance
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0091_filename_range_verification_history"
down_revision: str | None = "0090_symbol_reference_individual_cell_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WORKFLOW_CONSTRAINT = "ck_semi_automatic_selection_runs_workflow_mode"
_V2_FILENAME_RECOGNIZER = "8b876e8a7cdc25f0709bf27ece4e99b1c777231fa3fcef4aa31e617123825b0f"


def upgrade() -> None:
    op.add_column(
        "semi_automatic_image_selection_runs",
        sa.Column("workflow_mode", sa.String(length=32), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE semi_automatic_image_selection_runs "
            "SET workflow_mode = CASE "
            "WHEN recognizer_fingerprint = :filename_recognizer "
            "THEN 'filename_verification' ELSE 'selection' END"
        ).bindparams(filename_recognizer=_V2_FILENAME_RECOGNIZER)
    )
    op.alter_column("semi_automatic_image_selection_runs", "workflow_mode", nullable=False)
    op.create_check_constraint(
        _WORKFLOW_CONSTRAINT,
        "semi_automatic_image_selection_runs",
        "workflow_mode IN ('selection', 'filename_verification')",
    )
    op.create_index(
        "ix_semi_automatic_selection_runs_workflow_created",
        "semi_automatic_image_selection_runs",
        ["workflow_mode", "created_at"],
    )
    op.create_table(
        "semi_automatic_filename_verification_reviews",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("source_index", sa.BigInteger(), nullable=False),
        sa.Column("source_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_index >= 0 AND revision >= 0",
            name="ck_filename_verification_reviews_bounds",
        ),
        sa.CheckConstraint(
            "decision IN ('keep', 'reject')",
            name="ck_filename_verification_reviews_decision",
        ),
        sa.CheckConstraint(
            "source_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_filename_verification_reviews_checksum",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["semi_automatic_image_selection_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("run_id", "source_index"),
    )
    op.create_index(
        "ix_filename_verification_reviews_run_decision",
        "semi_automatic_filename_verification_reviews",
        ["run_id", "decision"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_filename_verification_reviews_run_decision",
        table_name="semi_automatic_filename_verification_reviews",
    )
    op.drop_table("semi_automatic_filename_verification_reviews")
    op.drop_index(
        "ix_semi_automatic_selection_runs_workflow_created",
        table_name="semi_automatic_image_selection_runs",
    )
    op.drop_constraint(
        _WORKFLOW_CONSTRAINT,
        "semi_automatic_image_selection_runs",
        type_="check",
    )
    op.drop_column("semi_automatic_image_selection_runs", "workflow_mode")
