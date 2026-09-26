"""Rebinding only unchanged sources, preserving complete durable decisions."""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from game_predictor_worker.vision_lab.annotation_contracts import (
    AnnotationRequest,
    GeometryAnnotation,
)
from game_predictor_worker.vision_lab.annotations import (
    AnnotationStore,
    interpolate,
    read_checked,
    write_atomic,
)
from game_predictor_worker.vision_lab.catalog import Catalog
from game_predictor_worker.vision_lab.contracts import Point, Topology
from game_predictor_worker.vision_lab.rebase_annotations import rebase_annotations
from game_predictor_worker.vision_lab.snapshot import import_folder
from PIL import Image


def setup_rebase(tmp_path: Path):
    folder = tmp_path / "input"
    for game in ("777", "ordinary"):
        (folder / game).mkdir(parents=True)
        Image.new("RGB", (121, 81), (20, 30, 40)).save(folder / game / "one.jpg")
    old = import_folder(folder, tmp_path / "snapshots")
    store = AnnotationStore(tmp_path / "annotations", Catalog(old))
    source = next(s for s in store.catalog.sources.values() if s.game_name == "777")
    corners = [Point(x=10, y=10), Point(x=110, y=10), Point(x=110, y=70), Point(x=10, y=70)]
    nodes = interpolate(corners, Topology(columns=5))
    for point in nodes:
        point.provenance = "human"
    request = AnnotationRequest(
        request_id="original-request",
        expected_revision=0,
        actor="original-human",
        annotation=GeometryAnnotation(
            source_id=source.id,
            board_index=0,
            topology=Topology(columns=5),
            corners=corners,
            nodes=nodes,
        ),
        action="approve_full",
        reviewed_all_nodes=True,
        activity_intervals_ms=[1000, 2000],
        correction_count=3,
    )
    store.mutate(request)
    # A new unrelated image changes the catalog without changing referenced metadata.
    Image.new("RGB", (121, 81), (60, 70, 80)).save(folder / "ordinary" / "new.jpg")
    new = import_folder(folder, tmp_path / "snapshots")
    return old, new, store, request


