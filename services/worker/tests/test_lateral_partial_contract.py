from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from game_predictor_worker.images.lateral_partial_contract import (
    GeometryEngineVariant,
    LateralPartialContractError,
    LateralPartialGeometrySnapshot,
    require_geometry_engine_variant_available,
)
from game_predictor_worker.images.pipeline_contract import (
    GeometryPipelineRolloutSnapshot,
    GeometryRolloutMode,
    ImagePipelineContractError,
    canonical_json_bytes,
    effective_pipeline_fingerprint,
)
from game_predictor_worker.images.production_workflow import _geometry_rollout_snapshot
from game_predictor_worker.jobs.runtime import JobHandlerError
from test_image_pipeline_contract import _active_lattice_rollout, _candidate_rollout, _rollout


def test_partial_policy_roundtrip_and_detached_payload() -> None:
    policy = LateralPartialGeometrySnapshot()
    raw = policy.to_payload()
    assert LateralPartialGeometrySnapshot.from_payload(json.loads(json.dumps(raw))) == policy
    raw["minimumInliers"] = 0
    assert policy.to_payload()["minimumInliers"] == 9


@pytest.mark.parametrize(
    "field,value",
    [
        ("policyVersion", "new-unpinned-version"),
        ("checksumSha256", "a" * 64),
        ("minimumInliers", 8),
        ("maximumAdditionalPasses", True),
        ("verticalClippingAllowed", True),
        ("requiresManualConfirmation", False),
        ("excludeFromPageAnchors", False),
        ("analysisWidth", 1600),
    ],
)
def test_policy_drift_is_rejected(field: str, value: object) -> None:
    raw = LateralPartialGeometrySnapshot().to_payload()
    raw[field] = value
    with pytest.raises(LateralPartialContractError) as error:
        LateralPartialGeometrySnapshot.from_payload(raw)
    assert error.value.code == "IMAGE_LATERAL_PARTIAL_SNAPSHOT_DRIFT"


@pytest.mark.parametrize("raw", [None, {}, {"unknown": 1}])
def test_incomplete_policy_is_rejected(raw: object) -> None:
    with pytest.raises(LateralPartialContractError):
        LateralPartialGeometrySnapshot.from_payload(raw)


def test_new_rollout_roundtrip_and_pipeline_identity() -> None:
    v3 = _active_lattice_rollout()
    v3_bytes = canonical_json_bytes(v3.to_payload())
    v4 = replace(v3, lateral_partial_geometry=LateralPartialGeometrySnapshot())
    assert v4.to_payload()["schemaVersion"] == "virtual-geometry-rollout-snapshot-v4"
    replay = GeometryPipelineRolloutSnapshot.from_payload(json.loads(json.dumps(v4.to_payload())))
    assert replay == v4
    assert replay.active_lattice_geometry == v3.active_lattice_geometry
    assert replay.geometry_engine_version == v3.geometry_engine_version
    assert effective_pipeline_fingerprint("a" * 64, replay) != effective_pipeline_fingerprint(
        "a" * 64, v3
    )
    assert canonical_json_bytes(v3.to_payload()) == v3_bytes


@pytest.mark.parametrize(
    "baseline",
    [_rollout(GeometryRolloutMode.LEGACY), _candidate_rollout(), _active_lattice_rollout()],
)
def test_absent_extension_preserves_historical_bytes(
    baseline: GeometryPipelineRolloutSnapshot,
) -> None:
    before = canonical_json_bytes(baseline.to_payload())
    replay = GeometryPipelineRolloutSnapshot.from_payload(json.loads(before))
    assert canonical_json_bytes(replay.to_payload()) == before
    assert "lateralPartialGeometry" not in replay.to_payload()
    # Obtained from the pre-change implementation at d74fc4d7, not from replay.
    historical_checksums = {
        "virtual-geometry-rollout-snapshot-v1": (
            "16c93e04945897e097204850d551dbdcc98825e7df02c0d3ea5da7e763721b82"
        ),
        "virtual-geometry-rollout-snapshot-v2": (
            "2be44b7f5b673b3a9c870171b859609ff88f5fd73fcea3257f216c4ee664e6e4"
        ),
        "virtual-geometry-rollout-snapshot-v3": (
            "ee4a22d5670c71e8b0601948ed3ab6dbeba38b38751d134cef0a69c2986ab878"
        ),
    }
    assert replay.checksum_sha256 == historical_checksums[replay.to_payload()["schemaVersion"]]


def test_partial_extension_cannot_masquerade_as_v3() -> None:
    raw = _active_lattice_rollout().to_payload()
    raw["lateralPartialGeometry"] = LateralPartialGeometrySnapshot().to_payload()
    with pytest.raises(ImagePipelineContractError) as error:
        GeometryPipelineRolloutSnapshot.from_payload(raw)
    assert error.value.code == "IMAGE_LATERAL_PARTIAL_SNAPSHOT_INVALID"


def test_partial_extension_requires_full_board_baseline() -> None:
    with pytest.raises(ImagePipelineContractError):
        replace(
            _rollout(GeometryRolloutMode.LEGACY),
            lateral_partial_geometry=LateralPartialGeometrySnapshot(),
        )


def test_unimplemented_variant_never_dispatches_to_v3() -> None:
    raw = replace(
        _active_lattice_rollout(), lateral_partial_geometry=LateralPartialGeometrySnapshot()
    ).to_payload()
    with pytest.raises(JobHandlerError) as error:
        _geometry_rollout_snapshot(SimpleNamespace(input_payload={"image_geometry_rollout": raw}))
    assert error.value.code == "IMAGE_GEOMETRY_ENGINE_VARIANT_NOT_ENABLED"
    require_geometry_engine_variant_available(None)
    with pytest.raises(LateralPartialContractError) as error:
        require_geometry_engine_variant_available("unknown")
    assert error.value.code == "IMAGE_GEOMETRY_ENGINE_VARIANT_UNSUPPORTED"
    with pytest.raises(LateralPartialContractError) as error:
        require_geometry_engine_variant_available(
            GeometryEngineVariant.STRUCTURED_LATTICE_V4_PARTIAL_SIDES
        )
    assert error.value.code == "IMAGE_GEOMETRY_ENGINE_VARIANT_NOT_ENABLED"
