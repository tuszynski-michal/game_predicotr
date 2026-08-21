"""Bind online Reviewer work assignments to their scoped access sessions.

Revision ID: 0052_reviewer_assignment_sessions
Revises: 0051_reviewer_work_assignments
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0052_reviewer_assignment_sessions"
down_revision: str | Sequence[str] | None = "0051_reviewer_work_assignments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_reviewer_access_sessions_scope_identity",
        "reviewer_access_sessions",
        ["id", "game_id", "import_job_id"],
    )
    op.add_column(
        "reviewer_work_assignments",
        sa.Column(
            "reviewer_access_session_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_reviewer_work_assignments_session_mode",
        "reviewer_work_assignments",
        "(assignment_type = 'local' AND reviewer_access_session_id IS NULL) "
        "OR (assignment_type = 'online' AND reviewer_access_session_id IS NOT NULL)",
    )
    op.create_foreign_key(
        "fk_reviewer_work_assignments_session_scope",
        "reviewer_work_assignments",
        "reviewer_access_sessions",
        ["reviewer_access_session_id", "game_id", "import_job_id"],
        ["id", "game_id", "import_job_id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_reviewer_work_assignments_access_session",
        "reviewer_work_assignments",
        ["reviewer_access_session_id"],
        unique=True,
        postgresql_where=sa.text("reviewer_access_session_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_reviewer_work_assignments_access_session",
        table_name="reviewer_work_assignments",
    )
    op.drop_constraint(
        "fk_reviewer_work_assignments_session_scope",
        "reviewer_work_assignments",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_reviewer_work_assignments_session_mode",
        "reviewer_work_assignments",
        type_="check",
    )
    op.drop_column("reviewer_work_assignments", "reviewer_access_session_id")
    op.drop_constraint(
        "uq_reviewer_access_sessions_scope_identity",
        "reviewer_access_sessions",
        type_="unique",
    )
