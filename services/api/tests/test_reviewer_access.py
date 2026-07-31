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
    unlocked = service.unlock(created.session.id, created.code)
    assert unlocked.session.game_id == game_id
    assert service.authenticate(unlocked.access_token).import_job_id == import_job_id
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
    service = ReviewerAccessService("http://127.0.0.1:3001")
    app = create_app(
        ApiSettings(
            host="127.0.0.1",
            port=8000,
            admin_origin="http://127.0.0.1:3000",
        ),
        reviewer_access_service_dependency=lambda: service,
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
        assert len(unlocked.json()["accessToken"]) >= 32


def test_five_failed_attempts_lock_session_and_revoke_invalidates_token() -> None:
    service = ReviewerAccessService("http://127.0.0.1:3001")
    created = service.create(
        game_id=uuid4(),
        import_job_id=uuid4(),
        lifetime_minutes=60,
    )

    for _attempt in range(4):
        with pytest.raises(ReviewerAccessError) as error:
            service.unlock(created.session.id, "WRONG-CODE")
        assert error.value.code == "REVIEWER_ACCESS_CODE_INVALID"
    with pytest.raises(ReviewerAccessError) as locked:
        service.unlock(created.session.id, "WRONG-CODE")
    assert locked.value.code == "REVIEWER_SESSION_LOCKED"
    with pytest.raises(ReviewerAccessError) as still_locked:
        service.unlock(created.session.id, created.code)
    assert still_locked.value.code == "REVIEWER_SESSION_LOCKED"

    second = service.create(
        game_id=uuid4(),
        import_job_id=uuid4(),
        lifetime_minutes=60,
    )
    second_unlock = service.unlock(second.session.id, second.code)
    service.revoke(second.session.id)
    with pytest.raises(ReviewerAccessError) as revoked:
        service.authenticate(second_unlock.access_token)
    assert revoked.value.code in {"REVIEWER_SESSION_REVOKED", "REVIEWER_TOKEN_INVALID"}


def test_token_cannot_be_used_outside_session_scope() -> None:
    service = ReviewerAccessService("http://127.0.0.1:3001")
    created = service.create(
        game_id=uuid4(),
        import_job_id=uuid4(),
        lifetime_minutes=60,
    )
    unlocked = service.unlock(created.session.id, created.code)
    session = service.authenticate(unlocked.access_token)

    with pytest.raises(ReviewerAccessError) as forbidden:
        service.authorize_scope(
            session,
            game_id=uuid4(),
            import_job_id=session.import_job_id,
        )
    assert forbidden.value.code == "REVIEWER_SCOPE_FORBIDDEN"
