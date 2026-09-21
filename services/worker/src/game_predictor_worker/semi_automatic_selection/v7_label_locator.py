"""Versioned source-local numeric-label crops for 3x3 V7 page photographs.

The legacy V1 locator deliberately keeps its whole-image coordinates.  V2 uses
only image-local text-component geometry and a regular 3x3 lattice.  It never
consults an expected range, source order, game symbols or border colour.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
from typing import Protocol

import cv2
import numpy as np
from numpy.typing import NDArray

from .v7_range_proof import V7LabelEvidence


class V7LabelRecognitionBackend(Protocol):
    def recognize_many(self, crops: list[NDArray[np.uint8]]) -> tuple[object, ...]:
        """Return recognition-like values with ``raw_text`` and ``confidence``."""


@dataclass(frozen=True, slots=True)
class V7GridLabelLocatorConfig:
    """Immutable whole-image V1 crop configuration kept for historical profiles."""

    centers: tuple[tuple[float, float], ...] = (
        (0.26, 0.36),
        (0.50, 0.37),
        (0.72, 0.40),
        (0.26, 0.55),
        (0.50, 0.57),
        (0.72, 0.60),
        (0.25, 0.75),
        (0.45, 0.77),
        (0.72, 0.80),
    )
    width_ratios: tuple[float, ...] = (0.14,) * 6 + (0.18, 0.20, 0.16)
    height_ratio: float = 0.05
    minimum_aspect_ratio: float = 1.0
    maximum_aspect_ratio: float = 1.8
    position_confidence: float = 0.0

    def __post_init__(self) -> None:
        if (
            len(self.centers) != 9
            or len(self.width_ratios) != 9
            or any(not 0 < x < 1 or not 0 < y < 1 for x, y in self.centers)
            or any(not 0 < value < 1 for value in self.width_ratios)
            or not 0 < self.height_ratio < 1
            or not 0 < self.minimum_aspect_ratio < self.maximum_aspect_ratio
            or not 0 <= self.position_confidence <= 1
        ):
            raise ValueError("V7 grid label locator configuration is invalid.")

    def as_dict(self) -> dict[str, object]:
        """Keep the V1 profile payload byte-for-byte compatible."""
        return {
            "centers": [list(center) for center in self.centers],
            "heightRatio": self.height_ratio,
            "maximumAspectRatio": self.maximum_aspect_ratio,
            "minimumAspectRatio": self.minimum_aspect_ratio,
            "positionConfidence": self.position_confidence,
            "widthRatios": list(self.width_ratios),
        }


@dataclass(frozen=True, slots=True)
class V7DynamicGridLabelLocatorConfig:
    """V2 policy expressed in local grid-spacing units, never image coordinates."""

    crop_width_spacing_ratio: float = 0.58
    crop_height_spacing_ratio: float = 0.34
    minimum_aspect_ratio: float = 1.0
    maximum_aspect_ratio: float = 1.8
    minimum_lattice_margin: float = 0.08
    maximum_lattice_residual_ratio: float = 0.10
    position_confidence: float = 0.0

    def __post_init__(self) -> None:
        if (
            not 0.2 <= self.crop_width_spacing_ratio <= 1.2
            or not 0.15 <= self.crop_height_spacing_ratio <= 1.0
            or not 0 < self.minimum_aspect_ratio < self.maximum_aspect_ratio
            or not 0 <= self.minimum_lattice_margin < 1
            or not 0 < self.maximum_lattice_residual_ratio <= 0.25
            or not 0 <= self.position_confidence <= 1
        ):
            raise ValueError("V7 dynamic grid label locator configuration is invalid.")

    def as_dict(self) -> dict[str, object]:
        return {
            "cropHeightSpacingRatio": self.crop_height_spacing_ratio,
            "cropWidthSpacingRatio": self.crop_width_spacing_ratio,
            "kind": "dynamic_lattice_v2",
            "maximumAspectRatio": self.maximum_aspect_ratio,
            "maximumLatticeResidualRatio": self.maximum_lattice_residual_ratio,
            "minimumAspectRatio": self.minimum_aspect_ratio,
            "minimumLatticeMargin": self.minimum_lattice_margin,
            "positionConfidence": self.position_confidence,
        }


type V7LabelLocatorConfig = V7GridLabelLocatorConfig | V7DynamicGridLabelLocatorConfig
DEFAULT_V7_GRID_LABEL_LOCATOR_CONFIG = V7GridLabelLocatorConfig()
DEFAULT_V7_DYNAMIC_GRID_LABEL_LOCATOR_CONFIG = V7DynamicGridLabelLocatorConfig()


@dataclass(frozen=True, slots=True)
class V7GridLabelCrop:
    position_index: int
    rgb: NDArray[np.uint8]
    complete: bool


class V7GridLabelLocator:
    """Historical V1 whole-image locator."""

    def __init__(self, config: V7GridLabelLocatorConfig | None = None) -> None:
        self.config = config or DEFAULT_V7_GRID_LABEL_LOCATOR_CONFIG

    def locate(self, rgb: NDArray[np.uint8]) -> tuple[V7GridLabelCrop, ...]:
        if not _valid_image(
            rgb, self.config.minimum_aspect_ratio, self.config.maximum_aspect_ratio
        ):
            return ()
        height, width = rgb.shape[:2]
        crop_height = max(1, round(height * self.config.height_ratio))
        result: list[V7GridLabelCrop] = []
        for position, (x_ratio, y_ratio) in enumerate(self.config.centers):
            crop_width = max(1, round(width * self.config.width_ratios[position]))
            center_x, center_y = round(width * x_ratio), round(height * y_ratio)
            left, top = center_x - crop_width // 2, center_y - crop_height // 2
            right, bottom = left + crop_width, top + crop_height
            if left >= 0 and top >= 0 and right <= width and bottom <= height:
                result.append(V7GridLabelCrop(position, rgb[top:bottom, left:right], True))
        return tuple(result)


@dataclass(frozen=True, slots=True)
class _TextBox:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def center(self) -> tuple[float, float]:
        return ((self.left + self.right) / 2, (self.top + self.bottom) / 2)

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


@dataclass(frozen=True, slots=True)
class _Lattice:
    centers: tuple[tuple[float, float], ...]
    score: float


class V7DynamicGridLabelLocator:
    """V2 image-only localizer for a complete, unambiguous 3x3 number lattice."""

    def __init__(self, config: V7DynamicGridLabelLocatorConfig | None = None) -> None:
        self.config = config or DEFAULT_V7_DYNAMIC_GRID_LABEL_LOCATOR_CONFIG

    def locate(self, rgb: NDArray[np.uint8]) -> tuple[V7GridLabelCrop, ...]:
        if not _valid_image(
            rgb, self.config.minimum_aspect_ratio, self.config.maximum_aspect_ratio
        ):
            return ()
        candidates = _find_text_candidates(rgb)
        lattice = _find_complete_lattice(
            candidates,
            rgb.shape[:2],
            self.config.minimum_lattice_margin,
            self.config.maximum_lattice_residual_ratio,
        )
        if lattice is None:
            return ()
        return _extract_dynamic_crops(rgb, lattice, self.config)


def build_v7_label_locator(
    config: V7LabelLocatorConfig,
) -> V7GridLabelLocator | V7DynamicGridLabelLocator:
    if isinstance(config, V7DynamicGridLabelLocatorConfig):
        return V7DynamicGridLabelLocator(config)
    return V7GridLabelLocator(config)


def recognize_grid_labels(
    rgb: NDArray[np.uint8],
    recognizer: V7LabelRecognitionBackend,
    *,
    locator: V7GridLabelLocator | V7DynamicGridLabelLocator | None = None,
) -> tuple[V7LabelEvidence, ...]:
    """Return only own numeric OCR labels; no expected range is an input here."""
    active_locator = locator or V7GridLabelLocator()
    crops = active_locator.locate(rgb)
    values = recognizer.recognize_many([crop.rgb for crop in crops])
    if len(values) != len(crops):
        raise ValueError("OCR result count differs from v7 label crop count.")
    evidence: list[V7LabelEvidence] = []
    for crop, value in zip(crops, values, strict=True):
        raw_text = getattr(value, "raw_text", None)
        confidence = getattr(value, "confidence", None)
        if (
            not isinstance(raw_text, str)
            or isinstance(confidence, bool)
            or not isinstance(confidence, int | float)
        ):
            raise ValueError("OCR result has an invalid v7 label contract.")
        if raw_text.isdecimal() and int(raw_text) > 0:
            evidence.append(
                V7LabelEvidence(
                    crop.position_index,
                    int(raw_text),
                    float(confidence),
                    active_locator.config.position_confidence,
                )
            )
    return tuple(evidence)


def _valid_image(rgb: NDArray[np.uint8], minimum_aspect: float, maximum_aspect: float) -> bool:
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
        return False
    height, width = rgb.shape[:2]
    return bool(min(height, width) >= 32 and minimum_aspect <= width / height <= maximum_aspect)


def _find_text_candidates(rgb: NDArray[np.uint8]) -> tuple[_TextBox, ...]:
    """Find number-like components in both contrast polarities without colour rules."""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    height, width = gray.shape
    candidates: dict[tuple[int, int, int, int], _TextBox] = {}
    # Otsu catches bright/dark labels; adaptive threshold retains labels under uneven lighting.
    variants = (
        cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1],
        cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1],
        cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, 7),
        cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 41, 7
        ),
    )
    kernel_width = max(3, round(width * 0.004))
    kernel_height = max(1, round(height * 0.002))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_width, kernel_height))
    for variant in variants:
        merged = cv2.morphologyEx(variant, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            left, top, box_width, box_height = cv2.boundingRect(contour)
            right, bottom = left + box_width, top + box_height
            aspect = box_width / max(1, box_height)
            if (
                box_width < max(24, width * 0.05)
                or box_width > width * 0.18
                or box_height < max(10, height * 0.015)
                or box_height > height * 0.055
                or not 2.5 <= aspect <= 10
                or left == 0
                or top == 0
                or right == width
                or bottom == height
            ):
                continue
            box = _TextBox(left, top, right, bottom)
            candidates[(left, top, right, bottom)] = box
    # Near-identical detections from four threshold variants are intentionally coalesced.
    values = sorted(candidates.values(), key=lambda box: (box.top, box.left, box.width, box.height))
    result: list[_TextBox] = []
    for candidate in values:
        if any(_iou(candidate, kept) >= 0.72 for kept in result):
            continue
        result.append(candidate)
    return tuple(result[:80])


def _find_complete_lattice(
    candidates: tuple[_TextBox, ...],
    shape: tuple[int, int],
    margin: float,
    maximum_residual_ratio: float,
) -> _Lattice | None:
    """RANSAC-like complete lattice fitting; ambiguity fails closed."""
    if len(candidates) < 9:
        return None
    height, width = shape
    hypotheses: list[_Lattice] = []
    for origin_index, right_index, down_index in permutations(range(len(candidates)), 3):
        origin = candidates[origin_index].center
        right = candidates[right_index].center
        down = candidates[down_index].center
        horizontal = (right[0] - origin[0], right[1] - origin[1])
        vertical = (down[0] - origin[0], down[1] - origin[1])
        horizontal_size, vertical_size = np.hypot(*horizontal), np.hypot(*vertical)
        if (
            horizontal[0] <= width * 0.08
            or vertical[1] <= height * 0.05
            or horizontal_size > width * 0.6
            or vertical_size > height * 0.45
            or abs(horizontal[1]) > horizontal_size * 0.28
            or abs(vertical[0]) > vertical_size * 0.28
        ):
            continue
        expected = tuple(
            (
                origin[0] + column * horizontal[0] + row * vertical[0],
                origin[1] + column * horizontal[1] + row * vertical[1],
            )
            for row in range(3)
            for column in range(3)
        )
        used: set[int] = set()
        assigned: list[int] = []
        distances: list[float] = []
        # Initial affine assignment tolerates perspective; the accepted lattice
        # is then refit projectively and must still beat every other lattice.
        tolerance = min(horizontal_size, vertical_size) * 0.65
        for point in expected:
            options = sorted(
                (
                    float(np.hypot(candidate.center[0] - point[0], candidate.center[1] - point[1])),
                    index,
                )
                for index, candidate in enumerate(candidates)
                if index not in used
            )
            if not options or options[0][0] > tolerance:
                break
            distance, index = options[0]
            used.add(index)
            assigned.append(index)
            distances.append(distance)
        if len(assigned) != 9:
            continue
        observed = np.asarray([candidates[index].center for index in assigned], dtype=np.float32)
        source = np.asarray(
            [(column, row) for row in range(3) for column in range(3)], dtype=np.float32
        )
        transform, _ = cv2.findHomography(source, observed, method=0)
        if transform is None or not np.isfinite(transform).all():
            continue
        projected = cv2.perspectiveTransform(source.reshape(1, -1, 2), transform).reshape(-1, 2)
        residual = float(
            np.mean(np.linalg.norm(projected - observed, axis=1))
            / max(1.0, min(horizontal_size, vertical_size))
        )
        if residual > maximum_residual_ratio:
            continue
        score = 1.0 - min(1.0, residual)
        hypotheses.append(_Lattice(tuple((float(x), float(y)) for x, y in projected), score))
    if not hypotheses:
        return None
    hypotheses.sort(key=lambda item: item.score, reverse=True)
    best = hypotheses[0]
    # A different complete lattice with an equivalent score is unsafe.
    for candidate in hypotheses[1:]:
        if best.score - candidate.score >= margin:
            break
        if not _same_lattice(best, candidate, max(shape) * 0.03):
            return None
    return best


def _extract_dynamic_crops(
    rgb: NDArray[np.uint8], lattice: _Lattice, config: V7DynamicGridLabelLocatorConfig
) -> tuple[V7GridLabelCrop, ...]:
    height, width = rgb.shape[:2]
    centers = np.asarray(lattice.centers, dtype=np.float64).reshape(3, 3, 2)
    horizontal = [
        np.linalg.norm(centers[row, column + 1] - centers[row, column])
        for row in range(3)
        for column in range(2)
    ]
    vertical = [
        np.linalg.norm(centers[row + 1, column] - centers[row, column])
        for row in range(2)
        for column in range(3)
    ]
    crop_width = max(1, round(float(np.median(horizontal)) * config.crop_width_spacing_ratio))
    crop_height = max(1, round(float(np.median(vertical)) * config.crop_height_spacing_ratio))
    result: list[V7GridLabelCrop] = []
    for position, (center_x, center_y) in enumerate(lattice.centers):
        left, top = round(center_x - crop_width / 2), round(center_y - crop_height / 2)
        right, bottom = left + crop_width, top + crop_height
        if left < 0 or top < 0 or right > width or bottom > height:
            return ()
        crop = rgb[top:bottom, left:right]
        if crop.size == 0:
            return ()
        result.append(V7GridLabelCrop(position, crop, True))
    return tuple(result)


def _iou(first: _TextBox, second: _TextBox) -> float:
    left, top = max(first.left, second.left), max(first.top, second.top)
    right, bottom = min(first.right, second.right), min(first.bottom, second.bottom)
    intersection = max(0, right - left) * max(0, bottom - top)
    union = first.width * first.height + second.width * second.height - intersection
    return intersection / union if union else 0.0


def _same_lattice(first: _Lattice, second: _Lattice, tolerance: float) -> bool:
    return all(
        np.hypot(x1 - x2, y1 - y2) <= tolerance
        for (x1, y1), (x2, y2) in zip(first.centers, second.centers, strict=True)
    )


__all__ = [
    "DEFAULT_V7_DYNAMIC_GRID_LABEL_LOCATOR_CONFIG",
    "DEFAULT_V7_GRID_LABEL_LOCATOR_CONFIG",
    "V7DynamicGridLabelLocator",
    "V7DynamicGridLabelLocatorConfig",
    "V7GridLabelCrop",
    "V7GridLabelLocator",
    "V7GridLabelLocatorConfig",
    "V7LabelLocatorConfig",
    "V7LabelRecognitionBackend",
    "build_v7_label_locator",
    "recognize_grid_labels",
]
