"""Versioned engine acceptance of persisted neural positions, never human truth."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from .neural_crop_policy import NEURAL_AUTO_CROP_POLICY, full_neural_prediction_geometry
from .neural_grid_proposal import NeuralGridProposalError, validate_neural_source_binding

V3_ENGINE_ACCEPTANCE_POLICY = "v3-engine-acceptance-v1"
V3_ENGINE_ACCEPTANCE_PAYLOAD_KEY = "v3_engine_acceptance_policy_version"
V3_ENGINE_ACCEPTANCE_ACTOR = "system:v3-engine-acceptance-v1"


def pin_v3_engine_acceptance_policy(payload: dict[str, object], fingerprint: str) -> str:
    """Called only at new import creation; retry reads the existing pin."""
    if payload.get("neural_grid_proposal") is None:
        return fingerprint
    payload[V3_ENGINE_ACCEPTANCE_PAYLOAD_KEY] = V3_ENGINE_ACCEPTANCE_POLICY
    return hashlib.sha256(
        f"{fingerprint}:{V3_ENGINE_ACCEPTANCE_POLICY}".encode("ascii")
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
) -> tuple[str, ...]:
    """Return stable blockers; empty means a complete, bound engine result.

    Uncalibrated confidence remains diagnostic. No score threshold, approval
    field or training eligibility follows from this structural qualification.
    """
    if policy != V3_ENGINE_ACCEPTANCE_POLICY:
        return ("V3_ACCEPTANCE_POLICY_UNSUPPORTED",)
    try:
        checked = validate_neural_source_binding(binding, proposal)
    except NeuralGridProposalError:
        return ("V3_ACCEPTANCE_PROVENANCE_INVALID",)
    source = cast(Mapping[str, object], proposal)
    reasons = []
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
            or geometry.get("neuralExecutionPolicy") != NEURAL_AUTO_CROP_POLICY
        ):
            reasons.append("V3_ACCEPTANCE_GEOMETRY_INVALID")
    return tuple(dict.fromkeys(reasons))
