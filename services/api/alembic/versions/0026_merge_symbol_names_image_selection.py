"""Merge localized symbol names and image-selection migration heads.

Revision ID: 0026_merge_v03_v04_heads
Revises: 0025_symbol_localized_names, 0025_image_selection
Create Date: 2026-08-03
"""

from collections.abc import Sequence

revision: str = "0026_merge_v03_v04_heads"
down_revision: str | Sequence[str] | None = (
    "0025_symbol_localized_names",
    "0025_image_selection",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Join the two already-applied feature branches without schema changes."""


def downgrade() -> None:
    """Split the migration graph back into both feature heads."""
