"""Add a frozen board-search archive independent from operational review.

Revision ID: 0098_legacy_board_search_archive
Revises: 0097_page_source_exclusions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0098_legacy_board_search_archive"
down_revision: str | Sequence[str] | None = "0097_page_source_exclusions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "legacy_board_search_archive_documents",
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("board_relative_path", sa.String(1000), nullable=False),
        sa.Column("board_checksum_sha256", sa.String(64), nullable=False),
        sa.Column(
            "known_evidence_positions",
            postgresql.ARRAY(sa.String(2)),
            nullable=False,
        ),
        sa.Column(
            "primary_symbol_mobile_codes",
            postgresql.ARRAY(sa.SmallInteger()),
            nullable=False,
        ),
        sa.Column(
            "alternative_rank_1_mobile_codes",
            postgresql.ARRAY(sa.SmallInteger()),
            nullable=False,
        ),
        sa.Column(
            "alternative_rank_2_mobile_codes",
            postgresql.ARRAY(sa.SmallInteger()),
            nullable=False,
        ),
        sa.Column(
            "alternative_rank_3_mobile_codes",
            postgresql.ARRAY(sa.SmallInteger()),
            nullable=False,
        ),
        sa.Column(
            "alternative_rank_4_mobile_codes",
            postgresql.ARRAY(sa.SmallInteger()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "sequence_number > 0",
            name="ck_legacy_board_search_archive_documents_sequence_positive",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'corrected')",
            name="ck_legacy_board_search_archive_documents_status",
        ),
        sa.CheckConstraint(
            "board_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_legacy_board_search_archive_documents_checksum",
        ),
        sa.CheckConstraint(
            "length(btrim(board_relative_path)) > 0 "
            "AND board_relative_path !~ '(^/|(^|/)\\.\\.(/|$)|\\\\)'",
            name="ck_legacy_board_search_archive_documents_path",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("game_id", "sequence_number"),
    )
    op.create_index(
        "ix_legacy_board_search_archive_documents_game_status_sequence",
        "legacy_board_search_archive_documents",
        ["game_id", "status", "sequence_number"],
    )

    op.create_table(
        "legacy_board_search_archive_states",
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("sequence_start", sa.BigInteger(), nullable=False),
        sa.Column("sequence_end", sa.BigInteger(), nullable=False),
        sa.Column("document_count", sa.BigInteger(), nullable=False),
        sa.Column("source_preview_fingerprint", sa.String(64), nullable=False),
        sa.Column("archive_fingerprint", sa.String(64), nullable=False),
        sa.Column("failure_message", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('building', 'ready', 'failed')",
            name="ck_legacy_board_search_archive_states_status",
        ),
        sa.CheckConstraint(
            "sequence_start > 0 AND sequence_end >= sequence_start AND document_count >= 0",
            name="ck_legacy_board_search_archive_states_range",
        ),
        sa.CheckConstraint(
            "source_preview_fingerprint ~ '^[0-9a-f]{64}$' "
            "AND archive_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_legacy_board_search_archive_states_fingerprints",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("game_id"),
    )


def downgrade() -> None:
    op.drop_table("legacy_board_search_archive_states")
    op.drop_index(
        "ix_legacy_board_search_archive_documents_game_status_sequence",
        table_name="legacy_board_search_archive_documents",
    )
    op.drop_table("legacy_board_search_archive_documents")
