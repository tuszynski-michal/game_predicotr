"""Fixed-padding crops rectified by the guarded whole-lattice homography."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from .rectification import BOARD_COLUMNS, BOARD_HEIGHT, BOARD_ROWS, BOARD_WIDTH
from .symbol_lattice_homography import (
    FloatPoint,
    SymbolLatticeHomography,
    estimate_symbol_lattice_homography,
    project_points,
)

CROPPER_VERSION = "board-cell-crops-v12-projective-lattice-fixed-padding-preflight-v1"
GRID_VERSION = "projective-lattice-fixed-padding-grid-v1"
FIXED_PADDING_PX = 10
CELL_OUTPUT_SIZE = 90
REQUIRED_SUPPORT_FRACTION = 1.0


@dataclass(frozen=True, slots=True)
class ProjectiveLatticeCell:
    row_index: int
    column_index: int
    canonical_bounds: tuple[int, int, int, int]
    observed_quad: tuple[FloatPoint, FloatPoint, FloatPoint, FloatPoint]
    support_fraction: float
    rgb: NDArray[np.uint8]

    def to_dict(self) -> dict[str, object]:
        left, top, right, bottom = self.canonical_bounds
        return {
            "canonicalBounds": {
                "bottomExclusive": bottom,
                "left": left,
                "rightExclusive": right,
                "top": top,
            },
            "columnIndex": self.column_index,
            "observedQuad": [{"x": round(x, 4), "y": round(y, 4)} for x, y in self.observed_quad],
            "rowIndex": self.row_index,
            "supportFraction": round(self.support_fraction, 6),
        }


@dataclass(frozen=True, slots=True)
class ProjectiveLatticeCropResult:
    status: Literal["cropped", "fallback"]
    homography: SymbolLatticeHomography
    board_rgb: NDArray[np.uint8] | None
    grid_overlay_rgb: NDArray[np.uint8] | None
    observed_overlay_rgb: NDArray[np.uint8]
    support_mask: NDArray[np.uint8] | None
    cells: tuple[ProjectiveLatticeCell, ...]
    minimum_support_fraction: float | None
    fallback_reason: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "cellCount": len(self.cells),
            "cropperVersion": CROPPER_VERSION,
            "fallbackReason": self.fallback_reason,
            "fixedPaddingPx": FIXED_PADDING_PX,
            "gridVersion": GRID_VERSION,
            "homography": self.homography.to_dict(),
            "minimumSupportFraction": (
                None
                if self.minimum_support_fraction is None
                else round(self.minimum_support_fraction, 6)
            ),
            "outputCellHeight": CELL_OUTPUT_SIZE,
            "outputCellWidth": CELL_OUTPUT_SIZE,
            "status": self.status,
        }


def _empty_observed_overlay(
    expanded_board_rgb: NDArray[np.uint8],
) -> NDArray[np.uint8]:
    return expanded_board_rgb.copy()


def _draw_observed_grid(
    expanded_board_rgb: NDArray[np.uint8],
    homography: SymbolLatticeHomography,
) -> NDArray[np.uint8]:
    matrix = homography.ideal_to_observed_matrix
    overlay = expanded_board_rgb.copy()
    if matrix is not None:
        for column in range(BOARD_COLUMNS + 1):
            projected = project_points(
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
                tuple(int(round(value)) for value in projected[0]),
                tuple(int(round(value)) for value in projected[1]),
                (30, 225, 245),
                2,
                cv2.LINE_AA,
            )
        for row in range(BOARD_ROWS + 1):
            projected = project_points(
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
                tuple(int(round(value)) for value in projected[0]),
                tuple(int(round(value)) for value in projected[1]),
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


def _observed_cell_quad(
    bounds: tuple[int, int, int, int],
    matrix: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ],
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
        matrix,
    )
    return cast(
        tuple[FloatPoint, FloatPoint, FloatPoint, FloatPoint],
        tuple((float(point[0]), float(point[1])) for point in projected),
    )


def _quad_is_supported(
    quad: tuple[FloatPoint, FloatPoint, FloatPoint, FloatPoint],
) -> bool:
    return all(0.0 <= x <= BOARD_WIDTH - 1 and 0.0 <= y <= BOARD_HEIGHT - 1 for x, y in quad)


def _fallback(
    expanded_board_rgb: NDArray[np.uint8],
    homography: SymbolLatticeHomography,
    reason: str,
    *,
    observed_overlay: NDArray[np.uint8] | None = None,
    board_rgb: NDArray[np.uint8] | None = None,
    support_mask: NDArray[np.uint8] | None = None,
    cells: tuple[ProjectiveLatticeCell, ...] = (),
    minimum_support_fraction: float | None = None,
) -> ProjectiveLatticeCropResult:
    return ProjectiveLatticeCropResult(
        status="fallback",
        homography=homography,
        board_rgb=board_rgb,
        grid_overlay_rgb=None,
        observed_overlay_rgb=(
            observed_overlay
            if observed_overlay is not None
            else _empty_observed_overlay(expanded_board_rgb)
        ),
        support_mask=support_mask,
        cells=cells,
        minimum_support_fraction=minimum_support_fraction,
        fallback_reason=reason,
    )


def build_projective_lattice_crops(
    expanded_board_rgb: NDArray[np.uint8],
) -> ProjectiveLatticeCropResult:
    """Rectify one expanded board and crop only fully source-supported cells."""

    if (
        expanded_board_rgb.shape != (BOARD_HEIGHT, BOARD_WIDTH, 3)
        or expanded_board_rgb.dtype != np.uint8
    ):
        raise ValueError("Expanded board must be RGB uint8 500 × 300.")
    homography = estimate_symbol_lattice_homography(expanded_board_rgb)
    observed_overlay = _draw_observed_grid(expanded_board_rgb, homography)
    matrix_value = homography.ideal_to_observed_matrix
    if homography.status != "fitted" or matrix_value is None:
        return _fallback(
            expanded_board_rgb,
            homography,
            homography.fallback_reason or "PROJECTIVE_LATTICE_HOMOGRAPHY_FAILED",
            observed_overlay=observed_overlay,
        )
    ideal_to_observed = np.asarray(matrix_value, dtype=np.float64)
    try:
        observed_to_ideal = np.linalg.inv(ideal_to_observed)
    except np.linalg.LinAlgError:
        return _fallback(
            expanded_board_rgb,
            homography,
            "PROJECTIVE_LATTICE_HOMOGRAPHY_SINGULAR",
            observed_overlay=observed_overlay,
        )
    rectified = cast(
        NDArray[np.uint8],
        cv2.warpPerspective(
            expanded_board_rgb,
            observed_to_ideal,
            (BOARD_WIDTH, BOARD_HEIGHT),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0),
        ),
    )
    source_support = np.full((BOARD_HEIGHT, BOARD_WIDTH), 255, dtype=np.uint8)
    support_mask = cast(
        NDArray[np.uint8],
        cv2.warpPerspective(
            source_support,
            observed_to_ideal,
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
            observed_quad = _observed_cell_quad(bounds, matrix_value)
            if not _quad_is_supported(observed_quad):
                return _fallback(
                    expanded_board_rgb,
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
                    expanded_board_rgb,
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
                    observed_quad=observed_quad,
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
    overlay = rectified.copy()
    for cell in cells:
        left, top, right, bottom = cell.canonical_bounds
        cv2.rectangle(
            overlay,
            (left, top),
            (right - 1, bottom - 1),
            (30, 235, 90),
            2,
            cv2.LINE_AA,
        )
    return ProjectiveLatticeCropResult(
        status="cropped",
        homography=homography,
        board_rgb=rectified,
        grid_overlay_rgb=overlay,
        observed_overlay_rgb=observed_overlay,
        support_mask=support_mask,
        cells=tuple(cells),
        minimum_support_fraction=minimum_support,
        fallback_reason=None,
    )


__all__ = [
    "CELL_OUTPUT_SIZE",
    "CROPPER_VERSION",
    "FIXED_PADDING_PX",
    "GRID_VERSION",
    "REQUIRED_SUPPORT_FRACTION",
    "ProjectiveLatticeCell",
    "ProjectiveLatticeCropResult",
    "build_projective_lattice_crops",
]
