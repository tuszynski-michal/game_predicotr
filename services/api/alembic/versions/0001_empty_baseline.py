"""Establish the empty PostgreSQL migration baseline.

Revision ID: 0001_empty_baseline
Revises:
Create Date: 2026-07-26
"""

from collections.abc import Sequence

revision: str = "0001_empty_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Keep the baseline intentionally free of domain tables."""


def downgrade() -> None:
    """Return to the pre-baseline state."""
