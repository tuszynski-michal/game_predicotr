"""Add versioned precomputed layout payouts.

Revision ID: 0009_layout_payouts
Revises: 0008_job_leases
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_layout_payouts"
down_revision: str | Sequence[str] | None = "0008_job_leases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "layout_payouts",
        sa.Column(
            "dataset_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "rules_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("algorithm_version", sa.String(length=100), nullable=False),
        sa.Column("total_payout", sa.BigInteger(), nullable=False),
        sa.Column("audit_path", sa.String(length=1000), nullable=True),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "sequence_number > 0",
            name="ck_layout_payouts_sequence_positive",
        ),
        sa.CheckConstraint(
            "length(btrim(algorithm_version)) > 0",
            name="ck_layout_payouts_algorithm_not_blank",
        ),
        sa.CheckConstraint(
            "total_payout >= 0",
            name="ck_layout_payouts_total_nonnegative",
        ),
        sa.CheckConstraint(
            "audit_path IS NULL OR length(btrim(audit_path)) > 0",
            name="ck_layout_payouts_audit_path_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "sequence_number"],
            ["layouts.dataset_version_id", "layouts.sequence_number"],
            name="fk_layout_payouts_layout",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rules_version_id"],
            ["rules_versions.id"],
            name="fk_layout_payouts_rules_version_id_rules_versions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "dataset_version_id",
            "rules_version_id",
            "sequence_number",
            "algorithm_version",
            name="pk_layout_payouts",
        ),
    )
    op.create_index(
        "ix_layout_payouts_rules_version_id",
        "layout_payouts",
        ["rules_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_layout_payouts_rules_version_id",
        table_name="layout_payouts",
    )
    op.drop_table("layout_payouts")
