"""Source-aware fixed-padding crops from a globally assigned symbol lattice."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from .geometry import Point, Quad
from .projective_lattice_crops import ProjectiveLatticeCell
from .rectification import BOARD_COLUMNS, BOARD_HEIGHT, BOARD_ROWS, BOARD_WIDTH
from .symbol_grid_refinement import rectify_board
from .symbol_lattice_homography import (
    FloatPoint,
    Matrix3x3,
    SymbolLatticeHomography,
    estimate_global_symbol_lattice_homography,
    project_points,
)

CROPPER_VERSION = (
    "board-cell-crops-v13-global-lattice-source-aware-fixed-padding-preflight-v1"
)
GRID_VERSION = "global-lattice-source-aware-fixed-padding-grid-v1"
BOUNDING_FALLBACK_CROPPER_VERSION = (
    "board-cell-crops-v14-global-lattice-source-aware-bbox-analysis-fallback-v1"
)
BOUNDING_FALLBACK_GRID_VERSION = (
    "global-lattice-source-aware-bbox-analysis-fallback-grid-v1"
)
BOUNDING_FALLBACK_PAD_X_RATIO = 0.06
BOUNDING_FALLBACK_PAD_Y_RATIO = 0.04
FIXED_PADDING_PX = 10
CELL_OUTPUT_SIZE = 90
REQUIRED_SUPPORT_FRACTION = 1.0


@dataclass(frozen=True, slots=True)
class SourceProjectiveLatticeCropResult:
    status: Literal["cropped", "fallback"]
    homography: SymbolLatticeHomography
    board_rgb: NDArray[np.uint8] | None
    grid_overlay_rgb: NDArray[np.uint8] | None
    observed_overlay_rgb: NDArray[np.uint8]
    support_mask: NDArray[np.uint8] | None
    cells: tuple[ProjectiveLatticeCell, ...]
    minimum_support_fraction: float | None
    fallback_reason: str | None
    cropper_version: str = CROPPER_VERSION
    grid_version: str = GRID_VERSION
    analysis_frame_source: str = "projective-expanded-quad"
    primary_fallback_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "analysisFrameSource": self.analysis_frame_source,
            "cellCount": len(self.cells),
            "cropperVersion": self.cropper_version,
            "fallbackReason": self.fallback_reason,
            "fixedPaddingPx": FIXED_PADDING_PX,
            "gridVersion": self.grid_version,
            "homography": self.homography.to_dict(),
            "minimumSupportFraction": (
                None
                if self.minimum_support_fraction is None
                else round(self.minimum_support_fraction, 6)
            ),
            "outputCellHeight": CELL_OUTPUT_SIZE,
            "outputCellWidth": CELL_OUTPUT_SIZE,
            "primaryFallbackReason": self.primary_fallback_reason,
            "status": self.status,
        }


def _draw_analysis_grid(
    analysis_board_rgb: NDArray[np.uint8],
    homography: SymbolLatticeHomography,
) -> NDArray[np.uint8]:
    overlay = analysis_board_rgb.copy()
    matrix = homography.ideal_to_observed_matrix
    if matrix is not None:
        for column in range(BOARD_COLUMNS + 1):
            line = project_points(
                np.asarray(
                    (
                        (column * 100.0, 0.0),
                        (column * 100.0, float(BOARD_HEIGHT)),
                    ),
                    dtype=np.float64,
                ),
                matrix,
            )
            cv2.line(
                overlay,
                tuple(int(round(value)) for value in line[0]),
                tuple(int(round(value)) for value in line[1]),
                (30, 225, 245),
                2,
                cv2.LINE_AA,
            )
        for row in range(BOARD_ROWS + 1):
            line = project_points(
                np.asarray(
                    (
                        (0.0, row * 100.0),
                        (float(BOARD_WIDTH), row * 100.0),
                    ),
                    dtype=np.float64,
                ),
                matrix,
            )
            cv2.line(
                overlay,
                tuple(int(round(value)) for value in line[0]),
                tuple(int(round(value)) for value in line[1]),
                (30, 225, 245),
                2,
                cv2.LINE_AA,
            )
    inlier_slots = set(homography.inlier_slots)
    for center in homography.centers:
        colour = (
            (35, 235, 80)
            if (center.row_index, center.column_index) in inlier_slots
            else (245, 70, 45)
        )
        cv2.circle(
            overlay,
            (int(round(center.x)), int(round(center.y))),
            5,
            colour,
            2,
            cv2.LINE_AA,
        )
    return overlay


def _canonical_bounds(row: int, column: int) -> tuple[int, int, int, int]:
    return (
        column * 100 + FIXED_PADDING_PX,
        row * 100 + FIXED_PADDING_PX,
        (column + 1) * 100 - FIXED_PADDING_PX,
        (row + 1) * 100 - FIXED_PADDING_PX,
    )


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


def _source_cell_quad(
    bounds: tuple[int, int, int, int],
    ideal_to_source: Matrix3x3,
) -> tuple[FloatPoint, FloatPoint, FloatPoint, FloatPoint]:
    left, top, right, bottom = bounds
    projected = project_points(
        np.asarray(
            (
                (float(left), float(top)),
                (float(right - 1), float(top)),
                (float(right - 1), float(bottom - 1)),
                (float(left), float(bottom - 1)),
            ),
            dtype=np.float64,
        ),
        ideal_to_source,
    )
    return cast(
        tuple[FloatPoint, FloatPoint, FloatPoint, FloatPoint],
        tuple((float(point[0]), float(point[1])) for point in projected),
    )


def _quad_is_inside_source(
    quad: tuple[FloatPoint, FloatPoint, FloatPoint, FloatPoint],
    *,
    source_width: int,
    source_height: int,
) -> bool:
    return all(
        0.0 <= x <= source_width - 1 and 0.0 <= y <= source_height - 1
        for x, y in quad
    )


def _fallback(
    analysis_board_rgb: NDArray[np.uint8],
    homography: SymbolLatticeHomography,
    reason: str,
    *,
    observed_overlay: NDArray[np.uint8] | None = None,
    board_rgb: NDArray[np.uint8] | None = None,
    support_mask: NDArray[np.uint8] | None = None,
    cells: tuple[ProjectiveLatticeCell, ...] = (),
    minimum_support_fraction: float | None = None,
) -> SourceProjectiveLatticeCropResult:
    return SourceProjectiveLatticeCropResult(
        status="fallback",
        homography=homography,
        board_rgb=board_rgb,
        grid_overlay_rgb=None,
        observed_overlay_rgb=(
            analysis_board_rgb.copy()
            if observed_overlay is None
            else observed_overlay
        ),
        support_mask=support_mask,
        cells=cells,
        minimum_support_fraction=minimum_support_fraction,
        fallback_reason=reason,
    )


def build_source_projective_lattice_crops(
    source_rgb: NDArray[np.uint8],
    analysis_quad: Quad,
) -> SourceProjectiveLatticeCropResult:
    """Fit on an analysis plane, then sample every cell from the real source."""

    if source_rgb.ndim != 3 or source_rgb.shape[2] != 3 or source_rgb.dtype != np.uint8:
        raise ValueError("Source must be an RGB uint8 image.")
    analysis_board, source_to_analysis = rectify_board(source_rgb, analysis_quad)
    homography = estimate_global_symbol_lattice_homography(analysis_board)
    observed_overlay = _draw_analysis_grid(analysis_board, homography)
    matrix_value = homography.ideal_to_observed_matrix
    if homography.status != "fitted" or matrix_value is None:
        return _fallback(
            analysis_board,
            homography,
            homography.fallback_reason or "PROJECTIVE_LATTICE_HOMOGRAPHY_FAILED",
            observed_overlay=observed_overlay,
        )
    try:
        analysis_to_source = np.linalg.inv(source_to_analysis)
    except np.linalg.LinAlgError:
        return _fallback(
            analysis_board,
            homography,
            "PROJECTIVE_LATTICE_ANALYSIS_TRANSFORM_SINGULAR",
            observed_overlay=observed_overlay,
        )
    ideal_to_source_array = cast(
        NDArray[np.float64],
        analysis_to_source @ np.asarray(matrix_value, dtype=np.float64),
    )
    ideal_to_source = _matrix_tuple(ideal_to_source_array)
    try:
        source_to_ideal = np.linalg.inv(ideal_to_source_array)
    except np.linalg.LinAlgError:
        return _fallback(
            analysis_board,
            homography,
            "PROJECTIVE_LATTICE_HOMOGRAPHY_SINGULAR",
            observed_overlay=observed_overlay,
        )

    rectified = cast(
        NDArray[np.uint8],
        cv2.warpPerspective(
            source_rgb,
            source_to_ideal,
            (BOARD_WIDTH, BOARD_HEIGHT),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0),
        ),
    )
    source_height, source_width = source_rgb.shape[:2]
    source_support = np.full((source_height, source_width), 255, dtype=np.uint8)
    support_mask = cast(
        NDArray[np.uint8],
        cv2.warpPerspective(
            source_support,
            source_to_ideal,
            (BOARD_WIDTH, BOARD_HEIGHT),
            flags=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        ),
    )
    cells: list[ProjectiveLatticeCell] = []
    minimum_support = 1.0
    for row in range(BOARD_ROWS):
        for column in range(BOARD_COLUMNS):
            bounds = _canonical_bounds(row, column)
            source_quad = _source_cell_quad(bounds, ideal_to_source)
            if not _quad_is_inside_source(
                source_quad,
                source_width=source_width,
                source_height=source_height,
            ):
                return _fallback(
                    analysis_board,
                    homography,
                    "PROJECTIVE_LATTICE_CELL_OUTSIDE_SOURCE",
                    observed_overlay=observed_overlay,
                    board_rgb=rectified,
                    support_mask=support_mask,
                    cells=tuple(cells),
                    minimum_support_fraction=minimum_support,
                )
            left, top, right, bottom = bounds
            support = support_mask[top:bottom, left:right]
            support_fraction = float(np.count_nonzero(support) / support.size)
            minimum_support = min(minimum_support, support_fraction)
            if support_fraction < REQUIRED_SUPPORT_FRACTION:
                return _fallback(
                    analysis_board,
                    homography,
                    "PROJECTIVE_LATTICE_CELL_SUPPORT_INCOMPLETE",
                    observed_overlay=observed_overlay,
                    board_rgb=rectified,
                    support_mask=support_mask,
                    cells=tuple(cells),
                    minimum_support_fraction=minimum_support,
                )
            crop = rectified[top:bottom, left:right]
            cells.append(
                ProjectiveLatticeCell(
                    row_index=row,
                    column_index=column,
                    canonical_bounds=bounds,
                    observed_quad=source_quad,
                    support_fraction=support_fraction,
                    rgb=cast(
                        NDArray[np.uint8],
                        cv2.resize(
                            crop,
                            (CELL_OUTPUT_SIZE, CELL_OUTPUT_SIZE),
                            interpolation=cv2.INTER_AREA,
                        ),
                    ),
                )
            )
    grid_overlay = rectified.copy()
    for cell in cells:
        left, top, right, bottom = cell.canonical_bounds
        cv2.rectangle(
            grid_overlay,
            (left, top),
            (right - 1, bottom - 1),
            (30, 235, 90),
            2,
            cv2.LINE_AA,
        )
    return SourceProjectiveLatticeCropResult(
        status="cropped",
        homography=homography,
        board_rgb=rectified,
        grid_overlay_rgb=grid_overlay,
        observed_overlay_rgb=observed_overlay,
        support_mask=support_mask,
        cells=tuple(cells),
        minimum_support_fraction=minimum_support,
        fallback_reason=None,
    )


def _bounding_box_analysis_quad(
    bounding_box: tuple[int, int, int, int],
    *,
    source_width: int,
    source_height: int,
) -> Quad:
    x, y, width, height = bounding_box
    if width <= 0 or height <= 0:
        raise ValueError("Detector bounding box dimensions must be positive.")
    padding_x = round(width * BOUNDING_FALLBACK_PAD_X_RATIO)
    padding_y = round(height * BOUNDING_FALLBACK_PAD_Y_RATIO)
    left = max(0, x - padding_x)
    top = max(0, y - padding_y)
    right = min(source_width - 1, x + width - 1 + padding_x)
    bottom = min(source_height - 1, y + height - 1 + padding_y)
    if left >= right or top >= bottom:
        raise ValueError("Detector bounding box cannot form a valid analysis quad.")
    return (
        Point(left, top),
        Point(right, top),
        Point(right, bottom),
        Point(left, bottom),
    )


def build_bounding_fallback_source_projective_lattice_crops(
    source_rgb: NDArray[np.uint8],
    projective_analysis_quad: Quad,
    detector_bounding_box: tuple[int, int, int, int],
) -> SourceProjectiveLatticeCropResult:
    """Retry global assignment on a bounded box only after locator failure."""

    primary = build_source_projective_lattice_crops(
        source_rgb,
        projective_analysis_quad,
    )
    if primary.status == "cropped":
        return replace(
            primary,
            cropper_version=BOUNDING_FALLBACK_CROPPER_VERSION,
            grid_version=BOUNDING_FALLBACK_GRID_VERSION,
        )
    retryable_reasons = {
        "GLOBAL_SYMBOL_LATTICE_AXIS_ASSIGNMENT_FAILED",
        "GLOBAL_SYMBOL_LATTICE_INSUFFICIENT_ASSIGNMENTS",
        "GLOBAL_SYMBOL_LATTICE_INSUFFICIENT_COMPONENTS",
    }
    if primary.fallback_reason not in retryable_reasons:
        return replace(
            primary,
            cropper_version=BOUNDING_FALLBACK_CROPPER_VERSION,
            grid_version=BOUNDING_FALLBACK_GRID_VERSION,
        )
    source_height, source_width = source_rgb.shape[:2]
    bounding_quad = _bounding_box_analysis_quad(
        detector_bounding_box,
        source_width=source_width,
        source_height=source_height,
    )
    fallback = build_source_projective_lattice_crops(source_rgb, bounding_quad)
    return replace(
        fallback,
        cropper_version=BOUNDING_FALLBACK_CROPPER_VERSION,
        grid_version=BOUNDING_FALLBACK_GRID_VERSION,
        analysis_frame_source="detector-bounding-box-fallback",
        primary_fallback_reason=primary.fallback_reason,
    )


__all__ = [
    "BOUNDING_FALLBACK_CROPPER_VERSION",
    "BOUNDING_FALLBACK_GRID_VERSION",
    "BOUNDING_FALLBACK_PAD_X_RATIO",
    "BOUNDING_FALLBACK_PAD_Y_RATIO",
    "CELL_OUTPUT_SIZE",
    "CROPPER_VERSION",
    "FIXED_PADDING_PX",
    "GRID_VERSION",
    "REQUIRED_SUPPORT_FRACTION",
    "SourceProjectiveLatticeCropResult",
    "build_bounding_fallback_source_projective_lattice_crops",
    "build_source_projective_lattice_crops",
]
