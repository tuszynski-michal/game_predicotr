"""Explicit geometry qualification never changes source roles or human approvals."""

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
    GeometryQualificationBinding,
    GeometryQualificationRequest,
    PhotoReviewRequest,
)
from game_predictor_worker.vision_lab.annotations import (
    AnnotationStore,
    digest,
    read_checked,
    write_atomic,
)
from game_predictor_worker.vision_lab.api import create_app
from game_predictor_worker.vision_lab.catalog import Catalog
from game_predictor_worker.vision_lab.geometry_qualification import qualification_effective
from game_predictor_worker.vision_lab.photo_review import board_revisions
from game_predictor_worker.vision_lab.qualify_geometry import qualify_geometry
from game_predictor_worker.vision_lab.rebase_annotations import _references
from game_predictor_worker.vision_lab.snapshot import import_folder
from test_vision_lab_annotations import (
    accept_photo,
    approve_full_photo,
    populate,
    request_for,
    setup_store,
)


def prepared(tmp_path):
    store = setup_store(tmp_path)
    source = next(s for s in store.catalog.sources.values() if s.game_name == "777")
    approve_full_photo(store, source.id)
    state = store.read()
    request = GeometryQualificationRequest(
        request_id="qualify-777-request",
        expected_revision=state.revision,
        actor="operator",
        policy_version="historical-777-lab-geometry-v1",
        decision_reference="D-453",
        purpose="geometry",
        game_id=source.game_id,
        bindings=[
            GeometryQualificationBinding(
                source_id=source.id,
                source_sha256=source.sha256,
                expected_board_revisions=board_revisions(state, source.id),
            )
        ],
    )
    return store, source, request


def verified_family(store, source):
    state = store.read()
    return store.mutate(
        FamilyRequest(
            request_id=f"family-history-{state.revision}",
            expected_revision=state.revision,
            actor="operator",
            decision=FamilyDecision(
                source_ids=[source.id],
                family_id="historical-recording",
                evidence="Explicit original recording",
                provenance="verified",
            ),
        )
    )


def test_preview_atomic_apply_restart_retry_backup_and_api(tmp_path):
    store, source, request = prepared(tmp_path)
    before = read_checked(store.root / "state.json")
    files = sorted(p.name for p in store.root.iterdir())
    assert qualify_geometry(store.catalog.root, store.root, request)["status"] == "ready"
    assert read_checked(store.root / "state.json") == before
    assert sorted(p.name for p in store.root.iterdir()) == files
    # Preview on a copied state without a .lock must not create one.
    preview_root = tmp_path / "preview"
    preview_root.mkdir()
    write_atomic(preview_root / "state.json", before)
    qualify_geometry(store.catalog.root, preview_root, request)
    assert not (preview_root / ".lock").exists()
    state = store.mutate(request)
    assert state.revision == before["state"]["revision"] + 1
    assert state.annotations == store.read().annotations
    assert state.model_dump()["annotations"] == before["state"]["annotations"]
    assert state.model_dump()["photo_reviews"] == before["state"]["photo_reviews"]
    assert source.role == "comparison_only" and source.training_eligible is False
    assert qualification_effective(state, source)
    assert store.mutate(request) == state
    assert qualify_geometry(store.catalog.root, store.root, request)["status"] == "already_applied"
    backup = store.backup()
    restored = store.restore(backup.backup_id, tmp_path / "restored")
    assert read_checked(restored.root / "state.json") == read_checked(store.root / "state.json")
    code = (
        "from pathlib import Path; import sys; "
        "from game_predictor_worker.vision_lab.annotation_contracts "
        "import GeometryQualificationRequest; "
        "from game_predictor_worker.vision_lab.qualify_geometry import qualify_geometry; "
        "r=GeometryQualificationRequest.model_validate_json(sys.argv[3]); "
        "print(qualify_geometry(Path(sys.argv[1]),Path(sys.argv[2]),r,apply=True)['revision'])"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(store.catalog.root),
            str(restored.root),
            request.model_dump_json(),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
    )
    assert result.stdout.strip() == str(state.revision)
    client = TestClient(create_app(store.catalog, store.root), base_url="http://127.0.0.1:8102")
    assert (
        client.get("/annotations").json()["geometry_qualifications"][source.id]["purpose"]
        == "geometry"
    )
    assert (
        client.post(
            "/annotations", json=request.model_dump(), headers={"Origin": "http://127.0.0.1:3102"}
        ).status_code
        == 422
    )
    changed = request.model_copy(update={"actor": "other"})
    with pytest.raises(ValueError, match="REQUEST_ID_CONFLICT"):
        store.mutate(changed)


