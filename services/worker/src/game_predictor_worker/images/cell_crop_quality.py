"""Deterministic per-cell eligibility gate for symbol training crops."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

import cv2
import numpy as np
from numpy.typing import NDArray

QUALITY_GATE_VERSION = "cell-crop-quality-gate-v2-inner-columns-bootstrap"
MIN_CENTER_CONFIDENCE = 0.34
MIN_COMPONENT_AREA_PX = 24
MIN_PRIMARY_AREA_FRACTION = 0.035
MAX_CENTER_OFFSET_RATIO = 0.28
MAX_EXTRA_TO_PRIMARY_RATIO = 0.55
BORDER_WIDTH_PX = 3
EDGE_COLUMNS_TRAINING_ALLOWED = False

CellCropQualityStatus = Literal[
    "eligible",
    "clipped",
    "occluded",
    "interface_contaminated",
    "uncertain",
]


@dataclass(frozen=True, slots=True)
class CellCropQuality:
    status: CellCropQualityStatus
    reasons: tuple[str, ...]
    center_confidence: float
    center_offset_ratio: float | None
    primary_area_fraction: float
    extra_area_fraction: float
    primary_touches_border: bool
    side_border_foreground_fraction: float

    @property
    def training_eligible(self) -> bool:
        return self.status == "eligible"

    def to_dict(self) -> dict[str, object]:
        return {
            "centerConfidence": round(self.center_confidence, 6),
            "centerOffsetRatio": (
                None if self.center_offset_ratio is None else round(self.center_offset_ratio, 6)
            ),
            "extraAreaFraction": round(self.extra_area_fraction, 6),
            "gateVersion": QUALITY_GATE_VERSION,
            "primaryAreaFraction": round(self.primary_area_fraction, 6),
            "primaryTouchesBorder": self.primary_touches_border,
            "reasons": list(self.reasons),
            "sideBorderForegroundFraction": round(
                self.side_border_foreground_fraction,
                6,
            ),
            "status": self.status,
            "trainingEligible": self.training_eligible,
        }


def _normalise(values: NDArray[np.float32]) -> NDArray[np.float32]:
    low, high = np.percentile(values, (40.0, 96.0))
    span = float(high - low)
    if span < 1e-6:
        return np.zeros_like(values)
    return cast(NDArray[np.float32], np.clip((values - low) / span, 0.0, 1.0))


def _foreground_mask(rgb: NDArray[np.uint8]) -> NDArray[np.uint8]:
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    corner = max(4, min(rgb.shape[:2]) // 9)
    samples = np.concatenate(
        (
            lab[:corner, :corner].reshape((-1, 3)),
            lab[:corner, -corner:].reshape((-1, 3)),
            lab[-corner:, :corner].reshape((-1, 3)),
            lab[-corner:, -corner:].reshape((-1, 3)),
        ),
        axis=0,
    )
    background = np.median(samples, axis=0)
    colour_distance = cast(
        NDArray[np.float32],
        np.linalg.norm(lab - background, axis=2).astype(np.float32),
    )
    gradient_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gradient_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    gradient = cast(NDArray[np.float32], cv2.magnitude(gradient_x, gradient_y))
    saliency = 0.78 * _normalise(colour_distance) + 0.22 * _normalise(gradient)
    threshold = max(0.36, float(np.percentile(saliency, 68.0)))
    mask = np.where(saliency >= threshold, 255, 0).astype(np.uint8)
    kernel = np.ones((3, 3), dtype=np.uint8)
    mask = cast(
        NDArray[np.uint8],
        cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel),
    )
    return cast(
        NDArray[np.uint8],
        cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), dtype=np.uint8)),
    )


def assess_cell_crop(
    rgb: NDArray[np.uint8],
    *,
    expected_center_x: float,
    expected_center_y: float,
    center_confidence: float,
    edge_column: bool,
) -> CellCropQuality:
    """Classify whether one crop is safe as a classifier training observation."""

    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
        raise ValueError("Cell quality input must be an RGB uint8 image.")
    height, width = rgb.shape[:2]
    if height < 20 or width < 20:
        raise ValueError("Cell quality input must be at least 20 × 20.")
    if not (0.0 <= expected_center_x < width and 0.0 <= expected_center_y < height):
        raise ValueError("Expected center must stay inside the cell crop.")
    if not 0.0 <= center_confidence <= 1.0:
        raise ValueError("Center confidence must be between 0 and 1.")

    mask = _foreground_mask(rgb)
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(
        mask,
        connectivity=8,
    )
    components: list[tuple[int, int, float, float]] = []
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < MIN_COMPONENT_AREA_PX:
            continue
        centroid_x = float(centroids[label, 0])
        centroid_y = float(centroids[label, 1])
        distance = float(
            np.hypot(
                centroid_x - expected_center_x,
                centroid_y - expected_center_y,
            )
        )
        components.append((label, area, distance, float(area) / mask.size))

    if not components:
        status: CellCropQualityStatus = (
            "uncertain" if center_confidence < MIN_CENTER_CONFIDENCE else "occluded"
        )
        return CellCropQuality(
            status=status,
            reasons=(
                "CELL_FOREGROUND_NOT_FOUND"
                if status == "uncertain"
                else "CELL_VISIBLE_FRAGMENT_TOO_SMALL",
            ),
            center_confidence=center_confidence,
            center_offset_ratio=None,
            primary_area_fraction=0.0,
            extra_area_fraction=0.0,
            primary_touches_border=False,
            side_border_foreground_fraction=0.0,
        )

    primary_label, _, _, primary_fraction = min(
        components,
        key=lambda item: (item[2], -item[1]),
    )
    primary_centroid = centroids[primary_label]
    diagonal = float(np.hypot(width, height))
    center_offset_ratio = float(
        np.hypot(
            float(primary_centroid[0]) - expected_center_x,
            float(primary_centroid[1]) - expected_center_y,
        )
        / diagonal
    )
    primary = labels == primary_label
    center_band_top = max(0, int(round(expected_center_y - height * 0.28)))
    center_band_bottom = min(
        height,
        int(round(expected_center_y + height * 0.28)) + 1,
    )
    primary_touches_border = bool(
        np.any(primary[center_band_top:center_band_bottom, :BORDER_WIDTH_PX])
        or np.any(primary[center_band_top:center_band_bottom, -BORDER_WIDTH_PX:])
    )
    side_border_pixels = np.concatenate(
        (
            mask[center_band_top:center_band_bottom, :BORDER_WIDTH_PX].reshape(-1),
            mask[center_band_top:center_band_bottom, -BORDER_WIDTH_PX:].reshape(-1),
        )
    )
    side_border_foreground_fraction = float(
        np.count_nonzero(side_border_pixels) / side_border_pixels.size
    )
    extra_fraction = float(
        sum(fraction for label, _, _, fraction in components if label != primary_label)
    )

    if center_confidence < MIN_CENTER_CONFIDENCE:
        return CellCropQuality(
            status="uncertain",
            reasons=("CELL_CENTER_CONFIDENCE_LOW",),
            center_confidence=center_confidence,
            center_offset_ratio=center_offset_ratio,
            primary_area_fraction=primary_fraction,
            extra_area_fraction=extra_fraction,
            primary_touches_border=primary_touches_border,
            side_border_foreground_fraction=side_border_foreground_fraction,
        )
    if primary_fraction < MIN_PRIMARY_AREA_FRACTION:
        return CellCropQuality(
            status="occluded",
            reasons=("CELL_PRIMARY_FOREGROUND_TOO_SMALL",),
            center_confidence=center_confidence,
            center_offset_ratio=center_offset_ratio,
            primary_area_fraction=primary_fraction,
            extra_area_fraction=extra_fraction,
            primary_touches_border=primary_touches_border,
            side_border_foreground_fraction=side_border_foreground_fraction,
        )
    if primary_touches_border or center_offset_ratio > MAX_CENTER_OFFSET_RATIO:
        reasons = []
        if primary_touches_border:
            reasons.append("CELL_PRIMARY_TOUCHES_BORDER")
        if center_offset_ratio > MAX_CENTER_OFFSET_RATIO:
            reasons.append("CELL_PRIMARY_CENTER_DISPLACED")
        return CellCropQuality(
            status="clipped",
            reasons=tuple(reasons),
            center_confidence=center_confidence,
            center_offset_ratio=center_offset_ratio,
            primary_area_fraction=primary_fraction,
            extra_area_fraction=extra_fraction,
            primary_touches_border=primary_touches_border,
            side_border_foreground_fraction=side_border_foreground_fraction,
        )
    if extra_fraction > primary_fraction * MAX_EXTRA_TO_PRIMARY_RATIO:
        return CellCropQuality(
            status="interface_contaminated" if edge_column else "uncertain",
            reasons=(
                "CELL_EDGE_EXTRA_FOREGROUND" if edge_column else "CELL_MULTIPLE_FOREGROUND_REGIONS",
            ),
            center_confidence=center_confidence,
            center_offset_ratio=center_offset_ratio,
            primary_area_fraction=primary_fraction,
            extra_area_fraction=extra_fraction,
            primary_touches_border=primary_touches_border,
            side_border_foreground_fraction=side_border_foreground_fraction,
        )
    if edge_column and not EDGE_COLUMNS_TRAINING_ALLOWED:
        return CellCropQuality(
            status="uncertain",
            reasons=("CELL_EDGE_COLUMN_BOOTSTRAP_QUARANTINE",),
            center_confidence=center_confidence,
            center_offset_ratio=center_offset_ratio,
            primary_area_fraction=primary_fraction,
            extra_area_fraction=extra_fraction,
            primary_touches_border=primary_touches_border,
            side_border_foreground_fraction=side_border_foreground_fraction,
        )
    return CellCropQuality(
        status="eligible",
        reasons=(),
        center_confidence=center_confidence,
        center_offset_ratio=center_offset_ratio,
        primary_area_fraction=primary_fraction,
        extra_area_fraction=extra_fraction,
        primary_touches_border=primary_touches_border,
        side_border_foreground_fraction=side_border_foreground_fraction,
    )


__all__ = [
    "EDGE_COLUMNS_TRAINING_ALLOWED",
    "QUALITY_GATE_VERSION",
    "CellCropQuality",
    "CellCropQualityStatus",
    "assess_cell_crop",
]
