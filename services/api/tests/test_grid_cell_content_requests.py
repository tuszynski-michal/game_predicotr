"""Actual HTTP/security boundary; persistence is covered by disposable PostgreSQL."""

from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.grid_cell_content import (
    content_error_response,
    create_grid_cell_content_router,
)
from game_predictor_api.application.grid_cell_content import GridCellContentService
from game_predictor_api.domain.grid_cell_content import ContentError
from game_predictor_api.security.local_admin import (
    AppendOnlyAdminAuditLog,
    LocalAdminSecurityMiddleware,
)


def test_blind_session_http_is_source_only_authorized_and_strict(tmp_path):
    game, session, cohort, source, key = (uuid4() for _ in range(5))
    calls = []
    status = {
        "sessionId": str(session),
        "gameId": str(game),
        "revision": 1,
        "phase": "pass1",
        "completed": 0,
        "total": 1,
        "report": None,
    }

    class Repository:
        def readiness(self, game_id, cohort_id, manifest_sha):
            missing = {"version": "source-cell-content-v1", "state": "not_evaluable", "games": {}}
            return {
                **missing,
                "basis": "frozen_content_pins",
                "frozenPinCoverage": missing,
                "annotationProgress": {**missing, "state": "evaluable"},
            }

        def sampling_preview(self, game_id, command):
            calls.append(("sampling", game_id, command))
            return {"state": "selection_ready", "roleWrites": False}

        def create_session(self, game_id, command, actor):
            calls.append(("create", game_id, command, actor))
            return {"idempotencyKey": str(command.idempotencyKey), "session": status}

        def get_session(self, game_id, session_id):
            calls.append(("get", game_id, session_id))
            return {**status, "targets": []}

        def list_sessions(self, game_id, limit):
            calls.append(("list", game_id, limit))
            return {"items": [status]}

        def blind_write(self, game_id, session_id, command, actor):
            calls.append(("observe", game_id, session_id, command, actor))
            raise ContentError("CONTENT_SESSION_STALE", "Reload the session.")

    service = SimpleNamespace(grid_cell_content=GridCellContentService(Repository()))
    app = FastAPI()

    @app.exception_handler(ContentError)
    async def handle_content(_request, error):
        return content_error_response(error)

    app.add_middleware(
        LocalAdminSecurityMiddleware,
        admin_origin="http://127.0.0.1:3000",
        reviewer_origin="http://127.0.0.1:3001",
        audit_log=AppendOnlyAdminAuditLog(tmp_path),
    )
    app.include_router(create_grid_cell_content_router(lambda: service), prefix="/api/v1")
    path = f"/api/v1/admin/games/{game}/grid-quality-measurements/content-sessions"
    body = {
        "idempotencyKey": str(key),
        "cohortId": str(cohort),
        "expectedManifestSha256": "a" * 64,
        "sourceIds": [str(source)],
    }
    headers = {"Origin": "http://127.0.0.1:3001", "X-Admin-Intent": "local-owner"}
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        assert client.post(path, json=body).status_code == 403
        assert calls == []
        assert client.post(path, json=body, headers=headers).status_code == 200
        assert calls[-1][-1] == "local-owner"
        assert (
            client.post(path, json={**body, "actor": "worker:fake"}, headers=headers).status_code
            == 422
        )
        assert client.get(path).json() == {"items": [status]}
        view = client.get(f"{path}/{session}").json()
        assert set(view) == {*status, "targets"}
        observation = {
            "idempotencyKey": str(uuid4()),
            "expectedSessionRevision": 1,
            "passNumber": 1,
            "sourceId": str(source),
            "positionIndex": 0,
            "humanApproval": True,
            "cells": [{"state": "unknown"} for _ in range(15)],
            "measuredNodes": [[float(c), float(r)] for r in range(4) for c in range(6)],
        }
        for invalid in (1, "true", False):
            assert (
                client.post(
                    f"{path}/{session}/observations",
                    json={**observation, "humanApproval": invalid},
                    headers=headers,
                ).status_code
                == 422
            )
        response = client.post(f"{path}/{session}/observations", json=observation, headers=headers)
        assert response.status_code == 409
        assert response.json()["code"] == "CONTENT_SESSION_STALE"
        assert response.json()["details"] == {}
        assert [entry[0] for entry in calls].count("observe") == 1
        sampling = client.post(
            path.replace("content-sessions", "content-sampling-preview"),
            json={
                "baseVersionId": str(cohort),
                "familyId": str(game),
                "importJobIds": [str(source)],
            },
            headers={"Origin": "http://127.0.0.1:3000", "X-Admin-Intent": "local-owner"},
        )
        assert sampling.status_code == 200
        assert sampling.json()["state"] == "selection_ready"
        assert sampling.json()["qualificationState"] == "not_evaluated"
        readiness = client.get(
            path.replace("content-sessions", "content-readiness"),
            params={"cohortId": str(cohort), "manifestSha256": "a" * 64},
        )
        assert readiness.status_code == 200
        assert readiness.json()["annotationProgress"]["state"] == "evaluable"
        assert (
            readiness.json()["state"]
            == readiness.json()["frozenPinCoverage"]["state"]
            == "not_evaluable"
        )


def test_actual_write_maps_out_of_source_quad_to_typed_422(tmp_path):
    from game_predictor_api.domain.grid_cell_content import ContentSource
    from game_predictor_api.storage.grid_cell_content import SqlAlchemyGridCellContentRepository

    game, source_id = uuid4(), uuid4()
    source = ContentSource(
        sourceId=source_id,
        sourceSha256="a" * 64,
        sourceRepresentativeSha256="b" * 64,
        width=100,
        height=100,
    )

    class Repository(SqlAlchemyGridCellContentRepository):
        def begin_command(self, *args):
            return None

        def current_source(self, *args, **kwargs):
            return source

        def require_board(self, *args):
            pass

        def lock(self, *args):
            pass

        def latest(self, *args):
            return None

        def append(self, *args, **kwargs):
            raise AssertionError("Invalid request must never persist a revision")

    app = FastAPI()

    @app.exception_handler(ContentError)
    async def handle_content(_request, error):
        return content_error_response(error)

    app.add_middleware(
        LocalAdminSecurityMiddleware,
        admin_origin="http://127.0.0.1:3000",
        reviewer_origin="http://127.0.0.1:3001",
        audit_log=AppendOnlyAdminAuditLog(tmp_path),
    )
    service = SimpleNamespace(grid_cell_content=GridCellContentService(Repository(None, tmp_path)))
    app.include_router(create_grid_cell_content_router(lambda: service), prefix="/api/v1")
    cells = [{"state": "unknown"} for _ in range(15)]
    cells[0] = {"state": "visible", "quad": [[101, 1], [102, 1], [102, 2], [101, 2]]}
    body = {
        "idempotencyKey": str(uuid4()),
        "sourceId": str(source_id),
        "expectedSourceSha256": "a" * 64,
        "expectedPixelSha256": "b" * 64,
        "positionIndex": 0,
        "sequenceNumber": 1,
        "expectedRevision": 0,
        "humanApproval": True,
        "cells": cells,
    }
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        response = client.post(
            f"/api/v1/admin/games/{game}/grid-quality-measurements/content-references",
            json=body,
            headers={"Origin": "http://127.0.0.1:3000", "X-Admin-Intent": "local-owner"},
        )
    assert response.status_code == 422
    assert response.json()["code"] == "CONTENT_QUAD_OUTSIDE_SOURCE"
