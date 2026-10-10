"""Join the V7 delivery and main symbol-review migration branches.

Revision ID: 0147_merge_v7_main
Revises: 0146_symbol_review_import_filter_index, 0146_v7_operator_sources
"""

from __future__ import annotations

revision: str = "0147_merge_v7_main"
down_revision: tuple[str, str] = (
    "0146_symbol_review_import_filter_index",
    "0146_v7_operator_sources",
)
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
