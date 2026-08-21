"""Local per-cell symbol mesh derived from a complete rectified board frame."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Literal, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from .rectification import BOARD_COLUMNS, BOARD_HEIGHT, BOARD_ROWS, BOARD_WIDTH
from .symbol_grid_refinement import (
    MIN_CENTER_CONFIDENCE,
    SymbolCenter,
    locate_symbol_centers,
)

MESH_VERSION = "expanded-wide-frame-bright-lattice-symbol-mesh-spike-v9"
HISTORICAL_CENTERED_MESH_VERSION = "expanded-frame-centered-symbol-mesh-spike-v4"
MIN_RELIABLE_CENTERS = 10
MIN_COLUMN_SPACING = 55.0
MAX_COLUMN_SPACING = 145.0
MIN_ROW_SPACING = 55.0
MAX_ROW_SPACING = 145.0
CELL_OUTPUT_SIZE = 90
CENTERED_V4_CONTEXT_SCALE = 0.92
MIN_LATTICE_COMPONENT_AREA = 180
MAX_LATTICE_COMPONENT_AREA = 6000
MIN_LATTICE_COMPONENT_SIZE = 14
MAX_LATTICE_COMPONENT_WIDTH = 82
MAX_LATTICE_COMPONENT_HEIGHT = 92
MIN_LATTICE_COLUMN_SPACING = 55.0
MAX_LATTICE_COLUMN_SPACING = 110.0
LATTICE_MATCH_TOLERANCE = 18.0
MIN_LATTICE_COMPONENT_MATCHES = 8
BoundsMode = Literal["centered_v4", "extrapolated_v8"]


@dataclass(frozen=True, slots=True)
class SymbolMeshCell:
    row_index: int
    column_index: int
    center_x: float
    center_y: float
    left: int
    top: int
    right: int
    bottom: int
    rgb: NDArray[np.uint8]


@dataclass(frozen=True, slots=True)
class SymbolMeshResult:
    status: Literal["meshed", "fallback"]
    raw_centers: tuple[SymbolCenter, ...]
    reliable_center_count: int
    cells: tuple[SymbolMeshCell, ...]
    overlay_rgb: NDArray[np.uint8]
    fallback_reason: str | None
    column_center_source: str | None


def _fallback(
    board_rgb: NDArray[np.uint8],
    centers: tuple[SymbolCenter, ...],
    reliable_count: int,
    reason: str,
) -> SymbolMeshResult:
    return SymbolMeshResult(
        status="fallback",
        raw_centers=centers,
        reliable_center_count=reliable_count,
        cells=(),
        overlay_rgb=board_rgb.copy(),
        fallback_reason=reason,
        column_center_source=None,
    )


def _partitioned_axis_bounds(
    centers: list[float],
    *,
    limit: int,
    minimum_spacing: float,
    maximum_spacing: float,
) -> list[tuple[int, int]] | None:
    spacings = [centers[index + 1] - centers[index] for index in range(len(centers) - 1)]
    if any(spacing < minimum_spacing or spacing > maximum_spacing for spacing in spacings):
        return None
    edges = [max(0, int(round(centers[0] - spacings[0] / 2.0)))]
    edges.extend(
        int(round((centers[index] + centers[index + 1]) / 2.0)) for index in range(len(centers) - 1)
    )
    edges.append(
        min(
            limit,
            int(round(centers[-1] + spacings[-1] / 2.0)),
        )
    )
    bounds: list[tuple[int, int]] = []
    for index in range(len(centers)):
        start = edges[index]
        end = edges[index + 1]
        if end - start < 35:
            return None
        bounds.append((start, end))
    return bounds


def _centered_v4_axis_bounds(
    centers: list[float],
    *,
    limit: int,
    minimum_spacing: float,
    maximum_spacing: float,
) -> list[tuple[int, int]] | None:
    spacings = [centers[index + 1] - centers[index] for index in range(len(centers) - 1)]
    if any(spacing < minimum_spacing or spacing > maximum_spacing for spacing in spacings):
        return None
    context_size = max(
        45,
        min(
            limit,
            int(round(statistics.median(spacings) * CENTERED_V4_CONTEXT_SCALE)),
        ),
    )
    bounds: list[tuple[int, int]] = []
    for center in centers:
        start = int(round(center - context_size / 2.0))
        start = min(max(0, start), limit - context_size)
        bounds.append((start, start + context_size))
    return bounds


def _bright_component_x_centers(
    board_rgb: NDArray[np.uint8],
) -> list[tuple[float, float]]:
    hsv = cv2.cvtColor(board_rgb, cv2.COLOR_RGB2HSV)
    value = hsv[:, :, 2]
    threshold = max(115.0, float(np.percentile(value, 67.0)))
    mask = np.where(value >= threshold, 255, 0).astype(np.uint8)
    mask = cast(
        NDArray[np.uint8],
        cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), dtype=np.uint8)),
    )
    count, _, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    candidates: list[tuple[float, float]] = []
    for label in range(1, count):
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        width = int(stats[label, cv2.CC_STAT_WIDTH])
        height = int(stats[label, cv2.CC_STAT_HEIGHT])
        area = int(stats[label, cv2.CC_STAT_AREA])
        if not (
            MIN_LATTICE_COMPONENT_AREA <= area <= MAX_LATTICE_COMPONENT_AREA
            and MIN_LATTICE_COMPONENT_SIZE <= width <= MAX_LATTICE_COMPONENT_WIDTH
            and MIN_LATTICE_COMPONENT_SIZE <= height <= MAX_LATTICE_COMPONENT_HEIGHT
        ):
            continue
        if x <= 1 or y <= 1 or x + width >= BOARD_WIDTH - 1 or y + height >= BOARD_HEIGHT - 1:
            continue
        fill_fraction = area / float(width * height)
        if not 0.18 <= fill_fraction <= 0.96:
            continue
        candidates.append((float(centroids[label, 0]), min(1.0, area / 1800.0)))
    return candidates


def _bright_lattice_column_bases(
    board_rgb: NDArray[np.uint8],
) -> list[float] | None:
    candidates = _bright_component_x_centers(board_rgb)
    if len(candidates) < MIN_LATTICE_COMPONENT_MATCHES:
        return None
    best: tuple[float, float, float, list[list[tuple[float, float]]]] | None = None
    for spacing_step in range(
        int(MIN_LATTICE_COLUMN_SPACING * 2),
        int(MAX_LATTICE_COLUMN_SPACING * 2) + 1,
    ):
        spacing = spacing_step / 2.0
        maximum_start = BOARD_WIDTH - 1.0 - 4.0 * spacing
        if maximum_start <= 0:
            continue
        for start_step in range(0, int(maximum_start * 2) + 1):
            start = start_step / 2.0
            matched: list[list[tuple[float, float]]] = [[] for _ in range(BOARD_COLUMNS)]
            for x, weight in candidates:
                column = int(round((x - start) / spacing))
                if not 0 <= column < BOARD_COLUMNS:
                    continue
                distance = abs(x - (start + column * spacing))
                if distance <= LATTICE_MATCH_TOLERANCE:
                    matched[column].append((x, weight))
            if any(not column for column in matched):
                continue
            selected = [
                sorted(column, key=lambda item: abs(item[0] - (start + index * spacing)))[:3]
                for index, column in enumerate(matched)
            ]
            match_count = sum(len(column) for column in selected)
            if match_count < MIN_LATTICE_COMPONENT_MATCHES:
                continue
            distance_penalty = sum(
                abs(x - (start + index * spacing)) / LATTICE_MATCH_TOLERANCE
                for index, column in enumerate(selected)
                for x, _ in column
            )
            support_weight = sum(weight for column in selected for _, weight in column)
            score = match_count * 4.0 + support_weight - distance_penalty
            candidate_result = (score, -distance_penalty, -spacing, selected)
            if best is None or candidate_result[:3] > best[:3]:
                best = candidate_result
    if best is None:
        return None
    selected = best[3]
    bases = [statistics.median(x for x, _ in column) for column in selected]
    spacings = [bases[index + 1] - bases[index] for index in range(BOARD_COLUMNS - 1)]
    if any(
        spacing < MIN_LATTICE_COLUMN_SPACING or spacing > MAX_LATTICE_COLUMN_SPACING
        for spacing in spacings
    ):
        return None
    return bases


def _mesh_centers(
    centers: tuple[SymbolCenter, ...],
    *,
    board_rgb: NDArray[np.uint8],
    use_bright_lattice: bool,
) -> tuple[list[list[float]], list[list[float]], str]:
    x_values = [
        [centers[row * BOARD_COLUMNS + column].x for column in range(BOARD_COLUMNS)]
        for row in range(BOARD_ROWS)
    ]
    y_values = [
        [centers[row * BOARD_COLUMNS + column].y for column in range(BOARD_COLUMNS)]
        for row in range(BOARD_ROWS)
    ]
    raw_column_bases = [
        statistics.median(x_values[row][column] for row in range(BOARD_ROWS))
        for column in range(BOARD_COLUMNS)
    ]
    bright_column_bases = _bright_lattice_column_bases(board_rgb) if use_bright_lattice else None
    column_bases = bright_column_bases if bright_column_bases is not None else raw_column_bases
    column_center_source = (
        "bright-component-lattice" if bright_column_bases is not None else "raw-slot-medians"
    )
    raw_row_bases = [
        statistics.median(y_values[row][column] for column in range(BOARD_COLUMNS))
        for row in range(BOARD_ROWS)
    ]
    lower_row_spacing = raw_row_bases[2] - raw_row_bases[1]
    row_bases = [
        raw_row_bases[1] - 0.85 * lower_row_spacing,
        raw_row_bases[1],
        raw_row_bases[2],
    ]
    row_x_offsets = [
        statistics.median(
            x_values[row][column] - raw_column_bases[column]
            for column in range(1, BOARD_COLUMNS - 1)
            if abs(x_values[row][column] - raw_column_bases[column]) <= 28.0
        )
        for row in range(BOARD_ROWS)
    ]
    column_y_offsets = [
        statistics.median(
            y_values[row][column] - row_bases[row]
            for row in (1, 2)
            if abs(y_values[row][column] - row_bases[row]) <= 24.0
        )
        for column in range(BOARD_COLUMNS)
    ]
    mesh_x = [
        [column_bases[column] + row_x_offsets[row] for column in range(BOARD_COLUMNS)]
        for row in range(BOARD_ROWS)
    ]
    mesh_y = [
        [row_bases[row] + column_y_offsets[column] for column in range(BOARD_COLUMNS)]
        for row in range(BOARD_ROWS)
    ]
    return mesh_x, mesh_y, column_center_source


def _build_symbol_mesh(
    board_rgb: NDArray[np.uint8],
    *,
    bounds_mode: BoundsMode,
) -> SymbolMeshResult:
    if board_rgb.shape != (BOARD_HEIGHT, BOARD_WIDTH, 3) or board_rgb.dtype != np.uint8:
        raise ValueError("Symbol mesh input must be RGB uint8 500 × 300.")
    centers = locate_symbol_centers(board_rgb)
    reliable_count = sum(center.confidence >= MIN_CENTER_CONFIDENCE for center in centers)
    if reliable_count < MIN_RELIABLE_CENTERS:
        return _fallback(
            board_rgb,
            centers,
            reliable_count,
            "SYMBOL_MESH_INSUFFICIENT_RELIABLE_CENTERS",
        )
    mesh_x, mesh_y, column_center_source = _mesh_centers(
        centers,
        board_rgb=board_rgb,
        use_bright_lattice=bounds_mode == "extrapolated_v8",
    )
    bounds_builder = (
        _centered_v4_axis_bounds if bounds_mode == "centered_v4" else _partitioned_axis_bounds
    )
    horizontal = [
        bounds_builder(
            mesh_x[row],
            limit=BOARD_WIDTH,
            minimum_spacing=MIN_COLUMN_SPACING,
            maximum_spacing=MAX_COLUMN_SPACING,
        )
        for row in range(BOARD_ROWS)
    ]
    vertical = [
        bounds_builder(
            [mesh_y[row][column] for row in range(BOARD_ROWS)],
            limit=BOARD_HEIGHT,
            minimum_spacing=MIN_ROW_SPACING,
            maximum_spacing=MAX_ROW_SPACING,
        )
        for column in range(BOARD_COLUMNS)
    ]
    if any(bounds is None for bounds in horizontal + vertical):
        return _fallback(
            board_rgb,
            centers,
            reliable_count,
            "SYMBOL_MESH_SPACING_IMPLAUSIBLE",
        )
    typed_horizontal = cast(list[list[tuple[int, int]]], horizontal)
    typed_vertical = cast(list[list[tuple[int, int]]], vertical)
    overlay = board_rgb.copy()
    cells: list[SymbolMeshCell] = []
    for row in range(BOARD_ROWS):
        for column in range(BOARD_COLUMNS):
            left, right = typed_horizontal[row][column]
            top, bottom = typed_vertical[column][row]
            crop = board_rgb[top:bottom, left:right]
            if crop.size == 0:
                return _fallback(
                    board_rgb,
                    centers,
                    reliable_count,
                    "SYMBOL_MESH_CELL_EMPTY",
                )
            resized = cast(
                NDArray[np.uint8],
                cv2.resize(
                    crop,
                    (CELL_OUTPUT_SIZE, CELL_OUTPUT_SIZE),
                    interpolation=cv2.INTER_AREA,
                ),
            )
            cv2.rectangle(
                overlay,
                (left, top),
                (right - 1, bottom - 1),
                (25, 235, 90),
                2,
                cv2.LINE_AA,
            )
            cv2.circle(
                overlay,
                (round(mesh_x[row][column]), round(mesh_y[row][column])),
                3,
                (20, 220, 255),
                -1,
                cv2.LINE_AA,
            )
            cells.append(
                SymbolMeshCell(
                    row_index=row,
                    column_index=column,
                    center_x=mesh_x[row][column],
                    center_y=mesh_y[row][column],
                    left=left,
                    top=top,
                    right=right,
                    bottom=bottom,
                    rgb=resized,
                )
            )
    return SymbolMeshResult(
        status="meshed",
        raw_centers=centers,
        reliable_center_count=reliable_count,
        cells=tuple(cells),
        overlay_rgb=overlay,
        fallback_reason=None,
        column_center_source=column_center_source,
    )


def build_symbol_mesh(board_rgb: NDArray[np.uint8]) -> SymbolMeshResult:
    """Build current wide-frame extrapolated local symbol crops."""

    return _build_symbol_mesh(board_rgb, bounds_mode="extrapolated_v8")


def build_historical_centered_symbol_mesh_v4(
    board_rgb: NDArray[np.uint8],
) -> SymbolMeshResult:
    """Reproduce the immutable v4 crop geometry for owner-feedback calibration."""

    return _build_symbol_mesh(board_rgb, bounds_mode="centered_v4")


__all__ = [
    "CELL_OUTPUT_SIZE",
    "HISTORICAL_CENTERED_MESH_VERSION",
    "MESH_VERSION",
    "SymbolMeshCell",
    "SymbolMeshResult",
    "build_historical_centered_symbol_mesh_v4",
    "build_symbol_mesh",
]
