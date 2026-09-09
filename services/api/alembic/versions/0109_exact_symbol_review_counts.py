"""Add resumable exact counts for the V2 symbol review projection."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0109_exact_symbol_review_counts"
down_revision: str | Sequence[str] | None = "0108_indexed_symbol_review_list"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    for schema in ("public", "game_data_v2"):
        for column in (
            sa.Column(
                "count_projection_status",
                sa.String(length=20),
                nullable=False,
                server_default="unavailable",
            ),
            sa.Column(
                "count_projection",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "count_projection_revision",
                sa.BigInteger(),
                nullable=False,
                server_default="0",
            ),
            sa.Column("count_rebuild_cursor", sa.Uuid(), nullable=True),
            sa.Column(
                "count_rebuild_accumulator",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("count_projection_failure_message", sa.String(length=500), nullable=True),
        ):
            op.add_column("image_symbol_review_states", column, schema=schema)
        prefix = "v2_" if schema == "game_data_v2" else ""
        op.create_check_constraint(
            f"ck_{prefix}image_symbol_review_states_count_projection_status",
            "image_symbol_review_states",
            "count_projection_status IN ('unavailable', 'rebuilding', 'ready', 'failed')",
            schema=schema,
        )
        op.create_check_constraint(
            f"ck_{prefix}image_symbol_review_states_count_projection_revision",
            "image_symbol_review_states",
            "count_projection_revision >= 0",
            schema=schema,
        )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    for schema in ("game_data_v2", "public"):
        prefix = "v2_" if schema == "game_data_v2" else ""
        op.drop_constraint(
            f"ck_{prefix}image_symbol_review_states_count_projection_revision",
            "image_symbol_review_states",
            schema=schema,
            type_="check",
        )
        op.drop_constraint(
            f"ck_{prefix}image_symbol_review_states_count_projection_status",
            "image_symbol_review_states",
            schema=schema,
            type_="check",
        )
        for column in (
            "count_projection_failure_message",
            "count_rebuild_accumulator",
            "count_rebuild_cursor",
            "count_projection_revision",
            "count_projection",
            "count_projection_status",
        ):
            op.drop_column("image_symbol_review_states", column, schema=schema)
