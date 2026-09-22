"""Shared, deterministic frame-and-grid proposal core for shape geometry v2.

This module is deliberately independent from jobs, storage, game profiles, and
legacy geometry.  It produces a proposal for a later local verifier; it never
accepts an import by itself.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, cast

import cv2
import numpy as np
from numpy.typing import NDArray

SHAPE_GEOMETRY_V2_CORE_VERSION: Final = "shape-frame-geometry-v2-core-v2.1"
_PAGE_ROWS: Final = 3
_PAGE_COLUMNS: Final = 3
_CELL_ROWS: Final = 3
_CELL_COLUMNS: Final = 5
_POINT = tuple[float, float]
_QUAD = tuple[_POINT, _POINT, _POINT, _POINT]


class ShapeGeometryV2Error(ValueError):
    """Stable fatal error for an invalid core input or configuration."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ShapeGeometryV2Status(StrEnum):
    PROPOSAL = "proposal"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"


class ShapeGeometryV2ReasonCode(StrEnum):
    FRAME_EVIDENCE_INSUFFICIENT = "frame_evidence_insufficient"
    PAGE_INCOMPLETE = "page_incomplete"
    GRID_EVIDENCE_INSUFFICIENT = "grid_evidence_insufficient"


@dataclass(frozen=True, slots=True)
class ShapeGeometryV2Config:
    """Non-production structural limits for the shared framed-page family."""

    canonical_width: int = 900
    canonical_height: int = 600
    minimum_input_edge: int = 96
    minimum_frame_area_fraction: float = 0.12
    minimum_frame_edge_contrast: float = 0.08
    minimum_complete_margin_fraction: float = 0.018
    minimum_grid_support: float = 0.72
    minimum_board_grid_support: float = 0.90
    minimum_grid_line_contrast: float = 0.055
    maximum_frame_candidates: int = 32
    minimum_board_frame_area_fraction: float = 0.006
    maximum_board_frame_area_fraction: float = 0.18
    minimum_board_frame_edge_contrast: float = 0.035

    def __post_init__(self) -> None:
        if (
            self.canonical_width < 300
            or self.canonical_height < 200
            or self.minimum_input_edge < 32
            or not 0.0 < self.minimum_frame_area_fraction < 1.0
            or not 0.0 < self.minimum_frame_edge_contrast < 1.0
            or not 0.0 < self.minimum_complete_margin_fraction < 0.25
            or not 0.0 < self.minimum_grid_support <= 1.0
            or not 0.0 < self.minimum_board_grid_support <= 1.0
            or not 0.0 < self.minimum_grid_line_contrast < 1.0
            or not 1 <= self.maximum_frame_candidates <= 256
            or not 0.0 < self.minimum_board_frame_area_fraction < 1.0
            or not (
                self.minimum_board_frame_area_fraction
                < self.maximum_board_frame_area_fraction
                < 1.0
            )
            or not 0.0 < self.minimum_board_frame_edge_contrast < 1.0
        ):
            raise ShapeGeometryV2Error(
                "SHAPE_GEOMETRY_V2_CONFIG_INVALID",
                "Shape geometry v2 configuration is outside structural bounds.",
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "canonicalHeight": self.canonical_height,
            "canonicalWidth": self.canonical_width,
            "maximumFrameCandidates": self.maximum_frame_candidates,
            "minimumCompleteMarginFraction": _round(self.minimum_complete_margin_fraction),
            "minimumFrameAreaFraction": _round(self.minimum_frame_area_fraction),
            "minimumFrameEdgeContrast": _round(self.minimum_frame_edge_contrast),
            "minimumBoardGridSupport": _round(self.minimum_board_grid_support),
            "minimumGridLineContrast": _round(self.minimum_grid_line_contrast),
            "minimumGridSupport": _round(self.minimum_grid_support),
            "minimumInputEdge": self.minimum_input_edge,
            "minimumBoardFrameAreaFraction": _round(self.minimum_board_frame_area_fraction),
            "maximumBoardFrameAreaFraction": _round(self.maximum_board_frame_area_fraction),
            "minimumBoardFrameEdgeContrast": _round(self.minimum_board_frame_edge_contrast),
        }


