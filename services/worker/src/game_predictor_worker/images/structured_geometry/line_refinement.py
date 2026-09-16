"""Independent local 6 × 4 line refinement for one photographed 5 × 3 board.

The initial quad is rectified only in memory to make line families easier to
observe.  The returned homography and quad are projected back to canonical
source pixels and are never constrained to be rectangular in the photograph.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, cast

import cv2
import numpy as np
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_geometry_v2 import (
    SourcePoint,
    SourceQuad,
    canonical_json_bytes,
)
from numpy.typing import NDArray

from .confidence import (
    DEFAULT_STRUCTURED_GEOMETRY_VALIDATION_THRESHOLDS,
    BoardGeometryEvidence,
    BoardGeometryReasonCode,
    GeometryConfidenceComponents,
    StructuredGeometryValidationThresholds,
)

STRUCTURED_BOARD_LINE_REFINEMENT_VERSION: Final = "structured-opencv-board-line-refinement-v1"
STRUCTURED_BOARD_LINE_CONFIG_VERSION: Final = "structured-board-line-thresholds-v1"
_ANALYSIS_SCALE: Final = 0.5
_SUPPORTED_ROWS: Final = 3
_SUPPORTED_COLUMNS: Final = 5

type Matrix3x3 = tuple[
    tuple[float, float, float],
    tuple[float, float, float],
    tuple[float, float, float],
]


class StructuredBoardLineRefinementError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class GridLineOrientation(StrEnum):
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"


@dataclass(frozen=True, slots=True)
class StructuredBoardLineThresholds:
    canonical_cell_size: int = 64
    analysis_margin: int = 28
    maximum_axis_angle_degrees: float = 18.0
    maximum_expected_line_distance_fraction: float = 0.24
    minimum_segment_axis_fraction: float = 0.10
    minimum_line_axis_coverage: float = 0.28
    minimum_outer_border_axis_coverage: float = 0.34
    line_cluster_distance_px: float = 5.0
    line_cluster_angle_degrees: float = 8.0
    ransac_half_scale_reprojection_threshold: float = 2.5
    maximum_initial_quad_corner_shift_fraction: float = 0.42
    minimum_initial_quad_iou: float = 0.48
    cell_padding_fraction: float = 0.08

    def __post_init__(self) -> None:
        fractions = (
            self.maximum_expected_line_distance_fraction,
            self.minimum_segment_axis_fraction,
            self.minimum_line_axis_coverage,
            self.minimum_outer_border_axis_coverage,
            self.maximum_initial_quad_corner_shift_fraction,
            self.minimum_initial_quad_iou,
            self.cell_padding_fraction,
        )
        if (
            self.canonical_cell_size < 16
            or self.analysis_margin < 4
            or not 0 < self.maximum_axis_angle_degrees < 45
            or any(not math.isfinite(value) or not 0 <= value <= 1 for value in fractions)
            or not math.isfinite(self.line_cluster_distance_px)
            or self.line_cluster_distance_px <= 0
            or not 0 < self.line_cluster_angle_degrees < 45
            or not math.isfinite(self.ransac_half_scale_reprojection_threshold)
            or self.ransac_half_scale_reprojection_threshold <= 0
            or self.cell_padding_fraction >= 0.5
        ):
            raise StructuredBoardLineRefinementError(
                "IMAGE_STRUCTURED_BOARD_LINE_CONFIG_INVALID",
                "Structured board-line refinement thresholds are invalid.",
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "analysisMargin": self.analysis_margin,
            "analysisScale": _ANALYSIS_SCALE,
            "canonicalCellSize": self.canonical_cell_size,
            "cellPaddingFraction": self.cell_padding_fraction,
            "configVersion": STRUCTURED_BOARD_LINE_CONFIG_VERSION,
            "lineClusterAngleDegrees": self.line_cluster_angle_degrees,
            "lineClusterDistancePx": self.line_cluster_distance_px,
            "maximumAxisAngleDegrees": self.maximum_axis_angle_degrees,
            "maximumExpectedLineDistanceFraction": (self.maximum_expected_line_distance_fraction),
            "maximumInitialQuadCornerShiftFraction": (
                self.maximum_initial_quad_corner_shift_fraction
            ),
            "minimumInitialQuadIou": self.minimum_initial_quad_iou,
            "minimumLineAxisCoverage": self.minimum_line_axis_coverage,
            "minimumOuterBorderAxisCoverage": self.minimum_outer_border_axis_coverage,
            "minimumSegmentAxisFraction": self.minimum_segment_axis_fraction,
            "ransacHalfScaleReprojectionThreshold": (self.ransac_half_scale_reprojection_threshold),
        }


DEFAULT_STRUCTURED_BOARD_LINE_THRESHOLDS = StructuredBoardLineThresholds()


@dataclass(frozen=True, slots=True)
class RefinedGridLine:
    orientation: GridLineOrientation
    index: int
    source_start: SourcePoint
    source_end: SourcePoint
    support_score: float
    inferred: bool
    border_evidence: bool
    segment_count: int

    def to_payload(self) -> dict[str, object]:
        return {
            "borderEvidence": self.border_evidence,
            "index": self.index,
            "inferred": self.inferred,
            "orientation": self.orientation.value,
            "segmentCount": self.segment_count,
            "sourceEnd": self.source_end.to_dict(),
            "sourceStart": self.source_start.to_dict(),
            "supportScore": round(self.support_score, 8),
        }


@dataclass(frozen=True, slots=True)
class BoardLineRefinementResult:
    initial_quad: SourceQuad
    final_quad: SourceQuad | None
    ideal_to_source_homography: Matrix3x3 | None
    evidence: BoardGeometryEvidence
    confidence_components: GeometryConfidenceComponents
    lines: tuple[RefinedGridLine, ...]
    intrinsic_reason_codes: tuple[BoardGeometryReasonCode, ...]
    diagnostics: tuple[tuple[str, float | int | str], ...]
    version: str = STRUCTURED_BOARD_LINE_REFINEMENT_VERSION

    def to_payload(self) -> dict[str, object]:
        return {
            "confidenceComponents": self.confidence_components.to_payload(),
            "diagnostics": dict(self.diagnostics),
            "evidence": self.evidence.to_payload(),
            "finalQuad": None if self.final_quad is None else self.final_quad.to_dict(),
            "idealToSourceHomography": (
                None
                if self.ideal_to_source_homography is None
                else [list(row) for row in self.ideal_to_source_homography]
            ),
            "initialQuad": self.initial_quad.to_dict(),
            "intrinsicReasonCodes": [value.value for value in self.intrinsic_reason_codes],
            "lines": [line.to_payload() for line in self.lines],
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class _Segment:
    start: NDArray[np.float64]
    end: NDArray[np.float64]
    orientation: GridLineOrientation
    coordinate: float
    angle_degrees: float
    length: float


@dataclass(frozen=True, slots=True)
class _LineObservation:
    orientation: GridLineOrientation
    index: int
    line: NDArray[np.float64]
    coverage: float
    support_score: float
    segment_count: int
    border_evidence: bool


@dataclass(frozen=True, slots=True)
class _HomographyFit:
    ideal_to_patch: NDArray[np.float64]
    ideal_to_source: NDArray[np.float64]
    final_quad: SourceQuad
    p95_half_scale_reprojection_error: float
    supported_intersection_count: int
    inlier_intersection_count: int
    source_support_complete: bool
    initialization_alignment_valid: bool


class BoardLineRefiner:
    """Refine one initial board ROI without borrowing geometry from neighbours."""

    version = STRUCTURED_BOARD_LINE_REFINEMENT_VERSION

    def __init__(
        self,
        *,
        thresholds: StructuredBoardLineThresholds = DEFAULT_STRUCTURED_BOARD_LINE_THRESHOLDS,
        validation_thresholds: StructuredGeometryValidationThresholds = (
            DEFAULT_STRUCTURED_GEOMETRY_VALIDATION_THRESHOLDS
        ),
    ) -> None:
        self.thresholds = thresholds
        self.validation_thresholds = validation_thresholds
        self.config_checksum_sha256 = hashlib.sha256(
            canonical_json_bytes(
                {
                    "lineRefinement": thresholds.to_payload(),
                    "validation": validation_thresholds.to_payload(),
                }
            )
        ).hexdigest()

    def refine(
        self,
        rgb: NDArray[np.uint8],
        *,
        initial_quad: SourceQuad,
        topology: BoardTopology,
        global_registration_score: float,
    ) -> BoardLineRefinementResult:
        _validate_rgb(rgb)
        if topology.rows != _SUPPORTED_ROWS or topology.columns != _SUPPORTED_COLUMNS:
            return self._failed(
                initial_quad,
                global_registration_score=global_registration_score,
                reason=BoardGeometryReasonCode.TOPOLOGY_UNSUPPORTED,
                diagnostic=("topologyCellCount", topology.cell_count),
            )
        try:
            patch, source_to_patch, patch_to_half, board_rect = _rectified_analysis_patch(
                rgb,
                initial_quad=initial_quad,
                thresholds=self.thresholds,
            )
        except (cv2.error, StructuredBoardLineRefinementError, ValueError):
            return self._failed(
                initial_quad,
                global_registration_score=global_registration_score,
                reason=BoardGeometryReasonCode.LOCAL_ROI_UNUSABLE,
            )

        observations, detected_segment_count = _detect_grid_lines(
            patch,
            board_rect=board_rect,
            thresholds=self.thresholds,
        )
        vertical = tuple(
            value for value in observations if value.orientation is GridLineOrientation.VERTICAL
        )
        horizontal = tuple(
            value for value in observations if value.orientation is GridLineOrientation.HORIZONTAL
        )
        spacing_score = _spacing_regularity_score(vertical, horizontal, board_rect=board_rect)
        fit = _fit_local_homography(
            vertical,
            horizontal,
            patch_to_half=patch_to_half,
            initial_quad=initial_quad,
            source_width=rgb.shape[1],
            source_height=rgb.shape[0],
            topology=topology,
            thresholds=self.thresholds,
        )
        inferred_vertical, inferred_horizontal = _infer_single_internal_line(
            vertical,
            horizontal,
            spacing_regular=(
                spacing_score >= self.validation_thresholds.minimum_spacing_regularity_for_automatic
            ),
            initialization_alignment_valid=(fit is not None and fit.initialization_alignment_valid),
        )
        observed_vertical = tuple(value.index for value in vertical)
        observed_horizontal = tuple(value.index for value in horizontal)
        outer = _external_boundary_support_count(vertical, horizontal)
        border_score = _border_evidence_score(vertical, horizontal)
        supported_intersections = len(vertical) * len(horizontal)
        evidence = BoardGeometryEvidence(
            observed_vertical_line_indexes=observed_vertical,
            observed_horizontal_line_indexes=observed_horizontal,
            inferred_vertical_line_indexes=inferred_vertical,
            inferred_horizontal_line_indexes=inferred_horizontal,
            external_boundaries_supported=outer,
            supported_intersection_count=supported_intersections,
            inlier_intersection_count=0 if fit is None else fit.inlier_intersection_count,
            half_scale_p95_reprojection_error=(
                None if fit is None else fit.p95_half_scale_reprojection_error
            ),
            homography_available=fit is not None,
            padded_cell_source_support_complete=(
                False if fit is None else fit.source_support_complete
            ),
            initialization_alignment_valid=(
                False if fit is None else fit.initialization_alignment_valid
            ),
        )
        line_score = _line_coverage_score(vertical, horizontal)
        intersection_score = min(1.0, supported_intersections / 24.0)
        reprojection_score = _reprojection_score(
            None if fit is None else fit.p95_half_scale_reprojection_error,
            maximum=self.validation_thresholds.maximum_half_scale_p95_reprojection_error,
        )
        components = GeometryConfidenceComponents(
            global_registration_score=_unit(global_registration_score),
            line_coverage_score=line_score,
            intersection_coverage_score=intersection_score,
            spacing_regularity_score=spacing_score,
            reprojection_score=reprojection_score,
            border_evidence_score=border_score,
            slot_order_score=1.0,
            source_support_score=(1.0 if fit is not None and fit.source_support_complete else 0.0),
        )
        output_lines = (
            ()
            if fit is None
            else _output_grid_lines(
                fit.ideal_to_source,
                vertical=vertical,
                horizontal=horizontal,
                inferred_vertical=inferred_vertical,
                inferred_horizontal=inferred_horizontal,
            )
        )
        return BoardLineRefinementResult(
            initial_quad=initial_quad,
            final_quad=None if fit is None else fit.final_quad,
            ideal_to_source_homography=(
                None if fit is None else _matrix_payload(fit.ideal_to_source)
            ),
            evidence=evidence,
            confidence_components=components,
            lines=output_lines,
            intrinsic_reason_codes=(),
            diagnostics=_diagnostics(
                analysisPatchHeight=patch.shape[0],
                analysisPatchWidth=patch.shape[1],
                detectedLineSegmentCount=detected_segment_count,
                horizontalLineCount=len(horizontal),
                sourceToPatchDeterminant=float(np.linalg.det(source_to_patch)),
                verticalLineCount=len(vertical),
            ),
        )

    @staticmethod
    def _failed(
        initial_quad: SourceQuad,
        *,
        global_registration_score: float,
        reason: BoardGeometryReasonCode,
        diagnostic: tuple[str, float | int | str] | None = None,
    ) -> BoardLineRefinementResult:
        return BoardLineRefinementResult(
            initial_quad=initial_quad,
            final_quad=None,
            ideal_to_source_homography=None,
            evidence=BoardGeometryEvidence.empty(),
            confidence_components=GeometryConfidenceComponents(
                global_registration_score=_unit(global_registration_score),
                line_coverage_score=0.0,
                intersection_coverage_score=0.0,
                spacing_regularity_score=0.0,
                reprojection_score=0.0,
                border_evidence_score=0.0,
                slot_order_score=0.0,
                source_support_score=0.0,
            ),
            lines=(),
            intrinsic_reason_codes=(reason,),
            diagnostics=() if diagnostic is None else (diagnostic,),
        )


def _validate_rgb(rgb: NDArray[np.uint8]) -> None:
    if (
        not isinstance(rgb, np.ndarray)
        or rgb.dtype != np.uint8
        or rgb.ndim != 3
        or rgb.shape[2] != 3
    ):
        raise StructuredBoardLineRefinementError(
            "IMAGE_STRUCTURED_BOARD_SOURCE_INVALID",
            "Board-line refinement requires an RGB uint8 source.",
        )


def _rectified_analysis_patch(
    rgb: NDArray[np.uint8],
    *,
    initial_quad: SourceQuad,
    thresholds: StructuredBoardLineThresholds,
) -> tuple[
    NDArray[np.uint8],
    NDArray[np.float64],
    NDArray[np.float64],
    tuple[float, float, float, float],
]:
    half = cast(
        NDArray[np.uint8],
        cv2.resize(rgb, None, fx=_ANALYSIS_SCALE, fy=_ANALYSIS_SCALE, interpolation=cv2.INTER_AREA),
    )
    source = np.asarray(
        [[point.x * _ANALYSIS_SCALE, point.y * _ANALYSIS_SCALE] for point in initial_quad.corners],
        dtype=np.float32,
    )
    if not cv2.isContourConvex(source) or abs(cv2.contourArea(source)) < 24.0:
        raise StructuredBoardLineRefinementError(
            "IMAGE_STRUCTURED_BOARD_INITIAL_QUAD_INVALID",
            "The initial board quad is too small or non-convex.",
        )
    cell = thresholds.canonical_cell_size
    margin = thresholds.analysis_margin
    board_width = _SUPPORTED_COLUMNS * cell
    board_height = _SUPPORTED_ROWS * cell
    destination = np.asarray(
        [
            [margin, margin],
            [margin + board_width, margin],
            [margin + board_width, margin + board_height],
            [margin, margin + board_height],
        ],
        dtype=np.float32,
    )
    source_to_patch = cast(NDArray[np.float64], cv2.getPerspectiveTransform(source, destination))
    patch_to_half = cast(NDArray[np.float64], np.linalg.inv(source_to_patch))
    patch = cast(
        NDArray[np.uint8],
        cv2.warpPerspective(
            half,
            source_to_patch,
            (board_width + 2 * margin, board_height + 2 * margin),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0),
        ),
    )
    return (
        patch,
        source_to_patch,
        patch_to_half,
        (float(margin), float(margin), float(board_width), float(board_height)),
    )


def _detect_grid_lines(
    patch: NDArray[np.uint8],
    *,
    board_rect: tuple[float, float, float, float],
    thresholds: StructuredBoardLineThresholds,
) -> tuple[tuple[_LineObservation, ...], int]:
    gray = cast(NDArray[np.uint8], cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY))
    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(6, 6)).apply(gray)
    vertical_gradient = cast(
        NDArray[np.uint8],
        cv2.convertScaleAbs(cv2.Sobel(enhanced, cv2.CV_32F, 1, 0, ksize=3)),
    )
    horizontal_gradient = cast(
        NDArray[np.uint8],
        cv2.convertScaleAbs(cv2.Sobel(enhanced, cv2.CV_32F, 0, 1, ksize=3)),
    )
    detector = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
    segments = tuple(
        segment
        for channel in (enhanced, vertical_gradient, horizontal_gradient)
        for segment in _segments(
            cast(NDArray[np.float32] | None, detector.detect(channel)[0]),
            board_rect=board_rect,
            thresholds=thresholds,
        )
    )
    red = _red_mask(patch)
    observations: list[_LineObservation] = []
    for orientation, count in (
        (GridLineOrientation.VERTICAL, _SUPPORTED_COLUMNS + 1),
        (GridLineOrientation.HORIZONTAL, _SUPPORTED_ROWS + 1),
    ):
        for index in range(count):
            grouped = tuple(
                segment
                for segment in segments
                if segment.orientation is orientation
                and _nearest_expected_index(
                    segment.coordinate,
                    orientation=orientation,
                    board_rect=board_rect,
                    thresholds=thresholds,
                )
                == index
            )
            observed = _fit_segment_group(
                grouped,
                orientation=orientation,
                index=index,
                board_rect=board_rect,
                thresholds=thresholds,
            )
            if index in {0, count - 1}:
                border = _fit_red_border(
                    red,
                    orientation=orientation,
                    index=index,
                    board_rect=board_rect,
                    thresholds=thresholds,
                )
                if border is not None and (
                    observed is None or border.support_score > observed.support_score
                ):
                    observed = border
                elif observed is not None and border is not None:
                    observed = _LineObservation(
                        orientation=observed.orientation,
                        index=observed.index,
                        line=observed.line,
                        coverage=max(observed.coverage, border.coverage),
                        support_score=max(observed.support_score, border.support_score),
                        segment_count=observed.segment_count,
                        border_evidence=True,
                    )
            if observed is not None:
                observations.append(observed)
    return tuple(observations), len(segments)


def _segments(
    raw: NDArray[np.float32] | None,
    *,
    board_rect: tuple[float, float, float, float],
    thresholds: StructuredBoardLineThresholds,
) -> tuple[_Segment, ...]:
    if raw is None:
        return ()
    left, top, width, height = board_rect
    centre_x, centre_y = left + width / 2.0, top + height / 2.0
    tolerance = thresholds.maximum_axis_angle_degrees
    result: list[_Segment] = []
    for x1, y1, x2, y2 in raw.reshape(-1, 4):
        start = np.asarray([float(x1), float(y1)], dtype=np.float64)
        end = np.asarray([float(x2), float(y2)], dtype=np.float64)
        delta = end - start
        length = float(np.linalg.norm(delta))
        if length <= 0:
            continue
        angle = abs(math.degrees(math.atan2(float(delta[1]), float(delta[0])))) % 180.0
        horizontal_error = min(angle, 180.0 - angle)
        vertical_error = abs(90.0 - angle)
        if vertical_error <= tolerance:
            orientation = GridLineOrientation.VERTICAL
            if length < height * thresholds.minimum_segment_axis_fraction:
                continue
            coordinate = _segment_axis_coordinate(start, end, at=centre_y, vertical=True)
        elif horizontal_error <= tolerance:
            orientation = GridLineOrientation.HORIZONTAL
            if length < width * thresholds.minimum_segment_axis_fraction:
                continue
            coordinate = _segment_axis_coordinate(start, end, at=centre_x, vertical=False)
        else:
            continue
        margin = thresholds.analysis_margin * 0.8
        midpoint = (start + end) / 2.0
        if not (
            left - margin <= midpoint[0] <= left + width + margin
            and top - margin <= midpoint[1] <= top + height + margin
        ):
            continue
        result.append(
            _Segment(
                start=start,
                end=end,
                orientation=orientation,
                coordinate=coordinate,
                angle_degrees=angle,
                length=length,
            )
        )
    return tuple(result)


def _segment_axis_coordinate(
    start: NDArray[np.float64],
    end: NDArray[np.float64],
    *,
    at: float,
    vertical: bool,
) -> float:
    if vertical:
        delta = float(end[1] - start[1])
        return (
            float((start[0] + end[0]) / 2.0)
            if abs(delta) < 1e-9
            else float(start[0] + (at - start[1]) * (end[0] - start[0]) / delta)
        )
    delta = float(end[0] - start[0])
    return (
        float((start[1] + end[1]) / 2.0)
        if abs(delta) < 1e-9
        else float(start[1] + (at - start[0]) * (end[1] - start[1]) / delta)
    )


def _nearest_expected_index(
    coordinate: float,
    *,
    orientation: GridLineOrientation,
    board_rect: tuple[float, float, float, float],
    thresholds: StructuredBoardLineThresholds,
) -> int | None:
    left, top, width, height = board_rect
    count = _SUPPORTED_COLUMNS if orientation is GridLineOrientation.VERTICAL else _SUPPORTED_ROWS
    origin = left if orientation is GridLineOrientation.VERTICAL else top
    span = width if orientation is GridLineOrientation.VERTICAL else height
    pitch = span / count
    raw = (coordinate - origin) / pitch
    index = int(round(raw))
    if (
        index not in range(count + 1)
        or abs(raw - index) > thresholds.maximum_expected_line_distance_fraction
    ):
        return None
    return index


def _fit_segment_group(
    segments: Sequence[_Segment],
    *,
    orientation: GridLineOrientation,
    index: int,
    board_rect: tuple[float, float, float, float],
    thresholds: StructuredBoardLineThresholds,
) -> _LineObservation | None:
    if not segments:
        return None
    left, top, width, height = board_rect
    expected = (
        left + index * width / _SUPPORTED_COLUMNS
        if orientation is GridLineOrientation.VERTICAL
        else top + index * height / _SUPPORTED_ROWS
    )
    seed = min(
        segments,
        key=lambda value: (abs(value.coordinate - expected), -value.length, value.coordinate),
    )
    compatible = tuple(
        value
        for value in segments
        if abs(value.coordinate - seed.coordinate) <= thresholds.line_cluster_distance_px
        and _angle_distance(value.angle_degrees, seed.angle_degrees)
        <= thresholds.line_cluster_angle_degrees
    )
    points = np.asarray(
        [point for value in compatible for point in (value.start, value.end)],
        dtype=np.float32,
    )
    if len(points) < 2:
        return None
    fitted = cv2.fitLine(points, cv2.DIST_HUBER, 0, 0.01, 0.01).reshape(-1)
    vx, vy, x0, y0 = (float(value) for value in fitted)
    line = _normal_line(np.asarray([vy, -vx, vx * y0 - vy * x0], dtype=np.float64))
    axis_start, axis_end = (
        (top, top + height) if orientation is GridLineOrientation.VERTICAL else (left, left + width)
    )
    intervals = []
    for value in compatible:
        first = float(
            value.start[1] if orientation is GridLineOrientation.VERTICAL else value.start[0]
        )
        second = float(
            value.end[1] if orientation is GridLineOrientation.VERTICAL else value.end[0]
        )
        intervals.append((max(axis_start, min(first, second)), min(axis_end, max(first, second))))
    coverage = _interval_coverage(intervals, start=axis_start, end=axis_end)
    if coverage < thresholds.minimum_line_axis_coverage:
        return None
    orientation_quality = max(
        0.0,
        1.0
        - min(_orientation_error(value.angle_degrees, orientation) for value in compatible)
        / thresholds.maximum_axis_angle_degrees,
    )
    return _LineObservation(
        orientation=orientation,
        index=index,
        line=line,
        coverage=coverage,
        support_score=_unit(0.75 * coverage + 0.25 * orientation_quality),
        segment_count=len(compatible),
        border_evidence=False,
    )


def _fit_red_border(
    red_mask: NDArray[np.uint8],
    *,
    orientation: GridLineOrientation,
    index: int,
    board_rect: tuple[float, float, float, float],
    thresholds: StructuredBoardLineThresholds,
) -> _LineObservation | None:
    left, top, width, height = board_rect
    count = _SUPPORTED_COLUMNS if orientation is GridLineOrientation.VERTICAL else _SUPPORTED_ROWS
    expected = (
        left + index * width / count
        if orientation is GridLineOrientation.VERTICAL
        else top + index * height / count
    )
    band = max(4, int(round(thresholds.canonical_cell_size * 0.18)))
    ys, xs = np.nonzero(red_mask)
    if orientation is GridLineOrientation.VERTICAL:
        valid = (np.abs(xs - expected) <= band) & (ys >= top - 3) & (ys <= top + height + 3)
        axis = ys[valid].astype(np.float64)
    else:
        valid = (np.abs(ys - expected) <= band) & (xs >= left - 3) & (xs <= left + width + 3)
        axis = xs[valid].astype(np.float64)
    points = np.column_stack((xs[valid], ys[valid])).astype(np.float32)
    if len(points) < 12:
        return None
    fitted = cv2.fitLine(points, cv2.DIST_HUBER, 0, 0.01, 0.01).reshape(-1)
    vx, vy, x0, y0 = (float(value) for value in fitted)
    angle = abs(math.degrees(math.atan2(vy, vx))) % 180.0
    if _orientation_error(angle, orientation) > thresholds.maximum_axis_angle_degrees:
        return None
    line = _normal_line(np.asarray([vy, -vx, vx * y0 - vy * x0], dtype=np.float64))
    axis_start, axis_length = (
        (top, height) if orientation is GridLineOrientation.VERTICAL else (left, width)
    )
    bins = max(12, int(round(axis_length / 3.0)))
    occupied = np.unique(
        np.clip(((axis - axis_start) / max(axis_length, 1.0) * bins).astype(np.intp), 0, bins - 1)
    )
    coverage = float(len(occupied) / bins)
    if coverage < thresholds.minimum_outer_border_axis_coverage:
        return None
    return _LineObservation(
        orientation=orientation,
        index=index,
        line=line,
        coverage=coverage,
        support_score=_unit(coverage),
        segment_count=0,
        border_evidence=True,
    )


def _red_mask(rgb: NDArray[np.uint8]) -> NDArray[np.uint8]:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    low = cv2.inRange(hsv, np.array((0, 70, 45)), np.array((20, 255, 255)))
    high = cv2.inRange(hsv, np.array((163, 70, 45)), np.array((179, 255, 255)))
    return cast(
        NDArray[np.uint8],
        cv2.morphologyEx(cv2.bitwise_or(low, high), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)),
    )


def _fit_local_homography(
    vertical: Sequence[_LineObservation],
    horizontal: Sequence[_LineObservation],
    *,
    patch_to_half: NDArray[np.float64],
    initial_quad: SourceQuad,
    source_width: int,
    source_height: int,
    topology: BoardTopology,
    thresholds: StructuredBoardLineThresholds,
) -> _HomographyFit | None:
    ideal: list[tuple[float, float]] = []
    observed: list[tuple[float, float]] = []
    for horizontal_line in horizontal:
        for vertical_line in vertical:
            point = _intersection(vertical_line.line, horizontal_line.line)
            if point is None:
                continue
            ideal.append((float(vertical_line.index), float(horizontal_line.index)))
            observed.append(point)
    if len(ideal) < 4:
        return None
    ideal_array = np.asarray(ideal, dtype=np.float64)
    observed_array = np.asarray(observed, dtype=np.float64)
    patch_scale = _patch_to_half_scale(patch_to_half)
    ransac_patch_threshold = thresholds.ransac_half_scale_reprojection_threshold / max(
        patch_scale, 1e-6
    )
    candidate, raw_mask = cv2.findHomography(
        ideal_array,
        observed_array,
        method=cv2.RANSAC,
        ransacReprojThreshold=max(1.5, ransac_patch_threshold),
        maxIters=2000,
        confidence=0.995,
    )
    if candidate is None or raw_mask is None:
        return None
    mask = raw_mask.reshape(-1).astype(bool)
    if int(mask.sum()) < 4:
        return None
    refined, _ = cv2.findHomography(ideal_array[mask], observed_array[mask], method=0)
    if refined is None:
        return None
    ideal_to_patch = _normalize_homography(cast(NDArray[np.float64], refined))
    if ideal_to_patch is None:
        return None
    projected_patch = _project_points(ideal_array, ideal_to_patch)
    projected_half = _project_points(projected_patch, patch_to_half)
    observed_half = _project_points(observed_array, patch_to_half)
    residuals = np.linalg.norm(projected_half - observed_half, axis=1)
    p95 = float(np.percentile(residuals[mask], 95))
    half_to_full = np.diag([2.0, 2.0, 1.0])
    ideal_to_source = _normalize_homography(half_to_full @ patch_to_half @ ideal_to_patch)
    if ideal_to_source is None:
        return None
    outer = np.asarray(
        [
            [0.0, 0.0],
            [float(topology.columns), 0.0],
            [float(topology.columns), float(topology.rows)],
            [0.0, float(topology.rows)],
        ],
        dtype=np.float64,
    )
    final_points = _project_points(outer, ideal_to_source)
    try:
        final_quad = _source_quad(final_points)
    except ValueError:
        return None
    source_support = _padded_cells_within_source(
        ideal_to_source,
        topology=topology,
        width=source_width,
        height=source_height,
        padding=thresholds.cell_padding_fraction,
    )
    alignment = _initialization_alignment_valid(
        initial_quad,
        final_quad,
        maximum_corner_shift_fraction=thresholds.maximum_initial_quad_corner_shift_fraction,
        minimum_iou=thresholds.minimum_initial_quad_iou,
    )
    return _HomographyFit(
        ideal_to_patch=ideal_to_patch,
        ideal_to_source=ideal_to_source,
        final_quad=final_quad,
        p95_half_scale_reprojection_error=p95,
        supported_intersection_count=len(ideal),
        inlier_intersection_count=int(mask.sum()),
        source_support_complete=source_support,
        initialization_alignment_valid=alignment,
    )


def _infer_single_internal_line(
    vertical: Sequence[_LineObservation],
    horizontal: Sequence[_LineObservation],
    *,
    spacing_regular: bool,
    initialization_alignment_valid: bool,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    vertical_indexes = {value.index for value in vertical}
    horizontal_indexes = {value.index for value in horizontal}
    outer_complete = {0, _SUPPORTED_COLUMNS}.issubset(vertical_indexes) and {
        0,
        _SUPPORTED_ROWS,
    }.issubset(horizontal_indexes)
    if not outer_complete or not spacing_regular or not initialization_alignment_valid:
        return (), ()
    missing_vertical = tuple(
        index for index in range(1, _SUPPORTED_COLUMNS) if index not in vertical_indexes
    )
    missing_horizontal = tuple(
        index for index in range(1, _SUPPORTED_ROWS) if index not in horizontal_indexes
    )
    if len(missing_vertical) + len(missing_horizontal) > 1:
        return (), ()
    return missing_vertical, missing_horizontal


def _external_boundary_support_count(
    vertical: Sequence[_LineObservation],
    horizontal: Sequence[_LineObservation],
) -> int:
    return sum(
        1
        for orientation, index, values in (
            (GridLineOrientation.VERTICAL, 0, vertical),
            (GridLineOrientation.VERTICAL, _SUPPORTED_COLUMNS, vertical),
            (GridLineOrientation.HORIZONTAL, 0, horizontal),
            (GridLineOrientation.HORIZONTAL, _SUPPORTED_ROWS, horizontal),
        )
        if any(value.orientation is orientation and value.index == index for value in values)
    )


def _line_coverage_score(
    vertical: Sequence[_LineObservation],
    horizontal: Sequence[_LineObservation],
) -> float:
    count_score = (len(vertical) + len(horizontal)) / 10.0
    supports = [value.support_score for value in (*vertical, *horizontal)]
    support_score = float(np.mean(supports)) if supports else 0.0
    return _unit(0.65 * count_score + 0.35 * support_score)


def _border_evidence_score(
    vertical: Sequence[_LineObservation],
    horizontal: Sequence[_LineObservation],
) -> float:
    support: list[float] = []
    for index, values in (
        (0, vertical),
        (_SUPPORTED_COLUMNS, vertical),
        (0, horizontal),
        (_SUPPORTED_ROWS, horizontal),
    ):
        matches = [value.support_score for value in values if value.index == index]
        support.append(max(matches) if matches else 0.0)
    return _unit(float(np.mean(support)))


def _spacing_regularity_score(
    vertical: Sequence[_LineObservation],
    horizontal: Sequence[_LineObservation],
    *,
    board_rect: tuple[float, float, float, float],
) -> float:
    left, top, width, height = board_rect
    scores = (
        _family_spacing_score(vertical, at=top + height / 2.0, pitch=width / _SUPPORTED_COLUMNS),
        _family_spacing_score(horizontal, at=left + width / 2.0, pitch=height / _SUPPORTED_ROWS),
    )
    return _unit(float(np.mean(scores)))


def _family_spacing_score(
    observations: Sequence[_LineObservation],
    *,
    at: float,
    pitch: float,
) -> float:
    ordered = sorted(observations, key=lambda value: value.index)
    normalized: list[float] = []
    for first, second in zip(ordered, ordered[1:], strict=False):
        index_gap = second.index - first.index
        if index_gap <= 0:
            continue
        first_coordinate = _line_coordinate(
            first.line, at=at, vertical=first.orientation is GridLineOrientation.VERTICAL
        )
        second_coordinate = _line_coordinate(
            second.line, at=at, vertical=second.orientation is GridLineOrientation.VERTICAL
        )
        normalized.append(abs(second_coordinate - first_coordinate) / (pitch * index_gap))
    if not normalized:
        return 0.0
    deviations = [abs(value - 1.0) for value in normalized]
    return _unit(1.0 - 2.5 * float(np.mean(deviations)))


def _output_grid_lines(
    ideal_to_source: NDArray[np.float64],
    *,
    vertical: Sequence[_LineObservation],
    horizontal: Sequence[_LineObservation],
    inferred_vertical: tuple[int, ...],
    inferred_horizontal: tuple[int, ...],
) -> tuple[RefinedGridLine, ...]:
    vertical_by_index = {value.index: value for value in vertical}
    horizontal_by_index = {value.index: value for value in horizontal}
    output: list[RefinedGridLine] = []
    for index in range(_SUPPORTED_COLUMNS + 1):
        observation = vertical_by_index.get(index)
        if observation is None and index not in inferred_vertical:
            continue
        points = _project_points(
            np.asarray([[index, 0.0], [index, float(_SUPPORTED_ROWS)]], dtype=np.float64),
            ideal_to_source,
        )
        output.append(
            RefinedGridLine(
                orientation=GridLineOrientation.VERTICAL,
                index=index,
                source_start=SourcePoint(x=float(points[0, 0]), y=float(points[0, 1])),
                source_end=SourcePoint(x=float(points[1, 0]), y=float(points[1, 1])),
                support_score=0.0 if observation is None else observation.support_score,
                inferred=observation is None,
                border_evidence=False if observation is None else observation.border_evidence,
                segment_count=0 if observation is None else observation.segment_count,
            )
        )
    for index in range(_SUPPORTED_ROWS + 1):
        observation = horizontal_by_index.get(index)
        if observation is None and index not in inferred_horizontal:
            continue
        points = _project_points(
            np.asarray([[0.0, index], [float(_SUPPORTED_COLUMNS), index]], dtype=np.float64),
            ideal_to_source,
        )
        output.append(
            RefinedGridLine(
                orientation=GridLineOrientation.HORIZONTAL,
                index=index,
                source_start=SourcePoint(x=float(points[0, 0]), y=float(points[0, 1])),
                source_end=SourcePoint(x=float(points[1, 0]), y=float(points[1, 1])),
                support_score=0.0 if observation is None else observation.support_score,
                inferred=observation is None,
                border_evidence=False if observation is None else observation.border_evidence,
                segment_count=0 if observation is None else observation.segment_count,
            )
        )
    return tuple(output)


def _padded_cells_within_source(
    ideal_to_source: NDArray[np.float64],
    *,
    topology: BoardTopology,
    width: int,
    height: int,
    padding: float,
) -> bool:
    for row in range(topology.rows):
        for column in range(topology.columns):
            points = np.asarray(
                [
                    [column - padding, row - padding],
                    [column + 1 + padding, row - padding],
                    [column + 1 + padding, row + 1 + padding],
                    [column - padding, row + 1 + padding],
                ],
                dtype=np.float64,
            )
            projected = _project_points(points, ideal_to_source)
            if (
                np.any(projected[:, 0] < 0)
                or np.any(projected[:, 0] > width)
                or np.any(projected[:, 1] < 0)
                or np.any(projected[:, 1] > height)
            ):
                return False
    return True


def _initialization_alignment_valid(
    initial: SourceQuad,
    final: SourceQuad,
    *,
    maximum_corner_shift_fraction: float,
    minimum_iou: float,
) -> bool:
    initial_array = _quad_array(initial)
    final_array = _quad_array(final)
    initial_scale = max(
        1.0,
        float(
            (
                np.linalg.norm(initial_array[1] - initial_array[0])
                + np.linalg.norm(initial_array[3] - initial_array[0])
            )
            / 2.0
        ),
    )
    maximum_shift = float(np.max(np.linalg.norm(final_array - initial_array, axis=1)))
    intersection, _ = cv2.intersectConvexConvex(
        initial_array.astype(np.float32), final_array.astype(np.float32)
    )
    union = (
        abs(cv2.contourArea(initial_array.astype(np.float32)))
        + abs(cv2.contourArea(final_array.astype(np.float32)))
        - intersection
    )
    iou = 0.0 if union <= 0 else float(intersection / union)
    return maximum_shift / initial_scale <= maximum_corner_shift_fraction and iou >= minimum_iou


def _reprojection_score(value: float | None, *, maximum: float) -> float:
    if value is None:
        return 0.0
    return _unit(1.0 - value / (2.0 * maximum))


def _patch_to_half_scale(matrix: NDArray[np.float64]) -> float:
    origin = _project_points(np.asarray([[0.0, 0.0]], dtype=np.float64), matrix)[0]
    axes = _project_points(np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float64), matrix)
    return float((np.linalg.norm(axes[0] - origin) + np.linalg.norm(axes[1] - origin)) / 2.0)


def _project_points(
    points: NDArray[np.float64], matrix: NDArray[np.float64]
) -> NDArray[np.float64]:
    projected = cv2.perspectiveTransform(points.reshape(-1, 1, 2), matrix).reshape(-1, 2)
    return cast(NDArray[np.float64], projected)


def _intersection(
    first: NDArray[np.float64], second: NDArray[np.float64]
) -> tuple[float, float] | None:
    point = np.cross(first, second)
    if abs(float(point[2])) < 1e-9:
        return None
    return float(point[0] / point[2]), float(point[1] / point[2])


def _normal_line(line: NDArray[np.float64]) -> NDArray[np.float64]:
    scale = math.hypot(float(line[0]), float(line[1]))
    if scale <= 1e-12:
        raise ValueError("Line is singular.")
    normalized = line / scale
    if normalized[0] < 0 or (abs(float(normalized[0])) < 1e-12 and normalized[1] < 0):
        normalized = -normalized
    return normalized


def _line_coordinate(line: NDArray[np.float64], *, at: float, vertical: bool) -> float:
    a, b, c = (float(value) for value in line)
    if vertical:
        return float("inf") if abs(a) < 1e-9 else -(b * at + c) / a
    return float("inf") if abs(b) < 1e-9 else -(a * at + c) / b


def _interval_coverage(
    intervals: Sequence[tuple[float, float]],
    *,
    start: float,
    end: float,
) -> float:
    valid = sorted((left, right) for left, right in intervals if right > left)
    if not valid or end <= start:
        return 0.0
    merged: list[list[float]] = []
    for left, right in valid:
        if not merged or left > merged[-1][1] + 2.0:
            merged.append([left, right])
        else:
            merged[-1][1] = max(merged[-1][1], right)
    return _unit(sum(right - left for left, right in merged) / (end - start))


def _angle_distance(first: float, second: float) -> float:
    difference = abs(first - second) % 180.0
    return min(difference, 180.0 - difference)


def _orientation_error(angle: float, orientation: GridLineOrientation) -> float:
    if orientation is GridLineOrientation.VERTICAL:
        return abs(90.0 - angle)
    return min(angle, 180.0 - angle)


def _normalize_homography(matrix: NDArray[np.float64]) -> NDArray[np.float64] | None:
    if not np.isfinite(matrix).all() or abs(float(matrix[2, 2])) < 1e-12:
        return None
    normalized = matrix / matrix[2, 2]
    return cast(NDArray[np.float64], normalized)


def _source_quad(points: NDArray[np.float64]) -> SourceQuad:
    values = tuple(SourcePoint(x=float(point[0]), y=float(point[1])) for point in points)
    return SourceQuad(
        corners=cast(tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint], values)
    )


def _quad_array(quad: SourceQuad) -> NDArray[np.float64]:
    return np.asarray([[point.x, point.y] for point in quad.corners], dtype=np.float64)


def _matrix_payload(matrix: NDArray[np.float64]) -> Matrix3x3:
    normalized = matrix / matrix[2, 2]
    rows = tuple(tuple(round(float(value), 12) for value in row) for row in normalized)
    return cast(Matrix3x3, rows)


def _unit(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def _diagnostics(**values: float | int | str) -> tuple[tuple[str, float | int | str], ...]:
    return tuple(sorted(values.items()))


__all__ = [
    "DEFAULT_STRUCTURED_BOARD_LINE_THRESHOLDS",
    "STRUCTURED_BOARD_LINE_CONFIG_VERSION",
    "STRUCTURED_BOARD_LINE_REFINEMENT_VERSION",
    "BoardLineRefinementResult",
    "BoardLineRefiner",
    "GridLineOrientation",
    "RefinedGridLine",
    "StructuredBoardLineRefinementError",
    "StructuredBoardLineThresholds",
]
