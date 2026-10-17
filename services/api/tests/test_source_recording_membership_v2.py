"""Bounded transport and permission regression coverage for the0162 seam."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.source_recording_groups import create_source_recording_groups_router
from game_predictor_api.application.source_recording_groups import SourceRecordingGroupsService
from game_predictor_api.storage import source_recording_permissions as v1
from game_predictor_api.storage import source_recording_permissions_v2 as permissions
from game_predictor_api.storage.database_roles import DatabaseRoleError
from game_predictor_api.storage.source_recording_groups import SqlAlchemySourceRecordingRepository
from game_predictor_api.storage.source_recording_sql_v2 import (
    DROP_SOURCE_RECORDING_V2_SQL,
    INSTALL_SOURCE_RECORDING_V2_SQL,
)
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session


class _Result:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one(self) -> Any:
        return self.value

    def mappings(self) -> _Result:
        return self

    def one_or_none(self) -> Any:
        return self.value


class _Connection:
    def __init__(self) -> None:
        self.function: dict[str, Any] | None = {
            "oid": 42,
            "owner": "gp_rec_fixture",
            "prosecdef": True,
            "proconfig": ["search_path=pg_catalog"],
            "public_execute": True,
        }
        self.runtime_execute = False
        self.relations: set[str] = set()
        self.revision162 = False
        self.manifest15 = False
        self.statements: list[str] = []

    def execute(self, statement: object, parameters: Any = None) -> _Result:
        sql = str(statement)
        if "pg_catalog.pg_proc" in sql:
            assert parameters == {"signature": permissions.SOURCE_RECORDING_V2_FUNCTION}
            assert "LIKE" not in sql
            return _Result(self.function)
        if "has_function_privilege" in sql:
            assert parameters == {"role": "runtime", "oid": 42}
            return _Result(self.runtime_execute)
        if "FROM public.alembic_version" in sql:
            return _Result(self.revision162)
        if "FROM public.game_storage_locations" in sql:
            return _Result(self.manifest15)
        raise AssertionError(sql)

    def exec_driver_sql(self, sql: str) -> None:
        self.statements.append(sql)
        assert self.function is not None
        if sql.startswith("REVOKE"):
            self.function["public_execute"] = False
            self.runtime_execute = False
        elif sql.startswith("GRANT"):
            self.runtime_execute = True
        else:
            raise AssertionError(sql)


@pytest.fixture
def boundary(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        v1,
        "enforce_recording_permissions",
        lambda connection, role: calls.append(("enforce_v1", role)),
    )
    monkeypatch.setattr(
        v1,
        "recording_permission_errors",
        lambda connection, role: (),
    )
    monkeypatch.setattr(v1, "_exists", lambda connection, name: name in connection.relations)
    monkeypatch.setattr(
        permissions, "validate_recording_capability", lambda connection: "gp_rec_fixture"
    )
    return calls


def test_current_boundary_keeps_old_audit_findings(
    boundary: list[tuple[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        v1,
        "recording_permission_errors",
        lambda connection, role: ("old-private-table:runtime_access",),
    )
    connection = _Connection()
    connection.function = None
    assert permissions.recording_permission_errors(cast(Connection, connection), "runtime") == (
        "old-private-table:runtime_access",
    )


def test_reprovision_reapplies_exact_union_after_broad_grants(
    boundary: list[tuple[str, str]],
) -> None:
    connection = _Connection()
    for _ in range(2):
        assert connection.function is not None
        connection.function["public_execute"] = True
        connection.runtime_execute = True
        permissions.enforce_recording_permissions(cast(Connection, connection), "runtime")
        assert not permissions.recording_permission_errors(cast(Connection, connection), "runtime")
    assert boundary == [("enforce_v1", "runtime"), ("enforce_v1", "runtime")]
    signature = permissions.SOURCE_RECORDING_V2_FUNCTION
    assert (
        connection.statements
        == [
            f'REVOKE ALL PRIVILEGES ON FUNCTION {signature} FROM "runtime", PUBLIC',
            f'GRANT EXECUTE ON FUNCTION {signature} TO "runtime"',
        ]
        * 2
    )
    assert signature not in v1.RECORDING_FUNCTIONS


@pytest.mark.parametrize("marker", ["none", "table", "revision", "manifest"])
def test_missing_overload_is_required_only_by_real_installation(
    boundary: list[tuple[str, str]],
    marker: str,
) -> None:
    connection = _Connection()
    connection.function = None
    if marker == "table":
        connection.relations.add("game_data_v2.grid_quality_measurements")
        # Upgrade has not moved Alembic or routing manifest yet.
    elif marker == "revision":
        connection.relations.add("public.alembic_version")
        connection.revision162 = True
    elif marker == "manifest":
        connection.relations.add("public.game_storage_locations")
        connection.manifest15 = True
    errors = permissions.recording_permission_errors(cast(Connection, connection), "runtime")
    if marker == "none":
        assert errors == ()
        permissions.enforce_recording_permissions(cast(Connection, connection), "runtime")
    else:
        assert errors == (f"{permissions.SOURCE_RECORDING_V2_FUNCTION}:missing",)
        with pytest.raises(DatabaseRoleError) as caught:
            permissions.enforce_recording_permissions(cast(Connection, connection), "runtime")
        assert caught.value.code == "RECORDING_PERMISSION_NOT_COMPLIANT"
    assert connection.statements == []


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("owner", "foreign_owner", "owner"),
        ("prosecdef", False, "security"),
        ("proconfig", ["search_path=public, pg_catalog"], "security"),
        ("public_execute", True, "public_execute"),
    ],
)
def test_exact_overload_owner_security_and_public_are_audited(
    boundary: list[tuple[str, str]],
    field: str,
    value: Any,
    error: str,
) -> None:
    connection = _Connection()
    assert connection.function is not None
    connection.function["public_execute"] = False
    connection.function[field] = value
    connection.runtime_execute = True
    assert permissions.recording_permission_errors(cast(Connection, connection), "runtime") == (
        f"{permissions.SOURCE_RECORDING_V2_FUNCTION}:{error}",
    )


def test_runtime_missing_execute_is_reported(boundary: list[tuple[str, str]]) -> None:
    connection = _Connection()
    assert connection.function is not None
    connection.function["public_execute"] = False
    assert permissions.recording_permission_errors(cast(Connection, connection), "runtime") == (
        f"{permissions.SOURCE_RECORDING_V2_FUNCTION}:runtime_execute",
    )


@pytest.mark.parametrize("field,value", [("owner", "foreign_owner"), ("prosecdef", False)])
def test_reprovision_does_not_repair_owner_or_security(
    boundary: list[tuple[str, str]],
    field: str,
    value: Any,
) -> None:
    connection = _Connection()
    assert connection.function is not None
    connection.function[field] = value
    with pytest.raises(DatabaseRoleError) as caught:
        permissions.enforce_recording_permissions(cast(Connection, connection), "runtime")
    assert caught.value.code == "RECORDING_PERMISSION_NOT_COMPLIANT"
    assert connection.function[field] == value


def test_v1_enforcement_failure_stops_new_grants(
    boundary: list[tuple[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection()

    def fail(_connection: Connection, _role: str) -> None:
        raise DatabaseRoleError("V1_BOUNDARY_BROKEN", "Existing registry boundary failed.")

    monkeypatch.setattr(v1, "enforce_recording_permissions", fail)
    with pytest.raises(DatabaseRoleError) as caught:
        permissions.enforce_recording_permissions(cast(Connection, connection), "runtime")
    assert caught.value.code == "V1_BOUNDARY_BROKEN"
    assert connection.statements == []


def test_sql_membership_is_own_main_and_precedes_pagination() -> None:
    sql = INSTALL_SOURCE_RECORDING_V2_SQL
    assert "occurrence.game_id=wanted" in sql
    assert "occurrence.origin='MAIN'" in sql
    assert "occurrence.source_id=wanted_source" in sql
    assert sql.index("occurrence.source_id=wanted_source") < sql.index("selected.id>after_id")
    assert sql.index("occurrence.source_id=wanted_source") < sql.index("LIMIT page_limit")
    assert "SECURITY DEFINER SET search_path=pg_catalog" in sql
    assert DROP_SOURCE_RECORDING_V2_SQL.strip() == (
        "DROP FUNCTION public.resolve_own_groups(uuid,uuid[],uuid,integer,uuid,uuid);"
    )


@pytest.mark.parametrize("filtered", [False, True])
def test_repository_uses_old_overload_unless_source_filter_is_given(
    filtered: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = SqlAlchemySourceRecordingRepository(cast(Session, object()))
    game, source, after, group = (uuid4() for _ in range(4))
    calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(repository, "bind", lambda wanted: None)

    def call(sql: str, values: dict[str, Any]) -> dict[str, Any]:
        calls.append((sql, values))
        return {"items": [], "nextCursor": None}

    monkeypatch.setattr(repository, "_call", call)
    repository.list_groups(game, None, 4, after, [group], source if filtered else None)
    sql, values = calls[0]
    assert ",CAST(:source AS uuid)" in sql if filtered else ":source" not in sql
    assert values == {
        "game": game,
        "family": None,
        "limit": 4,
        "after": after,
        "ids": [group],
        **({"source": source} if filtered else {}),
    }


def test_get_source_filter_flows_through_service_and_rejects_invalid_uuid(tmp_path: Any) -> None:
    calls: list[tuple[Any, ...]] = []

    class Repository:
        def list_groups(self, *args: Any) -> dict[str, Any]:
            calls.append(args)
            return {"items": [], "nextCursor": None}

    service = SourceRecordingGroupsService(cast(Any, Repository()), tmp_path)
    application = FastAPI()
    application.include_router(create_source_recording_groups_router(lambda: service))
    game, source, group, after = (uuid4() for _ in range(4))
    url = f"/api/v1/admin/games/{game}/source-recording-groups"
    with TestClient(application) as client:
        assert client.get(url).status_code == 200
        assert calls[-1] == (game, None, 100, None, None)
        response = client.get(
            url,
            params={
                "sourceId": str(source),
                "groupId": str(group),
                "after": str(after),
                "limit": 3,
            },
        )
        assert response.status_code == 200
        assert calls[-1] == (game, None, 3, after, [group], source)
        assert client.get(url, params={"sourceId": "invalid"}).status_code == 422
    parameters = application.openapi()["paths"][url.replace(str(game), "{game_id}")]["get"][
        "parameters"
    ]
    source_parameter = next(p for p in parameters if p["name"] == "sourceId")
    assert not source_parameter["required"]
    assert isinstance(calls[-1][-1], UUID)
