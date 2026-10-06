"""Versioned operational availability, distinct from human geometry approval."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from .image_geometry_v2 import ImageGeometryContractError, SourceLatticeNodes, SourcePoint

NEURAL_AUTO_CROP_POLICY = "neural-auto-crop-v1"
NEURAL_AUTO_CROP_PAYLOAD_KEY = "neural_grid_execution_policy_version"


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
    """Require the exact full lattice and unique bound identity, without approval."""
    if not isinstance(geometry, Mapping):
        return False
    if geometry.get("neuralExecutionPolicy") != NEURAL_AUTO_CROP_POLICY:
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
    try:
        surface = SourceLatticeNodes(
            tuple(SourcePoint(float(point["x"]), float(point["y"])) for point in nodes)
        )
        if any(not 0 <= point.x <= width or not 0 <= point.y <= height for point in surface.nodes):
            return False
        return geometry.get("quad") == [nodes[index] for index in (0, 5, 23, 18)]
    except (ImageGeometryContractError, KeyError, TypeError, ValueError):
        return False
