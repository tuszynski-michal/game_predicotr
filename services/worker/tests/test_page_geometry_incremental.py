from __future__ import annotations

import json
from pathlib import Path

import game_predictor_worker.images.page_geometry_incremental as incremental_module
import pytest
from game_predictor_worker.images.page_geometry_incremental import (
    BASELINE_TO_SELECTIVE_COMPATIBILITY,
    EXACT_POLICY_COMPATIBILITY,
    LATERAL_V2_TO_V3_COMPATIBILITY,
    LATERAL_V3_TO_V2_COMPATIBILITY,
    REPLACEMENT_LINEAGE_COMPATIBILITY,
    BasePageGeometryManifestDescriptor,
    PageGeometryCheckpointStore,
    load_base_manifest,
    plan_manifest_reuse,
    source_inventory_checksum,
)
from game_predictor_worker.images.source_ingestion import ManagedOriginal
from game_predictor_worker.jobs.runtime import JobHandlerError


def test_atomic_checkpoint_retries_only_windows_sharing_violations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "state.json"
    path.write_bytes(b"old")
    replace = incremental_module.os.replace
    calls = []

    def sharing_once(source: object, target: object) -> None:
        calls.append(target)
        if len(calls) == 1:
            error = OSError(13, "sharing violation")
            error.winerror = 32
            raise error
        replace(source, target)

    monkeypatch.setattr(incremental_module.os, "replace", sharing_once)
    monkeypatch.setattr(incremental_module.time, "sleep", lambda _: None)
    incremental_module._write_atomic(path, b"new")
    assert len(calls) == 2
    assert path.read_bytes() == b"new"
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_checkpoint_reports_disk_failure_and_preserves_old_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "state.json"
    path.write_bytes(b"old")

    def disk_full(source: object, target: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(incremental_module.os, "replace", disk_full)
    with pytest.raises(JobHandlerError, match="errno=28"):
        incremental_module._write_atomic(path, b"new")
    assert path.read_bytes() == b"old"
    assert list(tmp_path.glob("*.tmp")) == []


def _original(index: int) -> ManagedOriginal:
    checksum = f"{index + 1:064x}"
    return ManagedOriginal(
        checksum_sha256=checksum,
        source_relative_path=f"seq_{index * 9 + 1}-{index * 9 + 9}.jpg",
        managed_relative_path=f"data/originals/{checksum[:2]}/{checksum}.jpg",
        size_bytes=100,
        sequence_range_start=index * 9 + 1,
        sequence_range_end=index * 9 + 9,
    )


def _registered(original: ManagedOriginal, *, weak_count: int = 0, anchor: str = "f" * 64):
    return {
        "status": "registered",
        "sourceRelativePath": original.source_relative_path,
        "imageWidth": 1080,
        "imageHeight": 700,
        "registrationVersion": "verified-page-registration-v1",
        "anchorSourceChecksumSha256": anchor,
        "boardRedEdgeCoverages": [0.4] * weak_count + [0.9] * (9 - weak_count),
        "quads": [],
    }


def test_replacement_recomputes_new_source_and_old_anchor_dependents() -> None:
    old = tuple(_original(index) for index in range(3))
    replacement = ManagedOriginal(
        checksum_sha256="e" * 64,
        source_relative_path=old[0].source_relative_path,
        managed_relative_path="data/originals/ee/" + "e" * 64 + ".jpg",
        size_bytes=100,
        sequence_range_start=1,
        sequence_range_end=9,
    )
    current = (replacement, old[1], old[2])
    entries = {
        old[0].checksum_sha256: _registered(old[0]),
        old[1].checksum_sha256: _registered(old[1], anchor=old[0].checksum_sha256),
        old[2].checksum_sha256: _registered(old[2]),
    }
    plan = plan_manifest_reuse(
        current,
        payload={
            "pageGeometryOverrides": {},
            "pageRegistrationProfile": {"anchors": [{"sourceChecksumSha256": "f" * 64}]},
            "canonicalSequenceNumbers": set(),
        },
        base_manifest={"entries": entries},
        compatibility_mode=REPLACEMENT_LINEAGE_COMPATIBILITY,
    )
    assert set(plan.entries) == {old[2].checksum_sha256}
    assert {item.checksum_sha256 for item in plan.recompute_originals} == {
        replacement.checksum_sha256,
        old[1].checksum_sha256,
    }


def test_lateral_v2_to_v3_reuses_only_safe_registered_classes() -> None:
    originals = tuple(_original(index) for index in range(6))
    entries = {
        originals[0].checksum_sha256: _registered(originals[0], weak_count=0),
        originals[1].checksum_sha256: _registered(originals[1], weak_count=1),
        originals[2].checksum_sha256: _registered(originals[2], weak_count=2),
        originals[3].checksum_sha256: _registered(originals[3], weak_count=3),
        originals[4].checksum_sha256: _registered(originals[4], weak_count=4),
        originals[5].checksum_sha256: {
            "status": "review_required",
            "sourceRelativePath": originals[5].source_relative_path,
        },
    }
    plan = plan_manifest_reuse(
        originals,
        payload={
            "pageGeometryOverrides": {},
            "pageRegistrationProfile": {"anchors": [{"sourceChecksumSha256": "f" * 64}]},
            "canonicalSequenceNumbers": set(),
            "lateralPartialGeometry": {
                "minimumAutomaticBoardRedEdgeCoverage": 0.65,
                "maximumFrameReviewSlots": 3,
            },
        },
        base_manifest={"entries": entries},
        compatibility_mode=LATERAL_V2_TO_V3_COMPATIBILITY,
    )

    assert list(plan.entries) == [
        originals[0].checksum_sha256,
        originals[4].checksum_sha256,
    ]
    assert [item.checksum_sha256 for item in plan.recompute_originals] == [
        originals[index].checksum_sha256 for index in (1, 2, 3, 5)
    ]


def test_lateral_v3_to_v2_reuses_registered_and_recomputes_review() -> None:
    originals = tuple(_original(index) for index in range(3))
    entries = {
        originals[0].checksum_sha256: _registered(originals[0]),
        originals[1].checksum_sha256: {
            "status": "review_required",
            "sourceRelativePath": originals[1].source_relative_path,
            "automaticFrameProposal": {"version": "automatic-frame-geometry-proposal-v1"},
        },
        originals[2].checksum_sha256: _registered(originals[2]),
    }
    plan = plan_manifest_reuse(
        originals,
        payload={
            "pageGeometryOverrides": {originals[2].checksum_sha256: {"revision": 2}},
            "pageRegistrationProfile": {"anchors": [{"sourceChecksumSha256": "f" * 64}]},
            "canonicalSequenceNumbers": set(),
        },
        base_manifest={"entries": entries},
        compatibility_mode=LATERAL_V3_TO_V2_COMPATIBILITY,
    )

    assert list(plan.entries) == [originals[0].checksum_sha256]
    assert [item.checksum_sha256 for item in plan.recompute_originals] == [
        originals[1].checksum_sha256,
        originals[2].checksum_sha256,
    ]


def test_selective_reuses_all_baseline_registered_and_recomputes_only_review() -> None:
    originals = tuple(_original(index) for index in range(4))
    entries = {
        originals[0].checksum_sha256: _registered(originals[0], weak_count=0),
        originals[1].checksum_sha256: _registered(originals[1], weak_count=1),
        originals[2].checksum_sha256: _registered(originals[2], weak_count=2),
        originals[3].checksum_sha256: {
            "status": "review_required",
            "sourceRelativePath": originals[3].source_relative_path,
        },
    }
    plan = plan_manifest_reuse(
        originals,
        payload={
            "pageGeometryOverrides": {},
            "pageRegistrationProfile": {"anchors": [{"sourceChecksumSha256": "f" * 64}]},
            "canonicalSequenceNumbers": set(),
        },
        base_manifest={"entries": entries},
        compatibility_mode=BASELINE_TO_SELECTIVE_COMPATIBILITY,
    )
    assert list(plan.entries) == [item.checksum_sha256 for item in originals[:3]]
    assert plan.recompute_originals == (originals[3],)


def test_registered_entry_without_anchor_provenance_is_recomputed() -> None:
    original = _original(0)
    entry = _registered(original)
    del entry["anchorSourceChecksumSha256"]
    plan = plan_manifest_reuse(
        (original,),
        payload={"pageGeometryOverrides": {}, "canonicalSequenceNumbers": set()},
        base_manifest={"entries": {original.checksum_sha256: entry}},
        compatibility_mode=EXACT_POLICY_COMPATIBILITY,
    )
    assert plan.reused_source_count == 0
    assert plan.recompute_originals == (original,)


def test_exact_reuse_invalidates_changed_manual_anchor_and_dependants() -> None:
    manual, dependant, independent = (_original(index) for index in range(3))
    old_decision = "a" * 64
    override_id = "00000000-0000-0000-0000-000000000001"
    entries = {
        manual.checksum_sha256: {
            **_registered(manual),
            "registrationVersion": "manual-page-geometry-override-v1",
            "manualOverrideDecisionChecksumSha256": old_decision,
            "manualOverrideId": override_id,
            "manualOverrideRevision": 1,
        },
        dependant.checksum_sha256: _registered(dependant, anchor=manual.checksum_sha256),
        independent.checksum_sha256: _registered(independent),
    }
    plan = plan_manifest_reuse(
        (manual, dependant, independent),
        payload={
            "pageGeometryOverrides": {
                manual.checksum_sha256: {
                    "decisionChecksumSha256": "b" * 64,
                    "overrideId": override_id,
                    "revision": 2,
                }
            },
            "pageRegistrationProfile": {"anchors": [{"sourceChecksumSha256": "f" * 64}]},
            "canonicalSequenceNumbers": set(),
        },
        base_manifest={"entries": entries},
        compatibility_mode=EXACT_POLICY_COMPATIBILITY,
    )

    assert list(plan.entries) == [independent.checksum_sha256]
    assert [item.checksum_sha256 for item in plan.recompute_originals] == [
        manual.checksum_sha256,
        dependant.checksum_sha256,
    ]


def test_changed_manual_anchor_invalidates_transitive_automatic_dependants() -> None:
    manual, promoted, dependant, independent = (_original(index) for index in range(4))
    override_id = "00000000-0000-0000-0000-000000000001"
    old = {
        "decisionChecksumSha256": "a" * 64,
        "overrideId": override_id,
        "revision": 1,
    }
    entries = {
        manual.checksum_sha256: {
            **_registered(manual),
            "registrationVersion": "manual-page-geometry-override-v1",
            "manualOverrideDecisionChecksumSha256": old["decisionChecksumSha256"],
            "manualOverrideId": override_id,
            "manualOverrideRevision": 1,
        },
        promoted.checksum_sha256: _registered(promoted, anchor=manual.checksum_sha256),
        dependant.checksum_sha256: _registered(dependant, anchor=promoted.checksum_sha256),
        independent.checksum_sha256: _registered(independent),
    }
    plan = plan_manifest_reuse(
        (manual, promoted, dependant, independent),
        payload={
            "pageGeometryOverrides": {
                manual.checksum_sha256: {**old, "decisionChecksumSha256": "b" * 64}
            },
            "pageRegistrationProfile": {"anchors": [{"sourceChecksumSha256": "f" * 64}]},
            "canonicalSequenceNumbers": set(),
        },
        base_manifest={"entries": entries},
        compatibility_mode=EXACT_POLICY_COMPATIBILITY,
        base_override_fingerprints={
            manual.checksum_sha256: incremental_module._override_fingerprint(old)
        },
    )
    assert list(plan.entries) == [independent.checksum_sha256]
    assert [item.checksum_sha256 for item in plan.recompute_originals] == [
        manual.checksum_sha256,
        promoted.checksum_sha256,
        dependant.checksum_sha256,
    ]


def test_external_manual_anchor_reuse_requires_pinned_unchanged_decision() -> None:
    original = _original(0)
    external_checksum = "e" * 64
    decision = {
        "decisionChecksumSha256": "a" * 64,
        "overrideId": "00000000-0000-0000-0000-000000000001",
        "revision": 1,
    }
    base_entries = {original.checksum_sha256: _registered(original, anchor=external_checksum)}
    fingerprint = incremental_module._override_fingerprint(decision)
    assert fingerprint is not None
    arguments = {
        "originals": (original,),
        "base_manifest": {"entries": base_entries},
        "compatibility_mode": EXACT_POLICY_COMPATIBILITY,
        "base_override_fingerprints": {external_checksum: fingerprint},
    }
    stable = plan_manifest_reuse(
        **arguments,
        payload={"pageGeometryOverrides": {external_checksum: decision}},
    )
    removed = plan_manifest_reuse(
        **arguments,
        payload={"pageGeometryOverrides": {}},
    )
    unverifiable = plan_manifest_reuse(
        (original,),
        payload={"pageGeometryOverrides": {external_checksum: decision}},
        base_manifest={"entries": base_entries},
        compatibility_mode=EXACT_POLICY_COMPATIBILITY,
    )
    assert stable.reused_source_count == 1
    assert removed.recomputed_source_count == 1
    assert unverifiable.recomputed_source_count == 1


def test_recomputed_unknown_provenance_anchor_invalidates_its_descendants() -> None:
    anchor, dependant, second_dependant, independent = (_original(index) for index in range(4))
    entries = {
        anchor.checksum_sha256: {
            key: value
            for key, value in _registered(anchor).items()
            if key != "anchorSourceChecksumSha256"
        },
        dependant.checksum_sha256: _registered(dependant, anchor=anchor.checksum_sha256),
        second_dependant.checksum_sha256: _registered(
            second_dependant, anchor=dependant.checksum_sha256
        ),
        independent.checksum_sha256: _registered(independent),
    }
    plan = plan_manifest_reuse(
        (anchor, dependant, second_dependant, independent),
        payload={
            "pageGeometryOverrides": {},
            "pageRegistrationProfile": {"anchors": [{"sourceChecksumSha256": "f" * 64}]},
        },
        base_manifest={"entries": entries},
        compatibility_mode=EXACT_POLICY_COMPATIBILITY,
    )
    assert list(plan.entries) == [independent.checksum_sha256]
    assert [original.checksum_sha256 for original in plan.recompute_originals] == [
        anchor.checksum_sha256,
        dependant.checksum_sha256,
        second_dependant.checksum_sha256,
    ]


def test_checkpoint_shards_resume_and_detect_tampering(tmp_path: Path) -> None:
    originals = (_original(0), _original(1))
    store = PageGeometryCheckpointStore(
        tmp_path,
        job_id="00000000-0000-0000-0000-000000000001",
        input_fingerprint_sha256="a" * 64,
        source_inventory_checksum_sha256=source_inventory_checksum(originals),
        shard_size=1,
    )
    metadata = {
        "phase": "source_registration",
        "sourceNextIndex": 0,
        "recomputeInventoryChecksumSha256": "b" * 64,
        "reusedSourceCount": 1,
        "recomputedSourceCount": 1,
        "autoAnchorPasses": [],
        "activeAutoAnchorPass": None,
    }
    first_entry = _registered(originals[0])
    initial = store.initialize({originals[0].checksum_sha256: first_entry}, metadata=metadata)
    second_entry = _registered(originals[1])
    all_entries = {
        originals[0].checksum_sha256: first_entry,
        originals[1].checksum_sha256: second_entry,
    }
    metadata["sourceNextIndex"] = 1
    updated = store.append(
        {originals[1].checksum_sha256: second_entry},
        metadata=metadata,
        all_entries=all_entries,
    )

    resumed = PageGeometryCheckpointStore(
        tmp_path,
        job_id="00000000-0000-0000-0000-000000000001",
        input_fingerprint_sha256="a" * 64,
        source_inventory_checksum_sha256=source_inventory_checksum(originals),
        shard_size=1,
    ).load(required=True)
    assert resumed is not None
    assert resumed.entries == all_entries
    assert resumed.metadata["sourceNextIndex"] == 1
    assert initial.state_checksum_sha256 != updated.state_checksum_sha256

    state_path = (
        tmp_path
        / "data/page-geometry-preflight-checkpoints"
        / "00000000-0000-0000-0000-000000000001"
        / "state.json"
    )
    state = json.loads(state_path.read_text())
    shard = tmp_path / Path(*state["shards"][0]["relativePath"].split("/"))
    shard.write_bytes(b"tampered")
    with pytest.raises(JobHandlerError) as captured:
        PageGeometryCheckpointStore(
            tmp_path,
            job_id="00000000-0000-0000-0000-000000000001",
            input_fingerprint_sha256="a" * 64,
            source_inventory_checksum_sha256=source_inventory_checksum(originals),
        ).load(required=True)
    assert captured.value.code == "IMAGE_PAGE_GEOMETRY_CHECKPOINT_INVALID"


def test_pinned_missing_base_manifest_fails_closed(tmp_path: Path) -> None:
    descriptor = BasePageGeometryManifestDescriptor(
        job_id="00000000-0000-0000-0000-000000000001",
        manifest_checksum_sha256="a" * 64,
        source_manifest_checksum_sha256="b" * 64,
        compatibility_mode=EXACT_POLICY_COMPATIBILITY,
    )

    with pytest.raises(JobHandlerError) as captured:
        load_base_manifest(
            tmp_path,
            descriptor,
            game_id="00000000-0000-0000-0000-000000000002",
            source_selection_id="00000000-0000-0000-0000-000000000003",
            source_manifest_checksum_sha256="b" * 64,
            preflight_policy_version="page-geometry-preflight-v3-board-area-mask",
            page_registration_profile={"schemaVersion": 1},
            lateral_partial_geometry=None,
        )

    assert captured.value.code == "IMAGE_PAGE_GEOMETRY_BASE_MANIFEST_INVALID"


def test_replacement_lineage_loads_only_pinned_parent_manifest(tmp_path: Path) -> None:
    import hashlib

    parent_id = "00000000-0000-0000-0000-000000000001"
    replacement_id = "00000000-0000-0000-0000-000000000002"
    game_id = "00000000-0000-0000-0000-000000000003"
    manifest = {
        "gameId": game_id,
        "sourceSelectionId": parent_id,
        "sourceManifestChecksumSha256": "a" * 64,
        "version": "page-geometry-preflight-v2-auto-anchor",
        "pageRegistrationProfile": {"schemaVersion": 1},
        "lateralPartialGeometry": None,
        "entries": {},
    }
    content = json.dumps(manifest).encode()
    checksum = hashlib.sha256(content).hexdigest()
    path = tmp_path / "data" / "page-geometry-manifests" / f"{checksum}.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    descriptor = BasePageGeometryManifestDescriptor(
        job_id="00000000-0000-0000-0000-000000000004",
        manifest_checksum_sha256=checksum,
        source_manifest_checksum_sha256="a" * 64,
        compatibility_mode=REPLACEMENT_LINEAGE_COMPATIBILITY,
        base_source_selection_id=parent_id,
    )

    loaded = load_base_manifest(
        tmp_path,
        descriptor,
        game_id=game_id,
        source_selection_id=replacement_id,
        source_manifest_checksum_sha256="b" * 64,
        preflight_policy_version="page-geometry-preflight-v2-auto-anchor",
        page_registration_profile={"schemaVersion": 1},
        lateral_partial_geometry=None,
    )
    assert loaded["sourceSelectionId"] == parent_id

    with pytest.raises(JobHandlerError) as captured:
        load_base_manifest(
            tmp_path,
            BasePageGeometryManifestDescriptor(
                job_id=descriptor.job_id,
                manifest_checksum_sha256=checksum,
                source_manifest_checksum_sha256="c" * 64,
                compatibility_mode=REPLACEMENT_LINEAGE_COMPATIBILITY,
                base_source_selection_id=parent_id,
            ),
            game_id=game_id,
            source_selection_id=replacement_id,
            source_manifest_checksum_sha256="b" * 64,
            preflight_policy_version="page-geometry-preflight-v2-auto-anchor",
            page_registration_profile={"schemaVersion": 1},
            lateral_partial_geometry=None,
        )
    assert captured.value.code == "IMAGE_PAGE_GEOMETRY_BASE_MANIFEST_INVALID"


