"""Source-direct five-anchor locator for visible range labels.

This module deliberately has no concept of a source filename, expected sequence
range, OCR result, board geometry or image-selection job.  It only turns an
already EXIF-canonical RGB screen into five bounded candidate crops.  A later
recognizer must independently prove any numeric range from those pixels.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import cv2
import numpy as np
from numpy.typing import NDArray

FIVE_ANCHOR_RANGE_LABEL_LOCATOR_VERSION: Final = "five-anchor-range-label-locator-v6"
FIVE_ANCHOR_RANGE_LABEL_COORDINATE_SPACE: Final = "exif-transposed-rgb-v1"


class FiveAnchorPosition(StrEnum):
    """Named positions used only to locate visible numeric label candidates."""

    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    CENTER = "center"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"


_ANCHOR_ORDER: Final = (
    FiveAnchorPosition.TOP_LEFT,
    FiveAnchorPosition.TOP_RIGHT,
    FiveAnchorPosition.CENTER,
    FiveAnchorPosition.BOTTOM_LEFT,
    FiveAnchorPosition.BOTTOM_RIGHT,
)


class FiveAnchorLocatorMode(StrEnum):
    """Whether a crop was tightened around local bright text components."""

    COMPONENT_REFINED = "component_refined"
    VIEWPORT_FALLBACK = "viewport_fallback"


class FiveAnchorLocatorUnknownReason(StrEnum):
    """Fail-closed reasons for an image that cannot yield all five crops."""

    INVALID_RGB = "INVALID_RGB"
    UNSUPPORTED_VIEWPORT = "UNSUPPORTED_VIEWPORT"
    CROP_OUT_OF_BOUNDS = "CROP_OUT_OF_BOUNDS"


@dataclass(frozen=True, slots=True)
class FiveAnchorBoundingBox:
    """An integer source-image rectangle in EXIF-canonical RGB space."""

    left: int
    top: int
    right: int
    bottom: int

    def __post_init__(self) -> None:
        if self.left < 0 or self.top < 0 or self.right <= self.left or self.bottom <= self.top:
            raise ValueError("Five-anchor crop bounds are invalid.")

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def width(self) -> int:
        return self.right - self.left

    def as_dict(self) -> dict[str, int]:
        return {
            "bottom": self.bottom,
            "left": self.left,
            "right": self.right,
            "top": self.top,
        }


@dataclass(frozen=True, slots=True)
class FiveAnchorLabelCrop:
    """One full, source-direct candidate crop and its localizer provenance."""

    position: FiveAnchorPosition
    box: FiveAnchorBoundingBox
    rgb: NDArray[np.uint8]
    complete: bool
    mode: FiveAnchorLocatorMode

    def __post_init__(self) -> None:
        if self.rgb.ndim != 3 or self.rgb.shape[2] != 3 or self.rgb.dtype != np.uint8:
            raise ValueError("Five-anchor crop must be a uint8 RGB image.")
        if self.rgb.shape[:2] != (self.box.height, self.box.width):
            raise ValueError("Five-anchor crop pixels do not match its source box.")
        if not self.complete:
            raise ValueError("A successful five-anchor crop must be complete.")


@dataclass(frozen=True, slots=True)
class FiveAnchorLocation:
    """Exactly five source-direct candidate crops in stable anchor order."""

    crops: tuple[
        FiveAnchorLabelCrop,
        FiveAnchorLabelCrop,
        FiveAnchorLabelCrop,
        FiveAnchorLabelCrop,
        FiveAnchorLabelCrop,
    ]
    fingerprint: str

    def __post_init__(self) -> None:
        positions = tuple(crop.position for crop in self.crops)
        if positions != _ANCHOR_ORDER:
            raise ValueError("Five-anchor crops must use the stable anchor order.")


@dataclass(frozen=True, slots=True)
class FiveAnchorLocatorResult:
    """A complete crop set or an explicit local failure, never partial success."""

    location: FiveAnchorLocation | None
    reason_code: FiveAnchorLocatorUnknownReason | None
    diagnostics: dict[str, object]

    def __post_init__(self) -> None:
        if (self.location is None) == (self.reason_code is None):
            raise ValueError("Five-anchor result must contain either a location or a reason.")


@dataclass(frozen=True, slots=True)
class FiveAnchorRangeLabelLocatorConfig:
    """Versioned viewport and component-refinement policy for v6.

    Ratios describe a broad portrait game screen, not a particular range.  The
    component refiner can tighten a candidate around local high-value strokes;
    otherwise the complete bounded viewport is retained for OCR.
    """

    version: str = "five-anchor-range-label-locator-config-v1"
    minimum_aspect_ratio: float = 0.30
    maximum_aspect_ratio: float = 0.92
    anchor_centers: tuple[
        tuple[FiveAnchorPosition, float, float],
        tuple[FiveAnchorPosition, float, float],
        tuple[FiveAnchorPosition, float, float],
        tuple[FiveAnchorPosition, float, float],
        tuple[FiveAnchorPosition, float, float],
    ] = (
        (FiveAnchorPosition.TOP_LEFT, 0.19, 0.51),
        (FiveAnchorPosition.TOP_RIGHT, 0.79, 0.51),
        (FiveAnchorPosition.CENTER, 0.50, 0.61),
        (FiveAnchorPosition.BOTTOM_LEFT, 0.19, 0.71),
        (FiveAnchorPosition.BOTTOM_RIGHT, 0.79, 0.71),
    )
    fallback_width_ratio: float = 0.18
    fallback_height_ratio: float = 0.075
    component_minimum_brightness: int = 172
    component_maximum_saturation: int = 180
    component_minimum_area_ratio: float = 0.002
    component_maximum_area_ratio: float = 0.38
    refined_horizontal_padding_ratio: float = 0.35
    refined_vertical_padding_ratio: float = 0.65
    minimum_crop_width_ratio: float = 0.055
    minimum_crop_height_ratio: float = 0.022

    def __post_init__(self) -> None:
        ratios = (
            self.minimum_aspect_ratio,
            self.maximum_aspect_ratio,
            self.fallback_width_ratio,
            self.fallback_height_ratio,
            self.component_minimum_area_ratio,
            self.component_maximum_area_ratio,
            self.refined_horizontal_padding_ratio,
            self.refined_vertical_padding_ratio,
            self.minimum_crop_width_ratio,
            self.minimum_crop_height_ratio,
        )
        if (
            not 0 < self.minimum_aspect_ratio < self.maximum_aspect_ratio
            or any(value <= 0 or value > 1 for value in ratios[2:])
            or not self.component_minimum_area_ratio < self.component_maximum_area_ratio
            or not 0 <= self.component_minimum_brightness <= 255
            or not 0 <= self.component_maximum_saturation <= 255
            or tuple(value[0] for value in self.anchor_centers) != _ANCHOR_ORDER
            or any(not 0 < x < 1 or not 0 < y < 1 for _, x, y in self.anchor_centers)
        ):
            raise ValueError("Five-anchor range-label locator configuration is invalid.")

    def as_dict(self) -> dict[str, object]:
        return {
            "anchorCenters": [
                {"position": position.value, "x": x_ratio, "y": y_ratio}
                for position, x_ratio, y_ratio in self.anchor_centers
            ],
            "component": {
                "maximumArea": self.component_maximum_area_ratio,
                "maximumSaturation": self.component_maximum_saturation,
                "minimumArea": self.component_minimum_area_ratio,
                "minimumBrightness": self.component_minimum_brightness,
            },
            "cropMinimum": {
                "height": self.minimum_crop_height_ratio,
                "width": self.minimum_crop_width_ratio,
            },
            "fallback": {
                "height": self.fallback_height_ratio,
                "width": self.fallback_width_ratio,
            },
            "padding": {
                "horizontal": self.refined_horizontal_padding_ratio,
                "vertical": self.refined_vertical_padding_ratio,
            },
            "supportedAspectRatio": [self.minimum_aspect_ratio, self.maximum_aspect_ratio],
            "version": self.version,
        }


DEFAULT_FIVE_ANCHOR_RANGE_LABEL_LOCATOR_CONFIG = FiveAnchorRangeLabelLocatorConfig()


class FiveAnchorRangeLabelLocator:
    """Locate five candidate labels without reading, inferring or matching text."""

    def __init__(self, config: FiveAnchorRangeLabelLocatorConfig | None = None) -> None:
        self.config = config or DEFAULT_FIVE_ANCHOR_RANGE_LABEL_LOCATOR_CONFIG

    @property
    def fingerprint(self) -> str:
        return _canonical_sha256(
            {
                "coordinateSpace": FIVE_ANCHOR_RANGE_LABEL_COORDINATE_SPACE,
                "locator": self.config.as_dict(),
                "variant": FIVE_ANCHOR_RANGE_LABEL_LOCATOR_VERSION,
            }
        )

    def locate(self, rgb: NDArray[np.uint8]) -> FiveAnchorLocatorResult:
        if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
            return self._unknown(FiveAnchorLocatorUnknownReason.INVALID_RGB)
        height, width = rgb.shape[:2]
        if min(height, width) < 32:
            return self._unknown(FiveAnchorLocatorUnknownReason.INVALID_RGB)
        aspect_ratio = width / height
        if not self.config.minimum_aspect_ratio <= aspect_ratio <= self.config.maximum_aspect_ratio:
            return self._unknown(
                FiveAnchorLocatorUnknownReason.UNSUPPORTED_VIEWPORT,
                {"aspectRatio": aspect_ratio},
            )

        crops: list[FiveAnchorLabelCrop] = []
        modes: dict[str, str] = {}
        for position, x_ratio, y_ratio in self.config.anchor_centers:
            fallback = self._fallback_box(
                width=width,
                height=height,
                x_ratio=x_ratio,
                y_ratio=y_ratio,
            )
            if fallback is None:
                return self._unknown(
                    FiveAnchorLocatorUnknownReason.CROP_OUT_OF_BOUNDS,
                    {"anchor": position.value},
                )
            refined = self._refine_box(rgb, fallback)
            box = refined or fallback
            mode = (
                FiveAnchorLocatorMode.COMPONENT_REFINED
                if refined is not None
                else FiveAnchorLocatorMode.VIEWPORT_FALLBACK
            )
            modes[position.value] = mode.value
            crops.append(
                FiveAnchorLabelCrop(
                    position=position,
                    box=box,
                    rgb=np.ascontiguousarray(rgb[box.top : box.bottom, box.left : box.right]),
                    complete=True,
                    mode=mode,
                )
            )

        return FiveAnchorLocatorResult(
            location=FiveAnchorLocation(
                crops=(crops[0], crops[1], crops[2], crops[3], crops[4]),
                fingerprint=self.fingerprint,
            ),
            reason_code=None,
            diagnostics={
                "anchorCount": len(crops),
                "anchorModes": modes,
                "coordinateSpace": FIVE_ANCHOR_RANGE_LABEL_COORDINATE_SPACE,
                "locatorVersion": FIVE_ANCHOR_RANGE_LABEL_LOCATOR_VERSION,
            },
        )

    def _fallback_box(
        self,
        *,
        width: int,
        height: int,
        x_ratio: float,
        y_ratio: float,
    ) -> FiveAnchorBoundingBox | None:
        crop_width = max(1, round(width * self.config.fallback_width_ratio))
        crop_height = max(1, round(height * self.config.fallback_height_ratio))
        center_x = round(width * x_ratio)
        center_y = round(height * y_ratio)
        left = center_x - crop_width // 2
        top = center_y - crop_height // 2
        right = left + crop_width
        bottom = top + crop_height
        if left < 0 or top < 0 or right > width or bottom > height:
            return None
        return FiveAnchorBoundingBox(left=left, top=top, right=right, bottom=bottom)

    def _refine_box(
        self,
        rgb: NDArray[np.uint8],
        fallback: FiveAnchorBoundingBox,
    ) -> FiveAnchorBoundingBox | None:
        window = rgb[fallback.top : fallback.bottom, fallback.left : fallback.right]
        hsv = cv2.cvtColor(window, cv2.COLOR_RGB2HSV)
        bright = hsv[:, :, 2] >= self.config.component_minimum_brightness
        muted = hsv[:, :, 1] <= self.config.component_maximum_saturation
        mask = np.asarray(bright & muted, dtype=np.uint8) * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 1))
        merged = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(merged)
        minimum_area = window.shape[0] * window.shape[1] * self.config.component_minimum_area_ratio
        maximum_area = window.shape[0] * window.shape[1] * self.config.component_maximum_area_ratio
        components: list[tuple[int, int, int, int]] = []
        for index in range(1, count):
            left, top, component_width, component_height, area = (
                int(value) for value in stats[index]
            )
            if not minimum_area <= area <= maximum_area:
                continue
            if component_height < 2 or component_width < 1:
                continue
            components.append((left, top, component_width, component_height))
        if not components:
            return None

        left = min(item[0] for item in components)
        top = min(item[1] for item in components)
        right = max(item[0] + item[2] for item in components)
        bottom = max(item[1] + item[3] for item in components)
        component_width = right - left
        component_height = bottom - top
        requested_pad_x = max(
            1,
            round(component_width * self.config.refined_horizontal_padding_ratio),
        )
        requested_pad_y = max(
            1,
            round(component_height * self.config.refined_vertical_padding_ratio),
        )
        # A label may span nearly the entire broad anchor viewport.  Preserve
        # its evidence instead of discarding component refinement merely
        # because the preferred padding would extend outside that viewport.
        pad_x = min(requested_pad_x, max(0, (fallback.width - component_width) // 2))
        pad_y = min(requested_pad_y, max(0, (fallback.height - component_height) // 2))
        minimum_width = max(1, round(rgb.shape[1] * self.config.minimum_crop_width_ratio))
        minimum_height = max(1, round(rgb.shape[0] * self.config.minimum_crop_height_ratio))
        target_width = max(component_width + 2 * pad_x, minimum_width)
        target_height = max(component_height + 2 * pad_y, minimum_height)
        center_x = fallback.left + (left + right) // 2
        center_y = fallback.top + (top + bottom) // 2
        source_left = center_x - target_width // 2
        source_top = center_y - target_height // 2
        source_left = min(max(source_left, fallback.left), fallback.right - target_width)
        source_top = min(max(source_top, fallback.top), fallback.bottom - target_height)
        source_right = source_left + target_width
        source_bottom = source_top + target_height
        return FiveAnchorBoundingBox(
            left=source_left,
            top=source_top,
            right=source_right,
            bottom=source_bottom,
        )

    def _unknown(
        self,
        reason: FiveAnchorLocatorUnknownReason,
        diagnostics: dict[str, object] | None = None,
    ) -> FiveAnchorLocatorResult:
        return FiveAnchorLocatorResult(
            location=None,
            reason_code=reason,
            diagnostics={
                "coordinateSpace": FIVE_ANCHOR_RANGE_LABEL_COORDINATE_SPACE,
                "locatorVersion": FIVE_ANCHOR_RANGE_LABEL_LOCATOR_VERSION,
                **(diagnostics or {}),
            },
        )


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


__all__ = [
    "DEFAULT_FIVE_ANCHOR_RANGE_LABEL_LOCATOR_CONFIG",
    "FIVE_ANCHOR_RANGE_LABEL_COORDINATE_SPACE",
    "FIVE_ANCHOR_RANGE_LABEL_LOCATOR_VERSION",
    "FiveAnchorBoundingBox",
    "FiveAnchorLabelCrop",
    "FiveAnchorLocation",
    "FiveAnchorLocatorMode",
    "FiveAnchorLocatorResult",
    "FiveAnchorLocatorUnknownReason",
    "FiveAnchorPosition",
    "FiveAnchorRangeLabelLocator",
    "FiveAnchorRangeLabelLocatorConfig",
]
