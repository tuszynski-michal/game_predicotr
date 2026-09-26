"""Durability and provenance regressions using isolated tiny fixtures."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from game_predictor_worker.vision_lab.annotation_contracts import (
    AnnotationRequest,
    FamilyDecision,
    FamilyRequest,
    GeometryAnnotation,
    SplitRequest,
)
from game_predictor_worker.vision_lab.annotations import (
    AnnotationStore,
    active_time,
    interpolate,
    read_checked,
)
from game_predictor_worker.vision_lab.api import create_app
from game_predictor_worker.vision_lab.catalog import Catalog
from game_predictor_worker.vision_lab.contracts import Point, Topology
from game_predictor_worker.vision_lab.snapshot import import_folder
from PIL import Image


def setup_store(tmp_path: Path) -> AnnotationStore:
    for game, count in (("ordinary", 7), ("unseen", 1), ("777", 1)):
        directory = tmp_path / "input" / game
        directory.mkdir(parents=True)
        for i in range(count):
            Image.new("RGB", (121, 81), (i * 20, len(game) * 20, 30)).save(
                directory / f"name{i}.jpg"
            )
    catalog = Catalog(import_folder(tmp_path / "input", tmp_path / "snapshots"))
    return AnnotationStore(tmp_path / "annotations", catalog)


def request_for(store: AnnotationStore, source_id: str, columns=5, action="approve_location"):
    corners = [Point(x=10, y=10), Point(x=110, y=10), Point(x=110, y=70), Point(x=10, y=70)]
    return AnnotationRequest(
        request_id=f"request-{store.read().revision}",
        expected_revision=store.read().revision,
        actor="human-test",
        annotation=GeometryAnnotation(
            source_id=source_id, board_index=0, topology=Topology(columns=columns), corners=corners
        ),
        action=action,
    )


def test_layers_restart_retry_backup_and_corruption(tmp_path: Path):
    store = setup_store(tmp_path)
    source_id = next(iter(store.catalog.sources))
    request = request_for(store, source_id)
    first = store.mutate(request)
    assert first.annotations[f"{source_id}:0"].location_approved
    assert not first.annotations[f"{source_id}:0"].full_approved
    assert store.mutate(request) == first  # lost response
    restarted = AnnotationStore(store.root, store.catalog)
    assert restarted.read() == first
    backup = store.backup()
    restored = store.restore(backup.backup_id, tmp_path / "restored")
    assert restored.read() == first
    with pytest.raises(ValueError, match="NEW_DESTINATION"):
        store.restore(backup.backup_id, restored.root)
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")}
    code = (
        "from pathlib import Path; "
        "from game_predictor_worker.vision_lab.annotations import AnnotationStore; "
        "from game_predictor_worker.vision_lab.catalog import Catalog; import sys; "
        "print(AnnotationStore(Path(sys.argv[1]),Catalog(Path(sys.argv[2]))).read().revision)"
    )
    snapshot = next((tmp_path / "snapshots").iterdir())
    result = subprocess.run(
        [sys.executable, "-c", code, str(restored.root), str(snapshot)],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        check=True,
    )
    assert result.stdout.strip() == "1"
    (restored.root / "state.json").write_text('{"broken":true}')
    with pytest.raises(ValueError, match="INTEGRITY"):
        restored.read()
    (store.root / "backups" / f"{backup.backup_id}.json").write_text("{}")
    with pytest.raises(ValueError, match="INTEGRITY"):
        store.restore(backup.backup_id, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()


@pytest.mark.parametrize("columns,count", [(3, 16), (5, 24)])
def test_explicit_full_approval_and_revision_invalidates(tmp_path: Path, columns, count):
    store = setup_store(tmp_path)
    source_id = next(iter(store.catalog.sources))
    request = request_for(store, source_id, columns, "approve_full")
    with pytest.raises(ValueError, match="FULL_NODE_REVIEW"):
        store.mutate(request)
    request.reviewed_all_nodes = True
    request.annotation.nodes = interpolate(request.annotation.corners, request.annotation.topology)
    with pytest.raises(ValueError, match="FULL_NODE_REVIEW"):
        store.mutate(request)
    for point in request.annotation.nodes:
        point.provenance = "human"
    full = store.mutate(request).annotations[f"{source_id}:0"]
    assert len(full.nodes) == count and full.full_approved
    draft = request_for(store, source_id, columns, "draft")
    draft.annotation.corners[0].x += 1
    updated = store.mutate(draft).annotations[f"{source_id}:0"]
    assert not updated.full_approved and not updated.location_approved
    assert updated.revision == 2 and updated.geometry_sha256 != full.geometry_sha256
    historical = read_checked(store.root / "state.json")["history"][0]["annotation"]
    assert historical == full.model_dump()
    backup = store.backup()
    restored = store.restore(backup.backup_id, tmp_path / "history-restored")
    assert read_checked(restored.root / "state.json")["history"][0]["annotation"] == historical
    with pytest.raises(ValueError, match="REQUEST_ID_CONFLICT"):
        request.actor = "someone-else"
        store.mutate(request)


def test_concurrent_cas_and_activity(tmp_path: Path):
    store = setup_store(tmp_path)
    source_id = next(iter(store.catalog.sources))
    a = request_for(store, source_id)
    a.activity_intervals_ms = [1000, 30000, 30001, 2500]
    b = a.model_copy(deep=True)
    b.request_id = "different-id"

    def write(request):
        try:
            AnnotationStore(store.root, store.catalog).mutate(request)
            return "ok"
        except ValueError as error:
            return str(error)

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(write, [a, b]))
    assert results.count("ok") == 1
    assert any("BUSY" in r or "REVISION_CONFLICT" in r for r in results)
    assert active_time(a.activity_intervals_ms) == 33500
    assert store.read().timings[0].active_ms == 33500


def populate(store):
    for source_id, source in store.catalog.sources.items():
        if source.role != "data":
            continue
        store.mutate(request_for(store, source_id))
        revision = store.read().revision
        store.mutate(
            FamilyRequest(
                request_id=f"family-{revision}",
                expected_revision=revision,
                actor="human",
                decision=FamilyDecision(
                    source_ids=[source_id],
                    family_id=source_id,
                    evidence="Original recording manually verified",
                    provenance="verified",
                ),
            )
        )
    ordinary = [s.id for s in store.catalog.sources.values() if s.game_name == "ordinary"]
    unseen = next(s.game_id for s in store.catalog.sources.values() if s.game_name == "unseen")
    return SplitRequest(
        request_id="freeze-first",
        expected_revision=store.read().revision,
        actor="human",
        unseen_game_id=unseen,
        seed=17,
        measurement_source_ids=ordinary[:2],
        difficulties=dict.fromkeys(ordinary[:2], "normal"),
    )


def test_freeze_is_immutable_after_draft_or_family_change(tmp_path: Path):
    store = setup_store(tmp_path)
    request = populate(store)
    frozen = store.mutate(request)
    assert frozen.split and not frozen.split_stale
    assert {"development", "validation", "final_test", "unseen_game", "measurement"} == set(
        frozen.split.assignments.values()
    )
    assert set(frozen.split.measurement.values()) == {"baseline", "hybrid"}
    historical = next(s.id for s in store.catalog.sources.values() if s.role == "comparison_only")
    assert historical in frozen.split.exclusions and historical not in frozen.split.assignments
    source_id = next(iter(frozen.split.assignments))
    changed = store.mutate(request_for(store, source_id, action="draft"))
    assert changed.split == frozen.split and changed.split_stale
    request.request_id = "refreeze-attempt"
    request.expected_revision = changed.revision
    request.seed = 99
    with pytest.raises(ValueError, match="ALREADY_FROZEN"):
        store.mutate(request)
    revision = changed.revision
    family = FamilyRequest(
        request_id="changed-family",
        expected_revision=revision,
        actor="human",
        decision=FamilyDecision(
            source_ids=[source_id],
            family_id="new-family",
            evidence="Changed evidence",
            provenance="unresolved",
        ),
    )
    assert store.mutate(family).split == frozen.split


def test_unresolved_777_and_transitive_relations_fail_closed(tmp_path: Path):
    store = setup_store(tmp_path)
    request = populate(store)
    ordinary = [s.id for s in store.catalog.sources.values() if s.game_name == "ordinary"]
    revision = store.read().revision
    # A links B; B links C. C unresolved excludes the whole component.
    for index in range(2):
        store.mutate(
            FamilyRequest(
                request_id=f"linking-{index}",
                expected_revision=revision,
                actor="human",
                decision=FamilyDecision(
                    source_ids=[ordinary[index]],
                    related_source_ids=[ordinary[index + 1]],
                    family_id=f"group-{index}",
                    evidence="Related derivative verified",
                    provenance="verified",
                ),
            )
        )
        revision += 1
    store.mutate(
        FamilyRequest(
            request_id="unresolved-last",
            expected_revision=revision,
            actor="human",
            decision=FamilyDecision(
                source_ids=[ordinary[2]],
                family_id="other",
                evidence="Unknown origin",
                provenance="unresolved",
            ),
        )
    )
    request.expected_revision = store.read().revision
    with pytest.raises(ValueError, match="MEASUREMENT"):
        store.mutate(request)
    v2 = FamilyRequest(
        request_id="cannot-verify-777",
        expected_revision=store.read().revision,
        actor="human",
        decision=FamilyDecision(
            source_ids=[ordinary[0]],
            family_id="v2",
            evidence="Declaration alone",
            provenance="777_v2_verified",
            checksum_reviewed=True,
            similarity_reviewed=True,
        ),
    )
    with pytest.raises(ValueError, match="SIMILARITY_EVIDENCE_NOT_IMPLEMENTED"):
        store.mutate(v2)


def test_http_roundtrip_and_boundaries(tmp_path: Path):
    store = setup_store(tmp_path)
    client = TestClient(create_app(store.catalog, store.root), base_url="http://127.0.0.1:8102")
    source_id = next(iter(store.catalog.sources))
    request = request_for(store, source_id)
    headers = {"Origin": "http://127.0.0.1:3102"}
    assert client.get("/annotations").json()["revision"] == 0
    response = client.post("/annotations", json=request.model_dump(), headers=headers)
    assert response.status_code == 200 and response.json()["revision"] == 1
    assert (
        client.post("/annotations", json=request.model_dump(), headers=headers).json()
        == response.json()
    )
    assert client.post("/annotations", json=request.model_dump()).status_code == 403
    assert client.post("/families", content="{}", headers=headers).status_code == 415
    assert client.post("/backups", json={}, headers=headers).status_code == 200
    assert client.get("/timings").status_code == 200
    no_config = TestClient(create_app(store.catalog), base_url="http://127.0.0.1:8102")
    assert no_config.get("/annotations").status_code == 503


def test_identical_bytes_and_derivatives_cannot_cross_partitions(tmp_path: Path):
    original = setup_store(tmp_path)
    folder = tmp_path / "input" / "ordinary"
    (folder / "different-name.jpg").write_bytes((folder / "name0.jpg").read_bytes())
    catalog = Catalog(import_folder(tmp_path / "input", tmp_path / "snapshots"))
    store = AnnotationStore(tmp_path / "with-duplicate", catalog)
    request = populate(store)
    by_name = {s.filename: s.id for s in catalog.sources.values()}
    a, b = by_name["ordinary/name1.jpg"], by_name["ordinary/name2.jpg"]
    store.mutate(
        FamilyRequest(
            request_id="related-pair",
            expected_revision=store.read().revision,
            actor="human",
            decision=FamilyDecision(
                source_ids=[a],
                related_source_ids=[b],
                family_id="derivatives",
                evidence="Same original recording",
                provenance="verified",
            ),
        )
    )
    request.expected_revision = store.read().revision
    request.measurement_source_ids = [by_name["ordinary/name5.jpg"], by_name["ordinary/name6.jpg"]]
    request.difficulties = dict.fromkeys(request.measurement_source_ids, "normal")
    split = store.mutate(request).split
    assert split is not None
    assert split.assignments[a] == split.assignments[b]
    assert (
        split.assignments[by_name["ordinary/name0.jpg"]]
        == split.assignments[by_name["ordinary/different-name.jpg"]]
    )
    assert original.root != store.root


def test_absent_board_does_not_supply_topology_coverage(tmp_path: Path):
    store = setup_store(tmp_path)
    request = populate(store)
    unseen = next(s.id for s in store.catalog.sources.values() if s.game_name == "unseen")
    store.mutate(request_for(store, unseen, columns=3))
    for source in store.catalog.sources.values():
        if source.game_name != "ordinary":
            continue
        observation = request_for(store, source.id, columns=3)
        observation.annotation.board_index = 1
        observation.annotation.presence = "absent"
        observation.annotation.corners = []
        store.mutate(observation)
    request.expected_revision = store.read().revision
    with pytest.raises(ValueError, match="REMOVES_TRAINING_TOPOLOGY"):
        store.mutate(request)