@dataclass(frozen=True, slots=True)
class ShapeGeometryV2ColorEvidence:
    """Optional chroma evidence that can only decorate a structural proposal."""

    chromatic_edge_fraction: float
    mean_saturation: float

    def as_dict(self) -> dict[str, float]:
        return {
            "chromaticEdgeFraction": _round(self.chromatic_edge_fraction),
            "meanSaturation": _round(self.mean_saturation),
        }


@dataclass(frozen=True, slots=True)
class ShapeGeometryV2GridEvidence:
    horizontal_support: float
    vertical_support: float
    board_support: tuple[float, ...]
    expected_horizontal_lines: int
    expected_vertical_lines: int

    @property
    def support(self) -> float:
        return min(self.horizontal_support, self.vertical_support)

    @property
    def minimum_board_support(self) -> float:
        return min(self.board_support, default=0.0)

    def as_dict(self) -> dict[str, object]:
        return {
            "boardSupport": [_round(value) for value in self.board_support],
            "expectedHorizontalLines": self.expected_horizontal_lines,
            "expectedVerticalLines": self.expected_vertical_lines,
            "horizontalSupport": _round(self.horizontal_support),
            "minimumBoardSupport": _round(self.minimum_board_support),
            "support": _round(self.support),
            "verticalSupport": _round(self.vertical_support),
        }


@dataclass(frozen=True, slots=True)
class ShapeGeometryV2Board:
    position_index: int
    board_quad: _QUAD
    cell_quads: tuple[_QUAD, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "boardQuad": _quad_dict(self.board_quad),
            "cellQuads": [_quad_dict(cell) for cell in self.cell_quads],
            "positionIndex": self.position_index,
        }


@dataclass(frozen=True, slots=True)
class ShapeGeometryV2Result:
    status: ShapeGeometryV2Status
    reason_codes: tuple[ShapeGeometryV2ReasonCode, ...]
    input_width: int
    input_height: int
    frame_candidate_count: int
    frame_quad: _QUAD | None
    source_to_canonical_homography: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ] | None
    structural_score: float | None
    color_evidence: ShapeGeometryV2ColorEvidence | None
    grid_evidence: ShapeGeometryV2GridEvidence | None
    boards: tuple[ShapeGeometryV2Board, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "boards": [board.as_dict() for board in self.boards],
            "colorEvidence": (
                None if self.color_evidence is None else self.color_evidence.as_dict()
            ),
            "coreVersion": SHAPE_GEOMETRY_V2_CORE_VERSION,
            "frameCandidateCount": self.frame_candidate_count,
            "frameQuad": None if self.frame_quad is None else _quad_dict(self.frame_quad),
            "gridEvidence": (
                None if self.grid_evidence is None else self.grid_evidence.as_dict()
            ),
            "inputHeight": self.input_height,
            "inputWidth": self.input_width,
            "reasonCodes": [reason.value for reason in self.reason_codes],
            "sourceToCanonicalHomography": (
                None
                if self.source_to_canonical_homography is None
                else [
                    [_round(value) for value in row]
                    for row in self.source_to_canonical_homography
                ]
            ),
            "status": self.status.value,
            "structuralScore": (
                None if self.structural_score is None else _round(self.structural_score)
            ),
        }


@dataclass(frozen=True, slots=True)
class _FrameCandidate:
    quad: _QUAD
    area_fraction: float
    edge_contrast: float
    shape_score: float

    @property
    def structural_score(self) -> float:
        return 0.50 * self.area_fraction + 0.35 * self.edge_contrast + 0.15 * self.shape_score

    def rank_key(self) -> tuple[float, float, float, tuple[float, ...]]:
        return (
            -_round(self.structural_score),
            -_round(self.area_fraction),
            -_round(self.edge_contrast),
            tuple(_round(value) for point in self.quad for value in point),
        )


