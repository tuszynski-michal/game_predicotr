from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.reviewer_access import (
    ReviewerAccessError,
    ReviewerAccessService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.main import create_app


def test_session_uses_separate_code_and_scope() -> None:
    game_id = uuid4()
    import_job_id = uuid4()
    service = ReviewerAccessService("http://127.0.0.1:3001")

    created = service.create(
        game_id=game_id,
        import_job_id=import_job_id,
        lifetime_minutes=60,
    )

    assert str(created.session.id) in created.review_url
    assert created.code not in created.review_url
    assert len(created.code) == 9
    assert created.session.code_hash != created.code.encode()
    assert service.unlock(created.session.id, created.code).game_id == game_id
    with pytest.raises(ReviewerAccessError, match="invalid"):
        service.unlock(created.session.id, "WRONG-CODE")


def test_expired_session_fails_closed() -> None:
    now = datetime(2026, 7, 29, 10, 0, tzinfo=UTC)
    current = now
    service = ReviewerAccessService(
        "http://127.0.0.1:3001",
        now=lambda: current,
    )
    created = service.create(
        game_id=uuid4(),
        import_job_id=uuid4(),
        lifetime_minutes=5,
    )
    current = now + timedelta(minutes=6)

    with pytest.raises(ReviewerAccessError, match="expired"):
        service.unlock(created.session.id, created.code)


def test_http_create_and_unlock_do_not_put_code_in_link() -> None:
    app = create_app(
        ApiSettings(
            host="127.0.0.1",
            port=8000,
            admin_origin="http://127.0.0.1:3000",
        )
    )
    game_id = str(uuid4())
    import_job_id = str(uuid4())

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/admin/reviewer-sessions",
            json={
                "gameId": game_id,
                "importJobId": import_job_id,
                "lifetimeMinutes": 60,
            },
        )
        assert created.status_code == 201
        body = created.json()
        assert body["accessCode"] not in body["reviewUrl"]

        wrong = client.post(
            f"/api/v1/reviewer/sessions/{body['sessionId']}/unlock",
            json={"accessCode": "WRONG-CODE"},
        )
        assert wrong.status_code == 401
        assert wrong.json()["code"] == "REVIEWER_ACCESS_CODE_INVALID"

        unlocked = client.post(
            f"/api/v1/reviewer/sessions/{body['sessionId']}/unlock",
            json={"accessCode": body["accessCode"]},
        )
        assert unlocked.status_code == 200
        assert unlocked.json()["gameId"] == game_id
        assert unlocked.json()["importJobId"] == import_job_id