def test_preserves_full_payload_preflight_retry_and_new_process(tmp_path: Path):
    old, new, store, request = setup_rebase(tmp_path)
    destination = tmp_path / "new-annotations"
    original_bytes = (store.root / "state.json").read_bytes()
    before = read_checked(store.root / "state.json")
    report = rebase_annotations(old, new, store.root, destination)
    assert report["status"] == "ready" and not destination.exists()
    assert report["preserved_history_events"] == 1
    result = rebase_annotations(old, new, store.root, destination, apply=True)
    assert result["status"] == "applied"
    expected = copy.deepcopy(before)
    expected["state"]["snapshot_id"] = AnnotationStore(destination, Catalog(new)).snapshot_id
    assert read_checked(destination / "state.json") == expected
    assert (store.root / "state.json").read_bytes() == original_bytes
    assert (
        rebase_annotations(old, new, store.root, destination, apply=True)["status"]
        == "already_applied"
    )
    restored = AnnotationStore(destination, Catalog(new))
    assert restored.mutate(request).revision == 1  # preserved receipt, no reapproval
    assert (
        restored.read().annotations[next(iter(restored.read().annotations))].actor
        == "original-human"
    )
    code = (
        "from pathlib import Path; import sys; "
        "from game_predictor_worker.vision_lab.annotations import AnnotationStore; "
        "from game_predictor_worker.vision_lab.catalog import Catalog; "
        "store = AnnotationStore(Path(sys.argv[1]), Catalog(Path(sys.argv[2]))); "
        "print(store.read().model_dump_json())"
    )
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")}
    process = subprocess.run(
        [sys.executable, "-c", code, str(destination), str(new)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert json.loads(process.stdout) == expected["state"]


@pytest.mark.parametrize("history_only", [False, True])
def test_changed_referenced_source_is_blocked_including_history(tmp_path: Path, history_only: bool):
    old, _, store, _ = setup_rebase(tmp_path)
    if history_only:
        payload = read_checked(store.root / "state.json")
        payload["state"]["annotations"] = {}
        payload["state"]["timings"] = []
        write_atomic(store.root / "state.json", payload)
    Image.new("RGB", (121, 81), (100, 30, 40)).save(tmp_path / "input" / "777" / "one.jpg")
    changed = import_folder(tmp_path / "input", tmp_path / "snapshots")
    destination = tmp_path / "rejected"
    with pytest.raises(ValueError, match="REFERENCED_SOURCE_CHANGED"):
        rebase_annotations(old, changed, store.root, destination, apply=True)
    assert not destination.exists()


def test_existing_destination_and_newer_state_are_never_overwritten(tmp_path: Path):
    old, new, store, request = setup_rebase(tmp_path)
    destination = tmp_path / "existing"
    destination.mkdir()
    with pytest.raises(ValueError, match="DESTINATION_CONFLICT"):
        rebase_annotations(old, new, store.root, destination, apply=True)
    assert list(destination.iterdir()) == []
    destination = tmp_path / "new"
    rebase_annotations(old, new, store.root, destination, apply=True)
    newer = request.model_copy(deep=True)
    newer.request_id = "newer-request"
    newer.expected_revision = 1
    newer.action = "draft"
    AnnotationStore(destination, Catalog(new)).mutate(newer)
    latest = (destination / "state.json").read_bytes()
    with pytest.raises(ValueError, match="DESTINATION_CONFLICT"):
        rebase_annotations(old, new, store.root, destination, apply=True)
    assert (destination / "state.json").read_bytes() == latest


@pytest.mark.parametrize("location", ["state", "history"])
def test_split_or_family_history_fails_closed(tmp_path: Path, location: str):
    old, new, store, _ = setup_rebase(tmp_path)
    payload = read_checked(store.root / "state.json")
    if location == "state":
        payload["state"]["split_stale"] = True
    else:
        payload["history"][0]["family"] = {"source_ids": []}
    write_atomic(store.root / "state.json", payload)
    with pytest.raises(ValueError, match="FAMILIES_OR_SPLIT"):
        rebase_annotations(old, new, store.root, tmp_path / "blocked")


def test_metadata_change_is_not_hidden_by_same_image_bytes(tmp_path: Path):
    old, _, store, _ = setup_rebase(tmp_path)
    # Same bytes under a new name changes duplicate metadata of the approved source.
    image = tmp_path / "input" / "777" / "one.jpg"
    (tmp_path / "input" / "ordinary" / "copy.jpg").write_bytes(image.read_bytes())
    new = import_folder(tmp_path / "input", tmp_path / "snapshots")
    with pytest.raises(ValueError, match="REFERENCED_SOURCE_CHANGED"):
        rebase_annotations(old, new, store.root, tmp_path / "blocked")


def test_apply_rereads_latest_source_after_preflight_and_retry_detects_drift(tmp_path: Path):
    old, new, store, request = setup_rebase(tmp_path)
    destination = tmp_path / "destination"
    assert rebase_annotations(old, new, store.root, destination)["revision"] == 1
    updated = request.model_copy(deep=True)
    updated.request_id = "later-source-request"
    updated.expected_revision = 1
    updated.annotation.board_index = 1
    store.mutate(updated)
    assert rebase_annotations(old, new, store.root, destination, apply=True)["revision"] == 2
    before = (destination / "state.json").read_bytes()
    updated.request_id = "after-rebase-request"
    updated.expected_revision = 2
    store.mutate(updated)
    with pytest.raises(ValueError, match="DESTINATION_CONFLICT"):
        rebase_annotations(old, new, store.root, destination, apply=True)
    assert (destination / "state.json").read_bytes() == before


def test_destination_overlap_is_rejected_without_writes(tmp_path: Path):
    old, new, store, _ = setup_rebase(tmp_path)
    before = (store.root / "state.json").read_bytes()
    for destination in (store.root, store.root / "nested", old / "nested", new, tmp_path):
        with pytest.raises(ValueError, match="PATH_OVERLAP"):
            rebase_annotations(old, new, store.root, destination, apply=True)
    assert (store.root / "state.json").read_bytes() == before
    assert not (store.root / "nested").exists()
