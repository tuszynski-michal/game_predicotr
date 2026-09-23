"""Index-only support for the D-437 board-import-coverage read path.

Adds two read indexes used by TASK-0629's coverage repository:

- ``(game_id, sequence_number, status)`` on ``image_review_items`` — the
  existing partial unique index only covers ``status = 'pending'``; the
  coverage sweep needs every status (pending/accepted/corrected/rejected/
  superseded) to compute "added" islands and the ``rejected`` reason.
- a partial index on ``recognized_boards(id) WHERE completeness_status =
  'pending_partial'`` — the coverage sweep joins ``image_review_items`` to
  this table only to test ``pending_partial`` boards.

``public.image_review_items`` and ``public.recognized_boards`` are plain
tables, so their indexes are built ``CONCURRENTLY`` in an autocommit block
(mirroring 0104): a retry only repairs an invalid index with our exact
definition. Their ``game_data_v2`` counterparts are partitioned tables —
PostgreSQL does not support ``CONCURRENTLY`` on a partitioned parent — so
those two mirror 0108's plain, transactional ``CREATE INDEX``.

No domain rows change.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0122_board_import_coverage_indexes"
down_revision: str | Sequence[str] | None = "0121_partial_visibility_quality_issue"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (index_name, table, column_list, where_clause | None, canonical_where | None)
# — always public.*. canonical_where is the predicate exactly as
# pg_get_indexdef renders it (casts added), used to recognise our own index.
_CONCURRENT_INDEXES: tuple[tuple[str, str, str, str | None, str | None], ...] = (
    (
        "ix_image_review_items_game_sequence_status",
        "image_review_items",
        "game_id, sequence_number, status",
        None,
        None,
    ),
    (
        "ix_recognized_boards_pending_partial",
        "recognized_boards",
        "id",
        "completeness_status = 'pending_partial'",
        "((completeness_status)::text = 'pending_partial'::text)",
    ),
)


def _expected_def(name: str, table: str, columns: str, canonical_where: str | None) -> str:
    clause = f" WHERE {canonical_where}" if canonical_where else ""
    return f"CREATE INDEX {name} ON public.{table} USING btree ({columns}){clause}"


def _upgrade_concurrent_public_indexes() -> None:
    if op.get_context().as_sql:
        raise RuntimeError("0122 requires online catalog validation; no offline SQL")
    connection = op.get_bind()
    # Alembic commits the preceding DDL before a concurrent index operation.
    with op.get_context().autocommit_block():
        previous = connection.execute(
            sa.text("SELECT current_setting('statement_timeout'),current_setting('lock_timeout')")
        ).one()
        try:
            connection.execute(sa.text("SET statement_timeout='120s'"))
            connection.execute(sa.text("SET lock_timeout='2s'"))
            for name, table, columns, where, canonical_where in _CONCURRENT_INDEXES:
                expected = _expected_def(name, table, columns, canonical_where)
                existing = connection.execute(
                    sa.text(
                        "SELECT pg_get_indexdef(c.oid),i.indisvalid,i.indisready "
                        "FROM pg_class c LEFT JOIN pg_index i ON i.indexrelid=c.oid "
                        "JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE n.nspname='public' AND c.relname=:name"
                    ),
                    {"name": name},
                ).one_or_none()
                if existing:
                    if existing[0] != expected:
                        raise RuntimeError(f"BOARD_IMPORT_COVERAGE_INDEX_NAME_CONFLICT: {name}")
                    if existing[1] and existing[2]:
                        continue
                    connection.execute(sa.text(f"DROP INDEX CONCURRENTLY public.{name}"))
                where_clause = f" WHERE {where}" if where else ""
                connection.execute(
                    sa.text(
                        f"CREATE INDEX CONCURRENTLY {name} ON public.{table} "
                        f"({columns}){where_clause}"
                    )
                )
        finally:
            connection.execute(
                sa.text("SELECT set_config('statement_timeout',:value,false)"),
                {"value": previous[0]},
            )
            connection.execute(
                sa.text("SELECT set_config('lock_timeout',:value,false)"), {"value": previous[1]}
            )


def _downgrade_concurrent_public_indexes() -> None:
    connection = op.get_bind()
    with op.get_context().autocommit_block():
        previous = connection.execute(
            sa.text("SELECT current_setting('statement_timeout'),current_setting('lock_timeout')")
        ).one()
        try:
            connection.execute(sa.text("SET statement_timeout='120s'"))
            connection.execute(sa.text("SET lock_timeout='2s'"))
            for name, table, columns, _where, canonical_where in reversed(_CONCURRENT_INDEXES):
                expected = _expected_def(name, table, columns, canonical_where)
                existing = connection.execute(
                    sa.text(
                        "SELECT pg_get_indexdef(c.oid) FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE n.nspname='public' AND c.relname=:name"
                    ),
                    {"name": name},
                ).one_or_none()
                if existing and existing[0] != expected:
                    raise RuntimeError(f"BOARD_IMPORT_COVERAGE_INDEX_NAME_CONFLICT: {name}")
                connection.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS public.{name}"))
        finally:
            connection.execute(
                sa.text("SELECT set_config('statement_timeout',:v,false)"), {"v": previous[0]}
            )
            connection.execute(
                sa.text("SELECT set_config('lock_timeout',:v,false)"), {"v": previous[1]}
            )


def upgrade() -> None:
    # Public indexes first: they commit on their own and are retry-safe. The v2
    # DDL then runs in the transaction that stamps 0122, so a failure there
    # rolls it back instead of leaving an index that breaks the next attempt.
    _upgrade_concurrent_public_indexes()
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.execute(
        "CREATE INDEX v2_ix_image_review_items_game_sequence_status "
        "ON game_data_v2.image_review_items (game_id, sequence_number, status)"
    )
    op.execute(
        "CREATE INDEX v2_ix_recognized_boards_pending_partial "
        "ON game_data_v2.recognized_boards (game_id, id) "
        "WHERE completeness_status = 'pending_partial'"
    )


def downgrade() -> None:
    _downgrade_concurrent_public_indexes()
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.execute("DROP INDEX game_data_v2.v2_ix_recognized_boards_pending_partial")
    op.execute("DROP INDEX game_data_v2.v2_ix_image_review_items_game_sequence_status")
