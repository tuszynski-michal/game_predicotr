"""Experimental, measurement-only configuration for Structured Geometry v2.

The production v1 thresholds remain intentionally untouched.  This module is
an additive candidate contract for read-only feasibility work: it makes scale,
normalised tolerances and evidence combination explicit and checksummable.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final, cast
from uuid import UUID

STRUCTURED_GEOMETRY_CONFIG_V2_VERSION: Final = (
    "structured-opencv-geometry-config-v2-multi-evidence-experimental-v1"
)


class GeometryConfigV2Error(ValueError):
    """Stable error raised for an invalid experimental configuration."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class GeometryConfigMaturity(StrEnum):
    EXPERIMENTAL_MEASUREMENT_ONLY = "experimental_measurement_only"


class GeometryCandidateDisposition(StrEnum):
    AUTOMATIC_CANDIDATE = "automatic_candidate"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"
    NEEDS_MANUAL_CORRECTION = "needs_manual_correction"


class GeometryEvidenceReasonV2(StrEnum):
    HOMOGRAPHY_UNAVAILABLE = "homography_unavailable"
    SOURCE_SUPPORT_INCOMPLETE = "source_support_incomplete"
    INITIALIZATION_ALIGNMENT_FAILED = "initialization_alignment_failed"
    SLOT_ORDER_INVALID = "slot_order_invalid"
    BOARD_OVERLAP_DETECTED = "board_overlap_detected"
    REPROJECTION_ERROR_EXCEEDED = "normalized_reprojection_error_exceeded"
    INDEPENDENT_EVIDENCE_INSUFFICIENT = "independent_evidence_insufficient"
    CONFIDENCE_REVIEW = "geometry_confidence_review"
    CONFIDENCE_TOO_LOW = "geometry_confidence_too_low"


@dataclass(frozen=True, slots=True)
class AdaptiveAnalysisPolicyV2:
    """Choose a bounded scale while preserving useful local ROI resolution."""

    target_source_long_edge_px: int = 1600
    minimum_local_roi_short_edge_px: int = 240
    minimum_analysis_scale: float = 0.25
    maximum_analysis_scale: float = 1.0

    def __post_init__(self) -> None:
        if (
            self.target_source_long_edge_px < 256
            or self.minimum_local_roi_short_edge_px < 64
            or not math.isfinite(self.minimum_analysis_scale)
            or not math.isfinite(self.maximum_analysis_scale)
            or not 0 < self.minimum_analysis_scale <= self.maximum_analysis_scale <= 1
        ):
            raise GeometryConfigV2Error(
                "IMAGE_STRUCTURED_GEOMETRY_CONFIG_V2_INVALID",
                "Adaptive analysis sizing is invalid.",
            )

    def resolve_scale(
        self,
        *,
        source_width: int,
        source_height: int,
        smallest_roi_short_edge_px: float,
    ) -> float:
        """Return a deterministic no-upscale factor for this source and ROI set."""

        if (
            source_width <= 0
            or source_height <= 0
            or not math.isfinite(smallest_roi_short_edge_px)
            or smallest_roi_short_edge_px <= 0
        ):
            raise GeometryConfigV2Error(
                "IMAGE_STRUCTURED_GEOMETRY_ANALYSIS_INPUT_INVALID",
                "Source dimensions and local ROI size must be positive.",
            )
        source_cap = self.target_source_long_edge_px / max(source_width, source_height)
        roi_floor = self.minimum_local_roi_short_edge_px / smallest_roi_short_edge_px
        scale = max(self.minimum_analysis_scale, min(1.0, source_cap), min(1.0, roi_floor))
        return round(min(self.maximum_analysis_scale, scale), 8)

    def to_payload(self) -> dict[str, object]:
        return {
            "maximumAnalysisScale": self.maximum_analysis_scale,
            "minimumAnalysisScale": self.minimum_analysis_scale,
            "minimumLocalRoiShortEdgePx": self.minimum_local_roi_short_edge_px,
            "targetSourceLongEdgePx": self.target_source_long_edge_px,
        }


