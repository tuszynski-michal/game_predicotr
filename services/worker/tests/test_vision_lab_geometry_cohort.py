"""A target cohort never removes unselected sources from the leakage graph."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from game_predictor_worker.vision_lab.annotation_contracts import (
    FamilyDecision,
    FamilyRequest,
    SplitRequest,
)
from game_predictor_worker.vision_lab.annotations import (
    AnnotationStore,
    digest,
    read_checked,
    write_atomic,
)
from game_predictor_worker.vision_lab.api import create_app
from game_predictor_worker.vision_lab.catalog import Catalog
from game_predictor_worker.vision_lab.snapshot import import_folder
from game_predictor_worker.vision_lab.splits import (
    build_components,
    component_fingerprints,
    freeze_splits,
)
from test_vision_lab_annotations import approve_full_photo, populate, setup_store
from test_vision_lab_geometry_qualification import prepared, verified_family


def family(store, ids, *, related=(), provenance="verified"):
    return store.mutate(
        FamilyRequest(
            request_id=f"family-{store.read().revision}",
            expected_revision=store.read().revision,
            actor="human-test",
            decision=FamilyDecision(
                source_ids=ids,
                related_source_ids=list(related),
                family_id=ids[0],
                evidence="Explicit recording evidence",
                provenance=provenance,
            ),
        )
    )


def cohort_store(tmp_path):
    setup_store(tmp_path)
    folder = tmp_path / "input" / "ordinary"
    (folder / "alias.jpg").write_bytes((folder / "name6.jpg").read_bytes())
    catalog = Catalog(import_folder(tmp_path / "input", tmp_path / "snapshots"))
    store = AnnotationStore(tmp_path / "cohort", catalog)
    by_name = {source.filename: source.id for source in catalog.sources.values()}
    alias = by_name["ordinary/alias.jpg"]
    selected = []
    for source in catalog.sources.values():
        if source.role != "data":
            continue
        if source.id != alias:
            approve_full_photo(store, source.id)
            selected.append(source.id)
        family(store, [source.id])
    measure = [by_name[f"ordinary/name{i}.jpg"] for i in (0, 1)]
    request = SplitRequest(
        request_id="cohort-freeze",
        expected_revision=store.read().revision,
        actor="operator",
        purpose="geometry",
        geometry_source_ids=selected,
        unseen_game_id=catalog.sources[by_name["unseen/name0.jpg"]].game_id,
        seed=17,
        measurement_source_ids=measure,
        difficulties=dict.fromkeys(measure, "normal"),
    )
    return store, request, by_name


def retry_new_process(store, request):
    code = (
        "from pathlib import Path; import sys; "
        "from game_predictor_worker.vision_lab.annotation_contracts import SplitRequest; "
        "from game_predictor_worker.vision_lab.annotations import AnnotationStore; "
        "from game_predictor_worker.vision_lab.catalog import Catalog; "
        "s=AnnotationStore(Path(sys.argv[1]),Catalog(Path(sys.argv[2]))); "
        "print(s.mutate(SplitRequest.model_validate_json(sys.argv[3])).split.fingerprint)"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(store.root),
            str(store.catalog.root),
            request.model_dump_json(),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
    )
    return result.stdout.strip()


def test_alias_not_target_but_complete_graph_frozen_and_durable(tmp_path):
    store, request, names = cohort_store(tmp_path)
    before = store.read()
    original = names["ordinary/name6.jpg"]
    alias = names["ordinary/alias.jpg"]
    no_cohort = request.model_copy(update={"geometry_source_ids": None})
    old = freeze_splits(store.catalog, before, no_cohort)
    assert old.exclusions[original] == "HUMAN_LOCATION_APPROVAL_REQUIRED"
    assert old.policy_version == "lab-geometry-split-v1"
    frozen = store.mutate(request)
    split = frozen.split
    assert split.policy_version == "lab-geometry-cohort-split-v1"
    assert original in split.assignments and alias not in split.assignments
    assert split.exclusions[alias] == "NOT_IN_GEOMETRY_COHORT"
    assert all(not key.startswith(alias + ":") for key in split.geometry_target_fingerprints)
    assert alias not in split.measurement and alias not in split.geometry_qualification_fingerprints
    assert any(ids == sorted([alias, original]) for ids in split.leakage_components.values())
    assert {s for ids in split.leakage_components.values() for s in ids} == set(
        store.catalog.sources
    )
    assert split.leakage_component_fingerprints == component_fingerprints(
        store.catalog, frozen, split.leakage_components
    )
    assert frozen.annotations == before.annotations and frozen.photo_reviews == before.photo_reviews
    assert (
        frozen.families == before.families
        and frozen.geometry_qualifications == before.geometry_qualifications
    )
    # The unrelated, unqualified historical 777 component does not make the split stale.
    assert not store.read().split_stale
    assert retry_new_process(store, request) == split.fingerprint
    backup = store.backup()
    restored = store.restore(backup.backup_id, tmp_path / "restored")
    assert restored.read() == frozen
    assert retry_new_process(restored, request) == split.fingerprint
    changed = request.model_copy(
        update={"geometry_source_ids": list(reversed(request.geometry_source_ids))}
    )
    with pytest.raises(ValueError, match="REQUEST_ID_CONFLICT"):
        store.mutate(changed)
    refreeze = request.model_copy(
        update={"request_id": "new-cohort-freeze", "expected_revision": frozen.revision}
    )
    with pytest.raises(ValueError, match="SPLIT_ALREADY_FROZEN"):
        store.mutate(refreeze)


@pytest.mark.parametrize(
    "change,reason",
    [
        ("empty", "GEOMETRY_COHORT_EMPTY"),
        ("unknown", "GEOMETRY_COHORT_SOURCE_NOT_FOUND"),
        ("duplicate", "GEOMETRY_COHORT_DUPLICATE_SOURCE"),
        ("legacy", "GEOMETRY_COHORT_PURPOSE_REQUIRED"),
        ("measure_outside", "MEASUREMENT_OUTSIDE_GEOMETRY_COHORT"),
        ("measure_duplicate", "MEASUREMENT_DUPLICATE_SOURCE"),
    ],
)
def test_invalid_requests_are_atomic(tmp_path, change, reason):
    store, request, names = cohort_store(tmp_path)
    if change == "empty":
        request.geometry_source_ids = []
    elif change == "unknown":
        request.geometry_source_ids.append("not-in-catalog")
    elif change == "duplicate":
        request.geometry_source_ids.append(request.geometry_source_ids[0])
    elif change == "legacy":
        request.purpose = "legacy"
    elif change == "measure_outside":
        request.measurement_source_ids.append(names["ordinary/alias.jpg"])
    else:
        request.measurement_source_ids.append(request.measurement_source_ids[0])
    before = (store.root / "state.json").read_bytes()
    with pytest.raises(ValueError, match=reason):
        store.mutate(request)
    assert (store.root / "state.json").read_bytes() == before


@pytest.mark.parametrize("gate", ["unresolved", "comparison_only", "777_v2_declared"])
def test_unselected_alias_does_not_bypass_provenance_or_role(tmp_path, gate):
    store, request, names = cohort_store(tmp_path)
    alias, original = names["ordinary/alias.jpg"], names["ordinary/name6.jpg"]
    if gate == "unresolved":
        family(store, [alias], provenance="unresolved")
    else:
        store.catalog.sources[alias].role = gate
    split = freeze_splits(store.catalog, store.read(), request)
    expected = (
        "FAMILY_PROVENANCE_UNRESOLVED"
        if gate == "unresolved"
        else "COMPARISON_OR_777_PROVENANCE_UNRESOLVED"
    )
    assert split.exclusions[original] == expected
    assert split.exclusions[alias] == "NOT_IN_GEOMETRY_COHORT"


def test_transitive_unselected_bridge_and_measurement_whole_group(tmp_path):
    store, request, names = cohort_store(tmp_path)
    alias, first, second = [names[f"ordinary/{name}.jpg"] for name in ("alias", "name6", "name5")]
    family(store, [alias], related=[second])
    request.expected_revision = store.read().revision
    request.measurement_source_ids = [first, names["ordinary/name0.jpg"]]
    request.difficulties = dict.fromkeys(request.measurement_source_ids, "normal")
    with pytest.raises(ValueError, match="MEASUREMENT_STRATUM_REQUIRED"):
        store.mutate(request)
    request.difficulties.update({alias: "normal", second: "hard"})
    with pytest.raises(ValueError, match="RELATED_MEASUREMENT_DIFFICULTY_CONFLICT"):
        store.mutate(request)
    request.difficulties[second] = "normal"
    split = store.mutate(request).split
    assert split.assignments[first] == split.assignments[second] == "measurement"
    assert split.measurement[first] == split.measurement[second]
    assert alias not in split.assignments


def test_unseen_game_cannot_be_hidden_outside_cohort(tmp_path):
    store, request, names = cohort_store(tmp_path)
    alias, unseen = names["ordinary/alias.jpg"], names["unseen/name0.jpg"]
    family(store, [alias], related=[unseen])
    request.geometry_source_ids.remove(unseen)
    request.expected_revision = store.read().revision
    with pytest.raises(ValueError, match="UNSEEN_GAME_RELATED_TO_DEVELOPMENT"):
        store.mutate(request)


def test_read_and_mutation_detect_unselected_family_drift(tmp_path):
    store, request, names = cohort_store(tmp_path)
    frozen = store.mutate(request).split
    payload = read_checked(store.root / "state.json")
    alias = names["ordinary/alias.jpg"]
    payload["state"]["families"][alias]["evidence"] = "New evidence, same graph"
    write_atomic(store.root / "state.json", payload)
    before = (store.root / "state.json").read_bytes()
    assert store.read().split_stale and store.read().split == frozen
    assert (store.root / "state.json").read_bytes() == before
    assert family(store, [alias]).split_stale


@pytest.mark.parametrize("drift", ["missing", "changed", "rejected"])
def test_unselected_historical_bridge_qualification_must_stay_effective(tmp_path, drift):
    store, historical, qualification = prepared(tmp_path)
    store.mutate(qualification)
    request = populate(store)
    verified_family(store, historical)
    ordinary = [s.id for s in store.catalog.sources.values() if s.game_name == "ordinary"]
    family(store, [historical.id], related=[ordinary[-1]])
    request.purpose = "geometry"
    request.geometry_source_ids = [s.id for s in store.catalog.sources.values() if s.role == "data"]
    request.expected_revision = store.read().revision
    frozen = store.mutate(request).split
    assert historical.id not in frozen.assignments
    assert historical.id not in frozen.geometry_qualification_fingerprints
    assert not store.read().split_stale
    groups = build_components(store.catalog, store.read())
    payload = read_checked(store.root / "state.json")
    if drift == "missing":
        payload["state"]["geometry_qualifications"].pop(historical.id)
    elif drift == "changed":
        payload["state"]["geometry_qualifications"][historical.id]["actor"] = "changed"
    else:
        payload["state"]["photo_reviews"][historical.id]["rejected"] = True
    write_atomic(store.root / "state.json", payload)
    state = store.read()
    assert build_components(store.catalog, state) == groups
    assert state.split_stale and state.split == frozen


@pytest.mark.parametrize("purpose", ["legacy", "geometry"])
def test_pre_cohort_fingerprints_and_receipts_stay_identical(tmp_path, purpose):
    store = setup_store(tmp_path)
    request = populate(store)
    request.purpose = purpose
    split = store.mutate(request).split
    payload = read_checked(store.root / "state.json")
    raw_split = split.model_dump(
        exclude={
            "fingerprint",
            "game_partitions",
            "geometry_source_ids",
            "leakage_components",
            "leakage_component_fingerprints",
        }
    )
    if purpose == "legacy":
        for key in (
            "purpose",
            "policy_version",
            "geometry_qualification_fingerprints",
            "geometry_target_fingerprints",
        ):
            raw_split.pop(key)
    assert digest([store.snapshot_id, raw_split]) == split.fingerprint
    historical_request = request.model_dump(
        exclude={"geometry_source_ids", "geometry_policy", "game_partitions"}
    )
    if purpose == "legacy":
        historical_request.pop("purpose")
    assert payload["receipts"][request.request_id]["fingerprint"] == digest(historical_request)
    for field in (
        "geometry_source_ids",
        "leakage_components",
        "leakage_component_fingerprints",
        "game_partitions",
    ):
        payload["state"]["split"].pop(field)
    write_atomic(store.root / "state.json", payload)
    before = (store.root / "state.json").read_bytes()
    assert retry_new_process(store, request) == split.fingerprint
    assert (store.root / "state.json").read_bytes() == before


def test_cohort_freeze_cas_race_and_http(tmp_path):
    store, request, _ = cohort_store(tmp_path)
    other = request.model_copy(update={"request_id": "competing-freeze"})

    def freeze(candidate):
        try:
            AnnotationStore(store.root, store.catalog).mutate(candidate)
            return "ok"
        except ValueError as error:
            return str(error)

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(freeze, [request, other]))
    assert results.count("ok") == 1
    assert any("BUSY" in result or "REVISION_CONFLICT" in result for result in results)
    winner = request if results[0] == "ok" else other
    client = TestClient(create_app(store.catalog, store.root), base_url="http://127.0.0.1:8102")
    response = client.post(
        "/splits", json=winner.model_dump(), headers={"Origin": "http://127.0.0.1:3102"}
    )
    assert response.status_code == 200
    assert response.json()["split"]["geometry_source_ids"] == sorted(request.geometry_source_ids)
    assert response.json()["split"]["leakage_components"]
    assert client.get("/annotations").json() == response.json()


def test_selected_target_failure_excludes_entire_component_without_promoting_alias(tmp_path):
    store, request, names = cohort_store(tmp_path)
    original, alias = names["ordinary/name6.jpg"], names["ordinary/alias.jpg"]
    approve_full_photo(store, alias)
    request.geometry_source_ids.append(alias)
    state = store.read()
    # An accepted full geometry with machine nodes is not a human target.
    state.annotations[f"{original}:0"].nodes[0].provenance = "interpolated"
    split = freeze_splits(store.catalog, state, request)
    assert split.exclusions[original] == "FULL_HUMAN_GEOMETRY_TARGET_REQUIRED"
    assert split.exclusions[alias] == "FULL_HUMAN_GEOMETRY_TARGET_REQUIRED"
    assert original not in split.assignments and alias not in split.assignments


def test_measurement_and_independent_group_gates_apply_to_complete_components(tmp_path):
    store, request, names = cohort_store(tmp_path)
    state = store.read()
    empty = request.model_copy(update={"measurement_source_ids": []})
    with pytest.raises(ValueError, match="VERIFIED_MEASUREMENT_SOURCES_REQUIRED"):
        freeze_splits(store.catalog, state, empty)
    unseen = names["unseen/name0.jpg"]
    overlap = request.model_copy(update={"measurement_source_ids": [unseen]})
    with pytest.raises(ValueError, match="MEASUREMENT_UNSEEN_OVERLAP"):
        freeze_splits(store.catalog, state, overlap)
    # Two photos linked through an unselected alias remain one measurement group.
    first, second, alias = (
        names["ordinary/name0.jpg"],
        names["ordinary/name1.jpg"],
        names["ordinary/alias.jpg"],
    )
    family(store, [alias], related=[first, second])
    request.difficulties = dict.fromkeys(
        [first, second, alias, names["ordinary/name6.jpg"]], "normal"
    )
    with pytest.raises(ValueError, match="MEASUREMENT_REQUIRES_TWO_INDEPENDENT_GROUPS_PER_STRATUM"):
        freeze_splits(store.catalog, store.read(), request)
    # Several selected development photos in one family cannot supply three groups.
    family(store, [names[f"ordinary/name{i}.jpg"] for i in (2, 3, 4, 5)])
    with pytest.raises(ValueError, match="INSUFFICIENT_VERIFIED_SPLIT_GROUPS"):
        freeze_splits(store.catalog, store.read(), request)


def test_unselected_full_target_cannot_supply_training_topology(tmp_path):
    store, request, names = cohort_store(tmp_path)
    approve_full_photo(store, names["unseen/name0.jpg"], columns=3)
    approve_full_photo(store, names["ordinary/alias.jpg"], columns=3)
    with pytest.raises(ValueError, match="UNSEEN_GAME_REMOVES_TRAINING_TOPOLOGY"):
        freeze_splits(store.catalog, store.read(), request)


def test_full_source_and_disconnected_family_drift_mark_split_stale(tmp_path):
    store, request, names = cohort_store(tmp_path)
    frozen = store.mutate(request).split
    alias = names["ordinary/alias.jpg"]
    store.catalog.sources[alias].filename = "ordinary/changed.jpg"
    assert store.read().split_stale and store.read().split == frozen
    store.catalog.sources[alias].filename = "ordinary/alias.jpg"
    historical = next(s.id for s in store.catalog.sources.values() if s.role != "data")
    changed = family(store, [historical])
    assert changed.split_stale and changed.split == frozen
    assert store.mutate(request).split_stale


def test_http_cohort_validation_is_atomic(tmp_path):
    store, request, _ = cohort_store(tmp_path)
    client = TestClient(create_app(store.catalog, store.root), base_url="http://127.0.0.1:8102")
    headers = {"Origin": "http://127.0.0.1:3102"}
    before = (store.root / "state.json").read_bytes()
    for ids, status, reason in [
        ([], 409, "GEOMETRY_COHORT_EMPTY"),
        (["missing"], 409, "GEOMETRY_COHORT_SOURCE_NOT_FOUND"),
        ("invalid", 422, None),
    ]:
        body = request.model_dump()
        body["geometry_source_ids"] = ids
        response = client.post("/splits", json=body, headers=headers)
        assert response.status_code == status
        if reason:
            assert reason in response.text
        assert (store.root / "state.json").read_bytes() == before
