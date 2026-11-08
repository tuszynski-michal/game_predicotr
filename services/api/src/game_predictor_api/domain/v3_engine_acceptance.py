"""Versioned engine acceptance of persisted neural positions, never human truth."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from .neural_crop_policy import (
    LEGACY_NEURAL_AUTO_CROP_POLICY,
    NEURAL_AUTO_CROP_POLICY,
    full_neural_prediction_geometry,
    neural_auto_crop_blockers,
    neural_auto_crop_evidence,
)
from .neural_grid_operation_pin import OPERATION_PIN_KEY, operation_pin_blockers
from .neural_grid_proposal import NeuralGridProposalError, validate_neural_source_binding

LEGACY_V3_ENGINE_ACCEPTANCE_POLICY = "v3-engine-acceptance-v1"
V3_ENGINE_ACCEPTANCE_POLICY = "v3-engine-acceptance-v2"
GAME_SCOPED_V3_ENGINE_ACCEPTANCE_POLICY = "v3-engine-acceptance-v3"
CALIBRATED_V3_ENGINE_ACCEPTANCE_POLICY = "v3-engine-acceptance-v4"
V3_ENGINE_ACCEPTANCE_POLICIES = (
    LEGACY_V3_ENGINE_ACCEPTANCE_POLICY,
    V3_ENGINE_ACCEPTANCE_POLICY,
    GAME_SCOPED_V3_ENGINE_ACCEPTANCE_POLICY,
    CALIBRATED_V3_ENGINE_ACCEPTANCE_POLICY,
)
V3_ENGINE_ACCEPTANCE_PAYLOAD_KEY = "v3_engine_acceptance_policy_version"
V3_ENGINE_ACCEPTANCE_ACTOR = "system:v3-engine-acceptance-v1"


def is_game_scoped_neural_acceptance(policy: object) -> bool:
    """Trusted job policy owns strict gates, never worker kind/source claims."""
    return policy in (
        GAME_SCOPED_V3_ENGINE_ACCEPTANCE_POLICY,
        CALIBRATED_V3_ENGINE_ACCEPTANCE_POLICY,
    )


def acceptance_for_operation_pin(pin: Mapping[str, object]) -> str:
    """Retry preserves the policy paired with the immutable pin's version."""
    return (
        CALIBRATED_V3_ENGINE_ACCEPTANCE_POLICY
        if pin.get("contractVersion") == "neural-grid-operation-pin-v3"
        else GAME_SCOPED_V3_ENGINE_ACCEPTANCE_POLICY
    )


def crop_policy_for_acceptance(policy: object) -> str | None:
    if policy == LEGACY_V3_ENGINE_ACCEPTANCE_POLICY:
        return LEGACY_NEURAL_AUTO_CROP_POLICY
    if policy == V3_ENGINE_ACCEPTANCE_POLICY or is_game_scoped_neural_acceptance(policy):
        return NEURAL_AUTO_CROP_POLICY
    return None