@dataclass(frozen=True, slots=True)
class GeometryEvidenceWeightsV2:
    outer_frame: float = 0.20
    known_layout: float = 0.25
    lsd_lines: float = 0.10
    hough_lines: float = 0.05
    gradient_profiles: float = 0.10
    grid_regularity: float = 0.20
    symbol_centers: float = 0.05
    reprojection: float = 0.05

    def __post_init__(self) -> None:
        values = self.values()
        if any(not math.isfinite(value) or value < 0 for value in values) or not math.isclose(
            sum(values), 1.0, abs_tol=1e-9
        ):
            raise GeometryConfigV2Error(
                "IMAGE_STRUCTURED_GEOMETRY_CONFIG_V2_INVALID",
                "Evidence weights must be non-negative and sum to one.",
            )

    def values(self) -> tuple[float, ...]:
        return (
            self.outer_frame,
            self.known_layout,
            self.lsd_lines,
            self.hough_lines,
            self.gradient_profiles,
            self.grid_regularity,
            self.symbol_centers,
            self.reprojection,
        )

    def to_payload(self) -> dict[str, float]:
        return {
            "gradientProfiles": self.gradient_profiles,
            "gridRegularity": self.grid_regularity,
            "houghLines": self.hough_lines,
            "knownLayout": self.known_layout,
            "lsdLines": self.lsd_lines,
            "outerFrame": self.outer_frame,
            "reprojection": self.reprojection,
            "symbolCenters": self.symbol_centers,
        }


@dataclass(frozen=True, slots=True)
class GeometryEvidenceThresholdsV2:
    strong_outer_frame: float = 0.70
    strong_known_layout: float = 0.75
    strong_grid_regularity: float = 0.72
    strong_internal_structure: float = 0.68
    maximum_reprojection_cell_diagonal_fraction: float = 0.04
    automatic_confidence: float = 0.80
    review_confidence: float = 0.58

    def __post_init__(self) -> None:
        values = (
            self.strong_outer_frame,
            self.strong_known_layout,
            self.strong_grid_regularity,
            self.strong_internal_structure,
            self.maximum_reprojection_cell_diagonal_fraction,
            self.automatic_confidence,
            self.review_confidence,
        )
        if (
            any(not math.isfinite(value) or not 0 < value <= 1 for value in values)
            or self.review_confidence >= self.automatic_confidence
        ):
            raise GeometryConfigV2Error(
                "IMAGE_STRUCTURED_GEOMETRY_CONFIG_V2_INVALID",
                "Multi-evidence thresholds are invalid.",
            )

    def to_payload(self) -> dict[str, float]:
        return {
            "automaticConfidence": self.automatic_confidence,
            "maximumReprojectionCellDiagonalFraction": (
                self.maximum_reprojection_cell_diagonal_fraction
            ),
            "reviewConfidence": self.review_confidence,
            "strongGridRegularity": self.strong_grid_regularity,
            "strongInternalStructure": self.strong_internal_structure,
            "strongKnownLayout": self.strong_known_layout,
            "strongOuterFrame": self.strong_outer_frame,
        }


@dataclass(frozen=True, slots=True)
class GameGeometryEvidenceProfileV2:
    game_id: UUID
    thresholds: GeometryEvidenceThresholdsV2

    def to_payload(self) -> dict[str, object]:
        return {"gameId": str(self.game_id), "thresholds": self.thresholds.to_payload()}


