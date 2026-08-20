"""Persist scoped Reviewer work assignments and their lease history.

Revision ID: 0051_reviewer_work_assignments
Revises: 0050_image_review_first_save_wins
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0051_reviewer_work_assignments"
down_revision: str | Sequence[str] | None = "0050_image_review_first_save_wins"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reviewer_work_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_type", sa.String(length=16), nullable=False),
        sa.Column("lease_owner", sa.String(length=200), nullable=False),
        sa.Column("lease_token", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_reason", sa.String(length=100), nullable=True),
        sa.Column("closed_by", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "assignment_type IN ('local', 'online')",
            name="ck_reviewer_work_assignments_type",
        ),
        sa.CheckConstraint(
            "length(btrim(lease_owner)) BETWEEN 1 AND 200",
            name="ck_reviewer_work_assignments_lease_owner",
        ),
        sa.CheckConstraint(
            "heartbeat_at >= created_at AND lease_expires_at > heartbeat_at "
            "AND updated_at >= heartbeat_at",
            name="ck_reviewer_work_assignments_lease_timestamps",
        ),
        sa.CheckConstraint(
            "(closed_at IS NULL AND close_reason IS NULL AND closed_by IS NULL) "
            "OR (closed_at IS NOT NULL AND closed_at >= heartbeat_at "
            "AND close_reason IS NOT NULL AND closed_by IS NOT NULL "
            "AND length(btrim(close_reason)) BETWEEN 1 AND 100 "
            "AND length(btrim(closed_by)) BETWEEN 1 AND 200)",
            name="ck_reviewer_work_assignments_closure",
        ),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
            name="fk_reviewer_work_assignments_game_id_games",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_job_id"],
            ["jobs.id"],
            name="fk_reviewer_work_assignments_import_job_id_jobs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_reviewer_work_assignments"),
    )
    op.create_index(
        "uq_reviewer_work_assignments_active_import",
        "reviewer_work_assignments",
        ["import_job_id"],
        unique=True,
        postgresql_where=sa.text("closed_at IS NULL"),
    )
    op.create_index(
        "ix_reviewer_work_assignments_active_lease",
        "reviewer_work_assignments",
        ["lease_expires_at", "import_job_id"],
        unique=False,
        postgresql_where=sa.text("closed_at IS NULL"),
    )
    op.create_index(
        "ix_reviewer_work_assignments_scope_history",
        "reviewer_work_assignments",
        ["game_id", "import_job_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_reviewer_work_assignments_scope_history",
        table_name="reviewer_work_assignments",
    )
    op.drop_index(
        "ix_reviewer_work_assignments_active_lease",
        table_name="reviewer_work_assignments",
    )
    op.drop_index(
        "uq_reviewer_work_assignments_active_import",
        table_name="reviewer_work_assignments",
    )
    op.drop_table("reviewer_work_assignments")
