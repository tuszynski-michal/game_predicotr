"""Symbol-aware refinement of a known 5 × 3 board lattice."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from .geometry import Point, Quad
from .rectification import (
    BOARD_COLUMNS,
    BOARD_HEIGHT,
    BOARD_ROWS,
    BOARD_WIDTH,
    DETECTOR_SYMBOL_AWARE_CROPPER_VERSION,
    SYMBOL_AWARE_AFFINE_CROPPER_VERSION,
    BoardCropResult,
    BoardGeometry,
    PageGeometry,
    PerspectiveBoardCellCropperV2,
    SymbolRefinementMetadata,
)

REFINER_VERSION = "symbol-grid-refiner-affine-v1"
MIN_CENTER_CONFIDENCE = 0.34
MIN_RELIABLE_CENTERS = 10
MIN_INLIERS = 7
MAX_RANSAC_RESIDUAL_PX = 12.0
MAX_REFINED_P95_PX = 12.5
MAX_CORNER_SHIFT_PX = 70.0
SOURCE_QUAD_SOURCE = "symbol-aware-projective-grid"


class SymbolGridRefinementError(ValueError):
    """Stable error for invalid refiner input."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class SymbolCenter:
    row_index: int
    column_index: int
    x: float
    y: float
    confidence: float

    def to_dict(self) -> dict[str, int | float]:
        return {
            "columnIndex": self.column_index,
            "confidence": round(self.confidence, 6),
            "rowIndex": self.row_index,
            "x": round(self.x, 4),
            "y": round(self.y, 4),
        }


@dataclass(frozen=True, slots=True)
class SymbolGridRefinement:
    status: Literal["refined", "fallback"]
    source_quad: Quad
    centers: tuple[SymbolCenter, ...]
    reliable_center_count: int
    inlier_count: int
    baseline_median_residual_px: float | None
    refined_median_residual_px: float | None
    refined_p95_residual_px: float | None
    all_center_p95_residual_px: float | None
    max_corner_shift_px: float | None
    fallback_reason: str | None

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "allCenterP95ResidualPx": _rounded_optional(self.all_center_p95_residual_px),
            "baselineMedianResidualPx": _rounded_optional(self.baseline_median_residual_px),
            "centers": [center.to_dict() for center in self.centers],
            "fallbackReason": self.fallback_reason,
            "inlierCount": self.inlier_count,
            "maxCornerShiftPx": _rounded_optional(self.max_corner_shift_px),
            "refinedMedianResidualPx": _rounded_optional(self.refined_median_residual_px),
            "refinedP95ResidualPx": _rounded_optional(self.refined_p95_residual_px),
            "refinerVersion": REFINER_VERSION,
            "reliableCenterCount": self.reliable_center_count,
            "sourceQuad": [point.to_dict() for point in self.source_quad],
            "status": self.status,
        }
        return value


