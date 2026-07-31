"""Add durable, revocable Reviewer access sessions and audit.

Revision ID: 0021_reviewer_access
Revises: 0020_verified_cohorts
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_reviewer_access"
down_revision: str | Sequence[str] | None = "0020_verified_cohorts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reviewer_access_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code_salt", sa.LargeBinary(length=16), nullable=False),
        sa.Column("code_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("failed_attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_hash", sa.LargeBinary(length=32), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_unlocked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_reviewer_access_sessions_expiration",
        ),
        sa.CheckConstraint(
            "failed_attempts BETWEEN 0 AND 5",
            name="ck_reviewer_access_sessions_failed_attempts",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["import_job_id"], ["jobs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_reviewer_access_sessions_game_id",
        "reviewer_access_sessions",
        ["game_id"],
    )
    op.create_index(
        "ix_reviewer_access_sessions_import_job_id",
        "reviewer_access_sessions",
        ["import_job_id"],
    )
    op.create_index(
        "ix_reviewer_access_sessions_token_hash",
        "reviewer_access_sessions",
        ["token_hash"],
        unique=True,
    )
    op.create_table(
        "reviewer_access_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('created', 'unlock_failed', 'unlocked', 'locked', 'revoked')",
            name="ck_reviewer_access_audit_events_type",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["reviewer_access_sessions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_reviewer_access_audit_events_session_created",
        "reviewer_access_audit_events",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_reviewer_access_audit_events_session_created",
        table_name="reviewer_access_audit_events",
    )
    op.drop_table("reviewer_access_audit_events")
    op.drop_index(
        "ix_reviewer_access_sessions_token_hash",
        table_name="reviewer_access_sessions",
    )
    op.drop_index(
        "ix_reviewer_access_sessions_import_job_id",
        table_name="reviewer_access_sessions",
    )
    op.drop_index(
        "ix_reviewer_access_sessions_game_id",
        table_name="reviewer_access_sessions",
    )
    op.drop_table("reviewer_access_sessions")
