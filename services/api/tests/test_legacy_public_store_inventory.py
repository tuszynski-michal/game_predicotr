from __future__ import annotations

import shutil
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from scripts import audit_legacy_public_game_store as audit_script


def _catalog() -> list[dict[str, object]]:
    return [
        {
            "tableName": name,
            "exists": True,
            "oid": str(index),
            "relkind": "r",
            "relrowsecurity": True,
            "relforcerowsecurity": True,
            "total_bytes": 0,
        }
        for index, name in enumerate(audit_script.GAME_TABLES, start=1)
    ]


def _ready_storage() -> dict[str, object]:
    return {
        "locations": [
            {
                "game_id": "bfc4f949-5c14-4850-b02a-db99610bcfa5",
                "store_schema": "game_data_v2",
                "generation": 2,
                "manifest_version": audit_script.VERSION,
                "status": "active",
                "revision": 0,
            }
        ],
        "migrations": [],
        "activeJobs": [],
    }


def test_manifest_has_closed_legacy_table_set() -> None:
    assert len(audit_script.GAME_TABLES) == 65
    assert tuple(sorted(audit_script.GAME_TABLES)) == audit_script.GAME_TABLES
    assert audit_script._quoted_table("recognized_boards") == 'public."recognized_boards"'
    with pytest.raises(audit_script.AuditError, match="UNKNOWN_TABLE"):
        audit_script._quoted_table("games")


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            lambda catalog, counts, _storage: catalog.__setitem__(
                0, {**catalog[0], "exists": False, "relkind": None}
            ),
            "TABLE_MISSING",
        ),
        (
            lambda _catalog, counts, _storage: counts.__setitem__(0, {**counts[0], "rowCount": 1}),
            "TABLE_NOT_EMPTY",
        ),
        (
            lambda _catalog, _counts, storage: storage["locations"].__setitem__(
                0, {**storage["locations"][0], "store_schema": "public", "generation": 1}
            ),
            "LOCATION_NOT_ACTIVE_V2",
        ),
    ],
)
def test_blockers_fail_closed(
    mutation: Any,
    expected: str,
) -> None:
    catalog = _catalog()
    counts = [{"tableName": row["tableName"], "rowCount": 0} for row in catalog]
    storage = _ready_storage()
    mutation(catalog, counts, storage)

    blockers = audit_script._blockers(catalog, counts, [], [], storage, [])

    assert any(expected in str(blocker["code"]) for blocker in blockers)


def test_external_dependencies_jobs_migrations_and_locks_block() -> None:
    catalog = _catalog()
    counts = [{"tableName": row["tableName"], "rowCount": 0} for row in catalog]
    storage = _ready_storage()
    storage["migrations"] = [{"status": "copying", "id": "migration"}]
    storage["activeJobs"] = [{"status": "processing", "count": 1}]

    blockers = audit_script._blockers(
        catalog,
        counts,
        [{"constraint_name": "outside_fk"}],
        [{"dependent_relation": "outside_view"}],
        storage,
        [{"table_name": "recognized_boards", "mode": "AccessShareLock", "count": 1}],
    )

    assert {str(blocker["code"]) for blocker in blockers} >= {
        "LEGACY_PUBLIC_STORE_EXTERNAL_FK",
        "LEGACY_PUBLIC_STORE_EXTERNAL_RELATION_DEPENDENCY",
        "LEGACY_PUBLIC_STORE_ACTIVE_MIGRATION",
        "LEGACY_PUBLIC_STORE_ACTIVE_JOB",
        "LEGACY_PUBLIC_STORE_EXTERNAL_LOCK",
    }


def test_job_status_query_casts_postgresql_enum_to_text(monkeypatch: pytest.MonkeyPatch) -> None:
    statements: list[str] = []

    class Result:
        def mappings(self) -> Result:
            return self

        def __iter__(self) -> Result:
            return iter(())  # type: ignore[return-value]

    def bounded(_connection: object, statement: str, _params: object = None) -> Result:
        statements.append(statement)
        return Result()

    monkeypatch.setattr(audit_script, "_bounded", bounded)

    audit_script._storage_state(object())  # type: ignore[arg-type]

    job_query = next(statement for statement in statements if "FROM public.jobs" in statement)
    assert "status::text = ANY" in job_query


def test_relation_dependency_query_ignores_internal_indexes_and_toast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements: list[str] = []

    class Result:
        def mappings(self) -> Result:
            return self

        def __iter__(self) -> Result:
            return iter(())  # type: ignore[return-value]

    def bounded(_connection: object, statement: str, _params: object = None) -> Result:
        statements.append(statement)
        return Result()

    monkeypatch.setattr(audit_script, "_bounded", bounded)

    assert audit_script._relation_dependencies(object()) == []  # type: ignore[arg-type]
    assert "dependent.relkind IN ('r', 'p', 'v', 'm', 'f')" in statements[0]
    assert "pg_rewrite" in statements[0]


def test_audit_uses_read_only_transaction_and_reports_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements: list[str] = []

    class Connection:
        def __init__(self) -> None:
            self.info: dict[str, object] = {}

        def exec_driver_sql(self, statement: str) -> None:
            statements.append(statement)

        def execute(self, statement: object, _params: object | None = None) -> Any:
            statements.append(str(statement))
            return SimpleNamespace()

        def rollback(self) -> None:
            statements.append("ROLLBACK")

    connection = Connection()

    class Engine:
        def connect(self) -> Any:
            @contextmanager
            def opened() -> Any:
                yield connection

            return opened()

    monkeypatch.setattr(audit_script, "_database_state", lambda _connection: {"alembic": "0124"})
    monkeypatch.setattr(audit_script, "_catalog", lambda _connection: _catalog())
    monkeypatch.setattr(
        audit_script,
        "_table_counts",
        lambda _connection, catalog: [
            {"tableName": row["tableName"], "rowCount": 0} for row in catalog
        ],
    )
    monkeypatch.setattr(audit_script, "_foreign_key_dependencies", lambda _connection: [])
    monkeypatch.setattr(audit_script, "_relation_dependencies", lambda _connection: [])
    monkeypatch.setattr(
        audit_script,
        "_trigger_and_policy_summary",
        lambda _connection: {"triggers": [], "policies": []},
    )
    monkeypatch.setattr(audit_script, "_storage_state", lambda _connection: _ready_storage())
    monkeypatch.setattr(audit_script, "_locks", lambda _connection: [])

    report = audit_script.audit(Engine())  # type: ignore[arg-type]

    assert report["status"] == "ready"
    assert statements[0] == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
    assert "statement_timeout" in statements[1]
    assert "lock_timeout" in statements[2]
    assert statements[-1] == "ROLLBACK"


def test_report_is_canonical_and_atomic() -> None:
    workspace = Path.cwd() / ".test-artifacts" / f"legacy-public-store-{uuid4().hex}"
    workspace.mkdir(parents=True)
    try:
        target = workspace / "inventory.json"
        report = {"status": "ready", "readOnly": True}

        first = audit_script._write_report(target, report)
        second = audit_script._write_report(target, report)

        assert first == second
        assert target.read_bytes() == b'{"readOnly":true,"status":"ready"}\n'
        assert not list(workspace.glob(".inventory.json.*"))
    finally:
        shutil.rmtree(workspace)