def detect_shape_geometry_v2(
    rgb: NDArray[np.uint8],
    *,
    config: ShapeGeometryV2Config | None = None,
) -> ShapeGeometryV2Result:
    """Return a shared structural proposal or a safe manual-review result."""

    resolved_config = config or ShapeGeometryV2Config()
    _validate_rgb(rgb, resolved_config)
    height, width = rgb.shape[:2]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    candidates = _find_frame_candidates(gray, resolved_config)
    if not candidates:
        return ShapeGeometryV2Result(
            status=ShapeGeometryV2Status.NEEDS_MANUAL_REVIEW,
            reason_codes=(ShapeGeometryV2ReasonCode.FRAME_EVIDENCE_INSUFFICIENT,),
            input_width=width,
            input_height=height,
            frame_candidate_count=0,
            frame_quad=None,
            source_to_canonical_homography=None,
            structural_score=None,
            color_evidence=None,
            grid_evidence=None,
            boards=(),
        )

    selected = candidates[0]
    homography = _source_to_canonical_homography(selected.quad, resolved_config)
    rectified = cv2.warpPerspective(
        rgb,
        np.asarray(homography, dtype=np.float64),
        (resolved_config.canonical_width, resolved_config.canonical_height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
    )
    color_evidence = _color_evidence(rectified)
    complete = _is_complete_frame(selected.quad, width, height, resolved_config)
    grid_evidence = _grid_evidence(rectified, resolved_config)
    reasons: list[ShapeGeometryV2ReasonCode] = []
    if not complete:
        reasons.append(ShapeGeometryV2ReasonCode.PAGE_INCOMPLETE)
    if (
        grid_evidence.support < resolved_config.minimum_grid_support
        or grid_evidence.minimum_board_support < resolved_config.minimum_board_grid_support
    ):
        reasons.append(ShapeGeometryV2ReasonCode.GRID_EVIDENCE_INSUFFICIENT)
    if reasons:
        return ShapeGeometryV2Result(
            status=ShapeGeometryV2Status.NEEDS_MANUAL_REVIEW,
            reason_codes=tuple(reasons),
            input_width=width,
            input_height=height,
            frame_candidate_count=len(candidates),
            frame_quad=selected.quad,
            source_to_canonical_homography=homography,
            structural_score=selected.structural_score,
            color_evidence=color_evidence,
            grid_evidence=grid_evidence,
            boards=(),
        )
    return ShapeGeometryV2Result(
        status=ShapeGeometryV2Status.PROPOSAL,
        reason_codes=(),
        input_width=width,
        input_height=height,
        frame_candidate_count=len(candidates),
        frame_quad=selected.quad,
        source_to_canonical_homography=homography,
        structural_score=selected.structural_score,
        color_evidence=color_evidence,
        grid_evidence=grid_evidence,
        boards=_derive_boards(homography, resolved_config),
    )


def _validate_rgb(rgb: NDArray[np.uint8], config: ShapeGeometryV2Config) -> None:
    if (
        not isinstance(rgb, np.ndarray)
        or rgb.dtype != np.uint8
        or rgb.ndim != 3
        or rgb.shape[2] != 3
    ):
        raise ShapeGeometryV2Error(
            "SHAPE_GEOMETRY_V2_INPUT_INVALID",
            "Shape geometry v2 requires an RGB uint8 array.",
        )
    height, width = rgb.shape[:2]
    if min(height, width) < config.minimum_input_edge:
        raise ShapeGeometryV2Error(
            "SHAPE_GEOMETRY_V2_INPUT_TOO_SMALL",
            "Shape geometry v2 input is smaller than the configured structural minimum.",
        )


def _find_frame_candidates(
    gray: NDArray[np.uint8],
    config: ShapeGeometryV2Config,
) -> tuple[_FrameCandidate, ...]:
    height, width = gray.shape
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 120, apertureSize=3)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[_FrameCandidate] = []
    image_area = float(height * width)
    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue
        approximation = cv2.approxPolyDP(contour, 0.018 * perimeter, True)
        if len(approximation) != 4 or not cv2.isContourConvex(approximation):
            continue
        quad = _ordered_quad(approximation.reshape((4, 2)))
        if quad is None:
            continue
        area_fraction = _polygon_area(quad) / image_area
        if area_fraction < config.minimum_frame_area_fraction or area_fraction > 0.98:
            continue
        shape_score = _quad_shape_score(quad)
        if shape_score <= 0.0:
            continue
        edge_contrast = _quad_edge_contrast(gray, quad)
        if edge_contrast < config.minimum_frame_edge_contrast:
            continue
        candidates.append(
            _FrameCandidate(
                quad=quad,
                area_fraction=area_fraction,
                edge_contrast=edge_contrast,
                shape_score=shape_score,
            )
        )
    return tuple(_deduplicate_candidates(candidates)[: config.maximum_frame_candidates])


