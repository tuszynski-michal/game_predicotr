"""Whole boards retain exact crop identity and one durable publication boundary."""

import base64
import os
import subprocess
import sys

import numpy as np
import pytest
from fastapi.testclient import TestClient
from game_predictor_worker.vision_lab.api import create_app
from game_predictor_worker.vision_lab.contracts import Point
from game_predictor_worker.vision_lab.symbol_contracts import (
    BoardCellDecision,
    LabBoardRequest,
    LabCropRequest,
    LabelBoardDecide,
    LabelWithdraw,
)
from game_predictor_worker.vision_lab.symbol_crops import board_context
from game_predictor_worker.vision_lab.symbol_store import SymbolLabelStore
from pydantic import ValidationError
from test_vision_lab_symbol_labels import dictionary, symbols


def preview(store, source):
    return store.preview(
        LabBoardRequest(
            kind="lab_board", source_id=source.id, board_index=0, expected_geometry_revision=1
        )
    )


def board_request(store, source):
    version = dictionary(store, source)
    board = preview(store, source)
    return LabelBoardDecide(
        op="label_board_decide",
        request_id="whole-board",
        expected_revision=2,
        dictionary_version=1,
        dictionary_digest=version.digest,
        cells=[
            BoardCellDecision(binding=c.binding, action="approve", symbol_id="a")
            for c in board.cells
        ],
    )


@pytest.mark.parametrize("columns", [3, 5])
def test_preview_exact_parity_one_decode_and_overlay(tmp_path, monkeypatch, columns):
    store, source = symbols(tmp_path, columns)
    original = store.catalog.image
    calls = []

    def image(s):
        calls.append(s.id)
        return original(s)

    monkeypatch.setattr(store.catalog, "image", image)
    board = preview(store, source)
    assert calls == [source.id]
    assert board.dictionary is None and board.revision == 0
    assert len(board.cells) == columns * 3
    assert len(base64.b64decode(board.board_png_base64)) <= 4 * 1024 * 1024
    assert max(board.width, board.height) <= 960
    for index, cell in enumerate(board.cells):
        single = store.preview(
            LabCropRequest(
                kind="lab_cell",
                source_id=source.id,
                board_index=0,
                cell_index=index,
                expected_geometry_revision=1,
            )
        )
        assert (cell.binding, cell.png_base64) == (single.binding, single.png_base64)
        assert cell.current is None
    nodes = store.annotations.read().annotations[f"{source.id}:0"].nodes
    # Fixture fits in the context without downscaling: same translated grid, including inner nodes.
    assert [n.x - board.nodes[0].x for n in board.nodes] == pytest.approx(
        [n.x - nodes[0].x for n in nodes]
    )
    assert [n.y - board.nodes[0].y for n in board.nodes] == pytest.approx(
        [n.y - nodes[0].y for n in nodes]
    )


@pytest.mark.parametrize("columns", [3, 5])
def test_atomic_board_retry_restart_backup_and_withdraw(tmp_path, columns):
    store, source = symbols(tmp_path, columns)
    request = board_request(store, source)
    result = store.mutate(request)
    assert result.revision == 3 and result.label_valid and not result.trainable
    assert len(set(result.decision_ids)) == columns * 3
    payload = store.load()
    assert len(payload["history"]) == 3 and len(payload["receipts"]) == 3
    saved = (store.root / "state.json").read_bytes()
    restarted = SymbolLabelStore(store.root, store.annotations)
    assert restarted.mutate(request).decision_ids == result.decision_ids
    assert (store.root / "state.json").read_bytes() == saved
    assert all(c.current.label_valid for c in preview(restarted, source).cells)
    backup = store.backup()
    restored = store.restore(backup.backup_id, tmp_path / "restored")
    assert restored.mutate(request).decision_ids == result.decision_ids
    code = """
import sys
from pathlib import Path
from game_predictor_worker.vision_lab.catalog import Catalog
from game_predictor_worker.vision_lab.annotations import AnnotationStore
from game_predictor_worker.vision_lab.symbol_store import SymbolLabelStore
from game_predictor_worker.vision_lab.symbol_contracts import LabelBoardDecide
s=SymbolLabelStore(Path(sys.argv[1]), AnnotationStore(Path(sys.argv[2]),Catalog(Path(sys.argv[3]))))
r=LabelBoardDecide.model_validate(s.load()['history'][-1]['request'])
v=s.mutate(r)
print(v.replayed, len(v.decision_ids), s.list_labels().total)
"""
    fresh = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(store.root),
            str(store.annotations.root),
            str(store.catalog.root),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        env=os.environ.copy(),
    )
    assert fresh.stdout.strip() == f"True {columns * 3} {columns * 3}"
    withdrawn = store.mutate(
        LabelWithdraw(
            op="label_withdraw",
            request_id="withdraw",
            expected_revision=3,
            decision_id=result.decision_ids[0],
        )
    )
    retry = store.mutate(request)
    assert retry.replayed and retry.revision == 3 and not retry.label_valid
    assert retry.decision_ids == result.decision_ids
    assert withdrawn.result_id not in retry.decision_ids
    assert "SYMBOL_DECISION_SUPERSEDED" in retry.reasons


