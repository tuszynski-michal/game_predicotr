"""Bounded, independently committed legacy deletion. No physical file deletion."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.exc import DBAPIError

from game_predictor_api.storage.game_deletion_archive import verify_database_archive
from game_predictor_api.storage.game_deletion_policy_v1 import (
    CONFIRMATION,
    DIRECT,
    INDIRECT,
    LEGACY_ID,
    LOCK_KEY,
    MAX_BATCH_BYTES,
    MAX_BATCH_ROWS,
    OWNED,
    POLICY,
    PRESERVED,
    PROTECTED_ID,
    SELF_LINKS,
    SPECIAL,
    DeletionError,
    ForeignKey,
    deletion_order,
    digest,
    owner_chain,
    owner_sql,
    policy_digest,
    quote,
)


@dataclass(frozen=True)
class Table:
    name: str
    columns: tuple[str, ...]
    primary_key: tuple[str, ...]


@dataclass(frozen=True)
class Schema:
    tables: Mapping[str, Table]
    foreign_keys: tuple[ForeignKey, ...]
    sha256: str
    missing_indexes: tuple[str, ...]
    catalog_sha256: str


def catalog_digest(connection: Connection) -> str:
    """Cheap single-query fence against DDL between independently committed batches."""
    rows = connection.execute(
        text("""
SELECT 'constraint',c.oid::text,c.xmin::text,pg_get_constraintdef(c.oid)
FROM pg_constraint c
UNION ALL
SELECT 'attribute',a.attrelid::text||':'||a.attnum::text,a.xmin::text,a.attname::text
FROM pg_attribute a JOIN pg_class t ON t.oid=a.attrelid
JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='public'
UNION ALL
SELECT 'trigger',t.oid::text,t.xmin::text,pg_get_triggerdef(t.oid)
FROM pg_trigger t WHERE NOT t.tgisinternal
UNION ALL
SELECT 'function',p.oid::text,p.xmin::text,p.prosrc
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public'
UNION ALL
SELECT 'index',i.indexrelid::text,i.xmin::text,pg_get_indexdef(i.indexrelid)
FROM pg_index i
ORDER BY 1,2
""")
    ).all()
    return digest([tuple(row) for row in rows])


def transaction_limits(connection: Connection) -> None:
    connection.execute(text("SET LOCAL lock_timeout = '2s'"))
    connection.execute(text("SET LOCAL statement_timeout = '15s'"))
    connection.execute(text("SET LOCAL idle_in_transaction_session_timeout = '20s'"))
    connection.execute(text("SET LOCAL transaction_timeout = '30s'"))


def load_schema(connection: Connection) -> Schema:
    """Catalog only: no application row counts, paths or ownership markers."""
    inspector = inspect(connection)
    foreign_schema = connection.execute(
        text("""
SELECT c.conname FROM pg_constraint c
JOIN pg_class child ON child.oid=c.conrelid JOIN pg_namespace cn ON cn.oid=child.relnamespace
JOIN pg_class parent ON parent.oid=c.confrelid JOIN pg_namespace pn ON pn.oid=parent.relnamespace
WHERE c.contype='f' AND ((cn.nspname='public' AND pn.nspname<>'public')
OR (pn.nspname='public' AND cn.nspname<>'public')) LIMIT 1
""")
    ).scalar()
    if foreign_schema:
        raise DeletionError("GAME_DELETE_FOREIGN_SCHEMA", str(foreign_schema))
    names = set(inspector.get_table_names(schema="public"))
    if names - OWNED - PRESERVED or OWNED - names:
        raise DeletionError(
            "GAME_DELETE_SCHEMA_DRIFT",
            str({"unknown": sorted(names - OWNED - PRESERVED), "missing": sorted(OWNED - names)}),
        )
    columns = inspector.get_multi_columns(schema="public")
    keys = inspector.get_multi_pk_constraint(schema="public")
    tables = {
        name: Table(
            name,
            tuple(column["name"] for column in columns["public", name]),
            tuple(keys["public", name]["constrained_columns"]),
        )
        for name in sorted(OWNED)
    }
    for table in tables.values():
        if not table.primary_key:
            raise DeletionError("GAME_DELETE_PRIMARY_KEY_MISSING", table.name)
    fks = tuple(
        ForeignKey(
            str(row["name"]),
            name,
            tuple(row["constrained_columns"]),
            str(row["referred_table"]),
            tuple(row["referred_columns"]),
            str(row.get("options", {}).get("ondelete", "NO ACTION")),
        )
        for (_, name), rows in inspector.get_multi_foreign_keys(schema="public").items()
        for row in rows
    )
    index_rows = connection.execute(
        text("""
