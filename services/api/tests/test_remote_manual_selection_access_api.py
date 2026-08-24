from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.application.remote_manual_selection_access import (
    REMOTE_SELECTION_COOKIE_NAME,
    REMOTE_SELECTION_PROXY_INTENT,
    RemoteManualSelectionAccessError,
    RemoteManualSelectionAccessService,
    RemoteManualSelectionBatchMonitorView,
)
from game_predictor_api.application.remote_manual_selection_host import (
    ConsumedRemoteManualSelectionBase,
)
from game_predictor_api.application.reviewer_ingress import (
    ReviewerIngressError,
    ReviewerIngressStatus,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.main import create_app
from game_predictor_api.storage.remote_manual_selection_access_repository import (
    InMemoryRemoteManualSelectionAccessRepository,
)


class FakeHostService:
    def __init__(self) -> None:
        self.used = False

    def consume_base_capability(self, capability: str) -> ConsumedRemoteManualSelectionBase:
        if self.used or capability != "x" * 32:
            raise RemoteManualSelectionAccessError(
                "REMOTE_SELECTION_BASE_CAPABILITY_INVALID",
                "The host base capability is invalid or expired.",
            )
        self.used = True
        return ConsumedRemoteManualSelectionBase(
            base_binding_id=UUID(int=99),
            host_base_path=Path(r"C:\private\owner\Documents"),
            display_name="Documents",
        )


class FakeIngress:
    def __init__(self) -> None:
        self.public_origin = "https://first.trycloudflare.com"
        self.online = True
        self.start_count = 0
        self.fail_status = False

    def status(self) -> ReviewerIngressStatus:
        if self.fail_status:
            raise ReviewerIngressError(
                "REVIEWER_INGRESS_COMMAND_FAILED",
                "Synthetic ingress status failure.",
            )
        return ReviewerIngressStatus(
            state="running" if self.online else "stopped",
            public_origin=self.public_origin if self.online else None,
            target="http://127.0.0.1:3001",
            started_at=(datetime(2026, 8, 24, 9, 0, tzinfo=UTC) if self.online else None),
            reviewer_ready=bool(self.online),
            instance_id=UUID(int=101) if self.online else None,
        )

    def start(self) -> ReviewerIngressStatus:
        self.start_count += 1
        self.online = True
        return self.status()


class FailingIngress(FakeIngress):
    def __init__(self) -> None:
        super().__init__()
        self.online = False

    def start(self) -> ReviewerIngressStatus:
        self.start_count += 1
        raise ReviewerIngressError(
            "REVIEWER_INGRESS_COMMAND_FAILED",
            "Synthetic ingress failure.",
        )


def _app(ingress: FakeIngress | None = None):
    repository = InMemoryRemoteManualSelectionAccessRepository()
    host = FakeHostService()
    service = RemoteManualSelectionAccessService(
        repository,
        host,
        now=lambda: datetime(2026, 8, 24, 10, 0, tzinfo=UTC),
    )
    ingress = ingress or FakeIngress()
    app = create_app(
        ApiSettings(
            host="127.0.0.1",
            port=8000,
            admin_origin="http://127.0.0.1:3000",
        ),
        remote_manual_selection_host_service_dependency=lambda: host,
        remote_manual_selection_access_service_dependency=lambda: service,
        reviewer_ingress_service_dependency=lambda: ingress,
    )
    return app, repository, ingress


def _create(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v1/admin/remote-manual-selections/sessions",
        json={"baseCapability": "x" * 32, "lifetimeMinutes": 60},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_with_label(client: TestClient, label: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/admin/remote-manual-selections/sessions",
        json={
            "baseCapability": "x" * 32,
            "label": label,
            "lifetimeMinutes": 60,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _unlock(client: TestClient, created: dict[str, object], client_id: UUID):
    session = created["session"]
    assert isinstance(session, dict)
    return client.post(
        f"/api/v1/remote-manual-selections/sessions/{session['sessionId']}/unlock",
        json={
            "accessCode": created["accessCode"],
            "clientInstanceId": str(client_id),
        },
        headers=_proxy_headers(),
    )


def _cookie(response) -> str:
    return response.cookies.get(REMOTE_SELECTION_COOKIE_NAME)


def _cookie_header(token: str) -> dict[str, str]:
    return {
        "Cookie": f"{REMOTE_SELECTION_COOKIE_NAME}={token}",
        **_proxy_headers(),
    }


def _proxy_headers() -> dict[str, str]:
    return {"X-Remote-Selection-Proxy": REMOTE_SELECTION_PROXY_INTENT}


def test_loopback_create_unlock_context_and_revoke_never_put_token_in_json() -> None:
    app, repository, ingress = _app()
    client_id = uuid4()
    with TestClient(app, base_url="https://testserver") as client:
        created = _create(client)
        session = created["session"]
        assert isinstance(session, dict)
        session_id = session["sessionId"]
        assert session["displayName"] == "Documents"
        assert session["ready"] is True
        assert session["reviewUrl"] == (
            f"{ingress.public_origin}/manual-selection?session={session_id}"
        )
        assert "hostBasePath" not in repr(created)
        assert "C:\\private" not in repr(created)

        listed = client.get("/api/v1/admin/remote-manual-selections/sessions")
        assert listed.status_code == 200
        serialized_list = repr(listed.json())
        assert created["accessCode"] not in serialized_list
        assert "token" not in serialized_list.casefold()
        assert "C:\\private" not in serialized_list

        unlocked = _unlock(client, created, client_id)
        assert unlocked.status_code == 200, unlocked.text
        assert "token" not in repr(unlocked.json()).casefold()
        cookie = unlocked.headers["set-cookie"]
        assert "HttpOnly" in cookie
        assert "Secure" in cookie
        assert "SameSite=strict" in cookie
        assert "Path=/selection-api" in cookie
        access_token = _cookie(unlocked)
        assert access_token
        assert access_token not in repr(unlocked.json())

        context = client.get(
            "/api/v1/remote-manual-selections/context",
            headers={
                **_cookie_header(access_token),
                "X-Remote-Selection-Client": str(client_id),
            },
        )
        assert context.status_code == 200, context.text
        assert context.json()["sessionId"] == session_id
        assert context.json()["isWriter"] is True
        assert "gameId" not in context.json()
        assert "importJobId" not in context.json()

        revoked = client.post(
            f"/api/v1/admin/remote-manual-selections/sessions/{session_id}/revoke"
        )
        assert revoked.status_code == 200
        assert revoked.json()["status"] == "revoked"
        denied = client.get(
            "/api/v1/remote-manual-selections/context",
            headers={
                **_cookie_header(access_token),
                "X-Remote-Selection-Client": str(client_id),
            },
        )
        assert denied.status_code == 401
        assert denied.json()["code"] == "REMOTE_SELECTION_TOKEN_INVALID"

    record = next(iter(repository.records.values()))
    assert record.token_hash is None
    assert record.writer_lease_token is None


def test_unlock_lockout_survives_http_errors_and_code_is_not_in_error() -> None:
    app, repository, _ingress = _app()
    client_id = uuid4()
    with TestClient(app, base_url="https://testserver") as client:
        created = _create(client)
        session = created["session"]
        assert isinstance(session, dict)
        session_id = session["sessionId"]
        for attempt in range(1, 6):
            response = client.post(
                f"/api/v1/remote-manual-selections/sessions/{session_id}/unlock",
                json={"accessCode": "WRONG-CODE", "clientInstanceId": str(client_id)},
                headers=_proxy_headers(),
            )
            assert response.status_code == 401
            expected = (
                "REMOTE_SELECTION_SESSION_LOCKED"
                if attempt == 5
                else "REMOTE_SELECTION_ACCESS_CODE_INVALID"
            )
            assert response.json()["code"] == expected
            assert "WRONG-CODE" not in response.text
        correct = _unlock(client, created, client_id)
        assert correct.status_code == 401
        assert correct.json()["code"] == "REMOTE_SELECTION_SESSION_LOCKED"

    record = next(iter(repository.records.values()))
    assert record.failed_attempts == 5
    assert record.locked_at is not None


def test_context_requires_cookie_and_writer_mutations_reject_session_substitution() -> None:
    app, _repository, _ingress = _app()
    client_id = uuid4()
    with TestClient(app, base_url="https://testserver") as client:
        created = _create(client)
        unlocked = _unlock(client, created, client_id)
        assert unlocked.status_code == 200
        access_token = _cookie(unlocked)
        assert access_token

        missing = client.get(
            "/api/v1/remote-manual-selections/context",
            headers={
                **_proxy_headers(),
                "X-Remote-Selection-Client": str(client_id),
            },
        )
        assert missing.status_code == 401
        assert missing.json()["code"] == "REMOTE_SELECTION_TOKEN_REQUIRED"

        foreign_session = uuid4()
        substituted = client.post(
            f"/api/v1/remote-manual-selections/sessions/{foreign_session}/writer-lease/heartbeat",
            json={"clientInstanceId": str(client_id)},
            headers=_cookie_header(access_token),
        )
        assert substituted.status_code == 401
        assert substituted.json()["code"] == "REMOTE_SELECTION_TOKEN_INVALID"


def test_openapi_contract_has_cookie_transport_and_no_access_token_response_field() -> None:
    app, _repository, _ingress = _app()
    schema = app.openapi()
    paths = schema["paths"]
    assert "/api/v1/admin/remote-manual-selections/sessions" in paths
    assert "/api/v1/remote-manual-selections/sessions/{session_id}/unlock" in paths
    assert "/api/v1/remote-manual-selections/context" in paths
    serialized = repr(
        {
            key: value
            for key, value in schema["components"]["schemas"].items()
            if key.startswith("RemoteManualSelection")
        }
    ).casefold()
    assert "access_token" not in serialized
    assert "accesstoken" not in serialized
    assert "host_base_path" not in serialized
    assert "hostbasepath" not in serialized
    context_parameters = paths["/api/v1/remote-manual-selections/context"]["get"]["parameters"]
    assert any(
        item["in"] == "cookie" and item["name"] == REMOTE_SELECTION_COOKIE_NAME
        for item in context_parameters
    )
    assert any(
        item["in"] == "header"
        and item["name"] == "X-Remote-Selection-Proxy"
        and item["required"] is False
        for item in context_parameters
    )
    create_parameters = {
        item["name"]
        for item in paths["/api/v1/admin/remote-manual-selections/sessions"]["post"]["parameters"]
    }
    assert {"X-Admin-Confirmation", "X-Admin-Target"} <= create_parameters


def test_public_routes_require_the_fixed_reviewer_proxy_intent() -> None:
    app, _repository, _ingress = _app()
    with TestClient(app, base_url="https://testserver") as client:
        missing = client.get("/api/v1/remote-manual-selections/context")
        wrong = client.get(
            "/api/v1/remote-manual-selections/context",
            headers={"X-Remote-Selection-Proxy": "legacy-reviewer"},
        )
    assert missing.status_code == 403
    assert missing.json()["code"] == "REMOTE_SELECTION_PROXY_REQUIRED"
    assert wrong.status_code == 403
    assert wrong.json()["code"] == "REMOTE_SELECTION_PROXY_REQUIRED"


def test_session_url_tracks_restarted_shared_ingress_without_new_session() -> None:
    app, _repository, ingress = _app()
    with TestClient(app, base_url="https://testserver") as client:
        created = _create(client)
        session = created["session"]
        assert isinstance(session, dict)
        session_id = session["sessionId"]
        ingress.public_origin = "https://second.trycloudflare.com"

        refreshed = client.get(f"/api/v1/admin/remote-manual-selections/sessions/{session_id}")

    assert refreshed.status_code == 200
    assert refreshed.json()["session"]["sessionId"] == session_id
    assert refreshed.json()["session"]["reviewUrl"] == (
        f"{ingress.public_origin}/manual-selection?session={session_id}"
    )
    assert ingress.start_count == 0


def test_host_monitor_is_bounded_and_exposes_counts_without_path_or_secret() -> None:
    app, repository, _ingress = _app()
    with TestClient(app, base_url="https://testserver") as client:
        created = _create_with_label(client, "  Nocna   partia  ")
        session = created["session"]
        assert isinstance(session, dict)
        session_id = UUID(str(session["sessionId"]))
        repository.batch_monitors[session_id] = [
            RemoteManualSelectionBatchMonitorView(
                batch_id=UUID(int=index + 1),
                name=f"Partia {index + 1}",
                status="active",
                total_file_count=100,
                selected_file_count=25,
                synced_file_count=20,
                failed_file_count=1,
                pending_host_action_count=2,
                last_error_codes=("REMOTE_SELECTION_SYNTHETIC_FAILURE",),
            )
            for index in range(3)
        ]

        monitored = client.get(
            f"/api/v1/admin/remote-manual-selections/sessions/{session_id}",
            params={"batch_limit": 2},
        )

    assert monitored.status_code == 200, monitored.text
    payload = monitored.json()
    assert payload["session"]["displayName"] == "Nocna partia"
    assert payload["hasMoreBatches"] is True
    assert len(payload["batches"]) == 2
    assert payload["batches"][0]["syncedFileCount"] == 20
    assert payload["batches"][0]["lastErrorCodes"] == ["REMOTE_SELECTION_SYNTHETIC_FAILURE"]
    serialized = repr(payload).casefold()
    assert created["accessCode"].casefold() not in serialized
    assert "c:\\private" not in serialized
    assert "hostbasepath" not in serialized


def test_create_reuses_warm_ingress_and_starts_only_a_missing_shared_ingress() -> None:
    warm_app, _warm_repository, warm_ingress = _app()
    with TestClient(warm_app, base_url="https://testserver") as client:
        _create(client)
    assert warm_ingress.start_count == 0

    cold_ingress = FakeIngress()
    cold_ingress.online = False
    cold_app, _cold_repository, _ = _app(cold_ingress)
    with TestClient(cold_app, base_url="https://testserver") as client:
        created = _create(client)
    assert created["session"]["ready"] is True
    assert cold_ingress.start_count == 1


def test_ingress_failure_does_not_consume_the_one_time_base_capability() -> None:
    ingress = FailingIngress()
    app, repository, _ = _app(ingress)
    with TestClient(app, base_url="https://testserver") as client:
        failed = client.post(
            "/api/v1/admin/remote-manual-selections/sessions",
            json={"baseCapability": "x" * 32, "lifetimeMinutes": 60},
        )
    assert failed.status_code == 503
    assert failed.json()["code"] == "REVIEWER_INGRESS_COMMAND_FAILED"
    assert repository.records == {}


def test_revocation_succeeds_even_when_shared_ingress_status_is_unavailable() -> None:
    app, repository, ingress = _app()
    with TestClient(app, base_url="https://testserver") as client:
        created = _create(client)
        session = created["session"]
        assert isinstance(session, dict)
        ingress.fail_status = True

        revoked = client.post(
            f"/api/v1/admin/remote-manual-selections/sessions/{session['sessionId']}/revoke"
        )

    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert revoked.json()["ready"] is False
    assert revoked.json()["reviewUrl"] is None
    record = next(iter(repository.records.values()))
    assert record.revoked_at is not None
    assert record.token_hash is None
