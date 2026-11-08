"""One versioned rescue path shared by selection evaluation and durable inference."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
from game_predictor_api.domain.image_geometry_v2 import SourcePoint, SourceQuad
from game_predictor_api.domain.neural_grid_proposal import associate_quad_slots

from ..geometry_core.inference import BoardDetection
from ..geometry_core.metrics import quad_iou
from ..geometry_core.preprocessing import quad_is_usable
from ..geometry_core.rescue import GridRescueVariantV1, GridRescueVariantV2

ROUTING_POLICY = "grid-rescue-exact-slots-fit-or-pixels-v1"
COMPLETENESS_ROUTING_POLICY = "grid-rescue-exact-slots-input-completeness-v2"


def completeness_routing(selection: Mapping[str, Any], board: Any) -> dict[str, Any]:
    """Frozen before A path validation; no B acceptance thresholds enter routing."""
    from game_predictor_api.domain.grid_training_cohorts import digest

    from ..geometry_core.settings import BoardPreset

    if selection.get("policy") != "validation-purpose-a-v1":
        raise ValueError("GRID_RESCUE_ROUTING_A_REQUIRED")
    value = {
        "version": COMPLETENESS_ROUTING_POLICY,
        "selectionInputSha256": selection["sha256"],
        "boardPreset": BoardPreset.model_validate(board, from_attributes=True).model_dump(
            mode="json"
        ),
        "coverageEpsilon": 1e-6,
        "coverageUnit": "missing-cell-area-fraction-normalized-xy-v1",
        "trigger": "legacy-or-fitted-cell-outside-real-board-input-v1",
    }
    return {**value, "sha256": digest(value)}


def require_completeness_routing(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = completeness_routing(
        {"policy": "validation-purpose-a-v1", "sha256": value.get("selectionInputSha256")},
        value.get("boardPreset"),
    )
    if (
        dict(value) != expected
        or not isinstance(value.get("selectionInputSha256"), str)
        or len(value["selectionInputSha256"]) != 64
    ):
        raise ValueError("GRID_RESCUE_ROUTING_PROOF_REQUIRED")
    return expected


def completeness_suspicious(
    detection: BoardDetection, width: int, height: int, routing: Mapping[str, Any]
) -> bool:
    from ..geometry_core.settings import BoardPreset
    from .full_board_completeness import input_support, missing_cell_area

    if detection.nodes is None or suspicious(detection, width, height):
        return True
    try:
        support = input_support(
            detection.screen_quad, BoardPreset.model_validate(routing["boardPreset"])
        )
        missing = missing_cell_area(detection.nodes, support, width, height)
    except (ValueError, np.linalg.LinAlgError):
        return True
    return missing is None or missing > routing["coverageEpsilon"]


@dataclass(frozen=True)
class RescueResult:
    detections: list[BoardDetection]
    redetect_calls: int
    crop_calls: dict[int, int]
    reasons: tuple[str, ...]
    replacement_positions: tuple[int, ...] = ()


def slots(detections: list[BoardDetection], *, screen: bool = False) -> dict[int, int] | None:
    quads = []
    for detection in detections:
        if not screen and detection.nodes is None:
            return None
        points = detection.screen_quad if screen else np.asarray(detection.nodes)[[0, 5, 23, 18]]
        if points.shape != (4, 2) or not np.isfinite(points).all() or not quad_is_usable(points):
            return None
        try:
            p0, p1, p2, p3 = [SourcePoint(x=float(x), y=float(y)) for x, y in points]
            quads.append(SourceQuad(corners=(p0, p1, p2, p3)))
        except ValueError:
            return None
    ordered = associate_quad_slots(quads, len(detections))
    return None if ordered is None else dict(enumerate(ordered))


def suspicious(detection: BoardDetection, width: int, height: int) -> bool:
    nodes = detection.nodes
    return (
        nodes is None
        or not np.isfinite(nodes).all()
        or bool(
            set(detection.reasons)
            & {
                "NEURAL_GRID_FIT_FAILED",
                "NEURAL_GRID_FIT_OUTLIERS",
                "NEURAL_GRID_SCREEN_QUAD_INVALID",
            }
        )
        or bool(
            np.any(nodes[:, 0] < 0)
            or np.any(nodes[:, 0] > width)
            or np.any(nodes[:, 1] < 0)
            or np.any(nodes[:, 1] > height)
        )
    )


def execute_path(
    baseline: list[BoardDetection],
    *,
    width: int,
    height: int,
    variant: GridRescueVariantV1 | GridRescueVariantV2,
    path: str,
    detect: Callable[[Any], list[BoardDetection] | None],
    recrop: Callable[[int, BoardDetection, Any], BoardDetection | None],
    expected_positions: set[int] | None = None,
    trigger: Callable[[BoardDetection, int, int], bool] = suspicious,
    routing: Mapping[str, Any] | None = None,
) -> RescueResult:
    # This routing version was validated on A with this exact trigger. T4 must
    # introduce and validate a new routing proof before enabling another trigger.
    if trigger is not suspicious:
        return RescueResult(baseline, 0, {}, ("GRID_RESCUE_ROUTING_PROOF_REQUIRED",))
    if routing is not None:
        checked_routing = require_completeness_routing(routing)

        def trigger(detection: BoardDetection, width: int, height: int) -> bool:
            return completeness_suspicious(detection, width, height, checked_routing)

    if path not in variant.paths:
        raise ValueError("GRID_RESCUE_PATH_UNSUPPORTED")
    binding = slots(baseline)
    if binding is None or (expected_positions is not None and set(binding) != expected_positions):
        return RescueResult(baseline, 0, {}, ("GRID_RESCUE_SLOT_BINDING_REQUIRED",))
    targets = {
        position: index
        for position, index in binding.items()
        if trigger(baseline[index], width, height)
    }
    if not targets:
        return RescueResult(baseline, 0, {}, ("GRID_RESCUE_NOT_TRIGGERED",))
    found = baseline
    remap = binding
    redetect = 0
    if path in ("screen_only", "combined"):
        detected = detect(variant.screen)
        redetect = 1
        if detected is None:
            return RescueResult(baseline, redetect, {}, ("GRID_RESCUE_ATTEMPT_CONSUMED",))
        found = detected
        redetected = slots(found, screen=True)
        if redetected is None or set(redetected) != set(binding):
            return RescueResult(baseline, redetect, {}, ("GRID_RESCUE_REDETECTION_AMBIGUOUS",))
        for position, index in binding.items():
            overlaps = [
                other
                for other, candidate in enumerate(found)
                if quad_iou(baseline[index].screen_quad, candidate.screen_quad) >= 0.5
            ]
            if overlaps != [redetected[position]]:
                return RescueResult(baseline, redetect, {}, ("GRID_RESCUE_REDETECTION_AMBIGUOUS",))
        remap = redetected
    output = list(baseline)
    calls = {}
    reasons = []
    replacements = []
    geometry = variant.board if path in ("board_only", "combined") else None
    for position, index in sorted(targets.items()):
        replacement = recrop(position, found[remap[position]], geometry)
        calls[position] = 1
        if replacement is None:
            reasons.append("GRID_RESCUE_ATTEMPT_CONSUMED")
        else:
            output[index] = replacement
            replacements.append(position)
    return RescueResult(output, redetect, calls, tuple(sorted(set(reasons))), tuple(replacements))
