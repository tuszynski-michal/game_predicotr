"""TASK-0797: a Reviewer session works through the real API on the application role.

The Reviewer's bearer token is looked up in ``reviewer_access_sessions``, a
game table behind forced RLS. Routes that name their game (path or
``gameId``) look only in that game; ``unlock`` and the context routes find the
session's game through per-game RLS-bound reads. The board is seeded as the
schema owner (deferred slot resolved through the Admin wiring), then every
Reviewer allowlist route is called with the token through ``create_app`` whose
runtime sessions log in as a test-scoped ``game_predictor_app_test_<hex>``
LOGIN role (random password, valid one hour, dropped afterwards).
"""

from __future__ import annotations

import json
import re
import secrets
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.config import ApiSettings
from game_predictor_api.main import create_app
from game_predictor_api.storage.database_roles import (
    ApplicationRoleSpec,
    provision_application_role,
)
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
from test_reviewer_operational_geometry_postgres import _SHIFTED_CORNERS, _add_symbols
from test_virtual_deferred_resolution_postgres import (
    _Database,
    _factory,
    _provision_game,
    _resolve_via_reviewer_endpoint,
    _seed,
    database,  # noqa: F401  (pytest fixture)
    pytestmark,  # noqa: F401  (PostgreSQL opt-in)
)


@dataclass(frozen=True)
class _ApplicationRole:
    settings: ApiSettings
    role: str


