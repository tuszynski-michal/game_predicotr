"""Create the compact projection used by partial board search.

Revision ID: 0057_board_search_projection
Revises: 0056_remote_manual_selection_persistence
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0057_board_search_projection"
down_revision: str | Sequence[str] | None = "0056_remote_manual_selection_persistence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "image_board_search_candidates",
        sa.Column("review_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recognized_board_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("board_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("board_confidence", sa.Float(), nullable=False),
        sa.Column("sequence_confidence", sa.Float(), nullable=False),
        sa.Column("source_pixel_count", sa.BigInteger(), nullable=False),
        sa.Column("primary_symbol_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "alternative_symbol_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("primary_match_tokens", postgresql.ARRAY(sa.String(length=80)), nullable=False),
        sa.Column(
            "alternative_rank_1_match_tokens",
            postgresql.ARRAY(sa.String(length=80)),
            nullable=False,
        ),
        sa.Column(
            "alternative_rank_2_match_tokens",
            postgresql.ARRAY(sa.String(length=80)),
            nullable=False,
        ),
        sa.Column(
            "alternative_rank_3_match_tokens",
            postgresql.ARRAY(sa.String(length=80)),
            nullable=False,
        ),
        sa.Column(
            "alternative_rank_4_match_tokens",
            postgresql.ARRAY(sa.String(length=80)),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "sequence_number > 0", name="ck_image_board_search_candidates_sequence_positive"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'corrected')",
            name="ck_image_board_search_candidates_status",
        ),
        sa.CheckConstraint(
            "board_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_board_search_candidates_checksum",
        ),
        sa.CheckConstraint(
            "board_confidence BETWEEN 0 AND 1 AND sequence_confidence BETWEEN 0 AND 1 "
            "AND source_pixel_count > 0",
            name="ck_image_board_search_candidates_scores",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(primary_symbol_codes) = 'array' "
            "AND jsonb_array_length(primary_symbol_codes) = 15",
            name="ck_image_board_search_candidates_primary_cells",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(alternative_symbol_codes) = 'array' "
            "AND jsonb_array_length(alternative_symbol_codes) = 15",
            name="ck_image_board_search_candidates_alternative_cells",
        ),
        sa.ForeignKeyConstraint(["review_item_id"], ["image_review_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["import_job_id"], ["jobs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["recognized_board_id"], ["recognized_boards.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("review_item_id", name="pk_image_board_search_candidates"),
    )
    op.create_index(
        "ix_image_board_search_candidates_game_sequence",
        "image_board_search_candidates",
        ["game_id", "sequence_number"],
    )
    op.create_index(
        "ix_image_board_search_candidates_game_status_sequence",
        "image_board_search_candidates",
        ["game_id", "status", "sequence_number"],
    )
    for column_name, index_name in (
        ("primary_match_tokens", "ix_ibsc_primary_tokens_gin"),
        ("alternative_rank_1_match_tokens", "ix_ibsc_alt1_tokens_gin"),
        ("alternative_rank_2_match_tokens", "ix_ibsc_alt2_tokens_gin"),
        ("alternative_rank_3_match_tokens", "ix_ibsc_alt3_tokens_gin"),
        ("alternative_rank_4_match_tokens", "ix_ibsc_alt4_tokens_gin"),
    ):
        op.create_index(
            index_name,
            "image_board_search_candidates",
            [column_name],
            postgresql_using="gin",
        )

    op.create_table(
        "image_board_search_documents",
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("review_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("selection_kind", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "sequence_number > 0", name="ck_image_board_search_documents_sequence_positive"
        ),
        sa.CheckConstraint(
            "selection_kind IN ('canonical', 'pending')",
            name="ck_image_board_search_documents_selection_kind",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["review_item_id"],
            ["image_board_search_candidates.review_item_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "game_id", "sequence_number", name="pk_image_board_search_documents"
        ),
        sa.UniqueConstraint("review_item_id", name="uq_image_board_search_documents_review_item"),
    )
    op.create_index(
        "ix_image_board_search_documents_game_review",
        "image_board_search_documents",
        ["game_id", "review_item_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_image_board_search_documents_game_review", "image_board_search_documents")
    op.drop_table("image_board_search_documents")
    for index_name in (
        "ix_ibsc_alt4_tokens_gin",
        "ix_ibsc_alt3_tokens_gin",
        "ix_ibsc_alt2_tokens_gin",
        "ix_ibsc_alt1_tokens_gin",
        "ix_ibsc_primary_tokens_gin",
    ):
        op.drop_index(
            index_name,
            "image_board_search_candidates",
        )
    op.drop_index(
        "ix_image_board_search_candidates_game_status_sequence",
        "image_board_search_candidates",
    )
    op.drop_index(
        "ix_image_board_search_candidates_game_sequence",
        "image_board_search_candidates",
    )
    op.drop_table("image_board_search_candidates")
