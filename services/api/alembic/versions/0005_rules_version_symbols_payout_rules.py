"""Create per-symbol rules configuration and payout rules.

Revision ID: 0005_symbol_payouts
Revises: 0004_paylines
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_symbol_payouts"
down_revision: str | Sequence[str] | None = "0004_paylines"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rules_version_symbols",
        sa.Column(
            "rules_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("symbol_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("minimum_match_length", sa.SmallInteger(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "minimum_match_length IS NULL OR minimum_match_length BETWEEN 2 AND 32767",
            name="ck_rules_version_symbols_minimum_range",
        ),
        sa.ForeignKeyConstraint(
            ["rules_version_id"],
            ["rules_versions.id"],
            name="fk_rules_version_symbols_rules_version_id_rules_versions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["symbol_id"],
            ["symbols.id"],
            name="fk_rules_version_symbols_symbol_id_symbols",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "rules_version_id",
            "symbol_id",
            name="pk_rules_version_symbols",
        ),
    )
    op.create_index(
        "ix_rules_version_symbols_symbol_id",
        "rules_version_symbols",
        ["symbol_id"],
        unique=False,
    )

    op.create_table(
        "payout_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "rules_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("symbol_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_length", sa.SmallInteger(), nullable=False),
        sa.Column("payout_credits", sa.Integer(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "match_length BETWEEN 2 AND 32767",
            name="ck_payout_rules_match_length_range",
        ),
        sa.CheckConstraint(
            "payout_credits >= 0",
            name="ck_payout_rules_credits_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["rules_version_id", "symbol_id"],
            [
                "rules_version_symbols.rules_version_id",
                "rules_version_symbols.symbol_id",
            ],
            name="fk_payout_rules_rules_version_symbol",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_payout_rules"),
        sa.UniqueConstraint(
            "rules_version_id",
            "symbol_id",
            "match_length",
            name="uq_payout_rules_version_symbol_length",
        ),
    )
    op.create_index(
        "ix_payout_rules_rules_version_id",
        "payout_rules",
        ["rules_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_payout_rules_symbol_id",
        "payout_rules",
        ["symbol_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_payout_rules_symbol_id", table_name="payout_rules")
    op.drop_index("ix_payout_rules_rules_version_id", table_name="payout_rules")
    op.drop_table("payout_rules")
    op.drop_index(
        "ix_rules_version_symbols_symbol_id",
        table_name="rules_version_symbols",
    )
    op.drop_table("rules_version_symbols")