@pytest.fixture
def application_role(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> Iterator[_ApplicationRole]:
    role = f"game_predictor_app_test_{uuid4().hex[:12]}"
    assert re.fullmatch(r"game_predictor_app_test_[0-9a-f]{12}", role)
    password = secrets.token_urlsafe(24)
    owner_url = make_url(database.url)
    with database.engine.begin() as connection:
        provision_application_role(
            connection, ApplicationRoleSpec(role_name=role, password=password)
        )
        expires = connection.exec_driver_sql(
            "SELECT to_char(now() + interval '1 hour', 'YYYY-MM-DD HH24:MI:SSOF')"
        ).scalar_one()
        connection.exec_driver_sql(f"ALTER ROLE \"{role}\" VALID UNTIL '{expires}'")
    settings = ApiSettings(
        host="127.0.0.1",
        port=8000,
        admin_origin="http://127.0.0.1:3000",
        database_url=owner_url.set(username=role, password=password).render_as_string(
            hide_password=False
        ),
        configured_owner_database_url=database.url,
        artifact_root=(tmp_path / "artifacts").resolve(),
        import_root=(tmp_path / "imports").resolve(),
    )
    try:
        yield _ApplicationRole(settings=settings, role=role)
    finally:
        # Grants live in the test database; revoke them there, then drop the
        # cluster-wide role (the database fixture drops the database).
        with database.engine.begin() as connection:
            connection.exec_driver_sql(f'DROP OWNED BY "{role}"')
        maintenance = create_engine(
            owner_url.set(database="postgres"),
            isolation_level="AUTOCOMMIT",
            poolclass=NullPool,
        )
        try:
            with maintenance.connect() as connection:
                connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{role}"')
        finally:
            maintenance.dispose()


def _reviewable(
    database: _Database,  # noqa: F811
    artifact_root: Path,
    code: str,
) -> tuple[UUID, UUID, UUID]:
    game_id = _provision_game(database.engine, code)
    factory = _factory(database.engine)
    seed = _seed(factory, game_id, artifact_root, label=f"{code}-source", slot_count=1)
    _add_symbols(factory, game_id)
    resolution = _resolve_via_reviewer_endpoint(database, artifact_root, seed)
    # The seed's import payload carries only what the deferred resolution
    # needs; ``/reviewer/context/jobs`` serializes the full browser payload.
    with database.engine.begin() as connection:
        connection.execute(
            text("UPDATE public.jobs SET input_payload = input_payload || :extra WHERE id = :id"),
            {
                "id": seed.import_job_id,
                "extra": json.dumps(
                    {
                        "source_selection_id": str(uuid4()),
                        "source_directory": f"browser-selections/{code}",
                        "source_display_name": code,
                        "source_pipeline_fingerprint": "c" * 64,
                        "source_manifest_sha256": "d" * 64,
                        "start_mode": "reuse_exact",
                        "grid_profile": {
                            "profile_version": "t0797-grid",
                            "profile_checksum_sha256": "e" * 64,
                            "profile_payload": {},
                            "inference_fingerprint": "f" * 64,
                        },
                    }
                ),
            },
        )
    return game_id, seed.import_job_id, UUID(str(resolution["reviewItemId"]))


def _json(response: Any, status: int) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_reviewer_token_session_works_on_every_allowlisted_route(
    database: _Database,  # noqa: F811
    application_role: _ApplicationRole,
    tmp_path: Path,
) -> None:
    artifact_root = application_role.settings.artifact_root
    game_a, import_a, item_a = _reviewable(database, artifact_root, "t0797-rev-a")
    game_b, import_b, _item_b = _reviewable(database, artifact_root, "t0797-reviewer-bb")
    app = create_app(application_role.settings)
    try:
        with TestClient(app) as client:
            created_a = _json(
                client.post(
                    "/api/v1/admin/reviewer-sessions",
                    json={"gameId": str(game_a), "importJobId": str(import_a)},
                ),
                201,
            )
            created_b = _json(
                client.post(
                    "/api/v1/admin/reviewer-sessions",
                    json={"gameId": str(game_b), "importJobId": str(import_b)},
                ),
                201,
            )
            unlock_a = f"/api/v1/reviewer/sessions/{created_a['sessionId']}/unlock"
            token_a = _json(
                client.post(unlock_a, json={"accessCode": created_a["accessCode"]}), 200
            )["accessToken"]
            token_b = _json(
                client.post(
                    f"/api/v1/reviewer/sessions/{created_b['sessionId']}/unlock",
                    json={"accessCode": created_b["accessCode"]},
                ),
                200,
            )["accessToken"]
            auth_a = {"Authorization": f"Bearer {token_a}"}
            auth_b = {"Authorization": f"Bearer {token_b}"}
            scope_a = {"gameId": str(game_a), "importJobId": str(import_a)}
            item_path = f"/api/v1/admin/image-review-items/{item_a}"

            # Context routes name no game: the session's game is located.
            games = _json(client.get("/api/v1/reviewer/context/games", headers=auth_a), 200)
            assert [game["id"] for game in games] == [str(game_a)]
            jobs = _json(client.get("/api/v1/reviewer/context/jobs", headers=auth_b), 200)
            assert [job["id"] for job in jobs] == [str(import_b)]
            symbols = _json(
                client.get(f"/api/v1/reviewer/context/games/{game_a}/symbols", headers=auth_a),
                200,
            )
            assert {symbol["code"] for symbol in symbols} == {"CYTRYNA", "WISNIA"}

            # Operational review routes name the game in ``gameId``.
            page = _json(
                client.get("/api/v1/admin/image-review-items", params=scope_a, headers=auth_a),
                200,
            )
            assert [entry["id"] for entry in page["items"]] == [str(item_a)]
            item = _json(client.get(item_path, params=scope_a, headers=auth_a), 200)
            _json(
                client.get(f"{item_path}/resolution-events", params=scope_a, headers=auth_a),
                200,
            )
            source = client.get(f"{item_path}/assets/source", params=scope_a, headers=auth_a)
            assert source.status_code == 200, source.text
            _json(
                client.get(
                    f"/api/v1/admin/games/{game_a}/image-imports/{import_a}/"
                    "board-cell-geometry-pending",
                    headers=auth_a,
                ),
                200,
            )
            command = {
                "corners": _SHIFTED_CORNERS,
                "expectedGeometryRevision": item["geometryRevision"],
                "expectedResolutionRevision": item["resolutionRevision"],
            }
            preview = client.post(
                f"{item_path}/geometry-preview", params=scope_a, headers=auth_a, json=command
            )
            assert preview.status_code == 200, preview.text
            corrected = _json(
                client.post(
                    f"{item_path}/geometry-revisions",
                    params=scope_a,
                    headers=auth_a,
                    json={**command, "idempotencyKey": str(uuid4()), "correctedBy": "ignored"},
                ),
                200,
            )
            assert corrected["geometryRevision"]["correctedBy"] == (
                f"reviewer-session:{created_a['sessionId']}"
            )
            refreshed = _json(client.get(item_path, params=scope_a, headers=auth_a), 200)
            resolved = _json(
                client.post(
                    f"{item_path}/resolution",
                    params=scope_a,
                    headers=auth_a,
                    json={
                        "idempotencyKey": str(uuid4()),
                        "expectedRevision": refreshed["resolutionRevision"],
                        "action": "rejected",
                        "geometryRevision": refreshed["geometryRevision"],
                        "rejectionReason": "task-0797 reviewer token",
                        "resolvedBy": "ignored",
                    },
                ),
                200,
            )
            assert resolved["item"]["status"] == "rejected"
            assert resolved["event"]["resolvedBy"] == f"reviewer-session:{created_a['sessionId']}"

            # A token of game B never authorizes game A: in game A's scope the
            # session does not exist, so the token is invalid (no scope leak).
            foreign = client.get("/api/v1/admin/image-review-items", params=scope_a, headers=auth_b)
            assert foreign.status_code == 401, foreign.text
            assert foreign.json()["code"] == "REVIEWER_TOKEN_INVALID"
            foreign_symbols = client.get(
                f"/api/v1/reviewer/context/games/{game_a}/symbols", headers=auth_b
            )
            assert foreign_symbols.status_code == 401, foreign_symbols.text
    finally:
        app.state.database_engine.dispose()


def test_reviewer_unlock_attempts_lock_the_session_whatever_game_is_named(
    database: _Database,  # noqa: F811
    application_role: _ApplicationRole,
) -> None:
    artifact_root = application_role.settings.artifact_root
    game_a, import_a, _item_a = _reviewable(database, artifact_root, "t0797-lock-a")
    other_game = _provision_game(database.engine, "t0797-lock-other")
    app = create_app(application_role.settings)
    try:
        with TestClient(app) as client:
            created = _json(
                client.post(
                    "/api/v1/admin/reviewer-sessions",
                    json={"gameId": str(game_a), "importJobId": str(import_a)},
                ),
                201,
            )
            unlock = f"/api/v1/reviewer/sessions/{created['sessionId']}/unlock"
            # Naming another game hides the session: the code is never checked,
            # so a foreign ``gameId`` cannot be used to guess without a limit.
            hidden = client.post(
                unlock,
                params={"gameId": str(other_game)},
                json={"accessCode": created["accessCode"]},
            )
            assert hidden.status_code == 404, hidden.text
            assert hidden.json()["code"] == "REVIEWER_SESSION_NOT_FOUND"
            codes = []
            for _attempt in range(5):
                response = client.post(unlock, json={"accessCode": "WRONG-CODE"})
                codes.append(response.json()["code"])
            assert codes == ["REVIEWER_ACCESS_CODE_INVALID"] * 4 + ["REVIEWER_SESSION_LOCKED"]
            locked = client.post(unlock, json={"accessCode": created["accessCode"]})
            assert locked.json()["code"] == "REVIEWER_SESSION_LOCKED"
            with_game = client.post(
                unlock, params={"gameId": str(game_a)}, json={"accessCode": created["accessCode"]}
            )
            assert with_game.json()["code"] == "REVIEWER_SESSION_LOCKED"
    finally:
        app.state.database_engine.dispose()
