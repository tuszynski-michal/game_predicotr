from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from game_predictor_worker.images.symbol_review_http import (
    SymbolReviewHttpError,
    create_review_server,
)
from PIL import Image

SAMPLE_ID = "a" * 64


class _ReviewStub:
    def __init__(self, crop: Path) -> None:
        self.crop = crop
        self.calls: list[tuple[str, dict[str, object]]] = []

    def state(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("state", kwargs))
        return {"configuration": {"configured": False}, "samples": []}

    def resolve_crop(self, sample_id: str) -> tuple[Path, str]:
        assert sample_id == SAMPLE_ID
        return self.crop, "b" * 64

    def configure(self, **kwargs: object) -> bool:
        self.calls.append(("configure", kwargs))
        return True

    def decide(self, **kwargs: object) -> int:
        self.calls.append(("decide", kwargs))
        return 1

    def clear(self, **kwargs: object) -> int:
        self.calls.append(("clear", kwargs))
        return 1


@contextmanager
def _running_server(
    tmp_path: Path,
) -> Iterator[tuple[str, str, _ReviewStub]]:
    static_root = tmp_path / "static"
    static_root.mkdir()
    (static_root / "index.html").write_text("<h1>review</h1>", encoding="utf-8")
    (static_root / "app.js").write_text("void 0;", encoding="utf-8")
    (static_root / "styles.css").write_text("body{}", encoding="utf-8")
    crop = tmp_path / "crop.png"
    Image.new("RGB", (90, 90), (1, 2, 3)).save(crop)
    review = _ReviewStub(crop)
    server = create_review_server(  # type: ignore[arg-type]
        review,
        static_root,
        host="127.0.0.1",
        port=0,
        token="test-token",
    )
    port = int(server.server_address[1])
    origin = f"http://127.0.0.1:{port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield origin, "test-token", review
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _request(
    url: str,
    *,
    body: dict[str, object] | None = None,
    token: str | None = None,
    origin: str | None = None,
    content_type: str = "application/json",
) -> tuple[int, bytes, dict[str, str]]:
    headers: dict[str, str] = {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = content_type
    if token is not None:
        headers["X-Review-Token"] = token
    if origin is not None:
        headers["Origin"] = origin
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, error.read(), dict(error.headers)


def _json(content: bytes) -> dict[str, Any]:
    value = json.loads(content)
    assert isinstance(value, dict)
    return value


def test_static_bootstrap_state_and_crop_are_served(tmp_path: Path) -> None:
    with _running_server(tmp_path) as (origin, token, review):
        status, body, headers = _request(f"{origin}/")
        assert status == 200
        assert body == b"<h1>review</h1>"
        assert headers["X-Content-Type-Options"] == "nosniff"

        status, body, _ = _request(f"{origin}/api/bootstrap")
        assert status == 200
        assert _json(body) == {"token": token}

        status, body, _ = _request(
            f"{origin}/api/state?status=accepted&offset=2&limit=1"
        )
        assert status == 200
        assert _json(body)["samples"] == []
        assert review.calls[-1] == (
            "state",
            {"limit": 1, "offset": 2, "status": "accepted"},
        )

        status, body, headers = _request(f"{origin}/api/crops/{SAMPLE_ID}")
        assert status == 200
        assert body == review.crop.read_bytes()
        assert headers["ETag"] == f'"{"b" * 64}"'


def test_configure_requires_token_and_same_browser_origin(tmp_path: Path) -> None:
    body = {
        "gameCode": "game",
        "reviewedBy": "owner",
        "symbolCodes": ["seven", "star"],
    }
    with _running_server(tmp_path) as (origin, token, review):
        status, content, _ = _request(f"{origin}/api/configure", body=body)
        assert status == 403
        assert _json(content)["code"] == "SYMBOL_REVIEW_HTTP_FORBIDDEN"

        status, content, _ = _request(
            f"{origin}/api/configure",
            body=body,
            token=token,
            origin="http://example.test",
        )
        assert status == 403
        assert _json(content)["code"] == "SYMBOL_REVIEW_HTTP_ORIGIN_REJECTED"

        status, content, _ = _request(
            f"{origin}/api/configure",
            body=body,
            token=token,
            origin=origin,
        )
        assert status == 200
        assert _json(content) == {"changed": True}
        assert review.calls[-1][0] == "configure"


def test_decision_and_clear_validate_json_contract(tmp_path: Path) -> None:
    with _running_server(tmp_path) as (origin, token, review):
        status, content, _ = _request(
            f"{origin}/api/decision",
            body={
                "applyToIdentical": True,
                "decision": "accepted",
                "sampleId": SAMPLE_ID,
                "symbolCode": "seven",
            },
            token=token,
            origin=origin,
        )
        assert status == 200
        assert _json(content) == {"changed": 1}
        assert review.calls[-1] == (
            "decide",
            {
                "apply_to_identical": True,
                "decision": "accepted",
                "sample_id": SAMPLE_ID,
                "symbol_code": "seven",
            },
        )

        status, content, _ = _request(
            f"{origin}/api/clear",
            body={"sampleId": SAMPLE_ID, "applyToIdentical": "yes"},
            token=token,
            origin=origin,
        )
        assert status == 400
        assert _json(content)["code"] == "SYMBOL_REVIEW_HTTP_REQUEST_INVALID"


def test_unknown_routes_and_invalid_query_are_stable(tmp_path: Path) -> None:
    with _running_server(tmp_path) as (origin, _, _):
        status, content, _ = _request(f"{origin}/../secret")
        assert status == 404
        assert _json(content)["code"] == "SYMBOL_REVIEW_HTTP_NOT_FOUND"

        status, content, _ = _request(f"{origin}/api/state?offset=nope")
        assert status == 400
        assert _json(content)["code"] == "SYMBOL_REVIEW_HTTP_REQUEST_INVALID"


def test_non_loopback_binding_is_refused(tmp_path: Path) -> None:
    static_root = tmp_path / "static"
    static_root.mkdir()
    crop = tmp_path / "crop.png"
    Image.new("RGB", (90, 90)).save(crop)

    with pytest.raises(SymbolReviewHttpError) as error:
        create_review_server(  # type: ignore[arg-type]
            _ReviewStub(crop),
            static_root,
            host="0.0.0.0",
            port=0,
        )

    assert error.value.code == "SYMBOL_REVIEW_HTTP_NON_LOOPBACK"
