from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from game_predictor_worker.images.calibrated_symbol_inventory import (
    build_calibrated_symbol_crop_inventory,
)
from game_predictor_worker.images.symbol_dataset import (
    CALIBRATED_INVENTORY_VERSION,
    SymbolDatasetError,
    load_symbol_crop_inventory,
)
from game_predictor_worker.images.symbol_review import (
    BootstrapSymbolReview,
    SymbolReviewError,
)
from game_predictor_worker.images.symbol_review_http import create_review_server

ROOT = Path(__file__).resolve().parents[3]
QUALITY = ROOT / "ai_docs" / "quality"
CROP_ROOT = ROOT / "artifacts" / "m5-board-crops"
INVENTORY = QUALITY / "m6-symbol-crop-inventory-v2.json"


def _build(*, quality: Path | None = None):
    return build_calibrated_symbol_crop_inventory(
        QUALITY / "m5-corpus-manifest.json",
        QUALITY / "m5-golden-annotations.json",
        QUALITY / "m5-cell-grid-golden.json",
        QUALITY / "m5-grid-calibration-profiles.json",
        QUALITY / "m5-board-cell-crops-v2-calibrated-report.json",
        quality or QUALITY / "m5-board-cell-crops-v2-calibrated-quality-report.json",
        CROP_ROOT,
    )


def _review(tmp_path: Path) -> BootstrapSymbolReview:
    review = BootstrapSymbolReview(
        INVENTORY,
        CROP_ROOT,
        tmp_path / "reviewed-labels.json",
        require_calibrated=True,
    )
    review.configure(
        game_code="blazing-hot-7-deluxe",
        reviewed_by="owner",
        symbol_codes=("cherries", "lemon", "seven"),
    )
    return review


def test_real_calibrated_inventory_is_deterministic_and_complete() -> None:
    content, loaded = load_symbol_crop_inventory(INVENTORY)
    rebuilt = _build()

    assert loaded.inventory_version == CALIBRATED_INVENTORY_VERSION
    assert len(loaded.samples) == 5805
    assert len({sample.board_id for sample in loaded.samples}) == 387
    assert all(sample.observation_id != sample.sample_id for sample in loaded.samples)
    assert rebuilt.to_json_bytes() == content


def test_inventory_rejects_quality_gate_drift(tmp_path: Path) -> None:
    quality = json.loads(
        (QUALITY / "m5-board-cell-crops-v2-calibrated-quality-report.json").read_text(
            encoding="utf-8"
        )
    )
    quality["trainingAllowed"] = False
    quality_path = tmp_path / "quality.json"
    quality_path.write_text(json.dumps(quality), encoding="utf-8")

    with pytest.raises(SymbolDatasetError) as error:
        _build(quality=quality_path)

    assert error.value.code == "SYMBOL_DATASET_CALIBRATED_CROPS_NOT_ACCEPTED"


def test_board_decisions_are_atomic_idempotent_and_resumable(tmp_path: Path) -> None:
    review = _review(tmp_path)
    payload = review.board_state()
    board = payload["board"]
    assert isinstance(board, dict)
    cells = board["cells"]
    assert isinstance(cells, list)
    assert len(cells) == 15
    assert [cell["cellIndex"] for cell in cells] == list(range(15))

    first = cells[0]["sampleId"]
    changed = review.decide_board(
        board_id=str(board["boardId"]),
        decisions=[{"decision": "accepted", "sampleId": first, "symbolCode": "lemon"}],
    )
    assert changed == 1
    assert (
        review.decide_board(
            board_id=str(board["boardId"]),
            decisions=[{"decision": "accepted", "sampleId": first, "symbolCode": "lemon"}],
        )
        == 0
    )

    resumed = BootstrapSymbolReview(
        INVENTORY,
        CROP_ROOT,
        tmp_path / "reviewed-labels.json",
        require_calibrated=True,
    )
    resumed_board = resumed.board_state()["board"]
    assert isinstance(resumed_board, dict)
    assert resumed_board["status"] == "pending"
    assert resumed_board["cells"][0]["symbolCode"] == "lemon"


