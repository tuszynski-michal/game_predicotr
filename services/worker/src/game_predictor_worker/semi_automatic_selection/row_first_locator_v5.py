"""Row-first source-local label locator for the experimental range OCR v5.

The locator is deliberately separate from v4.1.  It only finds potential
numeric-label crops; it neither recognizes their text nor decides a sequence
range.  Each discovered row is independent, which keeps two visible rows useful
when a hand, edge, or transition frame hides the third one.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations
from statistics import median

import cv2
import numpy as np
from numpy.typing import NDArray

from .middle_row_locator import (
    BoundingBox,
    CanonicalSourceImage,
    ImageDimensions,
    LocalQualityScores,
    LocalReadabilityPolicy,
)
from .range_proof_v5 import RangeRowOffset

ROW_FIRST_LOCATOR_VERSION = "row-first-range-locator-v1"
ROW_FIRST_LOCATOR_CONFIG_VERSION = "row-first-range-locator-config-v1"
ROW_FIRST_LOCATOR_COORDINATE_SPACE = "exif-transposed-rgb-v1"


class RowFirstLocatorUnknownReason(StrEnum):
    """Stable, local reasons why no usable numeric-label row was found."""

    UNKNOWN_ROWS = "UNKNOWN_ROWS"
    AMBIGUOUS_ROWS = "AMBIGUOUS_ROWS"
    POSITION_PRIOR_MISMATCH = "POSITION_PRIOR_MISMATCH"


@dataclass(frozen=True, slots=True)
class RowFirstLocatorConfig:
    """Versioned layout-only settings for the independently fitted row finder."""

    version: str = ROW_FIRST_LOCATOR_CONFIG_VERSION
    thumbnail_max_edge: int = 960
    minimum_x_ratio: float = 0.14
    maximum_x_ratio: float = 0.90
    roi_y_levels: tuple[tuple[float, float], ...] = (
        (0.22, 0.50),
        (0.17, 0.62),
        (0.12, 0.74),
    )
    minimum_saturation: int = 0
    maximum_saturation: int = 125
    minimum_brightness: int = 160
    maximum_brightness: int = 255
    horizontal_close_ratio: float = 0.0055
    vertical_close_ratio: float = 0.0016
    minimum_component_height_ratio: float = 0.003
    maximum_component_height_ratio: float = 0.045
    minimum_component_width_ratio: float = 0.0025
    maximum_component_width_ratio: float = 0.22
    minimum_component_area_ratio: float = 0.000004
    minimum_fill_ratio: float = 0.08
    digit_group_gap_ratio: float = 0.020
    digit_group_baseline_ratio: float = 0.012
    minimum_label_width_ratio: float = 0.018
    minimum_label_aspect_ratio: float = 1.05
    maximum_label_width_ratio: float = 0.100
    row_cluster_tolerance_ratio: float = 0.024
    minimum_column_gap_ratio: float = 0.10
    maximum_column_gap_ratio: float = 0.42
    maximum_row_baseline_residual_ratio: float = 0.010
    maximum_row_spacing_imbalance: float = 2.25
    row_anchor_y_ratios: tuple[float, float, float] = (0.34, 0.40, 0.47)
    row_anchor_tolerance_ratio: float = 0.080
    crop_width_spacing_ratio: float = 0.52
    crop_minimum_width_ratio: float = 0.045
    crop_maximum_width_ratio: float = 0.15
    crop_height_component_ratio: float = 2.8
    crop_minimum_height_ratio: float = 0.018
    crop_maximum_height_ratio: float = 0.060
    crop_margin_ratio: float = 0.025

    def __post_init__(self) -> None:
        ratios = (
            self.minimum_x_ratio,
            self.maximum_x_ratio,
            self.horizontal_close_ratio,
            self.vertical_close_ratio,
            self.minimum_component_height_ratio,
            self.maximum_component_height_ratio,
            self.minimum_component_width_ratio,
            self.maximum_component_width_ratio,
            self.minimum_component_area_ratio,
            self.minimum_fill_ratio,
            self.digit_group_gap_ratio,
            self.digit_group_baseline_ratio,
            self.minimum_label_width_ratio,
            self.maximum_label_width_ratio,
            self.row_cluster_tolerance_ratio,
            self.minimum_column_gap_ratio,
            self.maximum_column_gap_ratio,
            self.maximum_row_baseline_residual_ratio,
            self.row_anchor_tolerance_ratio,
            self.crop_width_spacing_ratio,
            self.crop_minimum_width_ratio,
            self.crop_maximum_width_ratio,
            self.crop_minimum_height_ratio,
            self.crop_maximum_height_ratio,
            self.crop_margin_ratio,
        )
        if (
            self.thumbnail_max_edge < 128
            or any(value < 0 or value > 1 for value in ratios)
            or not self.minimum_x_ratio < self.maximum_x_ratio
            or not self.minimum_component_height_ratio < self.maximum_component_height_ratio
            or not self.minimum_component_width_ratio < self.maximum_component_width_ratio
            or not self.minimum_label_width_ratio < self.maximum_label_width_ratio
            or not self.minimum_column_gap_ratio < self.maximum_column_gap_ratio
            or self.minimum_label_aspect_ratio < 1
            or self.crop_height_component_ratio <= 0
            or self.maximum_row_spacing_imbalance < 1
            or tuple(sorted(self.row_anchor_y_ratios)) != self.row_anchor_y_ratios
            or len(self.row_anchor_y_ratios) != 3
            or any(start < 0 or end > 1 or start >= end for start, end in self.roi_y_levels)
            or not self.roi_y_levels
        ):
            raise ValueError("Row-first locator configuration is invalid.")

    def as_dict(self) -> dict[str, object]:
        return {
            "brightness": [self.minimum_brightness, self.maximum_brightness],
            "componentArea": self.minimum_component_area_ratio,
            "componentHeight": [
                self.minimum_component_height_ratio,
                self.maximum_component_height_ratio,
            ],
            "componentWidth": [
                self.minimum_component_width_ratio,
                self.maximum_component_width_ratio,
            ],
            "crop": {
                "heightComponentRatio": self.crop_height_component_ratio,
                "heightRange": [self.crop_minimum_height_ratio, self.crop_maximum_height_ratio],
                "margin": self.crop_margin_ratio,
                "widthRange": [self.crop_minimum_width_ratio, self.crop_maximum_width_ratio],
                "widthSpacingRatio": self.crop_width_spacing_ratio,
            },
            "digitGrouping": {
                "baseline": self.digit_group_baseline_ratio,
                "gap": self.digit_group_gap_ratio,
            },
            "fillRatio": self.minimum_fill_ratio,
            "labelShape": [
                self.minimum_label_width_ratio,
                self.minimum_label_aspect_ratio,
                self.maximum_label_width_ratio,
            ],
            "morphology": [self.horizontal_close_ratio, self.vertical_close_ratio],
            "roi": {
                "x": [self.minimum_x_ratio, self.maximum_x_ratio],
                "yLevels": [list(value) for value in self.roi_y_levels],
            },
            "rowAnchors": list(self.row_anchor_y_ratios),
            "rowAnchorTolerance": self.row_anchor_tolerance_ratio,
            "rowFit": {
                "clusterTolerance": self.row_cluster_tolerance_ratio,
                "maximumBaselineResidual": self.maximum_row_baseline_residual_ratio,
                "maximumSpacingImbalance": self.maximum_row_spacing_imbalance,
            },
            "saturation": [self.minimum_saturation, self.maximum_saturation],
            "thumbnailMaxEdge": self.thumbnail_max_edge,
            "version": self.version,
            "xGap": [self.minimum_column_gap_ratio, self.maximum_column_gap_ratio],
        }


@dataclass(frozen=True, slots=True)
class RowFirstPositionPrior:
    """Optional geometry-only initializer. It cannot attest a range value."""

    row_axes: tuple[float, float, float]
    locked: bool = True

    def __post_init__(self) -> None:
        if (
            not self.locked
            or len(self.row_axes) != 3
            or tuple(sorted(self.row_axes)) != self.row_axes
            or any(value < 0 or value > 1 for value in self.row_axes)
        ):
            raise ValueError("Row-first position prior is invalid or unlocked.")


@dataclass(frozen=True, slots=True)
class RowFirstLabelCrop:
    box: BoundingBox
    component_box: BoundingBox
    rgb: NDArray[np.uint8]
    complete: bool
    quality: LocalQualityScores
    readable: bool


@dataclass(frozen=True, slots=True)
class RowFirstRowHypothesis:
    """One independently fitted three-label row in source coordinates."""

    row: RangeRowOffset
    centers: tuple[tuple[float, float], tuple[float, float], tuple[float, float]]
    component_boxes: tuple[BoundingBox, BoundingBox, BoundingBox]
    crops: tuple[RowFirstLabelCrop, RowFirstLabelCrop, RowFirstLabelCrop]
    baseline_slope: float
    score: float
    source_roi_level: int


@dataclass(frozen=True, slots=True)
class RowFirstLocation:
    rows: tuple[RowFirstRowHypothesis, ...]
    candidate_boxes: tuple[BoundingBox, ...]
    locator_fingerprint: str


@dataclass(frozen=True, slots=True)
class RowFirstLocatorResult:
    location: RowFirstLocation | None
    reason_code: RowFirstLocatorUnknownReason | None
    diagnostics: dict[str, object]

    def __post_init__(self) -> None:
        if (self.location is None) == (self.reason_code is None):
            raise ValueError(
                "Row-first result must contain either a location or an unknown reason."
            )


@dataclass(frozen=True, slots=True)
class _Candidate:
    box: BoundingBox
    area: int
    fill_ratio: float


@dataclass(frozen=True, slots=True)
class _RowGeometry:
    boxes: tuple[_Candidate, _Candidate, _Candidate]
    center_y: float
    slope: float
    score: float
    roi_level: int


class RowFirstTripleLocator:
    """Locate all independently supported numeric rows without OCR."""

    def __init__(
        self,
        config: RowFirstLocatorConfig | None = None,
        *,
        readability: LocalReadabilityPolicy | None = None,
    ) -> None:
        self.config = config or RowFirstLocatorConfig()
        self.readability = readability or LocalReadabilityPolicy()

    @property
    def fingerprint(self) -> str:
        value = {
            "coordinateSpace": ROW_FIRST_LOCATOR_COORDINATE_SPACE,
            "exifPolicy": "pillow-imageops-exif-transpose-once-v1",
            "locator": self.config.as_dict(),
            "readability": self.readability.as_dict(),
            "variant": ROW_FIRST_LOCATOR_VERSION,
        }
        return hashlib.sha256(
            json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()

    def locate(
        self,
        source: CanonicalSourceImage,
        *,
        prior: RowFirstPositionPrior | None = None,
    ) -> RowFirstLocatorResult:
        thumbnail, scale_x, scale_y = self._thumbnail(source.rgb)
        discovered: tuple[_RowGeometry, ...] = ()
        candidates: tuple[_Candidate, ...] = ()
        selected_candidates: tuple[_Candidate, ...] = ()
        selected_level = 0
        levels_scanned = 0
        for level, (minimum_y, maximum_y) in enumerate(self.config.roi_y_levels):
            levels_scanned = level + 1
            candidates = self._candidate_boxes(thumbnail, minimum_y=minimum_y, maximum_y=maximum_y)
            proposed = self._row_geometries(candidates, thumbnail.shape[:2], roi_level=level)
            if len(proposed) > len(discovered):
                discovered = proposed
                selected_candidates = candidates
                selected_level = level
            if len(discovered) >= 2:
                break
        if not discovered:
            return RowFirstLocatorResult(
                location=None,
                reason_code=RowFirstLocatorUnknownReason.UNKNOWN_ROWS,
                diagnostics={
                    "candidateCount": len(candidates),
                    "roiLevelsScanned": levels_scanned,
                },
            )

        assigned = self._assign_row_offsets(
            discovered,
            thumbnail_height=thumbnail.shape[0],
            prior=prior,
        )
        if assigned is None:
            return RowFirstLocatorResult(
                location=None,
                reason_code=(
                    RowFirstLocatorUnknownReason.POSITION_PRIOR_MISMATCH
                    if prior is not None
                    else RowFirstLocatorUnknownReason.AMBIGUOUS_ROWS
                ),
                diagnostics={
                    "candidateCount": len(selected_candidates),
                    "rowHypothesisCount": len(discovered),
                },
            )

        source_candidates = tuple(
            _scale_box(candidate.box, scale_x, scale_y, source.oriented_dimensions)
            for candidate in selected_candidates
        )
        rows: list[RowFirstRowHypothesis] = []
        for offset, geometry in assigned:
            rows.append(
                self._to_source_row(
                    offset,
                    geometry,
                    source=source,
                    scale_x=scale_x,
                    scale_y=scale_y,
                )
            )
        rows.sort(key=lambda value: value.row.row_index)
        return RowFirstLocatorResult(
            location=RowFirstLocation(
                rows=tuple(rows),
                candidate_boxes=source_candidates,
                locator_fingerprint=self.fingerprint,
            ),
            reason_code=None,
            diagnostics={
                "candidateCount": len(selected_candidates),
                "roiLevel": selected_level,
                "rowHypothesisCount": len(rows),
                "rows": [row.row.value for row in rows],
            },
        )

    def _thumbnail(
        self,
        rgb: NDArray[np.uint8],
    ) -> tuple[NDArray[np.uint8], float, float]:
        height, width = rgb.shape[:2]
        maximum = max(height, width)
        if maximum <= self.config.thumbnail_max_edge:
            return rgb, 1.0, 1.0
        scale = self.config.thumbnail_max_edge / maximum
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
        minimum_y: float,
        maximum_y: float,
    ) -> tuple[_Candidate, ...]:
        height, width = rgb.shape[:2]
        hsv = np.asarray(cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV), dtype=np.uint8)
        mask = cv2.inRange(
            hsv,
            np.array((0, self.config.minimum_saturation, self.config.minimum_brightness)),
            np.array((179, self.config.maximum_saturation, self.config.maximum_brightness)),
        )
        roi: NDArray[np.uint8] = np.zeros(mask.shape, dtype=np.uint8)
        left = int(round(width * self.config.minimum_x_ratio))
        right = int(round(width * self.config.maximum_x_ratio))
        top = int(round(height * minimum_y))
        bottom = int(round(height * maximum_y))
        roi[top:bottom, left:right] = mask[top:bottom, left:right]
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (
                max(1, int(round(width * self.config.horizontal_close_ratio)) | 1),
                max(1, int(round(height * self.config.vertical_close_ratio)) | 1),
            ),
        )
        closed = cv2.morphologyEx(roi, cv2.MORPH_CLOSE, kernel)
        count, _, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
        minimum_area = max(4, int(round(width * height * self.config.minimum_component_area_ratio)))
        fragments: list[_Candidate] = []
        for index in range(1, count):
            x, y, box_width, box_height, area = (int(value) for value in stats[index])
            if not (
                height * self.config.minimum_component_height_ratio
                <= box_height
                <= height * self.config.maximum_component_height_ratio
                and width * self.config.minimum_component_width_ratio
                <= box_width
                <= width * self.config.maximum_component_width_ratio
                and area >= minimum_area
            ):
                continue
            box = BoundingBox(x, y, x + box_width, y + box_height)
            fill_ratio = area / max(1, box.width * box.height)
            if fill_ratio < self.config.minimum_fill_ratio:
                continue
            fragments.extend(self._split_wide_component(box, roi, area=area))
        grouped = self._group_digit_fragments(fragments, width=width, height=height)
        return tuple(
            candidate
            for candidate in grouped
            if (
                candidate.box.width >= width * self.config.minimum_label_width_ratio
                and candidate.box.width <= width * self.config.maximum_label_width_ratio
                and candidate.box.width / max(1, candidate.box.height)
                >= self.config.minimum_label_aspect_ratio
            )
        )

    def _split_wide_component(
        self,
        box: BoundingBox,
        mask: NDArray[np.uint8],
        *,
        area: int,
    ) -> tuple[_Candidate, ...]:
        """Split a number/control merge at a low-ink vertical valley.

        Returning both halves is intentional: triplet fitting later accepts the
        three similarly shaped numeric labels and rejects a narrow side control.
        A component without a defensible valley is kept intact and then rejected
        by the label-width gate rather than being guessed apart.
        """

        maximum_width = mask.shape[1] * self.config.maximum_label_width_ratio
        if box.width <= maximum_width:
            return (_Candidate(box, area, area / max(1, box.width * box.height)),)
        component = mask[box.top : box.bottom, box.left : box.right]
        projection = np.count_nonzero(component, axis=0)
        threshold = max(1, int(round(box.height * 0.08)))
        valleys = np.flatnonzero(projection <= threshold)
        best: tuple[float, int] | None = None
        for run in _contiguous_runs(valleys):
            if run[0] == 0 or run[1] == box.width:
                continue
            split = (run[0] + run[1]) // 2
            left_width = split
            right_width = box.width - split
            if min(left_width, right_width) < mask.shape[1] * self.config.minimum_label_width_ratio:
                continue
            balance = min(left_width, right_width) / max(left_width, right_width)
            candidate = (balance, split)
            if best is None or candidate > best:
                best = candidate
        if best is None:
            return (_Candidate(box, area, area / max(1, box.width * box.height)),)
        split = best[1]
        values: list[_Candidate] = []
        for left, right in ((0, split), (split, box.width)):
            child = BoundingBox(box.left + left, box.top, box.left + right, box.bottom)
            child_mask = component[:, left:right]
            child_area = int(np.count_nonzero(child_mask))
            if child_area:
                values.append(
                    _Candidate(
                        child,
                        child_area,
                        child_area / max(1, child.width * child.height),
                    )
                )
        return tuple(values) or (_Candidate(box, area, area / max(1, box.width * box.height)),)

    def _group_digit_fragments(
        self,
        candidates: Sequence[_Candidate],
        *,
        width: int,
        height: int,
    ) -> tuple[_Candidate, ...]:
        pending = sorted(candidates, key=lambda value: (value.box.center[1], value.box.left))
        groups: list[list[_Candidate]] = []
        for candidate in pending:
            selected: list[_Candidate] | None = None
            for group in groups:
                union = _union_boxes(item.box for item in group)
                gap = max(0, candidate.box.left - union.right, union.left - candidate.box.right)
                baseline_delta = abs(candidate.box.bottom - union.bottom)
                height_ratio = max(candidate.box.height, union.height) / min(
                    candidate.box.height, union.height
                )
                if (
                    gap <= width * self.config.digit_group_gap_ratio
                    and baseline_delta <= height * self.config.digit_group_baseline_ratio
                    and height_ratio <= 1.8
                ):
                    selected = group
                    break
            if selected is None:
                groups.append([candidate])
            else:
                selected.append(candidate)
        result: list[_Candidate] = []
        for group in groups:
            box = _union_boxes(item.box for item in group)
            total_area = sum(item.area for item in group)
            result.append(_Candidate(box, total_area, total_area / max(1, box.width * box.height)))
        return tuple(result)

    def _row_geometries(
        self,
        candidates: Sequence[_Candidate],
        shape: tuple[int, int],
        *,
        roi_level: int,
    ) -> tuple[_RowGeometry, ...]:
        height, width = shape
        if len(candidates) < 3:
            return ()
        tolerance = max(
            height * self.config.row_cluster_tolerance_ratio,
            median(candidate.box.height for candidate in candidates) * 1.8,
        )
        clusters: list[list[_Candidate]] = []
        for candidate in sorted(
            candidates,
            key=lambda value: (value.box.center[1], value.box.left),
        ):
            if (
                not clusters
                or abs(candidate.box.center[1] - _cluster_center_y(clusters[-1])) > tolerance
            ):
                clusters.append([candidate])
            else:
                clusters[-1].append(candidate)
        result: list[_RowGeometry] = []
        for cluster in clusters:
            result.extend(
                self._best_triplets(cluster, width=width, height=height, roi_level=roi_level)
            )
        return _deduplicate_rows(result)

    def _best_triplets(
        self,
        cluster: Sequence[_Candidate],
        *,
        width: int,
        height: int,
        roi_level: int,
    ) -> tuple[_RowGeometry, ...]:
        if len(cluster) < 3:
            return ()
        values: list[_RowGeometry] = []
        for selected in combinations(sorted(cluster, key=lambda item: item.box.center[0]), 3):
            centers = tuple(item.box.center for item in selected)
            gaps = (centers[1][0] - centers[0][0], centers[2][0] - centers[1][0])
            if not all(
                width * self.config.minimum_column_gap_ratio
                <= gap
                <= width * self.config.maximum_column_gap_ratio
                for gap in gaps
            ):
                continue
            spacing_imbalance = max(gaps) / max(1e-6, min(gaps))
            if spacing_imbalance > self.config.maximum_row_spacing_imbalance:
                continue
            x_values = np.asarray([value[0] for value in centers], dtype=np.float64)
            y_values = np.asarray([value[1] for value in centers], dtype=np.float64)
            slope, intercept = np.polyfit(x_values, y_values, 1)
            residual = float(np.max(np.abs(y_values - (slope * x_values + intercept))))
            if residual > height * self.config.maximum_row_baseline_residual_ratio:
                continue
            widths = [item.box.width for item in selected]
            heights = [item.box.height for item in selected]
            shape_score = (min(widths) / max(widths) + min(heights) / max(heights)) / 2
            spacing_score = 1 / spacing_imbalance
            baseline_score = 1 - min(
                1,
                residual / max(1, height * self.config.maximum_row_baseline_residual_ratio),
            )
            values.append(
                _RowGeometry(
                    boxes=(selected[0], selected[1], selected[2]),
                    center_y=float(median(y_values)),
                    slope=float(slope),
                    score=float(shape_score * 0.45 + spacing_score * 0.35 + baseline_score * 0.20),
                    roi_level=roi_level,
                )
            )
        values.sort(
            key=lambda value: (
                value.score,
                -value.center_y,
                -value.boxes[0].box.center[0],
            ),
            reverse=True,
        )
        return tuple(values[:2])

    def _assign_row_offsets(
        self,
        rows: Sequence[_RowGeometry],
        *,
        thumbnail_height: int,
        prior: RowFirstPositionPrior | None,
    ) -> tuple[tuple[RangeRowOffset, _RowGeometry], ...] | None:
        anchors = prior.row_axes if prior is not None else self.config.row_anchor_y_ratios
        sorted_rows = tuple(sorted(rows, key=lambda value: value.center_y))
        # Each visible row is independently fitted.  Position only maps it to a
        # top/middle/bottom slot; numeric evidence still comes exclusively from
        # later OCR of the returned source crops.
        matches: list[tuple[float, tuple[tuple[RangeRowOffset, _RowGeometry], ...]]] = []
        for row_count in range(min(3, len(sorted_rows)), 0, -1):
            for selected_rows in combinations(sorted_rows, row_count):
                for offsets in combinations(tuple(RangeRowOffset), row_count):
                    residuals = [
                        abs(row.center_y / thumbnail_height - anchors[offset.row_index])
                        for offset, row in zip(offsets, selected_rows, strict=True)
                    ]
                    if any(
                        residual > self.config.row_anchor_tolerance_ratio for residual in residuals
                    ):
                        continue
                    # Prefer the maximum number of mutually compatible rows,
                    # then the closest position-only mapping. Geometry breaks a
                    # residual tie but does not contribute numeric evidence.
                    spacing_penalty = sum(
                        abs(
                            (later.center_y - earlier.center_y) / thumbnail_height
                            - (anchors[later_offset.row_index] - anchors[earlier_offset.row_index])
                        )
                        for (earlier_offset, earlier), (later_offset, later) in zip(
                            zip(offsets, selected_rows, strict=True),
                            zip(offsets[1:], selected_rows[1:], strict=True),
                            strict=False,
                        )
                    )
                    score = float(
                        (3 - row_count) * 2
                        + sum(residuals)
                        + spacing_penalty
                        - sum(row.score for row in selected_rows) * 0.001
                    )
                    matches.append((score, tuple(zip(offsets, selected_rows, strict=True))))
        if not matches:
            return None
        matches.sort(key=lambda value: (value[0], tuple(item[0].value for item in value[1])))
        return matches[0][1]

    def _to_source_row(
        self,
        offset: RangeRowOffset,
        geometry: _RowGeometry,
        *,
        source: CanonicalSourceImage,
        scale_x: float,
        scale_y: float,
    ) -> RowFirstRowHypothesis:
        dimensions = source.oriented_dimensions
        components = tuple(
            _scale_box(candidate.box, scale_x, scale_y, dimensions) for candidate in geometry.boxes
        )
        centers = tuple(component.center for component in components)
        spacing = float(median((centers[1][0] - centers[0][0], centers[2][0] - centers[1][0])))
        crop_width = int(
            round(
                _clamp(
                    spacing * self.config.crop_width_spacing_ratio,
                    dimensions.width * self.config.crop_minimum_width_ratio,
                    dimensions.width * self.config.crop_maximum_width_ratio,
                )
            )
        )
        crop_height = int(
            round(
                _clamp(
                    max(component.height for component in components)
                    * self.config.crop_height_component_ratio,
                    dimensions.height * self.config.crop_minimum_height_ratio,
                    dimensions.height * self.config.crop_maximum_height_ratio,
                )
            )
        )
        crops = tuple(
            self._crop(source.rgb, component, crop_width=crop_width, crop_height=crop_height)
            for component in components
        )
        return RowFirstRowHypothesis(
            row=offset,
            centers=(centers[0], centers[1], centers[2]),
            component_boxes=(components[0], components[1], components[2]),
            crops=(crops[0], crops[1], crops[2]),
            baseline_slope=geometry.slope * scale_y / scale_x,
            score=geometry.score,
            source_roi_level=geometry.roi_level,
        )

    def _crop(
        self,
        rgb: NDArray[np.uint8],
        component: BoundingBox,
        *,
        crop_width: int,
        crop_height: int,
    ) -> RowFirstLabelCrop:
        dimensions = ImageDimensions(width=rgb.shape[1], height=rgb.shape[0])
        requested_left = int(round(component.center[0] - crop_width / 2))
        requested_top = int(round(component.center[1] - crop_height / 2))
        box = _centered_box(
            component.center,
            width=crop_width,
            height=crop_height,
            dimensions=dimensions,
        )
        crop = rgb[box.top : box.bottom, box.left : box.right].copy()
        margin_x = min(component.left - box.left, box.right - component.right)
        margin_y = min(component.top - box.top, box.bottom - component.bottom)
        complete = (
            requested_left >= 0
            and requested_top >= 0
            and requested_left + crop_width <= dimensions.width
            and requested_top + crop_height <= dimensions.height
            and margin_x >= box.width * self.config.crop_margin_ratio
            and margin_y >= box.height * self.config.crop_margin_ratio
        )
        quality = _quality_scores(crop)
        return RowFirstLabelCrop(
            box=box,
            component_box=component,
            rgb=crop,
            complete=complete,
            quality=quality,
            readable=_is_readable(quality, self.readability),
        )


def _contiguous_runs(values: NDArray[np.int64]) -> tuple[tuple[int, int], ...]:
    if not len(values):
        return ()
    runs: list[tuple[int, int]] = []
    start = int(values[0])
    previous = start
    for raw in values[1:]:
        value = int(raw)
        if value != previous + 1:
            runs.append((start, previous + 1))
            start = value
        previous = value
    runs.append((start, previous + 1))
    return tuple(runs)


def _cluster_center_y(values: Sequence[_Candidate]) -> float:
    return float(median(item.box.center[1] for item in values))


def _deduplicate_rows(values: Sequence[_RowGeometry]) -> tuple[_RowGeometry, ...]:
    result: list[_RowGeometry] = []
    for value in sorted(values, key=lambda item: (-item.score, item.center_y)):
        identity = tuple(item.box for item in value.boxes)
        if any(tuple(item.box for item in existing.boxes) == identity for existing in result):
            continue
        if any(abs(existing.center_y - value.center_y) < 2 for existing in result):
            continue
        result.append(value)
    return tuple(sorted(result, key=lambda item: item.center_y))


def _union_boxes(boxes: Iterable[BoundingBox]) -> BoundingBox:
    values = tuple(boxes)
    if not values:
        raise ValueError("Cannot union an empty box collection.")
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
    left = min(max(0, int(np.floor(box.left * scale_x))), dimensions.width - 1)
    top = min(max(0, int(np.floor(box.top * scale_y))), dimensions.height - 1)
    right = min(max(left + 1, int(np.ceil(box.right * scale_x))), dimensions.width)
    bottom = min(max(top + 1, int(np.ceil(box.bottom * scale_y))), dimensions.height)
    return BoundingBox(left, top, right, bottom)


def _centered_box(
    center: tuple[float, float],
    *,
    width: int,
    height: int,
    dimensions: ImageDimensions,
) -> BoundingBox:
    resolved_width = min(max(1, width), dimensions.width)
    resolved_height = min(max(1, height), dimensions.height)
    left = min(
        max(0, int(round(center[0] - resolved_width / 2))),
        dimensions.width - resolved_width,
    )
    top = min(
        max(0, int(round(center[1] - resolved_height / 2))),
        dimensions.height - resolved_height,
    )
    return BoundingBox(left, top, left + resolved_width, top + resolved_height)


def _quality_scores(rgb: NDArray[np.uint8]) -> LocalQualityScores:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    x_gradient = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    y_gradient = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    x_energy = float(np.mean(np.abs(x_gradient)))
    y_energy = float(np.mean(np.abs(y_gradient)))
    low, high = np.percentile(gray, (10, 98))
    edges = cv2.Canny(gray, 50, 150)
    return LocalQualityScores(
        tenengrad=float(np.mean(np.sqrt(x_gradient * x_gradient + y_gradient * y_gradient))),
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
    "ROW_FIRST_LOCATOR_CONFIG_VERSION",
    "ROW_FIRST_LOCATOR_COORDINATE_SPACE",
    "ROW_FIRST_LOCATOR_VERSION",
    "RowFirstLabelCrop",
    "RowFirstLocation",
    "RowFirstLocatorConfig",
    "RowFirstLocatorResult",
    "RowFirstLocatorUnknownReason",
    "RowFirstPositionPrior",
    "RowFirstRowHypothesis",
    "RowFirstTripleLocator",
]
