"""Add a transaction-scoped revision to symbol-cell review state.

Revision ID: 0067_symbol_cell_review_catalog_revision
Revises: 0066_image_symbol_review_cells
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0067_symbol_cell_review_catalog_revision"
down_revision: str | Sequence[str] | None = "0066_image_symbol_review_cells"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "image_symbol_review_states",
        sa.Column("catalog_revision", sa.BigInteger(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("image_symbol_review_states", "catalog_revision")