@pytest.mark.parametrize(
    "change,reason",
    [
        ("sha", "SOURCE_CHANGED"),
        ("map", "GEOMETRY_CHANGED"),
        ("game", "HISTORICAL_777_REQUIRED"),
        ("duplicate", "DUPLICATE_SOURCE"),
        ("missing", "SOURCE_NOT_FOUND"),
        ("actor", "ACTOR_REQUIRED"),
        ("revision", "REVISION_CONFLICT"),
    ],
)
def test_invalid_batch_is_atomic(tmp_path, change, reason):
    store, _, request = prepared(tmp_path)
    if change == "sha":
        request.bindings[0].source_sha256 = "f" * 64
    elif change == "map":
        request.bindings[0].expected_board_revisions = {"0": 999}
    elif change == "game":
        request.game_id = "not-the-game"
    elif change == "duplicate":
        request.bindings.append(request.bindings[0])
    elif change == "missing":
        request.bindings.append(request.bindings[0].model_copy(update={"source_id": "missing"}))
    elif change == "actor":
        request.actor = " "
    else:
        request.expected_revision -= 1
    before = (store.root / "state.json").read_bytes()
    with pytest.raises(ValueError, match=reason):
        store.mutate(request)
    assert (store.root / "state.json").read_bytes() == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("game_name", "777 V2"),
        ("game_name", "other"),
        ("role", "777_v2_declared"),
        ("role", "data"),
        ("source_kind", "database"),
        ("filename", "other/777.jpg"),
    ],
)
def test_only_exact_historical_folder_identity(tmp_path, field, value):
    store, source, request = prepared(tmp_path)
    setattr(source, field, value)
    with pytest.raises(ValueError, match="HISTORICAL_777_REQUIRED"):
        store.mutate(request)


@pytest.mark.parametrize("change", ["draft", "location", "model", "baseline_proposal", "reject"])
def test_missing_human_target_or_current_acceptance_is_rejected(tmp_path, change):
    store, source, request = prepared(tmp_path)
    payload = read_checked(store.root / "state.json")
    item = payload["state"]["annotations"][f"{source.id}:0"]
    if change in ("draft", "location"):
        item["full_approved"] = False
    elif change == "reject":
        payload["state"]["photo_reviews"][source.id]["rejected"] = True
    else:
        item["nodes"][0]["provenance"] = change
    write_atomic(store.root / "state.json", payload)
    before = (store.root / "state.json").read_bytes()
    with pytest.raises(ValueError, match="ACCEPTANCE_REQUIRED|FULL_HUMAN_TARGET_REQUIRED"):
        store.mutate(request)
    assert (store.root / "state.json").read_bytes() == before


def test_geometry_split_targets_family_gate_and_legacy_behavior(tmp_path):
    store, source, qualification = prepared(tmp_path)
    store.mutate(qualification)
    request = populate(store)
    request.purpose = "geometry"
    # Qualification does not resolve source families.
    from game_predictor_worker.vision_lab.splits import freeze_splits

    assert (
        freeze_splits(store.catalog, store.read(), request).exclusions[source.id]
        == "FAMILY_PROVENANCE_UNRESOLVED"
    )
    verified_family(store, source)
    # Saved draft must not be a geometry target even when the photo is accepted.
    draft = request_for(store, source.id, action="draft")
    draft.annotation.board_index = 1
    store.mutate(draft)
    accept_photo(store, source.id)
    qualification.request_id = "qualify-current-revisions"
    qualification.expected_revision = store.read().revision
    qualification.bindings[0].expected_board_revisions = board_revisions(store.read(), source.id)
    store.mutate(qualification)
    request.expected_revision = store.read().revision
    legacy = request.model_copy(update={"purpose": "legacy"})
    assert source.id in freeze_splits(store.catalog, store.read(), legacy).exclusions
    frozen = store.mutate(request)
    assert frozen.split.purpose == "geometry"
    assert frozen.split.policy_version == "lab-geometry-split-v1"
    assert source.id in frozen.split.assignments
    assert f"{source.id}:0" in frozen.split.geometry_target_fingerprints
    assert f"{source.id}:1" not in frozen.split.geometry_target_fingerprints
    assert frozen.split.geometry_qualification_fingerprints[source.id] == digest(
        frozen.geometry_qualifications[source.id].model_dump()
    )
    rejected = store.mutate(
        PhotoReviewRequest(
            request_id="reject-qualified-photo",
            expected_revision=frozen.revision,
            actor="operator",
            action="reject",
            source_id=source.id,
            source_sha256=source.sha256,
            expected_board_revisions=board_revisions(frozen, source.id),
        )
    )
    assert not qualification_effective(rejected, source)
    assert rejected.split_stale and rejected.split == frozen.split
    accepted = accept_photo(store, source.id)
    assert qualification_effective(accepted, source)
    assert accepted.split_stale and accepted.split == frozen.split
    edited = store.mutate(request_for(store, source.id, action="draft"))
    assert not qualification_effective(edited, source)
    assert edited.split_stale and edited.split == frozen.split


