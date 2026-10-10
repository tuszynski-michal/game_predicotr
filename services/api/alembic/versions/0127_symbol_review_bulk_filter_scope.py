"""Persist the explicit outside/all/unknown/symbol scope of bulk snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0127_symbol_review_bulk_filter_scope"
down_revision = "0126_symbol_cell_source_visibility"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.add_column(
        "image_symbol_review_bulk_operations",
        sa.Column("filter_scope", sa.String(50), nullable=True),
        schema="game_data_v2",
    )


def downgrade() -> None:
    raise RuntimeError("BULK_FILTER_SCOPE_DOWNGRADE_UNSUPPORTED: explicit scope may be recorded")
