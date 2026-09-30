from datetime import UTC, datetime
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.application.board_search_share_access import (
    BoardSearchShareAccessService,
)
from game_predictor_api.application.reviewer_ingress import (
    ReviewerIngressError,
    ReviewerIngressStatus,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_search import BoardSearchError
from game_predictor_api.main import create_app
from game_predictor_api.storage.board_search_share_repository import (
    InMemoryBoardSearchShareRepository,
)

GAME_ID = UUID(int=7)
NOW = datetime(2099, 9, 30, 10, 0, tzinfo=UTC)
SESSIONS = "/api/v1/admin/board-search-shares/sessions"


class FakeIngress:
    def __init__(self, *, online: bool = True, start_fails: bool = False) -> None:
        self.online = online
        self.start_fails = start_fails
        self.start_count = 0
        self.status_fails = False

    def status(self) -> ReviewerIngressStatus:
        if self.status_fails:
            raise ReviewerIngressError(
                "REVIEWER_INGRESS_CONTROLLER_MISSING", "Synthetic status failure."
            )
        return ReviewerIngressStatus(
            state="running" if self.online else "stopped",
            public_origin="https://share.trycloudflare.com" if self.online else None,
            target="http://127.0.0.1:3001",
            started_at=NOW if self.online else None,
            reviewer_ready=self.online,
            instance_id=UUID(int=101) if self.online else None,
        )

    def start(self) -> ReviewerIngressStatus:
        self.start_count += 1
        if self.start_fails:
            raise ReviewerIngressError(
                "REVIEWER_INGRESS_COMMAND_FAILED", "Synthetic ingress failure."
            )
        self.online = True
        return self.status()


def _app(
    *,
    ingress: FakeIngress | None = None,
    readiness_error: Exception | None = None,
    enabled: bool = True,
) -> tuple[FastAPI, InMemoryBoardSearchShareRepository, FakeIngress]:
    repository = InMemoryBoardSearchShareRepository()

    def readiness(game_id: UUID) -> None:
        if readiness_error is not None:
            raise readiness_error

    service = BoardSearchShareAccessService(
        repository, readiness=readiness, enabled=enabled, now=lambda: NOW
    )
    resolved_ingress = ingress or FakeIngress()
    app = create_app(
        ApiSettings(host="127.0.0.1", port=8000, admin_origin="http://127.0.0.1:3000"),
        board_search_share_access_service_dependency=lambda: service,
        reviewer_ingress_service_dependency=lambda: resolved_ingress,
    )
    return app, repository, resolved_ingress


def test_create_returns_link_and_code_once_and_list_has_no_secrets() -> None:
    app, repository, ingress = _app(ingress=FakeIngress(online=False))
    with TestClient(app, base_url="https://testserver") as client:
        created = client.post(
            SESSIONS, json={"gameId": str(GAME_ID), "label": "Dla Ani", "lifetimeMinutes": 240}
        )
        listed = client.get(SESSIONS, params={"gameId": str(GAME_ID)})

    assert created.status_code == 201, created.text
    body = created.json()
    session_id = body["session"]["sessionId"]
    assert ingress.start_count == 1
    assert body["accessCode"].count("-") == 1 and len(body["accessCode"]) == 9
    assert body["session"]["status"] == "active"
    assert body["session"]["ready"] is True
    assert body["session"]["shareUrl"] == (
        f"https://share.trycloudflare.com/board-search?share={session_id}"
    )
    assert body["accessCode"] not in body["session"]["shareUrl"]
    assert listed.status_code == 200
    sessions = listed.json()["sessions"]
    assert [item["sessionId"] for item in sessions] == [session_id]
    assert body["accessCode"] not in listed.text
    for secret in ("codeHash", "codeSalt", "tokenHash", "accessCode", "accessToken"):
        assert secret not in listed.text
    assert len(repository.records) == 1


def test_default_lifetime_is_8_hours() -> None:
    app, _repository, _ingress = _app()
    with TestClient(app, base_url="https://testserver") as client:
        created = client.post(SESSIONS, json={"gameId": str(GAME_ID)})
    assert created.status_code == 201, created.text
    assert created.json()["session"]["expiresAt"].startswith("2099-09-30T18:00:00")


def test_invalid_lifetime_is_rejected_before_starting_the_ingress() -> None:
    app, repository, ingress = _app(ingress=FakeIngress(online=False))
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post(SESSIONS, json={"gameId": str(GAME_ID), "lifetimeMinutes": 1441})
    assert response.status_code == 422
    assert ingress.start_count == 0
    assert repository.records == {}


def test_a_game_without_ready_data_gets_409_and_the_ingress_stays_off() -> None:
    app, repository, ingress = _app(
        ingress=FakeIngress(online=False),
        readiness_error=BoardSearchError(
            "BOARD_SEARCH_PROJECTION_INCOMPLETE", "The projection is not ready."
        ),
    )
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post(SESSIONS, json={"gameId": str(GAME_ID)})
    assert response.status_code == 409
    assert response.json()["code"] == "BOARD_SEARCH_PROJECTION_INCOMPLETE"
    assert ingress.start_count == 0
    assert repository.records == {}


def test_unknown_game_is_404() -> None:
    app, _repository, _ingress = _app(
        readiness_error=BoardSearchError("GAME_NOT_FOUND", "The selected game does not exist.")
    )
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post(SESSIONS, json={"gameId": str(GAME_ID)})
    assert response.status_code == 404


def test_sixth_active_link_is_409_without_starting_the_ingress_again() -> None:
    app, _repository, ingress = _app()
    with TestClient(app, base_url="https://testserver") as client:
        for _ in range(5):
            assert client.post(SESSIONS, json={"gameId": str(GAME_ID)}).status_code == 201
        response = client.post(SESSIONS, json={"gameId": str(GAME_ID)})
    assert response.status_code == 409
    assert response.json()["code"] == "BOARD_SEARCH_SHARE_ACTIVE_LIMIT"
    assert ingress.start_count == 0


def test_ingress_failure_creates_no_session() -> None:
    app, repository, _ingress = _app(ingress=FakeIngress(online=False, start_fails=True))
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post(SESSIONS, json={"gameId": str(GAME_ID)})
    assert response.status_code >= 400
    assert repository.records == {}


def test_revoke_works_without_the_ingress_and_is_idempotent() -> None:
    app, _repository, ingress = _app()
    with TestClient(app, base_url="https://testserver") as client:
        session_id = client.post(SESSIONS, json={"gameId": str(GAME_ID)}).json()["session"][
            "sessionId"
        ]
        ingress.online = False
        first = client.post(f"{SESSIONS}/{session_id}/revoke")
        second = client.post(f"{SESSIONS}/{session_id}/revoke")
        missing = client.post(f"{SESSIONS}/{UUID(int=5)}/revoke")
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "revoked"
    assert first.json()["shareUrl"] is None
    assert second.json()["revokedAt"] == first.json()["revokedAt"]
    assert missing.status_code == 404
    assert missing.json()["code"] == "BOARD_SEARCH_SHARE_NOT_FOUND"


def test_disabled_sharing_is_503_for_create() -> None:
    app, _repository, ingress = _app(enabled=False, ingress=FakeIngress(online=False))
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post(SESSIONS, json={"gameId": str(GAME_ID)})
    assert response.status_code == 503
    assert response.json()["code"] == "BOARD_SEARCH_SHARE_DISABLED"
    assert ingress.start_count == 0


def test_share_flag_defaults_on_and_any_invalid_value_disables_it() -> None:
    assert ApiSettings.from_environment({}).board_search_share_enabled is True
    assert (
        ApiSettings.from_environment(
            {"GAME_PREDICTOR_BOARD_SEARCH_SHARE_ENABLED": "false"}
        ).board_search_share_enabled
        is False
    )
    for value in ("yes", "1", "", "TRUE "):
        expected = value.strip().lower() == "true"
        assert (
            ApiSettings.from_environment(
                {"GAME_PREDICTOR_BOARD_SEARCH_SHARE_ENABLED": value}
            ).board_search_share_enabled
            is expected
        )


def test_the_list_survives_an_unreadable_ingress_status_so_links_can_be_stopped() -> None:
    app, _repository, ingress = _app()
    with TestClient(app, base_url="https://testserver") as client:
        session_id = client.post(SESSIONS, json={"gameId": str(GAME_ID)}).json()["session"][
            "sessionId"
        ]
        ingress.status_fails = True
        listed = client.get(SESSIONS)
    assert listed.status_code == 200, listed.text
    [item] = listed.json()["sessions"]
    assert item["sessionId"] == session_id
    assert item["ready"] is False and item["shareUrl"] is None
