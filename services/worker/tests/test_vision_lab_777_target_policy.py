"""Explicit D-455 exempts historical context without qualifying extra targets."""

import pytest
from fastapi.testclient import TestClient
from game_predictor_worker.vision_lab.annotation_contracts import (
    GeometryQualificationBinding,
    GeometryQualificationRequest,
)
from game_predictor_worker.vision_lab.annotations import (
    AnnotationStore,
    digest,
    read_checked,
    write_atomic,
)
from game_predictor_worker.vision_lab.api import create_app
from game_predictor_worker.vision_lab.catalog import Catalog
from game_predictor_worker.vision_lab.geometry_qualification import (
    TARGETS_ONLY_777_POLICY,
    geometry_role_eligible,
)
from game_predictor_worker.vision_lab.photo_review import board_revisions
from game_predictor_worker.vision_lab.snapshot import import_folder
from game_predictor_worker.vision_lab.splits import freeze_splits
from test_vision_lab_annotations import approve_full_photo, populate, setup_store
from test_vision_lab_geometry_cohort import family, retry_new_process


def policy_store(tmp_path):
    setup_store(tmp_path)
    directory = tmp_path / "input" / "777"
    (directory / "alias.jpg").write_bytes((directory / "name0.jpg").read_bytes())
    catalog = Catalog(import_folder(tmp_path / "input", tmp_path / "snapshots"))
    store = AnnotationStore(tmp_path / "policy", catalog)
    request = populate(store)
    target = next(s for s in catalog.sources.values() if s.filename == "777/name0.jpg")
    context = next(s for s in catalog.sources.values() if s.filename == "777/alias.jpg")
    approve_full_photo(store, target.id)
    family(store, [target.id, context.id])
    store.mutate(
        GeometryQualificationRequest(
            request_id="qualify-target",
            expected_revision=store.read().revision,
            actor="operator",
            game_id=target.game_id,
            policy_version="historical-777-lab-geometry-v1",
            decision_reference="D-453",
            purpose="geometry",
            bindings=[
                GeometryQualificationBinding(
                    source_id=target.id,
                    source_sha256=target.sha256,
                    expected_board_revisions=board_revisions(store.read(), target.id),
                )
            ],
        )
    )
    request.purpose = "geometry"
    request.geometry_policy = TARGETS_ONLY_777_POLICY
    request.geometry_source_ids = [s.id for s in catalog.sources.values() if s.role == "data"] + [
        target.id
    ]
    request.expected_revision = store.read().revision
    return store, request, target, context


def test_v2_context_is_not_a_target_and_restart_backup_retry_stay_current(tmp_path):
    store, request, target, context = policy_store(tmp_path)
    before = store.read()
    old = freeze_splits(store.catalog, before, request.model_copy(update={"geometry_policy": None}))
    assert old.exclusions[target.id] == "COMPARISON_OR_777_PROVENANCE_UNRESOLVED"
    state = store.mutate(request)
    split = state.split
    assert split.policy_version == TARGETS_ONLY_777_POLICY
    assert target.id in split.assignments and context.id not in split.assignments
    assert context.id not in split.geometry_qualification_fingerprints
    assert not any(key.startswith(context.id + ":") for key in split.geometry_target_fingerprints)
    assert state.annotations == before.annotations and state.photo_reviews == before.photo_reviews
    assert (
        state.geometry_qualifications == before.geometry_qualifications
        and state.families == before.families
    )
    assert not store.read().split_stale
    assert retry_new_process(store, request) == split.fingerprint
    restored = store.restore(store.backup().backup_id, tmp_path / "restored-v2")
    assert restored.read() == state
    assert retry_new_process(restored, request) == split.fingerprint
    assert not restored.read().split_stale
    with pytest.raises(ValueError, match="REQUEST_ID_CONFLICT"):
        store.mutate(request.model_copy(update={"geometry_policy": None}))


def test_v2_target_qualification_and_full_component_provenance_are_required(tmp_path):
    store, request, target, context = policy_store(tmp_path)
    state = store.read()
    state.geometry_qualifications.clear()
    assert (
        freeze_splits(store.catalog, state, request).exclusions[target.id]
        == "COMPARISON_OR_777_PROVENANCE_UNRESOLVED"
    )
    state = store.read()
    state.families[context.id].provenance = "unresolved"
    assert (
        freeze_splits(store.catalog, state, request).exclusions[target.id]
        == "FAMILY_PROVENANCE_UNRESOLVED"
    )
    # A selected but unassigned source never becomes exempt context.
    request.geometry_source_ids.append(context.id)
    assert not geometry_role_eligible(
        store.read(), context, TARGETS_ONLY_777_POLICY, set(request.geometry_source_ids)
    )
    assert (
        freeze_splits(store.catalog, store.read(), request).exclusions[target.id]
        == "COMPARISON_OR_777_PROVENANCE_UNRESOLVED"
    )