def _rounded_optional(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def _quad_array(quad: Quad) -> NDArray[np.float32]:
    return np.asarray([(point.x, point.y) for point in quad], dtype=np.float32)


def _destination() -> NDArray[np.float32]:
    return np.asarray(
        (
            (0.0, 0.0),
            (BOARD_WIDTH - 1.0, 0.0),
            (BOARD_WIDTH - 1.0, BOARD_HEIGHT - 1.0),
            (0.0, BOARD_HEIGHT - 1.0),
        ),
        dtype=np.float32,
    )


def _validate_input(rgb_image: NDArray[np.uint8], source_quad: Quad) -> None:
    if rgb_image.ndim != 3 or rgb_image.shape[2] != 3 or rgb_image.dtype != np.uint8:
        raise SymbolGridRefinementError(
            "SYMBOL_GRID_INVALID_IMAGE",
            "Input must be an RGB uint8 image.",
        )
    image_height, image_width = rgb_image.shape[:2]
    if any(
        point.x < 0 or point.y < 0 or point.x >= image_width or point.y >= image_height
        for point in source_quad
    ):
        raise SymbolGridRefinementError(
            "SYMBOL_GRID_QUAD_OUT_OF_BOUNDS",
            "Source quad must stay inside the image.",
        )
    contour = _quad_array(source_quad).astype(np.int32)
    if not cv2.isContourConvex(contour) or abs(float(cv2.contourArea(contour))) < 100:
        raise SymbolGridRefinementError(
            "SYMBOL_GRID_QUAD_INVALID",
            "Source quad must be convex and non-degenerate.",
        )


def rectify_board(
    rgb_image: NDArray[np.uint8],
    source_quad: Quad,
) -> tuple[NDArray[np.uint8], NDArray[np.float64]]:
    """Rectify one board and return its source-to-canonical transform."""

    _validate_input(rgb_image, source_quad)
    matrix = cast(
        NDArray[np.float64],
        cv2.getPerspectiveTransform(_quad_array(source_quad), _destination()),
    )
    board = cast(
        NDArray[np.uint8],
        cv2.warpPerspective(
            rgb_image,
            matrix,
            (BOARD_WIDTH, BOARD_HEIGHT),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        ),
    )
    return board, matrix


def _normalise_plane(values: NDArray[np.float32]) -> NDArray[np.float32]:
    low, high = np.percentile(values, (35.0, 95.0))
    span = float(high - low)
    if span < 1e-6:
        return np.zeros_like(values)
    return cast(NDArray[np.float32], np.clip((values - low) / span, 0.0, 1.0))


def _slot_center(
    board_rgb: NDArray[np.uint8],
    *,
    row_index: int,
    column_index: int,
) -> SymbolCenter:
    slot_width = BOARD_WIDTH // BOARD_COLUMNS
    slot_height = BOARD_HEIGHT // BOARD_ROWS
    inset_x = 10
    inset_y = 10
    x0 = column_index * slot_width + inset_x
    y0 = row_index * slot_height + inset_y
    patch = board_rgb[
        y0 : (row_index + 1) * slot_height - inset_y,
        x0 : (column_index + 1) * slot_width - inset_x,
    ]
    lab = cv2.cvtColor(patch, cv2.COLOR_RGB2LAB).astype(np.float32)
    gray = cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY).astype(np.float32)
    height, width = gray.shape
    border_mask = np.zeros((height, width), dtype=np.uint8)
    border_mask[:8, :] = 1
    border_mask[-8:, :] = 1
    border_mask[:, :8] = 1
    border_mask[:, -8:] = 1
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
    expected_x = (width - 1.0) / 2.0
    expected_y = (height - 1.0) / 2.0
    sigma_x = width * 0.38
    sigma_y = height * 0.38
    prior = np.exp(
        -0.5 * (((xx - expected_x) / sigma_x) ** 2 + ((yy - expected_y) / sigma_y) ** 2)
    ).astype(np.float32)
    threshold = float(np.percentile(saliency, 62.0))
    foreground = saliency >= max(0.28, threshold)
    weights = np.where(foreground, saliency * prior, 0.0).astype(np.float32)
    mass = float(weights.sum())
    if mass <= 1e-6:
        local_x = expected_x
        local_y = expected_y
        confidence = 0.0
    else:
        local_x = float((weights * xx).sum() / mass)
        local_y = float((weights * yy).sum() / mass)
        distance = math.hypot(local_x - expected_x, local_y - expected_y)
        distance_score = max(0.0, 1.0 - distance / (min(width, height) * 0.45))
        contrast = float(
            np.clip(
                np.percentile(saliency, 90.0) - np.percentile(saliency, 45.0),
                0.0,
                1.0,
            )
        )
        foreground_fraction = float(np.count_nonzero(foreground) / foreground.size)
        fraction_score = max(0.0, 1.0 - abs(foreground_fraction - 0.30) / 0.30)
        confidence = float(
            np.clip(
                0.50 * contrast + 0.35 * distance_score + 0.15 * fraction_score,
                0.0,
                1.0,
            )
        )
    return SymbolCenter(
        row_index=row_index,
        column_index=column_index,
        x=x0 + local_x,
        y=y0 + local_y,
        confidence=confidence,
    )