SELECT t.relname, i.relname, x.indisvalid, x.indisready,
       pg_get_indexdef(x.indexrelid), x.indpred IS NULL AND am.amname='btree',
       ARRAY(SELECT a.attname FROM unnest(x.indkey) WITH ORDINALITY k(attnum,n)
             JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=k.attnum
             WHERE k.n <= x.indnkeyatts ORDER BY k.n)
FROM pg_index x JOIN pg_class t ON t.oid=x.indrelid
JOIN pg_namespace ns ON ns.oid=t.relnamespace JOIN pg_class i ON i.oid=x.indexrelid
JOIN pg_am am ON am.oid=i.relam
WHERE ns.nspname='public' ORDER BY t.relname,i.relname
""")
    ).all()
    usable: dict[str, list[tuple[str, ...]]] = {}
    for name, _, valid, ready, _, whole, fields in index_rows:
        if valid and ready and whole:
            usable.setdefault(name, []).append(tuple(fields))
    needed = {(fk.child, fk.columns) for fk in fks if fk.parent in OWNED}
    needed.update((name, ("game_id",)) for name in DIRECT)
    needed.update((name, (edge[0],)) for name, edge in INDIRECT.items())
    for name, table in tables.items():
        field = "game_id" if name in DIRECT else SPECIAL.get(name)
        if field is None:
            field = INDIRECT[name][0]
        needed.add((name, tuple(dict.fromkeys((field,) + table.primary_key))))
    missing = tuple(
        f"{name}({','.join(fields)})"
        for name, fields in sorted(needed)
        if not any(index[: len(fields)] == fields for index in usable.get(name, []))
    )
    triggers = connection.execute(
        text("""
