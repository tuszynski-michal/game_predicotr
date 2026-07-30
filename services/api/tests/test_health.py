from fastapi.testclient import TestClient
from game_predictor_api.config import ApiSettings
from game_predictor_api.main import create_app


def test_health_matches_the_accepted_contract() -> None:
    app = create_app(
        ApiSettings(
            host="127.0.0.1",
            port=8000,
            admin_origin="http://127.0.0.1:3000",
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_cors_allows_configured_local_admin_and_reviewer_origins() -> None:
    app = create_app(
        ApiSettings(
            host="127.0.0.1",
            port=8000,
            admin_origin="http://localhost:3000",
        )
    )

    with TestClient(app) as client:
        allowed = client.get(
            "/api/v1/health",
            headers={"Origin": "http://localhost:3000"},
        )
        reviewer = client.get(
            "/api/v1/health",
            headers={"Origin": "http://127.0.0.1:3001"},
        )
        remote = client.get(
            "/api/v1/health",
            headers={"Origin": "https://admin.example.com"},
        )

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert reviewer.headers["access-control-allow-origin"] == "http://127.0.0.1:3001"
    assert "access-control-allow-origin" not in remote.headers
