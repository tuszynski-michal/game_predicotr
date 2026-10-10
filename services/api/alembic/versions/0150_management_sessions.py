"""Independent panel capabilities and retained security audit."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0150_management_sessions"
down_revision = "0149_management_stake_saves"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.create_table(
        "management_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("code_salt", sa.LargeBinary(16), nullable=False),
        sa.Column("code_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("token_hash", sa.LargeBinary(32)),
        sa.Column("token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_unlocked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "failed_attempts BETWEEN 0 AND 5", name="ck_management_session_attempts"
        ),
        sa.CheckConstraint(
            "length(btrim(label)) BETWEEN 1 AND 100", name="ck_management_session_label"
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_management_session_expiry"),
        sa.CheckConstraint(
            "octet_length(code_salt)=16 AND octet_length(code_hash)=32",
            name="ck_management_session_code",
        ),
        sa.CheckConstraint(
            "(token_hash IS NULL AND token_expires_at IS NULL) OR "
            "(token_hash IS NOT NULL AND octet_length(token_hash)=32 "
            "AND token_expires_at IS NOT NULL AND token_expires_at <= expires_at)",
            name="ck_management_session_token",
        ),
        schema="public",
    )
    op.create_index(
        "uq_management_session_token",
        "management_sessions",
        ["token_hash"],
        unique=True,
        schema="public",
        postgresql_where=sa.text("token_hash IS NOT NULL"),
    )
    op.create_index(
        "ix_management_session_expiry", "management_sessions", ["expires_at", "id"], schema="public"
    )
    op.create_table(
        "management_session_audit",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("public.management_sessions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('created','unlock_failed','unlocked','locked','revoked')",
            name="ck_management_session_event",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND octet_length(payload::text) <= 4096",
            name="ck_management_session_payload",
        ),
        schema="public",
    )
    op.create_index(
        "ix_management_session_audit",
        "management_session_audit",
        ["session_id", "created_at", "id"],
        schema="public",
    )
    op.execute(
        "CREATE TRIGGER management_session_audit_immutable "
        "BEFORE UPDATE OR DELETE ON public.management_session_audit "
        "FOR EACH ROW EXECUTE FUNCTION public.management_history_immutable()"
    )


def downgrade() -> None:
    raise RuntimeError(
        "Management links and their audit must be retained; destructive downgrade is disabled."
    )
