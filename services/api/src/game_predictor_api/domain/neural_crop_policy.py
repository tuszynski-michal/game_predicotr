"""Versioned operational availability, distinct from human geometry approval."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import cast

from .image_geometry_v2 import (
    MAX_PAGE_BOARD_SLOTS,
    ImageGeometryContractError,
    SourceLatticeNodes,
    SourcePoint,
)
from .neural_grid_proposal import lattice_cell_quads, lattice_visibility

LEGACY_NEURAL_AUTO_CROP_POLICY = "neural-auto-crop-v1"
NEURAL_AUTO_CROP_POLICY = "neural-auto-crop-v2"
NEURAL_AUTO_CROP_POLICIES = (LEGACY_NEURAL_AUTO_CROP_POLICY, NEURAL_AUTO_CROP_POLICY)
NEURAL_AUTO_CROP_PAYLOAD_KEY = "neural_grid_execution_policy_version"
NEURAL_AUTO_CROP_BLOCKING_REASONS = frozenset(
    {
        "NEURAL_GRID_FIT_FAILED",
        "NEURAL_GRID_FIT_OUTLIERS",
        "NEURAL_GRID_LAYOUT_UNSUPPORTED",
        "NEURAL_GRID_SLOT_BINDING_REQUIRED",
        "NEURAL_GRID_SLOT_DETECTION_MISSING",
    }
)


def neural_auto_crop_evidence(detection: Mapping[str, object]) -> dict[str, object]:
    """Persist only the small detection facts needed by operational readers."""
    return {
        key: detection.get(key) for key in ("structurallyValid", "cellVisibility", "reasonCodes")
    }


def neural_auto_crop_blockers(
    *,
    policy: object,
    detection: object,
    binding: object,
    position: int,
    width: int,
    height: int,
    rows: int = 3,
    columns: int = 5,
    valid_pixel_box: tuple[float, float, float, float] | None = None,
) -> tuple[str, ...]:
    """Qualify a bound detection; callers retain source/model and owner fences.

    The explicit legacy branch preserves the old worker decision. V2 checks
    actual nodes, visibility and the complete binding, never an automatic flag.
    ``valid_pixel_box`` optionally restricts a retained crop's real pixels.
    Without it this checks image bounds only; production retained-crop bounds
    remain enforced by the worker's require_inside_valid_box and renderer.
    """
    if policy not in NEURAL_AUTO_CROP_POLICIES:
        return ("NEURAL_GRID_EXECUTION_POLICY_UNSUPPORTED",)
    if not isinstance(detection, Mapping):
        return ("NEURAL_GRID_SLOT_DETECTION_MISSING",)
    visibility = detection.get("cellVisibility")
    if policy == LEGACY_NEURAL_AUTO_CROP_POLICY:
        return (
            ()
            if (
                detection.get("structurallyValid") is True
                and isinstance(visibility, list)
                and all(value == "full" for value in visibility)
            )
            else ("NEURAL_GRID_GEOMETRY_INVALID",)
        )
    reasons: list[str] = []
    raw_reasons = detection.get("reasonCodes")
    if not isinstance(raw_reasons, list) or any(not isinstance(x, str) for x in raw_reasons):
        reasons.append("NEURAL_GRID_EVIDENCE_INVALID")
    else:
        reasons.extend(code for code in raw_reasons if code in NEURAL_AUTO_CROP_BLOCKING_REASONS)
    if (rows, columns) != (3, 5):
        reasons.append("NEURAL_GRID_LAYOUT_UNSUPPORTED")
    if not isinstance(binding, Mapping):
        reasons.append("NEURAL_GRID_SLOT_BINDING_REQUIRED")
    else:
        assignments, active = binding.get("assignments"), binding.get("confirmedRange")
        if not isinstance(assignments, list) or not isinstance(active, Mapping):
            reasons.append("NEURAL_GRID_SLOT_BINDING_REQUIRED")
        else:
            start, end = active.get("sequenceRangeStart"), active.get("sequenceRangeEnd")
            indexes = [x.get("positionIndex") for x in assignments if isinstance(x, Mapping)]
            identities = [x.get("detectionId") for x in assignments if isinstance(x, Mapping)]
            if (
                type(start) is not int
                or type(end) is not int
                or not 1 <= end - start + 1 <= MAX_PAGE_BOARD_SLOTS
                or binding.get("missingPositionIndexes") != []
                or len(indexes) != len(assignments)
                or any(type(x) is not int for x in indexes)
                or sorted(cast(list[int], indexes)) != list(range(end - start + 1))
                or any(not isinstance(x, str) for x in identities)
                or len(set(cast(list[str], identities))) != len(identities)
                or not any(
                    x.get("positionIndex") == position
                    and x.get("detectionId") == detection.get("detectionId")
                    for x in assignments
                    if isinstance(x, Mapping)
                )
            ):
                reasons.append("NEURAL_GRID_SLOT_BINDING_REQUIRED")
    try:
        nodes = detection.get("latticeNodes")
        quads = lattice_cell_quads(nodes, width=width, height=height)
        if detection.get("structurallyValid") is not True:
            reasons.append("NEURAL_GRID_GEOMETRY_INVALID")
        if (
            visibility != ["full"] * 15
            or lattice_visibility(quads, width=width, height=height) != ["full"] * 15
        ):
            reasons.append("NEURAL_GRID_PIXELS_UNAVAILABLE")
        if valid_pixel_box is not None:
            left, top, right, bottom = valid_pixel_box
            if any(
                not left <= float(node["x"]) <= right or not top <= float(node["y"]) <= bottom
                for node in cast(Sequence[Mapping[str, float]], nodes)
            ):
                reasons.append("NEURAL_GRID_PIXELS_UNAVAILABLE")
    except (ImageGeometryContractError, KeyError, TypeError, ValueError):
        reasons.append("NEURAL_GRID_GEOMETRY_INVALID")
    return tuple(dict.fromkeys(reasons))


def pin_neural_crop_policy(payload: dict[str, object], fingerprint: str) -> str:
    if payload.get("neural_grid_proposal") is None:
        return fingerprint
    payload[NEURAL_AUTO_CROP_PAYLOAD_KEY] = NEURAL_AUTO_CROP_POLICY
    return hashlib.sha256(f"{fingerprint}:{NEURAL_AUTO_CROP_POLICY}".encode("ascii")).hexdigest()


def full_neural_prediction_geometry(
    geometry: object,
    *,
    position: int,
    sequence: int | None,
    width: int,
    height: int,
    game_id: str,
    source_checksum_sha256: str,
) -> bool:
    """Project full-lattice consistency and bound identity, without approval.

    V2 checks evidence stored in this geometry, not its authenticity against
    the immutable proposal. Engine acceptance and the automatic-write guard
    separately compare that proposal; this projection cannot authorize writes.
    """
    if not isinstance(geometry, Mapping):
        return False
    policy = geometry.get("neuralExecutionPolicy")
    if policy not in NEURAL_AUTO_CROP_POLICIES:
        return False
    checksum = geometry.get("neuralProposalChecksumSha256")
    if (
        not isinstance(checksum, str)
        or len(checksum) != 64
        or any(char not in "0123456789abcdef" for char in checksum)
    ):
        return False
    binding = geometry.get("neuralProposalBinding")
    nodes = geometry.get("latticeNodes")
    if not isinstance(binding, Mapping) or not isinstance(nodes, list):
        return False
    if (
        binding.get("proposalChecksumSha256") != checksum
        or binding.get("gameId") != game_id
        or binding.get("sourceChecksumSha256") != source_checksum_sha256
        or binding.get("sourceWidth") != width
        or binding.get("sourceHeight") != height
    ):
        return False
    active = binding.get("confirmedRange")
    assignments = binding.get("assignments")
    if not isinstance(active, Mapping) or not isinstance(assignments, list):
        return False
    start, end = active.get("sequenceRangeStart"), active.get("sequenceRangeEnd")
    if (
        not isinstance(start, int)
        or not isinstance(end, int)
        or sequence != start + position
        or not start <= sequence <= end
    ):
        return False
    matches = [
        item
        for item in assignments
        if isinstance(item, Mapping) and item.get("positionIndex") == position
    ]
    detection_id = geometry.get("detectionId")
    if (
        len(matches) != 1
        or not isinstance(detection_id, str)
        or matches[0].get("detectionId") != detection_id
    ):
        return False
    if (
        sum(
            isinstance(item, Mapping) and item.get("detectionId") == detection_id
            for item in assignments
        )
        != 1
    ):
        return False
    if policy == NEURAL_AUTO_CROP_POLICY:
        evidence = geometry.get("neuralAcceptanceEvidence")
        if not isinstance(evidence, Mapping) or neural_auto_crop_blockers(
            policy=policy,
            detection={**evidence, "detectionId": detection_id, "latticeNodes": nodes},
            binding=binding,
            position=position,
            width=width,
            height=height,
        ):
            return False
    try:
        surface = SourceLatticeNodes(
            tuple(SourcePoint(float(point["x"]), float(point["y"])) for point in nodes)
        )
        if any(not 0 <= point.x <= width or not 0 <= point.y <= height for point in surface.nodes):
            return False
        return geometry.get("quad") == [nodes[index] for index in (0, 5, 23, 18)]
    except (ImageGeometryContractError, KeyError, TypeError, ValueError):
        return False
