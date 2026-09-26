"""Read-only, bounded preflight for removing legacy game-owned public tables.

The command writes only its local JSON report.  Its database transaction is
``REPEATABLE READ READ ONLY`` before the first catalog query and it never
executes DDL or DML.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.game_data_v2_manifest_v1 import GAME_TABLES, VERSION
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

AUDIT_VERSION = "legacy-public-game-store-audit-v1"
_STATEMENT_TIMEOUT_MS = 15_000
_LOCK_TIMEOUT_MS = 5_000
_TRANSACTION_TIMEOUT_MS = 30_000
_ACTIVE_MIGRATION_STATUSES = ("prepared", "copying", "validating", "ready")
_ACTIVE_JOB_STATUSES = ("created", "processing")


class AuditError(RuntimeError):
    """The inventory could not produce a trustworthy report."""


def _json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def _row(value: object) -> dict[str, object]:
    plain = _plain(value)
    if not isinstance(plain, Mapping):
        raise AuditError("LEGACY_PUBLIC_STORE_CATALOG_ROW_INVALID")
    return {str(key): item for key, item in plain.items()}


def _quoted_table(table_name: str) -> str:
    if table_name not in GAME_TABLES:
        raise AuditError(f"LEGACY_PUBLIC_STORE_UNKNOWN_TABLE: {table_name}")
    return f'public."{table_name}"'


@contextmanager
def _read_transaction(engine: Engine) -> Iterator[Connection]:
    with engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        connection.execute(
            text("SELECT set_config('statement_timeout', :timeout, true)"),
            {"timeout": str(_STATEMENT_TIMEOUT_MS)},
        )
        connection.execute(
            text("SELECT set_config('lock_timeout', :timeout, true)"),
            {"timeout": str(_LOCK_TIMEOUT_MS)},
        )
        connection.execute(
            text("SELECT set_config('idle_in_transaction_session_timeout', :timeout, true)"),
            {"timeout": str(_TRANSACTION_TIMEOUT_MS)},
        )
        connection.info["legacy_public_store_audit_deadline"] = (
            time.monotonic() + _TRANSACTION_TIMEOUT_MS / 1000
        )
        try:
            yield connection
        finally:
            connection.rollback()


def _remaining_ms(connection: Connection) -> int:
    deadline = connection.info.get("legacy_public_store_audit_deadline")
    if not isinstance(deadline, float):
        raise AuditError("LEGACY_PUBLIC_STORE_AUDIT_TRANSACTION_UNCONFIGURED")
    remaining = int((deadline - time.monotonic()) * 1000)
    if remaining <= 0:
        raise AuditError("LEGACY_PUBLIC_STORE_AUDIT_TIMEOUT")
    return remaining


def _bounded(
    connection: Connection, statement: str, params: Mapping[str, object] | None = None
) -> Any:
    remaining = _remaining_ms(connection)
    connection.execute(
        text("SELECT set_config('statement_timeout', :timeout, true)"),
        {"timeout": str(min(_STATEMENT_TIMEOUT_MS, remaining))},
    )
    return connection.execute(text(statement), params or {})


def _catalog(connection: Connection) -> list[dict[str, object]]:
    rows = _bounded(
        connection,
        """
        SELECT c.relname AS table_name, c.oid::text AS oid, c.relkind,
               c.relrowsecurity, c.relforcerowsecurity,
               pg_total_relation_size(c.oid)::bigint AS total_bytes
        FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relname = ANY(CAST(:tables AS text[]))
        ORDER BY c.relname
        """,
        {"tables": list(GAME_TABLES)},
    ).mappings()
    found = {str(row["table_name"]): _row(row) for row in rows}
    unknown_relation = {
        "oid": None,
        "relkind": None,
        "relrowsecurity": None,
        "relforcerowsecurity": None,
        "total_bytes": None,
    }
    return [
        {
            "tableName": table_name,
            "exists": table_name in found,
            **found.get(table_name, unknown_relation),
        }
        for table_name in GAME_TABLES
    ]


def _table_counts(
    connection: Connection, catalog: Sequence[Mapping[str, object]]
) -> list[dict[str, object]]:
    counts: list[dict[str, object]] = []
    for relation in catalog:
        name = str(relation["tableName"])
        if not relation["exists"] or relation["relkind"] != "r":
            counts.append({"tableName": name, "rowCount": None})
            continue
        row_count = _bounded(
            connection, f"SELECT count(*)::bigint FROM {_quoted_table(name)}"
        ).scalar_one()
        counts.append({"tableName": name, "rowCount": int(row_count)})
    return counts


def _foreign_key_dependencies(connection: Connection) -> list[dict[str, object]]:
    rows = _bounded(
        connection,
        """
        SELECT target.relname AS target_table, source_namespace.nspname AS source_schema,
               source.relname AS source_table, constraint_row.conname AS constraint_name
        FROM pg_constraint AS constraint_row
        JOIN pg_class AS target ON target.oid = constraint_row.confrelid
        JOIN pg_namespace AS target_namespace ON target_namespace.oid = target.relnamespace
        JOIN pg_class AS source ON source.oid = constraint_row.conrelid
        JOIN pg_namespace AS source_namespace ON source_namespace.oid = source.relnamespace
        WHERE constraint_row.contype = 'f'
          AND target_namespace.nspname = 'public'
          AND target.relname = ANY(CAST(:tables AS text[]))
          AND (source_namespace.nspname <> 'public'
               OR NOT (source.relname = ANY(CAST(:tables AS text[]))))
        ORDER BY target.relname, source_namespace.nspname, source.relname, constraint_row.conname
        """,
        {"tables": list(GAME_TABLES)},
    ).mappings()
    return [_row(row) for row in rows]


def _relation_dependencies(connection: Connection) -> list[dict[str, object]]:
    rows = _bounded(
        connection,
        """
        SELECT target.relname AS target_table, dependent_namespace.nspname AS dependent_schema,
               dependent.relname AS dependent_relation, dependent.relkind AS dependent_relkind
        FROM pg_depend AS dependency
        JOIN pg_class AS target ON target.oid = dependency.refobjid
        JOIN pg_namespace AS target_namespace ON target_namespace.oid = target.relnamespace
        JOIN pg_class AS dependent ON dependent.oid = dependency.objid
        JOIN pg_namespace AS dependent_namespace ON dependent_namespace.oid = dependent.relnamespace
        WHERE dependency.classid = 'pg_class'::regclass
          AND dependency.refclassid = 'pg_class'::regclass
          AND target_namespace.nspname = 'public'
          AND target.relname = ANY(CAST(:tables AS text[]))
          AND dependent.relkind IN ('r', 'p', 'v', 'm', 'f')
          AND (dependent_namespace.nspname <> 'public'
               OR NOT (dependent.relname = ANY(CAST(:tables AS text[]))))
        UNION
        SELECT target.relname AS target_table, dependent_namespace.nspname AS dependent_schema,
               dependent.relname AS dependent_relation, dependent.relkind AS dependent_relkind
        FROM pg_depend AS dependency
        JOIN pg_class AS target ON target.oid = dependency.refobjid
        JOIN pg_namespace AS target_namespace ON target_namespace.oid = target.relnamespace
        JOIN pg_rewrite AS rewrite_rule ON rewrite_rule.oid = dependency.objid
        JOIN pg_class AS dependent ON dependent.oid = rewrite_rule.ev_class
        JOIN pg_namespace AS dependent_namespace ON dependent_namespace.oid = dependent.relnamespace
        WHERE dependency.classid = 'pg_rewrite'::regclass
          AND dependency.refclassid = 'pg_class'::regclass
          AND target_namespace.nspname = 'public'
          AND target.relname = ANY(CAST(:tables AS text[]))
          AND dependent.relkind IN ('v', 'm')
          AND (dependent_namespace.nspname <> 'public'
               OR NOT (dependent.relname = ANY(CAST(:tables AS text[]))))
        ORDER BY target_table, dependent_schema, dependent_relation
        """,
        {"tables": list(GAME_TABLES)},
    ).mappings()
    return [_row(row) for row in rows]


def _trigger_and_policy_summary(connection: Connection) -> dict[str, list[dict[str, object]]]:
    triggers = _bounded(
        connection,
        """
        SELECT relation.relname AS table_name, trigger_row.tgname AS trigger_name
        FROM pg_trigger AS trigger_row
        JOIN pg_class AS relation ON relation.oid = trigger_row.tgrelid
        JOIN pg_namespace AS namespace_row ON namespace_row.oid = relation.relnamespace
        WHERE namespace_row.nspname = 'public'
          AND relation.relname = ANY(CAST(:tables AS text[]))
          AND NOT trigger_row.tgisinternal
        ORDER BY relation.relname, trigger_row.tgname
        """,
        {"tables": list(GAME_TABLES)},
    ).mappings()
    policies = _bounded(
        connection,
        """
        SELECT relation.relname AS table_name, policy_row.polname AS policy_name
        FROM pg_policy AS policy_row
        JOIN pg_class AS relation ON relation.oid = policy_row.polrelid
        JOIN pg_namespace AS namespace_row ON namespace_row.oid = relation.relnamespace
        WHERE namespace_row.nspname = 'public'
          AND relation.relname = ANY(CAST(:tables AS text[]))
        ORDER BY relation.relname, policy_row.polname
        """,
        {"tables": list(GAME_TABLES)},
    ).mappings()
    return {
        "triggers": [_row(row) for row in triggers],
        "policies": [_row(row) for row in policies],
    }


def _storage_state(connection: Connection) -> dict[str, object]:
    locations = _bounded(
        connection,
        """
        SELECT game_id::text AS game_id, store_schema, generation,
               manifest_version, status, revision
        FROM public.game_storage_locations ORDER BY game_id
        """,
    ).mappings()
    migrations = _bounded(
        connection,
        """
        SELECT id::text AS id, game_id::text AS game_id, source_schema, target_schema,
               source_generation, target_generation, manifest_version, status, revision
        FROM public.game_storage_migrations ORDER BY game_id, id
        """,
    ).mappings()
    jobs = _bounded(
        connection,
        """
        SELECT status, count(*)::bigint AS count
        FROM public.jobs
        WHERE status::text = ANY(CAST(:statuses AS text[]))
        GROUP BY status ORDER BY status
        """,
        {"statuses": list(_ACTIVE_JOB_STATUSES)},
    ).mappings()
    return {
        "locations": [_row(row) for row in locations],
        "migrations": [_row(row) for row in migrations],
        "activeJobs": [_row(row) for row in jobs],
    }


def _locks(connection: Connection) -> list[dict[str, object]]:
    rows = _bounded(
        connection,
        """
        SELECT relation.relname AS table_name, lock_row.mode, count(*)::bigint AS count
        FROM pg_locks AS lock_row
        JOIN pg_class AS relation ON relation.oid = lock_row.relation
        JOIN pg_namespace AS namespace_row ON namespace_row.oid = relation.relnamespace
        WHERE namespace_row.nspname = 'public'
          AND relation.relname = ANY(CAST(:tables AS text[]))
          AND lock_row.granted
          AND lock_row.pid <> pg_backend_pid()
        GROUP BY relation.relname, lock_row.mode
        ORDER BY relation.relname, lock_row.mode
        """,
        {"tables": list(GAME_TABLES)},
    ).mappings()
    return [_row(row) for row in rows]


def _database_state(connection: Connection) -> dict[str, object]:
    row = (
        _bounded(
            connection,
            """
        SELECT current_database() AS database_name,
               current_setting('server_version_num') AS server_version_num,
               current_setting('server_version') AS server_version,
               current_setting('transaction_read_only') AS transaction_read_only,
               (SELECT version_num FROM public.alembic_version LIMIT 1) AS alembic_revision
        """,
        )
        .mappings()
        .one()
    )
    return _row(row)


def _blockers(
    catalog: Sequence[Mapping[str, object]],
    counts: Sequence[Mapping[str, object]],
    external_fks: Sequence[Mapping[str, object]],
    external_relations: Sequence[Mapping[str, object]],
    storage: Mapping[str, object],
    locks: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    blockers: list[dict[str, object]] = []
    for relation in catalog:
        if not relation["exists"]:
            blockers.append(
                {"code": "LEGACY_PUBLIC_STORE_TABLE_MISSING", "table": relation["tableName"]}
            )
        elif relation["relkind"] != "r":
            blockers.append(
                {
                    "code": "LEGACY_PUBLIC_STORE_RELATION_KIND_INVALID",
                    "table": relation["tableName"],
                    "relkind": relation["relkind"],
                }
            )
    for count in counts:
        if count["rowCount"] not in (None, 0):
            blockers.append(
                {
                    "code": "LEGACY_PUBLIC_STORE_TABLE_NOT_EMPTY",
                    "table": count["tableName"],
                    "rowCount": count["rowCount"],
                }
            )
    for dependency in external_fks:
        blockers.append({"code": "LEGACY_PUBLIC_STORE_EXTERNAL_FK", **dict(dependency)})
    for dependency in external_relations:
        blockers.append(
            {"code": "LEGACY_PUBLIC_STORE_EXTERNAL_RELATION_DEPENDENCY", **dict(dependency)}
        )
    locations = storage["locations"]
    if not isinstance(locations, Sequence):
        raise AuditError("LEGACY_PUBLIC_STORE_LOCATION_REPORT_INVALID")
    for location in locations:
        if not isinstance(location, Mapping):
            raise AuditError("LEGACY_PUBLIC_STORE_LOCATION_REPORT_INVALID")
        if not (
            location.get("store_schema") == "game_data_v2"
            and int(str(location.get("generation"))) >= 2
            and location.get("manifest_version") == VERSION
            and location.get("status") == "active"
        ):
            blockers.append(
                {"code": "LEGACY_PUBLIC_STORE_LOCATION_NOT_ACTIVE_V2", **dict(location)}
            )
    migrations = storage["migrations"]
    if not isinstance(migrations, Sequence):
        raise AuditError("LEGACY_PUBLIC_STORE_MIGRATION_REPORT_INVALID")
    for migration in migrations:
        if isinstance(migration, Mapping) and migration.get("status") in _ACTIVE_MIGRATION_STATUSES:
            blockers.append({"code": "LEGACY_PUBLIC_STORE_ACTIVE_MIGRATION", **dict(migration)})
    active_jobs = storage["activeJobs"]
    if not isinstance(active_jobs, Sequence):
        raise AuditError("LEGACY_PUBLIC_STORE_JOB_REPORT_INVALID")
    for job in active_jobs:
        blockers.append({"code": "LEGACY_PUBLIC_STORE_ACTIVE_JOB", **dict(job)})
    for lock in locks:
        blockers.append({"code": "LEGACY_PUBLIC_STORE_EXTERNAL_LOCK", **dict(lock)})
    return blockers


def audit(engine: Engine) -> dict[str, object]:
    """Collect one bounded, transaction-consistent preflight report."""

    if len(GAME_TABLES) != 65:
        raise AuditError("LEGACY_PUBLIC_STORE_MANIFEST_COUNT_INVALID")
    with _read_transaction(engine) as connection:
        database = _database_state(connection)
        catalog = _catalog(connection)
        counts = _table_counts(connection, catalog)
        external_fks = _foreign_key_dependencies(connection)
        external_relations = _relation_dependencies(connection)
        metadata = _trigger_and_policy_summary(connection)
        storage = _storage_state(connection)
        locks = _locks(connection)
        blockers = _blockers(catalog, counts, external_fks, external_relations, storage, locks)
    return {
        "auditVersion": AUDIT_VERSION,
        "auditedAt": datetime.now(UTC).isoformat(),
        "readOnly": True,
        "manifestVersion": VERSION,
        "manifestTableCount": len(GAME_TABLES),
        "database": database,
        "legacyRelations": catalog,
        "rowCounts": counts,
        "externalForeignKeys": external_fks,
        "externalRelationDependencies": external_relations,
        "triggers": metadata["triggers"],
        "policies": metadata["policies"],
        "storage": storage,
        "externalLocks": locks,
        "status": "ready" if not blockers else "blocked",
        "blockers": blockers,
    }


def _write_report(path: Path, report: Mapping[str, object]) -> str:
    content = _json(report) + b"\n"
    digest = hashlib.sha256(content).hexdigest()
    destination = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "wb", dir=destination.parent, prefix=f".{destination.name}.", delete=False
    ) as tmp:
        temporary = Path(tmp.name)
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
    try:
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return digest


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    settings = ApiSettings.from_environment()
    engine = create_engine(
        settings.database_url,
        connect_args={
            "connect_timeout": 5,
            "options": (
                f"-c statement_timeout={_STATEMENT_TIMEOUT_MS} "
                f"-c lock_timeout={_LOCK_TIMEOUT_MS} -c default_transaction_read_only=on"
            ),
        },
    )
    try:
        report = audit(engine)
        digest = _write_report(args.report, report)
    except (AuditError, OSError, SQLAlchemyError, ValueError) as error:
        print(json.dumps({"code": "LEGACY_PUBLIC_STORE_AUDIT_FAILED", "message": str(error)}))
        return 2
    finally:
        engine.dispose()
    print(json.dumps({"status": report["status"], "reportSha256": digest}, sort_keys=True))
    return 0 if report["status"] == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
