"""Deterministic confidence and hard gates for structured board geometry.

Geometry confidence is deliberately independent from the symbol classifier.
The module contains no OpenCV calls so the acceptance policy can be tested and
versioned separately from the line detector.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

STRUCTURED_GEOMETRY_CONFIDENCE_VERSION: Final = "structured-geometry-confidence-v1"


class BoardGeometryDisposition(StrEnum):
    AUTOMATIC = "automatic"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"
    NEEDS_MANUAL_CORRECTION = "needs_manual_correction"


class BoardGeometryReasonCode(StrEnum):
    GLOBAL_INITIALIZATION_UNAVAILABLE = "global_initialization_unavailable"
    LOCAL_ROI_UNUSABLE = "local_roi_unusable"
    TOPOLOGY_UNSUPPORTED = "topology_unsupported"
    LOCAL_HOMOGRAPHY_UNAVAILABLE = "local_homography_unavailable"
    OUTER_BOUNDARY_EVIDENCE_INCOMPLETE = "outer_boundary_evidence_incomplete"
    VERTICAL_LINE_COVERAGE_INSUFFICIENT = "vertical_line_coverage_insufficient"
    HORIZONTAL_LINE_COVERAGE_INSUFFICIENT = "horizontal_line_coverage_insufficient"
    INTERSECTION_COVERAGE_INSUFFICIENT = "intersection_coverage_insufficient"
    LOCAL_REPROJECTION_ERROR_EXCEEDED = "local_reprojection_error_exceeded"
    SOURCE_SUPPORT_INCOMPLETE = "source_support_incomplete"
    INITIALIZATION_ALIGNMENT_FAILED = "initialization_alignment_failed"
    SLOT_ORDER_INVALID = "slot_order_invalid"
    BOARD_OVERLAP_DETECTED = "board_overlap_detected"
    LINE_SPACING_IRREGULAR = "line_spacing_irregular"
    BORDER_EVIDENCE_WEAK = "border_evidence_weak"
    GEOMETRY_CONFIDENCE_REVIEW = "geometry_confidence_review"
    GEOMETRY_CONFIDENCE_TOO_LOW = "geometry_confidence_too_low"


@dataclass(frozen=True, slots=True)
class StructuredGeometryValidationThresholds:
    minimum_vertical_lines: int = 5
    minimum_horizontal_lines: int = 3
    minimum_supported_intersections: int = 18
    maximum_half_scale_p95_reprojection_error: float = 2.5
    automatic_confidence: float = 0.85
    review_confidence: float = 0.65
    minimum_spacing_regularity_for_automatic: float = 0.72
    minimum_border_evidence_for_automatic: float = 0.62
    maximum_overlap_fraction: float = 0.01

    def __post_init__(self) -> None:
        fractions = (
            self.automatic_confidence,
            self.review_confidence,
            self.minimum_spacing_regularity_for_automatic,
            self.minimum_border_evidence_for_automatic,
            self.maximum_overlap_fraction,
        )
        if (
            self.minimum_vertical_lines < 1
            or self.minimum_horizontal_lines < 1
            or self.minimum_supported_intersections < 4
            or not math.isfinite(self.maximum_half_scale_p95_reprojection_error)
            or self.maximum_half_scale_p95_reprojection_error <= 0
            or any(not math.isfinite(value) or not 0 <= value <= 1 for value in fractions)
            or self.review_confidence >= self.automatic_confidence
        ):
            raise ValueError("Structured geometry validation thresholds are invalid.")

    def to_payload(self) -> dict[str, object]:
        return {
            "automaticConfidence": self.automatic_confidence,
            "confidenceVersion": STRUCTURED_GEOMETRY_CONFIDENCE_VERSION,
            "maximumHalfScaleP95ReprojectionError": (
                self.maximum_half_scale_p95_reprojection_error
            ),
            "maximumOverlapFraction": self.maximum_overlap_fraction,
            "minimumBorderEvidenceForAutomatic": self.minimum_border_evidence_for_automatic,
            "minimumHorizontalLines": self.minimum_horizontal_lines,
            "minimumSpacingRegularityForAutomatic": (self.minimum_spacing_regularity_for_automatic),
            "minimumSupportedIntersections": self.minimum_supported_intersections,
            "minimumVerticalLines": self.minimum_vertical_lines,
            "reviewConfidence": self.review_confidence,
        }


DEFAULT_STRUCTURED_GEOMETRY_VALIDATION_THRESHOLDS = StructuredGeometryValidationThresholds()


@dataclass(frozen=True, slots=True)
class GeometryConfidenceComponents:
    global_registration_score: float
    line_coverage_score: float
    intersection_coverage_score: float
    spacing_regularity_score: float
    reprojection_score: float
    border_evidence_score: float
    slot_order_score: float
    source_support_score: float

    def __post_init__(self) -> None:
        values = (
            self.global_registration_score,
            self.line_coverage_score,
            self.intersection_coverage_score,
            self.spacing_regularity_score,
            self.reprojection_score,
            self.border_evidence_score,
            self.slot_order_score,
            self.source_support_score,
        )
        if any(not math.isfinite(value) or not 0 <= value <= 1 for value in values):
            raise ValueError("Geometry confidence components must be finite values from 0 to 1.")

    @property
    def total(self) -> float:
        ordering_and_support = (self.slot_order_score + self.source_support_score) / 2.0
        return round(
            0.20 * self.global_registration_score
            + 0.25 * self.line_coverage_score
            + 0.15 * self.intersection_coverage_score
            + 0.15 * self.reprojection_score
            + 0.10 * self.spacing_regularity_score
            + 0.10 * self.border_evidence_score
            + 0.05 * ordering_and_support,
            8,
        )

    def to_payload(self) -> dict[str, float]:
        return {
            "borderEvidenceScore": round(self.border_evidence_score, 8),
            "geometryConfidence": self.total,
            "globalRegistrationScore": round(self.global_registration_score, 8),
            "intersectionCoverageScore": round(self.intersection_coverage_score, 8),
            "lineCoverageScore": round(self.line_coverage_score, 8),
            "reprojectionScore": round(self.reprojection_score, 8),
            "slotOrderScore": round(self.slot_order_score, 8),
            "sourceSupportScore": round(self.source_support_score, 8),
            "spacingRegularityScore": round(self.spacing_regularity_score, 8),
        }


@dataclass(frozen=True, slots=True)
class BoardGeometryEvidence:
    observed_vertical_line_indexes: tuple[int, ...]
    observed_horizontal_line_indexes: tuple[int, ...]
    inferred_vertical_line_indexes: tuple[int, ...]
    inferred_horizontal_line_indexes: tuple[int, ...]
    external_boundaries_supported: int
    supported_intersection_count: int
    inlier_intersection_count: int
    half_scale_p95_reprojection_error: float | None
    homography_available: bool
    padded_cell_source_support_complete: bool
    initialization_alignment_valid: bool
    slot_order_valid: bool = True
    overlap_valid: bool = True

    def __post_init__(self) -> None:
        if (
            self.external_boundaries_supported not in range(5)
            or self.supported_intersection_count not in range(25)
            or self.inlier_intersection_count not in range(25)
            or self.inlier_intersection_count > self.supported_intersection_count
            or (
                self.half_scale_p95_reprojection_error is not None
                and (
                    not math.isfinite(self.half_scale_p95_reprojection_error)
                    or self.half_scale_p95_reprojection_error < 0
                )
            )
        ):
            raise ValueError("Board geometry evidence is invalid.")
        for values, maximum in (
            (self.observed_vertical_line_indexes, 6),
            (self.inferred_vertical_line_indexes, 6),
            (self.observed_horizontal_line_indexes, 4),
            (self.inferred_horizontal_line_indexes, 4),
        ):
            if values != tuple(sorted(set(values))) or any(
                value < 0 or value >= maximum for value in values
            ):
                raise ValueError("Line evidence indexes must be unique and ordered.")

    @classmethod
    def empty(cls) -> BoardGeometryEvidence:
        return cls(
            observed_vertical_line_indexes=(),
            observed_horizontal_line_indexes=(),
            inferred_vertical_line_indexes=(),
            inferred_horizontal_line_indexes=(),
            external_boundaries_supported=0,
            supported_intersection_count=0,
            inlier_intersection_count=0,
            half_scale_p95_reprojection_error=None,
            homography_available=False,
            padded_cell_source_support_complete=False,
            initialization_alignment_valid=False,
            slot_order_valid=False,
            overlap_valid=False,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "externalBoundariesSupported": self.external_boundaries_supported,
            "halfScaleP95ReprojectionError": (
                None
                if self.half_scale_p95_reprojection_error is None
                else round(self.half_scale_p95_reprojection_error, 8)
            ),
            "homographyAvailable": self.homography_available,
            "inferredHorizontalLineIndexes": list(self.inferred_horizontal_line_indexes),
            "inferredVerticalLineIndexes": list(self.inferred_vertical_line_indexes),
            "initializationAlignmentValid": self.initialization_alignment_valid,
            "inlierIntersectionCount": self.inlier_intersection_count,
            "observedHorizontalLineIndexes": list(self.observed_horizontal_line_indexes),
            "observedVerticalLineIndexes": list(self.observed_vertical_line_indexes),
            "overlapValid": self.overlap_valid,
            "paddedCellSourceSupportComplete": self.padded_cell_source_support_complete,
            "slotOrderValid": self.slot_order_valid,
            "supportedIntersectionCount": self.supported_intersection_count,
        }


@dataclass(frozen=True, slots=True)
class GeometryConfidenceDecision:
    disposition: BoardGeometryDisposition
    confidence: float
    reason_codes: tuple[BoardGeometryReasonCode, ...]


def evaluate_geometry_confidence(
    *,
    evidence: BoardGeometryEvidence,
    components: GeometryConfidenceComponents,
    thresholds: StructuredGeometryValidationThresholds = (
        DEFAULT_STRUCTURED_GEOMETRY_VALIDATION_THRESHOLDS
    ),
) -> GeometryConfidenceDecision:
    """Apply hard gates first and confidence bands only after they pass."""

    hard_failures: list[BoardGeometryReasonCode] = []
    if not evidence.homography_available:
        hard_failures.append(BoardGeometryReasonCode.LOCAL_HOMOGRAPHY_UNAVAILABLE)
    if evidence.external_boundaries_supported < 4:
        hard_failures.append(BoardGeometryReasonCode.OUTER_BOUNDARY_EVIDENCE_INCOMPLETE)
    if len(evidence.observed_vertical_line_indexes) < thresholds.minimum_vertical_lines:
        hard_failures.append(BoardGeometryReasonCode.VERTICAL_LINE_COVERAGE_INSUFFICIENT)
    if len(evidence.observed_horizontal_line_indexes) < thresholds.minimum_horizontal_lines:
        hard_failures.append(BoardGeometryReasonCode.HORIZONTAL_LINE_COVERAGE_INSUFFICIENT)
    if (
        evidence.supported_intersection_count < thresholds.minimum_supported_intersections
        or evidence.inlier_intersection_count < thresholds.minimum_supported_intersections
    ):
        hard_failures.append(BoardGeometryReasonCode.INTERSECTION_COVERAGE_INSUFFICIENT)
    if (
        evidence.half_scale_p95_reprojection_error is None
        or evidence.half_scale_p95_reprojection_error
        > thresholds.maximum_half_scale_p95_reprojection_error
    ):
        hard_failures.append(BoardGeometryReasonCode.LOCAL_REPROJECTION_ERROR_EXCEEDED)
    if not evidence.padded_cell_source_support_complete:
        hard_failures.append(BoardGeometryReasonCode.SOURCE_SUPPORT_INCOMPLETE)
    if not evidence.initialization_alignment_valid:
        hard_failures.append(BoardGeometryReasonCode.INITIALIZATION_ALIGNMENT_FAILED)
    if not evidence.slot_order_valid:
        hard_failures.append(BoardGeometryReasonCode.SLOT_ORDER_INVALID)
    if not evidence.overlap_valid:
        hard_failures.append(BoardGeometryReasonCode.BOARD_OVERLAP_DETECTED)
    if hard_failures:
        return GeometryConfidenceDecision(
            disposition=BoardGeometryDisposition.NEEDS_MANUAL_CORRECTION,
            confidence=components.total,
            reason_codes=tuple(hard_failures),
        )

    soft_reasons: list[BoardGeometryReasonCode] = []
    if components.spacing_regularity_score < thresholds.minimum_spacing_regularity_for_automatic:
        soft_reasons.append(BoardGeometryReasonCode.LINE_SPACING_IRREGULAR)
    if components.border_evidence_score < thresholds.minimum_border_evidence_for_automatic:
        soft_reasons.append(BoardGeometryReasonCode.BORDER_EVIDENCE_WEAK)
    if components.total < thresholds.review_confidence:
        return GeometryConfidenceDecision(
            disposition=BoardGeometryDisposition.NEEDS_MANUAL_CORRECTION,
            confidence=components.total,
            reason_codes=(*soft_reasons, BoardGeometryReasonCode.GEOMETRY_CONFIDENCE_TOO_LOW),
        )
    if components.total < thresholds.automatic_confidence or soft_reasons:
        return GeometryConfidenceDecision(
            disposition=BoardGeometryDisposition.NEEDS_MANUAL_REVIEW,
            confidence=components.total,
            reason_codes=(*soft_reasons, BoardGeometryReasonCode.GEOMETRY_CONFIDENCE_REVIEW),
        )
    return GeometryConfidenceDecision(
        disposition=BoardGeometryDisposition.AUTOMATIC,
        confidence=components.total,
        reason_codes=(),
    )


__all__ = [
    "DEFAULT_STRUCTURED_GEOMETRY_VALIDATION_THRESHOLDS",
    "STRUCTURED_GEOMETRY_CONFIDENCE_VERSION",
    "BoardGeometryDisposition",
    "BoardGeometryEvidence",
    "BoardGeometryReasonCode",
    "GeometryConfidenceComponents",
    "GeometryConfidenceDecision",
    "StructuredGeometryValidationThresholds",
    "evaluate_geometry_confidence",
]
