"""Add immutable verified operational review cohort exports.

Revision ID: 0020_verified_cohorts
Revises: 0019_review_geometry
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_verified_cohorts"
down_revision: str | Sequence[str] | None = "0019_review_geometry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "image_verified_cohort_exports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("input_state_sha256", sa.String(length=64), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("artifact_relative_path", sa.String(length=1000), nullable=False),
        sa.Column("board_count", sa.Integer(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("pending_item_count", sa.Integer(), nullable=False),
        sa.Column("rejected_item_count", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "version > 0",
            name="ck_image_verified_cohort_exports_version",
        ),
        sa.CheckConstraint(
            "input_state_sha256 ~ '^[0-9a-f]{64}$' AND payload_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_verified_cohort_exports_sha256",
        ),
        sa.CheckConstraint(
            "board_count > 0 AND sample_count = board_count * 15 "
            "AND pending_item_count >= 0 AND rejected_item_count >= 0",
            name="ck_image_verified_cohort_exports_counts",
        ),
        sa.CheckConstraint(
            r"length(btrim(artifact_relative_path)) > 0 "
            r"AND artifact_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'",
            name="ck_image_verified_cohort_exports_relative_path",
        ),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
            name="fk_image_verified_cohort_exports_game",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_job_id"],
            ["jobs.id"],
            name="fk_image_verified_cohort_exports_job",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_image_verified_cohort_exports"),
        sa.UniqueConstraint(
            "game_id",
            "import_job_id",
            "version",
            name="uq_image_verified_cohort_exports_version",
        ),
        sa.UniqueConstraint(
            "game_id",
            "import_job_id",
            "input_state_sha256",
            name="uq_image_verified_cohort_exports_state",
        ),
    )


def downgrade() -> None:
    op.drop_table("image_verified_cohort_exports")
