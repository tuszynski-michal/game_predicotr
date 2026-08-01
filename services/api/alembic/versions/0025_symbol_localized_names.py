"""Add optional localized symbol names.

Revision ID: 0025_symbol_localized_names
Revises: 0024_cleanup_operations
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_symbol_localized_names"
down_revision: str | Sequence[str] | None = "0024_cleanup_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "symbols",
        sa.Column("name_pl", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "symbols",
        sa.Column("name_en", sa.String(length=200), nullable=True),
    )
    op.create_check_constraint(
        "ck_symbols_name_pl_nonblank",
        "symbols",
        "name_pl IS NULL OR length(btrim(name_pl)) > 0",
    )
    op.create_check_constraint(
        "ck_symbols_name_en_nonblank",
        "symbols",
        "name_en IS NULL OR length(btrim(name_en)) > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_symbols_name_en_nonblank",
        "symbols",
        type_="check",
    )
    op.drop_constraint(
        "ck_symbols_name_pl_nonblank",
        "symbols",
        type_="check",
    )
    op.drop_column("symbols", "name_en")
    op.drop_column("symbols", "name_pl")