def locate_symbol_centers(board_rgb: NDArray[np.uint8]) -> tuple[SymbolCenter, ...]:
    """Locate one foreground center inside every approximate logical slot."""

    if board_rgb.shape != (BOARD_HEIGHT, BOARD_WIDTH, 3) or board_rgb.dtype != np.uint8:
        raise SymbolGridRefinementError(
            "SYMBOL_GRID_BOARD_INVALID",
            "Rectified board must be RGB uint8 500 × 300.",
        )
    return tuple(
        _slot_center(
            board_rgb,
            row_index=row,
            column_index=column,
        )
        for row in range(BOARD_ROWS)
        for column in range(BOARD_COLUMNS)
    )


def _percentile(values: NDArray[np.float64], percentile: float) -> float:
    return float(np.percentile(values, percentile))


def _fallback(
    source_quad: Quad,
    centers: tuple[SymbolCenter, ...],
    *,
    reliable_count: int,
    reason: str,
    baseline_median: float | None = None,
    inlier_count: int = 0,
    refined_median: float | None = None,
    refined_p95: float | None = None,
    all_center_p95: float | None = None,
    max_corner_shift: float | None = None,
) -> SymbolGridRefinement:
    return SymbolGridRefinement(
        status="fallback",
        source_quad=source_quad,
        centers=centers,
        reliable_center_count=reliable_count,
        inlier_count=inlier_count,
        baseline_median_residual_px=baseline_median,
        refined_median_residual_px=refined_median,
        refined_p95_residual_px=refined_p95,
        all_center_p95_residual_px=all_center_p95,
        max_corner_shift_px=max_corner_shift,
        fallback_reason=reason,
    )


