"""Create versioned paylines.

Revision ID: 0004_paylines
Revises: 0003_rules_versions
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_paylines"
down_revision: str | Sequence[str] | None = "0003_rules_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paylines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "rules_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "row_path",
            postgresql.ARRAY(sa.SmallInteger(), dimensions=1),
            nullable=False,
        ),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "cardinality(row_path) > 0",
            name="ck_paylines_row_path_not_empty",
        ),
        sa.CheckConstraint(
            "0 <= ALL(row_path)",
            name="ck_paylines_row_path_nonnegative",
        ),
        sa.CheckConstraint(
            "display_order >= 0",
            name="ck_paylines_display_order_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["rules_version_id"],
            ["rules_versions.id"],
            name="fk_paylines_rules_version_id_rules_versions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_paylines"),
        sa.UniqueConstraint(
            "rules_version_id",
            "code",
            name="uq_paylines_rules_version_code",
        ),
        sa.UniqueConstraint(
            "rules_version_id",
            "row_path",
            name="uq_paylines_rules_version_row_path",
        ),
    )
    op.create_index(
        "ix_paylines_rules_version_id",
        "paylines",
        ["rules_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_paylines_rules_version_id", table_name="paylines")
    op.drop_table("paylines")
