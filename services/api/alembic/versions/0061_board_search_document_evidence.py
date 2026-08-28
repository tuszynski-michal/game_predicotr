"""Store selected-board evidence directly in the search document projection.

Revision ID: 0061_board_search_document_evidence
Revises: 0060_board_search_mobile_code_projection
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0061_board_search_document_evidence"
down_revision: str | Sequence[str] | None = "0060_board_search_mobile_code_projection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TEXT_TOKEN_COLUMNS = (
    "primary_match_tokens",
    "alternative_rank_1_match_tokens",
    "alternative_rank_2_match_tokens",
    "alternative_rank_3_match_tokens",
    "alternative_rank_4_match_tokens",
)
_MOBILE_CODE_COLUMNS = (
    "primary_symbol_mobile_codes",
    "alternative_rank_1_mobile_codes",
    "alternative_rank_2_mobile_codes",
    "alternative_rank_3_mobile_codes",
    "alternative_rank_4_mobile_codes",
)
_COPY_COLUMNS = (
    "recognized_board_id",
    "import_job_id",
    "status",
    "board_checksum_sha256",
    *_TEXT_TOKEN_COLUMNS,
    "known_evidence_positions",
    *_MOBILE_CODE_COLUMNS,
)


def upgrade() -> None:
    op.add_column(
        "image_board_search_documents",
        sa.Column("recognized_board_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "image_board_search_documents",
        sa.Column("import_job_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "image_board_search_documents",
        sa.Column("status", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "image_board_search_documents",
        sa.Column("board_checksum_sha256", sa.String(length=64), nullable=True),
    )
    for column_name in _TEXT_TOKEN_COLUMNS:
        op.add_column(
            "image_board_search_documents",
            sa.Column(column_name, postgresql.ARRAY(sa.String(length=80)), nullable=True),
        )
    op.add_column(
        "image_board_search_documents",
        sa.Column(
            "known_evidence_positions",
            postgresql.ARRAY(sa.String(length=2)),
            nullable=True,
        ),
    )
    for column_name in _MOBILE_CODE_COLUMNS:
        op.add_column(
            "image_board_search_documents",
            sa.Column(column_name, postgresql.ARRAY(sa.SmallInteger()), nullable=True),
        )
    op.execute(
        """
        UPDATE image_board_search_documents AS document
        SET
            recognized_board_id = candidate.recognized_board_id,
            import_job_id = candidate.import_job_id,
            status = candidate.status,
            board_checksum_sha256 = candidate.board_checksum_sha256,
            primary_match_tokens = candidate.primary_match_tokens,
            alternative_rank_1_match_tokens = candidate.alternative_rank_1_match_tokens,
            alternative_rank_2_match_tokens = candidate.alternative_rank_2_match_tokens,
            alternative_rank_3_match_tokens = candidate.alternative_rank_3_match_tokens,
            alternative_rank_4_match_tokens = candidate.alternative_rank_4_match_tokens,
            known_evidence_positions = candidate.known_evidence_positions,
            primary_symbol_mobile_codes = candidate.primary_symbol_mobile_codes,
            alternative_rank_1_mobile_codes = candidate.alternative_rank_1_mobile_codes,
            alternative_rank_2_mobile_codes = candidate.alternative_rank_2_mobile_codes,
            alternative_rank_3_mobile_codes = candidate.alternative_rank_3_mobile_codes,
            alternative_rank_4_mobile_codes = candidate.alternative_rank_4_mobile_codes
        FROM image_board_search_candidates AS candidate
        WHERE candidate.review_item_id = document.review_item_id
        """
    )
    for column_name in _COPY_COLUMNS:
        op.alter_column("image_board_search_documents", column_name, nullable=False)
    op.create_check_constraint(
        "ck_image_board_search_documents_status",
        "image_board_search_documents",
        "status IN ('pending', 'accepted', 'corrected')",
    )
    for column_name, index_name in (
        ("primary_match_tokens", "ix_ibsd_primary_tokens_gin"),
        ("alternative_rank_1_match_tokens", "ix_ibsd_alt1_tokens_gin"),
        ("alternative_rank_2_match_tokens", "ix_ibsd_alt2_tokens_gin"),
        ("alternative_rank_3_match_tokens", "ix_ibsd_alt3_tokens_gin"),
        ("alternative_rank_4_match_tokens", "ix_ibsd_alt4_tokens_gin"),
    ):
        op.create_index(
            index_name,
            "image_board_search_documents",
            [column_name],
            postgresql_using="gin",
        )


def downgrade() -> None:
    for index_name in (
        "ix_ibsd_alt4_tokens_gin",
        "ix_ibsd_alt3_tokens_gin",
        "ix_ibsd_alt2_tokens_gin",
        "ix_ibsd_alt1_tokens_gin",
        "ix_ibsd_primary_tokens_gin",
    ):
        op.drop_index(index_name, table_name="image_board_search_documents")
    op.drop_constraint(
        "ck_image_board_search_documents_status",
        "image_board_search_documents",
        type_="check",
    )
    for column_name in reversed(_COPY_COLUMNS):
        op.drop_column("image_board_search_documents", column_name)