def refine_symbol_grid(
    rgb_image: NDArray[np.uint8],
    source_quad: Quad,
) -> SymbolGridRefinement:
    """Fit a guarded projective lattice from visual symbol centers."""

    board, source_to_canonical = rectify_board(rgb_image, source_quad)
    centers = locate_symbol_centers(board)
    reliable = tuple(center for center in centers if center.confidence >= MIN_CENTER_CONFIDENCE)
    if len(reliable) < MIN_RELIABLE_CENTERS:
        return _fallback(
            source_quad,
            centers,
            reliable_count=len(reliable),
            reason="SYMBOL_GRID_INSUFFICIENT_CENTERS",
        )
    row_coverage = {center.row_index for center in reliable}
    column_coverage = {center.column_index for center in reliable}
    if len(row_coverage) != BOARD_ROWS or len(column_coverage) != BOARD_COLUMNS:
        return _fallback(
            source_quad,
            centers,
            reliable_count=len(reliable),
            reason="SYMBOL_GRID_INSUFFICIENT_COVERAGE",
        )

    observed = np.asarray([(center.x, center.y) for center in reliable], dtype=np.float64)
    ideal = np.asarray(
        [
            (
                (center.column_index + 0.5) * (BOARD_WIDTH / BOARD_COLUMNS),
                (center.row_index + 0.5) * (BOARD_HEIGHT / BOARD_ROWS),
            )
            for center in reliable
        ],
        dtype=np.float64,
    )
    baseline_residuals = cast(
        NDArray[np.float64],
        np.linalg.norm(observed - ideal, axis=1),
    )
    affine, raw_mask = cv2.estimateAffine2D(
        observed,
        ideal,
        method=cv2.RANSAC,
        ransacReprojThreshold=MAX_RANSAC_RESIDUAL_PX,
        maxIters=2000,
        confidence=0.995,
        refineIters=10,
    )
    if affine is None or raw_mask is None or not np.isfinite(affine).all():
        return _fallback(
            source_quad,
            centers,
            reliable_count=len(reliable),
            reason="SYMBOL_GRID_HOMOGRAPHY_FAILED",
            baseline_median=_percentile(baseline_residuals, 50.0),
        )
    correction = np.vstack(
        (
            affine.astype(np.float64),
            np.asarray((0.0, 0.0, 1.0), dtype=np.float64),
        )
    )
    mask = raw_mask.reshape(-1).astype(bool)
    inlier_count = int(np.count_nonzero(mask))
    if inlier_count < MIN_INLIERS:
        return _fallback(
            source_quad,
            centers,
            reliable_count=len(reliable),
            reason="SYMBOL_GRID_INSUFFICIENT_INLIERS",
            baseline_median=_percentile(baseline_residuals, 50.0),
            inlier_count=inlier_count,
        )
    projected = cv2.perspectiveTransform(
        observed.astype(np.float32).reshape((-1, 1, 2)),
        correction.astype(np.float64),
    ).reshape((-1, 2))
    refined_residuals = cast(
        NDArray[np.float64],
        np.linalg.norm(projected.astype(np.float64) - ideal, axis=1),
    )
    refined_median = _percentile(refined_residuals[mask], 50.0)
    refined_p95 = _percentile(refined_residuals[mask], 95.0)
    all_center_p95 = _percentile(refined_residuals, 95.0)
    baseline_median = _percentile(baseline_residuals, 50.0)
    if refined_p95 > MAX_REFINED_P95_PX:
        return _fallback(
            source_quad,
            centers,
            reliable_count=len(reliable),
            reason="SYMBOL_GRID_RESIDUAL_TOO_HIGH",
            baseline_median=baseline_median,
            inlier_count=inlier_count,
            refined_median=refined_median,
            refined_p95=refined_p95,
            all_center_p95=all_center_p95,
        )

    refined_source_to_canonical = correction @ source_to_canonical
    try:
        canonical_to_source = np.linalg.inv(refined_source_to_canonical)
    except np.linalg.LinAlgError:
        return _fallback(
            source_quad,
            centers,
            reliable_count=len(reliable),
            reason="SYMBOL_GRID_TRANSFORM_SINGULAR",
            baseline_median=baseline_median,
            inlier_count=inlier_count,
            refined_median=refined_median,
            refined_p95=refined_p95,
            all_center_p95=all_center_p95,
        )
    refined_points = cv2.perspectiveTransform(
        _destination().reshape((-1, 1, 2)),
        canonical_to_source,
    ).reshape((-1, 2))
    initial_points = _quad_array(source_quad).astype(np.float64)
    canonical_corner_shift = cv2.perspectiveTransform(
        _destination().reshape((-1, 1, 2)),
        correction.astype(np.float64),
    ).reshape((-1, 2)) - _destination().astype(np.float64)
    max_shift = float(np.linalg.norm(canonical_corner_shift, axis=1).max())
    image_height, image_width = rgb_image.shape[:2]
    contour = refined_points.astype(np.float32)
    if (
        max_shift > MAX_CORNER_SHIFT_PX
        or not np.isfinite(refined_points).all()
        or not cv2.isContourConvex(contour.astype(np.int32))
        or abs(float(cv2.contourArea(contour))) < 100
        or np.any(refined_points[:, 0] < 0)
        or np.any(refined_points[:, 1] < 0)
        or np.any(refined_points[:, 0] >= image_width)
        or np.any(refined_points[:, 1] >= image_height)
    ):
        return _fallback(
            source_quad,
            centers,
            reliable_count=len(reliable),
            reason="SYMBOL_GRID_REFINED_QUAD_IMPLAUSIBLE",
            baseline_median=baseline_median,
            inlier_count=inlier_count,
            refined_median=refined_median,
            refined_p95=refined_p95,
            all_center_p95=all_center_p95,
            max_corner_shift=max_shift,
        )
    refined_quad = cast(
        Quad,
        tuple(
            Point(
                int(round(float(point[0]))),
                int(round(float(point[1]))),
            )
            for point in refined_points
        ),
    )
    if _quad_array(refined_quad).shape != initial_points.shape:
        raise AssertionError("Refined quad contract changed unexpectedly.")
    return SymbolGridRefinement(
        status="refined",
        source_quad=refined_quad,
        centers=centers,
        reliable_center_count=len(reliable),
        inlier_count=inlier_count,
        baseline_median_residual_px=baseline_median,
        refined_median_residual_px=refined_median,
        refined_p95_residual_px=refined_p95,
        all_center_p95_residual_px=all_center_p95,
        max_corner_shift_px=max_shift,
        fallback_reason=None,
    )


