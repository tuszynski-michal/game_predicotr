"""Index the V2 symbol-review import-folder filter."""

from collections.abc import Sequence

from alembic import op

revision: str = "0146_symbol_review_import_filter_index"
down_revision: str | Sequence[str] | None = "0145_neural_page_geometry_binding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "v2_ix_symbol_review_list_import"


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.execute(
        f"CREATE INDEX {INDEX} ON game_data_v2.image_symbol_review_cells "
        "(game_id, import_job_id, sequence_number, cell_index, id) "
        "WHERE source_available OR source_visibility = 'outside'"
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.execute(f"DROP INDEX game_data_v2.{INDEX}")
