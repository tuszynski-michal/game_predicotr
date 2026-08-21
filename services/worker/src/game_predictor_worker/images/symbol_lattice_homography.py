"""Guarded projective homography fitted from the complete 5 × 3 symbol lattice."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Literal, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from .global_symbol_lattice import (
    LOCATOR_VERSION,
    locate_global_symbol_lattice,
)
from .rectification import BOARD_COLUMNS, BOARD_HEIGHT, BOARD_ROWS, BOARD_WIDTH
from .symbol_grid_refinement import (
    MIN_CENTER_CONFIDENCE,
    SymbolCenter,
    SymbolGridRefinementError,
    locate_symbol_centers,
)

HOMOGRAPHY_VERSION = "symbol-lattice-homography-ransac-v1"
GLOBAL_HOMOGRAPHY_VERSION = "symbol-lattice-homography-ransac-v2-global-assignment-v1"
MIN_RELIABLE_CENTERS = 10
MIN_INLIERS = 9
RANSAC_REPROJECTION_THRESHOLD_PX = 12.0
MAX_INLIER_P95_RESIDUAL_PX = 10.0
MAX_VIRTUAL_CORNER_MARGIN_PX = 16.0
MIN_VIRTUAL_GRID_AREA_RATIO = 0.65
MAX_VIRTUAL_GRID_AREA_RATIO = 1.15
MIN_PROJECTED_COLUMN_SPACING_PX = 45.0
MAX_PROJECTED_COLUMN_SPACING_PX = 135.0
MIN_PROJECTED_ROW_SPACING_PX = 45.0
MAX_PROJECTED_ROW_SPACING_PX = 145.0

FloatPoint = tuple[float, float]
Matrix3x3 = tuple[
    tuple[float, float, float],
    tuple[float, float, float],
    tuple[float, float, float],
]
LatticeSlot = tuple[int, int]


@dataclass(frozen=True, slots=True)
class LatticeGeometryGuard:
    minimum_virtual_grid_area_ratio: float
    maximum_virtual_grid_area_ratio: float
    maximum_virtual_corner_margin_px: float


EXPANDED_FRAME_GEOMETRY_GUARD = LatticeGeometryGuard(
    minimum_virtual_grid_area_ratio=MIN_VIRTUAL_GRID_AREA_RATIO,
    maximum_virtual_grid_area_ratio=MAX_VIRTUAL_GRID_AREA_RATIO,
    maximum_virtual_corner_margin_px=MAX_VIRTUAL_CORNER_MARGIN_PX,
)
SOURCE_AWARE_GEOMETRY_GUARD = LatticeGeometryGuard(
    minimum_virtual_grid_area_ratio=0.55,
    maximum_virtual_grid_area_ratio=MAX_VIRTUAL_GRID_AREA_RATIO,
    maximum_virtual_corner_margin_px=75.0,
)


@dataclass(frozen=True, slots=True)
class SymbolLatticeHomography:
    """Auditable result of fitting ideal lattice points to observed symbol centres."""

    status: Literal["fitted", "fallback"]
    centers: tuple[SymbolCenter, ...]
    reliable_center_count: int
    inlier_slots: tuple[LatticeSlot, ...]
    row_coverage: int
    column_coverage: int
    inlier_median_residual_px: float | None
    inlier_p95_residual_px: float | None
    all_center_p95_residual_px: float | None
    ideal_to_observed_matrix: Matrix3x3 | None
    virtual_grid_quad: tuple[FloatPoint, FloatPoint, FloatPoint, FloatPoint] | None
    fallback_reason: str | None
    homography_version: str = HOMOGRAPHY_VERSION
    locator_version: str | None = None
    global_candidate_count: int | None = None
    global_assigned_candidate_count: int | None = None
    global_column_bases: tuple[float, ...] | None = None
    global_row_bases: tuple[float, ...] | None = None

    @property
    def inlier_count(self) -> int:
        return len(self.inlier_slots)

    def to_dict(self) -> dict[str, object]:
        matrix_precision = 5 if self.locator_version is not None else 10
        value: dict[str, object] = {
            "allCenterP95ResidualPx": _rounded_optional(self.all_center_p95_residual_px),
            "columnCoverage": self.column_coverage,
            "fallbackReason": self.fallback_reason,
            "homographyVersion": self.homography_version,
            "idealToObservedMatrix": (
                [
                    [round(value, matrix_precision) for value in row]
                    for row in self.ideal_to_observed_matrix
                ]
                if self.ideal_to_observed_matrix is not None
                else None
            ),
            "inlierCount": self.inlier_count,
            "inlierMedianResidualPx": _rounded_optional(self.inlier_median_residual_px),
            "inlierP95ResidualPx": _rounded_optional(self.inlier_p95_residual_px),
            "inlierSlots": [
                {"columnIndex": column, "rowIndex": row} for row, column in self.inlier_slots
            ],
            "reliableCenterCount": self.reliable_center_count,
            "rowCoverage": self.row_coverage,
            "status": self.status,
            "virtualGridQuad": (
                [{"x": round(x, 4), "y": round(y, 4)} for x, y in self.virtual_grid_quad]
                if self.virtual_grid_quad is not None
                else None
            ),
        }
        if self.locator_version is not None:
            value.update(
                {
                    "globalAssignedCandidateCount": self.global_assigned_candidate_count,
                    "globalCandidateCount": self.global_candidate_count,
                    "globalColumnBases": (
                        None
                        if self.global_column_bases is None
                        else [round(item, 4) for item in self.global_column_bases]
                    ),
                    "globalRowBases": (
                        None
                        if self.global_row_bases is None
                        else [round(item, 4) for item in self.global_row_bases]
                    ),
                    "locatorVersion": self.locator_version,
                }
            )
        return value


def _rounded_optional(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def _matrix_tuple(matrix: NDArray[np.float64]) -> Matrix3x3:
    return (
        (
            float(matrix[0, 0]),
            float(matrix[0, 1]),
            float(matrix[0, 2]),
        ),
        (
            float(matrix[1, 0]),
            float(matrix[1, 1]),
            float(matrix[1, 2]),
        ),
        (
            float(matrix[2, 0]),
            float(matrix[2, 1]),
            float(matrix[2, 2]),
        ),
    )


def _as_matrix(matrix: Matrix3x3) -> NDArray[np.float64]:
    return np.asarray(matrix, dtype=np.float64)


def _ideal_point(center: SymbolCenter) -> FloatPoint:
    return (
        (center.column_index + 0.5) * (BOARD_WIDTH / BOARD_COLUMNS),
        (center.row_index + 0.5) * (BOARD_HEIGHT / BOARD_ROWS),
    )


def ideal_lattice_points() -> NDArray[np.float64]:
    """Return all 15 canonical centre points in deterministic row-major order."""

    return np.asarray(
        [
            (
                (column + 0.5) * (BOARD_WIDTH / BOARD_COLUMNS),
                (row + 0.5) * (BOARD_HEIGHT / BOARD_ROWS),
            )
            for row in range(BOARD_ROWS)
            for column in range(BOARD_COLUMNS)
        ],
        dtype=np.float64,
    )


def project_points(
    points: NDArray[np.float64],
    matrix: Matrix3x3,
) -> NDArray[np.float64]:
    """Project two-dimensional points through a fitted lattice homography."""

    if points.ndim != 2 or points.shape[1] != 2:
        raise ValueError("Projected points must have shape N × 2.")
    projected = cv2.perspectiveTransform(
        points.astype(np.float64).reshape((-1, 1, 2)),
        _as_matrix(matrix),
    )
    return cast(NDArray[np.float64], projected.reshape((-1, 2)))


def _fallback(
    centers: tuple[SymbolCenter, ...],
    reliable_count: int,
    reason: str,
    *,
    inlier_slots: tuple[LatticeSlot, ...] = (),
    inlier_median: float | None = None,
    inlier_p95: float | None = None,
    all_center_p95: float | None = None,
) -> SymbolLatticeHomography:
    return SymbolLatticeHomography(
        status="fallback",
        centers=centers,
        reliable_center_count=reliable_count,
        inlier_slots=inlier_slots,
        row_coverage=len({row for row, _ in inlier_slots}),
        column_coverage=len({column for _, column in inlier_slots}),
        inlier_median_residual_px=inlier_median,
        inlier_p95_residual_px=inlier_p95,
        all_center_p95_residual_px=all_center_p95,
        ideal_to_observed_matrix=None,
        virtual_grid_quad=None,
        fallback_reason=reason,
    )


def _validate_centers(centers: tuple[SymbolCenter, ...]) -> None:
    occupied: set[LatticeSlot] = set()
    for center in centers:
        slot = (center.row_index, center.column_index)
        if not (0 <= center.row_index < BOARD_ROWS and 0 <= center.column_index < BOARD_COLUMNS):
            raise SymbolGridRefinementError(
                "SYMBOL_LATTICE_SLOT_INVALID",
                "Every symbol centre must reference a valid 5 × 3 lattice slot.",
            )
        if slot in occupied:
            raise SymbolGridRefinementError(
                "SYMBOL_LATTICE_SLOT_DUPLICATED",
                "A lattice slot cannot have more than one assigned symbol centre.",
            )
        occupied.add(slot)
        if not (
            math.isfinite(center.x)
            and math.isfinite(center.y)
            and math.isfinite(center.confidence)
            and 0.0 <= center.confidence <= 1.0
        ):
            raise SymbolGridRefinementError(
                "SYMBOL_LATTICE_CENTER_INVALID",
                "Symbol centre coordinates and confidence must be finite.",
            )


def _normalise_homography(
    matrix: NDArray[np.float64],
) -> NDArray[np.float64] | None:
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        return None
    scale = float(matrix[2, 2])
    if abs(scale) < 1e-9:
        return None
    normalised = matrix.astype(np.float64) / scale
    if abs(float(np.linalg.det(normalised))) < 1e-9:
        return None
    return normalised


def _virtual_grid_quad(
    matrix: NDArray[np.float64],
) -> NDArray[np.float64]:
    canonical_corners = np.asarray(
        (
            (0.0, 0.0),
            (float(BOARD_WIDTH), 0.0),
            (float(BOARD_WIDTH), float(BOARD_HEIGHT)),
            (0.0, float(BOARD_HEIGHT)),
        ),
        dtype=np.float64,
    )
    return cast(
        NDArray[np.float64],
        cv2.perspectiveTransform(
            canonical_corners.reshape((-1, 1, 2)),
            matrix,
        ).reshape((-1, 2)),
    )


def _grid_geometry_is_plausible(
    matrix: NDArray[np.float64],
    virtual_quad: NDArray[np.float64],
    geometry_guard: LatticeGeometryGuard,
) -> bool:
    if not np.isfinite(virtual_quad).all():
        return False
    contour = virtual_quad.astype(np.float32)
    if not cv2.isContourConvex(contour.astype(np.int32)):
        return False
    area_ratio = abs(float(cv2.contourArea(contour))) / (BOARD_WIDTH * BOARD_HEIGHT)
    if not (
        geometry_guard.minimum_virtual_grid_area_ratio
        <= area_ratio
        <= geometry_guard.maximum_virtual_grid_area_ratio
    ):
        return False
    margin = geometry_guard.maximum_virtual_corner_margin_px
    if (
        np.any(virtual_quad[:, 0] < -margin)
        or np.any(virtual_quad[:, 1] < -margin)
        or np.any(virtual_quad[:, 0] > BOARD_WIDTH - 1 + margin)
        or np.any(virtual_quad[:, 1] > BOARD_HEIGHT - 1 + margin)
    ):
        return False

    projected = cast(
        NDArray[np.float64],
        cv2.perspectiveTransform(
            ideal_lattice_points().reshape((-1, 1, 2)),
            matrix,
        ).reshape((BOARD_ROWS, BOARD_COLUMNS, 2)),
    )
    horizontal_spacing = np.linalg.norm(
        projected[:, 1:, :] - projected[:, :-1, :],
        axis=2,
    )
    vertical_spacing = np.linalg.norm(
        projected[1:, :, :] - projected[:-1, :, :],
        axis=2,
    )
    return bool(
        np.all(horizontal_spacing >= MIN_PROJECTED_COLUMN_SPACING_PX)
        and np.all(horizontal_spacing <= MAX_PROJECTED_COLUMN_SPACING_PX)
        and np.all(vertical_spacing >= MIN_PROJECTED_ROW_SPACING_PX)
        and np.all(vertical_spacing <= MAX_PROJECTED_ROW_SPACING_PX)
    )


def fit_symbol_lattice_homography(
    centers: tuple[SymbolCenter, ...],
    *,
    geometry_guard: LatticeGeometryGuard = EXPANDED_FRAME_GEOMETRY_GUARD,
) -> SymbolLatticeHomography:
    """Fit ideal-to-observed projective geometry using all reliable centres."""

    _validate_centers(centers)
    reliable = tuple(center for center in centers if center.confidence >= MIN_CENTER_CONFIDENCE)
    if len(reliable) < MIN_RELIABLE_CENTERS:
        return _fallback(
            centers,
            len(reliable),
            "SYMBOL_LATTICE_INSUFFICIENT_CENTERS",
        )
    reliable_rows = {center.row_index for center in reliable}
    reliable_columns = {center.column_index for center in reliable}
    if len(reliable_rows) != BOARD_ROWS or len(reliable_columns) != BOARD_COLUMNS:
        return _fallback(
            centers,
            len(reliable),
            "SYMBOL_LATTICE_INSUFFICIENT_COVERAGE",
        )

    ideal = np.asarray([_ideal_point(center) for center in reliable], dtype=np.float64)
    observed = np.asarray(
        [(center.x, center.y) for center in reliable],
        dtype=np.float64,
    )
    candidate_matrix, raw_mask = cv2.findHomography(
        ideal,
        observed,
        method=cv2.RANSAC,
        ransacReprojThreshold=RANSAC_REPROJECTION_THRESHOLD_PX,
        maxIters=2000,
        confidence=0.995,
    )
    if candidate_matrix is None or raw_mask is None:
        return _fallback(
            centers,
            len(reliable),
            "SYMBOL_LATTICE_RANSAC_FAILED",
        )
    initial_matrix = _normalise_homography(cast(NDArray[np.float64], candidate_matrix))
    if initial_matrix is None:
        return _fallback(
            centers,
            len(reliable),
            "SYMBOL_LATTICE_HOMOGRAPHY_SINGULAR",
        )

    mask = raw_mask.reshape(-1).astype(bool)
    inlier_slots = tuple(
        (center.row_index, center.column_index)
        for center, is_inlier in zip(reliable, mask, strict=True)
        if is_inlier
    )
    if len(inlier_slots) < MIN_INLIERS:
        return _fallback(
            centers,
            len(reliable),
            "SYMBOL_LATTICE_INSUFFICIENT_INLIERS",
            inlier_slots=inlier_slots,
        )
    if (
        len({row for row, _ in inlier_slots}) != BOARD_ROWS
        or len({column for _, column in inlier_slots}) != BOARD_COLUMNS
    ):
        return _fallback(
            centers,
            len(reliable),
            "SYMBOL_LATTICE_INLIER_COVERAGE_INSUFFICIENT",
            inlier_slots=inlier_slots,
        )

    refined_matrix_raw, _ = cv2.findHomography(
        ideal[mask],
        observed[mask],
        method=0,
    )
    if refined_matrix_raw is None:
        return _fallback(
            centers,
            len(reliable),
            "SYMBOL_LATTICE_REFINEMENT_FAILED",
            inlier_slots=inlier_slots,
        )
    refined_matrix = _normalise_homography(cast(NDArray[np.float64], refined_matrix_raw))
    if refined_matrix is None:
        return _fallback(
            centers,
            len(reliable),
            "SYMBOL_LATTICE_HOMOGRAPHY_SINGULAR",
            inlier_slots=inlier_slots,
        )

    projected = cast(
        NDArray[np.float64],
        cv2.perspectiveTransform(
            ideal.reshape((-1, 1, 2)),
            refined_matrix,
        ).reshape((-1, 2)),
    )
    residuals = cast(
        NDArray[np.float64],
        np.linalg.norm(projected - observed, axis=1),
    )
    inlier_residuals = residuals[mask]
    inlier_median = float(np.percentile(inlier_residuals, 50.0))
    inlier_p95 = float(np.percentile(inlier_residuals, 95.0))
    all_center_p95 = float(np.percentile(residuals, 95.0))
    if inlier_p95 > MAX_INLIER_P95_RESIDUAL_PX:
        return _fallback(
            centers,
            len(reliable),
            "SYMBOL_LATTICE_RESIDUAL_TOO_HIGH",
            inlier_slots=inlier_slots,
            inlier_median=inlier_median,
            inlier_p95=inlier_p95,
            all_center_p95=all_center_p95,
        )

    virtual_quad_array = _virtual_grid_quad(refined_matrix)
    if not _grid_geometry_is_plausible(
        refined_matrix,
        virtual_quad_array,
        geometry_guard,
    ):
        return _fallback(
            centers,
            len(reliable),
            "SYMBOL_LATTICE_VIRTUAL_GRID_IMPLAUSIBLE",
            inlier_slots=inlier_slots,
            inlier_median=inlier_median,
            inlier_p95=inlier_p95,
            all_center_p95=all_center_p95,
        )
    virtual_quad = cast(
        tuple[FloatPoint, FloatPoint, FloatPoint, FloatPoint],
        tuple((float(point[0]), float(point[1])) for point in virtual_quad_array),
    )
    return SymbolLatticeHomography(
        status="fitted",
        centers=centers,
        reliable_center_count=len(reliable),
        inlier_slots=inlier_slots,
        row_coverage=BOARD_ROWS,
        column_coverage=BOARD_COLUMNS,
        inlier_median_residual_px=inlier_median,
        inlier_p95_residual_px=inlier_p95,
        all_center_p95_residual_px=all_center_p95,
        ideal_to_observed_matrix=_matrix_tuple(refined_matrix),
        virtual_grid_quad=virtual_quad,
        fallback_reason=None,
    )


def estimate_symbol_lattice_homography(
    board_rgb: NDArray[np.uint8],
) -> SymbolLatticeHomography:
    """Locate all candidates and fit one guarded homography for the whole board."""

    centers = locate_symbol_centers(board_rgb)
    return fit_symbol_lattice_homography(centers)


def estimate_global_symbol_lattice_homography(
    board_rgb: NDArray[np.uint8],
) -> SymbolLatticeHomography:
    """Fit the guarded homography from globally assigned symbol candidates."""

    assignment = locate_global_symbol_lattice(board_rgb)
    result = fit_symbol_lattice_homography(
        assignment.centers,
        geometry_guard=SOURCE_AWARE_GEOMETRY_GUARD,
    )
    fallback_reason = (
        assignment.fallback_reason if assignment.status == "fallback" else result.fallback_reason
    )
    return replace(
        result,
        fallback_reason=fallback_reason,
        homography_version=GLOBAL_HOMOGRAPHY_VERSION,
        locator_version=LOCATOR_VERSION,
        global_candidate_count=len(assignment.candidates),
        global_assigned_candidate_count=assignment.assigned_candidate_count,
        global_column_bases=assignment.column_bases,
        global_row_bases=assignment.row_bases,
    )


__all__ = [
    "EXPANDED_FRAME_GEOMETRY_GUARD",
    "GLOBAL_HOMOGRAPHY_VERSION",
    "HOMOGRAPHY_VERSION",
    "LatticeGeometryGuard",
    "MAX_INLIER_P95_RESIDUAL_PX",
    "MAX_VIRTUAL_CORNER_MARGIN_PX",
    "MIN_INLIERS",
    "MIN_RELIABLE_CENTERS",
    "RANSAC_REPROJECTION_THRESHOLD_PX",
    "SOURCE_AWARE_GEOMETRY_GUARD",
    "FloatPoint",
    "Matrix3x3",
    "SymbolLatticeHomography",
    "estimate_global_symbol_lattice_homography",
    "estimate_symbol_lattice_homography",
    "fit_symbol_lattice_homography",
    "ideal_lattice_points",
    "project_points",
]