class PerspectiveBoardCellCropperV5SymbolAwareAffine(PerspectiveBoardCellCropperV2):
    """Fail-closed logical-slot cropper refined by the visible symbol lattice."""

    version = SYMBOL_AWARE_AFFINE_CROPPER_VERSION

    def crop(
        self,
        rgb_image: NDArray[np.uint8],
        geometry: PageGeometry,
    ) -> BoardCropResult:
        if geometry.status != "detected":
            return super().crop(rgb_image, geometry)
        refined_boards: list[BoardGeometry] = []
        for board in geometry.boards:
            refinement = refine_symbol_grid(rgb_image, board.quad)
            if (
                refinement.status != "refined"
                or refinement.baseline_median_residual_px is None
                or refinement.refined_median_residual_px is None
                or refinement.refined_p95_residual_px is None
            ):
                return BoardCropResult(
                    status="needs_review",
                    boards=(),
                    review_reasons=(
                        "SYMBOL_GRID_REFINEMENT_FAILED",
                        refinement.fallback_reason or "SYMBOL_GRID_REFINEMENT_UNKNOWN",
                    ),
                )
            refined_boards.append(
                BoardGeometry(
                    position_index=board.position_index,
                    quad=refinement.source_quad,
                    bounding_box=board.bounding_box,
                    source_quad_source=SOURCE_QUAD_SOURCE,
                    calibration_profile_id=board.calibration_profile_id,
                    calibration_profile_version=board.calibration_profile_version,
                    calibration_anchor_sequence_numbers=(board.calibration_anchor_sequence_numbers),
                    calibration_interpolation_weight=(board.calibration_interpolation_weight),
                    symbol_refinement=SymbolRefinementMetadata(
                        refiner_version=REFINER_VERSION,
                        reliable_center_count=refinement.reliable_center_count,
                        inlier_count=refinement.inlier_count,
                        baseline_median_residual_px=(refinement.baseline_median_residual_px),
                        refined_median_residual_px=(refinement.refined_median_residual_px),
                        refined_p95_residual_px=(refinement.refined_p95_residual_px),
                    ),
                )
            )
        return super().crop(
            rgb_image,
            PageGeometry(
                status="detected",
                image_width=geometry.image_width,
                image_height=geometry.image_height,
                boards=tuple(refined_boards),
                review_reasons=(),
            ),
        )


class PerspectiveBoardCellCropperV6DetectorSymbolAwareAffine(
    PerspectiveBoardCellCropperV5SymbolAwareAffine
):
    """Versioned detector-start variant; caller must not pre-calibrate geometry."""

    version = DETECTOR_SYMBOL_AWARE_CROPPER_VERSION


__all__ = [
    "REFINER_VERSION",
    "SOURCE_QUAD_SOURCE",
    "PerspectiveBoardCellCropperV5SymbolAwareAffine",
    "PerspectiveBoardCellCropperV6DetectorSymbolAwareAffine",
    "SymbolCenter",
    "SymbolGridRefinement",
    "SymbolGridRefinementError",
    "locate_symbol_centers",
    "rectify_board",
    "refine_symbol_grid",
]
