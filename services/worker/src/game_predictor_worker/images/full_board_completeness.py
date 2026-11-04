"""Measured geometry features on existing observations, without network execution."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import cv2
import numpy as np
from game_predictor_api.domain.full_board_calibration import AXES, COVERAGE_EPSILON, FeatureVector
from game_predictor_api.domain.grid_model_registry import descriptor_sha256

from ..geometry_core.inference import BoardDetection
from ..geometry_core.metrics import quad_iou
from ..geometry_core.preprocessing import board_rectifier, transform_points
from ..geometry_core.rescue import BoardCropGeometryV1
from ..geometry_core.settings import BoardPreset

CORNERS = [0, 5, 23, 18]


def calibration_routing_sha(
    recognition_sha: str, board: Any, routing: Any, selected_path: str | None
) -> str:
    """One canonical identity for the actual evaluator and archived runtime preset."""
    return descriptor_sha256(
        {
            "recognitionManifestSha256": recognition_sha,
            "boardPreset": BoardPreset.model_validate(board, from_attributes=True).model_dump(
                mode="json"
            ),
            "routing": routing,
            "selectedPath": selected_path,
        }
    )


def cell_polygons(nodes: np.ndarray) -> list[np.ndarray]:
    value = np.asarray(nodes, dtype=np.float64)
    if value.shape != (24, 2) or not np.isfinite(value).all():
        raise ValueError("COMPLETENESS_NODES_INVALID")
    return [
        value[[r * 6 + c, r * 6 + c + 1, (r + 1) * 6 + c + 1, (r + 1) * 6 + c]]
        for r in range(3)
        for c in range(5)
    ]


def missing_cell_area(
    nodes: np.ndarray, support: np.ndarray, width: int, height: int
) -> float | None:
    """Maximum missing cell fraction; unitless, after normalization x/W,y/H.

    Convex real input/output support is explicit. Invalid support is unknown;
    numerical noise <=1e-6 is not a product allowance for missing content.
    """
    if width <= 0 or height <= 0:
        raise ValueError("COMPLETENESS_IMAGE_SIZE_INVALID")
    scale = np.array([width, height], dtype=np.float64)
    polygon = np.asarray(support, dtype=np.float64) / scale
    if polygon.shape != (4, 2) or not np.isfinite(polygon).all():
        return None
    contour = polygon.astype(np.float32)
    if not cv2.isContourConvex(contour) or cv2.contourArea(contour) <= 0:
        return None
    ratios = []
    for cell in cell_polygons(nodes):
        cell = (cell / scale).astype(np.float32)
        area = abs(float(cv2.contourArea(cell)))
        if area <= 0 or not cv2.isContourConvex(cell):
            return None
        intersection, _ = cv2.intersectConvexConvex(cell, contour)
        ratios.append(max(0.0, min(1.0, (area - float(intersection)) / area)))
    return max(ratios)


def input_support(
    quad: np.ndarray, board: BoardPreset, geometry: BoardCropGeometryV1 | None = None
) -> np.ndarray:
    matrix = board_rectifier(quad, board, geometry=geometry)
    width, height = board.canvas
    return transform_points(
        np.array([[0, 0], [width, 0], [width, height], [0, height]], np.float32),
        np.asarray(np.linalg.inv(matrix), dtype=np.float64),
    )


def gt_cropped(
    gt_nodes: np.ndarray,
    output_nodes: np.ndarray | None,
    *,
    real_input_support: np.ndarray | None,
    width: int,
    height: int,
) -> bool | None:
    if output_nodes is None or real_input_support is None:
        return None
    source = np.array([[0, 0], [width, 0], [width, height], [0, height]], np.float64)
    values = [
        missing_cell_area(gt_nodes, support, width, height)
        for support in (source, real_input_support, np.asarray(output_nodes)[CORNERS])
    ]
    if any(value is None for value in values):
        return None
    return any(value > COVERAGE_EPSILON for value in values if value is not None)


def log_aspect(nodes: np.ndarray) -> float | None:
    value = np.asarray(nodes)
    if value.shape != (24, 2) or not np.isfinite(value).all():
        return None
    tl, tr, br, bl = value[CORNERS]
    width = math.sqrt(float(np.linalg.norm(tr - tl) * np.linalg.norm(br - bl)))
    height = math.sqrt(float(np.linalg.norm(bl - tl) * np.linalg.norm(br - tr)))
    return math.log(width / height) if width > 0 and height > 0 else None


def perspective_neighbor_deviation(
    detections: Sequence[BoardDetection], binding: Mapping[int, int]
) -> dict[int, float | None]:
    """Rectify measured centers to known page slots, then compare local areas.

    This is only a suspicion signal. Four noncollinear, explicitly bound slots
    are needed; failure never means agreement or supplies a missing sequence.
    """
    result: dict[int, float | None] = dict.fromkeys(binding)
    if len(binding) < 4 or any(index < 0 or index >= len(detections) for index in binding.values()):
        return result
    positions = sorted(binding)
    centers = np.array(
        [detections[binding[p]].screen_quad.mean(axis=0) for p in positions], np.float32
    )
    target = np.array([[p % 3, p // 3] for p in positions], np.float32)
    if not np.isfinite(centers).all():
        return result
    matrix, _ = cv2.findHomography(centers, target, 0)
    if matrix is None or not np.isfinite(matrix).all():
        return result
    areas = {}
    for position in positions:
        nodes = detections[binding[position]].nodes
        if nodes is None:
            continue
        rectified = transform_points(
            np.asarray(nodes)[CORNERS], np.asarray(matrix, dtype=np.float64)
        )
        area = abs(float(cv2.contourArea(rectified)))
        if area > 0 and math.isfinite(area):
            areas[position] = area
    for position, area in areas.items():
        adjacent = [
            value
            for p, value in areas.items()
            if p != position and abs(p % 3 - position % 3) + abs(p // 3 - position // 3) == 1
        ]
        if adjacent:
            result[position] = abs(math.log(area / float(np.median(adjacent))))
    return result


def features(
    detection: BoardDetection,
    *,
    width: int,
    height: int,
    real_input_support: np.ndarray | None,
    game_log_aspect_reference: float | None,
    neighbor_deviation: float | None,
    neighbor_applicable: bool,
    primary: BoardDetection | None = None,
    rescue_required: bool = False,
    rescue_completed: bool = False,
    available_source_support: np.ndarray | None = None,
) -> FeatureVector:
    values: dict[str, float | None] = dict.fromkeys(AXES)
    reasons = set(detection.reasons) & {
        "NEURAL_GRID_FIT_FAILED",
        "NEURAL_GRID_FIT_OUTLIERS",
        "NEURAL_GRID_SCREEN_QUAD_INVALID",
    }
    not_applicable = []
    if not neighbor_applicable:
        not_applicable.append("neighborDeviation")
    else:
        values["neighborDeviation"] = neighbor_deviation
    if not rescue_required and not rescue_completed:
        not_applicable.append("rescueDisagreement")
    elif not rescue_completed or primary is None or primary.nodes is None:
        reasons.add("COMPLETENESS_RESCUE_REQUIRED")
    for axis, raw in (("peak", detection.node_peak), ("visibility", detection.visibility)):
        if raw is not None and np.asarray(raw).size == 24 and np.isfinite(raw).all():
            values[axis] = float(np.min(raw))
    nodes = detection.nodes
    if nodes is None or np.asarray(nodes).shape != (24, 2) or not np.isfinite(nodes).all():
        reasons.add("COMPLETENESS_NODES_REQUIRED")
    else:
        if (
            detection.raw_nodes is None
            or np.asarray(detection.raw_nodes).shape != (24, 2)
            or not np.isfinite(detection.raw_nodes).all()
        ):
            reasons.add("COMPLETENESS_RAW_NODES_REQUIRED")
        if detection.fit_inliers != 24:
            reasons.add("NEURAL_GRID_FIT_OUTLIERS")
        diagonal = max(float(np.linalg.norm(nodes[23] - nodes[0])), 1e-12)
        quad = np.asarray(detection.screen_quad)
        if quad.shape == (4, 2) and np.isfinite(quad).all():
            values["detectorIou"] = quad_iou(quad, nodes[CORNERS])
            values["detectorCornerError"] = float(
                np.linalg.norm(quad - nodes[CORNERS], axis=1).max() / diagonal
            )
        if detection.fit_residual is not None and math.isfinite(detection.fit_residual):
            values["fitResidual"] = detection.fit_residual
        aspect = log_aspect(nodes)
        if (
            aspect is not None
            and game_log_aspect_reference is not None
            and math.isfinite(game_log_aspect_reference)
        ):
            values["gameAspectDeviation"] = abs(aspect - game_log_aspect_reference)
        if (
            rescue_completed
            and primary is not None
            and primary.nodes is not None
            and np.asarray(primary.nodes).shape == (24, 2)
            and np.isfinite(primary.nodes).all()
        ):
            values["rescueDisagreement"] = float(
                np.linalg.norm(primary.nodes - nodes, axis=1).max() / diagonal
            )
        source = np.array([[0, 0], [width, 0], [width, height], [0, height]])
        supports = [source, real_input_support]
        if available_source_support is not None:
            supports.append(available_source_support)
        for support in supports:
            missing = None if support is None else missing_cell_area(nodes, support, width, height)
            if missing is None:
                reasons.add("COMPLETENESS_PIXEL_SUPPORT_REQUIRED")
            elif missing > COVERAGE_EPSILON:
                reasons.add("COMPLETENESS_PIXELS_MISSING")
    return FeatureVector(
        values=values, notApplicable=tuple(not_applicable), hardReasons=tuple(sorted(reasons))
    )