def test_checkpoint_resumes_after_shard_written_before_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = _original(0)
    inventory_checksum = source_inventory_checksum((original,))
    job_id = "00000000-0000-0000-0000-000000000001"
    metadata = {
        "phase": "source_registration",
        "sourceNextIndex": 0,
        "recomputeInventoryChecksumSha256": "b" * 64,
        "reusedSourceCount": 0,
        "recomputedSourceCount": 1,
        "autoAnchorPasses": [],
        "activeAutoAnchorPass": None,
    }
    store = PageGeometryCheckpointStore(
        tmp_path,
        job_id=job_id,
        input_fingerprint_sha256="a" * 64,
        source_inventory_checksum_sha256=inventory_checksum,
    )
    store.initialize({}, metadata=metadata)
    entry = _registered(original)
    real_replace = incremental_module.os.replace
    failed = False

    def fail_first_state_replace(source: object, target: object) -> None:
        nonlocal failed
        if not failed and Path(target).name == "state.json":
            failed = True
            raise OSError("simulated interruption before checkpoint index commit")
        real_replace(source, target)

    monkeypatch.setattr(incremental_module.os, "replace", fail_first_state_replace)
    metadata["sourceNextIndex"] = 1
    with pytest.raises(JobHandlerError) as captured:
        store.append(
            {original.checksum_sha256: entry},
            metadata=metadata,
            all_entries={original.checksum_sha256: entry},
        )
    assert captured.value.code == "IMAGE_PAGE_GEOMETRY_CHECKPOINT_INVALID"

    resumed_store = PageGeometryCheckpointStore(
        tmp_path,
        job_id=job_id,
        input_fingerprint_sha256="a" * 64,
        source_inventory_checksum_sha256=inventory_checksum,
    )
    old_state = resumed_store.load(required=True)
    assert old_state is not None
    assert old_state.entries == {}

    recovered = resumed_store.append(
        {original.checksum_sha256: entry},
        metadata=metadata,
        all_entries={original.checksum_sha256: entry},
    )
    assert recovered.entries == {original.checksum_sha256: entry}