def _ordered_quad(points: NDArray[np.int32] | NDArray[np.float32]) -> _QUAD | None:
    values = np.asarray(points, dtype=np.float64)
    sums = values[:, 0] + values[:, 1]
    differences = values[:, 0] - values[:, 1]
    top_left = int(np.argmin(sums))
    bottom_right = int(np.argmax(sums))
    top_right = int(np.argmax(differences))
    bottom_left = int(np.argmin(differences))
    indexes = (top_left, top_right, bottom_right, bottom_left)
    if len(set(indexes)) != 4:
        return None
    cycle = [values[index] for index in indexes]
    if _cross(cycle[0], cycle[1], cycle[2]) < 0:
        cycle = [cycle[0], cycle[3], cycle[2], cycle[1]]
    return cast(_QUAD, tuple((float(point[0]), float(point[1])) for point in cycle))


def _cross(
    first: NDArray[np.float64],
    second: NDArray[np.float64],
    third: NDArray[np.float64],
) -> float:
    return float(
        (second[0] - first[0]) * (third[1] - first[1])
        - (second[1] - first[1]) * (third[0] - first[0])
    )


def _polygon_area(quad: _QUAD) -> float:
    return abs(
        sum(
            quad[index][0] * quad[(index + 1) % 4][1]
            - quad[(index + 1) % 4][0] * quad[index][1]
            for index in range(4)
        )
    ) / 2.0


def _quad_shape_score(quad: _QUAD) -> float:
    edges = [
        math.dist(quad[index], quad[(index + 1) % 4])
        for index in range(4)
    ]
    if min(edges) <= 1.0:
        return 0.0
    opposite_balance = min(edges[0], edges[2]) / max(edges[0], edges[2])
    opposite_balance *= min(edges[1], edges[3]) / max(edges[1], edges[3])
    diagonals = (math.dist(quad[0], quad[2]), math.dist(quad[1], quad[3]))
    diagonal_balance = min(diagonals) / max(diagonals)
    return opposite_balance * diagonal_balance


def _quad_edge_contrast(gray: NDArray[np.uint8], quad: _QUAD) -> float:
    edge_mask = np.zeros(gray.shape, dtype=np.uint8)
    contour = np.asarray(quad, dtype=np.int32).reshape((-1, 1, 2))
    thickness = max(2, min(gray.shape) // 180)
    cv2.polylines(edge_mask, [contour], True, 255, thickness=thickness, lineType=cv2.LINE_AA)
    gradient_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gradient_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(gradient_x, gradient_y)
    samples = magnitude[edge_mask > 0]
    return 0.0 if samples.size == 0 else float(np.mean(samples) / 255.0)


def _deduplicate_candidates(candidates: list[_FrameCandidate]) -> list[_FrameCandidate]:
    selected: list[_FrameCandidate] = []
    for candidate in sorted(candidates, key=lambda value: value.rank_key()):
        if any(_quad_overlap(candidate.quad, prior.quad) >= 0.94 for prior in selected):
            continue
        selected.append(candidate)
    return selected


def _quad_overlap(first: _QUAD, second: _QUAD) -> float:
    first_polygon = np.asarray(first, dtype=np.float32)
    second_polygon = np.asarray(second, dtype=np.float32)
    first_area = abs(float(cv2.contourArea(first_polygon)))
    second_area = abs(float(cv2.contourArea(second_polygon)))
    if min(first_area, second_area) <= 0.0:
        return 0.0
    intersection_area, _ = cv2.intersectConvexConvex(first_polygon, second_polygon)
    return float(intersection_area / min(first_area, second_area))


def _source_to_canonical_homography(
    quad: _QUAD,
    config: ShapeGeometryV2Config,
) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]:
    source = np.asarray(quad, dtype=np.float32)
    target = np.asarray(
        (
            (0.0, 0.0),
            (float(config.canonical_width - 1), 0.0),
            (float(config.canonical_width - 1), float(config.canonical_height - 1)),
            (0.0, float(config.canonical_height - 1)),
        ),
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(source, target)
    if not np.isfinite(matrix).all() or abs(float(np.linalg.det(matrix))) < 1e-12:
        raise ShapeGeometryV2Error(
            "SHAPE_GEOMETRY_V2_HOMOGRAPHY_INVALID",
            "Frame corners do not define a usable homography.",
        )
    return cast(
        tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]],
        tuple(tuple(float(value) for value in row) for row in matrix),
    )