SELECT c.relname,t.tgname,t.tgenabled,pg_get_triggerdef(t.oid),pg_get_functiondef(t.tgfoid)
FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE NOT t.tgisinternal AND n.nspname='public' ORDER BY c.relname,t.tgname
""")
    ).all()
    for name in OWNED:
        for event in ("insert", "update", "delete"):
            if not any(
                row[0] == name and row[1] == f"a_game_delete_fence_{event}" and row[2] == "O"
                for row in triggers
            ):
                raise DeletionError("GAME_DELETE_FENCE_MISSING", name)
    catalog_sha256 = catalog_digest(connection)
    descriptor = {
        "tables": [(t.name, t.columns, t.primary_key) for t in tables.values()],
        "foreignKeys": sorted(
            (f.name, f.child, f.columns, f.parent, f.parent_columns, f.action) for f in fks
        ),
        "indexes": [tuple(row) for row in index_rows],
        "triggers": [tuple(row) for row in triggers],
        "policy": policy_digest(),
        "catalogSha256": catalog_sha256,
    }
    return Schema(tables, fks, digest(descriptor), missing, catalog_sha256)


def validate_identity(connection: Connection, *, allow_deleted: bool = False) -> None:
    rows = connection.execute(
        text("SELECT id::text,code,name FROM public.games WHERE id IN (:game,:protected)"),
        {"game": LEGACY_ID, "protected": PROTECTED_ID},
    ).all()
    actual = {row[0]: (row[1], row[2]) for row in rows}
    if actual.get(PROTECTED_ID) != ("new-siedem", "777"):
        raise DeletionError("GAME_DELETE_PROTECTED_IDENTITY", "Protected game mismatch")
    if actual.get(LEGACY_ID) != ("777", "777 v0.1") and not (
        allow_deleted and LEGACY_ID not in actual
    ):
        raise DeletionError("GAME_DELETE_TARGET_IDENTITY", "Legacy game mismatch")


def _join(left: str, right: str, columns: tuple[str, ...], other: tuple[str, ...]) -> str:
    return " AND ".join(
        f"{left}.{quote(a)}={right}.{quote(b)}" for a, b in zip(columns, other, strict=True)
    )


def _references(value: Any, prefix: str = "") -> list[dict[str, str]]:
    """Journal references, never images or a copy of the removed heavy payload."""
    result: list[dict[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            location = f"{prefix}.{key}" if prefix else key
            normalized = key.lower().replace("_", "")
            if isinstance(child, str) and (
                "path" in normalized
                or "checksum" in normalized
                or normalized in {"fileexecutionkey", "uploadid", "browserselectionid"}
            ):
                result.append({"field": location, "value": child})
            elif isinstance(child, dict | list):
                result.extend(_references(child, location))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            if isinstance(child, str) and "path" in prefix.lower():
                result.append({"field": f"{prefix}[{index}]", "value": child})
            else:
                result.extend(_references(child, f"{prefix}[{index}]"))
    return result


def select_owned_batch(
    connection: Connection,
    schema: Schema,
    table_name: str,
    cursor: list[dict[str, Any]],
    limit: int,
    unlink_column: str | None = None,
) -> tuple[list[Mapping[str, Any]], bool]:
    """Walk indexed owner prefixes; persist progress even through empty parents.

    At most 64 owner/leaf queries per transaction. No global UUID scan and no
    giant sort of all indirect descendants of a game.
    """
    chain = owner_chain(table_name)
    queries = 0
    selected_rows: list[Mapping[str, Any]] = []
    total_bytes = 0

    def visit(depth: int, parent: Mapping[str, Any] | None) -> tuple[list[Mapping[str, Any]], bool]:
        nonlocal queries
        while queries < 64:
            while len(cursor) <= depth:
                cursor.append({})
            entry = cursor[depth]
            table = schema.tables[chain[depth]]
            leaf = depth == len(chain) - 1
            current = entry.get("current")
            if leaf or current is None:
                group_parent = depth == len(chain) - 2
                params: dict[str, Any] = {"limit": limit if leaf or group_parent else 1}
                order = table.primary_key
                if depth == 0:
                    field = "game_id" if table.name in DIRECT else SPECIAL[table.name]
                    condition = f"r.{quote(field)}=CAST(:owner AS uuid)"
                    params["owner"] = LEGACY_ID
                else:
                    field, _, parent_field = INDIRECT[table.name]
                    assert parent is not None
                    if leaf and "parents" in parent:
                        placeholders = []
                        for n, item in enumerate(parent["parents"]):
                            params[f"owner_{n}"] = item[parent_field]
                            placeholders.append(f":owner_{n}")
                        condition = f"r.{quote(field)} IN ({','.join(placeholders)})"
                        order = tuple(dict.fromkeys((field,) + table.primary_key))
                    else:
                        condition = f"r.{quote(field)}=:owner"
                        params["owner"] = parent[parent_field]
                after = entry.get("after")
                if after:
                    conditions = []
                    for n, field in enumerate(order):
                        params[f"after_{n}"] = after[field]
                        conditions.append(f":after_{n}")
                    left = ",".join("r." + quote(k) for k in order)
                    condition += f" AND ({left}) > ({','.join(conditions)})"
                if leaf and unlink_column:
                    condition += f" AND r.{quote(unlink_column)} IS NOT NULL"
                selected = ",".join("r." + quote(k) for k in order)
                size = ", octet_length(to_jsonb(r)::text) AS row_bytes" if leaf else ""
                queries += 1
                rows: list[Mapping[str, Any]] = [
                    dict(row)
                    for row in (
                        connection.execute(
                            text(
                                f"SELECT {selected}{size} FROM public.{quote(table.name)} r "
                                f"WHERE {condition} ORDER BY {selected} "
                                "LIMIT :limit FOR UPDATE OF r"
                            ),
                            params,
                        )
                        .mappings()
                        .all()
                    )
                ]
                if not rows:
                    return [], True
                if leaf:
                    return rows, False
                current = (
                    {"parents": [dict(row) for row in rows]} if group_parent else dict(rows[0])
                )
                entry["current"] = current
            rows, exhausted = visit(depth + 1, current)
            if rows or not exhausted:
                return rows, False
            completed = entry.pop("current")
            entry["after"] = completed["parents"][-1] if "parents" in completed else completed
            del cursor[depth + 1 :]
        return [], False

    while queries < 64 and len(selected_rows) < limit:
        rows, exhausted = visit(0, None)
        if not rows:
            return selected_rows, exhausted
        for row in rows:
            size = int(row["row_bytes"])
            if size > MAX_BATCH_BYTES:
                raise DeletionError("GAME_DELETE_ROW_TOO_LARGE", table_name)
            if total_bytes + size > MAX_BATCH_BYTES or len(selected_rows) >= limit:
                return selected_rows, False
            selected_rows.append(row)
            total_bytes += size
            cursor[-1]["after"] = {k: v for k, v in row.items() if k != "row_bytes"}
    return selected_rows, False


class GameDeletionRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def preview(self, archive: Mapping[str, Any]) -> dict[str, Any]:
        with self.engine.begin() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            transaction_limits(connection)
            schema = load_schema(connection)
            receipt = (
                connection.execute(
                    text("SELECT * FROM public.game_deletion_operations WHERE game_id=:game"),
                    {"game": LEGACY_ID},
                )
                .mappings()
                .one_or_none()
            )
            validate_identity(
                connection, allow_deleted=bool(receipt and receipt["status"] == "database_done")
            )
            if receipt:
                if receipt["archive_proof"] != archive:
                    raise DeletionError(
                        "GAME_DELETE_ARCHIVE_CHANGED", "Resume with the preserved archive"
                    )
            else:
                verify_database_archive(connection, archive)
            active = connection.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM public.jobs WHERE game_id=:game "
                    "AND status IN ('created','processing'))"
                ),
                {"game": LEGACY_ID},
            )
            report: dict[str, Any] = {
                "policy": POLICY,
                "gameId": LEGACY_ID,
                "protectedGameId": PROTECTED_ID,
                "schemaSha256": schema.sha256,
                "archiveSha256": archive["sha256"],
                "archive": dict(archive),
                "order": list(deletion_order(schema.foreign_keys)),
                "missingIndexes": list(schema.missing_indexes),
                "activeJobs": bool(active),
                "confirmation": CONFIRMATION,
                "totalRows": None,
                "sharedExecutions": "preserved; journaled for reference-aware GC",
            }
            report["ready"] = not active and not schema.missing_indexes
            report["sha256"] = digest(report)
            return report

    def start(self, report: Mapping[str, Any], confirmation: str) -> None:
        payload = {key: value for key, value in report.items() if key != "sha256"}
        if (
            confirmation != CONFIRMATION
            or report.get("sha256") != digest(payload)
            or not report.get("ready")
        ):
            raise DeletionError("GAME_DELETE_CONFIRMATION_REQUIRED", "Use the exact ready preview")
        current = self.preview(report["archive"])
        if current != report:
            raise DeletionError("GAME_DELETE_PREVIEW_DRIFT", "Prepare a fresh preview")
        with self.engine.begin() as connection:
            transaction_limits(connection)
            connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})
            connection.execute(
                text(
                    "LOCK TABLE "
                    + ",".join("public." + quote(t) for t in sorted(OWNED))
                    + " IN ROW EXCLUSIVE MODE"
                )
            )
            if load_schema(connection).sha256 != report["schemaSha256"]:
                raise DeletionError("GAME_DELETE_SCHEMA_DRIFT", "Schema changed before activation")
            previous = (
                connection.execute(
                    text(
                        "SELECT * FROM public.game_deletion_operations "
                        "WHERE game_id=:game FOR UPDATE"
                    ),
                    {"game": LEGACY_ID},
                )
                .mappings()
                .one_or_none()
            )
            validate_identity(
                connection, allow_deleted=bool(previous and previous["status"] == "database_done")
            )
            if connection.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM public.jobs WHERE game_id=:game "
                    "AND status IN ('created','processing'))"
                ),
                {"game": LEGACY_ID},
            ):
                raise DeletionError("GAME_DELETE_ACTIVE_JOBS", "Wait for legacy jobs")
            if previous:
                if previous["preview_sha256"] != report["sha256"]:
                    raise DeletionError(
                        "GAME_DELETE_RECEIPT_CONFLICT", "Resume the existing operation"
                    )
                return
            verify_database_archive(connection, report["archive"])
            connection.execute(
                text("""
