"""Classical page and 3 Ã— 3 board detection for normalized RGB images."""

from __future__ import annotations

import hashlib
import json
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Protocol, cast

import cv2
import numpy as np
from numpy.typing import NDArray

DETECTOR_VERSION = "page-board-detector-v2"
EXPECTED_BOARD_COUNT = 9
MAX_BOARD_COUNT = 9
RED_LOW_1 = np.array((0, 80, 50), dtype=np.uint8)
RED_HIGH_1 = np.array((18, 255, 255), dtype=np.uint8)
RED_LOW_2 = np.array((165, 80, 50), dtype=np.uint8)
RED_HIGH_2 = np.array((179, 255, 255), dtype=np.uint8)


class GeometryDetectionError(ValueError):
    """Stable fatal error for detector orchestration."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class Point:
    x: int
    y: int

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y}


Quad = tuple[Point, Point, Point, Point]


@dataclass(frozen=True, slots=True)
class BoardDetection:
    position_index: int
    quad: Quad
    bounding_box: tuple[int, int, int, int]
    red_border_score: float
    refined_from_grid: bool

    def to_dict(self) -> dict[str, object]:
        x, y, width, height = self.bounding_box
        return {
            "boundingBox": {
                "height": height,
                "width": width,
                "x": x,
                "y": y,
            },
            "positionIndex": self.position_index,
            "quad": [point.to_dict() for point in self.quad],
            "redBorderScore": self.red_border_score,
            "refinedFromGrid": self.refined_from_grid,
        }


@dataclass(frozen=True, slots=True)
class DetectionResult:
    status: Literal["detected", "needs_review"]
    image_width: int
    image_height: int
    candidate_count: int
    page_quad: Quad | None
    boards: tuple[BoardDetection, ...]
    confidence: float
    confidence_components: Mapping[str, float]
    review_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "boards": [board.to_dict() for board in self.boards],
            "candidateCount": self.candidate_count,
            "confidence": self.confidence,
            "confidenceComponents": dict(self.confidence_components),
            "imageHeight": self.image_height,
            "imageWidth": self.image_width,
            "pageQuad": (
                [point.to_dict() for point in self.page_quad]
                if self.page_quad is not None
                else None
            ),
            "reviewReasons": list(self.review_reasons),
            "status": self.status,
        }


class PageBoardDetector(Protocol):
    """Port for replaceable page and board geometry."""

    version: str

    def detect(
        self,
        rgb_image: NDArray[np.uint8],
        *,
        expected_board_count: int = EXPECTED_BOARD_COUNT,
        allow_grid_recovery: bool = False,
        allow_occluded_grid_recovery: bool = False,
    ) -> DetectionResult:
        """Detect a supported page variant without mutating the input."""


@dataclass(frozen=True, slots=True)
class _Candidate:
    x: int
    y: int
    width: int
    height: int
    red_border_score: float
    refined_from_grid: bool = False

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2


def _odd_at_least(value: float, minimum: int) -> int:
    rounded = max(minimum, int(round(value)))
    return rounded if rounded % 2 == 1 else rounded + 1


def _red_mask(rgb_image: NDArray[np.uint8]) -> NDArray[np.uint8]:
    height, width = rgb_image.shape[:2]
    hsv = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2HSV)
    mask = cv2.bitwise_or(
        cv2.inRange(hsv, RED_LOW_1, RED_HIGH_1),
        cv2.inRange(hsv, RED_LOW_2, RED_HIGH_2),
    )
    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (
            _odd_at_least(width * 0.011, 3),
            _odd_at_least(height * 0.0055, 3),
        ),
    )
    return cast(
        NDArray[np.uint8],
        cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2),
    )


def _border_score(mask: NDArray[np.uint8], candidate: _Candidate) -> float:
    roi = mask[
        candidate.y : candidate.y + candidate.height,
        candidate.x : candidate.x + candidate.width,
    ]
    if roi.size == 0:
        return 0.0
    border_y = max(2, candidate.height // 10)
    border_x = max(2, candidate.width // 16)
    border = np.zeros(roi.shape, dtype=np.bool_)
    border[:border_y, :] = True
    border[-border_y:, :] = True
    border[:, :border_x] = True
    border[:, -border_x:] = True
    return round(float(np.mean(roi[border] > 0)), 6)


def _initial_candidates(mask: NDArray[np.uint8]) -> list[_Candidate]:
    image_height, image_width = mask.shape
    image_area = image_width * image_height
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[_Candidate] = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        area_ratio = width * height / image_area
        aspect_ratio = width / height
        if 0.008 <= area_ratio <= 0.06 and 1.15 <= aspect_ratio <= 2.7:
            candidate = _Candidate(
                x=x,
                y=y,
                width=width,
                height=height,
                red_border_score=0.0,
            )
            candidates.append(replace(candidate, red_border_score=_border_score(mask, candidate)))
    return candidates


def _positive_integral(mask: NDArray[np.uint8]) -> NDArray[np.int32]:
    """Return a summed-area table for exact non-zero pixel counts."""

    binary = np.asarray(mask > 0, dtype=np.uint8)
    return np.asarray(cv2.integral(binary, sdepth=cv2.CV_32S), dtype=np.int32)


def _rectangle_positive_count(
    integral: NDArray[np.int32],
    *,
    x: int,
    y: int,
    width: int,
    height: int,
) -> int:
    right = x + width
    bottom = y + height
    return int(integral[bottom, right] - integral[y, right] - integral[bottom, x] + integral[y, x])


def _refinement_window_densities(
    integral: NDArray[np.int32],
    *,
    x: int,
    y: int,
    width: int,
    height: int,
) -> tuple[float, float]:
    """Compute the existing rectangular border/interior densities in O(1)."""

    border_y = max(2, height // 10)
    border_x = max(2, width // 16)
    interior_width = width - border_x * 2
    interior_height = height - border_y * 2
    if interior_width <= 0 or interior_height <= 0:
        raise ValueError("Refinement window must contain a non-empty interior.")
    total_count = _rectangle_positive_count(
        integral,
        x=x,
        y=y,
        width=width,
        height=height,
    )
    interior_count = _rectangle_positive_count(
        integral,
        x=x + border_x,
        y=y + border_y,
        width=interior_width,
        height=interior_height,
    )
    interior_pixels = interior_width * interior_height
    border_pixels = width * height - interior_pixels
    return (
        (total_count - interior_count) / border_pixels,
        interior_count / interior_pixels,
    )


def _row_major(candidates: Sequence[_Candidate]) -> list[list[_Candidate]]:
    by_y = sorted(candidates, key=lambda candidate: (candidate.center_y, candidate.center_x))
    return [
        sorted(by_y[offset : offset + 3], key=lambda candidate: candidate.center_x)
        for offset in (0, 3, 6)
    ]


def _search_refined_candidate(
    mask: NDArray[np.uint8],
    *,
    center_x: float,
    center_y: float,
    target_width: int,
    target_height: int,
    search_fraction_x: float = 0.15,
    search_fraction_y: float = 0.15,
    positive_integral: NDArray[np.int32] | None = None,
) -> _Candidate:
    image_height, image_width = mask.shape
    minimum_x = max(
        0,
        int(center_x - target_width / 2 - target_width * search_fraction_x),
    )
    maximum_x = min(
        image_width - target_width,
        int(center_x - target_width / 2 + target_width * search_fraction_x),
    )
    minimum_y = max(
        0,
        int(center_y - target_height / 2 - target_height * search_fraction_y),
    )
    maximum_y = min(
        image_height - target_height,
        int(center_y - target_height / 2 + target_height * search_fraction_y),
    )
    if positive_integral is None:
        positive_integral = _positive_integral(mask)
    best: tuple[float, _Candidate] | None = None
    for y in range(minimum_y, maximum_y + 1, 2):
        for x in range(minimum_x, maximum_x + 1, 2):
            border_density, interior_density = _refinement_window_densities(
                positive_integral,
                x=x,
                y=y,
                width=target_width,
                height=target_height,
            )
            score = border_density - 0.15 * interior_density
            scored = _Candidate(
                x=x,
                y=y,
                width=target_width,
                height=target_height,
                red_border_score=round(border_density, 6),
                refined_from_grid=True,
            )
            if best is None or score > best[0]:
                best = (score, scored)
    if best is None:
        raise AssertionError("Refinement search has no valid window")
    return best[1]


def _cluster_axis(values: Sequence[float], cluster_count: int) -> tuple[float, ...]:
    """Split a projected grid axis at its largest deterministic gaps."""

    if cluster_count < 1 or len(values) < cluster_count:
        raise ValueError("Not enough values to fit the expected grid axis.")
    ordered = sorted(values)
    if cluster_count == 1:
        return (statistics.median(ordered),)
    gaps = sorted(
        ((ordered[index + 1] - ordered[index], index) for index in range(len(ordered) - 1)),
        key=lambda item: (-item[0], item[1]),
    )
    cuts = sorted(index for _, index in gaps[: cluster_count - 1])
    groups: list[list[float]] = []
    start = 0
    for cut in cuts:
        groups.append(ordered[start : cut + 1])
        start = cut + 1
    groups.append(ordered[start:])
    return tuple(statistics.median(group) for group in groups)


def _recover_expected_grid(
    mask: NDArray[np.uint8],
    candidates: Sequence[_Candidate],
    *,
    expected_board_count: int,
    allow_occluded_cells: bool = False,
) -> tuple[_Candidate, ...] | None:
    """Recover only an explicitly expected contiguous row-major page variant."""

    image_height, image_width = mask.shape
    if not 1 <= expected_board_count <= MAX_BOARD_COUNT or not candidates:
        return None
    median_width = statistics.median(candidate.width for candidate in candidates)
    median_height = statistics.median(candidate.height for candidate in candidates)
    minimum_usable_border_score = 0.18 if allow_occluded_cells else 0.28
    usable = [
        candidate
        for candidate in candidates
        if candidate.red_border_score >= minimum_usable_border_score
        and 0.55 <= candidate.width / median_width <= 1.55
        and 0.55 <= candidate.height / median_height <= 1.55
        and candidate.center_x < image_width * 0.95
        and candidate.center_y < image_height * 0.85
    ]
    required_rows = (expected_board_count + 2) // 3
    required_columns = min(3, expected_board_count)
    if len(usable) < max(required_rows, required_columns, 3):
        return None
    try:
        column_centers = _cluster_axis(
            [candidate.center_x for candidate in usable],
            required_columns,
        )
        row_centers = _cluster_axis(
            [candidate.center_y for candidate in usable],
            required_rows,
        )
    except ValueError:
        return None
    target_width = int(round(statistics.median(candidate.width for candidate in usable)))
    target_height = int(round(statistics.median(candidate.height for candidate in usable)))
    assignments = [
        (
            min(
                range(required_rows),
                key=lambda index: abs(candidate.center_y - row_centers[index]),
            ),
            min(
                range(required_columns),
                key=lambda index: abs(candidate.center_x - column_centers[index]),
            ),
            candidate,
        )
        for candidate in usable
    ]
    assigned_rows = {row for row, _, _ in assignments}
    assigned_columns = {column for _, column, _ in assignments}
    if assigned_rows != set(range(required_rows)) or assigned_columns != set(
        range(required_columns)
    ):
        return None
    column_y_offsets = tuple(
        statistics.median(
            candidate.center_y - row_centers[row]
            for row, assigned_column, candidate in assignments
            if assigned_column == column
        )
        for column in range(required_columns)
    )
    row_x_offsets = tuple(
        statistics.median(
            candidate.center_x - column_centers[column]
            for assigned_row, column, candidate in assignments
            if assigned_row == row
        )
        for row in range(required_rows)
    )
    recovered: list[_Candidate] = []
    positive_integral = None if allow_occluded_cells else _positive_integral(mask)
    for position in range(expected_board_count):
        row = position // 3
        column = position % 3
        predicted_center_x = column_centers[column] + row_x_offsets[row]
        predicted_center_y = row_centers[row] + column_y_offsets[column]
        if allow_occluded_cells:
            assigned = [
                candidate
                for assigned_row, assigned_column, candidate in assignments
                if assigned_row == row and assigned_column == column
            ]
            if assigned:
                candidate = min(
                    assigned,
                    key=lambda item: (
                        abs(item.center_x - predicted_center_x)
                        + abs(item.center_y - predicted_center_y),
                        -item.red_border_score,
                    ),
                )
            else:
                candidate = _Candidate(
                    x=max(
                        0,
                        min(
                            image_width - target_width,
                            int(round(predicted_center_x - target_width / 2)),
                        ),
                    ),
                    y=max(
                        0,
                        min(
                            image_height - target_height,
                            int(round(predicted_center_y - target_height / 2)),
                        ),
                    ),
                    width=target_width,
                    height=target_height,
                    red_border_score=0.0,
                    refined_from_grid=True,
                )
            recovered.append(candidate)
            continue
        candidate = _search_refined_candidate(
            mask,
            center_x=predicted_center_x,
            center_y=predicted_center_y,
            target_width=target_width,
            target_height=target_height,
            search_fraction_x=0.15,
            search_fraction_y=0.15,
            positive_integral=positive_integral,
        )
        if candidate.red_border_score < 0.20 and not allow_occluded_cells:
            return None
        recovered.append(candidate)
    if any(
        _overlap(recovered[first], recovered[second])
        for first in range(len(recovered))
        for second in range(first + 1, len(recovered))
    ):
        return None
    return tuple(recovered)


def _refine_outliers(
    mask: NDArray[np.uint8],
    rows: list[list[_Candidate]],
) -> list[list[_Candidate]]:
    flat = [candidate for row in rows for candidate in row]
    median_width = statistics.median(candidate.width for candidate in flat)
    median_height = statistics.median(candidate.height for candidate in flat)
    column_centers = [
        statistics.median(rows[row][column].center_x for row in range(3)) for column in range(3)
    ]
    row_centers = [statistics.median(candidate.center_y for candidate in row) for row in rows]
    column_widths = [
        int(
            round(
                statistics.median(
                    rows[row][column].width
                    for row in range(3)
                    if rows[row][column].width <= median_width * 1.45
                )
            )
        )
        for column in range(3)
    ]
    row_heights = [
        int(
            round(
                statistics.median(
                    candidate.height
                    for candidate in row
                    if candidate.height <= median_height * 1.45
                )
            )
        )
        for row in rows
    ]
    refined_rows: list[list[_Candidate]] = []
    positive_integral: NDArray[np.int32] | None = None
    for row_index, row in enumerate(rows):
        refined_row: list[_Candidate] = []
        for column_index, candidate in enumerate(row):
            if candidate.width > median_width * 1.45 or candidate.height > median_height * 1.45:
                if positive_integral is None:
                    positive_integral = _positive_integral(mask)
                candidate = _search_refined_candidate(
                    mask,
                    center_x=column_centers[column_index],
                    center_y=row_centers[row_index],
                    target_width=column_widths[column_index],
                    target_height=row_heights[row_index],
                    positive_integral=positive_integral,
                )
            refined_row.append(candidate)
        refined_rows.append(refined_row)
    return refined_rows


def _candidate_quad(mask: NDArray[np.uint8], candidate: _Candidate) -> Quad:
    roi = mask[
        candidate.y : candidate.y + candidate.height,
        candidate.x : candidate.x + candidate.width,
    ]
    y_values, x_values = np.nonzero(roi)
    if len(x_values) < 4:
        return (
            Point(candidate.x, candidate.y),
            Point(candidate.x + candidate.width - 1, candidate.y),
            Point(
                candidate.x + candidate.width - 1,
                candidate.y + candidate.height - 1,
            ),
            Point(candidate.x, candidate.y + candidate.height - 1),
        )
    points = np.column_stack((x_values + candidate.x, y_values + candidate.y)).astype(np.int32)
    sums = points[:, 0] + points[:, 1]
    differences = points[:, 0] - points[:, 1]
    return (
        Point(*map(int, points[int(np.argmin(sums))])),
        Point(*map(int, points[int(np.argmax(differences))])),
        Point(*map(int, points[int(np.argmax(sums))])),
        Point(*map(int, points[int(np.argmin(differences))])),
    )


def _overlap(first: _Candidate, second: _Candidate) -> bool:
    return not (
        first.x + first.width <= second.x
        or second.x + second.width <= first.x
        or first.y + first.height <= second.y
        or second.y + second.height <= first.y
    )


def _page_quad(
    boards: Sequence[BoardDetection],
    image_width: int,
    image_height: int,
) -> Quad:
    x_values = [point.x for board in boards for point in board.quad]
    y_values = [point.y for board in boards for point in board.quad]
    margin_x = int(round(image_width * 0.02))
    margin_y = int(round(image_height * 0.02))
    left = max(0, min(x_values) - margin_x)
    top = max(0, min(y_values) - margin_y)
    right = min(image_width - 1, max(x_values) + margin_x)
    bottom = min(image_height - 1, max(y_values) + margin_y)
    return (
        Point(left, top),
        Point(right, top),
        Point(right, bottom),
        Point(left, bottom),
    )


def _candidate_bounding_quad(candidate: _Candidate) -> Quad:
    """Use the fitted lattice window when an occluder removed border evidence."""

    return (
        Point(candidate.x, candidate.y),
        Point(candidate.x + candidate.width - 1, candidate.y),
        Point(candidate.x + candidate.width - 1, candidate.y + candidate.height - 1),
        Point(candidate.x, candidate.y + candidate.height - 1),
    )


class ClassicalPageBoardDetector:
    """HSV/contour detector for the explicitly supported red-frame 3 Ã— 3 page."""

    version = DETECTOR_VERSION

    def detect(
        self,
        rgb_image: NDArray[np.uint8],
        *,
        expected_board_count: int = EXPECTED_BOARD_COUNT,
        allow_grid_recovery: bool = False,
        allow_occluded_grid_recovery: bool = False,
    ) -> DetectionResult:
        if rgb_image.ndim != 3 or rgb_image.shape[2] != 3 or rgb_image.dtype != np.uint8:
            raise GeometryDetectionError(
                "PAGE_DETECTOR_INVALID_IMAGE",
                "Detector input must be an RGB uint8 image.",
            )
        if not 1 <= expected_board_count <= MAX_BOARD_COUNT:
            raise GeometryDetectionError(
                "PAGE_DETECTOR_EXPECTED_BOARD_COUNT_INVALID",
                "Expected board count must be between 1 and 9.",
            )
        image_height, image_width = rgb_image.shape[:2]
        mask = _red_mask(rgb_image)
        candidates = _initial_candidates(mask)
        if len(candidates) != expected_board_count:
            recovered = (
                _recover_expected_grid(
                    mask,
                    candidates,
                    expected_board_count=expected_board_count,
                    allow_occluded_cells=allow_occluded_grid_recovery,
                )
                if allow_grid_recovery
                else None
            )
            if recovered is not None:
                return self._detected_recovered(
                    mask,
                    recovered,
                    image_width=image_width,
                    image_height=image_height,
                    candidate_count=len(candidates),
                )
            confidence = round(
                min(len(candidates), expected_board_count) / expected_board_count,
                6,
            )
            return DetectionResult(
                status="needs_review",
                image_width=image_width,
                image_height=image_height,
                candidate_count=len(candidates),
                page_quad=None,
                boards=(),
                confidence=confidence,
                confidence_components={"candidateCount": confidence},
                review_reasons=("BOARD_CANDIDATE_COUNT",),
            )

        if expected_board_count != EXPECTED_BOARD_COUNT:
            recovered = _recover_expected_grid(
                mask,
                candidates,
                expected_board_count=expected_board_count,
                allow_occluded_cells=allow_occluded_grid_recovery,
            )
            if recovered is None:
                return DetectionResult(
                    status="needs_review",
                    image_width=image_width,
                    image_height=image_height,
                    candidate_count=len(candidates),
                    page_quad=None,
                    boards=(),
                    confidence=0.0,
                    confidence_components={"candidateCount": 1.0},
                    review_reasons=("BOARD_EXPECTED_GRID_RECOVERY_FAILED",),
                )
            return self._detected_recovered(
                mask,
                recovered,
                image_width=image_width,
                image_height=image_height,
                candidate_count=len(candidates),
            )

        rows = _refine_outliers(mask, _row_major(candidates))
        ordered = [candidate for row in rows for candidate in row]
        median_width = statistics.median(candidate.width for candidate in ordered)
        median_height = statistics.median(candidate.height for candidate in ordered)
        width_ratio = max(candidate.width for candidate in ordered) / median_width
        minimum_width_ratio = min(candidate.width for candidate in ordered) / median_width
        height_ratio = max(candidate.height for candidate in ordered) / median_height
        minimum_height_ratio = min(candidate.height for candidate in ordered) / median_height
        row_spread = max(
            (max(item.center_y for item in row) - min(item.center_y for item in row))
            / median_height
            for row in rows
        )
        column_spread = max(
            (
                max(rows[row][column].center_x for row in range(3))
                - min(rows[row][column].center_x for row in range(3))
            )
            / median_width
            for column in range(3)
        )
        overlaps = any(
            _overlap(ordered[first], ordered[second])
            for first in range(len(ordered))
            for second in range(first + 1, len(ordered))
        )
        reasons: list[str] = []
        if (
            width_ratio > 1.5
            or minimum_width_ratio < 0.65
            or height_ratio > 1.5
            or minimum_height_ratio < 0.65
        ):
            reasons.append("BOARD_GRID_SIZE_INCONSISTENT")
        if row_spread > 0.45:
            reasons.append("BOARD_GRID_ROW_ALIGNMENT")
        if column_spread > 0.18:
            reasons.append("BOARD_GRID_COLUMN_ALIGNMENT")
        if overlaps:
            reasons.append("BOARD_GRID_OVERLAP")

        size_consistency = max(
            0.0,
            1.0
            - (
                abs(width_ratio - 1)
                + abs(1 - minimum_width_ratio)
                + abs(height_ratio - 1)
                + abs(1 - minimum_height_ratio)
            )
            / 2,
        )
        row_alignment = max(0.0, 1.0 - row_spread / 0.45)
        column_alignment = max(0.0, 1.0 - column_spread / 0.18)
        border_evidence = statistics.mean(candidate.red_border_score for candidate in ordered)
        refinement_stability = 1.0 - sum(candidate.refined_from_grid for candidate in ordered) / 18
        components = {
            "borderEvidence": round(border_evidence, 6),
            "columnAlignment": round(column_alignment, 6),
            "refinementStability": round(refinement_stability, 6),
            "rowAlignment": round(row_alignment, 6),
            "sizeConsistency": round(size_consistency, 6),
        }
        confidence = round(statistics.mean(components.values()), 6)
        if reasons and allow_grid_recovery:
            recovered = _recover_expected_grid(
                mask,
                candidates,
                expected_board_count=expected_board_count,
                allow_occluded_cells=allow_occluded_grid_recovery,
            )
            if recovered is not None:
                return self._detected_recovered(
                    mask,
                    recovered,
                    image_width=image_width,
                    image_height=image_height,
                    candidate_count=len(candidates),
                )
        if reasons:
            return DetectionResult(
                status="needs_review",
                image_width=image_width,
                image_height=image_height,
                candidate_count=len(candidates),
                page_quad=None,
                boards=(),
                confidence=confidence,
                confidence_components=components,
                review_reasons=tuple(reasons),
            )

        boards = tuple(
            BoardDetection(
                position_index=index,
                quad=_candidate_quad(mask, candidate),
                bounding_box=(
                    candidate.x,
                    candidate.y,
                    candidate.width,
                    candidate.height,
                ),
                red_border_score=candidate.red_border_score,
                refined_from_grid=candidate.refined_from_grid,
            )
            for index, candidate in enumerate(ordered)
        )
        return DetectionResult(
            status="detected",
            image_width=image_width,
            image_height=image_height,
            candidate_count=len(candidates),
            page_quad=_page_quad(boards, image_width, image_height),
            boards=boards,
            confidence=confidence,
            confidence_components=components,
            review_reasons=(),
        )

    def _detected_recovered(
        self,
        mask: NDArray[np.uint8],
        candidates: Sequence[_Candidate],
        *,
        image_width: int,
        image_height: int,
        candidate_count: int,
    ) -> DetectionResult:
        boards = tuple(
            BoardDetection(
                position_index=index,
                quad=(
                    _candidate_quad(mask, candidate)
                    if candidate.red_border_score >= 0.20
                    else _candidate_bounding_quad(candidate)
                ),
                bounding_box=(
                    candidate.x,
                    candidate.y,
                    candidate.width,
                    candidate.height,
                ),
                red_border_score=candidate.red_border_score,
                refined_from_grid=True,
            )
            for index, candidate in enumerate(candidates)
        )
        border_evidence = statistics.mean(candidate.red_border_score for candidate in candidates)
        expected_evidence = min(1.0, candidate_count / len(candidates))
        components = {
            "borderEvidence": round(border_evidence, 6),
            "expectedCountEvidence": round(expected_evidence, 6),
            "gridRecovery": 1.0,
        }
        return DetectionResult(
            status="detected",
            image_width=image_width,
            image_height=image_height,
            candidate_count=candidate_count,
            page_quad=_page_quad(boards, image_width, image_height),
            boards=boards,
            confidence=round(statistics.mean(components.values()), 6),
            confidence_components=components,
            review_reasons=(),
        )


@dataclass(frozen=True, slots=True)
class CorpusDetection:
    source_checksum_sha256: str
    normalized_relative_path: str
    overlay_relative_path: str
    overlay_checksum_sha256: str
    result: DetectionResult

    def to_dict(self) -> dict[str, object]:
        return {
            "normalizedRelativePath": self.normalized_relative_path,
            "overlayChecksumSha256": self.overlay_checksum_sha256,
            "overlayRelativePath": self.overlay_relative_path,
            "result": self.result.to_dict(),
            "sourceChecksumSha256": self.source_checksum_sha256,
        }


@dataclass(frozen=True, slots=True)
class CorpusDetectionReport:
    normalization_report_sha256: str
    detections: tuple[CorpusDetection, ...]

    def to_dict(self) -> dict[str, object]:
        detected_count = sum(detection.result.status == "detected" for detection in self.detections)
        return {
            "detectedCount": detected_count,
            "detections": [detection.to_dict() for detection in self.detections],
            "detectorVersion": DETECTOR_VERSION,
            "imageCount": len(self.detections),
            "needsReviewCount": len(self.detections) - detected_count,
            "normalizationReportSha256": self.normalization_report_sha256,
            "numpyVersion": np.__version__,
            "opencvVersion": cv2.__version__,
            "schemaVersion": 1,
            "status": ("detected" if detected_count == len(self.detections) else "needs_review"),
        }

    def to_json_bytes(self) -> bytes:
        return (
            json.dumps(
                self.to_dict(),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise GeometryDetectionError(
            "PAGE_DETECTION_NORMALIZATION_REPORT_INVALID",
            f"{label} must be an object.",
        )
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise GeometryDetectionError(
            "PAGE_DETECTION_NORMALIZATION_REPORT_INVALID",
            f"{label} must be an array.",
        )
    return cast(Sequence[object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise GeometryDetectionError(
            "PAGE_DETECTION_NORMALIZATION_REPORT_INVALID",
            f"{label} must be a non-empty string.",
        )
    return value


def _safe_artifact_path(root: Path, value: object, label: str) -> tuple[str, Path]:
    text = _text(value, label)
    relative = PurePosixPath(text)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise GeometryDetectionError(
            "PAGE_DETECTION_UNSAFE_ARTIFACT_PATH",
            f"{label} must be a safe relative POSIX path.",
        )
    try:
        resolved = (root / Path(*relative.parts)).resolve(strict=True)
    except OSError as error:
        raise GeometryDetectionError(
            "PAGE_DETECTION_NORMALIZED_IMAGE_UNREADABLE",
            f"{label} cannot be resolved.",
        ) from error
    if not resolved.is_relative_to(root):
        raise GeometryDetectionError(
            "PAGE_DETECTION_UNSAFE_ARTIFACT_PATH",
            f"{label} escapes its artifact root.",
        )
    return text, resolved


def _encode_overlay(
    rgb_image: NDArray[np.uint8],
    result: DetectionResult,
) -> bytes:
    overlay = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)
    if result.page_quad is not None:
        page_points = np.array(
            [[point.x, point.y] for point in result.page_quad],
            dtype=np.int32,
        )
        cv2.polylines(overlay, [page_points], True, (0, 255, 0), 3)
    for board in result.boards:
        points = np.array(
            [[point.x, point.y] for point in board.quad],
            dtype=np.int32,
        )
        color = (0, 165, 255) if board.refined_from_grid else (0, 255, 0)
        cv2.polylines(overlay, [points], True, color, 3)
        cv2.putText(
            overlay,
            str(board.position_index),
            (board.bounding_box[0], max(20, board.bounding_box[1] - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            color,
            2,
            cv2.LINE_AA,
        )
    if result.status == "needs_review":
        cv2.putText(
            overlay,
            ",".join(result.review_reasons),
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
    encoded, buffer = cv2.imencode(
        ".png",
        overlay,
        [cv2.IMWRITE_PNG_COMPRESSION, 6],
    )
    if not encoded:
        raise GeometryDetectionError(
            "PAGE_DETECTION_OVERLAY_ENCODE_FAILED",
            "Diagnostic overlay cannot be encoded.",
        )
    return bytes(buffer)


def _write_immutable(path: Path, content: bytes) -> None:
    if path.exists():
        try:
            existing = path.read_bytes()
        except OSError as error:
            raise GeometryDetectionError(
                "PAGE_DETECTION_ARTIFACT_UNREADABLE",
                "Existing geometry artifact cannot be read.",
            ) from error
        if existing != content:
            raise GeometryDetectionError(
                "PAGE_DETECTION_ARTIFACT_COLLISION",
                "Existing geometry artifact has different content.",
            )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    except OSError as error:
        raise GeometryDetectionError(
            "PAGE_DETECTION_ARTIFACT_WRITE_FAILED",
            "Geometry artifact cannot be written.",
        ) from error
    finally:
        if temporary.exists():
            temporary.unlink()


def expected_board_counts_from_manifest(path: Path) -> dict[str, int]:
    """Load the explicit per-source page shape used to distinguish missing boards."""

    try:
        value: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GeometryDetectionError(
            "PAGE_DETECTION_CORPUS_MANIFEST_INVALID",
            "Corpus manifest cannot be read.",
        ) from error
    manifest = _mapping(value, "corpusManifest")
    result: dict[str, int] = {}
    for index, image_value in enumerate(_sequence(manifest.get("images"), "corpusManifest.images")):
        image = _mapping(image_value, f"corpusManifest.images[{index}]")
        checksum = _text(
            image.get("sha256"),
            f"corpusManifest.images[{index}].sha256",
        )
        board_count = image.get("expectedBoardCount")
        if (
            not isinstance(board_count, int)
            or isinstance(board_count, bool)
            or not 1 <= board_count <= MAX_BOARD_COUNT
        ):
            raise GeometryDetectionError(
                "PAGE_DETECTION_EXPECTED_BOARD_COUNT_INVALID",
                "Every corpus image must declare expectedBoardCount between 1 and 9.",
            )
        if checksum in result:
            raise GeometryDetectionError(
                "PAGE_DETECTION_CORPUS_MANIFEST_INVALID",
                "Corpus manifest contains a duplicate source checksum.",
            )
        result[checksum] = board_count
    return result


def detect_normalized_corpus(
    normalization_report_path: Path,
    normalization_root: Path,
    artifact_root: Path,
    *,
    detector: PageBoardDetector | None = None,
    expected_board_counts: Mapping[str, int] | None = None,
) -> CorpusDetectionReport:
    """Run the detector over a verified normalization report."""

    try:
        report_bytes = normalization_report_path.read_bytes()
        report_value: Any = json.loads(report_bytes)
    except (OSError, json.JSONDecodeError) as error:
        raise GeometryDetectionError(
            "PAGE_DETECTION_NORMALIZATION_REPORT_INVALID",
            "Normalization report cannot be read.",
        ) from error
    report = _mapping(report_value, "normalizationReport")
    if report.get("normalizationVersion") != "image-normalization-v1":
        raise GeometryDetectionError(
            "PAGE_DETECTION_NORMALIZATION_VERSION_UNSUPPORTED",
            "Normalization report version is not supported.",
        )
    if report.get("status") != "clean":
        raise GeometryDetectionError(
            "PAGE_DETECTION_NORMALIZATION_NOT_CLEAN",
            "Normalization report must be clean before geometry.",
        )
    try:
        normalization_base = normalization_root.resolve(strict=True)
    except OSError as error:
        raise GeometryDetectionError(
            "PAGE_DETECTION_NORMALIZATION_ROOT_NOT_FOUND",
            "Normalization artifact root does not exist.",
        ) from error
    if not normalization_base.is_dir():
        raise GeometryDetectionError(
            "PAGE_DETECTION_NORMALIZATION_ROOT_NOT_DIRECTORY",
            "Normalization artifact root must be a directory.",
        )
    geometry_base = artifact_root.resolve()
    if geometry_base == normalization_base or geometry_base.is_relative_to(normalization_base):
        raise GeometryDetectionError(
            "PAGE_DETECTION_OUTPUT_IN_NORMALIZATION_ROOT",
            "Geometry artifacts must use a separate root.",
        )
    implementation = detector or ClassicalPageBoardDetector()
    detections: list[CorpusDetection] = []
    for index, image_value in enumerate(_sequence(report.get("images"), "images")):
        image = _mapping(image_value, f"images[{index}]")
        source_checksum = _text(
            image.get("sourceChecksumSha256"),
            f"images[{index}].sourceChecksumSha256",
        )
        relative_path, normalized_path = _safe_artifact_path(
            normalization_base,
            image.get("normalizedRelativePath"),
            f"images[{index}].normalizedRelativePath",
        )
        expected_checksum = _text(
            image.get("normalizedChecksumSha256"),
            f"images[{index}].normalizedChecksumSha256",
        )
        try:
            normalized_bytes = normalized_path.read_bytes()
        except OSError as error:
            raise GeometryDetectionError(
                "PAGE_DETECTION_NORMALIZED_IMAGE_UNREADABLE",
                "Normalized image cannot be read.",
            ) from error
        if hashlib.sha256(normalized_bytes).hexdigest() != expected_checksum:
            raise GeometryDetectionError(
                "PAGE_DETECTION_NORMALIZED_CHECKSUM_MISMATCH",
                "Normalized image checksum differs from its report.",
            )
        bgr = cv2.imdecode(
            np.frombuffer(normalized_bytes, dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )
        if bgr is None:
            raise GeometryDetectionError(
                "PAGE_DETECTION_NORMALIZED_DECODE_FAILED",
                "Normalized image cannot be decoded.",
            )
        rgb = cast(NDArray[np.uint8], cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        expected_board_count = (
            expected_board_counts.get(source_checksum)
            if expected_board_counts is not None
            else EXPECTED_BOARD_COUNT
        )
        if expected_board_count is None:
            raise GeometryDetectionError(
                "PAGE_DETECTION_EXPECTATION_MISSING",
                "Corpus expectations do not contain the normalized source image.",
            )
        result = implementation.detect(
            rgb,
            expected_board_count=expected_board_count,
            allow_grid_recovery=expected_board_counts is not None,
        )
        overlay_bytes = _encode_overlay(rgb, result)
        overlay_relative = PurePosixPath(
            implementation.version,
            source_checksum[:2],
            source_checksum,
            "overlay.png",
        ).as_posix()
        overlay_path = geometry_base / Path(*PurePosixPath(overlay_relative).parts)
        _write_immutable(overlay_path, overlay_bytes)
        detections.append(
            CorpusDetection(
                source_checksum_sha256=source_checksum,
                normalized_relative_path=relative_path,
                overlay_relative_path=overlay_relative,
                overlay_checksum_sha256=hashlib.sha256(overlay_bytes).hexdigest(),
                result=result,
            )
        )
    return CorpusDetectionReport(
        normalization_report_sha256=hashlib.sha256(report_bytes).hexdigest(),
        detections=tuple(detections),
    )
