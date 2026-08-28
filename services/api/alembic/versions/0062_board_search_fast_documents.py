"""Create a narrow, selected-board read model for board search.

Revision ID: 0062_board_search_fast_documents
Revises: 0061_board_search_document_evidence
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0062_board_search_fast_documents"
down_revision: str | Sequence[str] | None = "0061_board_search_document_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MOBILE_CODE_COLUMNS = (
    "primary_symbol_mobile_codes",
    "alternative_rank_1_mobile_codes",
    "alternative_rank_2_mobile_codes",
    "alternative_rank_3_mobile_codes",
    "alternative_rank_4_mobile_codes",
)
_COPY_COLUMNS = (
    "game_id",
    "sequence_number",
    "review_item_id",
    "recognized_board_id",
    "import_job_id",
    "status",
    "board_checksum_sha256",
    "known_evidence_positions",
    *_MOBILE_CODE_COLUMNS,
)


def upgrade() -> None:
    op.create_table(
        "image_board_search_fast_documents",
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("review_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recognized_board_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("board_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "known_evidence_positions",
            postgresql.ARRAY(sa.String(length=2)),
            nullable=False,
        ),
        *(
            sa.Column(column_name, postgresql.ARRAY(sa.SmallInteger()), nullable=False)
            for column_name in _MOBILE_CODE_COLUMNS
        ),
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
            "sequence_number > 0",
            name="ck_image_board_search_fast_documents_sequence_positive",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'corrected')",
            name="ck_image_board_search_fast_documents_status",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["review_item_id"],
            ["image_board_search_candidates.review_item_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("game_id", "sequence_number"),
        sa.UniqueConstraint(
            "review_item_id", name="uq_image_board_search_fast_documents_review_item"
        ),
    )
    quoted_columns = ", ".join(_COPY_COLUMNS)
    op.execute(
        "INSERT INTO image_board_search_fast_documents "
        f"({quoted_columns}) "
        f"SELECT {quoted_columns} FROM image_board_search_documents"
    )


def downgrade() -> None:
    op.drop_table("image_board_search_fast_documents")