def _is_complete_frame(
    quad: _QUAD,
    width: int,
    height: int,
    config: ShapeGeometryV2Config,
) -> bool:
    required_margin = min(width, height) * config.minimum_complete_margin_fraction
    return all(
        min(x, y, float(width - 1) - x, float(height - 1) - y) >= required_margin
        for x, y in quad
    )


def _color_evidence(rectified_rgb: NDArray[np.uint8]) -> ShapeGeometryV2ColorEvidence:
    height, width = rectified_rgb.shape[:2]
    hsv = cv2.cvtColor(rectified_rgb, cv2.COLOR_RGB2HSV)
    thickness = max(2, min(width, height) // 100)
    edge_mask = np.zeros((height, width), dtype=np.uint8)
    cv2.rectangle(edge_mask, (0, 0), (width - 1, height - 1), 255, thickness=thickness)
    saturation = hsv[:, :, 1][edge_mask > 0]
    return ShapeGeometryV2ColorEvidence(
        chromatic_edge_fraction=float(np.mean(saturation >= 48)),
        mean_saturation=float(np.mean(saturation) / 255.0),
    )


def _grid_evidence(
    rectified_rgb: NDArray[np.uint8],
    config: ShapeGeometryV2Config,
) -> ShapeGeometryV2GridEvidence:
    gray = cv2.cvtColor(rectified_rgb, cv2.COLOR_RGB2GRAY)
    horizontal_gradient = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)) / 255.0
    vertical_gradient = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)) / 255.0
    vertical_scores: list[float] = []
    horizontal_scores: list[float] = []
    board_support: list[float] = []
    width_extent = config.canonical_width - 1
    height_extent = config.canonical_height - 1
    for board_row in range(_PAGE_ROWS):
        for board_column in range(_PAGE_COLUMNS):
            left = board_column * width_extent / _PAGE_COLUMNS
            right = (board_column + 1) * width_extent / _PAGE_COLUMNS
            top = board_row * height_extent / _PAGE_ROWS
            bottom = (board_row + 1) * height_extent / _PAGE_ROWS
            board_vertical = [
                _vertical_line_support(
                    vertical_gradient,
                    round(left + cell_column * (right - left) / _CELL_COLUMNS),
                    round(top),
                    round(bottom),
                )
                for cell_column in range(1, _CELL_COLUMNS)
            ]
            board_horizontal = [
                _horizontal_line_support(
                    horizontal_gradient,
                    round(top + cell_row * (bottom - top) / _CELL_ROWS),
                    round(left),
                    round(right),
                )
                for cell_row in range(1, _CELL_ROWS)
            ]
            vertical_scores.extend(board_vertical)
            horizontal_scores.extend(board_horizontal)
            board_support.append(
                min(
                    _supported_fraction(board_vertical, config.minimum_grid_line_contrast),
                    _supported_fraction(board_horizontal, config.minimum_grid_line_contrast),
                )
            )
    return ShapeGeometryV2GridEvidence(
        horizontal_support=_supported_fraction(
            horizontal_scores, config.minimum_grid_line_contrast
        ),
        vertical_support=_supported_fraction(
            vertical_scores, config.minimum_grid_line_contrast
        ),
        board_support=tuple(board_support),
        expected_horizontal_lines=len(horizontal_scores),
        expected_vertical_lines=len(vertical_scores),
    )