def pin_v3_engine_acceptance_policy(payload: dict[str, object], fingerprint: str) -> str:
    """Called only at new import creation; retry reads the existing pin."""
    if payload.get("neural_grid_proposal") is None:
        return fingerprint
    from .grid_model_registry import descriptor_sha256
    from .neural_grid_operation_pin import require_operation_pin
    from .neural_grid_proposal import NeuralGridSnapshot

    snapshot = NeuralGridSnapshot.from_payload(payload["neural_grid_proposal"])
    pin = payload.get(OPERATION_PIN_KEY)
    game_id = pin.get("gameId") if isinstance(pin, Mapping) else None
    require_operation_pin(pin, snapshot=snapshot, game_id=cast(str, game_id))
    policy = acceptance_for_operation_pin(cast(Mapping[str, object], pin))
    payload[V3_ENGINE_ACCEPTANCE_PAYLOAD_KEY] = policy
    return hashlib.sha256(
        f"{fingerprint}:{policy}:{descriptor_sha256(pin)}".encode("ascii")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class V3EnginePosition:
    position: int
    sequence: int | None
    geometry: object
    complete: bool
    current_revision: bool
    current_owner: bool
    grid_issue: bool


def qualify_v3_engine_acceptance(
    *,
    policy: object,
    proposal: object,
    binding: object,
    model_snapshot: object,
    game_id: str,
    source_checksum_sha256: str,
    width: int,
    height: int,
    active_slots: Sequence[int],
    sequence_start: int,
    sequence_end: int,
    positions: Sequence[V3EnginePosition],
    deferred: bool,
    source_current: bool,
    operation_pin: object = None,
    qualification_blockers: tuple[str, ...] | None = None,
    available_source_box: Sequence[int] | None = None,
) -> tuple[str, ...]:
    """Return stable blockers; empty means a complete, bound engine result.

    Uncalibrated confidence remains diagnostic. No score threshold, approval
    field or training eligibility follows from this structural qualification.
    """
    crop_policy = crop_policy_for_acceptance(policy)
    if crop_policy is None:
        return ("V3_ACCEPTANCE_POLICY_UNSUPPORTED",)
    try:
        checked = validate_neural_source_binding(binding, proposal)
    except NeuralGridProposalError:
        return ("V3_ACCEPTANCE_PROVENANCE_INVALID",)
    source = cast(Mapping[str, object], proposal)
    reasons: list[str] = []
    if policy == CALIBRATED_V3_ENGINE_ACCEPTANCE_POLICY and (
        not isinstance(operation_pin, Mapping)
        or operation_pin.get("contractVersion") != "neural-grid-operation-pin-v3"
    ):
        reasons.append("NEURAL_GRID_OPERATION_POLICY_MISMATCH")
    if is_game_scoped_neural_acceptance(policy):
        reasons.extend(
            operation_pin_blockers(operation_pin, model_snapshot=model_snapshot, game_id=game_id)
        )
        reasons.extend(
            qualification_blockers
            if qualification_blockers is not None
            else ("NEURAL_GRID_GAME_EVALUATION_UNCHECKED",)
        )
    if (
        not source_current
        or source["gameId"] != game_id
        or source["sourceChecksumSha256"] != source_checksum_sha256
        or source["sourceWidth"] != width
        or source["sourceHeight"] != height
        or source["engineSnapshot"] != model_snapshot
    ):
        reasons.append("V3_ACCEPTANCE_SOURCE_OR_MODEL_DRIFT")
    expected = tuple(range(sequence_end - sequence_start + 1))
    if (
        not expected
        or tuple(active_slots) != expected
        or checked["confirmedRange"]
        != {"sequenceRangeStart": sequence_start, "sequenceRangeEnd": sequence_end}
        or checked["missingPositionIndexes"]
        or sorted(item.position for item in positions) != list(expected)
    ):
        reasons.append("V3_ACCEPTANCE_POSITION_CONFLICT")
    if deferred:
        reasons.append("V3_ACCEPTANCE_DEFERRED")
    detections = {
        item["detectionId"]: item for item in cast(list[Mapping[str, object]], source["detections"])
    }
    for item in positions:
        geometry = item.geometry
        if not item.complete:
            reasons.append("V3_ACCEPTANCE_PARTIAL")
        if not item.current_revision:
            reasons.append("V3_ACCEPTANCE_REVISION_CONFLICT")
        if not item.current_owner or item.sequence != sequence_start + item.position:
            reasons.append("V3_ACCEPTANCE_OWNER_CONFLICT")
        if item.grid_issue:
            reasons.append("V3_ACCEPTANCE_GRID_ISSUE")
        if not isinstance(geometry, Mapping) or not full_neural_prediction_geometry(
            geometry,
            position=item.position,
            sequence=item.sequence,
            width=width,
            height=height,
            game_id=game_id,
            source_checksum_sha256=source_checksum_sha256,
        ):
            reasons.append("V3_ACCEPTANCE_GEOMETRY_INVALID")
            continue
        detection = detections.get(geometry.get("detectionId"))
        if (
            detection is None
            or geometry.get("neuralProposalBinding") != checked
            or geometry.get("latticeNodes") != detection["latticeNodes"]
            or detection["structurallyValid"] is not True
            or detection["cellVisibility"] != ["full"] * 15
            or geometry.get("neuralExecutionPolicy") != crop_policy
        ):
            reasons.append("V3_ACCEPTANCE_GEOMETRY_INVALID")
        if crop_policy == NEURAL_AUTO_CROP_POLICY and detection is not None:
            if policy == CALIBRATED_V3_ENGINE_ACCEPTANCE_POLICY:
                from .calibrated_neural_evidence import calibrated_result_blockers

                reasons.extend(
                    calibrated_result_blockers(
                        geometry.get("neuralCalibrationEvidence"),
                        pin=operation_pin,
                        proposal=source,
                        detection=detection,
                        available_source_box=available_source_box,
                    )
                )
            if geometry.get("neuralAcceptanceEvidence") != neural_auto_crop_evidence(detection):
                reasons.append("V3_ACCEPTANCE_EVIDENCE_INVALID")
            reasons.extend(
                neural_auto_crop_blockers(
                    policy=crop_policy,
                    detection=detection,
                    binding=checked,
                    position=item.position,
                    width=width,
                    height=height,
                )
            )
    return tuple(dict.fromkeys(reasons))
