"""Add durable deferred board-cell geometry state.

Revision ID: 0054_image_board_geometry_pending
Revises: 0053_image_review_job_completion
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0054_image_board_geometry_pending"
down_revision: str | Sequence[str] | None = "0053_image_review_job_completion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "image_board_geometry_pending",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_image_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recognized_board_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("review_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("position_index", sa.SmallInteger(), nullable=False),
        sa.Column("source_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_relative_path", sa.String(length=1000), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reason_code", sa.String(length=40), nullable=False),
        sa.Column("processing_manifest_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("processing_manifest_relative_path", sa.String(length=1000), nullable=False),
        sa.Column("pipeline_fingerprint_sha256", sa.String(length=64), nullable=False),
        sa.Column("expected_geometry_revision", sa.Integer(), nullable=False),
        sa.Column("expected_review_resolution_revision", sa.Integer(), nullable=False),
        sa.Column("resolved_geometry_revision", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "sequence_number > 0 AND position_index BETWEEN 0 AND 8 "
            "AND expected_geometry_revision >= 0 "
            "AND expected_review_resolution_revision >= 0",
            name="ck_image_board_geometry_pending_values",
        ),
        sa.CheckConstraint(
            "source_checksum_sha256 ~ '^[0-9a-f]{64}$' "
            "AND processing_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$' "
            "AND pipeline_fingerprint_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_board_geometry_pending_checksums",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'resolved', 'superseded')",
            name="ck_image_board_geometry_pending_status",
        ),
        sa.CheckConstraint(
            "reason_code IN ('insufficient_centers', 'incomplete_lattice', "
            "'residual_too_high', 'source_unavailable')",
            name="ck_image_board_geometry_pending_reason",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND resolved_geometry_revision IS NULL "
            "AND resolved_at IS NULL AND superseded_at IS NULL) OR "
            "(status = 'resolved' AND resolved_geometry_revision IS NOT NULL "
            "AND resolved_geometry_revision > expected_geometry_revision "
            "AND resolved_at IS NOT NULL AND superseded_at IS NULL) OR "
            "(status = 'superseded' AND resolved_geometry_revision IS NULL "
            "AND resolved_at IS NULL AND superseded_at IS NOT NULL)",
            name="ck_image_board_geometry_pending_lifecycle",
        ),
        sa.CheckConstraint(
            r"length(btrim(source_relative_path)) > 0 "
            r"AND source_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)' "
            r"AND length(btrim(processing_manifest_relative_path)) > 0 "
            r"AND processing_manifest_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'",
            name="ck_image_board_geometry_pending_paths",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["import_job_id"], ["jobs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_image_id"], ["source_images.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["recognized_board_id"], ["recognized_boards.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["review_item_id"], ["image_review_items.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "import_job_id",
            "source_image_id",
            "position_index",
            "processing_manifest_checksum_sha256",
            name="uq_image_board_geometry_pending_manifest",
        ),
    )
    op.create_index(
        "ix_image_board_geometry_pending_job_status_sequence",
        "image_board_geometry_pending",
        ["import_job_id", "status", "sequence_number", "position_index", "id"],
    )
    op.create_index(
        "uq_image_board_geometry_pending_current",
        "image_board_geometry_pending",
        ["import_job_id", "source_image_id", "position_index"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_image_board_geometry_pending_current",
        table_name="image_board_geometry_pending",
    )
    op.drop_index(
        "ix_image_board_geometry_pending_job_status_sequence",
        table_name="image_board_geometry_pending",
    )
    op.drop_table("image_board_geometry_pending")
