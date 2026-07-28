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
from game_predictor_worker.images.cell_grid_review_http import (
    CellGridReviewHttpError,
    create_cell_grid_review_server,
)
from PIL import Image

OBSERVATION_ID = "a" * 64


class _ReviewStub:
    def __init__(self, board: Path, source: Path) -> None:
        self.board = board
        self.source = source
        self.calls: list[tuple[str, dict[str, object]]] = []

    def state(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("state", kwargs))
        return {"progress": {"accepted": 0, "pending": 27, "total": 27}, "samples": []}

    def resolve_board(self, observation_id: str) -> tuple[Path, str]:
        assert observation_id == OBSERVATION_ID
        return self.board, "b" * 64

    def resolve_source(self, observation_id: str) -> tuple[Path, str]:
        assert observation_id == OBSERVATION_ID
        return self.source, "c" * 64

    def save_draft(self, **kwargs: object) -> bool:
        self.calls.append(("draft", kwargs))
        return True

    def accept(self, **kwargs: object) -> bool:
        self.calls.append(("accept", kwargs))
        return True

    def reopen(self, observation_id: str) -> bool:
        self.calls.append(("reopen", {"observation_id": observation_id}))
        return True


@contextmanager
def _running_server(tmp_path: Path) -> Iterator[tuple[str, str, _ReviewStub]]:
    static_root = tmp_path / "static"
    static_root.mkdir()
    (static_root / "index.html").write_text("<h1>grid review</h1>", encoding="utf-8")
    (static_root / "app.js").write_text("void 0;", encoding="utf-8")
    (static_root / "styles.css").write_text("body{}", encoding="utf-8")
    board = tmp_path / "board.png"
    Image.new("RGB", (500, 300), (1, 2, 3)).save(board)
    source = tmp_path / "source.jpg"
    Image.new("RGB", (960, 1280), (4, 5, 6)).save(source)
    review = _ReviewStub(board, source)
    server = create_cell_grid_review_server(  # type: ignore[arg-type]
        review,
        static_root,
        host="127.0.0.1",
        port=0,
        token="test-token",
        calibration_profiles={
            "profileSetVersion": "grid-calibration-profiles-v1",
            "profiles": [{"profileId": "p1"}],
            "status": "published",
        },
    )
    origin = f"http://127.0.0.1:{server.server_address[1]}"
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


def _decision_body() -> dict[str, object]:
    return {
        "observationId": OBSERVATION_ID,
        "sourceQuad": [
            {"x": 100, "y": 100},
            {"x": 599, "y": 100},
            {"x": 599, "y": 399},
            {"x": 100, "y": 399},
        ],
        "v1CutCellIndexes": [0, 14],
        "v1ImpactReviewed": True,
    }


def test_static_bootstrap_state_and_board_are_served(tmp_path: Path) -> None:
    with _running_server(tmp_path) as (origin, token, review):
        status, content, headers = _request(f"{origin}/")
        assert status == 200
        assert content == b"<h1>grid review</h1>"
        assert headers["X-Content-Type-Options"] == "nosniff"

        status, content, _ = _request(f"{origin}/api/bootstrap")
        assert status == 200
        assert _json(content) == {"token": token}

        status, content, _ = _request(f"{origin}/api/state?status=accepted&offset=2&limit=1")
        assert status == 200
        assert _json(content)["samples"] == []
        assert review.calls[-1] == (
            "state",
            {"limit": 1, "offset": 2, "status": "accepted"},
        )

        status, content, _ = _request(f"{origin}/api/profiles")
        assert status == 200
        assert _json(content) == {
            "profileSetVersion": "grid-calibration-profiles-v1",
            "profiles": [{"profileId": "p1"}],
            "status": "published",
        }

        status, content, headers = _request(f"{origin}/api/boards/{OBSERVATION_ID}")
        assert status == 200
        assert content == review.board.read_bytes()
        assert headers["ETag"] == f'"{"b" * 64}"'

        status, content, headers = _request(f"{origin}/api/sources/{OBSERVATION_ID}")
        assert status == 200
        assert content == review.source.read_bytes()
        assert headers["ETag"] == f'"{"c" * 64}"'


def test_mutations_require_token_and_same_origin(tmp_path: Path) -> None:
    with _running_server(tmp_path) as (origin, token, review):
        status, content, _ = _request(
            f"{origin}/api/draft",
            body=_decision_body(),
        )
        assert status == 403
        assert _json(content)["code"] == "CELL_GRID_HTTP_FORBIDDEN"

        status, content, _ = _request(
            f"{origin}/api/accept",
            body={**_decision_body(), "reviewedBy": "owner"},
            token=token,
            origin="http://example.test",
        )
        assert status == 403
        assert _json(content)["code"] == "CELL_GRID_HTTP_ORIGIN_REJECTED"

        status, content, _ = _request(
            f"{origin}/api/accept",
            body={**_decision_body(), "reviewedBy": "owner"},
            token=token,
            origin=origin,
        )
        assert status == 200
        assert _json(content) == {"changed": True}
        assert review.calls[-1][0] == "accept"


def test_draft_reopen_and_invalid_contract_are_stable(tmp_path: Path) -> None:
    with _running_server(tmp_path) as (origin, token, review):
        status, content, _ = _request(
            f"{origin}/api/draft",
            body=_decision_body(),
            token=token,
            origin=origin,
        )
        assert status == 200
        assert review.calls[-1][0] == "draft"

        status, content, _ = _request(
            f"{origin}/api/reopen",
            body={"observationId": OBSERVATION_ID},
            token=token,
            origin=origin,
        )
        assert status == 200
        assert _json(content) == {"changed": True}
        assert review.calls[-1] == (
            "reopen",
            {"observation_id": OBSERVATION_ID},
        )

        invalid = _decision_body()
        invalid["sourceQuad"] = "100,100"
        status, content, _ = _request(
            f"{origin}/api/draft",
            body=invalid,
            token=token,
            origin=origin,
        )
        assert status == 400
        assert _json(content)["code"] == "CELL_GRID_HTTP_REQUEST_INVALID"


def test_unknown_routes_and_non_loopback_binding_are_refused(tmp_path: Path) -> None:
    with _running_server(tmp_path) as (origin, _, _):
        status, content, _ = _request(f"{origin}/../secret")
        assert status == 404
        assert _json(content)["code"] == "CELL_GRID_HTTP_NOT_FOUND"

    static_root = tmp_path / "other-static"
    static_root.mkdir()
    board = tmp_path / "other-board.png"
    Image.new("RGB", (500, 300)).save(board)
    source = tmp_path / "other-source.jpg"
    Image.new("RGB", (960, 1280)).save(source)
    with pytest.raises(CellGridReviewHttpError) as error:
        create_cell_grid_review_server(  # type: ignore[arg-type]
            _ReviewStub(board, source),
            static_root,
            host="0.0.0.0",
            port=0,
        )
    assert error.value.code == "CELL_GRID_HTTP_NON_LOOPBACK"
