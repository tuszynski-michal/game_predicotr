"""Whole-game pilot preserves unresolved evidence and all catalog leakage links."""

import pytest
from fastapi.testclient import TestClient
from game_predictor_worker.vision_lab.annotation_contracts import (
    GeometryQualificationBinding,
    GeometryQualificationRequest,
    SplitRequest,
)
from game_predictor_worker.vision_lab.annotations import AnnotationStore, read_checked, write_atomic
from game_predictor_worker.vision_lab.api import create_app
from game_predictor_worker.vision_lab.catalog import Catalog
from game_predictor_worker.vision_lab.geometry_qualification import WHOLE_GAME_PILOT_POLICY
from game_predictor_worker.vision_lab.photo_review import board_revisions
from game_predictor_worker.vision_lab.snapshot import import_folder
from game_predictor_worker.vision_lab.splits import freeze_splits
from PIL import Image
from test_vision_lab_annotations import approve_full_photo
from test_vision_lab_geometry_cohort import family, retry_new_process


def pilot_store(tmp_path):
    roles = {
        "777": "development",
        "ordinary": "development",
        "validation": "validation",
        "final": "final_test",
        "unseen": "unseen_game",
    }
    for index, game in enumerate(roles):
        folder = tmp_path / "input" / game
        folder.mkdir(parents=True)
        for frame in range(2):
            Image.new("RGB", (121, 81), (index * 40, frame * 40, 30)).save(
                folder / f"image{frame}.jpg"
            )
    catalog = Catalog(import_folder(tmp_path / "input", tmp_path / "snapshots"))
    store = AnnotationStore(tmp_path / "annotations", catalog)
    selected = [
        source.id for source in catalog.sources.values() if source.filename.endswith("image0.jpg")
    ]
    for source_id in selected:
        approve_full_photo(store, source_id)
    historical = next(
        s for s in catalog.sources.values() if s.game_name == "777" and s.id in selected
    )
    state = store.read()
    store.mutate(
        GeometryQualificationRequest(
            request_id="qualified-777",
            expected_revision=state.revision,
            actor="operator",
            game_id=historical.game_id,
            policy_version="historical-777-lab-geometry-v1",
            purpose="geometry",
            decision_reference="D-453",
            bindings=[
                GeometryQualificationBinding(
                    source_id=historical.id,
                    source_sha256=historical.sha256,
                    expected_board_revisions=board_revisions(state, historical.id),
                )
            ],
        )
    )
    ordinary = [s.id for s in catalog.sources.values() if s.game_name == "ordinary"]
    family(store, ordinary, provenance="unresolved")
    family(
        store,
        [s.id for s in catalog.sources.values() if s.game_name == "777"],
        provenance="unresolved",
    )
    request = SplitRequest(
        request_id="freeze-pilot",
        expected_revision=store.read().revision,
        actor="operator",
        purpose="geometry",
        geometry_policy=WHOLE_GAME_PILOT_POLICY,
        geometry_source_ids=selected,
        seed=17,
        unseen_game_id=next(s.game_id for s in catalog.sources.values() if s.game_name == "unseen"),
        game_partitions={s.game_id: roles[s.game_name] for s in catalog.sources.values()},
    )
    return store, request