def test_v2_exact_historical_identity_only(tmp_path):
    store, request, target, context = policy_store(tmp_path)
    state = store.read()
    for changes in [
        {"source_kind": "database"},
        {"role": "777_v2_declared"},
        {"game_name": "other"},
        {"game_name": "777-old"},
        {"filename": "777-old/alias.jpg"},
        {"filename": "other/777/alias.jpg"},
        {"filename": "777"},
    ]:
        store.catalog.sources[context.id] = context.model_copy(update=changes)
        split = freeze_splits(store.catalog, state, request)
        assert split.exclusions[target.id] == "COMPARISON_OR_777_PROVENANCE_UNRESOLVED"
    store.catalog.sources[context.id] = context
    assert target.id in freeze_splits(store.catalog, state, request).assignments


def test_v2_full_graph_keeps_unseen_and_measurement_boundaries(tmp_path):
    store, request, _, context = policy_store(tmp_path)
    unseen = next(s.id for s in store.catalog.sources.values() if s.game_name == "unseen")
    family(store, [context.id], related=[unseen])
    request.geometry_source_ids.remove(unseen)
    with pytest.raises(ValueError, match="UNSEEN_GAME_RELATED_TO_DEVELOPMENT"):
        freeze_splits(store.catalog, store.read(), request)
    family(store, [context.id], related=[request.measurement_source_ids[0]])
    request.geometry_source_ids.append(unseen)
    with pytest.raises(ValueError, match="MEASUREMENT_STRATUM_REQUIRED"):
        freeze_splits(store.catalog, store.read(), request)


def test_v2_read_checks_full_fingerprints_and_target_qualification(tmp_path):
    store, request, target, context = policy_store(tmp_path)
    frozen = store.mutate(request).split
    original = read_checked(store.root / "state.json")
    for drift in ("source", "family", "qualification", "target_review"):
        payload = read_checked(store.root / "state.json")
        if drift == "source":
            store.catalog.sources[context.id] = context.model_copy(
                update={"filename": "777/renamed.jpg"}
            )
        elif drift == "family":
            payload["state"]["families"][context.id]["evidence"] = "changed"
        elif drift == "qualification":
            payload["state"]["geometry_qualifications"][target.id]["actor"] = "changed"
        else:
            payload["state"]["photo_reviews"][target.id]["rejected"] = True
        write_atomic(store.root / "state.json", payload)
        assert store.read().split_stale and store.read().split == frozen
        store.catalog.sources[context.id] = context
        write_atomic(store.root / "state.json", original)
    # No acceptance is needed from context, even if it has a rejected review.
    payload = read_checked(store.root / "state.json")
    payload["state"]["photo_reviews"][context.id] = {
        **payload["state"]["photo_reviews"][target.id],
        "source_id": context.id,
        "rejected": True,
    }
    write_atomic(store.root / "state.json", payload)
    assert not store.read().split_stale


def test_v2_http_validation_is_atomic(tmp_path):
    store, request, _, _ = policy_store(tmp_path)
    client = TestClient(create_app(store.catalog, store.root), base_url="http://127.0.0.1:8102")
    headers = {"Origin": "http://127.0.0.1:3102"}
    before = (store.root / "state.json").read_bytes()
    for update, status, reason in [
        ({"purpose": "legacy"}, 409, "GEOMETRY_POLICY_PURPOSE_REQUIRED"),
        ({"geometry_source_ids": None}, 409, "GEOMETRY_POLICY_COHORT_REQUIRED"),
        ({"geometry_source_ids": []}, 409, "GEOMETRY_COHORT_EMPTY"),
        ({"geometry_policy": "unrecognized"}, 422, None),
    ]:
        response = client.post("/splits", json={**request.model_dump(), **update}, headers=headers)
        assert response.status_code == status
        if reason:
            assert reason in response.text
        assert (store.root / "state.json").read_bytes() == before
    response = client.post("/splits", json=request.model_dump(), headers=headers)
    assert response.status_code == 200
    assert response.json()["split"]["policy_version"] == TARGETS_ONLY_777_POLICY


@pytest.mark.parametrize("policy", [None, TARGETS_ONLY_777_POLICY])
def test_existing_cohort_receipt_without_policy_is_retryable(tmp_path, policy):
    store, request, _, _ = policy_store(tmp_path)
    request.geometry_policy = policy
    frozen = store.mutate(request)
    payload = read_checked(store.root / "state.json")
    excluded = {"game_partitions"}
    if policy is None:
        excluded.add("geometry_policy")
    assert payload["receipts"][request.request_id]["fingerprint"] == digest(
        request.model_dump(exclude=excluded)
    )
    assert "game_partitions" not in payload["history"][-1]["request"]
    if policy is None:
        assert "geometry_policy" not in payload["history"][-1]["request"]
    old_split = frozen.split.model_dump(exclude={"fingerprint", "game_partitions"})
    assert frozen.split.fingerprint == digest([store.snapshot_id, old_split])
    payload["state"]["split"].pop("game_partitions")
    write_atomic(store.root / "state.json", payload)
    before = (store.root / "state.json").read_bytes()
    assert retry_new_process(store, request) == frozen.split.fingerprint
    assert (store.root / "state.json").read_bytes() == before
