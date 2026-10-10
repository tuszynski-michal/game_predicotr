"""TASK-0797: probe every API route on the application role for unbound game access.

The application role (TASK-0795) has no RLS bypass, and game tables live only
in ``game_data_v2``, which is on the ``search_path`` only after a game binding.
A route that touches game data without binding its game therefore fails with
``relation … does not exist`` (42P01) or ``GAME_STORAGE_SCOPE_REQUIRED``
(42501). This probe calls every OpenAPI operation once with synthesized
parameters on a disposable database (two provisioned games) through the real
``create_app`` wiring and fails on any such error. Validation errors, 404s
and domain conflicts are expected: they prove the route reached its handler
without an unbound statement first. Processes (Reviewer ingress, the
Windows folder picker) are stubbed; the database is dropped afterwards.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from _application_role_database import ApplicationRoleDatabase, application_role_database
from fastapi.testclient import TestClient
from game_predictor_api.application.controlled_folder_picker import WindowsFolderPicker
from game_predictor_api.application.reviewer_ingress import ReviewerIngressService
from game_predictor_api.main import create_app

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)

_UNBOUND_MARKERS = (
    "GAME_STORAGE_SCOPE_REQUIRED",
    "UndefinedTable",
    "does not exist",
    "InsufficientPrivilege",
    "permission denied",
)
# Justified exceptions (none): a route listed here would be allowed to fail
# with an unbound-game error. Keep empty unless the Outcome documents why.
_ALLOWED_UNBOUND: frozenset[tuple[str, str]] = frozenset()


@dataclass(frozen=True)
class _Outcome:
    method: str
    path: str
    status: int | None
    error: str | None

    @property
    def unbound(self) -> bool:
        text = self.error or ""
        return any(marker in text for marker in _UNBOUND_MARKERS)


class _NoIngress:
    def status(self) -> object:
        raise RuntimeError("PROBE_INGRESS_DISABLED")

    def start(self, *_args: object, **_kwargs: object) -> object:
        raise RuntimeError("PROBE_INGRESS_DISABLED")

    def start_local(self) -> object:
        raise RuntimeError("PROBE_INGRESS_DISABLED")

    def stop(self) -> object:
        raise RuntimeError("PROBE_INGRESS_DISABLED")


@pytest.fixture(scope="module")
def probe_database() -> Iterator[ApplicationRoleDatabase]:
    with application_role_database("t0797probe", ("t0797-a", "t0797-b")) as database:
        yield database


def _resolve(spec: Mapping[str, Any], schema: Mapping[str, Any]) -> Mapping[str, Any]:
    while "$ref" in schema:
        name = str(schema["$ref"]).rsplit("/", 1)[-1]
        schema = spec["components"]["schemas"][name]
    if "allOf" in schema and len(schema["allOf"]) == 1:
        return _resolve(spec, schema["allOf"][0])
    if "anyOf" in schema:
        options = [item for item in schema["anyOf"] if item.get("type") != "null"]
        if options:
            return _resolve(spec, options[0])
    return schema


def _value(
    spec: Mapping[str, Any], name: str, schema: Mapping[str, Any], game_id: UUID, depth: int = 0
) -> Any:
    schema = _resolve(spec, schema)
    if "enum" in schema:
        return schema["enum"][0]
    if "const" in schema:
        return schema["const"]
    kind = schema.get("type")
    lowered = name.replace("_", "").lower()
    if kind == "string":
        if schema.get("format") == "uuid":
            return str(game_id) if lowered == "gameid" else str(uuid4())
        if schema.get("format") == "date-time":
            return "2026-10-01T00:00:00Z"
        if "sha256" in lowered or "checksum" in lowered:
            return "a" * 64
        length = int(schema.get("minLength", 1))
        return "x" * max(1, length)
    if kind == "integer":
        return int(schema.get("minimum", 1))
    if kind == "number":
        return float(schema.get("minimum", 1))
    if kind == "boolean":
        return False
    if kind == "array":
        minimum = int(schema.get("minItems", 0))
        item = schema.get("items", {})
        return [_value(spec, name, item, game_id, depth + 1) for _ in range(minimum)]
    if kind == "object" or "properties" in schema:
        if depth > 4:
            return {}
        properties = schema.get("properties", {})
        return {
            key: _value(spec, key, properties[key], game_id, depth + 1)
            for key in schema.get("required", [])
            if key in properties
        }
    return "x"


def _request(
    spec: Mapping[str, Any], path: str, operation: Mapping[str, Any], game_id: UUID
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    url = path
    query: dict[str, Any] = {}
    for parameter in operation.get("parameters", []):
        name = str(parameter["name"])
        schema = parameter.get("schema", {})
        if parameter["in"] == "path":
            if "game_id" in name:
                value: Any = str(game_id)
            elif "index" in name or name == "sequence_number":
                value = 1
            else:
                value = _value(spec, name, schema, game_id)
            url = url.replace("{" + name + "}", str(value))
        elif parameter["in"] == "query" and (parameter.get("required") or name == "gameId"):
            query[name] = _value(spec, name, schema, game_id)
    kwargs: dict[str, Any] = {"params": query}
    body = operation.get("requestBody", {}).get("content", {})
    if "application/json" in body:
        kwargs["json"] = _value(spec, "body", body["application/json"]["schema"], game_id)
    elif "application/octet-stream" in body:
        kwargs["content"] = b"probe"
    return url, kwargs, {}


def _probe(
    database: ApplicationRoleDatabase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> list[_Outcome]:
    def no_picker(_self: object) -> None:
        raise RuntimeError("PROBE_FOLDER_PICKER_DISABLED")

    monkeypatch.setattr(WindowsFolderPicker, "choose", no_picker)
    # The Reviewer work lifecycle holds its own ingress instance.
    for method in ("status", "start", "start_local", "stop", "stop_if_current"):
        monkeypatch.setattr(ReviewerIngressService, method, _NoIngress.start)
    (tmp_path / "artifacts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "imports").mkdir(parents=True, exist_ok=True)
    application = create_app(
        database.settings(tmp_path),
        reviewer_ingress_service_dependency=lambda: _NoIngress(),
    )
    spec = application.openapi()
    game_id = database.games["t0797-a"]
    outcomes: list[_Outcome] = []
    try:
        with TestClient(application, raise_server_exceptions=True) as client:
            for path, operations in sorted(spec["paths"].items()):
                for method, operation in sorted(operations.items()):
                    url, kwargs, _ = _request(spec, path, operation, game_id)
                    try:
                        response = client.request(method.upper(), url, **kwargs)
                    except Exception as error:  # noqa: BLE001 - the probe records everything
                        cause = getattr(error, "orig", None) or error
                        outcomes.append(
                            _Outcome(
                                method.upper(),
                                path,
                                None,
                                f"{type(error).__name__}: {type(cause).__name__}: {cause}"[:400],
                            )
                        )
                        continue
                    error_text = response.text[:400] if response.status_code >= 500 else None
                    outcomes.append(
                        _Outcome(method.upper(), path, response.status_code, error_text)
                    )
    finally:
        application.state.database_engine.dispose()
    return outcomes


def test_no_route_fails_with_an_unbound_game_on_the_application_role(
    probe_database: ApplicationRoleDatabase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcomes = _probe(probe_database, tmp_path, monkeypatch)
    unbound = sorted(
        (outcome.method, outcome.path, outcome.error or "")
        for outcome in outcomes
        if outcome.unbound and (outcome.method, outcome.path) not in _ALLOWED_UNBOUND
    )
    other_server_errors = sorted(
        (outcome.method, outcome.path, outcome.error or "")
        for outcome in outcomes
        if outcome.error is not None and not outcome.unbound
    )
    report = Path(os.environ.get("GAME_PREDICTOR_ROUTE_PROBE_REPORT", tmp_path / "probe.txt"))
    report.write_text(
        "\n".join(
            [f"routes={len(outcomes)}", "== unbound"]
            + [" | ".join(item) for item in unbound]
            + ["== other server errors"]
            + [" | ".join(item) for item in other_server_errors]
        ),
        encoding="utf-8",
    )
    assert len(outcomes) > 250
    assert unbound == [], "\n".join(" | ".join(item) for item in unbound)
