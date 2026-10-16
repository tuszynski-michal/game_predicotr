from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.board_search_panels import (
    PANEL_COOKIE,
    PANEL_PROXY_HEADER,
    PANEL_PROXY_INTENT,
    BoardSearchPanelService,
    panel_child_token,
)
from game_predictor_api.application.board_search_share_access import BoardSearchShareAccessService
from game_predictor_api.application.reviewer_ingress import ReviewerIngressStatus
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_search_shares import (
    BoardSearchShareAuthenticationError,
    BoardSearchShareConflictError,
    BoardSearchShareError,
)
from game_predictor_api.main import create_app
from game_predictor_api.storage.board_search_panels import InMemoryBoardSearchPanelRepository
from game_predictor_api.storage.board_search_share_repository import (
    InMemoryBoardSearchShareRepository,
)

NOW = datetime(2099, 1, 1, tzinfo=UTC)
GAMES = [UUID(int=7), UUID(int=8)]


def test_local_admin_panel_actions_require_their_own_confirmed_targets():
    from game_predictor_api.security.local_admin import match_high_impact_operation

    operation, target = match_high_impact_operation("POST", "/api/v1/admin/board-search-panels")
    assert operation is not None and operation.action == "create-board-search-panel"
    assert target == "board-search-panel:new"
    panel_id = uuid4()
    operation, target = match_high_impact_operation(
        "POST", f"/api/v1/admin/board-search-panels/{panel_id}/revoke"
    )
    assert operation is not None and operation.action == "revoke-board-search-panel"
    assert target == f"board-search-panel:{panel_id}"


def setup():
    shares = InMemoryBoardSearchShareRepository()
    panels = InMemoryBoardSearchPanelRepository(shares, {GAMES[0]: "777", GAMES[1]: "Mumie"})
    clock = [NOW]
    checked = []

    def readiness(game_id):
        checked.append(game_id)
        if game_id not in GAMES:
            raise BoardSearchShareError("BOARD_SEARCH_PANEL_GAME_UNAVAILABLE", "Unavailable")

    service = BoardSearchPanelService(
        panels, shares, readiness=readiness, enabled=True, now=lambda: clock[0]
    )
    access = BoardSearchShareAccessService(
        shares, readiness=readiness, enabled=True, now=lambda: clock[0]
    )
    return service, access, panels, shares, clock, checked


def test_group_keeps_distinct_game_contexts_and_counts_once():
    service, access, panels, shares, _clock, _checked = setup()
    created = service.create(
        game_ids=list(reversed(GAMES)), lifetime_minutes=4320, label=" Rodzina "
    )
    assert created.panel.status == "active"
    assert created.panel.expires_at == NOW + timedelta(hours=72)
    assert [g.game_id for g in created.panel.games] == GAMES
    assert created.link_key not in repr(panels.records)
    assert created.link_key not in repr(shares.audit_events)
    assert shares.count_active_sessions(NOW) == 1
    assert access.list_sessions() == ()
    for game in created.panel.games:
        token = panel_child_token(created.link_key, created.panel.panel_id, game.session_id)
        assert access.authenticate(token).game_id == game.game_id
        assert service.authenticate(created.panel.panel_id, created.link_key) == created.panel
        # Opening again never rotates either game's credential.
        assert access.authenticate(token).session_id == game.session_id
        with pytest.raises(BoardSearchShareAuthenticationError):
            access.unlock(session_id=game.session_id, access_code="AAAA-AAAA")
        assert shares.records[game.session_id].failed_attempts == 0
        with pytest.raises(BoardSearchShareConflictError):
            access.revoke(game.session_id)
    with pytest.raises(BoardSearchShareAuthenticationError):
        access.authenticate(
            panel_child_token(created.link_key, uuid4(), created.panel.games[0].session_id)
        )


@pytest.mark.parametrize("ids", [[], [GAMES[0], GAMES[0]], [uuid4()]])
def test_invalid_games_do_not_write(ids):
    service, _access, panels, shares, _clock, _checked = setup()
    with pytest.raises(BoardSearchShareError):
        service.create(game_ids=ids, lifetime_minutes=60, label=None)
    assert not panels.records and not shares.records


