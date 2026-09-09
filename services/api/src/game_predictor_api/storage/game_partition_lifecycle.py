"""Resumable, manifest-bound lifecycle for one game's V2 partitions."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from graphlib import CycleError, TopologicalSorter
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from game_predictor_api.storage.game_data_v2_manifest_v1 import (
    CREATE_TABLES,
    DELETE_TABLES,
    SCHEMA,
    VERSION,
)

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")
_DDL_LOCK_TIMEOUT = "2s"
_DDL_STATEMENT_TIMEOUT = "30s"


class GamePartitionLifecycleKind(StrEnum):
    PROVISION = "provision"
    DELETE = "delete"


class GamePartitionLifecycleError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: Mapping[str, object] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


@dataclass(frozen=True, slots=True)
class GamePartitionLifecycleReceipt:
    operation_id: UUID
    game_id: UUID
    kind: GamePartitionLifecycleKind
    status: str
    next_table_index: int
    completed_tables: tuple[str, ...]
    failure_code: str | None


def partition_name(game_id: UUID, table_name: str) -> str:
    _require_manifest_table(table_name)
    suffix = hashlib.sha256(table_name.encode("ascii")).hexdigest()[:12]
    return f"gpv2_{game_id.hex[:12]}_{suffix}"


class GamePartitionLifecycleRepository:
    """Execute one DDL/checkpoint step per caller-owned transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def start_or_resume(
        self,
        *,
        game_id: UUID,
        kind: GamePartitionLifecycleKind,
    ) -> GamePartitionLifecycleReceipt:
        self._require_postgres()
        existing = self._active_receipt(game_id=game_id, kind=kind, for_update=True)
        if existing is not None:
            return existing
        completed = self._latest_done_receipt(game_id=game_id, kind=kind)
        if completed is not None:
            self._require_done_receipt_valid(completed)
            return completed
        if kind is GamePartitionLifecycleKind.PROVISION:
            self._require_catalog_game(game_id)
        else:
            self._close_writes_for_delete(game_id)
        operation_id = uuid4()
        self._session.execute(
            text(
                """INSERT INTO public.game_storage_lifecycle_operations
                (id, game_id, operation_kind, manifest_version, status,
                 next_table_index, completed_tables)
                VALUES (:id, :game_id, :kind, :version, 'running', 0, '[]'::jsonb)"""
            ),
            {
                "id": operation_id,
                "game_id": game_id,
                "kind": kind.value,
                "version": VERSION,
            },
        )
        receipt = self._receipt(operation_id, for_update=True)
        assert receipt is not None
        return receipt

    def run_next(self, operation_id: UUID) -> GamePartitionLifecycleReceipt:
        self._require_postgres()
        receipt = self._receipt(operation_id, for_update=True)
        if receipt is None:
            raise GamePartitionLifecycleError(
                "GAME_PARTITION_LIFECYCLE_NOT_FOUND", "The lifecycle operation does not exist."
            )
        if receipt.status == "done":
            return receipt
        if receipt.status == "blocked":
            raise GamePartitionLifecycleError(
                receipt.failure_code or "GAME_PARTITION_LIFECYCLE_BLOCKED",
                "The lifecycle operation is blocked and needs operator review.",
            )
        tables = (
            tuple(CREATE_TABLES)
            if receipt.kind is GamePartitionLifecycleKind.PROVISION
            else self._delete_tables()
        )
        if receipt.completed_tables != tables[: receipt.next_table_index]:
            error = GamePartitionLifecycleError(
                "GAME_PARTITION_CHECKPOINT_DRIFT",
                "The persisted lifecycle checkpoint no longer matches the frozen manifest.",
            )
            self._mark_blocked(operation_id, error)
            raise error
        if receipt.next_table_index >= len(tables):
            self._finalize(receipt)
            finished = self._receipt(operation_id, for_update=True)
            assert finished is not None
            return finished
        table_name = tables[receipt.next_table_index]
        try:
            self._set_ddl_timeouts()
            self._acquire_exclusive_game_fence(receipt.game_id)
            if receipt.kind is GamePartitionLifecycleKind.PROVISION:
                self._provision_partition(receipt.game_id, table_name)
            else:
                self._drop_partition(receipt.game_id, table_name)
            completed = (*receipt.completed_tables, table_name)
            self._session.execute(
                text(
                    """UPDATE public.game_storage_lifecycle_operations
                    SET next_table_index = :next_index,
                        completed_tables = CAST(:completed AS jsonb), updated_at = now()
                    WHERE id = :id"""
                ),
                {
                    "id": operation_id,
                    "next_index": receipt.next_table_index + 1,
                    "completed": _json_array(completed),
                },
            )
        except GamePartitionLifecycleError as error:
            self._mark_blocked(operation_id, error)
            raise
        updated = self._receipt(operation_id, for_update=True)
        assert updated is not None
        return updated

    def _provision_partition(self, game_id: UUID, table_name: str) -> None:
        parent = f"{_quote(SCHEMA)}.{_quote(table_name)}"
        child_name = partition_name(game_id, table_name)
        child = f"{_quote(SCHEMA)}.{_quote(child_name)}"
        existing = self._partition_binding(child_name)
        if existing is None:
            self._session.execute(
                text(f"CREATE TABLE {child} PARTITION OF {parent} FOR VALUES IN ('{game_id}')")
            )
            self._session.execute(
                text(
                    f"ALTER TABLE {child} SET "
                    "(autovacuum_vacuum_scale_factor = 0.02, "
                    "autovacuum_analyze_scale_factor = 0.01)"
                )
            )
        elif existing != (table_name, str(game_id)):
            raise GamePartitionLifecycleError(
                "GAME_PARTITION_STRUCTURE_DRIFT",
                "An existing partition name has a different parent or bound.",
                details={"table": table_name, "partition": child_name},
            )
        self._validate_partition_shape(table_name, child_name, game_id)
        self._session.execute(text(f"ANALYZE {child}"))

    def _drop_partition(self, game_id: UUID, table_name: str) -> None:
        child_name = partition_name(game_id, table_name)
        existing = self._partition_binding(child_name)
        if existing is None:
            return
        if existing != (table_name, str(game_id)):
            raise GamePartitionLifecycleError(
                "GAME_PARTITION_STRUCTURE_DRIFT",
                "The partition selected for deletion has a different owner.",
                details={"table": table_name, "partition": child_name},
            )
        parent = f"{_quote(SCHEMA)}.{_quote(table_name)}"
        child = f"{_quote(SCHEMA)}.{_quote(child_name)}"
        self._session.execute(text(f"ALTER TABLE {parent} DETACH PARTITION {child}"))
        self._session.execute(text(f"DROP TABLE {child}"))

    def _finalize(self, receipt: GamePartitionLifecycleReceipt) -> None:
        if receipt.kind is GamePartitionLifecycleKind.PROVISION:
            self._require_all_partitions(receipt.game_id)
            location = self._session.execute(
                text(
                    """INSERT INTO public.game_storage_locations
                    (game_id, store_schema, generation, manifest_version, status, revision)
                    VALUES (:game_id, 'game_data_v2', 1, :version, 'active', 0)
                    ON CONFLICT (game_id) DO UPDATE SET
                      store_schema = EXCLUDED.store_schema,
                      manifest_version = EXCLUDED.manifest_version,
                      status = 'active', revision = game_storage_locations.revision + 1
                    WHERE game_storage_locations.store_schema = 'game_data_v2'
                      AND game_storage_locations.status <> 'deleting'
                    RETURNING store_schema, status"""
                ),
                {"game_id": receipt.game_id, "version": VERSION},
            ).one_or_none()
            if location is None or tuple(map(str, location)) != ("game_data_v2", "active"):
                raise GamePartitionLifecycleError(
                    "GAME_PARTITION_LOCATION_CONFLICT",
                    "An existing storage location cannot be replaced by V2 provisioning.",
                )
        else:
            if any(
                self._partition_binding(partition_name(receipt.game_id, table)) is not None
                for table in DELETE_TABLES
            ):
                raise GamePartitionLifecycleError(
                    "GAME_PARTITION_DELETE_INCOMPLETE",
                    "A game partition still exists after the delete checkpoint.",
                )
            self._delete_catalog(receipt.game_id)
            self._session.execute(
                text("DELETE FROM public.game_storage_locations WHERE game_id = :game_id"),
                {"game_id": receipt.game_id},
            )
            deleted = self._session.execute(
                text("DELETE FROM public.games WHERE id = :game_id RETURNING id"),
                {"game_id": receipt.game_id},
            ).one_or_none()
            if deleted is None:
                raise GamePartitionLifecycleError(
                    "GAME_PARTITION_DELETE_CATALOG_MISSING",
                    "The game catalog row disappeared before lifecycle finalization.",
                )
        self._session.execute(
            text(
                """UPDATE public.game_storage_lifecycle_operations
                SET status = 'done', updated_at = now() WHERE id = :id"""
            ),
            {"id": receipt.operation_id},
        )

    def _delete_catalog(self, game_id: UUID) -> None:
        self._session.execute(
            text(
                "UPDATE public.games SET board_topology_rules_version_id = NULL WHERE id = :game_id"
            ),
            {"game_id": game_id},
        )
        for table_name in ("paylines", "payout_rules", "rules_version_symbols"):
            self._session.execute(
                text(
                    f"DELETE FROM public.{_quote(table_name)} WHERE rules_version_id IN "
                    "(SELECT id FROM public.rules_versions WHERE game_id = :game_id)"
                ),
                {"game_id": game_id},
            )
        for table_name in ("symbols", "rules_versions", "jobs"):
            self._session.execute(
                text(f"DELETE FROM public.{_quote(table_name)} WHERE game_id = :game_id"),
                {"game_id": game_id},
            )

    def _require_done_receipt_valid(self, receipt: GamePartitionLifecycleReceipt) -> None:
        if receipt.kind is GamePartitionLifecycleKind.PROVISION:
            self._require_catalog_game(receipt.game_id)
            self._require_all_partitions(receipt.game_id)
            location = self._session.execute(
                text(
                    """SELECT store_schema, manifest_version, status
                    FROM public.game_storage_locations WHERE game_id = :game_id"""
                ),
                {"game_id": receipt.game_id},
            ).one_or_none()
            if location is None or tuple(map(str, location)) != (
                "game_data_v2",
                VERSION,
                "active",
            ):
                raise GamePartitionLifecycleError(
                    "GAME_PARTITION_DONE_RECEIPT_DRIFT",
                    "A completed provision receipt no longer matches active V2 storage.",
                )
            return
        if any(
            self._partition_binding(partition_name(receipt.game_id, table)) is not None
            for table in DELETE_TABLES
        ):
            raise GamePartitionLifecycleError(
                "GAME_PARTITION_DONE_RECEIPT_DRIFT",
                "A completed delete receipt still has game partitions.",
            )
        if (
            self._session.execute(
                text("SELECT id FROM public.games WHERE id = :game_id"),
                {"game_id": receipt.game_id},
            ).one_or_none()
            is not None
        ):
            raise GamePartitionLifecycleError(
                "GAME_PARTITION_DONE_RECEIPT_DRIFT",
                "A completed delete receipt still has a game catalog row.",
            )

    def _close_writes_for_delete(self, game_id: UUID) -> None:
        self._acquire_exclusive_game_fence(game_id)
        result = self._session.execute(
            text(
                """UPDATE public.game_storage_locations
                SET status = 'deleting', revision = revision + 1, updated_at = now()
                WHERE game_id = :game_id AND store_schema = 'game_data_v2'
                  AND status IN ('active', 'deleting') RETURNING game_id"""
            ),
            {"game_id": game_id},
        ).one_or_none()
        if result is None:
            raise GamePartitionLifecycleError(
                "GAME_PARTITION_DELETE_LOCATION_INVALID",
                "Only a registered V2 game can enter partition deletion.",
            )

    def _validate_partition_shape(self, table_name: str, child_name: str, game_id: UUID) -> None:
        binding = self._partition_binding(child_name)
        if binding != (table_name, str(game_id)):
            raise GamePartitionLifecycleError(
                "GAME_PARTITION_STRUCTURE_DRIFT",
                "The created partition does not match the manifest parent and game bound.",
                details={"table": table_name, "partition": child_name},
            )
        missing = self._session.execute(
            text(
                """SELECT count(*) FROM pg_attribute parent_col
                JOIN pg_class parent ON parent.oid = parent_col.attrelid
                JOIN pg_namespace pn ON pn.oid = parent.relnamespace
                WHERE pn.nspname = :schema AND parent.relname = :parent
                  AND parent_col.attnum > 0 AND NOT parent_col.attisdropped
                  AND NOT EXISTS (
                    SELECT 1 FROM pg_attribute child_col
                    JOIN pg_class child ON child.oid = child_col.attrelid
                    JOIN pg_namespace cn ON cn.oid = child.relnamespace
                    WHERE cn.nspname = :schema AND child.relname = :child
                      AND child_col.attname = parent_col.attname
                      AND child_col.atttypid = parent_col.atttypid
                      AND child_col.attnotnull = parent_col.attnotnull)"""
            ),
            {"schema": SCHEMA, "parent": table_name, "child": child_name},
        ).scalar_one()
        if int(missing) != 0:
            raise GamePartitionLifecycleError(
                "GAME_PARTITION_STRUCTURE_DRIFT",
                "The partition columns differ from the manifest parent.",
                details={"table": table_name, "partition": child_name},
            )
        shape_gaps = self._session.execute(
            text(
                """WITH relations AS (
                    SELECT parent.oid AS parent_oid, child.oid AS child_oid
                    FROM pg_class parent
                    JOIN pg_namespace pn ON pn.oid = parent.relnamespace
                    JOIN pg_class child ON child.relname = :child
                    JOIN pg_namespace cn ON cn.oid = child.relnamespace
                    WHERE pn.nspname = :schema AND cn.nspname = :schema
                      AND parent.relname = :parent
                )
                SELECT
                  (SELECT count(*) FROM pg_index parent_index, relations r
                   WHERE parent_index.indrelid = r.parent_oid
                     AND NOT EXISTS (
                       SELECT 1 FROM pg_inherits link
                       JOIN pg_index child_index ON child_index.indexrelid = link.inhrelid
                       WHERE link.inhparent = parent_index.indexrelid
                         AND child_index.indrelid = r.child_oid))
                  +
                  (SELECT count(*) FROM pg_trigger parent_trigger, relations r
                   WHERE parent_trigger.tgrelid = r.parent_oid
                     AND NOT parent_trigger.tgisinternal
                     AND NOT EXISTS (
                       SELECT 1 FROM pg_trigger child_trigger
                       WHERE child_trigger.tgrelid = r.child_oid
                         AND child_trigger.tgname = parent_trigger.tgname
                         AND NOT child_trigger.tgisinternal))
                  +
                  (SELECT count(*) FROM pg_constraint parent_constraint, relations r
                   WHERE parent_constraint.conrelid = r.parent_oid
                     AND parent_constraint.contype = 'c'
                     AND NOT EXISTS (
                       SELECT 1 FROM pg_constraint child_constraint
                       WHERE child_constraint.conrelid = r.child_oid
                         AND child_constraint.conname = parent_constraint.conname
                         AND child_constraint.contype = 'c'))"""
            ),
            {"schema": SCHEMA, "parent": table_name, "child": child_name},
        ).scalar_one()
        if int(shape_gaps) != 0:
            raise GamePartitionLifecycleError(
                "GAME_PARTITION_STRUCTURE_DRIFT",
                "The partition is missing a manifest parent index, constraint or trigger.",
                details={"table": table_name, "partition": child_name},
            )

    def _require_all_partitions(self, game_id: UUID) -> None:
        for table_name in CREATE_TABLES:
            self._validate_partition_shape(
                table_name,
                partition_name(game_id, table_name),
                game_id,
            )

    def _delete_tables(self) -> tuple[str, ...]:
        rows = self._session.execute(
            text(
                """SELECT COALESCE(child_root.relname, child.relname),
                          COALESCE(parent_root.relname, parent.relname)
                FROM pg_constraint fk
                JOIN pg_class child ON child.oid = fk.conrelid
                JOIN pg_namespace cn ON cn.oid = child.relnamespace
                JOIN pg_class parent ON parent.oid = fk.confrelid
                JOIN pg_namespace pn ON pn.oid = parent.relnamespace
                LEFT JOIN pg_inherits child_link ON child_link.inhrelid = child.oid
                LEFT JOIN pg_class child_root ON child_root.oid = child_link.inhparent
                LEFT JOIN pg_inherits parent_link ON parent_link.inhrelid = parent.oid
                LEFT JOIN pg_class parent_root ON parent_root.oid = parent_link.inhparent
                WHERE fk.contype = 'f' AND cn.nspname = :schema
                  AND pn.nspname = :schema"""
            ),
            {"schema": SCHEMA},
        ).all()
        manifest = set(DELETE_TABLES)
        dependencies: dict[str, set[str]] = {table: set() for table in DELETE_TABLES}
        for child, parent in rows:
            child_name, parent_name = str(child), str(parent)
            if child_name not in manifest or parent_name not in manifest:
                raise GamePartitionLifecycleError(
                    "GAME_PARTITION_FOREIGN_KEY_DRIFT",
                    "A V2 foreign key points outside the frozen game-table manifest.",
                    details={"child": child_name, "parent": parent_name},
                )
            if child_name != parent_name:
                dependencies[parent_name].add(child_name)
        try:
            order = tuple(
                TopologicalSorter(
                    {table: sorted(children) for table, children in sorted(dependencies.items())}
                ).static_order()
            )
        except CycleError as error:
            raise GamePartitionLifecycleError(
                "GAME_PARTITION_DEPENDENCY_CYCLE",
                "The V2 partition dependency graph contains a cycle.",
            ) from error
        if set(order) != manifest:
            raise GamePartitionLifecycleError(
                "GAME_PARTITION_MANIFEST_DRIFT",
                "The partition delete order does not cover the frozen manifest.",
            )
        return order

    def _partition_binding(self, child_name: str) -> tuple[str, str] | None:
        row = self._session.execute(
            text(
                """SELECT parent.relname, pg_get_expr(child.relpartbound, child.oid)
                FROM pg_class child
                JOIN pg_namespace cn ON cn.oid = child.relnamespace
                LEFT JOIN pg_inherits i ON i.inhrelid = child.oid
                LEFT JOIN pg_class parent ON parent.oid = i.inhparent
                WHERE cn.nspname = :schema AND child.relname = :child"""
            ),
            {"schema": SCHEMA, "child": child_name},
        ).one_or_none()
        if row is None:
            return None
        parent, bound = str(row[0]), str(row[1])
        match = re.search(r"'([0-9a-f-]{36})'(?:::uuid)?", bound, re.IGNORECASE)
        return parent, "" if match is None else str(UUID(match.group(1)))

    def _active_receipt(
        self, *, game_id: UUID, kind: GamePartitionLifecycleKind, for_update: bool
    ) -> GamePartitionLifecycleReceipt | None:
        suffix = " FOR UPDATE" if for_update else ""
        row = (
            self._session.execute(
                text(
                    """SELECT id, game_id, operation_kind, status, next_table_index,
                          completed_tables, failure_code
                FROM public.game_storage_lifecycle_operations
                WHERE game_id = :game_id AND operation_kind = :kind AND status <> 'done'
                ORDER BY created_at DESC LIMIT 1"""
                    + suffix
                ),
                {"game_id": game_id, "kind": kind.value},
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _receipt_from_row(cast(Mapping[str, Any], row))

    def _latest_done_receipt(
        self, *, game_id: UUID, kind: GamePartitionLifecycleKind
    ) -> GamePartitionLifecycleReceipt | None:
        row = (
            self._session.execute(
                text(
                    """SELECT id, game_id, operation_kind, status, next_table_index,
                              completed_tables, failure_code
                    FROM public.game_storage_lifecycle_operations
                    WHERE game_id = :game_id AND operation_kind = :kind AND status = 'done'
                    ORDER BY created_at DESC LIMIT 1"""
                ),
                {"game_id": game_id, "kind": kind.value},
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _receipt_from_row(cast(Mapping[str, Any], row))

    def _receipt(
        self, operation_id: UUID, *, for_update: bool
    ) -> GamePartitionLifecycleReceipt | None:
        suffix = " FOR UPDATE" if for_update else ""
        row = (
            self._session.execute(
                text(
                    """SELECT id, game_id, operation_kind, status, next_table_index,
                          completed_tables, failure_code
                FROM public.game_storage_lifecycle_operations WHERE id = :id"""
                    + suffix
                ),
                {"id": operation_id},
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _receipt_from_row(cast(Mapping[str, Any], row))

    def _mark_blocked(self, operation_id: UUID, error: GamePartitionLifecycleError) -> None:
        self._session.execute(
            text(
                """UPDATE public.game_storage_lifecycle_operations
                SET status = 'blocked', failure_code = :code, failure_message = :message,
                    updated_at = now() WHERE id = :id"""
            ),
            {"id": operation_id, "code": error.code, "message": error.message[:500]},
        )

    def _require_catalog_game(self, game_id: UUID) -> None:
        if (
            self._session.execute(
                text("SELECT id FROM public.games WHERE id = :game_id FOR KEY SHARE"),
                {"game_id": game_id},
            ).one_or_none()
            is None
        ):
            raise GamePartitionLifecycleError("GAME_NOT_FOUND", "The selected game does not exist.")

    def _acquire_exclusive_game_fence(self, game_id: UUID) -> None:
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:game_id, 519))"),
            {"game_id": str(game_id)},
        )

    def _set_ddl_timeouts(self) -> None:
        self._session.execute(
            text("SELECT set_config('lock_timeout', :value, true)"),
            {"value": _DDL_LOCK_TIMEOUT},
        )
        self._session.execute(
            text("SELECT set_config('statement_timeout', :value, true)"),
            {"value": _DDL_STATEMENT_TIMEOUT},
        )

    def _require_postgres(self) -> None:
        if self._session.connection().dialect.name != "postgresql":
            raise GamePartitionLifecycleError(
                "GAME_PARTITION_POSTGRES_REQUIRED", "Partition lifecycle requires PostgreSQL."
            )


def _receipt_from_row(row: Mapping[str, Any]) -> GamePartitionLifecycleReceipt:
    completed = row["completed_tables"]
    if not isinstance(completed, list) or any(not isinstance(value, str) for value in completed):
        raise GamePartitionLifecycleError(
            "GAME_PARTITION_CHECKPOINT_INVALID", "The lifecycle checkpoint is invalid."
        )
    return GamePartitionLifecycleReceipt(
        operation_id=UUID(str(row["id"])),
        game_id=UUID(str(row["game_id"])),
        kind=GamePartitionLifecycleKind(str(row["operation_kind"])),
        status=str(row["status"]),
        next_table_index=int(row["next_table_index"]),
        completed_tables=tuple(cast(list[str], completed)),
        failure_code=None if row["failure_code"] is None else str(row["failure_code"]),
    )


def _require_manifest_table(table_name: str) -> None:
    if table_name not in CREATE_TABLES or _IDENTIFIER.fullmatch(table_name) is None:
        raise GamePartitionLifecycleError(
            "GAME_PARTITION_TABLE_NOT_IN_MANIFEST",
            "The requested partition table is not in the frozen manifest.",
            details={"table": table_name},
        )


def _quote(identifier: str) -> str:
    if _IDENTIFIER.fullmatch(identifier) is None:
        raise GamePartitionLifecycleError(
            "GAME_PARTITION_IDENTIFIER_INVALID", "A generated SQL identifier is invalid."
        )
    return f'"{identifier}"'


def _json_array(values: tuple[str, ...]) -> str:
    return "[" + ",".join(f'"{value}"' for value in values) + "]"


__all__ = [
    "GamePartitionLifecycleError",
    "GamePartitionLifecycleKind",
    "GamePartitionLifecycleReceipt",
    "GamePartitionLifecycleRepository",
    "partition_name",
]
