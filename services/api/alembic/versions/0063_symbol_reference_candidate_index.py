"""Index approved human symbol labels used by reference-crop selection.

Revision ID: 0063_symbol_reference_candidate_index
Revises: 0062_board_search_fast_documents
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0063_symbol_reference_candidate_index"
down_revision: str | Sequence[str] | None = "0062_board_search_fast_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_image_review_items_resolved_symbols_gin",
        "image_review_items",
        ["(resolved_value -> 'symbolCodes')"],
        postgresql_using="gin",
        postgresql_ops={"(resolved_value -> 'symbolCodes')": "jsonb_path_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_image_review_items_resolved_symbols_gin", table_name="image_review_items")
