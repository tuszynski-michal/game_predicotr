"""Allow immutable gate revisions for one geometry cohort.

Revision ID: 0094_grid_profile_gate_revisions
Revises: 0093_board_source_cleanup
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0094_grid_profile_gate_revisions"
down_revision: str | Sequence[str] | None = "0093_board_source_cleanup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_grid_calibration_profiles_cohort",
        "grid_calibration_profiles",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_grid_calibration_profiles_cohort_checksum",
        "grid_calibration_profiles",
        ["cohort_id", "profile_checksum_sha256"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_grid_calibration_profiles_cohort_checksum",
        "grid_calibration_profiles",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_grid_calibration_profiles_cohort",
        "grid_calibration_profiles",
        ["cohort_id"],
    )
