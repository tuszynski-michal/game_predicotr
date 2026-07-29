"""Add domain projections and staging for image processing.

Revision ID: 0017_image_processing
Revises: 0016_image_orchestration
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_image_processing"
down_revision: str | Sequence[str] | None = "0016_image_orchestration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "image_pipeline_stage_results",
        sa.Column("file_execution_key", sa.String(length=64), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("adapter_version", sa.String(length=150), nullable=False),
        sa.Column("result_payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "stage IN ('discovery', 'normalization', 'board_detection', "
            "'board_crops', 'sequence_ocr', 'symbol_inference')",
            name="ck_image_pipeline_stage_results_stage",
        ),
        sa.CheckConstraint(
            "length(btrim(adapter_version)) > 0",
            name="ck_image_pipeline_stage_results_adapter_version",
        ),
        sa.ForeignKeyConstraint(
            ["file_execution_key"],
            ["image_file_executions.file_execution_key"],
            name="fk_image_pipeline_stage_results_execution",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "file_execution_key",
            "stage",
            name="pk_image_pipeline_stage_results",
        ),
    )

    op.create_table(
        "source_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_execution_key", sa.String(length=64), nullable=False),
        sa.Column("relative_path", sa.String(length=1000), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_source_images_checksum",
        ),
        sa.CheckConstraint(
            "width > 0 AND height > 0",
            name="ck_source_images_dimensions_positive",
        ),
        sa.CheckConstraint(
            "status IN ('discovered', 'processing', 'waiting_for_review', "
            "'accepted', 'rejected', 'completed', 'failed')",
            name="ck_source_images_status",
        ),
        sa.CheckConstraint(
            r"length(btrim(relative_path)) > 0 "
            r"AND relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'",
            name="ck_source_images_relative_path",
        ),
        sa.ForeignKeyConstraint(
            ["file_execution_key"],
            ["image_file_executions.file_execution_key"],
            name="fk_source_images_execution",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_job_id"],
            ["jobs.id"],
            name="fk_source_images_job",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_source_images"),
        sa.UniqueConstraint(
            "import_job_id",
            "checksum_sha256",
            name="uq_source_images_job_checksum",
        ),
        sa.UniqueConstraint(
            "import_job_id",
            "file_execution_key",
            name="uq_source_images_job_execution",
        ),
    )
    op.create_index(
        "ix_source_images_job_status",
        "source_images",
        ["import_job_id", "status"],
        unique=False,
    )

    op.create_table(
        "recognized_boards",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_image_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position_index", sa.SmallInteger(), nullable=False),
        sa.Column("sequence_number_raw", sa.String(length=100), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=True),
        sa.Column("sequence_confidence", sa.Float(), nullable=False),
        sa.Column("board_geometry", postgresql.JSONB(), nullable=False),
        sa.Column("board_relative_path", sa.String(length=1000), nullable=False),
        sa.Column("board_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("cells_prediction", postgresql.JSONB(), nullable=False),
        sa.Column("board_confidence", sa.Float(), nullable=False),
        sa.Column("pipeline_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "position_index BETWEEN 0 AND 8",
            name="ck_recognized_boards_position",
        ),
        sa.CheckConstraint(
            "sequence_number IS NULL OR sequence_number > 0",
            name="ck_recognized_boards_sequence_positive",
        ),
        sa.CheckConstraint(
            "sequence_confidence BETWEEN 0 AND 1 AND board_confidence BETWEEN 0 AND 1",
            name="ck_recognized_boards_confidence",
        ),
        sa.CheckConstraint(
            "board_checksum_sha256 ~ '^[0-9a-f]{64}$' AND pipeline_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_recognized_boards_sha256",
        ),
        sa.CheckConstraint(
            r"length(btrim(board_relative_path)) > 0 "
            r"AND board_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'",
            name="ck_recognized_boards_relative_path",
        ),
        sa.CheckConstraint(
            "status IN ('pending_review', 'accepted', 'corrected', 'rejected')",
            name="ck_recognized_boards_status",
        ),
        sa.ForeignKeyConstraint(
            ["source_image_id"],
            ["source_images.id"],
            name="fk_recognized_boards_source_image",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_recognized_boards"),
        sa.UniqueConstraint(
            "source_image_id",
            "position_index",
            name="uq_recognized_boards_source_position",
        ),
    )
    op.create_index(
        "ix_recognized_boards_source_status",
        "recognized_boards",
        ["source_image_id", "status"],
        unique=False,
    )

    op.create_table(
        "cell_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recognized_board_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_index", sa.SmallInteger(), nullable=False),
        sa.Column("column_index", sa.SmallInteger(), nullable=False),
        sa.Column("crop_relative_path", sa.String(length=1000), nullable=False),
        sa.Column("crop_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("cropper_version", sa.String(length=150), nullable=False),
        sa.Column("prediction", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "row_index BETWEEN 0 AND 2 AND column_index BETWEEN 0 AND 4",
            name="ck_cell_observations_coordinates",
        ),
        sa.CheckConstraint(
            "crop_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_cell_observations_checksum",
        ),
        sa.CheckConstraint(
            r"length(btrim(crop_relative_path)) > 0 "
            r"AND crop_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'",
            name="ck_cell_observations_relative_path",
        ),
        sa.ForeignKeyConstraint(
            ["recognized_board_id"],
            ["recognized_boards.id"],
            name="fk_cell_observations_board",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_cell_observations"),
        sa.UniqueConstraint(
            "recognized_board_id",
            "row_index",
            "column_index",
            name="uq_cell_observations_board_cell",
        ),
    )

    op.create_table(
        "image_review_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recognized_board_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("resolved_value", postgresql.JSONB(), nullable=True),
        sa.Column("resolved_by", sa.String(length=200), nullable=True),
        sa.Column("resolution_revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'corrected', 'rejected')",
            name="ck_image_review_items_status",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND resolved_value IS NULL "
            "AND resolved_by IS NULL AND resolved_at IS NULL "
            "AND resolution_revision = 0) OR "
            "(status <> 'pending' AND resolved_value IS NOT NULL "
            "AND resolved_by IS NOT NULL AND resolved_at IS NOT NULL "
            "AND resolution_revision > 0)",
            name="ck_image_review_items_resolution_state",
        ),
        sa.ForeignKeyConstraint(
            ["recognized_board_id"],
            ["recognized_boards.id"],
            name="fk_image_review_items_board",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_image_review_items"),
        sa.UniqueConstraint(
            "recognized_board_id",
            name="uq_image_review_items_board",
        ),
    )

    op.create_table(
        "image_layout_staging_rows",
        sa.Column("import_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recognized_board_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("cells", postgresql.ARRAY(sa.SmallInteger(), dimensions=1), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "sequence_number > 0",
            name="ck_image_layout_staging_sequence_positive",
        ),
        sa.CheckConstraint(
            "cardinality(cells) = 15 AND 1 <= ALL(cells) AND 32767 >= ALL(cells)",
            name="ck_image_layout_staging_cells",
        ),
        sa.ForeignKeyConstraint(
            ["import_job_id"],
            ["jobs.id"],
            name="fk_image_layout_staging_job",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recognized_board_id"],
            ["recognized_boards.id"],
            name="fk_image_layout_staging_board",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["review_item_id"],
            ["image_review_items.id"],
            name="fk_image_layout_staging_review",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "import_job_id",
            "recognized_board_id",
            name="pk_image_layout_staging_rows",
        ),
        sa.UniqueConstraint(
            "review_item_id",
            name="uq_image_layout_staging_review",
        ),
    )
    op.create_index(
        "ix_image_layout_staging_job_sequence",
        "image_layout_staging_rows",
        ["import_job_id", "sequence_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_image_layout_staging_job_sequence",
        table_name="image_layout_staging_rows",
    )
    op.drop_table("image_layout_staging_rows")
    op.drop_table("image_review_items")
    op.drop_table("cell_observations")
    op.drop_index(
        "ix_recognized_boards_source_status",
        table_name="recognized_boards",
    )
    op.drop_table("recognized_boards")
    op.drop_index("ix_source_images_job_status", table_name="source_images")
    op.drop_table("source_images")
    op.drop_table("image_pipeline_stage_results")
