"""Index symbol-review foreign key to prediction revisions.

The index supports referential-integrity checks when removing obsolete
prediction revisions without scanning every symbol-review cell.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0102_index_symbol_review_prediction_revision"
down_revision: str | Sequence[str] | None = "0101_symbol_cell_source_availability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_image_symbol_review_cells_prediction_revision_id",
        "image_symbol_review_cells",
        ["prediction_revision_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_image_symbol_review_cells_prediction_revision_id",
        table_name="image_symbol_review_cells",
    )