def _supported_fraction(scores: list[float], minimum_contrast: float) -> float:
    return 0.0 if not scores else float(np.mean(np.asarray(scores) >= minimum_contrast))


def _vertical_line_support(
    gradient: NDArray[np.float32],
    x: int,
    top: int,
    bottom: int,
) -> float:
    margin = max(2, (bottom - top) // 30)
    window = gradient[top + margin : bottom - margin, max(0, x - 2) : x + 3]
    return 0.0 if window.size == 0 else float(np.quantile(window, 0.75))


def _horizontal_line_support(
    gradient: NDArray[np.float32],
    y: int,
    left: int,
    right: int,
) -> float:
    margin = max(2, (right - left) // 30)
    window = gradient[max(0, y - 2) : y + 3, left + margin : right - margin]
    return 0.0 if window.size == 0 else float(np.quantile(window, 0.75))


def _derive_boards(
    source_to_canonical: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ],
    config: ShapeGeometryV2Config,
) -> tuple[ShapeGeometryV2Board, ...]:
    canonical_to_source = np.linalg.inv(np.asarray(source_to_canonical, dtype=np.float64))
    boards: list[ShapeGeometryV2Board] = []
    width_extent = config.canonical_width - 1
    height_extent = config.canonical_height - 1
    for board_row in range(_PAGE_ROWS):
        for board_column in range(_PAGE_COLUMNS):
            board_quad = _project_quad(
                _canonical_rect(
                    board_column * width_extent / _PAGE_COLUMNS,
                    board_row * height_extent / _PAGE_ROWS,
                    (board_column + 1) * width_extent / _PAGE_COLUMNS,
                    (board_row + 1) * height_extent / _PAGE_ROWS,
                ),
                canonical_to_source,
            )
            cells = tuple(
                _project_quad(
                    _canonical_rect(
                        (board_column + cell_column / _CELL_COLUMNS)
                        * width_extent
                        / _PAGE_COLUMNS,
                        (board_row + cell_row / _CELL_ROWS) * height_extent / _PAGE_ROWS,
                        (board_column + (cell_column + 1) / _CELL_COLUMNS)
                        * width_extent
                        / _PAGE_COLUMNS,
                        (board_row + (cell_row + 1) / _CELL_ROWS)
                        * height_extent
                        / _PAGE_ROWS,
                    ),
                    canonical_to_source,
                )
                for cell_row in range(_CELL_ROWS)
                for cell_column in range(_CELL_COLUMNS)
            )
            boards.append(
                ShapeGeometryV2Board(
                    position_index=board_row * _PAGE_COLUMNS + board_column,
                    board_quad=board_quad,
                    cell_quads=cells,
                )
            )
    return tuple(boards)


def _canonical_rect(left: float, top: float, right: float, bottom: float) -> _QUAD:
    return ((left, top), (right, top), (right, bottom), (left, bottom))


def _project_quad(quad: _QUAD, transform: NDArray[np.float64]) -> _QUAD:
    source = cv2.perspectiveTransform(
        np.asarray(quad, dtype=np.float64).reshape((-1, 1, 2)),
        transform,
    ).reshape((-1, 2))
    if not np.isfinite(source).all():
        raise ShapeGeometryV2Error(
            "SHAPE_GEOMETRY_V2_HOMOGRAPHY_INVALID",
            "Inverse homography produced non-finite source coordinates.",
        )
    return cast(_QUAD, tuple((float(point[0]), float(point[1])) for point in source))


def _quad_dict(quad: _QUAD) -> list[dict[str, float]]:
    return [{"x": _round(x), "y": _round(y)} for x, y in quad]


def _round(value: float) -> float:
    return round(float(value), 8)


__all__ = [
    "SHAPE_GEOMETRY_V2_CORE_VERSION",
    "ShapeGeometryV2Board",
    "ShapeGeometryV2ColorEvidence",
    "ShapeGeometryV2Config",
    "ShapeGeometryV2Error",
    "ShapeGeometryV2GridEvidence",
    "ShapeGeometryV2ReasonCode",
    "ShapeGeometryV2Result",
    "ShapeGeometryV2Status",
    "detect_shape_geometry_v2",
]
