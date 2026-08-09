"""Add durable cursors and batches for curated image imports.

Revision ID: 0038_curated_image_import_batches
Revises: 0037_symbol_model_registry
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0038_curated_image_import_batches"
down_revision: str | Sequence[str] | None = "0037_symbol_model_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "curated_image_import_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "image_selection_run_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("manifest_relative_path", sa.String(length=1000), nullable=False),
        sa.Column("manifest_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("total_entries", sa.BigInteger(), nullable=False),
        sa.Column("next_entry_index", sa.BigInteger(), nullable=False),
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
        sa.CheckConstraint(
            "manifest_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_curated_image_import_sources_manifest_checksum",
        ),
        sa.CheckConstraint(
            "manifest_relative_path !~ '(^|/)\\.\\.(/|$)' AND "
            "manifest_relative_path !~ '^[A-Za-z]:' AND "
            "manifest_relative_path NOT LIKE '/%' AND "
            "manifest_relative_path NOT LIKE '%\\\\%'",
            name="ck_curated_image_import_sources_manifest_path",
        ),
        sa.CheckConstraint(
            "total_entries > 0 AND next_entry_index >= 0 AND next_entry_index <= total_entries",
            name="ck_curated_image_import_sources_cursor",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["image_selection_run_id"],
            ["image_selection_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "image_selection_run_id",
            name="uq_curated_image_import_sources_selection_run",
        ),
    )
    op.create_index(
        "ix_curated_image_import_sources_game_created",
        "curated_image_import_sources",
        ["game_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "curated_image_import_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_number", sa.Integer(), nullable=False),
        sa.Column("start_index", sa.BigInteger(), nullable=False),
        sa.Column("end_index", sa.BigInteger(), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "batch_number > 0 AND start_index >= 0 AND end_index > start_index",
            name="ck_curated_image_import_batches_range",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["curated_image_import_sources.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id",
            "batch_number",
            name="uq_curated_image_import_batches_number",
        ),
        sa.UniqueConstraint(
            "source_id",
            "start_index",
            name="uq_curated_image_import_batches_start",
        ),
        sa.UniqueConstraint("job_id", name="uq_curated_image_import_batches_job"),
    )
    op.create_index(
        "ix_curated_image_import_batches_source_created",
        "curated_image_import_batches",
        ["source_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_curated_image_import_batches_source_created",
        table_name="curated_image_import_batches",
    )
    op.drop_table("curated_image_import_batches")
    op.drop_index(
        "ix_curated_image_import_sources_game_created",
        table_name="curated_image_import_sources",
    )
    op.drop_table("curated_image_import_sources")