INSERT INTO public.game_deletion_operations
(game_id,policy,schema_sha256,archive_sha256,archive_proof,preview_sha256,status)
VALUES (:game,:policy,:schema,:archive,CAST(:proof AS jsonb),:preview,'deleting')
"""),
                {
                    "game": LEGACY_ID,
                    "policy": POLICY,
                    "schema": report["schemaSha256"],
                    "archive": report["archiveSha256"],
                    "proof": json.dumps(report["archive"]),
                    "preview": report["sha256"],
                },
            )

    def status(self) -> dict[str, Any] | None:
        with self.engine.begin() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            transaction_limits(connection)
            row = (
                connection.execute(
                    text("SELECT * FROM public.game_deletion_operations WHERE game_id=:game"),
                    {"game": LEGACY_ID},
                )
                .mappings()
                .one_or_none()
            )
            return dict(row) if row else None

    def step(self, schema: Schema, *, batch_size: int = MAX_BATCH_ROWS) -> dict[str, Any]:
        """One commit only; the caller may die immediately after this returns."""
        if not 1 <= batch_size <= MAX_BATCH_ROWS:
            raise ValueError("batch_size must be between 1 and 2000")
        with self.engine.begin() as connection:
            transaction_limits(connection)
            connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})
            connection.execute(
                text(
                    "LOCK TABLE "
                    + ",".join("public." + quote(t) for t in sorted(OWNED))
                    + " IN ROW EXCLUSIVE MODE"
                )
            )
            if catalog_digest(connection) != schema.catalog_sha256:
                raise DeletionError("GAME_DELETE_SCHEMA_DRIFT", "Schema changed between batches")
            state_row = (
                connection.execute(
                    text(
                        "SELECT * FROM public.game_deletion_operations "
                        "WHERE game_id=:game FOR UPDATE"
                    ),
                    {"game": LEGACY_ID},
                )
                .mappings()
                .one_or_none()
            )
            if state_row is None:
                raise DeletionError("GAME_DELETE_NOT_STARTED", "Confirmed operation required")
            state = dict(state_row)
            if state["schema_sha256"] != schema.sha256 or state["policy"] != POLICY:
                raise DeletionError("GAME_DELETE_SCHEMA_DRIFT", "Receipt schema mismatch")
            if state["status"] == "database_done":
                return state
            validate_identity(connection, allow_deleted=True)
            connection.execute(
                text(
                    "UPDATE public.game_deletion_operations SET executor_xid=txid_current() "
                    "WHERE game_id=:game"
                ),
                {"game": LEGACY_ID},
            )
            stages = (
                ("unlink:games",)
                + tuple(f"unlink:{t}" for t in sorted(SELF_LINKS))
                + deletion_order(schema.foreign_keys)
            )
            index = int(state["stage_index"])
            if index >= len(stages):
                state["status"] = "database_done"
                self._save(connection, state)
                return state
            stage = stages[index]
            table_name = stage.removeprefix("unlink:")
            table = schema.tables[table_name]
            column = None
            if stage.startswith("unlink:"):
                column = (
                    "board_topology_rules_version_id"
                    if table_name == "games"
                    else SELF_LINKS[table_name]
                )
            cursor = list(state["stage_cursor"])
            selected, exhausted = select_owned_batch(
                connection, schema, table_name, cursor, batch_size, column
            )
            state["stage_cursor"] = cursor
            if not selected:
                if exhausted:
                    state["stage_index"] = index + 1
                    state["stage_cursor"] = []
                self._save(connection, state)
                return state
            # Parameterized PK list is bounded; no global marker table.
            params: dict[str, Any] = {"game": LEGACY_ID}
            predicates = []
            for n, row in enumerate(selected):
                terms = []
                for field in table.primary_key:
                    param = f"pk_{n}_{field}"
                    params[param] = row[field]
                    terms.append(f"r.{quote(field)}=:{param}")
                predicates.append("(" + " AND ".join(terms) + ")")
            selection = "(" + " OR ".join(predicates) + ")"
            references: list[dict[str, Any]] = []
            actual_deleted = 0
            queue_jobs: list[str] = []
            queue_states_before = 0
            queue_params: dict[str, Any] = {}
            queue_selection = "FALSE"
            if stage.startswith("unlink:"):
                assert column is not None
                # Removing a self-reference never removes the parent or another game's row.
                connection.execute(
                    text(
                        f"UPDATE public.{quote(table_name)} r SET {quote(column)}=NULL "
                        f"WHERE {selection}"
                    ),
                    params,
                )
            else:
                self._check_foreign_owners(connection, schema, table, selection, params)
                if table_name == "image_review_items":
                    queue_rows = connection.execute(
                        text(
                            "SELECT q.review_item_id,q.import_job_id "
                            "FROM public.image_review_queue_items q "
                            "JOIN public.image_review_items r ON r.id=q.review_item_id "
                            f"WHERE {selection} FOR UPDATE OF q"
                        ),
                        params,
                    ).all()
                    if len(queue_rows) != len(selected):
                        raise DeletionError("GAME_DELETE_QUEUE_PROJECTION_CONFLICT", table_name)
                    queue_jobs = sorted({str(row.import_job_id) for row in queue_rows})
                    queue_params = {f"q{n}": row.review_item_id for n, row in enumerate(queue_rows)}
                    queue_selection = ",".join(":" + key for key in queue_params)
                    queue_states_before = int(
                        connection.scalar(
                            text(
                                "SELECT count(*) FROM public.image_review_queue_states "
                                "WHERE import_job_id=ANY(CAST(:ids AS uuid[]))"
                            ),
                            {"ids": queue_jobs},
                        )
                        or 0
                    )
                raw_rows = connection.execute(
                    text(f"SELECT to_jsonb(r) FROM public.{quote(table_name)} r WHERE {selection}"),
                    params,
                ).scalars()
                for raw in raw_rows:
                    refs = _references(raw)
                    if refs:
                        references.append(
                            {"key": {k: raw[k] for k in table.primary_key}, "refs": refs}
                        )
                if len(json.dumps(references).encode()) > MAX_BATCH_BYTES:
                    raise DeletionError("GAME_DELETE_JOURNAL_TOO_LARGE", table_name)
                deleted = connection.execute(
                    text(f"DELETE FROM public.{quote(table_name)} r WHERE {selection}"), params
                )
                actual_deleted = int(deleted.rowcount)
                if actual_deleted != len(selected):
                    raise DeletionError("GAME_DELETE_ROW_COUNT_CONFLICT", table_name)
                counts = dict(state["deleted_counts"])
                counts[table_name] = int(counts.get(table_name, 0)) + actual_deleted
                if table_name == "image_review_items":
                    remaining = connection.scalar(
                        text(
                            "SELECT count(*) FROM public.image_review_queue_items "
                            f"WHERE review_item_id IN ({queue_selection})"
                        ),
                        queue_params,
                    )
                    if remaining:
                        raise DeletionError("GAME_DELETE_QUEUE_PROJECTION_CONFLICT", table_name)
                    queue_states_after = int(
                        connection.scalar(
                            text(
                                "SELECT count(*) FROM public.image_review_queue_states "
                                "WHERE import_job_id=ANY(CAST(:ids AS uuid[]))"
                            ),
                            {"ids": queue_jobs},
                        )
                        or 0
                    )
                    counts["image_review_queue_items"] = int(
                        counts.get("image_review_queue_items", 0)
                    ) + len(queue_params)
                    counts["image_review_queue_states"] = (
                        int(counts.get("image_review_queue_states", 0))
                        + queue_states_before
                        - queue_states_after
                    )
                state["deleted_counts"] = counts
            sequence = int(state["batch_sequence"]) + 1
            connection.execute(
                text("""