def test_rebase_explicitly_rejects_current_or_history_qualification(tmp_path):
    store, _, request = prepared(tmp_path)
    store.mutate(request)
    payload = read_checked(store.root / "state.json")
    for clear in (False, True):
        if clear:
            payload["state"]["geometry_qualifications"] = {}
        with pytest.raises(ValueError, match="REBASE_GEOMETRY_QUALIFICATIONS_UNSUPPORTED"):
            _references(payload, store.catalog)


def test_old_split_receipt_retry_and_read_do_not_rewrite_payload(tmp_path):
    store = setup_store(tmp_path)
    request = populate(store)
    frozen = store.mutate(request)
    payload = read_checked(store.root / "state.json")
    payload["state"].pop("geometry_qualifications")
    for field in (
        "purpose",
        "policy_version",
        "geometry_qualification_fingerprints",
        "geometry_target_fingerprints",
    ):
        payload["state"]["split"].pop(field)
    legacy_request = request.model_dump(
        exclude={"purpose", "geometry_source_ids", "geometry_policy"}
    )
    assert payload["receipts"][request.request_id]["fingerprint"] == digest(legacy_request)
    write_atomic(store.root / "state.json", payload)
    before = (store.root / "state.json").read_bytes()
    restarted = AnnotationStore(store.root, store.catalog)
    assert restarted.read().split == frozen.split
    assert restarted.mutate(request).split == frozen.split
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
            request.model_dump_json(exclude={"purpose", "geometry_source_ids", "geometry_policy"}),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
    )
    assert result.stdout.strip() == frozen.split.fingerprint
    assert (store.root / "state.json").read_bytes() == before


def test_atomic_multiple_sources_and_competing_qualification(tmp_path):
    original, _, template = prepared(tmp_path)
    folder = tmp_path / "input" / "777"
    (folder / "alias.jpg").write_bytes((folder / "name0.jpg").read_bytes())
    catalog = Catalog(import_folder(tmp_path / "input", tmp_path / "snapshots"))
    store = AnnotationStore(tmp_path / "batch", catalog)
    sources = [s for s in catalog.sources.values() if s.game_name == "777"]
    for source in sources:
        approve_full_photo(store, source.id)
    state = store.read()
    request = template.model_copy(
        update={
            "expected_revision": state.revision,
            "bindings": [
                GeometryQualificationBinding(
                    source_id=s.id,
                    source_sha256=s.sha256,
                    expected_board_revisions=board_revisions(state, s.id),
                )
                for s in sources
            ],
        }
    )
    competing = request.model_copy(update={"request_id": "competing-qualification"})

    def apply(candidate):
        try:
            AnnotationStore(store.root, catalog).mutate(candidate)
            return "ok"
        except ValueError as error:
            return str(error)

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(apply, [request, competing]))
    assert results.count("ok") == 1
    assert any("BUSY" in result or "REVISION_CONFLICT" in result for result in results)
    current = store.read()
    assert current.revision == state.revision + 1
    assert len(current.geometry_qualifications) == 2
    assert current.annotations == state.annotations and current.photo_reviews == state.photo_reviews
    assert original.read().geometry_qualifications == {}


def test_read_detects_lost_qualification_without_rewriting_split(tmp_path):
    store, source, request = prepared(tmp_path)
    store.mutate(request)
    split_request = populate(store)
    verified_family(store, source)
    split_request.expected_revision = store.read().revision
    split_request.purpose = "geometry"
    frozen = store.mutate(split_request).split
    payload = read_checked(store.root / "state.json")
    payload["state"]["geometry_qualifications"] = {}
    write_atomic(store.root / "state.json", payload)
    before = (store.root / "state.json").read_bytes()
    state = AnnotationStore(store.root, store.catalog).read()
    assert state.split_stale and state.split == frozen
    assert (store.root / "state.json").read_bytes() == before


def test_geometry_coverage_does_not_use_location_only_topology(tmp_path):
    store = setup_store(tmp_path)
    request = populate(store)
    request.purpose = "geometry"
    unseen = next(s for s in store.catalog.sources.values() if s.game_name == "unseen")
    approve_full_photo(store, unseen.id, columns=3)
    for source in store.catalog.sources.values():
        if source.game_name != "ordinary":
            continue
        location = request_for(store, source.id, columns=3)
        location.annotation.board_index = 1
        store.mutate(location)
        accept_photo(store, source.id)
    request.expected_revision = store.read().revision
    with pytest.raises(ValueError, match="REMOVES_TRAINING_TOPOLOGY"):
        store.mutate(request)
