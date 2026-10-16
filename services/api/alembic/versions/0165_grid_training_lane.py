"""Separate grid-training job type, execution slot 3 and worker lane (TASK-0996, D-558).

Revision ID: 0165_grid_training_lane
Revises: 0164_merge_main_board_search_panels
Create Date: 2026-10-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0165_grid_training_lane"
down_revision: str | Sequence[str] | None = "0164_merge_main_board_search_panels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROCESSING = (
    "(status = 'processing' AND "
    "((job_type::text IN ('image_selection', 'semi_automatic_image_selection') "
    "AND execution_slot = 2) OR "
    "(job_type::text = 'grid_training' AND execution_slot = 3) OR "
    "(job_type::text NOT IN ('image_selection', 'semi_automatic_image_selection', "
    "'grid_training') AND execution_slot = 1)) AND "
    "lease_owner IS NOT NULL AND lease_token IS NOT NULL AND "
    "lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL) OR "
    "(status <> 'processing' AND execution_slot IS NULL AND lease_owner IS NULL AND "
    "lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL)"
)
_PREVIOUS = (
    "(status = 'processing' AND "
    "((job_type IN ('image_selection', 'semi_automatic_image_selection') "
    "AND execution_slot = 2) OR "
    "(job_type NOT IN ('image_selection', 'semi_automatic_image_selection') "
    "AND execution_slot = 1)) AND "
    "lease_owner IS NOT NULL AND lease_token IS NOT NULL AND "
    "lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL) OR "
    "(status <> 'processing' AND execution_slot IS NULL AND lease_owner IS NULL AND "
    "lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL)"
)


def upgrade() -> None:
    # The new label is committed before any constraint mentions it (as in 0087); the
    # constraint compares text, so it never needs the label inside one transaction.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'grid_training'")
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_constraint("ck_jobs_processing_lease_fields", "jobs", type_="check")
    op.create_check_constraint("ck_jobs_processing_lease_fields", "jobs", _PROCESSING)
    op.drop_constraint("ck_worker_lane_runtime_lane", "worker_lane_runtime", type_="check")
    op.create_check_constraint(
        "ck_worker_lane_runtime_lane",
        "worker_lane_runtime",
        "lane IN ('general', 'image_selection', 'grid_training')",
    )


def downgrade() -> None:
    # PostgreSQL cannot drop an enum label; history keeps it. Any grid-training job or
    # lane row blocks the downgrade instead of being reassigned to another lane.
    op.execute("""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM public.jobs WHERE job_type::text = 'grid_training')
           OR EXISTS (SELECT 1 FROM public.worker_lane_runtime WHERE lane = 'grid_training') THEN
            RAISE EXCEPTION 'GRID_TRAINING_LANE_DOWNGRADE_HAS_HISTORY';
        END IF;
    END $guard$""")
    op.drop_constraint("ck_worker_lane_runtime_lane", "worker_lane_runtime", type_="check")
    op.create_check_constraint(
        "ck_worker_lane_runtime_lane",
        "worker_lane_runtime",
        "lane IN ('general', 'image_selection')",
    )
    op.drop_constraint("ck_jobs_processing_lease_fields", "jobs", type_="check")
    op.create_check_constraint("ck_jobs_processing_lease_fields", "jobs", _PREVIOUS)
