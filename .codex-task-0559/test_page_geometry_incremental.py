from __future__ import annotations

import json
from pathlib import Path

import game_predictor_worker.images.page_geometry_incremental as incremental_module
import pytest
from game_predictor_worker.images.page_geometry_incremental import (
    EXACT_POLICY_COMPATIBILITY,
    LATERAL_V2_TO_V3_COMPATIBILITY,
    BasePageGeometryManifestDescriptor,
    PageGeometryCheckpointStore,
    load_base_manifest,
    plan_manifest_reuse,
    source_inventory_checksum,
)
from game_predictor_worker.images.source_ingestion import ManagedOriginal
from game_predictor_worker.jobs.runtime import JobHandlerError


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
        dependant.checksum_sha256: _registered(
            dependant, anchor=manual.checksum_sha256
        ),
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
    initial = store.initialize(
        {originals[0].checksum_sha256: first_entry}, metadata=metadata
    )
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