def test_revoke_and_expiry_stop_all_games_and_legacy_limit_is_shared():
    service, access, _panels, shares, clock, _checked = setup()
    created = service.create(game_ids=GAMES, lifetime_minutes=60, label=None)
    token = panel_child_token(
        created.link_key, created.panel.panel_id, created.panel.games[0].session_id
    )
    for _ in range(4):
        access.create(game_id=GAMES[0], lifetime_minutes=60, label=None)
    with pytest.raises(BoardSearchShareConflictError):
        service.create(game_ids=GAMES, lifetime_minutes=60, label=None)
    service.revoke(created.panel.panel_id)
    assert service.revoke(created.panel.panel_id).status == "revoked"
    assert shares.count_active_sessions(clock[0]) == 4
    with pytest.raises(BoardSearchShareAuthenticationError):
        access.authenticate(token)
    with pytest.raises(BoardSearchShareAuthenticationError):
        service.authenticate(created.panel.panel_id, created.link_key)
    another = service.create(game_ids=GAMES, lifetime_minutes=60, label=None)
    clock[0] += timedelta(hours=1)
    with pytest.raises(BoardSearchShareAuthenticationError):
        service.authenticate(another.panel.panel_id, another.link_key)
    assert shares.count_active_sessions(clock[0]) == 0


def test_http_link_open_context_has_no_secret_and_cookie_is_separate():
    service, access, _panels, _shares, _clock, _checked = setup()

    class Ingress:
        def status(self):
            return ReviewerIngressStatus(
                state="running",
                public_origin="https://share.trycloudflare.com",
                target="http://127.0.0.1:3001",
                started_at=NOW,
                reviewer_ready=True,
                instance_id=uuid4(),
            )

    app = create_app(
        ApiSettings(host="127.0.0.1", port=8000, admin_origin="http://127.0.0.1:3000"),
        board_search_panel_service_dependency=lambda: service,
        board_search_share_access_service_dependency=lambda: access,
        reviewer_ingress_service_dependency=lambda: Ingress(),
    )
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post(
            "/api/v1/admin/board-search-panels", json={"gameIds": [str(g) for g in GAMES]}
        )
        assert response.status_code == 201, response.text
        created = response.json()
        panel_id, secret = created["panel"]["panelId"], created["linkKey"]
        assert secret not in client.get("/api/v1/admin/board-search-panels").text
        path = f"/api/v1/board-search-panels/{panel_id}"
        assert client.post(path + "/open", json={"linkKey": secret}).status_code == 403
        headers = {PANEL_PROXY_HEADER: PANEL_PROXY_INTENT}
        opened = client.post(path + "/open", json={"linkKey": secret}, headers=headers)
        assert opened.status_code == 200, opened.text
        assert secret not in opened.text and "gameId" not in opened.text
        cookie = opened.headers["set-cookie"]
        assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
        assert "Path=/board-search-panel-api" in cookie
        # Backend API tests send the translated cookie explicitly (browser's path is the proxy).
        headers["cookie"] = f"{PANEL_COOKIE}={panel_id}.{secret}"
        assert client.get(path + "/context", headers=headers).status_code == 200
        headers["cookie"] = f"{PANEL_COOKIE}={uuid4()}.{secret}"
        assert client.get(path + "/context", headers=headers).status_code == 401
        stopped = client.post(f"/api/v1/admin/board-search-panels/{panel_id}/revoke")
        assert stopped.status_code == 200, stopped.text


def test_create_never_acknowledges_before_the_transaction_commits():
    service, access, _panels, _shares, _clock, _checked = setup()

    def failed_commit():
        yield service
        raise RuntimeError("Simulated commit failure")

    class Ingress:
        def status(self):
            return ReviewerIngressStatus(
                state="running",
                public_origin="https://share.trycloudflare.com",
                target="http://127.0.0.1:3001",
                started_at=NOW,
                reviewer_ready=True,
                instance_id=uuid4(),
            )

    app = create_app(
        ApiSettings(host="127.0.0.1", port=8000, admin_origin="http://127.0.0.1:3000"),
        board_search_panel_service_dependency=failed_commit,
        board_search_share_access_service_dependency=lambda: access,
        reviewer_ingress_service_dependency=lambda: Ingress(),
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/admin/board-search-panels", json={"gameIds": [str(g) for g in GAMES]}
        )
        assert response.status_code == 500
        assert "linkKey" not in response.text
