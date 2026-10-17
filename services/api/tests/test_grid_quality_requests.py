"""Real closed HTTP DTOs and scoped trusted actors without a database or service."""

from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.grid_quality_measurements import create_grid_quality_measurements_router
from game_predictor_api.application.grid_geometry_approvals import GridGeometryApprovalService
from game_predictor_api.application.grid_quality_measurements import GridQualityMeasurementService
from game_predictor_api.security.local_admin import (
    AppendOnlyAdminAuditLog,
    LocalAdminSecurityMiddleware,
)


def test_approval_authorizes_before_replay_and_retains_exact_scoped_body(tmp_path):
    game, job, review, measurement, source, key = (uuid4() for _ in range(6))
    calls = []

    class Repository:
        def approve(self, *arguments):
            calls.append(arguments)
            return {"receipt": {"eventId": str(key)}}

    service = SimpleNamespace(grid_geometry_approvals=GridGeometryApprovalService(Repository()))
    app = FastAPI()
    app.add_middleware(
        LocalAdminSecurityMiddleware,
        admin_origin="http://127.0.0.1:3000",
        reviewer_origin="http://127.0.0.1:3001",
        audit_log=AppendOnlyAdminAuditLog(tmp_path),
    )
    app.include_router(
        create_grid_quality_measurements_router(lambda: service, lambda: None, tmp_path),
        prefix="/api/v1",
    )
    path = f"/api/v1/admin/image-reviews/{review}/geometry-approvals"
    scope = {"gameId": str(game), "importJobId": str(job)}
    body = {
        "idempotencyKey": str(key),
        "measurementId": str(measurement),
        "sourceId": str(source),
        "sampleKind": "random",
        "positionIndex": 0,
        "manifestSha256": "a" * 64,
        "targetSha256": "b" * 64,
    }
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        assert client.post(path, params=scope, json=body).status_code == 403
        assert calls == []
        headers = {"Origin": "http://127.0.0.1:3001", "X-Admin-Intent": "local-owner"}
        assert client.post(path, params=scope, json=body, headers=headers).status_code == 200
        assert calls[-1] == (game, job, review, body, "local-owner")
        assert (
            client.post(
                path, params=scope, json={**body, "actor": "spoof"}, headers=headers
            ).status_code
            == 422
        )


def test_reload_get_is_read_only_and_forged_incomplete_nine_is_rejected(tmp_path):
    game, measurement = uuid4(), uuid4()
    calls = []

    class Repository:
        def list_measurements(self, *arguments):
            calls.append(("GET", arguments))
            return {"items": [], "nextCursor": None}

        def assess(self, *arguments):
            calls.append(("POST", arguments))

    service = SimpleNamespace(grid_quality_measurements=GridQualityMeasurementService(Repository()))
    app = FastAPI()
    app.add_middleware(
        LocalAdminSecurityMiddleware,
        admin_origin="http://127.0.0.1:3000",
        reviewer_origin="http://127.0.0.1:3001",
        audit_log=AppendOnlyAdminAuditLog(tmp_path),
    )
    app.include_router(
        create_grid_quality_measurements_router(lambda: service, lambda: None, tmp_path),
        prefix="/api/v1",
    )
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        path = f"/api/v1/admin/games/{game}/grid-quality-measurements"
        assert client.get(path).status_code == client.get(path).status_code == 200
        assert all(value[0] == "GET" for value in calls)
        body = {
            "idempotencyKey": str(uuid4()),
            "sourceId": str(uuid4()),
            "sampleKind": "random",
            "expectedRevision": 0,
            "manifestSha256": "a" * 64,
            "positions": [],
        }
        headers = {"Origin": "http://127.0.0.1:3000", "X-Admin-Intent": "local-owner"}
        assert (
            client.post(f"{path}/{measurement}/assess", json=body, headers=headers).status_code
            == 422
        )
        assert all(value[0] == "GET" for value in calls)