def test_pilot_freezes_whole_games_without_promoting_families_or_context(tmp_path):
    store, request = pilot_store(tmp_path)
    before = store.read()
    result = store.mutate(request)
    split = result.split
    assert split.policy_version == WHOLE_GAME_PILOT_POLICY
    assert split.game_partitions == request.game_partitions and split.measurement == {}
    assert set(split.assignments) == set(request.geometry_source_ids)
    assert set(split.assignments.values()) == {
        "development",
        "validation",
        "final_test",
        "unseen_game",
    }
    assert all(
        split.assignments[s] == request.game_partitions[store.catalog.sources[s].game_id]
        for s in split.assignments
    )
    assert all(reason == "NOT_IN_GEOMETRY_COHORT" for reason in split.exclusions.values())
    assert {s for ids in split.leakage_components.values() for s in ids} == set(
        store.catalog.sources
    )
    assert result.families == before.families and all(
        f.provenance == "unresolved" for f in result.families.values()
    )
    assert result.annotations == before.annotations and result.photo_reviews == before.photo_reviews
    assert (
        result.geometry_qualifications == before.geometry_qualifications
        and result.timings == before.timings
    )
    assert not store.read().split_stale
    assert retry_new_process(store, request) == split.fingerprint
    restored = store.restore(store.backup().backup_id, tmp_path / "restored")
    assert restored.read() == result
    assert retry_new_process(restored, request) == split.fingerprint
    changed = request.model_copy(deep=True)
    changed.game_partitions = dict(reversed(list(changed.game_partitions.items())))
    # JSON object ordering is immaterial; the target-list ordering is not.
    assert store.mutate(changed) == result
    changed.game_partitions[request.unseen_game_id] = "validation"
    with pytest.raises(ValueError, match="REQUEST_ID_CONFLICT"):
        store.mutate(changed)
    with pytest.raises(ValueError, match="SPLIT_ALREADY_FROZEN"):
        store.mutate(
            request.model_copy(
                update={"request_id": "second-freeze", "expected_revision": result.revision}
            )
        )


def test_pilot_http_rejects_invalid_maps_measurement_and_combinations_atomically(tmp_path):
    store, request = pilot_store(tmp_path)
    client = TestClient(create_app(store.catalog, store.root), base_url="http://127.0.0.1:8102")
    headers = {"Origin": "http://127.0.0.1:3102"}
    before = (store.root / "state.json").read_bytes()
    unseen = next(
        s.id
        for s in store.catalog.sources.values()
        if s.game_name == "unseen" and s.id in request.geometry_source_ids
    )
    variants = [
        ({"game_partitions": None}, "PILOT_GAME_PARTITIONS_REQUIRED"),
        ({"game_partitions": {}}, "PILOT_GAME_PARTITIONS_INVALID"),
        (
            {"game_partitions": {**request.game_partitions, "unknown": "development"}},
            "PILOT_GAME_PARTITIONS_INVALID",
        ),
        (
            {"game_partitions": dict.fromkeys(request.game_partitions, "development")},
            "PILOT_GAME_PARTITIONS_INVALID",
        ),
        ({"unseen_game_id": "missing"}, "PILOT_GAME_PARTITIONS_INVALID"),
        (
            {"geometry_source_ids": [s for s in request.geometry_source_ids if s != unseen]},
            "PILOT_GAME_PARTITIONS_INVALID",
        ),
        ({"geometry_source_ids": []}, "GEOMETRY_COHORT_EMPTY"),
        ({"geometry_source_ids": None}, "GEOMETRY_POLICY_COHORT_REQUIRED"),
        (
            {"geometry_source_ids": request.geometry_source_ids + [unseen]},
            "GEOMETRY_COHORT_DUPLICATE_SOURCE",
        ),
        ({"geometry_source_ids": ["unknown"]}, "GEOMETRY_COHORT_SOURCE_NOT_FOUND"),
        ({"purpose": "legacy"}, "GEOMETRY_POLICY_PURPOSE_REQUIRED"),
        ({"geometry_policy": None}, "PILOT_GAME_PARTITIONS_INVALID"),
        (
            {"geometry_policy": "lab-geometry-cohort-777-targets-v2"},
            "PILOT_GAME_PARTITIONS_INVALID",
        ),
        ({"measurement_source_ids": [unseen]}, "PILOT_MEASUREMENT_NOT_SUPPORTED"),
        ({"difficulties": {unseen: "normal"}}, "PILOT_MEASUREMENT_NOT_SUPPORTED"),
    ]
    for changes, reason in variants:
        response = client.post("/splits", json={**request.model_dump(), **changes}, headers=headers)
        assert response.status_code == 409 and reason in response.text
        assert (store.root / "state.json").read_bytes() == before
    response = client.post(
        "/splits",
        json={**request.model_dump(), "game_partitions": {"x": "measurement"}},
        headers=headers,
    )
    assert response.status_code == 422
    assert (store.root / "state.json").read_bytes() == before
    response = client.post("/splits", json=request.model_dump(), headers=headers)
    assert (
        response.status_code == 200
        and response.json()["split"]["game_partitions"] == request.game_partitions
    )


