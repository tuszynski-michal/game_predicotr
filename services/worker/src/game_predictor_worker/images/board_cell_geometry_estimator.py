"""Fail-closed v19 estimation of a 3 x 5 symbol lattice in source coordinates."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, replace
from itertools import combinations
from typing import Literal, cast

import numpy as np
from numpy.typing import NDArray

from .board_cell_geometry_contract import (
    BOARD_CELL_GEOMETRY_VERSION,
    BoardCellGeometryContractError,
    BoardCellGeometryEvidence,
    BoardCellQuad,
    Quad,
    derive_board_cell_quads,
)
from .geometry import Quad as DetectorQuad
from .global_symbol_lattice import (
    GlobalSymbolCandidate,
    detect_global_symbol_candidates,
    refine_global_symbol_center,
)
from .rectification import BOARD_COLUMNS, BOARD_HEIGHT, BOARD_ROWS, BOARD_WIDTH
from .symbol_grid_refinement import SymbolCenter, rectify_board
from .symbol_lattice_homography import (
    MAX_INLIER_P95_RESIDUAL_PX,
    MAX_PROJECTED_COLUMN_SPACING_PX,
    MAX_PROJECTED_ROW_SPACING_PX,
    MIN_INLIERS,
    MIN_PROJECTED_COLUMN_SPACING_PX,
    MIN_PROJECTED_ROW_SPACING_PX,
    MIN_RELIABLE_CENTERS,
    RANSAC_REPROJECTION_THRESHOLD_PX,
    SOURCE_AWARE_GEOMETRY_GUARD,
    Matrix3x3,
    SymbolLatticeHomography,
    fit_symbol_lattice_homography,
    project_points,
)

ESTIMATOR_VERSION = BOARD_CELL_GEOMETRY_VERSION
LOCATOR_VERSION = "global-bright-component-lattice-assignment-v2-bounded-hypotheses-v1"
HOMOGRAPHY_VERSION = "symbol-lattice-homography-ransac-v3-board-cell-geometry-v1"
THRESHOLDS_VERSION = "board-cell-geometry-guarded-ransac-thresholds-v1"

MIN_COLUMN_SPACING_PX = MIN_PROJECTED_COLUMN_SPACING_PX
MAX_COLUMN_SPACING_PX = MAX_PROJECTED_COLUMN_SPACING_PX
MIN_ROW_SPACING_PX = MIN_PROJECTED_ROW_SPACING_PX
MAX_ROW_SPACING_PX = MAX_PROJECTED_ROW_SPACING_PX
COLUMN_MATCH_TOLERANCE_PX = 22.0
ROW_MATCH_TOLERANCE_PX = 25.0
SLOT_COLUMN_TOLERANCE_PX = 25.0
SLOT_ROW_TOLERANCE_PX = 36.0
MIN_AXIS_COMPONENT_MATCHES = 8
MIN_ASSIGNED_COMPONENTS = 10
MAX_AXIS_HYPOTHESIS_CANDIDATES = 64
MAX_AXIS_SCORING_CANDIDATES = 96


@dataclass(frozen=True, slots=True)
class BoardCellGeometryEstimate:
    """Auditable estimator result which can become one manifest entry after success."""

    status: Literal["estimated", "needs_review"]
    lattice_bounds_quad: Quad | None
    cells: tuple[BoardCellQuad, ...]
    evidence: BoardCellGeometryEvidence | None
    candidate_center_count: int
    assigned_candidate_count: int
    reliable_center_count: int
    inlier_slots: tuple[tuple[int, int], ...]
    inlier_p95_residual_px: float | None
    fallback_reason: str | None

    @property
    def inlier_count(self) -> int:
        return len(self.inlier_slots)

    def to_dict(self) -> dict[str, object]:
        return {
            "assignedCandidateCount": self.assigned_candidate_count,
            "candidateCenterCount": self.candidate_center_count,
            "cells": [cell.to_dict() for cell in self.cells],
            "estimatorVersion": ESTIMATOR_VERSION,
            "evidence": None if self.evidence is None else self.evidence.to_dict(),
            "fallbackReason": self.fallback_reason,
            "inlierCount": self.inlier_count,
            "inlierP95ResidualPx": (
                None
                if self.inlier_p95_residual_px is None
                else round(self.inlier_p95_residual_px, 4)
            ),
            "inlierSlots": [
                {"columnIndex": column, "rowIndex": row} for row, column in self.inlier_slots
            ],
            "latticeBoundsQuad": (
                None
                if self.lattice_bounds_quad is None
                else [
                    {"x": round(point[0], 4), "y": round(point[1], 4)}
                    for point in self.lattice_bounds_quad
                ]
            ),
            "locatorVersion": LOCATOR_VERSION,
            "reliableCenterCount": self.reliable_center_count,
            "status": self.status,
            "thresholdsVersion": THRESHOLDS_VERSION,
        }


@dataclass(frozen=True, slots=True)
class _AxisLattice:
    bases: tuple[float, ...]


def _bounded_candidates(
    candidates: tuple[GlobalSymbolCandidate, ...],
    limit: int,
) -> tuple[GlobalSymbolCandidate, ...]:
    ranked = sorted(
        candidates,
        key=lambda candidate: (
            candidate.touches_border,
            -candidate.weight,
            -candidate.area,
            candidate.y,
            candidate.x,
            candidate.candidate_index,
        ),
    )
    return tuple(ranked[:limit])


def _axis_hypotheses(
    candidates: tuple[GlobalSymbolCandidate, ...],
    *,
    axis: Literal["x", "y"],
    count: int,
    limit: int,
    minimum_spacing: float,
    maximum_spacing: float,
    tolerance: float,
) -> tuple[tuple[float, float], ...]:
    coordinates = sorted(
        {
            round(candidate.x if axis == "x" else candidate.y, 4)
            for candidate in _bounded_candidates(
                candidates,
                MAX_AXIS_HYPOTHESIS_CANDIDATES,
            )
        }
    )
    hypotheses: set[tuple[float, float]] = set()
    for lower, upper in combinations(coordinates, 2):
        delta = upper - lower
        for lower_line in range(count - 1):
            for upper_line in range(lower_line + 1, count):
                spacing = delta / (upper_line - lower_line)
                if not minimum_spacing <= spacing <= maximum_spacing:
                    continue
                start = lower - lower_line * spacing
                end = start + (count - 1) * spacing
                if start < -tolerance or end > limit - 1 + tolerance:
                    continue
                hypotheses.add((round(start, 4), round(spacing, 4)))
    return tuple(sorted(hypotheses))


def _fit_axis_lattice(
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
    scoring_candidates = _bounded_candidates(candidates, MAX_AXIS_SCORING_CANDIDATES)
    best_key: tuple[int, float, float, float, float] | None = None
    best_bases: tuple[float, ...] | None = None
    for start, spacing in _axis_hypotheses(
        candidates,
        axis=axis,
        count=count,
        limit=limit,
        minimum_spacing=minimum_spacing,
        maximum_spacing=maximum_spacing,
        tolerance=tolerance,
    ):
        matched: list[list[tuple[float, float, float, int]]] = [[] for _ in range(count)]
        for candidate in scoring_candidates:
            coordinate = candidate.x if axis == "x" else candidate.y
            line_index = int(round((coordinate - start) / spacing))
            if not 0 <= line_index < count:
                continue
            distance = abs(coordinate - (start + line_index * spacing))
            if distance <= tolerance:
                matched[line_index].append(
                    (
                        distance,
                        -candidate.weight,
                        coordinate,
                        candidate.candidate_index,
                    )
                )
        if any(not line for line in matched):
            continue
        selected = [sorted(line)[:maximum_support_per_line] for line in matched]
        match_count = sum(len(line) for line in selected)
        if match_count < MIN_AXIS_COMPONENT_MATCHES:
            continue
        bases = tuple(float(statistics.median(value[2] for value in line)) for line in selected)
        spacings = tuple(bases[index + 1] - bases[index] for index in range(count - 1))
        if any(value < minimum_spacing or value > maximum_spacing for value in spacings):
            continue
        support_weight = -sum(value[1] for line in selected for value in line)
        distance_penalty = sum(value[0] for line in selected for value in line)
        spacing_variation = float(np.std(np.asarray(spacings, dtype=np.float64)))
        key = (
            match_count,
            round(support_weight, 8),
            -round(distance_penalty, 8),
            -round(spacing_variation, 8),
            -spacing,
        )
        if best_key is None or key > best_key:
            best_key = key
            best_bases = bases
    return None if best_bases is None else _AxisLattice(bases=best_bases)


def _assign_candidates(
    candidates: tuple[GlobalSymbolCandidate, ...],
    *,
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
        candidate_key = (score, candidate.candidate_index)
        if slot not in selected or candidate_key < selected[slot]:
            selected[slot] = candidate_key
    assigned: list[int | None] = []
    for row in range(BOARD_ROWS):
        for column in range(BOARD_COLUMNS):
            value = selected.get((row, column))
            assigned.append(None if value is None else value[1])
    return tuple(assigned)


def _refined_centers(
    board_rgb: NDArray[np.uint8],
    *,
    column_bases: tuple[float, ...],
    row_bases: tuple[float, ...],
    assigned: tuple[int | None, ...],
) -> tuple[SymbolCenter, ...]:
    column_spacing = statistics.median(
        column_bases[index + 1] - column_bases[index] for index in range(BOARD_COLUMNS - 1)
    )
    row_spacing = statistics.median(
        row_bases[index + 1] - row_bases[index] for index in range(BOARD_ROWS - 1)
    )
    return tuple(
        refine_global_symbol_center(
            board_rgb,
            row_index=row,
            column_index=column,
            expected_x=column_bases[column],
            expected_y=row_bases[row],
            half_width=column_spacing * 0.44,
            half_height=row_spacing * 0.44,
            has_component_support=assigned[row * BOARD_COLUMNS + column] is not None,
        )
        for row in range(BOARD_ROWS)
        for column in range(BOARD_COLUMNS)
    )


def _matrix_tuple(matrix: NDArray[np.float64]) -> Matrix3x3:
    return cast(
        Matrix3x3,
        tuple(tuple(float(matrix[row, column]) for column in range(3)) for row in range(3)),
    )


def _failure(
    reason: str,
    *,
    candidate_count: int,
    assigned_count: int = 0,
    homography: SymbolLatticeHomography | None = None,
) -> BoardCellGeometryEstimate:
    return BoardCellGeometryEstimate(
        status="needs_review",
        lattice_bounds_quad=None,
        cells=(),
        evidence=None,
        candidate_center_count=candidate_count,
        assigned_candidate_count=assigned_count,
        reliable_center_count=(0 if homography is None else homography.reliable_center_count),
        inlier_slots=() if homography is None else homography.inlier_slots,
        inlier_p95_residual_px=(None if homography is None else homography.inlier_p95_residual_px),
        fallback_reason=reason,
    )


def _source_lattice_bounds(
    source_to_analysis: NDArray[np.float64],
    ideal_to_analysis: Matrix3x3,
) -> Quad | None:
    try:
        analysis_to_source = np.linalg.inv(source_to_analysis)
    except np.linalg.LinAlgError:
        return None
    ideal_to_source = cast(
        NDArray[np.float64],
        analysis_to_source
        @ np.asarray(
            ideal_to_analysis,
            dtype=np.float64,
        ),
    )
    if not np.isfinite(ideal_to_source).all() or abs(float(np.linalg.det(ideal_to_source))) < 1e-9:
        return None
    projected = project_points(
        np.asarray(
            (
                (0.0, 0.0),
                (float(BOARD_WIDTH), 0.0),
                (float(BOARD_WIDTH), float(BOARD_HEIGHT)),
                (0.0, float(BOARD_HEIGHT)),
            ),
            dtype=np.float64,
        ),
        _matrix_tuple(ideal_to_source),
    )
    if not np.isfinite(projected).all():
        return None
    return cast(
        Quad,
        tuple((round(float(point[0]), 4), round(float(point[1]), 4)) for point in projected),
    )


def estimate_board_cell_geometry(
    source_rgb: NDArray[np.uint8],
    analysis_quad: DetectorQuad,
) -> BoardCellGeometryEstimate:
    """Estimate complete source-space cell geometry without creating image crops."""

    analysis_board, source_to_analysis = rectify_board(source_rgb, analysis_quad)
    candidates = detect_global_symbol_candidates(analysis_board)
    candidate_count = len(candidates)
    if candidate_count < MIN_AXIS_COMPONENT_MATCHES:
        return _failure(
            "BOARD_CELL_GEOMETRY_INSUFFICIENT_GLOBAL_CANDIDATES",
            candidate_count=candidate_count,
        )
    columns = _fit_axis_lattice(
        candidates,
        axis="x",
        count=BOARD_COLUMNS,
        limit=BOARD_WIDTH,
        minimum_spacing=MIN_COLUMN_SPACING_PX,
        maximum_spacing=MAX_COLUMN_SPACING_PX,
        tolerance=COLUMN_MATCH_TOLERANCE_PX,
        maximum_support_per_line=BOARD_ROWS,
    )
    rows = _fit_axis_lattice(
        candidates,
        axis="y",
        count=BOARD_ROWS,
        limit=BOARD_HEIGHT,
        minimum_spacing=MIN_ROW_SPACING_PX,
        maximum_spacing=MAX_ROW_SPACING_PX,
        tolerance=ROW_MATCH_TOLERANCE_PX,
        maximum_support_per_line=BOARD_COLUMNS,
    )
    if columns is None or rows is None:
        return _failure(
            "BOARD_CELL_GEOMETRY_AXIS_ASSIGNMENT_FAILED",
            candidate_count=candidate_count,
        )
    assigned = _assign_candidates(
        candidates,
        column_bases=columns.bases,
        row_bases=rows.bases,
    )
    assigned_count = sum(candidate is not None for candidate in assigned)
    if assigned_count < MIN_ASSIGNED_COMPONENTS:
        return _failure(
            "BOARD_CELL_GEOMETRY_INSUFFICIENT_GLOBAL_ASSIGNMENTS",
            candidate_count=candidate_count,
            assigned_count=assigned_count,
        )
    centers = _refined_centers(
        analysis_board,
        column_bases=columns.bases,
        row_bases=rows.bases,
        assigned=assigned,
    )
    homography = replace(
        fit_symbol_lattice_homography(
            centers,
            geometry_guard=SOURCE_AWARE_GEOMETRY_GUARD,
        ),
        homography_version=HOMOGRAPHY_VERSION,
        locator_version=LOCATOR_VERSION,
        global_candidate_count=candidate_count,
        global_assigned_candidate_count=assigned_count,
        global_column_bases=columns.bases,
        global_row_bases=rows.bases,
    )
    if homography.status != "fitted" or homography.ideal_to_observed_matrix is None:
        return _failure(
            homography.fallback_reason or "BOARD_CELL_GEOMETRY_RANSAC_FAILED",
            candidate_count=candidate_count,
            assigned_count=assigned_count,
            homography=homography,
        )
    bounds = _source_lattice_bounds(
        source_to_analysis,
        homography.ideal_to_observed_matrix,
    )
    if bounds is None:
        return _failure(
            "BOARD_CELL_GEOMETRY_SOURCE_TRANSFORM_INVALID",
            candidate_count=candidate_count,
            assigned_count=assigned_count,
            homography=homography,
        )
    source_height, source_width = source_rgb.shape[:2]
    try:
        cells = derive_board_cell_quads(
            bounds,
            source_image_width=source_width,
            source_image_height=source_height,
        )
    except BoardCellGeometryContractError as error:
        return _failure(
            error.code,
            candidate_count=candidate_count,
            assigned_count=assigned_count,
            homography=homography,
        )
    evidence = BoardCellGeometryEvidence(
        kind="automatic",
        estimator_version=ESTIMATOR_VERSION,
        thresholds_version=THRESHOLDS_VERSION,
        locator_version=LOCATOR_VERSION,
        homography_version=HOMOGRAPHY_VERSION,
        candidate_center_count=candidate_count,
        reliable_center_count=homography.reliable_center_count,
        inlier_count=homography.inlier_count,
        inlier_slots=homography.inlier_slots,
        inlier_p95_residual_px=(
            None
            if homography.inlier_p95_residual_px is None
            else round(homography.inlier_p95_residual_px, 4)
        ),
        decision_checksum_sha256=None,
    )
    if (
        evidence.reliable_center_count < MIN_RELIABLE_CENTERS
        or evidence.inlier_count < MIN_INLIERS
        or evidence.inlier_p95_residual_px is None
        or evidence.inlier_p95_residual_px > MAX_INLIER_P95_RESIDUAL_PX
        or {row for row, _ in evidence.inlier_slots} != set(range(BOARD_ROWS))
        or {column for _, column in evidence.inlier_slots} != set(range(BOARD_COLUMNS))
    ):
        return _failure(
            "BOARD_CELL_GEOMETRY_AUTOMATIC_EVIDENCE_INSUFFICIENT",
            candidate_count=candidate_count,
            assigned_count=assigned_count,
            homography=homography,
        )
    return BoardCellGeometryEstimate(
        status="estimated",
        lattice_bounds_quad=bounds,
        cells=cells,
        evidence=evidence,
        candidate_center_count=candidate_count,
        assigned_candidate_count=assigned_count,
        reliable_center_count=homography.reliable_center_count,
        inlier_slots=homography.inlier_slots,
        inlier_p95_residual_px=homography.inlier_p95_residual_px,
        fallback_reason=None,
    )


def estimator_thresholds() -> dict[str, object]:
    """Expose the pinned fail-closed threshold set for manifests and audits."""

    return {
        "homographyVersion": HOMOGRAPHY_VERSION,
        "locatorVersion": LOCATOR_VERSION,
        "maximumColumnSpacingPx": MAX_COLUMN_SPACING_PX,
        "maximumInlierP95ResidualPx": MAX_INLIER_P95_RESIDUAL_PX,
        "maximumRowSpacingPx": MAX_ROW_SPACING_PX,
        "minimumAssignedComponents": MIN_ASSIGNED_COMPONENTS,
        "minimumAxisComponentMatches": MIN_AXIS_COMPONENT_MATCHES,
        "minimumColumnSpacingPx": MIN_COLUMN_SPACING_PX,
        "minimumInliers": MIN_INLIERS,
        "minimumReliableCenters": MIN_RELIABLE_CENTERS,
        "minimumRowSpacingPx": MIN_ROW_SPACING_PX,
        "ransacReprojectionThresholdPx": RANSAC_REPROJECTION_THRESHOLD_PX,
        "thresholdsVersion": THRESHOLDS_VERSION,
    }


__all__ = [
    "ESTIMATOR_VERSION",
    "HOMOGRAPHY_VERSION",
    "LOCATOR_VERSION",
    "THRESHOLDS_VERSION",
    "BoardCellGeometryEstimate",
    "estimate_board_cell_geometry",
    "estimator_thresholds",
]
