"""Reconcile browser-staging board status from all historical import jobs.

Revision ID: 0113_reconcile_browser_staging_board_import_status
Revises: 0112_browser_staging_board_import_status
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0113_reconcile_browser_staging_board_import_status"
down_revision: str | Sequence[str] | None = "0112_browser_staging_board_import_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    for schema in ("public", "game_data_v2"):
        op.execute(
            f"""
            UPDATE {schema}.browser_selection_retention_states AS retention
            SET board_import_status = CASE
                WHEN EXISTS (
                    SELECT 1 FROM public.jobs AS job
                    WHERE job.game_id = retention.game_id
                      AND job.job_type = 'import'
                      AND job.input_payload->>'import_kind' = 'image_directory'
                      AND job.input_payload->>'source_selection_id' = retention.upload_id::text
                      AND job.status IN ('waiting_for_review', 'completed')
                ) THEN 'boards_imported'
                WHEN EXISTS (
                    SELECT 1 FROM public.jobs AS job
                    WHERE job.game_id = retention.game_id
                      AND job.job_type = 'import'
                      AND job.input_payload->>'import_kind' = 'image_directory'
                      AND job.input_payload->>'source_selection_id' = retention.upload_id::text
                      AND job.status IN ('created', 'processing')
                ) THEN 'importing'
                WHEN EXISTS (
                    SELECT 1 FROM public.jobs AS job
                    WHERE job.game_id = retention.game_id
                      AND job.job_type = 'import'
                      AND job.input_payload->>'import_kind' = 'image_directory'
                      AND job.input_payload->>'source_selection_id' = retention.upload_id::text
                      AND job.status IN ('failed', 'cancelled')
                ) THEN 'failed'
                ELSE 'ready'
            END
            """
        )


def downgrade() -> None:
    """Status field remains; downgrade only removes the reconciliation revision."""
