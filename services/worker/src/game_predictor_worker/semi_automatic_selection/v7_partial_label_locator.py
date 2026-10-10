"""Optional V2 partial locator; historical strict V2 remains unchanged."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .v7_label_locator import (
    DEFAULT_V7_DYNAMIC_GRID_LABEL_LOCATOR_CONFIG,
    V7DynamicGridLabelLocatorConfig,
    V7GridLabelCrop,
    _find_text_candidates,
    _valid_image,
)
from .v7_partial_lattice import find_partial_lattice


@dataclass(frozen=True, slots=True)
class V7PartialLabelLocation:
    crops: tuple[V7GridLabelCrop, ...]
    reason_code: str | None = None


class V7PartialGridLabelLocator:
    """Stateless photo-local geometry with explicit observed slot indices."""

    def __init__(self, config: V7DynamicGridLabelLocatorConfig | None = None) -> None:
        self.config = config or DEFAULT_V7_DYNAMIC_GRID_LABEL_LOCATOR_CONFIG

    def locate(self, rgb: NDArray[np.uint8]) -> tuple[V7GridLabelCrop, ...]:
        return self.locate_with_diagnostics(rgb).crops

    def locate_with_diagnostics(self, rgb: NDArray[np.uint8]) -> V7PartialLabelLocation:
        if not _valid_image(
            rgb, self.config.minimum_aspect_ratio, self.config.maximum_aspect_ratio
        ):
            return V7PartialLabelLocation((), "V7_LABEL_IMAGE_INVALID")
        candidates = _find_text_candidates(rgb)
        result = find_partial_lattice(candidates, rgb.shape[:2], self.config)
        lattice = result.lattice
        if lattice is None:
            return V7PartialLabelLocation((), result.reason_code)
        centers = np.asarray(lattice.centers).reshape(3, 3, 2)
        crop_width = max(
            1,
            round(
                float(np.median(np.linalg.norm(np.diff(centers, axis=1), axis=2)))
                * self.config.crop_width_spacing_ratio
            ),
        )
        crop_height = max(
            1,
            round(
                float(np.median(np.linalg.norm(np.diff(centers, axis=0), axis=2)))
                * self.config.crop_height_spacing_ratio
            ),
        )
        height, width = rgb.shape[:2]
        crops = []
        for position, candidate_index in lattice.assignments:
            box = candidates[candidate_index]
            center_x, center_y = box.center
            left, top = round(center_x - crop_width / 2), round(center_y - crop_height / 2)
            right, bottom = left + crop_width, top + crop_height
            if (
                left < 0
                or top < 0
                or right > width
                or bottom > height
                or left > box.left
                or top > box.top
                or right < box.right
                or bottom < box.bottom
            ):
                return V7PartialLabelLocation((), "V7_LABEL_CROP_INCOMPLETE")
            crops.append(V7GridLabelCrop(position, rgb[top:bottom, left:right], True))
        return V7PartialLabelLocation(tuple(crops))