INSERT INTO public.game_deletion_batches(game_id,sequence,stage,deleted_count,asset_references)
VALUES (:game,:sequence,:stage,:count,CAST(:refs AS jsonb))
"""),
                {
                    "game": LEGACY_ID,
                    "sequence": sequence,
                    "stage": stage,
                    "count": actual_deleted,
                    "refs": json.dumps(references, default=str),
                },
            )
            state["batch_sequence"] = sequence
            state["status"] = "deleting"
            if stage == "games":
                # The final domain row and terminal receipt must share a commit.
                # Otherwise restart would see an absent game but a nonterminal receipt.
                state["status"] = "database_done"
                state["stage_index"] = len(stages)
                state["stage_cursor"] = []
            state["failure_code"] = None
            self._save(connection, state)
            return state

    @staticmethod
    def _save(connection: Connection, state: Mapping[str, Any]) -> None:
        connection.execute(
            text("""
UPDATE public.game_deletion_operations SET status=:status,stage_index=:stage,
stage_cursor=CAST(:cursor AS jsonb),
batch_sequence=:sequence,deleted_counts=CAST(:counts AS jsonb),failure_code=:failure,
executor_xid=NULL,updated_at=clock_timestamp() WHERE game_id=:game
"""),
            {
                "game": LEGACY_ID,
                "status": state["status"],
                "stage": state["stage_index"],
                "sequence": state["batch_sequence"],
                "counts": json.dumps(state["deleted_counts"]),
                "cursor": json.dumps(state["stage_cursor"], default=str),
                "failure": state["failure_code"],
            },
        )

    @staticmethod
    def _check_foreign_owners(
        connection: Connection,
        schema: Schema,
        table: Table,
        selection: str,
        params: Mapping[str, Any],
    ) -> None:
        for fk in schema.foreign_keys:
            if fk.parent != table.name:
                continue
            if fk.child not in OWNED:
                raise DeletionError("GAME_DELETE_FOREIGN_REFERENCE", fk.name)
            join = _join("child", "r", fk.columns, fk.parent_columns)
            conflict = connection.scalar(
                text(
                    f"SELECT EXISTS(SELECT 1 FROM public.{quote(fk.child)} child "
                    f"JOIN public.{quote(table.name)} r ON {join} WHERE {selection} "
                    f"AND {owner_sql(fk.child, 'child')} IS DISTINCT FROM CAST(:game AS uuid))"
                ),
                params,
            )
            if conflict:
                raise DeletionError("GAME_DELETE_FOREIGN_OWNER", fk.name)

    def run(
        self,
        schema: Schema,
        *,
        max_steps: int,
        on_progress: Callable[[dict[str, Any]], None],
        max_seconds: float = 90,
    ) -> None:
        deadline = time.monotonic() + max_seconds
        for _ in range(max_steps):
            if time.monotonic() >= deadline:
                return
            size = MAX_BATCH_ROWS
            for attempt in range(3):
                try:
                    state = self.step(schema, batch_size=size)
                    break
                except DBAPIError as error:
                    code = str(getattr(error.orig, "sqlstate", "DATABASE_ERROR"))
                    retryable = code in {"55P03", "57014", "40P01", "40001", "25P04"}
                    if not retryable or attempt == 2:
                        self.fail(code)
                        raise
                    size = max(1, size // 2)
                except DeletionError as error:
                    self.fail(error.code)
                    raise
            on_progress(state)
            if state["status"] == "database_done":
                return

    def fail(self, code: str) -> None:
        with self.engine.begin() as connection:
            transaction_limits(connection)
            connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})
            connection.execute(
                text(
                    "UPDATE public.game_deletion_operations SET status='failed',failure_code=:code,"
                    "executor_xid=NULL,updated_at=clock_timestamp() WHERE game_id=:game "
                    "AND status <> 'database_done'"
                ),
                {"game": LEGACY_ID, "code": code},
            )
