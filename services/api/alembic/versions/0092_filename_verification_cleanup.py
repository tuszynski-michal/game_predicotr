"""Add resumable terminal cleanup states to filename verification runs.

Revision ID: 0092_filename_verification_cleanup
Revises: 0091_filename_range_verification_history
Create Date: 2026-09-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0092_filename_verification_cleanup"
down_revision: str | None = "0091_filename_range_verification_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_CONSTRAINT = "ck_semi_automatic_selection_runs_status"
_PREVIOUS_STATUS_CONDITION = (
    "status IN ('ready', 'running', 'paused', 'analysis_complete', "
    "'syncing_output', 'review_mode', 'edit_source_mode', 'completed', "
    "'failed', 'cancelled')"
)
_CURRENT_STATUS_CONDITION = (
    "status IN ('ready', 'running', 'paused', 'analysis_complete', "
    "'syncing_output', 'review_mode', 'edit_source_mode', 'cleanup_pending', "
    "'cleanup_blocked', 'completed', 'failed', 'cancelled')"
)


def upgrade() -> None:
    op.drop_constraint(
        _STATUS_CONSTRAINT,
        "semi_automatic_image_selection_runs",
        type_="check",
    )
    op.create_check_constraint(
        _STATUS_CONSTRAINT,
        "semi_automatic_image_selection_runs",
        _CURRENT_STATUS_CONDITION,
    )


def downgrade() -> None:
    op.execute(
        "UPDATE semi_automatic_image_selection_runs "
        "SET status = 'failed' "
        "WHERE status IN ('cleanup_pending', 'cleanup_blocked')"
    )
    op.drop_constraint(
        _STATUS_CONSTRAINT,
        "semi_automatic_image_selection_runs",
        type_="check",
    )
    op.create_check_constraint(
        _STATUS_CONSTRAINT,
        "semi_automatic_image_selection_runs",
        _PREVIOUS_STATUS_CONDITION,
    )
