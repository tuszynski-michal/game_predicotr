"""Durable, explicit photo review and targeted repair without automatic approval."""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from game_predictor_worker.vision_lab.annotation_contracts import PhotoReviewRequest
from game_predictor_worker.vision_lab.annotations import (
    AnnotationStore,
    interpolate,
    read_checked,
    write_atomic,
)
from game_predictor_worker.vision_lab.api import create_app
from game_predictor_worker.vision_lab.catalog import Catalog
from game_predictor_worker.vision_lab.photo_review import board_revisions, photo_accepted
from game_predictor_worker.vision_lab.rebase_annotations import rebase_annotations
from game_predictor_worker.vision_lab.snapshot import import_folder
from PIL import Image
from test_vision_lab_annotations import populate, request_for, setup_store


def review_for(store, source_id, action="accept", indices=None, note=""):
    state = store.read()
    return PhotoReviewRequest(
        request_id=f"photo-review-{state.revision}",
        expected_revision=state.revision,
        actor="operator",
        source_id=source_id,
        source_sha256=store.catalog.sources[source_id].sha256,
        expected_board_revisions=board_revisions(state, source_id),
        action=action,
        board_indices=indices or [],
        note=note,
    )


def full(store, source_id, index=0):
    request = request_for(store, source_id, action="approve_full")
    request.annotation.board_index = index
    request.annotation.nodes = interpolate(request.annotation.corners, request.annotation.topology)
    for node in request.annotation.nodes:
        node.provenance = "human"
    request.reviewed_all_nodes = True
    return store.mutate(request)


def test_old_data_defaults_unreviewed_and_read_does_not_rewrite(tmp_path):
    store = setup_store(tmp_path)
    source_id = next(iter(store.catalog.sources))
    full(store, source_id)
    payload = read_checked(store.root / "state.json")
    payload["state"].pop("photo_reviews")
    write_atomic(store.root / "state.json", payload)
    before = (store.root / "state.json").read_bytes()
    state = store.read()
    assert state.photo_reviews == {}
    assert state.annotations[f"{source_id}:0"].full_approved
    assert not photo_accepted(state, store.catalog.sources[source_id])
    assert (store.root / "state.json").read_bytes() == before


def test_targeted_correction_draft_requires_full_then_accept_entire_current_set(tmp_path):
    store = setup_store(tmp_path)
    source_id = next(iter(store.catalog.sources))
    full(store, source_id, 0)
    full(store, source_id, 4)
    original = copy.deepcopy(store.read().annotations[f"{source_id}:4"])
    store.mutate(review_for(store, source_id))  # two full grids; no requirement for nine
    marked = store.mutate(review_for(store, source_id, "mark", [0], "Błędny lewy róg"))
    assert not photo_accepted(marked, store.catalog.sources[source_id])
    assert marked.annotations[f"{source_id}:0"].full_approved  # distinct approval layers
    with pytest.raises(ValueError, match="CORRECTIONS_REQUIRED"):
        store.mutate(review_for(store, source_id))
    store.mutate(request_for(store, source_id, action="draft"))
    assert store.read().photo_reviews[source_id].issues["0"].status == "needs_review"
    with pytest.raises(ValueError, match="CORRECTION_FULL_APPROVAL_REQUIRED"):
        store.mutate(review_for(store, source_id))
    fixed = full(store, source_id)
    assert not photo_accepted(fixed, store.catalog.sources[source_id])
    accepted = store.mutate(review_for(store, source_id))
    assert photo_accepted(accepted, store.catalog.sources[source_id])
    assert accepted.photo_reviews[source_id].issues == {}
    assert accepted.annotations[f"{source_id}:4"] == original
    assert len(read_checked(store.root / "state.json")["history"]) == accepted.revision


def test_withdraw_never_auto_accepts_and_nonfull_data_is_not_promoted(tmp_path):
    store = setup_store(tmp_path)
    source_id = next(iter(store.catalog.sources))
    with pytest.raises(ValueError, match="FULL_GEOMETRY_REQUIRED"):
        store.mutate(review_for(store, source_id))
    store.mutate(request_for(store, source_id))
    with pytest.raises(ValueError, match="FULL_GEOMETRY_REQUIRED"):
        store.mutate(review_for(store, source_id))
    full(store, source_id, 1)
    store.mutate(review_for(store, source_id, "mark", [0]))
    withdrawn = store.mutate(review_for(store, source_id, "withdraw", [0]))
    assert not photo_accepted(withdrawn, store.catalog.sources[source_id])
    accepted = store.mutate(review_for(store, source_id))
    assert photo_accepted(accepted, store.catalog.sources[source_id])
    assert not accepted.annotations[f"{source_id}:0"].full_approved


