"""Partition-aware recognition of unique-constraint violations on game tables.

Game-owned relations live in the partitioned ``game_data_v2`` store.  When an
insert violates a unique key there, PostgreSQL reports ``diag.constraint_name``
as the name of the *partition* index (for example
``gpv2_<game>_<hash>_game_id_import_job_id_idx1``).  The parent index of the
partitioned table carries a frozen generated name (``v2_ix_<hash>`` /
``v2_uq_<hash>``) that never equals the logical name declared by the ORM
(``uq_…``), and the legacy ``public`` copies that used the ORM names no longer
exist.  Matching by name therefore cannot work.

The catalog is the source of truth: the violated index is followed through
``pg_inherits`` to its top-level parent, and the parent's table, key columns and
partial predicate are matched against the unique constraints and unique indexes
the ORM declares for the table.  No partition-name pattern is ever parsed.

Resolution runs a catalog query, so the caller must be in a usable transaction:
wrap the failing write in ``Session.begin_nested()`` (the savepoint is rolled
back when the ``IntegrityError`` leaves the block) and resolve inside the
``except`` clause that follows it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import FromClause, Index, Table, UniqueConstraint, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# Column that the partitioned store adds to every key; the ORM may or may not
# list it, so it is ignored on both sides of the comparison.
_PARTITION_COLUMN = "game_id"

_PARENT_INDEX_SQL = text(
    """
    WITH RECURSIVE ancestry (oid, depth) AS (
        SELECT c.oid, 0
        FROM pg_catalog.pg_class AS c
        JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = :schema_name
          AND c.relname = :index_name
          AND c.relkind IN ('i', 'I')
        UNION ALL
        SELECT inh.inhparent, a.depth + 1
        FROM ancestry AS a
        JOIN pg_catalog.pg_inherits AS inh ON inh.inhrelid = a.oid
    )
    SELECT
        ic.relname::text AS index_name,
        tc.relname::text AS table_name,
        ix.indisunique AS is_unique,
        ARRAY(
            SELECT att.attname::text
            FROM unnest(ix.indkey::int2[]) WITH ORDINALITY AS k(attnum, ord)
            JOIN pg_catalog.pg_attribute AS att
              ON att.attrelid = ix.indrelid AND att.attnum = k.attnum
            ORDER BY k.ord
        )::text[] AS key_columns,
        pg_catalog.pg_get_expr(ix.indpred, ix.indrelid) AS predicate
    FROM ancestry AS an
    JOIN pg_catalog.pg_index AS ix ON ix.indexrelid = an.oid
    JOIN pg_catalog.pg_class AS ic ON ic.oid = an.oid
    JOIN pg_catalog.pg_class AS tc ON tc.oid = ix.indrelid
    ORDER BY an.depth DESC
    LIMIT 1
    """
)


@dataclass(frozen=True, slots=True)
class ParentUniqueIndex:
    """Definition of the top-level parent of a violated (partition) index."""

    index_name: str
    table_name: str
    is_unique: bool
    key_columns: tuple[str, ...]
    predicate: str | None


def violated_index_name(error: IntegrityError) -> tuple[str | None, str | None]:
    """Return ``(schema_name, constraint_name)`` reported by PostgreSQL."""

    diagnostic = getattr(error.orig, "diag", None)
    schema_name = getattr(diagnostic, "schema_name", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    return (
        schema_name if isinstance(schema_name, str) else None,
        constraint_name if isinstance(constraint_name, str) else None,
    )


def fetch_parent_unique_index(
    session: Session, *, schema_name: str, index_name: str
) -> ParentUniqueIndex | None:
    """Follow ``index_name`` to its top-level parent index through the catalog.

    Returns the definition of the index itself when it has no parent, and
    ``None`` when no such index exists.
    """

    row = session.execute(
        _PARENT_INDEX_SQL, {"schema_name": schema_name, "index_name": index_name}
    ).one_or_none()
    if row is None:
        return None
    return ParentUniqueIndex(
        index_name=row.index_name,
        table_name=row.table_name,
        is_unique=bool(row.is_unique),
        key_columns=tuple(row.key_columns),
        predicate=row.predicate,
    )


def declared_unique_names(table: Table) -> dict[str, tuple[tuple[str, ...], str | None]]:
    """Map every named ORM unique key of ``table`` to ``(columns, predicate)``."""

    declared: dict[str, tuple[tuple[str, ...], str | None]] = {}
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint) and constraint.name is not None:
            declared[str(constraint.name)] = (tuple(column.name for column in constraint), None)
    for index in table.indexes:
        if index.unique and index.name is not None and _all_plain_columns(index):
            where = index.dialect_options["postgresql"]["where"]
            declared[str(index.name)] = (
                tuple(column.name for column in index.columns),
                None if where is None else str(where),
            )
    return declared


def _all_plain_columns(index: Index) -> bool:
    return len(index.expressions) == len(index.columns)


def _normalized_predicate(predicate: str | None) -> str | None:
    if predicate is None:
        return None
    return re.sub(r"[\s()]+", "", predicate).lower()


def _without_partition_column(columns: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(column for column in columns if column != _PARTITION_COLUMN)


def match_declared_unique_name(table: Table, parent: ParentUniqueIndex) -> str | None:
    """Return the ORM name of the unique key that ``parent`` implements."""

    if not parent.is_unique or parent.table_name != table.name:
        return None
    wanted_columns = _without_partition_column(parent.key_columns)
    wanted_predicate = _normalized_predicate(parent.predicate)
    matches = [
        name
        for name, (columns, predicate) in declared_unique_names(table).items()
        if _without_partition_column(columns) == wanted_columns
        and _normalized_predicate(predicate) == wanted_predicate
    ]
    return matches[0] if len(matches) == 1 else None


def resolve_unique_constraint_name(
    session: Session, error: IntegrityError, table: FromClause
) -> str | None:
    """Return the logical (ORM) name of the unique key violated on ``table``.

    * A reported name that the ORM declares for ``table`` is returned unchanged
      (the non-partitioned layout).
    * Otherwise the reported index is followed through ``pg_inherits`` to its
      top-level parent and matched structurally against the ORM declarations.
    * When nothing matches, the reported name is returned unchanged so callers
      keep treating the violation as unknown and re-raise it.  ``None`` is
      returned only when PostgreSQL reported no name.
    """

    if not isinstance(table, Table):
        raise TypeError("resolve_unique_constraint_name requires a mapped Table")
    schema_name, reported = violated_index_name(error)
    if reported is None:
        return None
    if reported in declared_unique_names(table) or schema_name is None:
        return reported
    parent = fetch_parent_unique_index(session, schema_name=schema_name, index_name=reported)
    if parent is None:
        return reported
    return match_declared_unique_name(table, parent) or reported
