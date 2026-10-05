"""Durable symbol correction and owner-review events (D-492, TASK-0845)."""

from alembic import op
from sqlalchemy import text

revision = "0141_share_symbol_corrections"
down_revision = "0140_grid_engine_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.drop_constraint("ck_bss_query_kind", "board_search_share_query_events", schema="public")
    op.create_check_constraint(
        "ck_bss_query_kind",
        "board_search_share_query_events",
        "kind IN ('search','approximate_win','board_detail',"
        "'symbol_correction','correction_review')",
        schema="public",
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_bss_correction_operation "
        "ON public.board_search_share_query_events (session_id, (request->>'operationId')) "
        "WHERE kind='symbol_correction'"
    )
    op.execute(
        "CREATE INDEX ix_bss_correction_board "
        "ON public.board_search_share_query_events "
        "(session_id, ((request->>'sequenceNumber')::integer), occurred_at DESC, id DESC) "
        "WHERE kind IN ('symbol_correction','correction_review')"
    )
    op.execute(
        "CREATE INDEX ix_bss_correction_pattern "
        "ON public.board_search_share_query_events "
        "(session_id, (request->>'patternFingerprint'), occurred_at DESC, id DESC) "
        "WHERE kind='symbol_correction'"
    )
    op.execute(
        "CREATE INDEX ix_bss_correction_revision "
        "ON public.board_search_share_query_events "
        "(session_id, ((request->>'sequenceNumber')::integer), "
        "((request->>'boardRevision')::integer) DESC) WHERE kind='symbol_correction' "
        "AND (result_summary->>'changed')::boolean IS TRUE"
    )
    op.execute(
        "CREATE INDEX ix_bss_correction_review "
        "ON public.board_search_share_query_events (session_id, (request->>'reviewedThroughId')) "
        "WHERE kind='correction_review'"
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM public.board_search_share_query_events "
            "WHERE kind IN ('symbol_correction','correction_review'))"
        )
    ):
        raise RuntimeError(
            "BOARD_SEARCH_SHARE_CORRECTION_DOWNGRADE_UNSUPPORTED: correction history is present"
        )
    for name in (
        "uq_bss_correction_operation",
        "ix_bss_correction_board",
        "ix_bss_correction_pattern",
        "ix_bss_correction_review",
        "ix_bss_correction_revision",
    ):
        op.drop_index(name, table_name="board_search_share_query_events", schema="public")
    op.drop_constraint("ck_bss_query_kind", "board_search_share_query_events", schema="public")
    op.create_check_constraint(
        "ck_bss_query_kind",
        "board_search_share_query_events",
        "kind IN ('search','approximate_win','board_detail')",
        schema="public",
    )
