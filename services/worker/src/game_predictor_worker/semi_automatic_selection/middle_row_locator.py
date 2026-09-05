"""Source-direct locator and quality gates for v4.1 middle-row labels.

The locator is intentionally independent from Paddle and from every board or
symbol pipeline.  It may produce at most three in-memory source-resolution
crops.  It never persists image data and never supplies range values.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from io import BytesIO
from statistics import median
from time import perf_counter

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageOps, UnidentifiedImageError

from .middle_row_range import MIDDLE_ROW_RANGE_VARIANT, MiddleRowUnknownReason

MIDDLE_ROW_COORDINATE_SPACE = "exif-transposed-rgb-v1"
MIDDLE_ROW_LOCATOR_VERSION = "middle-row-triple-locator-v2-partial-lattice"
MIDDLE_ROW_CROP_POLICY_VERSION = "middle-row-source-crops-v2-compact-label"
MIDDLE_ROW_CROP_COMPLETENESS_VERSION = "middle-row-crop-completeness-v1"
MIDDLE_ROW_READABILITY_VERSION = "middle-row-local-readability-v1"
MIDDLE_ROW_OCR_PREPROCESSING_VERSION = "middle-row-rgb-source-v1"


class MiddleRowLocatorMode(StrEnum):
    FULL_LATTICE = "FULL_LATTICE"
    MIDDLE_ROW_WITH_LOCKED_PRIOR = "MIDDLE_ROW_WITH_LOCKED_PRIOR"


@dataclass(frozen=True, slots=True)
class ImageDimensions:
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width < 1 or self.height < 1:
            raise ValueError("Image dimensions must be positive.")

    def as_dict(self) -> dict[str, int]:
        return {"height": self.height, "width": self.width}


@dataclass(frozen=True, slots=True)
class BoundingBox:
    left: int
    top: int
    right: int
    bottom: int

    def __post_init__(self) -> None:
        if self.left < 0 or self.top < 0 or self.right <= self.left or self.bottom <= self.top:
            raise ValueError("Bounding box is invalid.")

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center(self) -> tuple[float, float]:
        return ((self.left + self.right) / 2, (self.top + self.bottom) / 2)

    def as_dict(self) -> dict[str, int]:
        return {
            "bottom": self.bottom,
            "left": self.left,
            "right": self.right,
            "top": self.top,
        }


@dataclass(frozen=True, slots=True)
class CanonicalSourceImage:
    """One decode with EXIF applied exactly once."""

    rgb: NDArray[np.uint8]
    raw_dimensions: ImageDimensions
    oriented_dimensions: ImageDimensions
    exif_orientation: int
    coordinate_space: str = MIDDLE_ROW_COORDINATE_SPACE
    decode_seconds: float = field(default=0.0, repr=False, compare=False)
    exif_seconds: float = field(default=0.0, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.rgb.dtype != np.uint8 or self.rgb.ndim != 3 or self.rgb.shape[2] != 3:
            raise ValueError("Canonical source image must be RGB uint8.")
        if self.exif_orientation not in range(1, 9):
            raise ValueError("EXIF orientation must be between 1 and 8.")
        if self.rgb.shape[:2] != (
            self.oriented_dimensions.height,
            self.oriented_dimensions.width,
        ):
            raise ValueError("Canonical RGB dimensions differ from metadata.")


def canonicalize_source_image(content: bytes) -> CanonicalSourceImage:
    """Decode source bytes once and return an EXIF-canonical RGB array."""

    try:
        with Image.open(BytesIO(content)) as source:
            raw = ImageDimensions(width=source.width, height=source.height)
            orientation = int(source.getexif().get(274, 1))
            if orientation not in range(1, 9):
                orientation = 1
            decode_started = perf_counter()
            source.load()
            decode_seconds = perf_counter() - decode_started
            exif_started = perf_counter()
            oriented = ImageOps.exif_transpose(source)
            rgb = np.asarray(oriented.convert("RGB"), dtype=np.uint8).copy()
            exif_seconds = perf_counter() - exif_started
    except (OSError, UnidentifiedImageError, ValueError) as error:
        raise ValueError("SOURCE_DECODE_ERROR") from error
    dimensions = ImageDimensions(width=int(rgb.shape[1]), height=int(rgb.shape[0]))
    return CanonicalSourceImage(
        rgb=rgb,
        raw_dimensions=raw,
        oriented_dimensions=dimensions,
        exif_orientation=orientation,
        decode_seconds=decode_seconds,
        exif_seconds=exif_seconds,
    )


@dataclass(frozen=True, slots=True)
class MiddleRowLocatorConfig:
    """Versioned experimental defaults for structural text localization."""

    version: str = MIDDLE_ROW_LOCATOR_VERSION
    thumbnail_max_edge: int = 960
    minimum_predicted_text_height: int = 10
    minimum_x_ratio: float = 0.20
    maximum_x_ratio: float = 0.82
    minimum_y_ratio: float = 0.24
    maximum_y_ratio: float = 0.48
    expanded_maximum_y_ratio: float = 0.60
    roi_boundary_margin_ratio: float = 0.02
    minimum_saturation: int = 0
    maximum_saturation: int = 115
    minimum_brightness: int = 165
    maximum_brightness: int = 255
    horizontal_close_ratio: float = 0.0065
    vertical_close_ratio: float = 0.0016
    minimum_component_height_ratio: float = 0.003
    maximum_component_height_ratio: float = 0.035
    minimum_component_width_ratio: float = 0.003
    maximum_component_width_ratio: float = 0.16
    minimum_label_width_ratio: float = 0.025
    minimum_label_aspect_ratio: float = 1.20
    minimum_component_area_ratio: float = 0.000005
    minimum_fill_ratio: float = 0.10
    digit_group_gap_ratio: float = 0.018
    digit_group_baseline_ratio: float = 0.010
    axis_x_tolerance_ratio: float = 0.035
    column_minimum_gap_ratio: float = 0.12
    column_maximum_gap_ratio: float = 0.38
    axis_y_tolerance_ratio: float = 0.022
    row_minimum_gap_ratio: float = 0.028
    row_maximum_gap_ratio: float = 0.12
    assignment_x_tolerance_ratio: float = 0.09
    assignment_y_tolerance_ratio: float = 0.025
    # Side controls can merge with one or two outer labels.  Seven structural
    # matches still establish all three rows and columns, while the exact
    # range proof continues to require all three independently read middle
    # labels below.
    minimum_full_lattice_cells: int = 7
    minimum_ambiguity_margin: float = 0.025
    prior_axis_tolerance_ratio: float = 0.035

    def __post_init__(self) -> None:
        ratios = (
            self.minimum_x_ratio,
            self.maximum_x_ratio,
            self.minimum_y_ratio,
            self.maximum_y_ratio,
            self.expanded_maximum_y_ratio,
            self.roi_boundary_margin_ratio,
            self.horizontal_close_ratio,
            self.vertical_close_ratio,
            self.minimum_component_height_ratio,
            self.maximum_component_height_ratio,
            self.minimum_component_width_ratio,
            self.maximum_component_width_ratio,
            self.minimum_label_width_ratio,
            self.minimum_component_area_ratio,
            self.minimum_fill_ratio,
            self.digit_group_gap_ratio,
            self.digit_group_baseline_ratio,
            self.axis_x_tolerance_ratio,
            self.column_minimum_gap_ratio,
            self.column_maximum_gap_ratio,
            self.axis_y_tolerance_ratio,
            self.row_minimum_gap_ratio,
            self.row_maximum_gap_ratio,
            self.assignment_x_tolerance_ratio,
            self.assignment_y_tolerance_ratio,
            self.minimum_ambiguity_margin,
            self.prior_axis_tolerance_ratio,
        )
        if (
            self.thumbnail_max_edge < 128
            or self.minimum_predicted_text_height < 4
            or any(value < 0 or value > 1 for value in ratios)
            or not self.minimum_x_ratio < self.maximum_x_ratio
            or not self.minimum_y_ratio < self.maximum_y_ratio
            or not self.maximum_y_ratio <= self.expanded_maximum_y_ratio
            or not self.minimum_component_height_ratio < self.maximum_component_height_ratio
            or not self.minimum_component_width_ratio < self.maximum_component_width_ratio
            or not self.column_minimum_gap_ratio < self.column_maximum_gap_ratio
            or not self.row_minimum_gap_ratio < self.row_maximum_gap_ratio
            or self.minimum_label_aspect_ratio < 1
            or not 3 <= self.minimum_full_lattice_cells <= 9
        ):
            raise ValueError("Middle-row locator configuration is invalid.")

    def as_dict(self) -> dict[str, object]:
        return {
            "assignmentTolerance": {
                "x": self.assignment_x_tolerance_ratio,
                "y": self.assignment_y_tolerance_ratio,
            },
            "axisTolerance": {
                "x": self.axis_x_tolerance_ratio,
                "y": self.axis_y_tolerance_ratio,
            },
            "brightness": [self.minimum_brightness, self.maximum_brightness],
            "columnGap": [self.column_minimum_gap_ratio, self.column_maximum_gap_ratio],
            "componentArea": self.minimum_component_area_ratio,
            "componentHeight": [
                self.minimum_component_height_ratio,
                self.maximum_component_height_ratio,
            ],
            "componentWidth": [
                self.minimum_component_width_ratio,
                self.maximum_component_width_ratio,
            ],
            "expandedMaximumYRatio": self.expanded_maximum_y_ratio,
            "digitGrouping": {
                "baseline": self.digit_group_baseline_ratio,
                "gap": self.digit_group_gap_ratio,
            },
            "fillRatio": self.minimum_fill_ratio,
            "labelShape": [
                self.minimum_label_width_ratio,
                self.minimum_label_aspect_ratio,
            ],
            "minimumAmbiguityMargin": self.minimum_ambiguity_margin,
            "minimumFullLatticeCells": self.minimum_full_lattice_cells,
            "minimumPredictedTextHeight": self.minimum_predicted_text_height,
            "morphology": [self.horizontal_close_ratio, self.vertical_close_ratio],
            "priorAxisTolerance": self.prior_axis_tolerance_ratio,
            "roi": [
                self.minimum_x_ratio,
                self.minimum_y_ratio,
                self.maximum_x_ratio,
                self.maximum_y_ratio,
            ],
            "roiBoundaryMarginRatio": self.roi_boundary_margin_ratio,
            "rowGap": [self.row_minimum_gap_ratio, self.row_maximum_gap_ratio],
            "saturation": [self.minimum_saturation, self.maximum_saturation],
            "thumbnailMaxEdge": self.thumbnail_max_edge,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class MiddleRowCropPolicy:
    version: str = MIDDLE_ROW_CROP_POLICY_VERSION
    width_spacing_ratio: float = 0.48
    minimum_width_ratio: float = 0.065
    maximum_width_ratio: float = 0.12
    height_spacing_ratio: float = 0.28
    minimum_height_ratio: float = 0.016
    maximum_height_ratio: float = 0.035
    union_padding_ratio: float = 0.30

    def as_dict(self) -> dict[str, object]:
        return {
            "height": [
                self.height_spacing_ratio,
                self.minimum_height_ratio,
                self.maximum_height_ratio,
            ],
            "unionPadding": self.union_padding_ratio,
            "version": self.version,
            "width": [
                self.width_spacing_ratio,
                self.minimum_width_ratio,
                self.maximum_width_ratio,
            ],
        }


@dataclass(frozen=True, slots=True)
class CropCompletenessPolicy:
    version: str = MIDDLE_ROW_CROP_COMPLETENESS_VERSION
    minimum_text_margin_ratio: float = 0.035
    maximum_text_height_ratio: float = 2.2
    maximum_text_width_ratio: float = 1.22
    maximum_baseline_delta_ratio: float = 0.45

    def as_dict(self) -> dict[str, object]:
        return {
            "maximumBaselineDeltaRatio": self.maximum_baseline_delta_ratio,
            "maximumTextHeightRatio": self.maximum_text_height_ratio,
            "maximumTextWidthRatio": self.maximum_text_width_ratio,
            "minimumTextMarginRatio": self.minimum_text_margin_ratio,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class LocalReadabilityPolicy:
    version: str = MIDDLE_ROW_READABILITY_VERSION
    minimum_tenengrad: float = 7.0
    minimum_contrast: float = 18.0
    minimum_edge_density: float = 0.003
    maximum_dark_ratio: float = 0.92
    maximum_bright_ratio: float = 0.90

    def as_dict(self) -> dict[str, object]:
        return {
            "maximumBrightRatio": self.maximum_bright_ratio,
            "maximumDarkRatio": self.maximum_dark_ratio,
            "minimumContrast": self.minimum_contrast,
            "minimumEdgeDensity": self.minimum_edge_density,
            "minimumTenengrad": self.minimum_tenengrad,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class OcrPreprocessingProfile:
    """Exactly one production preprocessing profile for later Paddle use."""

    version: str = MIDDLE_ROW_OCR_PREPROCESSING_VERSION
    color_space: str = "RGB"
    resize_height: int = 48
    maximum_resize_width: int = 320
    interpolation: str = "INTER_LINEAR"
    normalization: str = "paddle-minus-one-to-one-v1"

    def as_dict(self) -> dict[str, object]:
        return {
            "colorSpace": self.color_space,
            "interpolation": self.interpolation,
            "maximumResizeWidth": self.maximum_resize_width,
            "normalization": self.normalization,
            "resizeHeight": self.resize_height,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class MiddleRowLatticePrior:
    """Position-only prior; it never contains or proves sequence values."""

    column_axes: tuple[float, float, float]
    row_axes: tuple[float, float, float]
    local_scale: float
    local_slant: float
    locked: bool = True

    def __post_init__(self) -> None:
        if (
            not self.locked
            or tuple(sorted(self.column_axes)) != self.column_axes
            or tuple(sorted(self.row_axes)) != self.row_axes
            or any(not 0 <= value <= 1 for value in (*self.column_axes, *self.row_axes))
            or self.local_scale <= 0
        ):
            raise ValueError("Middle-row lattice prior is invalid or unlocked.")


@dataclass(frozen=True, slots=True)
class LocalQualityScores:
    tenengrad: float
    contrast: float
    edge_density: float
    dark_ratio: float
    bright_ratio: float
    directional_blur_ratio: float


@dataclass(frozen=True, slots=True)
class MiddleRowLabelCrop:
    box: BoundingBox
    rgb: NDArray[np.uint8]
    component_box: BoundingBox
    complete: bool
    quality: LocalQualityScores
    readable: bool


@dataclass(frozen=True, slots=True)
class MiddleRowLocation:
    locator_mode: MiddleRowLocatorMode
    column_axes: tuple[float, float, float]
    row_axes: tuple[float, float, float]
    middle_row_centers: tuple[tuple[float, float], ...]
    candidate_boxes: tuple[BoundingBox, ...]
    crop_boxes: tuple[BoundingBox, BoundingBox, BoundingBox]
    crops: tuple[MiddleRowLabelCrop, MiddleRowLabelCrop, MiddleRowLabelCrop]
    best_score: float
    second_best_score: float | None
    ambiguity_margin: float
    local_scale: float
    local_slant: float

    def as_prior(self, dimensions: ImageDimensions) -> MiddleRowLatticePrior:
        return MiddleRowLatticePrior(
            column_axes=tuple(value / dimensions.width for value in self.column_axes),  # type: ignore[arg-type]
            row_axes=tuple(value / dimensions.height for value in self.row_axes),  # type: ignore[arg-type]
            local_scale=self.local_scale / max(dimensions.width, dimensions.height),
            local_slant=self.local_slant,
        )


@dataclass(frozen=True, slots=True)
class MiddleRowLocatorResult:
    location: MiddleRowLocation | None
    reason_code: MiddleRowUnknownReason | None
    diagnostics: Mapping[str, object]

    def __post_init__(self) -> None:
        if (self.location is None) == (self.reason_code is None):
            raise ValueError("Locator result must contain either a location or an unknown reason.")


@dataclass(frozen=True, slots=True)
class MiddleRowComponentPolicy:
    locator: MiddleRowLocatorConfig = MiddleRowLocatorConfig()
    crops: MiddleRowCropPolicy = MiddleRowCropPolicy()
    completeness: CropCompletenessPolicy = CropCompletenessPolicy()
    readability: LocalReadabilityPolicy = LocalReadabilityPolicy()
    preprocessing: OcrPreprocessingProfile = OcrPreprocessingProfile()

    @property
    def fingerprint(self) -> str:
        value = {
            "coordinateSpace": MIDDLE_ROW_COORDINATE_SPACE,
            "cropCompleteness": self.completeness.as_dict(),
            "cropPolicy": self.crops.as_dict(),
            "exifPolicy": "pillow-imageops-exif-transpose-once-v1",
            "locator": self.locator.as_dict(),
            "preprocessing": self.preprocessing.as_dict(),
            "readability": self.readability.as_dict(),
            "variantId": MIDDLE_ROW_RANGE_VARIANT,
        }
        return hashlib.sha256(
            json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class _CandidateBox:
    box: BoundingBox
    area: int
    fill_ratio: float


@dataclass(frozen=True, slots=True)
class _LatticeHypothesis:
    columns: tuple[float, float, float]
    rows: tuple[float, float, float]
    assignments: Mapping[tuple[int, int], tuple[_CandidateBox, ...]]
    score: float
    grid_centers: Mapping[tuple[int, int], tuple[float, float]]


class MiddleRowTripleLocator:
    """Find exactly three source-direct labels without recognizing their text."""

    def __init__(self, policy: MiddleRowComponentPolicy | None = None) -> None:
        self.policy = policy or MiddleRowComponentPolicy()

    @property
    def fingerprint(self) -> str:
        return self.policy.fingerprint

    def locate(
        self,
        source: CanonicalSourceImage,
        *,
        prior: MiddleRowLatticePrior | None = None,
    ) -> MiddleRowLocatorResult:
        thumbnail, scale_x, scale_y = self._thumbnail(source.rgb)
        candidates = self._candidate_boxes(thumbnail)
        adaptive_thumbnail = False
        if candidates:
            median_height = float(median(candidate.box.height for candidate in candidates))
            if median_height < self.policy.locator.minimum_predicted_text_height:
                requested_maximum = min(
                    max(source.rgb.shape[:2]),
                    int(
                        np.ceil(
                            self.policy.locator.thumbnail_max_edge
                            * self.policy.locator.minimum_predicted_text_height
                            / median_height
                        )
                    ),
                )
                if requested_maximum > self.policy.locator.thumbnail_max_edge:
                    thumbnail, scale_x, scale_y = self._thumbnail(
                        source.rgb,
                        maximum_edge=requested_maximum,
                    )
                    candidates = self._candidate_boxes(thumbnail)
                    adaptive_thumbnail = True
        hypotheses = self._lattice_hypotheses(candidates, thumbnail.shape[:2])
        expanded_roi = False
        near_roi_boundary = bool(
            hypotheses
            and max(center[1] for center in hypotheses[0].grid_centers.values())
            >= thumbnail.shape[0]
            * (self.policy.locator.maximum_y_ratio - self.policy.locator.roi_boundary_margin_ratio)
        )
        if not self._has_unambiguous_complete_middle_row(hypotheses) or near_roi_boundary:
            expanded_candidates = self._candidate_boxes(
                thumbnail,
                maximum_y_ratio=self.policy.locator.expanded_maximum_y_ratio,
            )
            expanded_hypotheses = self._lattice_hypotheses(
                expanded_candidates,
                thumbnail.shape[:2],
            )
            if self._has_unambiguous_complete_middle_row(expanded_hypotheses):
                candidates = expanded_candidates
                hypotheses = expanded_hypotheses
                expanded_roi = True
        selected: _LatticeHypothesis | None = hypotheses[0] if hypotheses else None
        second_score = hypotheses[1].score if len(hypotheses) > 1 else None
        ambiguity_margin = (
            selected.score - second_score if selected and second_score is not None else 1.0
        )
        mode = MiddleRowLocatorMode.FULL_LATTICE

        if selected is None or ambiguity_margin < self.policy.locator.minimum_ambiguity_margin:
            fallback = self._prior_hypothesis(candidates, thumbnail.shape[:2], prior)
            if fallback is None:
                reason = (
                    MiddleRowUnknownReason.AMBIGUOUS_LATTICE
                    if selected is not None
                    else MiddleRowUnknownReason.UNKNOWN_LATTICE
                )
                return MiddleRowLocatorResult(
                    location=None,
                    reason_code=reason,
                    diagnostics={
                        "ambiguityMargin": ambiguity_margin,
                        "candidateCount": len(candidates),
                        "hypothesisCount": len(hypotheses),
                        "expandedRoi": expanded_roi,
                        "adaptiveThumbnail": adaptive_thumbnail,
                    },
                )
            selected = fallback
            second_score = None
            ambiguity_margin = 1.0
            mode = MiddleRowLocatorMode.MIDDLE_ROW_WITH_LOCKED_PRIOR

        source_columns = tuple(value * scale_x for value in selected.columns)
        source_rows = tuple(value * scale_y for value in selected.rows)
        source_candidate_boxes = tuple(
            _scale_box(candidate.box, scale_x, scale_y, source.oriented_dimensions)
            for candidate in candidates
        )
        if any((1, column_index) not in selected.assignments for column_index in range(3)):
            return MiddleRowLocatorResult(
                location=None,
                reason_code=MiddleRowUnknownReason.INCOMPLETE_MIDDLE_ROW,
                diagnostics={"candidateCount": len(candidates), "locatorMode": mode.value},
            )
        source_middle_centers = tuple(
            _scale_box(
                _union_boxes(value.box for value in selected.assignments[(1, column_index)]),
                scale_x,
                scale_y,
                source.oriented_dimensions,
            ).center
            for column_index in range(3)
        )
        crops = self._extract_crops(
            source.rgb,
            selected,
            scale_x=scale_x,
            scale_y=scale_y,
        )
        if crops is None:
            return MiddleRowLocatorResult(
                location=None,
                reason_code=MiddleRowUnknownReason.CROP_OUT_OF_BOUNDS,
                diagnostics={"candidateCount": len(candidates), "locatorMode": mode.value},
            )
        if not all(crop.complete for crop in crops):
            return MiddleRowLocatorResult(
                location=None,
                reason_code=MiddleRowUnknownReason.CROP_POSSIBLY_CLIPPED,
                diagnostics={
                    "cropBoxes": [crop.box.as_dict() for crop in crops],
                    "locatorMode": mode.value,
                },
            )
        if not all(crop.readable for crop in crops):
            reason = (
                MiddleRowUnknownReason.LOCAL_BLUR
                if any(
                    crop.quality.tenengrad < self.policy.readability.minimum_tenengrad
                    for crop in crops
                )
                else MiddleRowUnknownReason.LOW_LOCAL_CONTRAST
            )
            return MiddleRowLocatorResult(
                location=None,
                reason_code=reason,
                diagnostics={
                    "locatorMode": mode.value,
                    "quality": [
                        {
                            "brightRatio": crop.quality.bright_ratio,
                            "contrast": crop.quality.contrast,
                            "darkRatio": crop.quality.dark_ratio,
                            "edgeDensity": crop.quality.edge_density,
                            "tenengrad": crop.quality.tenengrad,
                        }
                        for crop in crops
                    ],
                },
            )

        column_spacing = median(
            (
                source_middle_centers[1][0] - source_middle_centers[0][0],
                source_middle_centers[2][0] - source_middle_centers[1][0],
            )
        )
        row_spacing = median((source_rows[1] - source_rows[0], source_rows[2] - source_rows[1]))
        slant = self._local_slant(selected)
        typed_columns = (source_columns[0], source_columns[1], source_columns[2])
        typed_rows = (source_rows[0], source_rows[1], source_rows[2])
        typed_crops = (crops[0], crops[1], crops[2])
        return MiddleRowLocatorResult(
            location=MiddleRowLocation(
                locator_mode=mode,
                column_axes=typed_columns,
                row_axes=typed_rows,
                middle_row_centers=source_middle_centers,
                candidate_boxes=source_candidate_boxes,
                crop_boxes=(crops[0].box, crops[1].box, crops[2].box),
                crops=typed_crops,
                best_score=selected.score,
                second_best_score=second_score,
                ambiguity_margin=ambiguity_margin,
                local_scale=float(median((column_spacing, row_spacing))),
                local_slant=slant,
            ),
            reason_code=None,
            diagnostics={
                "candidateCount": len(candidates),
                "adaptiveThumbnail": adaptive_thumbnail,
                "expandedRoi": expanded_roi,
                "locatorMode": mode.value,
                "thumbnailHeight": thumbnail.shape[0],
                "thumbnailWidth": thumbnail.shape[1],
            },
        )

    def _thumbnail(
        self,
        rgb: NDArray[np.uint8],
        *,
        maximum_edge: int | None = None,
    ) -> tuple[NDArray[np.uint8], float, float]:
        height, width = rgb.shape[:2]
        maximum = max(height, width)
        resolved_maximum_edge = maximum_edge or self.policy.locator.thumbnail_max_edge
        if maximum <= resolved_maximum_edge:
            return rgb, 1.0, 1.0
        scale = resolved_maximum_edge / maximum
        target_width = max(1, int(round(width * scale)))
        target_height = max(1, int(round(height * scale)))
        thumbnail = np.asarray(
            cv2.resize(rgb, (target_width, target_height), interpolation=cv2.INTER_AREA),
            dtype=np.uint8,
        )
        return thumbnail, width / target_width, height / target_height

    def _candidate_boxes(
        self,
        rgb: NDArray[np.uint8],
        *,
        maximum_y_ratio: float | None = None,
    ) -> tuple[_CandidateBox, ...]:
        config = self.policy.locator
        height, width = rgb.shape[:2]
        hsv = np.asarray(cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV), dtype=np.uint8)
        mask = cv2.inRange(
            hsv,
            np.array((0, config.minimum_saturation, config.minimum_brightness)),
            np.array((179, config.maximum_saturation, config.maximum_brightness)),
        )
        region = np.zeros_like(mask)
        left = int(round(width * config.minimum_x_ratio))
        right = int(round(width * config.maximum_x_ratio))
        top = int(round(height * config.minimum_y_ratio))
        bottom = int(round(height * (maximum_y_ratio or config.maximum_y_ratio)))
        region[top:bottom, left:right] = mask[top:bottom, left:right]
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (
                max(1, int(round(width * config.horizontal_close_ratio)) | 1),
                max(1, int(round(height * config.vertical_close_ratio)) | 1),
            ),
        )
        closed = cv2.morphologyEx(region, cv2.MORPH_CLOSE, kernel)
        count, _, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
        result: list[_CandidateBox] = []
        minimum_area = max(4, int(round(width * height * config.minimum_component_area_ratio)))
        for index in range(1, count):
            x, y, box_width, box_height, area = (int(value) for value in stats[index])
            if not (
                height * config.minimum_component_height_ratio
                <= box_height
                <= height * config.maximum_component_height_ratio
                and width * config.minimum_component_width_ratio
                <= box_width
                <= width * config.maximum_component_width_ratio
                and area >= minimum_area
            ):
                continue
            fill_ratio = area / max(1, box_width * box_height)
            if fill_ratio < config.minimum_fill_ratio:
                continue
            result.append(
                _CandidateBox(
                    box=BoundingBox(x, y, x + box_width, y + box_height),
                    area=area,
                    fill_ratio=float(fill_ratio),
                )
            )
        grouped = self._group_digit_fragments(result, width=width, height=height)
        return tuple(
            candidate
            for candidate in grouped
            if candidate.box.width >= width * config.minimum_label_width_ratio
            and candidate.box.width / max(1, candidate.box.height)
            >= config.minimum_label_aspect_ratio
        )

    def _group_digit_fragments(
        self,
        candidates: Sequence[_CandidateBox],
        *,
        width: int,
        height: int,
    ) -> tuple[_CandidateBox, ...]:
        config = self.policy.locator
        pending = sorted(candidates, key=lambda value: (value.box.center[1], value.box.left))
        groups: list[list[_CandidateBox]] = []
        for candidate in pending:
            selected: list[_CandidateBox] | None = None
            for group in groups:
                union = _union_boxes(item.box for item in group)
                gap = max(0, candidate.box.left - union.right, union.left - candidate.box.right)
                baseline_delta = abs(candidate.box.bottom - union.bottom)
                height_ratio = max(candidate.box.height, union.height) / min(
                    candidate.box.height, union.height
                )
                if (
                    gap <= width * config.digit_group_gap_ratio
                    and baseline_delta <= height * config.digit_group_baseline_ratio
                    and height_ratio <= 2.2
                ):
                    selected = group
                    break
            if selected is None:
                groups.append([candidate])
            else:
                selected.append(candidate)
        result: list[_CandidateBox] = []
        for group in groups:
            box = _union_boxes(item.box for item in group)
            result.append(
                _CandidateBox(
                    box=box,
                    area=sum(item.area for item in group),
                    fill_ratio=sum(item.area for item in group) / max(1, box.width * box.height),
                )
            )
        return tuple(result)

    def _lattice_hypotheses(
        self,
        candidates: Sequence[_CandidateBox],
        shape: tuple[int, int],
    ) -> tuple[_LatticeHypothesis, ...]:
        if len(candidates) < self.policy.locator.minimum_full_lattice_cells:
            return ()
        height, width = shape
        hypotheses: list[_LatticeHypothesis] = []
        seen_assignments: set[tuple[tuple[int, int, int], ...]] = set()
        for origin_index, origin in enumerate(candidates):
            origin_x, origin_y = origin.box.center
            for right_index, right in enumerate(candidates):
                if right_index == origin_index:
                    continue
                right_x, right_y = right.box.center
                horizontal = (right_x - origin_x, right_y - origin_y)
                if not (
                    width * self.policy.locator.column_minimum_gap_ratio
                    <= horizontal[0]
                    <= width * self.policy.locator.column_maximum_gap_ratio
                    and abs(horizontal[1])
                    <= height * self.policy.locator.assignment_y_tolerance_ratio * 2
                ):
                    continue
                if (
                    self._nearest_candidate(
                        candidates,
                        (origin_x + 2 * horizontal[0], origin_y + 2 * horizontal[1]),
                        shape,
                    )
                    is None
                ):
                    continue
                for down_index, down in enumerate(candidates):
                    if down_index in {origin_index, right_index}:
                        continue
                    down_x, down_y = down.box.center
                    vertical = (down_x - origin_x, down_y - origin_y)
                    if not (
                        height * self.policy.locator.row_minimum_gap_ratio
                        <= vertical[1]
                        <= height * self.policy.locator.row_maximum_gap_ratio
                        and abs(vertical[0])
                        <= width * self.policy.locator.assignment_x_tolerance_ratio
                    ):
                        continue
                    grid_centers = {
                        (row_index, column_index): (
                            origin_x + column_index * horizontal[0] + row_index * vertical[0],
                            origin_y + column_index * horizontal[1] + row_index * vertical[1],
                        )
                        for row_index in range(3)
                        for column_index in range(3)
                    }
                    assignments: dict[tuple[int, int], tuple[_CandidateBox, ...]] = {}
                    assignment_indices: dict[tuple[int, int], int] = {}
                    used: set[int] = set()
                    residual = 0.0
                    for key, expected_center in grid_centers.items():
                        nearest = self._nearest_candidate(
                            candidates,
                            expected_center,
                            shape,
                            excluded=used,
                        )
                        if nearest is None:
                            continue
                        distance, candidate_index = nearest
                        used.add(candidate_index)
                        assignments[key] = (candidates[candidate_index],)
                        assignment_indices[key] = candidate_index
                        residual += distance
                    occupied = tuple(assignments)
                    if (
                        len(occupied) < self.policy.locator.minimum_full_lattice_cells
                        or len({row_index for row_index, _ in occupied}) < 3
                        or len({column_index for _, column_index in occupied}) < 3
                    ):
                        continue
                    identity = tuple(
                        sorted(
                            (row, column, candidate_index)
                            for (row, column), candidate_index in assignment_indices.items()
                        )
                    )
                    if identity in seen_assignments:
                        continue
                    seen_assignments.add(identity)
                    assigned_candidates = [values[0] for values in assignments.values()]
                    widths = [value.box.width for value in assigned_candidates]
                    heights = [value.box.height for value in assigned_candidates]
                    shape_consistency = (
                        min(widths) / max(widths) + min(heights) / max(heights)
                    ) / 2
                    residual_score = 1.0 - min(1.0, residual / len(assignments))
                    score = (
                        len(occupied) / 9 * 0.65 + residual_score * 0.20 + shape_consistency * 0.15
                    )
                    columns = (
                        grid_centers[(1, 0)][0],
                        grid_centers[(1, 1)][0],
                        grid_centers[(1, 2)][0],
                    )
                    rows = (
                        grid_centers[(0, 1)][1],
                        grid_centers[(1, 1)][1],
                        grid_centers[(2, 1)][1],
                    )
                    hypotheses.append(
                        _LatticeHypothesis(
                            columns=columns,
                            rows=rows,
                            assignments=assignments,
                            score=float(score),
                            grid_centers=grid_centers,
                        )
                    )
        hypotheses.sort(
            key=lambda value: (
                value.score,
                -value.rows[1],
                -value.columns[1],
            ),
            reverse=True,
        )
        return tuple(hypotheses)

    def _has_unambiguous_complete_middle_row(
        self,
        hypotheses: Sequence[_LatticeHypothesis],
    ) -> bool:
        if not hypotheses:
            return False
        second_score = hypotheses[1].score if len(hypotheses) > 1 else None
        margin = hypotheses[0].score - second_score if second_score is not None else 1.0
        return margin >= self.policy.locator.minimum_ambiguity_margin and all(
            (1, column_index) in hypotheses[0].assignments for column_index in range(3)
        )

    def _nearest_candidate(
        self,
        candidates: Sequence[_CandidateBox],
        expected_center: tuple[float, float],
        shape: tuple[int, int],
        *,
        excluded: set[int] | None = None,
    ) -> tuple[float, int] | None:
        height, width = shape
        x_tolerance = width * self.policy.locator.axis_x_tolerance_ratio
        y_tolerance = height * self.policy.locator.axis_y_tolerance_ratio * 1.5
        matches: list[tuple[float, int]] = []
        for index, candidate in enumerate(candidates):
            if excluded and index in excluded:
                continue
            x, y = candidate.box.center
            x_distance = (x - expected_center[0]) / x_tolerance
            y_distance = (y - expected_center[1]) / y_tolerance
            normalized_distance = x_distance * x_distance + y_distance * y_distance
            if normalized_distance <= 1.0:
                matches.append((normalized_distance, index))
        return min(matches) if matches else None

    def _prior_hypothesis(
        self,
        candidates: Sequence[_CandidateBox],
        shape: tuple[int, int],
        prior: MiddleRowLatticePrior | None,
    ) -> _LatticeHypothesis | None:
        if prior is None:
            return None
        height, width = shape
        columns = (
            prior.column_axes[0] * width,
            prior.column_axes[1] * width,
            prior.column_axes[2] * width,
        )
        rows = (
            prior.row_axes[0] * height,
            prior.row_axes[1] * height,
            prior.row_axes[2] * height,
        )
        slant = float(np.tan(np.radians(prior.local_slant)))
        assignments: dict[tuple[int, int], tuple[_CandidateBox, ...]] = {}
        for column_index, column in enumerate(columns):
            expected_y = rows[1] + slant * (column - columns[1])
            matching = self._nearest_candidate(
                candidates,
                (column, expected_y),
                shape,
            )
            if matching is None:
                return None
            assignments[(1, column_index)] = (candidates[matching[1]],)
        return _LatticeHypothesis(
            columns=columns,
            rows=rows,
            assignments=assignments,
            score=0.5,
            grid_centers={
                (row_index, column_index): (
                    columns[column_index],
                    rows[row_index] + slant * (columns[column_index] - columns[1]),
                )
                for row_index in range(3)
                for column_index in range(3)
            },
        )

    def _extract_crops(
        self,
        source_rgb: NDArray[np.uint8],
        hypothesis: _LatticeHypothesis,
        *,
        scale_x: float,
        scale_y: float,
    ) -> tuple[MiddleRowLabelCrop, MiddleRowLabelCrop, MiddleRowLabelCrop] | None:
        height, width = source_rgb.shape[:2]
        columns = tuple(value * scale_x for value in hypothesis.columns)
        rows = tuple(value * scale_y for value in hypothesis.rows)
        column_spacing = float(median((columns[1] - columns[0], columns[2] - columns[1])))
        row_spacing = float(median((rows[1] - rows[0], rows[2] - rows[1])))
        crop_width = int(
            round(
                _clamp(
                    column_spacing * self.policy.crops.width_spacing_ratio,
                    width * self.policy.crops.minimum_width_ratio,
                    width * self.policy.crops.maximum_width_ratio,
                )
            )
        )
        crop_height = int(
            round(
                _clamp(
                    row_spacing * self.policy.crops.height_spacing_ratio,
                    height * self.policy.crops.minimum_height_ratio,
                    height * self.policy.crops.maximum_height_ratio,
                )
            )
        )
        result: list[MiddleRowLabelCrop] = []
        for column_index, _column in enumerate(columns):
            assigned = hypothesis.assignments.get((1, column_index), ())
            if not assigned:
                return None
            component_thumbnail = _union_boxes(value.box for value in assigned)
            component = _scale_box(
                component_thumbnail,
                scale_x,
                scale_y,
                ImageDimensions(width=width, height=height),
            )
            component_center = component.center
            if (
                component_center[0] - crop_width / 2 < 0
                or component_center[0] + crop_width / 2 > width
                or component_center[1] - crop_height / 2 < 0
                or component_center[1] + crop_height / 2 > height
            ):
                return None
            box = _centered_box(
                center=component_center,
                width=crop_width,
                height=crop_height,
                dimensions=ImageDimensions(width=width, height=height),
            )
            padded_component = _padded_box(
                component,
                padding=max(
                    2,
                    int(round(component.height * self.policy.crops.union_padding_ratio)),
                ),
                dimensions=ImageDimensions(width=width, height=height),
            )
            if (
                padded_component.width >= crop_width * 0.45
                and padded_component.width <= crop_width
                and padded_component.height <= crop_height
            ):
                box = _union_boxes((box, padded_component))
                box = _bounded_box(box, ImageDimensions(width=width, height=height))
            crop = source_rgb[box.top : box.bottom, box.left : box.right].copy()
            if crop.size == 0:
                return None
            quality = _quality_scores(crop)
            result.append(
                MiddleRowLabelCrop(
                    box=box,
                    rgb=crop,
                    component_box=component,
                    complete=True,
                    quality=quality,
                    readable=_is_readable(quality, self.policy.readability),
                )
            )
        completed = self._apply_completeness(tuple(result))
        return (completed[0], completed[1], completed[2])

    def _apply_completeness(
        self,
        crops: tuple[MiddleRowLabelCrop, ...],
    ) -> tuple[MiddleRowLabelCrop, ...]:
        policy = self.policy.completeness
        heights = [crop.component_box.height for crop in crops]
        widths = [crop.component_box.width for crop in crops]
        baselines = [crop.component_box.bottom for crop in crops]
        center_x_values = np.asarray(
            [crop.component_box.center[0] for crop in crops],
            dtype=np.float64,
        )
        baseline_values = np.asarray(baselines, dtype=np.float64)
        baseline_fit = np.polyval(np.polyfit(center_x_values, baseline_values, 1), center_x_values)
        maximum_baseline_residual = float(np.max(np.abs(baseline_values - baseline_fit)))
        shared = (
            max(heights) / min(heights) <= policy.maximum_text_height_ratio
            and max(widths) / min(widths) <= policy.maximum_text_width_ratio
            and maximum_baseline_residual <= median(heights) * policy.maximum_baseline_delta_ratio
        )
        result: list[MiddleRowLabelCrop] = []
        for index, crop in enumerate(crops):
            horizontal_margin = min(
                crop.component_box.left - crop.box.left,
                crop.box.right - crop.component_box.right,
            )
            vertical_margin = min(
                crop.component_box.top - crop.box.top,
                crop.box.bottom - crop.component_box.bottom,
            )
            sufficient_margin = (
                horizontal_margin >= crop.box.width * policy.minimum_text_margin_ratio
                and vertical_margin >= crop.box.height * policy.minimum_text_margin_ratio
            )
            no_overlap = all(
                index == other_index or not _boxes_overlap(crop.box, other.box)
                for other_index, other in enumerate(crops)
            )
            result.append(
                MiddleRowLabelCrop(
                    box=crop.box,
                    rgb=crop.rgb,
                    component_box=crop.component_box,
                    complete=shared and sufficient_margin and no_overlap,
                    quality=crop.quality,
                    readable=crop.readable,
                )
            )
        return tuple(result)

    @staticmethod
    def _local_slant(hypothesis: _LatticeHypothesis) -> float:
        centers: list[tuple[float, float]] = []
        for column_index in range(3):
            values = hypothesis.assignments.get((1, column_index), ())
            if values:
                box = _union_boxes(value.box for value in values)
                centers.append(box.center)
        if len(centers) < 2:
            return 0.0
        x_values = np.asarray([value[0] for value in centers], dtype=np.float64)
        y_values = np.asarray([value[1] for value in centers], dtype=np.float64)
        slope = np.polyfit(x_values, y_values, 1)[0]
        return float(np.degrees(np.arctan(slope)))


def _union_boxes(boxes: Iterable[BoundingBox]) -> BoundingBox:
    values: tuple[BoundingBox, ...] = tuple(boxes)
    if not values:
        raise ValueError("Cannot union an empty bounding-box collection.")
    return BoundingBox(
        left=min(value.left for value in values),
        top=min(value.top for value in values),
        right=max(value.right for value in values),
        bottom=max(value.bottom for value in values),
    )


def _scale_box(
    box: BoundingBox,
    scale_x: float,
    scale_y: float,
    dimensions: ImageDimensions,
) -> BoundingBox:
    return _bounded_box(
        BoundingBox(
            left=max(0, int(np.floor(box.left * scale_x))),
            top=max(0, int(np.floor(box.top * scale_y))),
            right=max(1, int(np.ceil(box.right * scale_x))),
            bottom=max(1, int(np.ceil(box.bottom * scale_y))),
        ),
        dimensions,
    )


def _centered_box(
    *,
    center: tuple[float, float],
    width: int,
    height: int,
    dimensions: ImageDimensions,
) -> BoundingBox:
    width = min(max(1, width), dimensions.width)
    height = min(max(1, height), dimensions.height)
    left = int(round(center[0] - width / 2))
    top = int(round(center[1] - height / 2))
    left = min(max(0, left), dimensions.width - width)
    top = min(max(0, top), dimensions.height - height)
    return BoundingBox(left, top, left + width, top + height)


def _padded_box(
    box: BoundingBox,
    *,
    padding: int,
    dimensions: ImageDimensions,
) -> BoundingBox:
    return BoundingBox(
        left=max(0, box.left - padding),
        top=max(0, box.top - padding),
        right=min(dimensions.width, box.right + padding),
        bottom=min(dimensions.height, box.bottom + padding),
    )


def _bounded_box(box: BoundingBox, dimensions: ImageDimensions) -> BoundingBox:
    left = min(max(0, box.left), dimensions.width - 1)
    top = min(max(0, box.top), dimensions.height - 1)
    right = min(max(left + 1, box.right), dimensions.width)
    bottom = min(max(top + 1, box.bottom), dimensions.height)
    return BoundingBox(left, top, right, bottom)


def _boxes_overlap(first: BoundingBox, second: BoundingBox) -> bool:
    return not (
        first.right <= second.left
        or second.right <= first.left
        or first.bottom <= second.top
        or second.bottom <= first.top
    )


def _quality_scores(rgb: NDArray[np.uint8]) -> LocalQualityScores:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    x_gradient = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    y_gradient = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    x_energy = float(np.mean(np.abs(x_gradient)))
    y_energy = float(np.mean(np.abs(y_gradient)))
    tenengrad = float(np.mean(np.sqrt(x_gradient * x_gradient + y_gradient * y_gradient)))
    # Sequence labels occupy only a small fraction of the padded crop.  P90
    # can therefore still describe the background and incorrectly classify a
    # crisp label as low contrast.  P98 retains a conservative local signal
    # without thresholding or inventing missing strokes.
    low, high = np.percentile(gray, (10, 98))
    edges = cv2.Canny(gray, 50, 150)
    return LocalQualityScores(
        tenengrad=tenengrad,
        contrast=float(high - low),
        edge_density=float(np.count_nonzero(edges) / edges.size),
        dark_ratio=float(np.count_nonzero(gray <= 8) / gray.size),
        bright_ratio=float(np.count_nonzero(gray >= 247) / gray.size),
        directional_blur_ratio=max(x_energy, y_energy) / max(1e-6, min(x_energy, y_energy)),
    )


def _is_readable(scores: LocalQualityScores, policy: LocalReadabilityPolicy) -> bool:
    return (
        scores.tenengrad >= policy.minimum_tenengrad
        and scores.contrast >= policy.minimum_contrast
        and scores.edge_density >= policy.minimum_edge_density
        and scores.dark_ratio <= policy.maximum_dark_ratio
        and scores.bright_ratio <= policy.maximum_bright_ratio
    )


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))


__all__ = [
    "MIDDLE_ROW_COORDINATE_SPACE",
    "MIDDLE_ROW_CROP_COMPLETENESS_VERSION",
    "MIDDLE_ROW_CROP_POLICY_VERSION",
    "MIDDLE_ROW_LOCATOR_VERSION",
    "MIDDLE_ROW_OCR_PREPROCESSING_VERSION",
    "MIDDLE_ROW_READABILITY_VERSION",
    "BoundingBox",
    "CanonicalSourceImage",
    "CropCompletenessPolicy",
    "ImageDimensions",
    "LocalQualityScores",
    "LocalReadabilityPolicy",
    "MiddleRowComponentPolicy",
    "MiddleRowCropPolicy",
    "MiddleRowLabelCrop",
    "MiddleRowLatticePrior",
    "MiddleRowLocation",
    "MiddleRowLocatorConfig",
    "MiddleRowLocatorMode",
    "MiddleRowLocatorResult",
    "MiddleRowTripleLocator",
    "OcrPreprocessingProfile",
    "canonicalize_source_image",
]
