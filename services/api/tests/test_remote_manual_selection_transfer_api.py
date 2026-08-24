from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient
from game_predictor_api.application.remote_manual_selection_access import (
    REMOTE_SELECTION_COOKIE_NAME,
    REMOTE_SELECTION_PROXY_INTENT,
)
from game_predictor_api.application.remote_manual_selection_transfer import (
    RemoteManualSelectionTransferLimitError,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionTransferStatus,
    RemoteManualSelectionTransferV1,
)
from game_predictor_api.main import create_app
from game_predictor_api.storage.remote_manual_selection_repository import (
    RemoteManualSelectionTransferRecord,
)

SESSION_ID = UUID("11111111-1111-4111-8111-111111111111")
BATCH_ID = UUID("22222222-2222-4222-8222-222222222222")
FILE_ID = UUID("33333333-3333-4333-8333-333333333333")
CLIENT_ID = UUID("44444444-4444-4444-8444-444444444444")
TRANSFER_ID = UUID("55555555-5555-4555-8555-555555555555")


class FakeTransferService:
    def __init__(self) -> None:
        self.received = b""
        self.record: RemoteManualSelectionTransferRecord | None = None

    def status(self, **_kwargs: object) -> RemoteManualSelectionTransferRecord | None:
        return self.record

    async def upload(self, *, chunks, declared_bytes: int, **_kwargs: object):
        self.received = b"".join([chunk async for chunk in chunks])
        assert declared_bytes == len(self.received)
        transfer = RemoteManualSelectionTransferV1(
            id=TRANSFER_ID,
            session_id=SESSION_ID,
            batch_id=BATCH_ID,
            file_id=FILE_ID,
            generation=1,
            attempt=1,
            declared_bytes=declared_bytes,
            received_bytes=declared_bytes,
            status=RemoteManualSelectionTransferStatus.VERIFIED,
            declared_checksum_sha256="a" * 64,
            verified_checksum_sha256="a" * 64,
        )
        self.record = RemoteManualSelectionTransferRecord(
            transfer,
            ".game-predictor/private.verified",
        )
        return self.record


class RejectingTransferService(FakeTransferService):
    async def upload(self, **_kwargs: object):
        raise RemoteManualSelectionTransferLimitError(
            "REMOTE_SELECTION_TRANSFER_TOO_LARGE",
            "too large",
        )


def test_streaming_put_and_status_expose_no_host_path() -> None:
    service = FakeTransferService()
    app = _app(service)
    with TestClient(app, base_url="https://testserver") as client:
        before = client.get(
            _status_url(),
            headers=_headers(),
        )
        assert before.status_code == 200, before.text
        assert before.json()["status"] == "not_started"

        uploaded = client.put(
            _content_url(),
            content=b"jpeg-bytes",
            headers={
                **_headers(),
                "Content-Type": "application/octet-stream",
                "X-Remote-Selection-Transfer-Id": str(TRANSFER_ID),
                "X-Remote-Selection-Generation": "1",
                "X-Remote-Selection-Source-Mtime": "123",
                "X-Remote-Selection-Checksum-Sha256": "a" * 64,
            },
        )
        assert uploaded.status_code == 200, uploaded.text
        assert uploaded.json()["status"] == "verified"
        assert "game-predictor" not in uploaded.text
        assert service.received == b"jpeg-bytes"

        after = client.get(_status_url(), headers=_headers())
        assert after.json()["transferId"] == str(TRANSFER_ID)


def test_transfer_limit_maps_to_stable_413() -> None:
    with TestClient(_app(RejectingTransferService()), base_url="https://testserver") as client:
        response = client.put(
            _content_url(),
            content=b"x",
            headers={
                **_headers(),
                "Content-Type": "application/octet-stream",
                "X-Remote-Selection-Transfer-Id": str(TRANSFER_ID),
                "X-Remote-Selection-Generation": "1",
                "X-Remote-Selection-Source-Mtime": "123",
                "X-Remote-Selection-Checksum-Sha256": "a" * 64,
            },
        )
    assert response.status_code == 413
    assert response.json()["code"] == "REMOTE_SELECTION_TRANSFER_TOO_LARGE"


def _app(service: FakeTransferService):
    return create_app(
        ApiSettings(
            host="127.0.0.1",
            port=8000,
            admin_origin="http://127.0.0.1:3000",
        ),
        remote_manual_selection_transfer_service_dependency=lambda: service,
    )


def _headers() -> dict[str, str]:
    return {
        "Cookie": f"{REMOTE_SELECTION_COOKIE_NAME}=token",
        "X-Remote-Selection-Client": str(CLIENT_ID),
        "X-Remote-Selection-Proxy": REMOTE_SELECTION_PROXY_INTENT,
    }


def _status_url() -> str:
    return (
        f"/api/v1/remote-manual-selections/batches/{BATCH_ID}/files/{FILE_ID}/transfer"
        f"?generation=1&transferId={TRANSFER_ID}"
    )


def _content_url() -> str:
    return f"/api/v1/remote-manual-selections/batches/{BATCH_ID}/files/{FILE_ID}/content"
