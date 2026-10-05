"""Operator-only crop review: exact pixels, restart, retry and protected legacy state."""

import base64
import hashlib
import io
import json
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from game_predictor_worker.vision_lab import symbol_batch_labels as module
from game_predictor_worker.vision_lab.annotations import digest, read_checked, write_atomic
from game_predictor_worker.vision_lab.api import create_app
from game_predictor_worker.vision_lab.geometry import crop_cell
from game_predictor_worker.vision_lab.snapshot import canonical, sha
from game_predictor_worker.vision_lab.symbol_contracts import BatchLabelDecide
from PIL import Image
from test_vision_lab_symbol_labels import symbols

HEADERS = {"origin": "http://127.0.0.1:3102"}


@pytest.fixture
def pack(tmp_path, monkeypatch):
    folder = tmp_path / "sources"
    folder.mkdir()
    source = folder / "seq_1-1.png"
    pixels = np.arange(150 * 150 * 3, dtype=np.uint8).reshape(150, 150, 3)
    Image.fromarray(pixels).save(source)
    row = {
        "path": str(source),
        "filename": source.name,
        "sha256": sha(source),
        "start": 1,
        "end": 1,
    }
    quad = [[10.0, 10.0], [100.0, 10.0], [100.0, 100.0], [10.0, 100.0]]
    crop = crop_cell(pixels, np.asarray(quad, dtype=np.float32))
    pixel_sha = hashlib.sha256(crop.tobytes()).hexdigest()
    batch = tmp_path / "batch"
    batch.mkdir()
    policy = tmp_path / "policy"
    policy.mkdir()
    training = policy / "training.json"
    training.write_text("{}")
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "manifest.json").write_text("{}")
    payload = {
        "training_manifest": str(training),
        "classes": ["A", "B"],
        "excluded_sha256": [],
        "training_photo_pixel_groups": [],
        "rows": [row],
    }
    (batch / "manifest.json").write_bytes(
        canonical({"payload": payload, "sha256": digest(payload)})
    )
    result = {
        "row": row,
        "cells": [
            {"board_index": 0, "cell_index": 0, "quad": quad, "crop_pixel_sha256": pixel_sha}
        ],
    }
    result_dir = batch / "photos" / "0000"
    result_dir.mkdir(parents=True)
    (result_dir / "result.json").write_text("{}")
    case = {
        "source": row,
        "photo_index": 0,
        "board": 1,
        "field": 1,
        "quad": quad,
        "crop_pixel_sha256": pixel_sha,
        "human_approved": False,
        "category": "Fixture",
    }
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    evidence = evidence_dir / "cases.json"
    write_atomic(
        evidence,
        {
            "format": "mumie-targeted-review-evidence-v1",
            "candidate_batch_id": digest(payload),
            "human_labels_written": 0,
            "cases": [case],
        },
    )
    dictionary = {
        "game_id": "mumie",
        "version": 1,
        "digest": "a" * 64,
        "status": "approved",
        "active": True,
        "entries": [
            {"id": name.lower(), "code": name, "display_name": name} for name in ["A", "B"]
        ],
    }
    inputs = SimpleNamespace(
        preparation={"dictionary": dictionary},
        bundle=bundle,
        payload={"live_bindings": {str(training): sha(training)}},
    )
    monkeypatch.setattr(module, "validate_batch", lambda _root: payload)
    monkeypatch.setattr(module, "validate_result", lambda *_args: result)
    monkeypatch.setattr(module.SymbolTrainingAdapter, "validate", lambda _self: inputs)
    reference = module.prepare(batch, evidence, tmp_path / "references")
    labels = tmp_path / "batch-labels"
    return module.BatchReviewStore(reference, labels), source, training, payload, evidence


def request(store, **changes):
    page = store.preview()
    return BatchLabelDecide(
        op="batch_label_decide",
        request_id="choice",
        expected_revision=page.revision,
        reference_id=page.reference_id,
        case_id=page.items[0].case_id,
        action="approve",
        symbol_id="a",
    ).model_copy(update=changes)


