"""Global bright-component detection and explicit assignment to a 5 x 3 lattice."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Literal, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from .rectification import BOARD_COLUMNS, BOARD_HEIGHT, BOARD_ROWS, BOARD_WIDTH
from .symbol_grid_refinement import SymbolCenter, SymbolGridRefinementError

LOCATOR_VERSION = "global-bright-component-lattice-assignment-v1"
MIN_COMPONENT_AREA = 180
MAX_COMPONENT_AREA = 6000
MIN_COMPONENT_SIZE = 14
MAX_COMPONENT_WIDTH = 82
MAX_COMPONENT_HEIGHT = 92
MIN_COLUMN_SPACING_PX = 55.0
MAX_COLUMN_SPACING_PX = 110.0
MIN_ROW_SPACING_PX = 55.0
MAX_ROW_SPACING_PX = 125.0
COLUMN_MATCH_TOLERANCE_PX = 22.0
ROW_MATCH_TOLERANCE_PX = 25.0
SLOT_COLUMN_TOLERANCE_PX = 25.0
SLOT_ROW_TOLERANCE_PX = 36.0
MIN_AXIS_COMPONENT_MATCHES = 8
MIN_ASSIGNED_COMPONENTS = 10
UNSUPPORTED_SLOT_CONFIDENCE_SCALE = 0.35


@dataclass(frozen=True, slots=True)
class GlobalSymbolCandidate:
    candidate_index: int
    x: float
    y: float
    width: int
    height: int
    area: int
    weight: float
    touches_border: bool
    left: int | None = None
    top: int | None = None
    core_left: float | None = None
    core_top: float | None = None
    core_width: float | None = None
    core_height: float | None = None

    def to_dict(self) -> dict[str, int | float | bool]:
        return {
            "area": self.area,
            "candidateIndex": self.candidate_index,
            "height": self.height,
            "touchesBorder": self.touches_border,
            "weight": round(self.weight, 6),
            "width": self.width,
            "x": round(self.x, 4),
            "y": round(self.y, 4),
        }


@dataclass(frozen=True, slots=True)
class GlobalSymbolLattice:
    status: Literal["assigned", "fallback"]
    candidates: tuple[GlobalSymbolCandidate, ...]
    centers: tuple[SymbolCenter, ...]
    column_bases: tuple[float, ...] | None
    row_bases: tuple[float, ...] | None
    assigned_candidate_indices: tuple[int | None, ...]
    assigned_candidate_count: int
    fallback_reason: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "assignedCandidateCount": self.assigned_candidate_count,
            "assignedCandidateIndices": list(self.assigned_candidate_indices),
            "candidateCount": len(self.candidates),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "centers": [center.to_dict() for center in self.centers],
            "columnBases": (
                None
                if self.column_bases is None
                else [round(value, 4) for value in self.column_bases]
            ),
            "fallbackReason": self.fallback_reason,
            "locatorVersion": LOCATOR_VERSION,
            "rowBases": (
                None if self.row_bases is None else [round(value, 4) for value in self.row_bases]
            ),
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class _AxisLattice:
    bases: tuple[float, ...]


def _validate_board(board_rgb: NDArray[np.uint8]) -> None:
    if board_rgb.shape != (BOARD_HEIGHT, BOARD_WIDTH, 3) or board_rgb.dtype != np.uint8:
        raise SymbolGridRefinementError(
            "GLOBAL_SYMBOL_LATTICE_BOARD_INVALID",
            "Expanded board must be RGB uint8 500 x 300.",
        )


def _bright_components(
    board_rgb: NDArray[np.uint8],
) -> tuple[GlobalSymbolCandidate, ...]:
    hsv = cv2.cvtColor(board_rgb, cv2.COLOR_RGB2HSV)
    value = hsv[:, :, 2]
    threshold = max(115.0, float(np.percentile(value, 67.0)))
    mask = np.where(value >= threshold, 255, 0).astype(np.uint8)
    mask = cast(
        NDArray[np.uint8],
        cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), dtype=np.uint8)),
    )
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    raw: list[
        tuple[float, float, int, int, int, float, bool, int, int, float, float, float, float]
    ] = []
    for label in range(1, count):
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        width = int(stats[label, cv2.CC_STAT_WIDTH])
        height = int(stats[label, cv2.CC_STAT_HEIGHT])
        area = int(stats[label, cv2.CC_STAT_AREA])
        if not (
            MIN_COMPONENT_AREA <= area <= MAX_COMPONENT_AREA
            and MIN_COMPONENT_SIZE <= width <= MAX_COMPONENT_WIDTH
            and MIN_COMPONENT_SIZE <= height <= MAX_COMPONENT_HEIGHT
        ):
            continue
        fill_fraction = area / float(width * height)
        if not 0.18 <= fill_fraction <= 0.96:
            continue
        touches_border = (
            x <= 1 or y <= 1 or x + width >= BOARD_WIDTH - 1 or y + height >= BOARD_HEIGHT - 1
        )
        weight = min(1.0, area / 1800.0)
        if touches_border:
            weight *= 0.65
        component_y, component_x = np.where(labels == label)
        core_left = float(np.percentile(component_x, 5.0))
        core_right = float(np.percentile(component_x, 95.0))
        core_top = float(np.percentile(component_y, 5.0))
        core_bottom = float(np.percentile(component_y, 95.0))
        raw.append(
            (
                float(centroids[label, 0]),
                float(centroids[label, 1]),
                width,
                height,
                area,
                weight,
                touches_border,
                x,
                y,
                core_left,
                core_top,
                max(1.0, core_right - core_left + 1.0),
                max(1.0, core_bottom - core_top + 1.0),
            )
        )
    raw.sort(key=lambda value: (value[1], value[0], value[4]))
    return tuple(
        GlobalSymbolCandidate(
            candidate_index=index,
            x=value[0],
            y=value[1],
            width=value[2],
            height=value[3],
            area=value[4],
            weight=value[5],
            touches_border=value[6],
            left=value[7],
            top=value[8],
            core_left=value[9],
            core_top=value[10],
            core_width=value[11],
            core_height=value[12],
        )
        for index, value in enumerate(raw)
    )


def detect_global_symbol_candidates(
    board_rgb: NDArray[np.uint8],
) -> tuple[GlobalSymbolCandidate, ...]:
    """Return the versioned global component set without assigning lattice slots."""

    _validate_board(board_rgb)
    return _bright_components(board_rgb)


def _axis_lattice(
    candidates: tuple[GlobalSymbolCandidate, ...],
    *,
    axis: Literal["x", "y"],
    count: int,
    limit: int,
    minimum_spacing: float,
    maximum_spacing: float,
    tolerance: float,
    maximum_support_per_line: int,
) -> _AxisLattice | None:
    best_key: tuple[float, float, float] | None = None
    best_selected: list[list[tuple[float, float]]] | None = None
    for spacing_step in range(int(minimum_spacing * 2), int(maximum_spacing * 2) + 1):
        spacing = spacing_step / 2.0
        maximum_start = limit - 1.0 - (count - 1) * spacing
        if maximum_start <= 0:
            continue
        for start_step in range(int(maximum_start * 2) + 1):
            start = start_step / 2.0
            matched: list[list[tuple[float, float]]] = [[] for _ in range(count)]
            for candidate in candidates:
                coordinate = candidate.x if axis == "x" else candidate.y
                line_index = int(round((coordinate - start) / spacing))
                if not 0 <= line_index < count:
                    continue
                distance = abs(coordinate - (start + line_index * spacing))
                if distance <= tolerance:
                    matched[line_index].append((coordinate, candidate.weight))
            if any(not line for line in matched):
                continue
            selected = [
                sorted(
                    line,
                    key=lambda value: abs(value[0] - (start + line_index * spacing)),
                )[:maximum_support_per_line]
                for line_index, line in enumerate(matched)
            ]
            match_count = sum(len(line) for line in selected)
            if match_count < MIN_AXIS_COMPONENT_MATCHES:
                continue
            distance_penalty = sum(
                abs(coordinate - (start + line_index * spacing)) / tolerance
                for line_index, line in enumerate(selected)
                for coordinate, _ in line
            )
            support_weight = sum(weight for line in selected for _, weight in line)
            score = match_count * 4.0 + support_weight - distance_penalty
            key = (score, -distance_penalty, -spacing)
            if best_key is None or key > best_key:
                best_key = key
                best_selected = selected
    if best_selected is None:
        return None
    bases = tuple(statistics.median(value for value, _ in line) for line in best_selected)
    spacings = tuple(bases[index + 1] - bases[index] for index in range(count - 1))
    if any(spacing < minimum_spacing or spacing > maximum_spacing for spacing in spacings):
        return None
    return _AxisLattice(bases=bases)


def _normalise_plane(values: NDArray[np.float32]) -> NDArray[np.float32]:
    low, high = np.percentile(values, (35.0, 95.0))
    span = float(high - low)
    if span < 1e-6:
        return np.zeros_like(values)
    return cast(NDArray[np.float32], np.clip((values - low) / span, 0.0, 1.0))


def _refine_center(
    board_rgb: NDArray[np.uint8],
    *,
    row_index: int,
    column_index: int,
    expected_x: float,
    expected_y: float,
    half_width: float,
    half_height: float,
    has_component_support: bool,
) -> SymbolCenter:
    left = max(0, int(round(expected_x - half_width)))
    right = min(BOARD_WIDTH, int(round(expected_x + half_width)))
    top = max(0, int(round(expected_y - half_height)))
    bottom = min(BOARD_HEIGHT, int(round(expected_y + half_height)))
    patch = board_rgb[top:bottom, left:right]
    lab = cv2.cvtColor(patch, cv2.COLOR_RGB2LAB).astype(np.float32)
    gray = cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY).astype(np.float32)
    height, width = gray.shape
    border_size = max(4, min(8, min(height, width) // 8))
    border_mask = np.zeros((height, width), dtype=np.uint8)
    border_mask[:border_size, :] = 1
    border_mask[-border_size:, :] = 1
    border_mask[:, :border_size] = 1
    border_mask[:, -border_size:] = 1
    background = np.median(lab[border_mask == 1], axis=0)
    colour_distance = cast(
        NDArray[np.float32],
        np.linalg.norm(lab - background, axis=2).astype(np.float32),
    )
    gradient_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gradient_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    gradient = cast(NDArray[np.float32], cv2.magnitude(gradient_x, gradient_y))
    saliency = (
        0.78 * _normalise_plane(colour_distance) + 0.22 * _normalise_plane(gradient)
    ).astype(np.float32)

    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    local_expected_x = expected_x - left
    local_expected_y = expected_y - top
    sigma_x = width * 0.36
    sigma_y = height * 0.36
    prior = np.exp(
        -0.5 * (((xx - local_expected_x) / sigma_x) ** 2 + ((yy - local_expected_y) / sigma_y) ** 2)
    ).astype(np.float32)
    threshold = float(np.percentile(saliency, 62.0))
    foreground = saliency >= max(0.28, threshold)
    weights = np.where(foreground, saliency * prior, 0.0).astype(np.float32)
    mass = float(weights.sum())
    if mass <= 1e-6:
        local_x = local_expected_x
        local_y = local_expected_y
        confidence = 0.0
    else:
        local_x = float((weights * xx).sum() / mass)
        local_y = float((weights * yy).sum() / mass)
        distance = math.hypot(
            local_x - local_expected_x,
            local_y - local_expected_y,
        )
        distance_score = max(0.0, 1.0 - distance / (min(width, height) * 0.45))
        contrast = float(
            np.clip(
                np.percentile(saliency, 90.0) - np.percentile(saliency, 45.0),
                0.0,
                1.0,
            )
        )
        foreground_fraction = float(np.count_nonzero(foreground) / foreground.size)
        fraction_score = max(
            0.0,
            1.0 - abs(foreground_fraction - 0.30) / 0.30,
        )
        confidence = float(
            np.clip(
                0.50 * contrast + 0.35 * distance_score + 0.15 * fraction_score,
                0.0,
                1.0,
            )
        )
    if not has_component_support:
        confidence *= UNSUPPORTED_SLOT_CONFIDENCE_SCALE
    return SymbolCenter(
        row_index=row_index,
        column_index=column_index,
        x=left + local_x,
        y=top + local_y,
        confidence=confidence,
    )


def refine_global_symbol_center(
    board_rgb: NDArray[np.uint8],
    *,
    row_index: int,
    column_index: int,
    expected_x: float,
    expected_y: float,
    half_width: float,
    half_height: float,
    has_component_support: bool,
) -> SymbolCenter:
    """Refine one globally assigned slot using the historical saliency calculation."""

    _validate_board(board_rgb)
    return _refine_center(
        board_rgb,
        row_index=row_index,
        column_index=column_index,
        expected_x=expected_x,
        expected_y=expected_y,
        half_width=half_width,
        half_height=half_height,
        has_component_support=has_component_support,
    )


def _assign_candidates(
    candidates: tuple[GlobalSymbolCandidate, ...],
    column_bases: tuple[float, ...],
    row_bases: tuple[float, ...],
) -> tuple[int | None, ...]:
    selected: dict[tuple[int, int], tuple[float, int]] = {}
    column_array = np.asarray(column_bases, dtype=np.float64)
    row_array = np.asarray(row_bases, dtype=np.float64)
    for candidate in candidates:
        column = int(np.argmin(np.abs(column_array - candidate.x)))
        row = int(np.argmin(np.abs(row_array - candidate.y)))
        x_distance = abs(candidate.x - column_bases[column])
        y_distance = abs(candidate.y - row_bases[row])
        if x_distance > SLOT_COLUMN_TOLERANCE_PX or y_distance > SLOT_ROW_TOLERANCE_PX:
            continue
        score = (
            x_distance / SLOT_COLUMN_TOLERANCE_PX
            + y_distance / SLOT_ROW_TOLERANCE_PX
            - 0.30 * candidate.weight
        )
        slot = (row, column)
        existing = selected.get(slot)
        if existing is None or (score, candidate.candidate_index) < existing:
            selected[slot] = (score, candidate.candidate_index)
    return tuple(
        (selected[(row, column)][1] if (row, column) in selected else None)
        for row in range(BOARD_ROWS)
        for column in range(BOARD_COLUMNS)
    )


def _fallback(
    candidates: tuple[GlobalSymbolCandidate, ...],
    reason: str,
    *,
    centers: tuple[SymbolCenter, ...] = (),
    column_bases: tuple[float, ...] | None = None,
    row_bases: tuple[float, ...] | None = None,
    assigned_candidate_indices: tuple[int | None, ...] = (),
) -> GlobalSymbolLattice:
    return GlobalSymbolLattice(
        status="fallback",
        candidates=candidates,
        centers=centers,
        column_bases=column_bases,
        row_bases=row_bases,
        assigned_candidate_indices=assigned_candidate_indices,
        assigned_candidate_count=sum(
            candidate_index is not None for candidate_index in assigned_candidate_indices
        ),
        fallback_reason=reason,
    )


def locate_global_symbol_lattice(
    board_rgb: NDArray[np.uint8],
) -> GlobalSymbolLattice:
    """Detect candidates globally and assign at most one candidate to every slot."""

    candidates = detect_global_symbol_candidates(board_rgb)
    if len(candidates) < MIN_AXIS_COMPONENT_MATCHES:
        return _fallback(candidates, "GLOBAL_SYMBOL_LATTICE_INSUFFICIENT_COMPONENTS")
    column_lattice = _axis_lattice(
        candidates,
        axis="x",
        count=BOARD_COLUMNS,
        limit=BOARD_WIDTH,
        minimum_spacing=MIN_COLUMN_SPACING_PX,
        maximum_spacing=MAX_COLUMN_SPACING_PX,
        tolerance=COLUMN_MATCH_TOLERANCE_PX,
        maximum_support_per_line=BOARD_ROWS,
    )
    row_lattice = _axis_lattice(
        candidates,
        axis="y",
        count=BOARD_ROWS,
        limit=BOARD_HEIGHT,
        minimum_spacing=MIN_ROW_SPACING_PX,
        maximum_spacing=MAX_ROW_SPACING_PX,
        tolerance=ROW_MATCH_TOLERANCE_PX,
        maximum_support_per_line=BOARD_COLUMNS,
    )
    if column_lattice is None or row_lattice is None:
        return _fallback(candidates, "GLOBAL_SYMBOL_LATTICE_AXIS_ASSIGNMENT_FAILED")
    assigned = _assign_candidates(
        candidates,
        column_lattice.bases,
        row_lattice.bases,
    )
    column_spacing = statistics.median(
        column_lattice.bases[index + 1] - column_lattice.bases[index]
        for index in range(BOARD_COLUMNS - 1)
    )
    row_spacing = statistics.median(
        row_lattice.bases[index + 1] - row_lattice.bases[index] for index in range(BOARD_ROWS - 1)
    )
    centers = tuple(
        _refine_center(
            board_rgb,
            row_index=row,
            column_index=column,
            expected_x=column_lattice.bases[column],
            expected_y=row_lattice.bases[row],
            half_width=column_spacing * 0.44,
            half_height=row_spacing * 0.44,
            has_component_support=assigned[row * BOARD_COLUMNS + column] is not None,
        )
        for row in range(BOARD_ROWS)
        for column in range(BOARD_COLUMNS)
    )
    assigned_count = sum(candidate_index is not None for candidate_index in assigned)
    if assigned_count < MIN_ASSIGNED_COMPONENTS:
        return _fallback(
            candidates,
            "GLOBAL_SYMBOL_LATTICE_INSUFFICIENT_ASSIGNMENTS",
            centers=centers,
            column_bases=column_lattice.bases,
            row_bases=row_lattice.bases,
            assigned_candidate_indices=assigned,
        )
    return GlobalSymbolLattice(
        status="assigned",
        candidates=candidates,
        centers=centers,
        column_bases=column_lattice.bases,
        row_bases=row_lattice.bases,
        assigned_candidate_indices=assigned,
        assigned_candidate_count=assigned_count,
        fallback_reason=None,
    )


__all__ = [
    "LOCATOR_VERSION",
    "GlobalSymbolCandidate",
    "GlobalSymbolLattice",
    "detect_global_symbol_candidates",
    "locate_global_symbol_lattice",
    "refine_global_symbol_center",
]
