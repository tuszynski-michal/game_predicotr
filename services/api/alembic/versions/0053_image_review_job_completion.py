"""Synchronize image-import completion with the durable review queue.

Revision ID: 0053_image_review_job_completion
Revises: 0052_reviewer_assignment_sessions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0053_image_review_job_completion"
down_revision: str | Sequence[str] | None = "0052_reviewer_assignment_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE FUNCTION synchronize_image_review_job_status()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF NEW.total_count > 0 AND NEW.pending_count = 0 THEN
                    UPDATE jobs
                    SET
                        status = 'completed',
                        updated_at = GREATEST(jobs.updated_at, NEW.updated_at),
                        finished_at = COALESCE(jobs.finished_at, NEW.updated_at),
                        error_code = NULL,
                        error_message = NULL
                    WHERE id = NEW.import_job_id
                      AND job_type = 'import'
                      AND status = 'waiting_for_review';
                ELSIF NEW.pending_count > 0 THEN
                    UPDATE jobs
                    SET
                        status = 'waiting_for_review',
                        updated_at = GREATEST(jobs.updated_at, NEW.updated_at),
                        finished_at = NULL,
                        error_code = NULL,
                        error_message = NULL
                    WHERE id = NEW.import_job_id
                      AND job_type = 'import'
                      AND status = 'completed';
                END IF;

                RETURN NEW;
            END
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_image_review_job_status
            AFTER INSERT OR UPDATE OF total_count, pending_count
            ON image_review_queue_states
            FOR EACH ROW
            EXECUTE FUNCTION synchronize_image_review_job_status()
            """
        )
    )

    # Reconcile imports completed before the lifecycle trigger existed. The
    # queue projection is authoritative and excludes empty imports.
    op.execute(
        sa.text(
            """
            UPDATE jobs AS job
            SET
                status = 'completed',
                updated_at = GREATEST(job.updated_at, state.updated_at),
                finished_at = COALESCE(job.finished_at, state.updated_at),
                error_code = NULL,
                error_message = NULL
            FROM image_review_queue_states AS state
            WHERE job.id = state.import_job_id
              AND job.job_type = 'import'
              AND job.status = 'waiting_for_review'
              AND state.total_count > 0
              AND state.pending_count = 0
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DROP TRIGGER trg_image_review_job_status
            ON image_review_queue_states
            """
        )
    )
    op.execute(sa.text("DROP FUNCTION synchronize_image_review_job_status()"))
