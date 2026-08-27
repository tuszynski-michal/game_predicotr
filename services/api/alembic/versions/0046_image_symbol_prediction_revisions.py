"""Store append-only predictions for explicit pending-only symbol refreshes."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0046_image_symbol_prediction_revisions"
down_revision: str | Sequence[str] | None = "0045_canonical_image_sequences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "image_symbol_prediction_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recognized_board_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_iteration_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("model_version", sa.String(length=150), nullable=False),
        sa.Column("model_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("crop_manifest_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("predictions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(btrim(model_version)) > 0 AND model_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_symbol_prediction_revisions_model",
        ),
        sa.CheckConstraint(
            "crop_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_symbol_prediction_revisions_crop_manifest",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["review_item_id"], ["image_review_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["recognized_board_id"], ["recognized_boards.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["source_job_id"], ["jobs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["model_iteration_id"],
            ["symbol_model_iterations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "review_item_id",
            "model_checksum_sha256",
            "crop_manifest_checksum_sha256",
            name="uq_image_symbol_prediction_revision_snapshot",
        ),
    )
    op.create_index(
        "ix_image_symbol_prediction_revisions_item_created",
        "image_symbol_prediction_revisions",
        ["review_item_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_image_symbol_prediction_revisions_item_created",
        table_name="image_symbol_prediction_revisions",
    )
    op.drop_table("image_symbol_prediction_revisions")
