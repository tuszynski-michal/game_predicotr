"""Keep unavailable cell history outside the current operational projection."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0101_symbol_cell_source_availability"
down_revision: str | Sequence[str] | None = "0100_manual_geometry_qualification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    # Constant default is metadata-only on the supported PostgreSQL baseline.
    op.add_column(
        "image_symbol_review_cells",
        sa.Column("source_available", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.execute("LOCK TABLE image_symbol_review_cells IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM image_symbol_review_cells WHERE NOT source_available) THEN
        RAISE EXCEPTION 'Cannot discard unavailable symbol-cell history protection';
      END IF;
    END $$""")
    op.drop_column("image_symbol_review_cells", "source_available")
