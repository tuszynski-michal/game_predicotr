"""Grid-local numeric-label crops for landscape 3x3 v7 page photographs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from .v7_range_proof import V7LabelEvidence


class V7LabelRecognitionBackend(Protocol):
    def recognize_many(self, crops: list[NDArray[np.uint8]]) -> tuple[object, ...]:
        """Return recognition-like values with ``raw_text`` and ``confidence``."""


@dataclass(frozen=True, slots=True)
class V7GridLabelLocatorConfig:
    """Provisional landscape label centers; T05 owns calibration and replacement."""

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
    width_ratios: tuple[float, ...] = (
        0.14,
        0.14,
        0.14,
        0.14,
        0.14,
        0.14,
        0.18,
        0.20,
        0.16,
    )
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


DEFAULT_V7_GRID_LABEL_LOCATOR_CONFIG = V7GridLabelLocatorConfig()


@dataclass(frozen=True, slots=True)
class V7GridLabelCrop:
    position_index: int
    rgb: NDArray[np.uint8]
    complete: bool


class V7GridLabelLocator:
    def __init__(self, config: V7GridLabelLocatorConfig | None = None) -> None:
        self.config = config or DEFAULT_V7_GRID_LABEL_LOCATOR_CONFIG

    def locate(self, rgb: NDArray[np.uint8]) -> tuple[V7GridLabelCrop, ...]:
        if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
            return ()
        height, width = rgb.shape[:2]
        aspect_ratio = width / height
        if min(height, width) < 32 or not (
            self.config.minimum_aspect_ratio <= aspect_ratio <= self.config.maximum_aspect_ratio
        ):
            return ()
        crop_height = max(1, round(height * self.config.height_ratio))
        result: list[V7GridLabelCrop] = []
        for position, (x_ratio, y_ratio) in enumerate(self.config.centers):
            crop_width = max(1, round(width * self.config.width_ratios[position]))
            center_x, center_y = round(width * x_ratio), round(height * y_ratio)
            left, top = center_x - crop_width // 2, center_y - crop_height // 2
            right, bottom = left + crop_width, top + crop_height
            complete = left >= 0 and top >= 0 and right <= width and bottom <= height
            if complete:
                result.append(V7GridLabelCrop(position, rgb[top:bottom, left:right], True))
        return tuple(result)


def recognize_grid_labels(
    rgb: NDArray[np.uint8],
    recognizer: V7LabelRecognitionBackend,
    *,
    locator: V7GridLabelLocator | None = None,
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
