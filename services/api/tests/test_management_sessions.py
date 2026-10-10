"""Purpose isolation, exact session identities, immutable public payloads and code lockout."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from game_predictor_api.application.management_access import ManagementAccessService
from game_predictor_api.domain.management import ManagementError
from game_predictor_api.domain.management_sessions import ManagementAccessError
from game_predictor_api.schemas.management_public import public_payload


class MemorySessions:
    def __init__(self):
        self.records = {}
        self.events = []

    def lock_ingress(self):
        pass

    def get(self, session_id, *, lock=False):
        return self.records.get(session_id)

    def find_token(self, token_hash):
        return next((item for item in self.records.values() if item.token_hash == token_hash), None)

    def save(self, record):
        self.records[record.id] = record

    def list(self, limit):
        return tuple(self.records.values())[:limit]

    def audit(self, record, event, at):
        self.events.append((record.id, event, at))


def test_local_link_http_confirmation_scope_and_secret_free_listing(tmp_path):
    from fastapi.testclient import TestClient
    from game_predictor_api.application.reviewer_ingress import ReviewerIngressStatus
    from game_predictor_api.config import ApiSettings
    from game_predictor_api.main import create_app

    class ReadyIngress:
        def status(self):
            return ReviewerIngressStatus(
                "running",
                "https://mock.trycloudflare.com",
                "http://127.0.0.1:3001",
                datetime.now(UTC),
                True,
                uuid4(),
            )

        def start(self):
            raise AssertionError("A ready mock must not start anything")

    service = ManagementAccessService(MemorySessions())
    app = create_app(
        ApiSettings(
            host="127.0.0.1",
            port=8000,
            admin_origin="http://127.0.0.1:3000",
            artifact_root=tmp_path,
            import_root=tmp_path,
        ),
        management_access_service_dependency=lambda: service,
        reviewer_ingress_service_dependency=lambda: ReadyIngress(),
    )
    base = "/api/v1/admin/management/sessions"
    headers = {
        "X-Admin-Intent": "local-owner",
        "X-Admin-Confirmation": "confirmed",
        "X-Admin-Target": "management-session:new",
    }
    try:
        with TestClient(app, client=("127.0.0.1", 43210)) as client:
            assert client.post(base, json={"label": "Recipient"}).status_code == 403
            assert (
                client.post(
                    base,
                    json={"label": "Recipient"},
                    headers={**headers, "X-Admin-Target": "other"},
                ).status_code
                == 403
            )
            response = client.post(
                base, json={"label": "Recipient", "lifetimeMinutes": 4320}, headers=headers
            )
            assert response.status_code == 201, response.text
            created = response.json()
            session_id = created["session"]["sessionId"]
            assert (
                created["session"]["shareUrl"]
                == f"https://mock.trycloudflare.com/management?share={session_id}"
            )
            listed = client.get(base, headers={"X-Admin-Intent": "local-owner"})
            assert listed.status_code == 200
            assert created["accessCode"] not in listed.text and "codeHash" not in listed.text
            revoked = client.post(
                f"{base}/{session_id}/revoke",
                headers={**headers, "X-Admin-Target": f"management-session:{session_id}"},
            )
            assert revoked.status_code == 200 and revoked.json()["status"] == "revoked"
    finally:
        app.state.database_engine.dispose()


@pytest.mark.parametrize("minutes", [60, 240, 480, 1440, 2880, 4320])
def test_independent_panel_lifetimes_and_matching_identity(minutes):
    now = datetime.now(UTC)
    repository = MemorySessions()
    service = ManagementAccessService(repository, now=lambda: now)
    record, code = service.create("  Named   recipient  ", minutes)
    assert record.label == "Named recipient"
    assert record.expires_at == now + timedelta(minutes=minutes)
    assert code not in repr(record)
    record, token = service.unlock(record.id, code)
    assert token not in repr(record)
    assert service.authenticate(token, record.id).id == record.id
    with pytest.raises(ManagementAccessError):
        service.authenticate(token, uuid4())
    assert record.actor == f"management-share:{record.id}:Named recipient"
    service.revoke(record.id)
    with pytest.raises(ManagementAccessError):
        service.authenticate(token, record.id)


def test_five_bad_codes_persist_lock_and_destroy_previous_token():
    repository = MemorySessions()
    service = ManagementAccessService(repository)
    record, code = service.create("Same label", 480)
    record, token = service.unlock(record.id, code)
    other, _ = service.create("Same label", 480)
    assert record.actor != other.actor
    for attempt in range(1, 6):
        with pytest.raises(ManagementAccessError) as error:
            service.unlock(record.id, "wrong")
        assert repository.get(record.id).failed_attempts == attempt
        assert error.value.code == (
            "MANAGEMENT_CODE_LOCKED" if attempt == 5 else "MANAGEMENT_CODE_INVALID"
        )
    assert repository.get(record.id).token_hash is None
    with pytest.raises(ManagementAccessError):
        service.authenticate(token, record.id)
    with pytest.raises(ManagementAccessError):
        service.unlock(record.id, code)
    assert repository.events[-1][1] == "locked"


def test_rotation_expiry_and_disabled_do_not_widen_old_sessions():
    repository = MemorySessions()
    now = datetime.now(UTC)
    service = ManagementAccessService(repository, now=lambda: now)
    record, code = service.create("Recipient", 60)
    _, old = service.unlock(record.id, code)
    _, current = service.unlock(record.id, code)
    with pytest.raises(ManagementAccessError):
        service.authenticate(old, record.id)
    service.authenticate(current, record.id)
    now += timedelta(hours=1)
    with pytest.raises(ManagementAccessError):
        service.authenticate(current, record.id)
    service.enabled = False
    assert service.list()
    service.revoke(record.id)
    with pytest.raises(ManagementAccessError):
        service.create("Recipient", 480)
    assert not issubclass(ManagementAccessError, ManagementError)


@pytest.mark.parametrize(
    "bad",
    [
        {"rulesSnapshot": {"symbols": [{"imagePath": "private.jpg"}]}},
        {"after": {"cellReviewId": str(uuid4())}},
        {"rulesSnapshot": {"description": "C:\\private\\secret.json"}},
        {"before": {"tokenHash": "a" * 64}},
    ],
)
def test_complete_frozen_history_rejects_paths_ids_and_secrets(bad):
    with pytest.raises(ManagementAccessError):
        public_payload(bad)
    assert public_payload({"name": "C:\\Display name", "rows": [[1, 2, 3]]})


def test_published_frozen_numeric_snapshot_is_public_safe():
    from game_predictor_api.application.board_search_approximate_win import (
        BoardSearchApproximateWinService,
    )
    from game_predictor_api.schemas.board_search_approximate_win import to_approximate_win_response
    from game_predictor_api.storage.management_result_snapshots import freeze_result
    from test_board_search_approximate_win_api import (
        _GAME_ID,
        MemoryBoardSearchApproximateWinRepository,
        _configuration,
        _document,
    )

    config = _configuration()
    calculation = to_approximate_win_response(
        BoardSearchApproximateWinService(
            MemoryBoardSearchApproximateWinRepository(
                _GAME_ID,
                sequence_length=8,
                configuration=config,
                documents=(_document(3, (1,) * 15),),
            )
        ).calculate(game_id=_GAME_ID, start_sequence_number=1, requested_spin_count=3)
    )
    _, payload, _ = freeze_result(calculation, config, ("A",) * 15, "a" * 64)
    assert public_payload(payload) == payload


def test_old_shares_accept_72h_without_rewriting_scope_or_expiry():
    from game_predictor_api.domain.board_search_shares import validate_board_search_share_lifetime
    from game_predictor_api.schemas.board_search_shares import BoardSearchShareCreate

    assert validate_board_search_share_lifetime(4320) == 4320
    assert BoardSearchShareCreate(gameId=uuid4(), lifetimeMinutes=2880).lifetime_minutes == 2880
