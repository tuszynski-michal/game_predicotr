"""Allow independent general and image-selection execution lanes.

Revision ID: 0031_job_execution_lanes
Revises: 0030_image_selection_optional_exceptions
Create Date: 2026-08-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0031_job_execution_lanes"
down_revision: str | Sequence[str] | None = "0030_image_selection_optional_exceptions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_jobs_processing_lease_fields",
        "jobs",
        type_="check",
    )
    op.execute(
        "UPDATE jobs SET execution_slot = 2 "
        "WHERE status = 'processing' AND job_type = 'image_selection'"
    )
    op.create_check_constraint(
        "ck_jobs_processing_lease_fields",
        "jobs",
        "(status = 'processing' "
        "AND ((job_type = 'image_selection' AND execution_slot = 2) "
        "OR (job_type <> 'image_selection' AND execution_slot = 1)) "
        "AND lease_owner IS NOT NULL AND lease_token IS NOT NULL "
        "AND lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL) "
        "OR (status <> 'processing' AND execution_slot IS NULL "
        "AND lease_owner IS NULL AND lease_token IS NULL "
        "AND lease_expires_at IS NULL AND heartbeat_at IS NULL)",
    )


def downgrade() -> None:
    # A downgrade restores the historical single lane. Any active selector is
    # safely requeued so the old constraint can be recreated without silently
    # assigning it to the general worker.
    op.execute(
        "UPDATE jobs SET status = 'created', execution_slot = NULL, "
        "lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL, "
        "heartbeat_at = NULL, updated_at = CURRENT_TIMESTAMP "
        "WHERE status = 'processing' AND execution_slot = 2"
    )
    op.drop_constraint(
        "ck_jobs_processing_lease_fields",
        "jobs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_jobs_processing_lease_fields",
        "jobs",
        "(status = 'processing' AND execution_slot = 1 "
        "AND lease_owner IS NOT NULL AND lease_token IS NOT NULL "
        "AND lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL) "
        "OR (status <> 'processing' AND execution_slot IS NULL "
        "AND lease_owner IS NULL AND lease_token IS NULL "
        "AND lease_expires_at IS NULL AND heartbeat_at IS NULL)",
    )