def test_cas_geometry_versions_sha_retry_and_per_source_invalidation(tmp_path):
    store = setup_store(tmp_path)
    source_id, other = list(store.catalog.sources)[:2]
    full(store, source_id)
    request = review_for(store, source_id)
    first = store.mutate(request)
    assert store.mutate(request) == first
    full(store, other)
    assert photo_accepted(store.read(), store.catalog.sources[source_id])
    # Stale photo map must fail even with a refreshed global CAS revision.
    stale = review_for(store, source_id)
    full(store, source_id, 1)
    assert not photo_accepted(store.read(), store.catalog.sources[source_id])
    with pytest.raises(ValueError, match="REVISION_CONFLICT"):
        store.mutate(stale)
    stale.expected_revision = store.read().revision
    with pytest.raises(ValueError, match="GEOMETRY_CHANGED"):
        store.mutate(stale)
    wrong = review_for(store, source_id)
    wrong.source_sha256 = "0" * 64
    with pytest.raises(ValueError, match="SOURCE_CHANGED"):
        store.mutate(wrong)
    # Retrying an old accepted command after geometry changes never reaccepts it.
    assert not photo_accepted(store.mutate(request), store.catalog.sources[source_id])


def test_restart_backup_and_rebase_preserve_review_and_history(tmp_path):
    store = setup_store(tmp_path)
    source_id = next(iter(store.catalog.sources))
    full(store, source_id)
    store.mutate(review_for(store, source_id, "mark", [0], "uwaga"))
    full(store, source_id)
    store.mutate(review_for(store, source_id))
    backup = store.backup()
    restored = store.restore(backup.backup_id, tmp_path / "restore")
    assert restored.read() == store.read()
    assert read_checked(restored.root / "state.json") == read_checked(store.root / "state.json")
    code = (
        "from pathlib import Path; import sys; "
        "from game_predictor_worker.vision_lab.annotations import AnnotationStore; "
        "from game_predictor_worker.vision_lab.catalog import Catalog; "
        "print(AnnotationStore(Path(sys.argv[1]), Catalog(Path(sys.argv[2])))"
        ".read().model_dump_json())"
    )
    process = subprocess.run(
        [sys.executable, "-c", code, str(restored.root), str(store.catalog.root)],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert json.loads(process.stdout) == restored.read().model_dump()
    Image.new("RGB", (121, 81), (247, 113, 76)).save(tmp_path / "input" / "ordinary" / "added.jpg")
    new = import_folder(tmp_path / "input", tmp_path / "snapshots")
    destination = tmp_path / "rebase"
    rebase_annotations(store.catalog.root, new, store.root, destination, apply=True)
    expected = read_checked(store.root / "state.json")
    expected["state"]["snapshot_id"] = AnnotationStore(destination, Catalog(new)).snapshot_id
    assert read_checked(destination / "state.json") == expected
    assert photo_accepted(
        AnnotationStore(destination, Catalog(new)).read(), store.catalog.sources[source_id]
    )


def test_http_review_uses_existing_annotation_route_and_boundary(tmp_path):
    store = setup_store(tmp_path)
    source_id = next(iter(store.catalog.sources))
    full(store, source_id)
    request = review_for(store, source_id)
    client = TestClient(create_app(store.catalog, store.root), base_url="http://127.0.0.1:8102")
    assert client.post("/annotations", json=request.model_dump()).status_code == 403
    headers = {"Origin": "http://127.0.0.1:3102"}
    response = client.post("/annotations", json=request.model_dump(), headers=headers)
    assert response.status_code == 200 and response.json()["photo_reviews"][source_id][
        "accepted_board_revisions"
    ] == {"0": 1}
    assert (
        client.post("/annotations", json=request.model_dump(), headers=headers).json()
        == response.json()
    )


def test_review_is_additional_split_gate_and_mark_keeps_frozen_assignments(tmp_path):
    store = setup_store(tmp_path)
    split_request = populate(store)
    state = store.read()
    source_id = split_request.measurement_source_ids[0]
    store.mutate(review_for(store, source_id, "mark", [0]))
    split_request.expected_revision = store.read().revision
    with pytest.raises(ValueError, match="MEASUREMENT"):
        store.mutate(split_request)
    store.mutate(review_for(store, source_id, "withdraw", [0]))
    store.mutate(review_for(store, source_id))
    split_request.expected_revision = store.read().revision
    frozen = store.mutate(split_request)
    assert frozen.split and not frozen.split_stale
    marked = store.mutate(review_for(store, source_id, "mark", [0]))
    assert marked.split_stale and marked.split == frozen.split
    assert all(store.catalog.sources[s].role == "data" for s in frozen.split.assignments)
    assert state.annotations == marked.annotations


def test_legacy_split_gate_is_consistent_on_read_retry_and_mutation(tmp_path):
    store = setup_store(tmp_path)
    split_request = populate(store)
    store.mutate(split_request)
    payload = read_checked(store.root / "state.json")
    payload["state"].pop("photo_reviews")
    payload["state"]["split_stale"] = False
    write_atomic(store.root / "state.json", payload)
    original = (store.root / "state.json").read_bytes()
    assert store.read().split_stale
    assert store.mutate(split_request).split_stale
    assert (store.root / "state.json").read_bytes() == original
    source_id = split_request.measurement_source_ids[0]
    assert store.mutate(review_for(store, source_id)).split_stale
