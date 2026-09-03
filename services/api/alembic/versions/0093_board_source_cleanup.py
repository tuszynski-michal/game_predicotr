"""Allow durable receipts for board-source range cleanup.

Revision ID: 0093_board_source_cleanup
Revises: 0092_filename_verification_cleanup
Create Date: 2026-09-03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0093_board_source_cleanup"
down_revision: str | Sequence[str] | None = "0092_filename_verification_cleanup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "ck_cleanup_operations_type"
_PREVIOUS = "operation_type IN ('mobile_release', 'game_layout_data')"
_CURRENT = "operation_type IN ('mobile_release', 'game_layout_data', 'board_source_ranges')"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "cleanup_operations", type_="check")
    op.create_check_constraint(_CONSTRAINT, "cleanup_operations", _CURRENT)


def downgrade() -> None:
    op.execute(
        "DELETE FROM cleanup_operations WHERE operation_type = 'board_source_ranges'"
    )
    op.drop_constraint(_CONSTRAINT, "cleanup_operations", type_="check")
    op.create_check_constraint(_CONSTRAINT, "cleanup_operations", _PREVIOUS)
