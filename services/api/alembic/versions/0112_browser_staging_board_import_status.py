"""Persist the board-import milestone separately from retention and job history."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0112_browser_staging_board_import_status"
down_revision: str | Sequence[str] | None = "0111_partial_grid_training_qualification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _constraint_name(schema: str) -> str:
    return (
        "ck_v2_browser_selection_retention_board_import_status"
        if schema == "game_data_v2"
        else "ck_browser_selection_retention_board_import_status"
    )


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    for schema in ("public", "game_data_v2"):
        op.add_column(
            "browser_selection_retention_states",
            sa.Column(
                "board_import_status",
                sa.String(length=24),
                nullable=False,
                server_default="ready",
            ),
            schema=schema,
        )
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
        op.create_check_constraint(
            _constraint_name(schema),
            "browser_selection_retention_states",
            "board_import_status IN ('ready', 'importing', 'boards_imported', 'failed')",
            schema=schema,
        )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    for schema in ("game_data_v2", "public"):
        op.drop_constraint(
            _constraint_name(schema),
            "browser_selection_retention_states",
            schema=schema,
            type_="check",
        )
        op.drop_column("browser_selection_retention_states", "board_import_status", schema=schema)