def test_suggestions_are_payload_only_and_never_create_a_decision(
    tmp_path: Path,
) -> None:
    class Provider:
        def for_sample(self, sample):
            return {
                "suggestionStatus": "suggested",
                "suggestions": [{"rank": 1, "symbolCode": "lemon"}],
            }

    review = BootstrapSymbolReview(
        INVENTORY,
        CROP_ROOT,
        tmp_path / "reviewed-labels.json",
        require_calibrated=True,
        suggestion_provider=Provider(),
    )
    review.configure(
        game_code="blazing-hot-7-deluxe",
        reviewed_by="owner",
        symbol_codes=("cherries", "lemon", "seven"),
    )

    board = review.board_state()["board"]

    assert isinstance(board, dict)
    assert board["cells"][0]["suggestions"][0]["symbolCode"] == "lemon"
    assert board["cells"][0]["decision"] == "pending"
    assert review.progress()["accepted"] == 0


def test_board_update_rejects_foreign_cell_without_partial_write(tmp_path: Path) -> None:
    review = _review(tmp_path)
    first = review.board_state(status="all", offset=0)["board"]
    second = review.board_state(status="all", offset=1)["board"]
    assert isinstance(first, dict) and isinstance(second, dict)

    with pytest.raises(SymbolReviewError) as error:
        review.decide_board(
            board_id=str(first["boardId"]),
            decisions=[
                {
                    "decision": "accepted",
                    "sampleId": first["cells"][0]["sampleId"],
                    "symbolCode": "lemon",
                },
                {
                    "decision": "accepted",
                    "sampleId": second["cells"][0]["sampleId"],
                    "symbolCode": "seven",
                },
            ],
        )

    assert error.value.code == "SYMBOL_REVIEW_BOARD_SAMPLE_INVALID"
    assert review.progress()["accepted"] == 0


def test_board_image_is_reverified_and_legacy_inventory_is_refused(tmp_path: Path) -> None:
    review = _review(tmp_path)
    board = review.board_state()["board"]
    assert isinstance(board, dict)
    path, checksum = review.resolve_board(str(board["boardId"]))
    assert path.is_file()
    assert len(checksum) == 64

    legacy = QUALITY / "m6-symbol-crop-inventory.json"
    if legacy.exists():
        with pytest.raises(SymbolReviewError) as error:
            BootstrapSymbolReview(
                legacy,
                CROP_ROOT,
                tmp_path / "legacy-labels.json",
                require_calibrated=True,
            )
        assert error.value.code == "SYMBOL_REVIEW_CALIBRATED_INVENTORY_REQUIRED"


def test_whole_layout_http_serves_board_and_saves_cell(tmp_path: Path) -> None:
    review = _review(tmp_path)
    static_root = ROOT / "scripts" / "m6_symbol_review"
    server = create_review_server(review, static_root, host="127.0.0.1", port=0, token="t")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(f"{base}/api/boards?status=pending&offset=0", timeout=5) as response:
            payload = json.loads(response.read())
        board = payload["board"]
        assert len(board["cells"]) == 15
        with urlopen(f"{base}{board['boardUrl']}", timeout=5) as response:
            assert response.headers["Content-Type"] == "image/png"
            assert len(response.read()) > 1000

        body = json.dumps(
            {
                "boardId": board["boardId"],
                "decisions": [
                    {
                        "decision": "accepted",
                        "sampleId": board["cells"][0]["sampleId"],
                        "symbolCode": "lemon",
                    }
                ],
            }
        ).encode()
        request = Request(
            f"{base}/api/board-decisions",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Origin": base,
                "X-Review-Token": "t",
            },
        )
        with urlopen(request, timeout=5) as response:
            assert json.loads(response.read()) == {"changed": 1}

        forbidden = Request(
            f"{base}/api/board-decisions",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(HTTPError) as error:
            urlopen(forbidden, timeout=5)
        assert error.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
