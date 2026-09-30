"""Online board-search share sessions, their audit and query log (D-471, D-472)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0129_board_search_share_sessions"
down_revision = "0128_partial_board_reconciliation_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.create_table(
        "board_search_share_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "game_id",
            sa.Uuid(),
            sa.ForeignKey("public.games.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("label", sa.String(100), nullable=True),
        sa.Column("code_salt", sa.LargeBinary(16), nullable=False),
        sa.Column("code_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("failed_attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_hash", sa.LargeBinary(32), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_unlocked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("failed_attempts BETWEEN 0 AND 5", name="ck_bss_sessions_attempts"),
        sa.CheckConstraint(
            "label IS NULL OR length(btrim(label)) BETWEEN 1 AND 100",
            name="ck_bss_sessions_label",
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_bss_sessions_timestamps"),
        sa.CheckConstraint(
            "octet_length(code_salt) = 16 AND octet_length(code_hash) = 32",
            name="ck_bss_sessions_code_hash",
        ),
        sa.CheckConstraint(
            "(token_hash IS NULL AND token_expires_at IS NULL) OR "
            "(token_hash IS NOT NULL AND octet_length(token_hash) = 32 "
            "AND token_expires_at IS NOT NULL)",
            name="ck_bss_sessions_token_hash",
        ),
        schema="public",
    )
    op.create_index(
        "uq_bss_sessions_token_hash",
        "board_search_share_sessions",
        ["token_hash"],
        unique=True,
        schema="public",
        postgresql_where=sa.text("token_hash IS NOT NULL"),
    )
    op.create_index(
        "ix_bss_sessions_game_created",
        "board_search_share_sessions",
        ["game_id", "created_at", "id"],
        schema="public",
    )
    op.create_index(
        "ix_bss_sessions_expiry",
        "board_search_share_sessions",
        ["expires_at", "id"],
        schema="public",
    )

    op.create_table(
        "board_search_share_audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("public.board_search_share_sessions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("outcome_code", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "event_type IN ('created','unlock_failed','unlocked','locked','revoked')",
            name="ck_bss_audit_event_type",
        ),
        sa.CheckConstraint("length(btrim(outcome_code)) > 0", name="ck_bss_audit_outcome"),
        sa.CheckConstraint("jsonb_typeof(payload) = 'object'", name="ck_bss_audit_payload"),
        schema="public",
    )
    op.create_index(
        "ix_bss_audit_session_created",
        "board_search_share_audit_events",
        ["session_id", "created_at", "id"],
        schema="public",
    )

    op.create_table(
        "board_search_share_query_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("public.board_search_share_sessions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "game_id",
            sa.Uuid(),
            sa.ForeignKey("public.games.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("request", postgresql.JSONB(), nullable=False),
        sa.Column("result_summary", postgresql.JSONB(), nullable=False),
        sa.Column("outcome_code", sa.String(100), nullable=False),
        sa.CheckConstraint(
            "kind IN ('search','approximate_win','board_detail')",
            name="ck_bss_query_kind",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(request) = 'object' AND octet_length(request::text) <= 4096",
            name="ck_bss_query_request",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(result_summary) = 'object' "
            "AND octet_length(result_summary::text) <= 2048",
            name="ck_bss_query_result_summary",
        ),
        sa.CheckConstraint("length(btrim(outcome_code)) > 0", name="ck_bss_query_outcome"),
        schema="public",
    )
    op.execute(
        "CREATE INDEX ix_bss_query_session_occurred ON public.board_search_share_query_events "
        "(session_id, occurred_at DESC, id DESC)"
    )


def downgrade() -> None:
    raise RuntimeError(
        "BOARD_SEARCH_SHARE_DOWNGRADE_UNSUPPORTED: share audit and query logs may exist"
    )
