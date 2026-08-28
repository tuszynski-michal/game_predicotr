"""Remove obsolete board-search storage and the legacy grid flag.

Revision ID: 0075_remove_obsolete_board_search_storage
Revises: 0074_unknown_layout_cells
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0075_remove_obsolete_board_search_storage"
down_revision: str | Sequence[str] | None = "0074_unknown_layout_cells"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TOKEN_COLUMNS = (
    "primary_match_tokens",
    "alternative_rank_1_match_tokens",
    "alternative_rank_2_match_tokens",
    "alternative_rank_3_match_tokens",
    "alternative_rank_4_match_tokens",
)
_CANDIDATE_TOKEN_INDEXES = (
    "ix_ibsc_primary_tokens_gin",
    "ix_ibsc_alt1_tokens_gin",
    "ix_ibsc_alt2_tokens_gin",
    "ix_ibsc_alt3_tokens_gin",
    "ix_ibsc_alt4_tokens_gin",
)
_DOCUMENT_TOKEN_INDEXES = (
    "ix_ibsd_primary_tokens_gin",
    "ix_ibsd_alt1_tokens_gin",
    "ix_ibsd_alt2_tokens_gin",
    "ix_ibsd_alt3_tokens_gin",
    "ix_ibsd_alt4_tokens_gin",
)
_MOBILE_COLUMNS = (
    "primary_symbol_mobile_codes",
    "alternative_rank_1_mobile_codes",
    "alternative_rank_2_mobile_codes",
    "alternative_rank_3_mobile_codes",
    "alternative_rank_4_mobile_codes",
)


def upgrade() -> None:
    # Preserve the complete quality audit before removing the redundant booleans.
    op.execute(
        "UPDATE image_symbol_review_cells SET quality_issue = 'grid_issue' "
        "WHERE has_grid_issue = true AND quality_issue IS NULL"
    )
    op.execute(
        "UPDATE image_symbol_review_events SET "
        "previous_quality_issue = 'grid_issue' "
        "WHERE previous_has_grid_issue = true AND previous_quality_issue IS NULL"
    )
    op.execute(
        "UPDATE image_symbol_review_events SET quality_issue = 'grid_issue' "
        "WHERE has_grid_issue = true AND quality_issue IS NULL"
    )
    op.drop_index(
        "ix_image_symbol_review_cells_grid_issue",
        table_name="image_symbol_review_cells",
    )
    op.drop_constraint(
        "ck_image_symbol_review_cells_grid_issue_state",
        "image_symbol_review_cells",
        type_="check",
    )
    op.drop_column("image_symbol_review_cells", "has_grid_issue")
    op.drop_column("image_symbol_review_events", "previous_has_grid_issue")
    op.drop_column("image_symbol_review_events", "has_grid_issue")

    for index_name in _CANDIDATE_TOKEN_INDEXES:
        op.drop_index(index_name, table_name="image_board_search_candidates")
    for column_name in _TOKEN_COLUMNS:
        op.drop_column("image_board_search_candidates", column_name)

    # All production reads and rebuilds use the narrow fast projection directly.
    op.drop_table("image_board_search_documents")


def downgrade() -> None:
    _restore_candidate_tokens()
    _restore_legacy_documents()

    op.add_column(
        "image_symbol_review_cells",
        sa.Column(
            "has_grid_issue",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute(
        "UPDATE image_symbol_review_cells SET has_grid_issue = (quality_issue = 'grid_issue')"
    )
    op.create_check_constraint(
        "ck_image_symbol_review_cells_grid_issue_state",
        "image_symbol_review_cells",
        "NOT has_grid_issue OR review_state = 'pending'",
    )
    op.create_index(
        "ix_image_symbol_review_cells_grid_issue",
        "image_symbol_review_cells",
        ["review_item_id"],
        postgresql_where=sa.text("has_grid_issue"),
    )
    op.add_column(
        "image_symbol_review_events",
        sa.Column(
            "previous_has_grid_issue",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "image_symbol_review_events",
        sa.Column(
            "has_grid_issue",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute(
        "UPDATE image_symbol_review_events SET "
        "previous_has_grid_issue = (previous_quality_issue = 'grid_issue'), "
        "has_grid_issue = (quality_issue = 'grid_issue')"
    )


def _restore_candidate_tokens() -> None:
    for column_name in _TOKEN_COLUMNS:
        op.add_column(
            "image_board_search_candidates",
            sa.Column(
                column_name,
                postgresql.ARRAY(sa.String(length=80)),
                nullable=False,
                server_default=sa.text("ARRAY[]::varchar[]"),
            ),
        )
    op.execute(_primary_token_rebuild_sql())
    for rank in range(1, 5):
        op.execute(_alternative_token_rebuild_sql(rank))
    for column_name in _TOKEN_COLUMNS:
        op.alter_column(
            "image_board_search_candidates",
            column_name,
            server_default=None,
        )
    for column_name, index_name in zip(
        _TOKEN_COLUMNS,
        _CANDIDATE_TOKEN_INDEXES,
        strict=True,
    ):
        op.create_index(
            index_name,
            "image_board_search_candidates",
            [column_name],
            postgresql_using="gin",
        )


def _restore_legacy_documents() -> None:
    op.create_table(
        "image_board_search_documents",
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("review_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("selection_kind", sa.String(length=20), nullable=False),
        sa.Column("recognized_board_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("board_checksum_sha256", sa.String(length=64), nullable=False),
        *(
            sa.Column(name, postgresql.ARRAY(sa.String(length=80)), nullable=False)
            for name in _TOKEN_COLUMNS
        ),
        sa.Column(
            "known_evidence_positions",
            postgresql.ARRAY(sa.String(length=2)),
            nullable=False,
        ),
        *(
            sa.Column(name, postgresql.ARRAY(sa.SmallInteger()), nullable=False)
            for name in _MOBILE_COLUMNS
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "sequence_number > 0",
            name="ck_image_board_search_documents_sequence_positive",
        ),
        sa.CheckConstraint(
            "selection_kind IN ('canonical', 'pending')",
            name="ck_image_board_search_documents_selection_kind",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'corrected')",
            name="ck_image_board_search_documents_status",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["review_item_id"],
            ["image_board_search_candidates.review_item_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("game_id", "sequence_number"),
        sa.UniqueConstraint(
            "review_item_id",
            name="uq_image_board_search_documents_review_item",
        ),
    )
    op.create_index(
        "ix_image_board_search_documents_game_review",
        "image_board_search_documents",
        ["game_id", "review_item_id"],
    )
    columns = (
        "game_id",
        "sequence_number",
        "review_item_id",
        "recognized_board_id",
        "import_job_id",
        "status",
        "board_checksum_sha256",
        *_TOKEN_COLUMNS,
        "known_evidence_positions",
        *_MOBILE_COLUMNS,
    )
    joined_columns = ", ".join(columns)
    selected_columns = ", ".join(f"c.{name}" for name in columns)
    op.execute(
        "INSERT INTO image_board_search_documents "
        f"({joined_columns}, selection_kind) "
        f"SELECT {selected_columns}, "
        "CASE WHEN canonical.review_item_id = fast.review_item_id "
        "THEN 'canonical' ELSE 'pending' END "
        "FROM image_board_search_fast_documents fast "
        "JOIN image_board_search_candidates c "
        "ON c.review_item_id = fast.review_item_id "
        "LEFT JOIN image_sequence_canonical canonical "
        "ON canonical.game_id = fast.game_id "
        "AND canonical.sequence_number = fast.sequence_number"
    )
    for column_name, index_name in zip(
        _TOKEN_COLUMNS,
        _DOCUMENT_TOKEN_INDEXES,
        strict=True,
    ):
        op.create_index(
            index_name,
            "image_board_search_documents",
            [column_name],
            postgresql_using="gin",
        )


def _primary_token_rebuild_sql() -> str:
    return """
        UPDATE image_board_search_candidates candidate
        SET primary_match_tokens = COALESCE((
          SELECT array_agg((cell.ordinality - 1)::text || ':' || (cell.value #>> '{}')
                           ORDER BY cell.ordinality)
          FROM jsonb_array_elements(candidate.primary_symbol_codes)
               WITH ORDINALITY AS cell(value, ordinality)
          WHERE jsonb_typeof(cell.value) = 'string'
            AND (cell.value #>> '{}') <> '?'
        ), ARRAY[]::varchar[])
    """


def _alternative_token_rebuild_sql(rank: int) -> str:
    column_name = f"alternative_rank_{rank}_match_tokens"
    return f"""
        UPDATE image_board_search_candidates candidate
        SET {column_name} = COALESCE((
          SELECT array_agg((cell.ordinality - 1)::text || ':' || (alternative.value #>> '{{}}')
                           ORDER BY cell.ordinality)
          FROM jsonb_array_elements(candidate.alternative_symbol_codes)
               WITH ORDINALITY AS cell(value, ordinality)
          JOIN LATERAL jsonb_array_elements(cell.value)
               WITH ORDINALITY AS alternative(value, alternative_rank) ON true
          WHERE alternative.alternative_rank = {rank}
            AND jsonb_typeof(alternative.value) = 'string'
            AND (alternative.value #>> '{{}}') <> '?'
        ), ARRAY[]::varchar[])
    """
