from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from game_predictor_api.application.reviewer_ingress import (
    ReviewerIngressStatus,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.main import create_app
from game_predictor_api.security.local_admin import (
    AppendOnlyAdminAuditLog,
    match_high_impact_operation,
    redact_security_metadata,
)


class _FakeIngress:
    def __init__(self) -> None:
        self.started = False

    def status(self) -> ReviewerIngressStatus:
        return self._response()

    def start(self) -> ReviewerIngressStatus:
        self.started = True
        return self._response()

    def start_local(self) -> ReviewerIngressStatus:
        return ReviewerIngressStatus(
            state="running",
            public_origin=None,
            target="http://127.0.0.1:3001",
            started_at=datetime(2026, 8, 15, 18, 0, tzinfo=UTC),
            reviewer_ready=True,
        )

    def stop(self) -> ReviewerIngressStatus:
        self.started = False
        return self._response()

    def _response(self) -> ReviewerIngressStatus:
        return ReviewerIngressStatus(
            state="running" if self.started else "stopped",
            public_origin=("https://bounded-review.trycloudflare.com" if self.started else None),
            target="http://127.0.0.1:3001",
            started_at=datetime(2026, 7, 31, 12, 0, tzinfo=UTC) if self.started else None,
            reviewer_ready=True,
        )


def _settings(tmp_path: Path) -> ApiSettings:
    return ApiSettings(
        host="127.0.0.1",
        port=8000,
        admin_origin="http://127.0.0.1:3000",
        artifact_root=tmp_path,
    )


def _confirmed_headers() -> dict[str, str]:
    return {
        "Origin": "http://127.0.0.1:3000",
        "X-Admin-Intent": "local-owner",
        "X-Admin-Confirmation": "confirmed",
        "X-Admin-Target": "remote-reviewer",
    }


def _post_start(client: TestClient, headers: dict[str, str] | None = None):
    return client.post(
        "/api/v1/admin/reviewer-ingress/start",
        headers=headers,
        json={"confirmed": True, "target": "remote-reviewer"},
    )


def test_admin_mutation_requires_loopback_origin_intent_confirmation_and_target(
    tmp_path: Path,
) -> None:
    ingress = _FakeIngress()
    app = create_app(
        _settings(tmp_path),
        reviewer_ingress_service_dependency=lambda: ingress,
    )

    with TestClient(
        app,
        base_url="http://127.0.0.1:8000",
        client=("203.0.113.50", 42000),
    ) as remote:
        assert _post_start(remote, _confirmed_headers()).json()["code"] == (
            "ADMIN_LOOPBACK_REQUIRED"
        )

    with TestClient(
        app,
        base_url="http://127.0.0.1:8000",
        client=("127.0.0.1", 42001),
    ) as local:
        missing_intent = _post_start(local)
        assert missing_intent.status_code == 403
        assert missing_intent.json()["code"] == "ADMIN_INTENT_REQUIRED"

        foreign_origin_headers = _confirmed_headers() | {"Origin": "https://attacker.example"}
        foreign_origin = _post_start(local, foreign_origin_headers)
        assert foreign_origin.status_code == 403
        assert foreign_origin.json()["code"] == "ADMIN_ORIGIN_FORBIDDEN"

        wrong_target_headers = _confirmed_headers() | {"X-Admin-Target": "remote-reviewer-typo"}
        wrong_target = _post_start(local, wrong_target_headers)
        assert wrong_target.status_code == 403
        assert wrong_target.json()["code"] == "ADMIN_CONFIRMATION_REQUIRED"

        accepted = _post_start(local, _confirmed_headers())
        assert accepted.status_code == 200
        assert accepted.json()["state"] == "running"

    events = [
        json.loads(line)
        for line in AppendOnlyAdminAuditLog(tmp_path).path.read_text(encoding="utf-8").splitlines()
    ]
    assert [event["outcome"] for event in events] == [
        "rejected",
        "rejected",
        "rejected",
        "rejected",
        "authorized",
        "succeeded",
    ]
    assert {event["actor"] for event in events} == {"local-owner"}
    assert {event["target"] for event in events} == {"remote-reviewer"}
    assert "attacker.example" not in json.dumps(events)


def test_security_metadata_redacts_nested_credentials() -> None:
    sanitized = redact_security_metadata(
        {
            "token": "top-secret-token",
            "nested": {
                "accessCode": "ABCD-EFGH",
                "releaseId": "safe-id",
                "keystorePassword": "password",
            },
        }
    )

    assert sanitized == {
        "token": "[REDACTED]",
        "nested": {
            "accessCode": "[REDACTED]",
            "releaseId": "safe-id",
            "keystorePassword": "[REDACTED]",
        },
    }


def test_cleanup_operations_require_the_exact_destructive_target() -> None:
    release_id = "22222222-2222-4222-8222-222222222222"
    game_id = "33333333-3333-4333-8333-333333333333"
    job_id = "44444444-4444-4444-8444-444444444444"

    release_operation, release_target = match_high_impact_operation(
        "DELETE", f"/api/v1/admin/mobile-releases/{release_id}"
    )
    game_operation, game_target = match_high_impact_operation(
        "DELETE", f"/api/v1/admin/games/{game_id}/layout-data"
    )
    job_operation, job_target = match_high_impact_operation(
        "DELETE", f"/api/v1/admin/jobs/{job_id}"
    )
    local_reviewer_operation, local_reviewer_target = match_high_impact_operation(
        "POST", "/api/v1/admin/reviewer-local/start"
    )

    assert release_operation is not None
    assert release_operation.action == "delete-mobile-release"
    assert release_target == f"mobile-release:{release_id}"
    assert game_operation is not None
    assert game_operation.action == "reset-game-layout-data"
    assert game_target == f"game-layout-data:{game_id}"
    assert job_operation is not None
    assert job_operation.action == "delete-image-selection-job"
    assert job_target == f"job:{job_id}"
    assert local_reviewer_operation is not None
    assert local_reviewer_operation.action == "start-local-reviewer"
    assert local_reviewer_target == "local-reviewer"


def test_openapi_publishes_intent_and_exact_target_confirmation(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path), reviewer_ingress_service_dependency=_FakeIngress)
    operation = app.openapi()["paths"]["/api/v1/admin/reviewer-ingress/start"]["post"]
    parameters = {item["name"]: item for item in operation["parameters"]}

    security_scheme = app.openapi()["components"]["securitySchemes"]["LocalAdminIntent"]
    assert security_scheme == {
        "type": "apiKey",
        "in": "header",
        "name": "X-Admin-Intent",
        "description": "Fixed local-owner intent added by the loopback Admin client.",
    }
    assert operation["security"] == [{"LocalAdminIntent": []}]
    assert parameters["X-Admin-Confirmation"]["schema"]["const"] == "confirmed"
    assert parameters["X-Admin-Target"]["required"] is True
    assert "403" in operation["responses"]


def test_manual_image_upload_header_is_allowed_by_cors(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path), reviewer_ingress_service_dependency=_FakeIngress)

    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        response = client.options(
            (
                "/api/v1/admin/image-selections/"
                "11111111-1111-4111-8111-111111111111/groups/"
                "22222222-2222-4222-8222-222222222222/manual-file"
            ),
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": (
                    "content-type,x-admin-intent,x-admin-confirmation,"
                    "x-admin-target,x-image-file-name"
                ),
            },
        )

    assert response.status_code == 200
    allowed_headers = response.headers["access-control-allow-headers"].casefold()
    assert "x-image-file-name" in allowed_headers
