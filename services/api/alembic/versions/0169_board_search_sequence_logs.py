"""Increase only the bounded request log for four-pattern searches.

Revision ID: 0169_board_search_sequence_logs
Revises: 0168_source_crop_runs
"""

from alembic import op
from sqlalchemy import text

revision = "0169_board_search_sequence_logs"
down_revision = "0168_source_crop_runs"
branch_labels = None
depends_on = None


def _constraint(limit: int) -> None:
    op.execute("SET LOCAL lock_timeout='5s'")
    op.drop_constraint("ck_bss_query_request", "board_search_share_query_events", schema="public")
    op.create_check_constraint(
        "ck_bss_query_request",
        "board_search_share_query_events",
        f"jsonb_typeof(request) = 'object' AND octet_length(request::text) <= {limit}",
        schema="public",
    )


def upgrade() -> None:
    _constraint(32768)


def downgrade() -> None:
    oversized = (
        op.get_bind()
        .execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM public.board_search_share_query_events "
                "WHERE octet_length(request::text) > 4096)"
            )
        )
        .scalar_one()
    )
    if oversized:
        raise RuntimeError(
            "Cannot lower the query log limit: requests larger than 4096 bytes exist."
        )
    _constraint(4096)