def test_exact_png_and_no_implicit_approval(pack):
    store, source, _, _, _ = pack
    page = store.preview()
    assert page.revision == 0 and not page.trainable
    assert page.items[0].action is None and page.items[0].symbol_id is None
    with Image.open(io.BytesIO(base64.b64decode(page.items[0].png_base64))) as crop:
        assert crop.size == (96, 96)
        assert hashlib.sha256(crop.tobytes()).hexdigest() == page.items[0].pixel_sha256
    assert not (store.root / "state.json").exists()
    assert source.exists()


def test_restart_lost_reply_cas_and_history(pack):
    store, _, _, _, _ = pack
    choice = request(store)
    result = store.mutate(choice)  # server commits; client may lose this reply
    reopened = module.BatchReviewStore(store.reference, store.root)
    replay = reopened.mutate(choice)
    assert replay.replayed and replay.revision == result.revision == 1
    assert replay.result_id == result.result_id
    assert not result.label_valid and not result.trainable
    assert result.training_blockers == module.BLOCKERS
    with pytest.raises(ValueError, match="REQUEST_ID_CONFLICT"):
        reopened.mutate(choice.model_copy(update={"symbol_id": "b"}))
    with pytest.raises(ValueError, match="SYMBOL_REVISION_CONFLICT"):
        reopened.mutate(choice.model_copy(update={"request_id": "stale"}))
    second = request(reopened, request_id="correct", symbol_id="b")
    reopened.mutate(second)
    state = read_checked(store.root / "state.json")
    assert (
        state["revision"]
        == len(state["history"])
        == len(state["decisions"])
        == len(state["receipts"])
        == 2
    )
    assert [d["symbol_id"] for d in state["decisions"]] == ["a", "b"]
    assert all(d["origin"] == "batch_crop_review" for d in state["decisions"])
    assert reopened.preview().items[0].symbol_id == "b"
    script = (
        "from pathlib import Path; "
        "from game_predictor_worker.vision_lab.symbol_batch_labels import BatchReviewStore; "
        "import sys; s=BatchReviewStore(Path(sys.argv[1]),Path(sys.argv[2])); "
        "print(s.preview().model_dump_json())"
    )
    fresh = subprocess.run(
        [sys.executable, "-c", script, str(store.reference), str(store.root)],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    assert json.loads(fresh.stdout)["revision"] == 2
    assert json.loads(fresh.stdout)["items"][0]["symbol_id"] == "b"


@pytest.mark.parametrize(
    "change,code",
    [
        ("class", "SYMBOL_CLASS_INVALID"),
        ("case", "CASE_CONFLICT"),
        ("reference", "REFERENCE_CONFLICT"),
        ("source", "SOURCE_DRIFT"),
        ("policy", "INPUT_DRIFT"),
        ("png", "CROP_INTEGRITY_ERROR"),
    ],
)
def test_invalid_inputs_never_publish(pack, change, code):
    store, source, policy, _, _ = pack
    choice = request(store)
    if change == "class":
        choice.symbol_id = "other"
    elif change == "case":
        choice.case_id = "f" * 64
    elif change == "reference":
        choice.reference_id = "f" * 64
    elif change == "source":
        source.write_bytes(b"changed")
    elif change == "policy":
        policy.write_bytes(b"changed")
    elif change == "png":
        next((store.reference / "crops").glob("*.png")).write_bytes(b"changed")
    with pytest.raises(ValueError, match=code):
        store.mutate(choice)
    assert not (store.root / "state.json").exists()


def test_failure_before_publication_and_retry(pack, monkeypatch):
    store, _, _, _, _ = pack
    choice = request(store)
    writer = module.write_atomic

    def fail(*_args):
        raise OSError("injected publication failure")

    monkeypatch.setattr(module, "write_atomic", fail)
    with pytest.raises(OSError):
        store.mutate(choice)
    assert not (store.root / "state.json").exists()
    monkeypatch.setattr(module, "write_atomic", writer)
    assert store.mutate(choice).revision == 1
    assert store.mutate(choice).replayed


def test_exclusion_checked_before_decoding(pack, monkeypatch, tmp_path):
    _, source, _, payload, evidence = pack
    payload["excluded_sha256"] = [sha(source)]
    data = read_checked(evidence)
    data["candidate_batch_id"] = digest(payload)
    write_atomic(evidence, data)

    def decode(*_args):
        raise AssertionError("excluded source decoded")

    monkeypatch.setattr(module, "load_photo", decode)
    with pytest.raises(ValueError, match="SOURCE_EXCLUDED"):
        module.prepare(tmp_path / "batch", evidence, tmp_path / "second-reference")


def test_existing_api_and_original_stores_are_unchanged(pack, tmp_path):
    review, _, _, _, _ = pack
    legacy, _ = symbols(tmp_path / "legacy")
    before = (legacy.annotations.root / "state.json").read_bytes()
    client = TestClient(
        create_app(
            legacy.catalog,
            legacy.annotations.root,
            symbol_root=legacy.root,
            symbol_batch_reference=review.reference,
            symbol_batch_labels=review.root,
        ),
        base_url="http://127.0.0.1:8102",
    )
    page = client.post("/symbol-crops", json={"kind": "batch_queue"}, headers=HEADERS)
    assert page.status_code == 200, page.text
    choice = request(review).model_dump()
    assert client.post("/symbols", json=choice).status_code == 403
    assert client.post("/symbols", json=choice, headers=HEADERS).status_code == 200
    assert client.post("/symbols", json=choice, headers=HEADERS).json()["replayed"]
    assert (
        client.post("/symbols", json={**choice, "path": "arbitrary"}, headers=HEADERS).status_code
        == 422
    )
    assert (
        client.post(
            "/symbols", json={**choice, "action": "unreadable"}, headers=HEADERS
        ).status_code
        == 422
    )
    assert client.get("/symbols").json()["revision"] == 0
    assert not (legacy.root / "state.json").exists()
    assert (legacy.annotations.root / "state.json").read_bytes() == before
    default = TestClient(
        create_app(legacy.catalog, legacy.annotations.root, symbol_root=legacy.root),
        base_url="http://127.0.0.1:8102",
    )
    assert (
        default.post("/symbol-crops", json={"kind": "batch_queue"}, headers=HEADERS).status_code
        == 503
    )
    assert default.get("/annotations").status_code == 200


def test_non_class_review_and_receipt_after_policy_drift(pack):
    store, _, policy, _, _ = pack
    choice = request(store, action="grid_issue", symbol_id=None)
    store.mutate(choice)
    policy.write_bytes(b"changed")
    assert store.mutate(choice).replayed  # acknowledgement remains recoverable; no new pixels
    assert read_checked(store.root / "state.json")["decisions"][0]["symbol_id"] is None
    with pytest.raises(ValueError, match="INPUT_DRIFT"):
        store.preview()


def test_portal_links_to_exact_case_and_keeps_original(pack):
    store, _, _, _, evidence = pack
    destination = evidence.parent / "review.html"
    destination.write_text("original read-only page")
    before = evidence.read_bytes()
    module.publish_portal(store.reference, destination)
    first = destination.read_bytes()
    case_id = store.preview().items[0].case_id
    assert ("http://127.0.0.1:3102/symbols/batch?case=" + case_id).encode() in first
    assert b"data:image/png;base64," in first
    assert (evidence.parent / "review.before-editing.html").read_text() == "original read-only page"
    module.publish_portal(store.reference, destination)
    assert destination.read_bytes() == first and evidence.read_bytes() == before
    assert not (store.root / "state.json").exists()
    with pytest.raises(ValueError, match="PORTAL_PATH_INVALID"):
        module.publish_portal(store.reference, store.reference / "review.html")