@dataclass(frozen=True, slots=True)
class StructuredGeometryConfigV2:
    """Pinned candidate configuration; it cannot authorize production rollout."""

    analysis: AdaptiveAnalysisPolicyV2 = field(default_factory=AdaptiveAnalysisPolicyV2)
    weights: GeometryEvidenceWeightsV2 = field(default_factory=GeometryEvidenceWeightsV2)
    thresholds: GeometryEvidenceThresholdsV2 = field(default_factory=GeometryEvidenceThresholdsV2)
    game_profiles: tuple[GameGeometryEvidenceProfileV2, ...] = ()
    maturity: GeometryConfigMaturity = GeometryConfigMaturity.EXPERIMENTAL_MEASUREMENT_ONLY
    activation_allowed: bool = False
    require_disjoint_tuning_and_evaluation: bool = True

    def __post_init__(self) -> None:
        ids = tuple(profile.game_id for profile in self.game_profiles)
        if ids != tuple(sorted(ids, key=str)) or len(ids) != len(set(ids)):
            raise GeometryConfigV2Error(
                "IMAGE_STRUCTURED_GEOMETRY_CONFIG_V2_INVALID",
                "Game profiles must be unique and sorted by game ID.",
            )
        if (
            self.maturity is not GeometryConfigMaturity.EXPERIMENTAL_MEASUREMENT_ONLY
            or self.activation_allowed
            or not self.require_disjoint_tuning_and_evaluation
        ):
            raise GeometryConfigV2Error(
                "IMAGE_STRUCTURED_GEOMETRY_CONFIG_V2_NOT_EXPERIMENTAL",
                "Config v2 must remain measurement-only until an independent gate passes.",
            )

    def thresholds_for(self, game_id: UUID | None) -> GeometryEvidenceThresholdsV2:
        if game_id is not None:
            for profile in self.game_profiles:
                if profile.game_id == game_id:
                    return profile.thresholds
        return self.thresholds

    def to_payload(self) -> dict[str, object]:
        return {
            "activationAllowed": self.activation_allowed,
            "adaptiveAnalysis": self.analysis.to_payload(),
            "configVersion": STRUCTURED_GEOMETRY_CONFIG_V2_VERSION,
            "evidencePolicy": {
                "lsdIsExclusiveGate": False,
                "thresholds": self.thresholds.to_payload(),
                "weights": self.weights.to_payload(),
            },
            "gameProfiles": [profile.to_payload() for profile in self.game_profiles],
            "maturity": self.maturity.value,
            "requireDisjointTuningAndEvaluation": (self.require_disjoint_tuning_and_evaluation),
            "tolerances": {"reprojectionUnit": "cell_diagonal_fraction"},
        }

    @classmethod
    def from_payload(cls, value: object) -> StructuredGeometryConfigV2:
        """Recreate one exact pinned config and reject unsupported fields."""

        payload = _mapping(value, "structuredGeometryConfigV2")
        if (
            set(payload)
            != {
                "activationAllowed",
                "adaptiveAnalysis",
                "configVersion",
                "evidencePolicy",
                "gameProfiles",
                "maturity",
                "requireDisjointTuningAndEvaluation",
                "tolerances",
            }
            or payload.get("configVersion") != STRUCTURED_GEOMETRY_CONFIG_V2_VERSION
        ):
            raise GeometryConfigV2Error(
                "IMAGE_STRUCTURED_GEOMETRY_CONFIG_V2_INVALID",
                "The pinned Structured Geometry v2 schema is unsupported.",
            )
        analysis = _mapping(payload.get("adaptiveAnalysis"), "adaptiveAnalysis")
        evidence_policy = _mapping(payload.get("evidencePolicy"), "evidencePolicy")
        tolerances = _mapping(payload.get("tolerances"), "tolerances")
        if (
            set(analysis)
            != {
                "maximumAnalysisScale",
                "minimumAnalysisScale",
                "minimumLocalRoiShortEdgePx",
                "targetSourceLongEdgePx",
            }
            or set(evidence_policy) != {"lsdIsExclusiveGate", "thresholds", "weights"}
            or evidence_policy.get("lsdIsExclusiveGate") is not False
            or dict(tolerances) != {"reprojectionUnit": "cell_diagonal_fraction"}
        ):
            raise GeometryConfigV2Error(
                "IMAGE_STRUCTURED_GEOMETRY_CONFIG_V2_INVALID",
                "The pinned Structured Geometry v2 policy is invalid.",
            )
        thresholds = _thresholds_from_payload(evidence_policy.get("thresholds"))
        profiles = tuple(
            _game_profile_from_payload(raw)
            for raw in _sequence(payload.get("gameProfiles"), "gameProfiles")
        )
        try:
            maturity = GeometryConfigMaturity(str(payload.get("maturity")))
            return cls(
                analysis=AdaptiveAnalysisPolicyV2(
                    target_source_long_edge_px=_integer(
                        analysis.get("targetSourceLongEdgePx"),
                        "adaptiveAnalysis.targetSourceLongEdgePx",
                    ),
                    minimum_local_roi_short_edge_px=_integer(
                        analysis.get("minimumLocalRoiShortEdgePx"),
                        "adaptiveAnalysis.minimumLocalRoiShortEdgePx",
                    ),
                    minimum_analysis_scale=_number(
                        analysis.get("minimumAnalysisScale"),
                        "adaptiveAnalysis.minimumAnalysisScale",
                    ),
                    maximum_analysis_scale=_number(
                        analysis.get("maximumAnalysisScale"),
                        "adaptiveAnalysis.maximumAnalysisScale",
                    ),
                ),
                weights=_weights_from_payload(evidence_policy.get("weights")),
                thresholds=thresholds,
                game_profiles=profiles,
                maturity=maturity,
                activation_allowed=_boolean(payload.get("activationAllowed"), "activationAllowed"),
                require_disjoint_tuning_and_evaluation=_boolean(
                    payload.get("requireDisjointTuningAndEvaluation"),
                    "requireDisjointTuningAndEvaluation",
                ),
            )
        except (TypeError, ValueError) as error:
            if isinstance(error, GeometryConfigV2Error):
                raise
            raise GeometryConfigV2Error(
                "IMAGE_STRUCTURED_GEOMETRY_CONFIG_V2_INVALID",
                "The pinned Structured Geometry v2 values are invalid.",
            ) from error

    @property
    def checksum_sha256(self) -> str:
        return hashlib.sha256(_canonical_json_bytes(self.to_payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class StructuredGeometryEvidenceV2:
    homography_available: bool
    padded_cell_source_support_complete: bool
    initialization_alignment_valid: bool
    slot_order_valid: bool
    overlap_valid: bool
    outer_frame_score: float
    known_layout_score: float
    lsd_grid_score: float
    hough_grid_score: float
    vertical_gradient_profile_score: float
    horizontal_gradient_profile_score: float
    grid_regularity_score: float
    symbol_center_support_score: float
    reprojection_cell_diagonal_fraction: float | None

    def __post_init__(self) -> None:
        scores = (
            self.outer_frame_score,
            self.known_layout_score,
            self.lsd_grid_score,
            self.hough_grid_score,
            self.vertical_gradient_profile_score,
            self.horizontal_gradient_profile_score,
            self.grid_regularity_score,
            self.symbol_center_support_score,
        )
        if any(not math.isfinite(value) or not 0 <= value <= 1 for value in scores) or (
            self.reprojection_cell_diagonal_fraction is not None
            and (
                not math.isfinite(self.reprojection_cell_diagonal_fraction)
                or self.reprojection_cell_diagonal_fraction < 0
            )
        ):
            raise GeometryConfigV2Error(
                "IMAGE_STRUCTURED_GEOMETRY_EVIDENCE_V2_INVALID",
                "Structured geometry evidence must be finite and normalized.",
            )

    @property
    def gradient_profile_score(self) -> float:
        return (self.vertical_gradient_profile_score + self.horizontal_gradient_profile_score) / 2

    def to_payload(self) -> dict[str, object]:
        return {
            "gradientProfileScore": round(self.gradient_profile_score, 8),
            "gridRegularityScore": round(self.grid_regularity_score, 8),
            "homographyAvailable": self.homography_available,
            "horizontalGradientProfileScore": round(self.horizontal_gradient_profile_score, 8),
            "houghGridScore": round(self.hough_grid_score, 8),
            "initializationAlignmentValid": self.initialization_alignment_valid,
            "knownLayoutScore": round(self.known_layout_score, 8),
            "lsdGridScore": round(self.lsd_grid_score, 8),
            "outerFrameScore": round(self.outer_frame_score, 8),
            "overlapValid": self.overlap_valid,
            "paddedCellSourceSupportComplete": self.padded_cell_source_support_complete,
            "reprojectionCellDiagonalFraction": (
                None
                if self.reprojection_cell_diagonal_fraction is None
                else round(self.reprojection_cell_diagonal_fraction, 8)
            ),
            "slotOrderValid": self.slot_order_valid,
            "symbolCenterSupportScore": round(self.symbol_center_support_score, 8),
            "verticalGradientProfileScore": round(self.vertical_gradient_profile_score, 8),
        }


@dataclass(frozen=True, slots=True)
class GeometryCandidateDecisionV2:
    disposition: GeometryCandidateDisposition
    confidence: float
    reason_codes: tuple[GeometryEvidenceReasonV2, ...]
    strong_evidence_families: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "confidence": round(self.confidence, 8),
            "disposition": self.disposition.value,
            "reasonCodes": [reason.value for reason in self.reason_codes],
            "strongEvidenceFamilies": list(self.strong_evidence_families),
        }


def evaluate_geometry_candidate_v2(
    evidence: StructuredGeometryEvidenceV2,
    *,
    config: StructuredGeometryConfigV2 | None = None,
    game_id: UUID | None = None,
) -> GeometryCandidateDecisionV2:
    """Evaluate a measurement-only candidate without changing production v1."""

    resolved_config = DEFAULT_STRUCTURED_GEOMETRY_CONFIG_V2 if config is None else config
    thresholds = resolved_config.thresholds_for(game_id)
    hard_failures: list[GeometryEvidenceReasonV2] = []
    if not evidence.homography_available:
        hard_failures.append(GeometryEvidenceReasonV2.HOMOGRAPHY_UNAVAILABLE)
    if not evidence.padded_cell_source_support_complete:
        hard_failures.append(GeometryEvidenceReasonV2.SOURCE_SUPPORT_INCOMPLETE)
    if not evidence.initialization_alignment_valid:
        hard_failures.append(GeometryEvidenceReasonV2.INITIALIZATION_ALIGNMENT_FAILED)
    if not evidence.slot_order_valid:
        hard_failures.append(GeometryEvidenceReasonV2.SLOT_ORDER_INVALID)
    if not evidence.overlap_valid:
        hard_failures.append(GeometryEvidenceReasonV2.BOARD_OVERLAP_DETECTED)
    reprojection = evidence.reprojection_cell_diagonal_fraction
    if (
        reprojection is None
        or reprojection > thresholds.maximum_reprojection_cell_diagonal_fraction
    ):
        hard_failures.append(GeometryEvidenceReasonV2.REPROJECTION_ERROR_EXCEEDED)

    confidence = _candidate_confidence(evidence, config=resolved_config, thresholds=thresholds)
    families = _strong_evidence_families(evidence, thresholds=thresholds)
    if hard_failures:
        return GeometryCandidateDecisionV2(
            GeometryCandidateDisposition.NEEDS_MANUAL_CORRECTION,
            confidence,
            tuple(hard_failures),
            families,
        )

    core_triangulation = all(
        value in families for value in ("outer_frame", "known_layout", "grid_regularity")
    )
    line_supported_triangulation = (
        "internal_structure" in families
        and sum(value in families for value in ("outer_frame", "known_layout", "grid_regularity"))
        >= 2
    )
    independent_evidence_valid = core_triangulation or line_supported_triangulation
    if not independent_evidence_valid:
        return GeometryCandidateDecisionV2(
            GeometryCandidateDisposition.NEEDS_MANUAL_CORRECTION,
            confidence,
            (GeometryEvidenceReasonV2.INDEPENDENT_EVIDENCE_INSUFFICIENT,),
            families,
        )
    if confidence < thresholds.review_confidence:
        return GeometryCandidateDecisionV2(
            GeometryCandidateDisposition.NEEDS_MANUAL_CORRECTION,
            confidence,
            (GeometryEvidenceReasonV2.CONFIDENCE_TOO_LOW,),
            families,
        )
    if confidence < thresholds.automatic_confidence:
        return GeometryCandidateDecisionV2(
            GeometryCandidateDisposition.NEEDS_MANUAL_REVIEW,
            confidence,
            (GeometryEvidenceReasonV2.CONFIDENCE_REVIEW,),
            families,
        )
    return GeometryCandidateDecisionV2(
        GeometryCandidateDisposition.AUTOMATIC_CANDIDATE,
        confidence,
        (),
        families,
    )


def _candidate_confidence(
    evidence: StructuredGeometryEvidenceV2,
    *,
    config: StructuredGeometryConfigV2,
    thresholds: GeometryEvidenceThresholdsV2,
) -> float:
    weights = config.weights
    reprojection = evidence.reprojection_cell_diagonal_fraction
    reprojection_score = (
        0.0
        if reprojection is None
        else max(0.0, 1.0 - reprojection / thresholds.maximum_reprojection_cell_diagonal_fraction)
    )
    total = (
        weights.outer_frame * evidence.outer_frame_score
        + weights.known_layout * evidence.known_layout_score
        + weights.lsd_lines * evidence.lsd_grid_score
        + weights.hough_lines * evidence.hough_grid_score
        + weights.gradient_profiles * evidence.gradient_profile_score
        + weights.grid_regularity * evidence.grid_regularity_score
        + weights.symbol_centers * evidence.symbol_center_support_score
        + weights.reprojection * reprojection_score
    )
    return round(min(1.0, max(0.0, total)), 8)


def _strong_evidence_families(
    evidence: StructuredGeometryEvidenceV2,
    *,
    thresholds: GeometryEvidenceThresholdsV2,
) -> tuple[str, ...]:
    families: list[str] = []
    if evidence.outer_frame_score >= thresholds.strong_outer_frame:
        families.append("outer_frame")
    if evidence.known_layout_score >= thresholds.strong_known_layout:
        families.append("known_layout")
    if evidence.grid_regularity_score >= thresholds.strong_grid_regularity:
        families.append("grid_regularity")
    internal_structure = max(
        evidence.lsd_grid_score,
        evidence.hough_grid_score,
        evidence.gradient_profile_score,
    )
    if internal_structure >= thresholds.strong_internal_structure:
        families.append("internal_structure")
    return tuple(families)


DEFAULT_STRUCTURED_GEOMETRY_CONFIG_V2 = StructuredGeometryConfigV2()


def _thresholds_from_payload(value: object) -> GeometryEvidenceThresholdsV2:
    payload = _mapping(value, "evidencePolicy.thresholds")
    if set(payload) != {
        "automaticConfidence",
        "maximumReprojectionCellDiagonalFraction",
        "reviewConfidence",
        "strongGridRegularity",
        "strongInternalStructure",
        "strongKnownLayout",
        "strongOuterFrame",
    }:
        raise GeometryConfigV2Error(
            "IMAGE_STRUCTURED_GEOMETRY_CONFIG_V2_INVALID",
            "The candidate evidence thresholds are invalid.",
        )
    return GeometryEvidenceThresholdsV2(
        strong_outer_frame=_number(payload.get("strongOuterFrame"), "strongOuterFrame"),
        strong_known_layout=_number(payload.get("strongKnownLayout"), "strongKnownLayout"),
        strong_grid_regularity=_number(payload.get("strongGridRegularity"), "strongGridRegularity"),
        strong_internal_structure=_number(
            payload.get("strongInternalStructure"), "strongInternalStructure"
        ),
        maximum_reprojection_cell_diagonal_fraction=_number(
            payload.get("maximumReprojectionCellDiagonalFraction"),
            "maximumReprojectionCellDiagonalFraction",
        ),
        automatic_confidence=_number(payload.get("automaticConfidence"), "automaticConfidence"),
        review_confidence=_number(payload.get("reviewConfidence"), "reviewConfidence"),
    )


def _weights_from_payload(value: object) -> GeometryEvidenceWeightsV2:
    payload = _mapping(value, "evidencePolicy.weights")
    expected = {
        "gradientProfiles",
        "gridRegularity",
        "houghLines",
        "knownLayout",
        "lsdLines",
        "outerFrame",
        "reprojection",
        "symbolCenters",
    }
    if set(payload) != expected:
        raise GeometryConfigV2Error(
            "IMAGE_STRUCTURED_GEOMETRY_CONFIG_V2_INVALID",
            "The candidate evidence weights are invalid.",
        )
    return GeometryEvidenceWeightsV2(
        outer_frame=_number(payload.get("outerFrame"), "outerFrame"),
        known_layout=_number(payload.get("knownLayout"), "knownLayout"),
        lsd_lines=_number(payload.get("lsdLines"), "lsdLines"),
        hough_lines=_number(payload.get("houghLines"), "houghLines"),
        gradient_profiles=_number(payload.get("gradientProfiles"), "gradientProfiles"),
        grid_regularity=_number(payload.get("gridRegularity"), "gridRegularity"),
        symbol_centers=_number(payload.get("symbolCenters"), "symbolCenters"),
        reprojection=_number(payload.get("reprojection"), "reprojection"),
    )


def _game_profile_from_payload(value: object) -> GameGeometryEvidenceProfileV2:
    payload = _mapping(value, "gameProfiles[]")
    if set(payload) != {"gameId", "thresholds"}:
        raise GeometryConfigV2Error(
            "IMAGE_STRUCTURED_GEOMETRY_CONFIG_V2_INVALID",
            "A candidate game profile is invalid.",
        )
    try:
        game_id = UUID(_text(payload.get("gameId"), "gameProfiles[].gameId"))
    except ValueError as error:
        raise GeometryConfigV2Error(
            "IMAGE_STRUCTURED_GEOMETRY_CONFIG_V2_INVALID",
            "A candidate game profile ID is invalid.",
        ) from error
    return GameGeometryEvidenceProfileV2(
        game_id=game_id,
        thresholds=_thresholds_from_payload(payload.get("thresholds")),
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise GeometryConfigV2Error(
            "IMAGE_STRUCTURED_GEOMETRY_CONFIG_V2_INVALID", f"{label} must be an object."
        )
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        raise GeometryConfigV2Error(
            "IMAGE_STRUCTURED_GEOMETRY_CONFIG_V2_INVALID", f"{label} must be an array."
        )
    return cast(Sequence[object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise GeometryConfigV2Error(
            "IMAGE_STRUCTURED_GEOMETRY_CONFIG_V2_INVALID", f"{label} must be text."
        )
    return value


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise GeometryConfigV2Error(
            "IMAGE_STRUCTURED_GEOMETRY_CONFIG_V2_INVALID", f"{label} must be an integer."
        )
    return value


def _number(value: object, label: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise GeometryConfigV2Error(
            "IMAGE_STRUCTURED_GEOMETRY_CONFIG_V2_INVALID", f"{label} must be numeric."
        )
    result = float(value)
    if not math.isfinite(result):
        raise GeometryConfigV2Error(
            "IMAGE_STRUCTURED_GEOMETRY_CONFIG_V2_INVALID", f"{label} must be finite."
        )
    return result


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise GeometryConfigV2Error(
            "IMAGE_STRUCTURED_GEOMETRY_CONFIG_V2_INVALID", f"{label} must be boolean."
        )
    return value


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


__all__ = [
    "DEFAULT_STRUCTURED_GEOMETRY_CONFIG_V2",
    "STRUCTURED_GEOMETRY_CONFIG_V2_VERSION",
    "AdaptiveAnalysisPolicyV2",
    "GameGeometryEvidenceProfileV2",
    "GeometryCandidateDecisionV2",
    "GeometryCandidateDisposition",
    "GeometryConfigMaturity",
    "GeometryConfigV2Error",
    "GeometryEvidenceReasonV2",
    "GeometryEvidenceThresholdsV2",
    "GeometryEvidenceWeightsV2",
    "StructuredGeometryConfigV2",
    "StructuredGeometryEvidenceV2",
    "evaluate_geometry_candidate_v2",
]
