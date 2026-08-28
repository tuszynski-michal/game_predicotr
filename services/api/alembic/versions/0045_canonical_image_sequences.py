"""Persist one canonical resolved source per game sequence.

Revision ID: 0045_canonical_image_sequences
Revises: 0044_representative_ranking
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0045_canonical_image_sequences"
down_revision: str | Sequence[str] | None = "0044_representative_ranking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "image_sequence_canonical",
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("review_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recognized_board_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_image_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("board_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("resolution_revision", sa.Integer(), nullable=False),
        sa.Column("geometry_revision", sa.Integer(), nullable=False),
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
            "sequence_number > 0 AND resolution_revision > 0 AND geometry_revision >= 0",
            name="ck_image_sequence_canonical_values",
        ),
        sa.CheckConstraint(
            "status IN ('accepted', 'corrected')",
            name="ck_image_sequence_canonical_status",
        ),
        sa.CheckConstraint(
            "source_checksum_sha256 ~ '^[0-9a-f]{64}$' "
            "AND board_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_sequence_canonical_checksums",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["review_item_id"], ["image_review_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["recognized_board_id"], ["recognized_boards.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["import_job_id"], ["jobs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_image_id"], ["source_images.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("game_id", "sequence_number", name="pk_image_sequence_canonical"),
        sa.UniqueConstraint(
            "game_id", "sequence_number", name="uq_image_sequence_canonical_game_sequence"
        ),
    )
    op.create_index(
        "ix_image_sequence_canonical_game_sequence",
        "image_sequence_canonical",
        ["game_id", "sequence_number"],
    )

    op.create_table(
        "image_sequence_alternatives",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("import_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_relative_path", sa.String(length=1000), nullable=False),
        sa.Column("reason", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "sequence_number > 0 AND source_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_sequence_alternatives_values",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["import_job_id"], ["jobs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_image_sequence_alternatives"),
        sa.UniqueConstraint(
            "game_id",
            "sequence_number",
            "source_checksum_sha256",
            "import_job_id",
            name="uq_image_sequence_alternatives_source",
        ),
    )
    op.create_index(
        "ix_image_sequence_alternatives_game_sequence",
        "image_sequence_alternatives",
        ["game_id", "sequence_number"],
    )

    # Reuse the current source-selection ordering when materialising the first
    # canonical projection. Existing duplicate rows remain available through
    # the historical staging tables and are not deleted.
    op.execute(
        sa.text(
            """
            INSERT INTO image_sequence_canonical (
                game_id, sequence_number, review_item_id, recognized_board_id,
                import_job_id, source_image_id, source_checksum_sha256,
                board_checksum_sha256, status, resolution_revision, geometry_revision
            )
            SELECT DISTINCT ON (j.game_id, s.sequence_number)
                j.game_id,
                s.sequence_number,
                r.id,
                b.id,
                s.import_job_id,
                source.id,
                source.checksum_sha256,
                b.board_checksum_sha256,
                r.status,
                r.resolution_revision,
                b.geometry_revision
            FROM image_layout_staging_rows s
            JOIN image_review_items r ON r.id = s.review_item_id
            JOIN recognized_boards b ON b.id = s.recognized_board_id
            JOIN source_images source ON source.id = b.source_image_id
            JOIN jobs j ON j.id = s.import_job_id
            LEFT JOIN LATERAL (
                SELECT selected_review_item_id
                FROM image_sequence_source_override_events o
                WHERE o.game_id = j.game_id
                  AND o.sequence_number = s.sequence_number
                ORDER BY o.revision DESC
                LIMIT 1
            ) selected_override ON TRUE
            WHERE r.status IN ('accepted', 'corrected')
            ORDER BY
                j.game_id,
                s.sequence_number,
                CASE WHEN selected_override.selected_review_item_id = r.id THEN 0 ELSE 1 END,
                b.board_confidence DESC,
                b.sequence_confidence DESC,
                r.id
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_image_sequence_alternatives_game_sequence",
        table_name="image_sequence_alternatives",
    )
    op.drop_table("image_sequence_alternatives")
    op.drop_index(
        "ix_image_sequence_canonical_game_sequence",
        table_name="image_sequence_canonical",
    )
    op.drop_table("image_sequence_canonical")