def test_pilot_rejects_bad_target_without_shrinking_cohort(tmp_path):
    store, request = pilot_store(tmp_path)
    target = next(
        s
        for s in store.catalog.sources.values()
        if s.game_name == "ordinary" and s.id in request.geometry_source_ids
    )
    for problem, reason in [
        ("review", "PHOTO_REVIEW_ACCEPTANCE_REQUIRED"),
        ("nodes", "PILOT_FULL_GEOMETRY_REQUIRED"),
        ("qualification", "COMPARISON_OR_777_PROVENANCE_UNRESOLVED"),
    ]:
        state = store.read()
        if problem == "review":
            state.photo_reviews[target.id].rejected = True
        elif problem == "nodes":
            state.annotations[f"{target.id}:0"].nodes[0].provenance = "interpolated"
        else:
            state.geometry_qualifications.clear()
        with pytest.raises(ValueError, match=reason):
            freeze_splits(store.catalog, state, request)
    approve_full_photo(store, target.id, columns=3)
    request.expected_revision = store.read().revision
    before = (store.root / "state.json").read_bytes()
    with pytest.raises(ValueError, match="PILOT_TOPOLOGY_NOT_SUPPORTED"):
        store.mutate(request)
    assert (store.root / "state.json").read_bytes() == before


def test_pilot_detects_cross_partition_sha_and_transitive_context_without_targets(tmp_path):
    store, request = pilot_store(tmp_path)
    contexts = {
        s.game_name: s
        for s in store.catalog.sources.values()
        if s.id not in request.geometry_source_ids
    }
    left, bridge, right = contexts["validation"], contexts["777"], contexts["final"]
    store.catalog.sources[right.id] = right.model_copy(update={"sha256": left.sha256})
    with pytest.raises(ValueError, match="PILOT_CROSS_PARTITION_COMPONENT"):
        freeze_splits(store.catalog, store.read(), request)
    store.catalog.sources[right.id] = right
    family(store, [left.id], related=[bridge.id], provenance="unresolved")
    family(store, [bridge.id], related=[right.id], provenance="unresolved")
    request.expected_revision = store.read().revision
    before = (store.root / "state.json").read_bytes()
    with pytest.raises(ValueError, match="PILOT_CROSS_PARTITION_COMPONENT"):
        store.mutate(request)
    assert (store.root / "state.json").read_bytes() == before


def test_pilot_stale_checks_remote_context_map_and_current_targets(tmp_path):
    store, request = pilot_store(tmp_path)
    frozen = store.mutate(request).split
    original = read_checked(store.root / "state.json")
    context = next(
        s
        for s in store.catalog.sources.values()
        if s.game_name == "final" and s.id not in request.geometry_source_ids
    )
    target = next(iter(original["state"]["geometry_qualifications"]))
    for drift in ("source", "map", "qualification", "nodes", "assignments"):
        payload = read_checked(store.root / "state.json")
        if drift == "source":
            store.catalog.sources[context.id] = context.model_copy(
                update={"filename": "final/renamed.jpg"}
            )
        elif drift == "map":
            payload["state"]["split"]["game_partitions"][context.game_id] = "development"
        elif drift == "qualification":
            payload["state"]["geometry_qualifications"][target]["actor"] = "changed"
        elif drift == "nodes":
            payload["state"]["annotations"][f"{target}:0"]["nodes"][0]["x"] += 1
        else:
            payload["state"]["split"]["assignments"][target] = "validation"
        write_atomic(store.root / "state.json", payload)
        stored_split = store.read().split
        assert store.read().split_stale
        assert store.read().split == stored_split
        store.catalog.sources[context.id] = context
        write_atomic(store.root / "state.json", original)
    # A disconnected, unselected group's new evidence still invalidates the pilot.
    family(store, [context.id], provenance="unresolved")
    assert store.read().split_stale and store.read().split == frozen
    assert store.mutate(request).split_stale
