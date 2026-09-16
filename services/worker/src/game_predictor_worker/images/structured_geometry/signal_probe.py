"""Read-only multi-evidence probes for one checksum-bound board quad."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, cast

import cv2
import numpy as np
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_geometry_v2 import SourcePoint, SourceQuad
from numpy.typing import NDArray

STRUCTURED_GEOMETRY_SIGNAL_PROBE_VERSION: Final = (
    "structured-geometry-multi-evidence-signal-probe-v1"
)
_CANONICAL_CELL_SIZE: Final = 100


@dataclass(frozen=True, slots=True)
class StructuredGeometrySignalProbe:
    outer_border_score: float
    lsd_vertical_count: int
    lsd_horizontal_count: int
    lsd_coverage_score: float
    hough_vertical_count: int
    hough_horizontal_count: int
    hough_coverage_score: float
    vertical_gradient_profile_score: float
    horizontal_gradient_profile_score: float
    grid_periodicity_score: float
    symbol_center_support_score: float
    analysis_scale: float
    analysis_width: int
    analysis_height: int
    probe_coordinate_source: str
    version: str = STRUCTURED_GEOMETRY_SIGNAL_PROBE_VERSION

    def to_payload(self) -> dict[str, object]:
        return {
            "analysisHeight": self.analysis_height,
            "analysisScale": round(self.analysis_scale, 8),
            "analysisWidth": self.analysis_width,
            "gridPeriodicityScore": round(self.grid_periodicity_score, 8),
            "horizontalGradientProfileScore": round(self.horizontal_gradient_profile_score, 8),
            "houghCoverageScore": round(self.hough_coverage_score, 8),
            "houghHorizontalCount": self.hough_horizontal_count,
            "houghVerticalCount": self.hough_vertical_count,
            "lsdCoverageScore": round(self.lsd_coverage_score, 8),
            "lsdHorizontalCount": self.lsd_horizontal_count,
            "lsdVerticalCount": self.lsd_vertical_count,
            "outerBorderScore": round(self.outer_border_score, 8),
            "probeCoordinateSource": self.probe_coordinate_source,
            "symbolCenterSupportScore": round(self.symbol_center_support_score, 8),
            "version": self.version,
            "verticalGradientProfileScore": round(self.vertical_gradient_profile_score, 8),
        }


def probe_board_signals(
    rgb: NDArray[np.uint8],
    quad: SourceQuad,
    *,
    topology: BoardTopology,
    analysis_scale: float,
    coordinate_source: str,
) -> StructuredGeometrySignalProbe:
    """Measure independent evidence without making or applying a geometry decision."""

    if (
        rgb.ndim != 3
        or rgb.shape[2] != 3
        or rgb.dtype != np.uint8
        or not 0 < analysis_scale <= 1
        or not coordinate_source
    ):
        raise ValueError("A signal probe requires RGB, a bounded scale and coordinate source.")
    analysis_rgb, analysis_quad = _scaled_source(rgb, quad, scale=analysis_scale)
    width = topology.columns * _CANONICAL_CELL_SIZE
    height = topology.rows * _CANONICAL_CELL_SIZE
    patch = _rectify(analysis_rgb, analysis_quad, width=width, height=height)
    gray = cast(NDArray[np.uint8], cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY))
    hsv = cv2.cvtColor(patch, cv2.COLOR_RGB2HSV)
    low_red = cv2.inRange(hsv, np.array([0, 70, 45]), np.array([12, 255, 255]))
    high_red = cv2.inRange(hsv, np.array([165, 70, 45]), np.array([179, 255, 255]))
    red = cv2.bitwise_or(low_red, high_red)
    border_size = max(4, round(_CANONICAL_CELL_SIZE * 0.12))
    border = np.zeros(red.shape, dtype=np.uint8)
    border[:border_size, :] = 255
    border[-border_size:, :] = 255
    border[:, :border_size] = 255
    border[:, -border_size:] = 255
    outer_border_score = float(
        np.count_nonzero(cv2.bitwise_and(red, border)) / max(1, int(np.count_nonzero(border)))
    )

    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(6, 6)).apply(gray)
    edges = cv2.Canny(enhanced, 45, 135)
    hough_vertical_coordinates: list[float] = []
    hough_horizontal_coordinates: list[float] = []
    hough = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=max(24, round(min(width, height) * 0.11)),
        minLineLength=max(30, round(min(width, height) * 0.14)),
        maxLineGap=max(8, round(min(width, height) * 0.047)),
    )
    if hough is not None:
        for x1, y1, x2, y2 in hough[:, 0]:
            _append_axis_coordinate(
                hough_vertical_coordinates,
                hough_horizontal_coordinates,
                x1=float(x1),
                y1=float(y1),
                x2=float(x2),
                y2=float(y2),
            )
    hough_vertical = _expected_support_count(hough_vertical_coordinates, width, topology.columns)
    hough_horizontal = _expected_support_count(hough_horizontal_coordinates, height, topology.rows)
    hough_score = _coverage_score(
        hough_vertical,
        hough_horizontal,
        topology=topology,
    )

    lsd_vertical_coordinates: list[float] = []
    lsd_horizontal_coordinates: list[float] = []
    detected = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD).detect(enhanced)[0]
    if detected is not None:
        for x1, y1, x2, y2 in detected.reshape((-1, 4)):
            _append_axis_coordinate(
                lsd_vertical_coordinates,
                lsd_horizontal_coordinates,
                x1=float(x1),
                y1=float(y1),
                x2=float(x2),
                y2=float(y2),
            )
    lsd_vertical = _expected_support_count(lsd_vertical_coordinates, width, topology.columns)
    lsd_horizontal = _expected_support_count(lsd_horizontal_coordinates, height, topology.rows)
    lsd_score = _coverage_score(lsd_vertical, lsd_horizontal, topology=topology)

    vertical_gradient = np.mean(np.abs(cv2.Sobel(enhanced, cv2.CV_32F, 1, 0, ksize=3)), axis=0)
    horizontal_gradient = np.mean(np.abs(cv2.Sobel(enhanced, cv2.CV_32F, 0, 1, ksize=3)), axis=1)
    vertical_profile, vertical_peaks = _profile_score(vertical_gradient, topology.columns)
    horizontal_profile, horizontal_peaks = _profile_score(horizontal_gradient, topology.rows)
    periodicity = (
        _spacing_score(vertical_peaks, expected_count=topology.columns + 1)
        + _spacing_score(horizontal_peaks, expected_count=topology.rows + 1)
    ) / 2
    return StructuredGeometrySignalProbe(
        outer_border_score=_unit(outer_border_score),
        lsd_vertical_count=lsd_vertical,
        lsd_horizontal_count=lsd_horizontal,
        lsd_coverage_score=_unit(lsd_score),
        hough_vertical_count=hough_vertical,
        hough_horizontal_count=hough_horizontal,
        hough_coverage_score=_unit(hough_score),
        vertical_gradient_profile_score=vertical_profile,
        horizontal_gradient_profile_score=horizontal_profile,
        grid_periodicity_score=_unit(periodicity),
        symbol_center_support_score=_symbol_center_support(gray, topology=topology),
        analysis_scale=analysis_scale,
        analysis_width=int(analysis_rgb.shape[1]),
        analysis_height=int(analysis_rgb.shape[0]),
        probe_coordinate_source=coordinate_source,
    )


def _scaled_source(
    rgb: NDArray[np.uint8],
    quad: SourceQuad,
    *,
    scale: float,
) -> tuple[NDArray[np.uint8], SourceQuad]:
    if math.isclose(scale, 1.0, abs_tol=1e-9):
        return rgb, quad
    width = max(1, round(rgb.shape[1] * scale))
    height = max(1, round(rgb.shape[0] * scale))
    scaled = cast(
        NDArray[np.uint8],
        cv2.resize(rgb, (width, height), interpolation=cv2.INTER_AREA),
    )
    lt, rt, rb, lb = quad.corners
    return scaled, SourceQuad(
        corners=(
            SourcePoint(x=lt.x * scale, y=lt.y * scale),
            SourcePoint(x=rt.x * scale, y=rt.y * scale),
            SourcePoint(x=rb.x * scale, y=rb.y * scale),
            SourcePoint(x=lb.x * scale, y=lb.y * scale),
        )
    )


def _rectify(
    rgb: NDArray[np.uint8],
    quad: SourceQuad,
    *,
    width: int,
    height: int,
) -> NDArray[np.uint8]:
    source = np.asarray([[point.x, point.y] for point in quad.corners], dtype=np.float32)
    destination = np.asarray(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(source, destination)
    return cast(
        NDArray[np.uint8],
        cv2.warpPerspective(rgb, transform, (width, height), flags=cv2.INTER_LINEAR),
    )


def _append_axis_coordinate(
    vertical: list[float],
    horizontal: list[float],
    *,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> None:
    angle = abs(math.degrees(math.atan2(y2 - y1, x2 - x1)))
    if 70 <= angle <= 110:
        vertical.append((x1 + x2) / 2)
    elif angle <= 20 or angle >= 160:
        horizontal.append((y1 + y2) / 2)


def _coverage_score(
    vertical_count: int,
    horizontal_count: int,
    *,
    topology: BoardTopology,
) -> float:
    return (vertical_count / (topology.columns + 1) + horizontal_count / (topology.rows + 1)) / 2


def _profile_score(profile: NDArray[np.floating], cells: int) -> tuple[float, tuple[float, ...]]:
    length = profile.shape[0]
    radius = max(2, round(length / cells * 0.08))
    baseline = float(np.median(profile)) + 1e-6
    peaks: list[float] = []
    strengths: list[float] = []
    for index in range(cells + 1):
        expected = round(index * (length - 1) / cells)
        start, end = max(0, expected - radius), min(length, expected + radius + 1)
        local = profile[start:end]
        local_index = start + int(np.argmax(local))
        peaks.append(float(local_index))
        strengths.append(float(profile[local_index]) / baseline)
    score = float(np.mean([min(1.0, max(0.0, (value - 1.0) / 2.0)) for value in strengths]))
    return _unit(score), tuple(peaks)


def _spacing_score(peaks: Sequence[float], *, expected_count: int) -> float:
    if len(peaks) != expected_count or expected_count < 2:
        return 0.0
    spacing = np.diff(np.asarray(peaks, dtype=np.float64))
    mean = float(np.mean(spacing))
    if mean <= 0:
        return 0.0
    return _unit(1.0 - float(np.std(spacing)) / mean)


def _symbol_center_support(
    gray: NDArray[np.uint8],
    *,
    topology: BoardTopology,
) -> float:
    scores: list[float] = []
    for row in range(topology.rows):
        for column in range(topology.columns):
            cell = gray[
                row * _CANONICAL_CELL_SIZE : (row + 1) * _CANONICAL_CELL_SIZE,
                column * _CANONICAL_CELL_SIZE : (column + 1) * _CANONICAL_CELL_SIZE,
            ]
            center = cell[22:78, 22:78]
            scores.append(min(1.0, float(np.std(center)) / (float(np.std(cell)) + 1e-6)))
    return _unit(float(np.mean(scores)))


def _expected_support_count(coordinates: Sequence[float], length: int, cells: int) -> int:
    tolerance = length / cells * 0.14
    return sum(
        any(abs(value - index * (length - 1) / cells) <= tolerance for value in coordinates)
        for index in range(cells + 1)
    )


def _unit(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


__all__ = [
    "STRUCTURED_GEOMETRY_SIGNAL_PROBE_VERSION",
    "StructuredGeometrySignalProbe",
    "probe_board_signals",
]