@pytest.mark.parametrize("fault", ["binding", "class", "source", "cas", "dictionary"])
def test_bad_last_cell_or_drift_never_publishes(tmp_path, fault):
    store, source = symbols(tmp_path)
    request = board_request(store, source)
    before = (store.root / "state.json").read_bytes()
    if fault == "binding":
        request.cells[-1].binding.byte_sha256 = "f" * 64
    elif fault == "class":
        request.cells[-1].symbol_id = "missing"
    elif fault == "source":
        store.catalog.paths[source.asset_id].write_bytes(b"changed")
    elif fault == "cas":
        request.expected_revision = 0
    else:
        request.dictionary_digest = "f" * 64
    with pytest.raises(ValueError):
        store.mutate(request)
    assert (store.root / "state.json").read_bytes() == before
    assert not (store.root / "crops").exists()


@pytest.mark.parametrize("fault", ["duplicate", "short", "order", "mixed"])
def test_complete_row_major_contract(tmp_path, fault):
    store, source = symbols(tmp_path)
    body = board_request(store, source).model_dump()
    if fault == "duplicate":
        body["cells"][-1] = body["cells"][0]
    elif fault == "short":
        body["cells"].pop()
    elif fault == "order":
        body["cells"].reverse()
    else:
        body["cells"][-1]["binding"]["source_id"] = "another"
    with pytest.raises(ValidationError):
        LabelBoardDecide.model_validate(body)


@pytest.mark.parametrize("boundary", ["crop", "state"])
def test_publication_crash_has_no_partial_decisions(tmp_path, monkeypatch, boundary):
    import game_predictor_worker.vision_lab.symbol_store as module

    store, source = symbols(tmp_path)
    request = board_request(store, source)
    before = (store.root / "state.json").read_bytes()
    name = "publish_file" if boundary == "crop" else "write_atomic"
    original = getattr(module, name)
    calls = 0

    def fail(*args):
        nonlocal calls
        calls += 1
        if boundary == "state" or calls == 15:
            raise OSError("publication crash")
        return original(*args)

    monkeypatch.setattr(module, name, fail)
    with pytest.raises(OSError, match="publication crash"):
        store.mutate(request)
    assert (store.root / "state.json").read_bytes() == before
    monkeypatch.setattr(module, name, original)
    assert store.mutate(request).label_valid


def test_role_and_holdout_guard_before_decode(tmp_path, monkeypatch):
    import game_predictor_worker.vision_lab.symbol_crops as module

    store, source = symbols(tmp_path)
    calls = []
    monkeypatch.setattr(store.catalog, "image", lambda s: calls.append(s))
    for reason in ("SYMBOL_ROLE_EXCLUDED", "HOLDOUT_NOT_RELEASED"):

        def blocked(*args, reason=reason):
            raise ValueError(reason)

        monkeypatch.setattr(module, "guard_pixels", blocked)
        with pytest.raises(ValueError, match=reason):
            preview(store, source)
    assert calls == []


def test_downscaled_context_keeps_irregular_internal_nodes():
    nodes = [
        Point(x=100 + c * 400, y=100 + r * 300, provenance="human")
        for r in range(4)
        for c in range(6)
    ]
    nodes[8].x += 53
    nodes[8].y -= 17
    data, width, height, scaled = board_context(np.zeros((1200, 2300, 3), dtype=np.uint8), nodes)
    assert width == 960 and height < 960 and data.startswith(b"\x89PNG")
    assert scaled[8].x == pytest.approx((nodes[8].x - 92) * width / 2017)
    assert scaled[8].y == pytest.approx((nodes[8].y - 92) * height / 917)
    assert scaled[8].x != pytest.approx((scaled[7].x + scaled[9].x) / 2)


def test_board_api_and_explicit_nonapproval(tmp_path):
    store, source = symbols(tmp_path)
    request = board_request(store, source)
    for cell, action in zip(
        request.cells[:3], ["unknown", "unreadable", "grid_issue"], strict=True
    ):
        cell.action, cell.symbol_id = action, None
    client = TestClient(
        create_app(store.catalog, store.annotations.root, symbol_root=store.root),
        base_url="http://127.0.0.1:8102",
    )
    headers = {"origin": "http://127.0.0.1:3102"}
    response = client.post("/symbols", json=request.model_dump(), headers=headers)
    assert response.status_code == 200, response.text
    assert not response.json()["label_valid"] and len(response.json()["decision_ids"]) == 15
    response = client.post(
        "/symbol-crops",
        json={
            "kind": "lab_board",
            "source_id": source.id,
            "board_index": 0,
            "expected_geometry_revision": 1,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    board = response.json()
    assert board["dictionary"]["active"] and board["revision"] == 3
    assert [c["current"]["action"] for c in board["cells"][:3]] == [
        "unknown",
        "unreadable",
        "grid_issue",
    ]
