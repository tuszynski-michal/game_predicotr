"""Measure existing detections, including real crop support, without running a model."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
from game_predictor_api.domain.grid_model_registry import descriptor_sha256 as digest
from game_predictor_api.domain.grid_visibility_contract import require_output_contract

from ..geometry_core.settings import BoardPreset
from .full_board_completeness import (
    calibration_routing_sha,
    features,
    input_support,
    perspective_neighbor_deviation,
)
from .grid_rescue_strategy import completeness_suspicious, slots


def runtime_evidence(
    *,
    found: list[Any],
    detections: list[dict[str, Any]],
    observation: dict[str, Any],
    pin: object,
    bundle: Path,
    bundle_sha: str,
    source_sha: str,
    width: int,
    height: int,
    available_source_box: list[int] | None = None,
) -> dict[str, Any]:
    if not isinstance(pin, Mapping) or pin.get("contractVersion") != "neural-grid-operation-pin-v3":
        return {}
    qualification = pin.get("automaticQualification", {})
    if qualification.get("state") != "qualified":
        return {}
    # The original canvas may be padded after managed cropping. Unknown extent
    # never becomes full support just because its raster has original dimensions.
    if available_source_box is None or len(available_source_box) != 4:
        return {}
    left, top, right, bottom = available_source_box
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        return {}
    available = np.array([[left, top], [right, top], [right, bottom], [left, bottom]])
    profile = qualification["profile"]
    path = bundle / "bundle.json"
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("COMPLETENESS_PRESET_SIZE")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != bundle_sha:
        raise ValueError("COMPLETENESS_PRESET_CHANGED")
    archived = json.loads(content)
    board = BoardPreset.model_validate(archived["preset"]["board"])
    contract = None
    if profile["version"] == "full-board-auto-profile-v2":
        if archived.get("format") != "neural-grid-bundle-v2":
            return {}
        contract = require_output_contract(archived)
    route = observation.get("routing")
    selected = observation.get("selectedPath")
    routing_sha = calibration_routing_sha(pin["catalogueManifestSha256"], board, route, selected)
    if routing_sha != profile["routingSha256"]:
        return {}
    binding = slots(found)
    neighbors = perspective_neighbor_deviation(found, binding or {})
    primary_found = observation.get("baseline", found)
    primary_binding = slots(primary_found)
    result = {}
    for index, (detection, document) in enumerate(zip(found, detections, strict=True)):
        positions = [position for position, value in (binding or {}).items() if value == index]
        position = positions[0] if len(positions) == 1 else None
        primary = (
            primary_found[primary_binding[position]]
            if primary_binding and position in primary_binding
            else None
        )
        completed = position in observation.get("cropPositions", []) and primary is not detection
        geometry = observation.get("boardGeometry") if completed else None
        support = input_support(detection.screen_quad, board, geometry)
        required = (
            route is not None
            and primary is not None
            and completeness_suspicious(primary, width, height, route)
        )
        vector = features(
            detection,
            width=width,
            height=height,
            real_input_support=support,
            game_log_aspect_reference=profile["gameLogAspectReference"],
            neighbor_deviation=neighbors.get(position) if position is not None else None,
            neighbor_applicable=len(found) > 1,
            primary=primary,
            rescue_required=required,
            rescue_completed=completed,
            available_source_support=available,
            output_contract=contract,
            board=board,
            geometry=geometry,
        )
        if position is None:
            vector = vector.model_copy(
                update={"hardReasons": (*vector.hardReasons, "COMPLETENESS_SLOT_BINDING_REQUIRED")}
            )
        value = {
            "version": "full-board-result-evidence-v2"
            if contract is not None
            else "full-board-result-evidence-v1",
            "sourceSha256": source_sha,
            "modelManifestSha256": pin["catalogueManifestSha256"],
            "operationPinSha256": pin["pinSha256"],
            "profileSha256": profile["sha256"],
            "detectionId": document["detectionId"],
            "nodesSha256": digest(document["latticeNodes"]),
            "features": vector.model_dump(mode="json"),
        }
        result[document["detectionId"]] = {**value, "sha256": digest(value)}
    return result
