"""Global initialization for the v0.10 structured OpenCV geometry engine.

This module intentionally stops before local board-line refinement.  Its
homography and projected quads are bounded starting regions only; TASK-0311
must independently establish the final geometry of every active board.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations
from typing import Final, cast
from uuid import UUID

import cv2
import numpy as np
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_geometry_v2 import (
    SOURCE_COORDINATE_SPACE,
    ActiveBoardSlot,
    AttestedSequenceRange,
    NormalizedSourceImage,
    SourcePoint,
    SourceQuad,
    canonical_json_bytes,
)
from numpy.typing import NDArray

from ..geometry import Point
from ..normalization import CanonicalSourceFrame
from ..page_geometry_registration import (
    DEFAULT_PAGE_REGISTRATION_THRESHOLDS,
    PAGE_REGISTRATION_THRESHOLDS_VERSION,
    PageRegistrationThresholds,
    VerifiedPageRegistrar,
)

STRUCTURED_GEOMETRY_ENGINE_ID: Final = "structured_opencv_v1"
STRUCTURED_GEOMETRY_GLOBAL_INITIALIZATION_VERSION: Final = (
    "structured-opencv-global-initialization-v1"
)
STRUCTURED_GEOMETRY_GLOBAL_CONFIG_VERSION: Final = (
    "structured-opencv-global-initialization-thresholds-v1"
)
GENERIC_FRAME_LINE_INITIALIZER_VERSION: Final = "generic-red-gradient-lsd-page-frame-v1"
_ANALYSIS_SCALE: Final = 0.5
_PAGE_COLUMNS: Final = 3
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

type MetricValue = bool | float | int | str
type HomographyPayload = tuple[
    tuple[float, float, float],
    tuple[float, float, float],
    tuple[float, float, float],
]


class StructuredGeometryInitializationError(ValueError):
    """Stable invalid-input error before image evidence is evaluated."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class GlobalInitializationStatus(StrEnum):
    INITIALIZED = "initialized"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"


class GlobalInitializationMethod(StrEnum):
    PINNED_PAGE_PREFLIGHT = "pinned_page_preflight"
    VERIFIED_PROFILE_ORB_RANSAC = "verified_profile_orb_ransac"
    GENERIC_FRAME_LINES = "generic_frame_lines"
    KEYPOINT_HEATMAPS = "keypoint_heatmaps"


@dataclass(frozen=True, slots=True)
class StructuredGeometryInitializationThresholds:
    """Pinned thresholds for evidence collection, not final board acceptance."""

    minimum_red_edge_coverage: float = 0.32
    minimum_gradient_edge_coverage: float = 0.34
    minimum_line_edge_coverage: float = 0.16
    minimum_candidate_area_fraction: float = 0.004
    maximum_candidate_area_fraction: float = 0.18
    minimum_candidate_aspect_ratio: float = 0.55
    maximum_candidate_aspect_ratio: float = 3.5
    maximum_generic_candidates: int = 13
    maximum_generic_p95_residual: float = 8.0

    def __post_init__(self) -> None:
        fractions = (
            self.minimum_red_edge_coverage,
            self.minimum_gradient_edge_coverage,
            self.minimum_line_edge_coverage,
            self.minimum_candidate_area_fraction,
            self.maximum_candidate_area_fraction,
        )
        if (
            any(not math.isfinite(value) or not 0 <= value <= 1 for value in fractions)
            or self.minimum_candidate_area_fraction >= self.maximum_candidate_area_fraction
            or not 0 < self.minimum_candidate_aspect_ratio < self.maximum_candidate_aspect_ratio
            or self.maximum_generic_candidates < 9
            or not math.isfinite(self.maximum_generic_p95_residual)
            or self.maximum_generic_p95_residual <= 0
        ):
            raise StructuredGeometryInitializationError(
                "IMAGE_STRUCTURED_GEOMETRY_CONFIG_INVALID",
                "Structured geometry initialization thresholds are invalid.",
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "analysisScale": _ANALYSIS_SCALE,
            "configVersion": STRUCTURED_GEOMETRY_GLOBAL_CONFIG_VERSION,
            "maximumCandidateAreaFraction": self.maximum_candidate_area_fraction,
            "maximumCandidateAspectRatio": self.maximum_candidate_aspect_ratio,
            "maximumGenericCandidates": self.maximum_generic_candidates,
            "maximumGenericP95Residual": self.maximum_generic_p95_residual,
            "minimumCandidateAreaFraction": self.minimum_candidate_area_fraction,
            "minimumCandidateAspectRatio": self.minimum_candidate_aspect_ratio,
            "minimumGradientEdgeCoverage": self.minimum_gradient_edge_coverage,
            "minimumLineEdgeCoverage": self.minimum_line_edge_coverage,
            "minimumRedEdgeCoverage": self.minimum_red_edge_coverage,
            "pageRegistrationThresholdsVersion": PAGE_REGISTRATION_THRESHOLDS_VERSION,
        }


DEFAULT_STRUCTURED_GEOMETRY_INITIALIZATION_THRESHOLDS = StructuredGeometryInitializationThresholds()


@dataclass(frozen=True, slots=True)
class StructuredGeometryInitializationRequest:
    source_checksum_sha256: str
    normalized_pixel_checksum_sha256: str
    canonical_width: int
    canonical_height: int
    topology: BoardTopology
    topology_rules_version_id: UUID
    attested_range: AttestedSequenceRange
    expected_board_count: int
    active_board_slots: tuple[int, ...]
    geometry_profile: Mapping[str, object] | None = None
    pinned_initial_quads: tuple[SourceQuad, ...] | None = None
    pinned_geometry_checksum_sha256: str | None = None

    def __post_init__(self) -> None:
        expected_slots = tuple(slot.position_index for slot in self.attested_range.active_slots)
        if (
            _SHA256.fullmatch(self.source_checksum_sha256) is None
            or _SHA256.fullmatch(self.normalized_pixel_checksum_sha256) is None
            or self.canonical_width < 1
            or self.canonical_height < 1
        ):
            raise StructuredGeometryInitializationError(
                "IMAGE_STRUCTURED_GEOMETRY_SOURCE_INVALID",
                "Structured geometry requires a canonical checksum-bound RGB source.",
            )
        if (
            self.expected_board_count != self.attested_range.board_count
            or self.active_board_slots != expected_slots
        ):
            raise StructuredGeometryInitializationError(
                "IMAGE_STRUCTURED_GEOMETRY_ACTIVE_SLOTS_INVALID",
                "Active board slots must be the attested row-major prefix.",
            )
        has_pinned_quads = self.pinned_initial_quads is not None
        has_pinned_checksum = self.pinned_geometry_checksum_sha256 is not None
        if has_pinned_quads != has_pinned_checksum:
            raise StructuredGeometryInitializationError(
                "IMAGE_STRUCTURED_GEOMETRY_PINNED_PREFLIGHT_INVALID",
                "Pinned preflight geometry requires both quads and its checksum.",
            )
        if has_pinned_quads:
            assert self.pinned_initial_quads is not None
            assert self.pinned_geometry_checksum_sha256 is not None
            if (
                _SHA256.fullmatch(self.pinned_geometry_checksum_sha256) is None
                or len(self.pinned_initial_quads) != len(self.active_board_slots)
                or self.geometry_profile is not None
            ):
                raise StructuredGeometryInitializationError(
                    "IMAGE_STRUCTURED_GEOMETRY_PINNED_PREFLIGHT_INVALID",
                    "Pinned preflight geometry must exactly cover the active slots.",
                )
            source = NormalizedSourceImage(
                source_checksum_sha256=self.source_checksum_sha256,
                normalized_pixel_checksum_sha256=self.normalized_pixel_checksum_sha256,
                width=self.canonical_width,
                height=self.canonical_height,
                exif_orientation=None,
                normalization_adapter_version="structured-preflight-validation-v1",
            )
            for quad in self.pinned_initial_quads:
                quad.require_within(source)

    @classmethod
    def for_frame(
        cls,
        frame: CanonicalSourceFrame,
        *,
        topology: BoardTopology,
        topology_rules_version_id: UUID,
        attested_range: AttestedSequenceRange,
        geometry_profile: Mapping[str, object] | None = None,
        pinned_initial_quads: tuple[SourceQuad, ...] | None = None,
        pinned_geometry_checksum_sha256: str | None = None,
    ) -> StructuredGeometryInitializationRequest:
        return cls(
            source_checksum_sha256=frame.source.source_checksum_sha256,
            normalized_pixel_checksum_sha256=frame.source.normalized_pixel_checksum_sha256,
            canonical_width=frame.source.width,
            canonical_height=frame.source.height,
            topology=topology,
            topology_rules_version_id=topology_rules_version_id,
            attested_range=attested_range,
            expected_board_count=attested_range.board_count,
            active_board_slots=tuple(slot.position_index for slot in attested_range.active_slots),
            geometry_profile=geometry_profile,
            pinned_initial_quads=pinned_initial_quads,
            pinned_geometry_checksum_sha256=pinned_geometry_checksum_sha256,
        )


@dataclass(frozen=True, slots=True)
class ActiveSlotInitialization:
    slot: ActiveBoardSlot
    initial_quad: SourceQuad

    def to_payload(self) -> dict[str, object]:
        return {
            "initialQuad": self.initial_quad.to_dict(),
            "positionIndex": self.slot.position_index,
            "sequenceNumber": self.slot.sequence_number,
        }


@dataclass(frozen=True, slots=True)
class GlobalInitializationResult:
    status: GlobalInitializationStatus
    method: GlobalInitializationMethod
    engine_id: str
    engine_version: str
    config_checksum_sha256: str
    source_checksum_sha256: str
    normalized_pixel_checksum_sha256: str
    canonical_width: int
    canonical_height: int
    topology_rows: int
    topology_columns: int
    topology_rules_version_id: UUID
    active_board_slots: tuple[int, ...]
    homography: HomographyPayload | None
    slots: tuple[ActiveSlotInitialization, ...]
    metrics: tuple[tuple[str, MetricValue], ...]
    reason_codes: tuple[str, ...]
    profile_checksum_sha256: str | None = None
    anchor_source_checksum_sha256: str | None = None
    schema_version: int = 1
    coordinate_space: str = SOURCE_COORDINATE_SPACE

    def __post_init__(self) -> None:
        if self.active_board_slots != tuple(range(len(self.active_board_slots))):
            raise StructuredGeometryInitializationError(
                "IMAGE_STRUCTURED_GEOMETRY_RESULT_INVALID",
                "A global initialization result must preserve the active slot prefix.",
            )
        if any(isinstance(value, float) and not math.isfinite(value) for _, value in self.metrics):
            raise StructuredGeometryInitializationError(
                "IMAGE_STRUCTURED_GEOMETRY_RESULT_INVALID",
                "Global initialization metrics must be finite.",
            )
        if self.status is GlobalInitializationStatus.INITIALIZED:
            homography_invalid = self.homography is not None and any(
                not math.isfinite(value) for row in self.homography for value in row
            )
            homography_missing = (
                self.method
                not in {
                    GlobalInitializationMethod.KEYPOINT_HEATMAPS,
                    GlobalInitializationMethod.PINNED_PAGE_PREFLIGHT,
                }
                and self.homography is None
            )
            if (
                homography_missing
                or homography_invalid
                or len(self.slots) != len(self.active_board_slots)
                or self.reason_codes
                or tuple(slot.slot.position_index for slot in self.slots) != self.active_board_slots
                or any(
                    point.x < 0
                    or point.x > self.canonical_width
                    or point.y < 0
                    or point.y > self.canonical_height
                    for slot in self.slots
                    for point in slot.initial_quad.corners
                )
            ):
                raise StructuredGeometryInitializationError(
                    "IMAGE_STRUCTURED_GEOMETRY_RESULT_INVALID",
                    "An initialized result requires one ROI per active slot.",
                )
        elif self.homography is not None or self.slots or not self.reason_codes:
            raise StructuredGeometryInitializationError(
                "IMAGE_STRUCTURED_GEOMETRY_RESULT_INVALID",
                "A manual-review result cannot expose unverified initialization quads.",
            )

    @property
    def result_checksum_sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self._payload())).hexdigest()

    def to_payload(self) -> dict[str, object]:
        payload = self._payload()
        payload["resultChecksumSha256"] = self.result_checksum_sha256
        return payload

    def _payload(self) -> dict[str, object]:
        return {
            "activeBoardSlots": list(self.active_board_slots),
            "anchorSourceChecksumSha256": self.anchor_source_checksum_sha256,
            "canonicalHeight": self.canonical_height,
            "canonicalWidth": self.canonical_width,
            "configChecksumSha256": self.config_checksum_sha256,
            "coordinateSpace": self.coordinate_space,
            "engineId": self.engine_id,
            "engineVersion": self.engine_version,
            "globalHomography": (
                [list(row) for row in self.homography] if self.homography is not None else None
            ),
            "method": self.method.value,
            "metrics": dict(self.metrics),
            "normalizedPixelChecksumSha256": self.normalized_pixel_checksum_sha256,
            "profileChecksumSha256": self.profile_checksum_sha256,
            "reasonCodes": list(self.reason_codes),
            "schemaVersion": self.schema_version,
            "slots": [slot.to_payload() for slot in self.slots],
            "sourceChecksumSha256": self.source_checksum_sha256,
            "status": self.status.value,
            "topology": {
                "columns": self.topology_columns,
                "rows": self.topology_rows,
                "rulesVersionId": str(self.topology_rules_version_id),
            },
        }


@dataclass(frozen=True, slots=True)
class _FrameCandidate:
    quad: NDArray[np.float32]
    center_x: float
    center_y: float
    area: float
    red_coverage: float
    gradient_coverage: float
    line_coverage: float

    @property
    def evidence(self) -> float:
        return (self.red_coverage + self.gradient_coverage + self.line_coverage) / 3.0


@dataclass(frozen=True, slots=True)
class _GenericInitialization:
    quads: tuple[SourceQuad, ...]
    homography: HomographyPayload
    metrics: tuple[tuple[str, MetricValue], ...]


class StructuredOpenCvGeometryEngine:
    """Compute a global starting point without claiming final board geometry."""

    engine_id = STRUCTURED_GEOMETRY_ENGINE_ID
    version = STRUCTURED_GEOMETRY_GLOBAL_INITIALIZATION_VERSION

    def __init__(
        self,
        *,
        load_anchor_rgb: Callable[[str], NDArray[np.uint8]],
        thresholds: StructuredGeometryInitializationThresholds = (
            DEFAULT_STRUCTURED_GEOMETRY_INITIALIZATION_THRESHOLDS
        ),
        registration_thresholds: PageRegistrationThresholds = (
            DEFAULT_PAGE_REGISTRATION_THRESHOLDS
        ),
    ) -> None:
        self._load_anchor_rgb = load_anchor_rgb
        self._thresholds = thresholds
        self._registration_thresholds = registration_thresholds
        config = {
            "global": thresholds.to_payload(),
            "registration": {
                "maximumP95ReprojectionError": (
                    registration_thresholds.maximum_p95_reprojection_error
                ),
                "minimumInlierRatio": registration_thresholds.minimum_inlier_ratio,
                "minimumInliers": registration_thresholds.minimum_inliers,
            },
        }
        self.config_checksum_sha256 = hashlib.sha256(canonical_json_bytes(config)).hexdigest()

    def initialize(
        self,
        frame: CanonicalSourceFrame,
        request: StructuredGeometryInitializationRequest,
    ) -> GlobalInitializationResult:
        self._validate_frame(frame, request=request)
        if request.pinned_initial_quads is not None:
            return self._initialize_from_pinned_preflight(request)
        profile = request.geometry_profile
        if _has_verified_anchors(profile):
            return self._initialize_from_profile(
                frame,
                request=request,
                profile=cast(Mapping[str, object], profile),
            )
        return self._initialize_without_profile(frame, request=request)

    def _initialize_from_pinned_preflight(
        self,
        request: StructuredGeometryInitializationRequest,
    ) -> GlobalInitializationResult:
        quads = request.pinned_initial_quads
        checksum = request.pinned_geometry_checksum_sha256
        if quads is None or checksum is None:
            raise StructuredGeometryInitializationError(
                "IMAGE_STRUCTURED_GEOMETRY_PINNED_PREFLIGHT_INVALID",
                "Pinned preflight geometry is incomplete.",
            )
        slots = tuple(
            ActiveSlotInitialization(slot=slot, initial_quad=quad)
            for slot, quad in zip(request.attested_range.active_slots, quads, strict=True)
        )
        return GlobalInitializationResult(
            status=GlobalInitializationStatus.INITIALIZED,
            method=GlobalInitializationMethod.PINNED_PAGE_PREFLIGHT,
            engine_id=self.engine_id,
            engine_version=self.version,
            config_checksum_sha256=self.config_checksum_sha256,
            source_checksum_sha256=request.source_checksum_sha256,
            normalized_pixel_checksum_sha256=request.normalized_pixel_checksum_sha256,
            canonical_width=request.canonical_width,
            canonical_height=request.canonical_height,
            topology_rows=request.topology.rows,
            topology_columns=request.topology.columns,
            topology_rules_version_id=request.topology_rules_version_id,
            active_board_slots=request.active_board_slots,
            homography=None,
            slots=slots,
            metrics=(("preflightVerified", True),),
            reason_codes=(),
            profile_checksum_sha256=checksum,
        )

    def _initialize_from_profile(
        self,
        frame: CanonicalSourceFrame,
        *,
        request: StructuredGeometryInitializationRequest,
        profile: Mapping[str, object],
    ) -> GlobalInitializationResult:
        registrar = VerifiedPageRegistrar(
            profile,
            load_anchor_rgb=self._load_anchor_rgb,
            thresholds=self._registration_thresholds,
        )
        registration = registrar.initialize(
            frame.rgb,
            active_board_slots=request.active_board_slots,
        )
        profile_checksum = _mapping_checksum(profile)
        if registration is None:
            return self._manual_review_result(
                request,
                method=GlobalInitializationMethod.VERIFIED_PROFILE_ORB_RANSAC,
                reason_code="verified_profile_registration_failed",
                metrics=(("analysisScale", _ANALYSIS_SCALE),),
                profile_checksum_sha256=profile_checksum,
            )
        slots = tuple(
            ActiveSlotInitialization(
                slot=slot,
                initial_quad=_source_quad_from_integer_quad(quad),
            )
            for slot, quad in zip(
                request.attested_range.active_slots,
                registration.initialization_quads,
                strict=True,
            )
        )
        return GlobalInitializationResult(
            status=GlobalInitializationStatus.INITIALIZED,
            method=GlobalInitializationMethod.VERIFIED_PROFILE_ORB_RANSAC,
            engine_id=self.engine_id,
            engine_version=self.version,
            config_checksum_sha256=self.config_checksum_sha256,
            source_checksum_sha256=request.source_checksum_sha256,
            normalized_pixel_checksum_sha256=request.normalized_pixel_checksum_sha256,
            canonical_width=request.canonical_width,
            canonical_height=request.canonical_height,
            topology_rows=request.topology.rows,
            topology_columns=request.topology.columns,
            topology_rules_version_id=request.topology_rules_version_id,
            active_board_slots=request.active_board_slots,
            homography=cast(HomographyPayload, registration.native_homography),
            slots=slots,
            metrics=_metrics(
                analysisScale=_ANALYSIS_SCALE,
                featureCount=registration.feature_count,
                inlierCount=registration.inlier_count,
                inlierRatio=round(registration.inlier_ratio, 8),
                p95ReprojectionError=round(registration.p95_reprojection_error, 8),
            ),
            reason_codes=(),
            profile_checksum_sha256=profile_checksum,
            anchor_source_checksum_sha256=registration.anchor_source_checksum_sha256,
        )

    def _initialize_without_profile(
        self,
        frame: CanonicalSourceFrame,
        *,
        request: StructuredGeometryInitializationRequest,
    ) -> GlobalInitializationResult:
        generic, diagnostic_metrics = _generic_frame_line_initialization(
            frame.rgb,
            active_board_slots=request.active_board_slots,
            thresholds=self._thresholds,
        )
        if generic is None:
            return self._manual_review_result(
                request,
                method=GlobalInitializationMethod.GENERIC_FRAME_LINES,
                reason_code="generic_frame_line_evidence_insufficient",
                metrics=diagnostic_metrics,
            )
        slots = tuple(
            ActiveSlotInitialization(slot=slot, initial_quad=quad)
            for slot, quad in zip(
                request.attested_range.active_slots,
                generic.quads,
                strict=True,
            )
        )
        return GlobalInitializationResult(
            status=GlobalInitializationStatus.INITIALIZED,
            method=GlobalInitializationMethod.GENERIC_FRAME_LINES,
            engine_id=self.engine_id,
            engine_version=self.version,
            config_checksum_sha256=self.config_checksum_sha256,
            source_checksum_sha256=request.source_checksum_sha256,
            normalized_pixel_checksum_sha256=request.normalized_pixel_checksum_sha256,
            canonical_width=request.canonical_width,
            canonical_height=request.canonical_height,
            topology_rows=request.topology.rows,
            topology_columns=request.topology.columns,
            topology_rules_version_id=request.topology_rules_version_id,
            active_board_slots=request.active_board_slots,
            homography=generic.homography,
            slots=slots,
            metrics=generic.metrics,
            reason_codes=(),
        )

    def _manual_review_result(
        self,
        request: StructuredGeometryInitializationRequest,
        *,
        method: GlobalInitializationMethod,
        reason_code: str,
        metrics: tuple[tuple[str, MetricValue], ...],
        profile_checksum_sha256: str | None = None,
    ) -> GlobalInitializationResult:
        return GlobalInitializationResult(
            status=GlobalInitializationStatus.NEEDS_MANUAL_REVIEW,
            method=method,
            engine_id=self.engine_id,
            engine_version=self.version,
            config_checksum_sha256=self.config_checksum_sha256,
            source_checksum_sha256=request.source_checksum_sha256,
            normalized_pixel_checksum_sha256=request.normalized_pixel_checksum_sha256,
            canonical_width=request.canonical_width,
            canonical_height=request.canonical_height,
            topology_rows=request.topology.rows,
            topology_columns=request.topology.columns,
            topology_rules_version_id=request.topology_rules_version_id,
            active_board_slots=request.active_board_slots,
            homography=None,
            slots=(),
            metrics=metrics,
            reason_codes=(reason_code,),
            profile_checksum_sha256=profile_checksum_sha256,
        )

    @staticmethod
    def _validate_frame(
        frame: CanonicalSourceFrame,
        *,
        request: StructuredGeometryInitializationRequest,
    ) -> None:
        source = frame.source
        if (
            source.source_checksum_sha256 != request.source_checksum_sha256
            or source.normalized_pixel_checksum_sha256 != request.normalized_pixel_checksum_sha256
            or source.width != request.canonical_width
            or source.height != request.canonical_height
            or source.coordinate_space != SOURCE_COORDINATE_SPACE
        ):
            raise StructuredGeometryInitializationError(
                "IMAGE_STRUCTURED_GEOMETRY_SOURCE_DRIFT",
                "The canonical source changed after the geometry request was pinned.",
            )


def _generic_frame_line_initialization(
    rgb: NDArray[np.uint8],
    *,
    active_board_slots: tuple[int, ...],
    thresholds: StructuredGeometryInitializationThresholds,
) -> tuple[_GenericInitialization | None, tuple[tuple[str, MetricValue], ...]]:
    half = cast(
        NDArray[np.uint8],
        cv2.resize(rgb, None, fx=_ANALYSIS_SCALE, fy=_ANALYSIS_SCALE, interpolation=cv2.INTER_AREA),
    )
    gray = cast(NDArray[np.uint8], cv2.cvtColor(half, cv2.COLOR_RGB2GRAY))
    red = _red_mask(half)
    gradient = _gradient_mask(gray)
    line_mask, line_count = _line_mask(gray)
    candidates = _frame_candidates(
        red,
        gradient_mask=gradient,
        line_mask=line_mask,
        thresholds=thresholds,
    )
    diagnostic = _metrics(
        analysisScale=_ANALYSIS_SCALE,
        detectedFrameCandidateCount=len(candidates),
        detectedLineSegmentCount=line_count,
        expectedBoardCount=len(active_board_slots),
        initializerVersion=GENERIC_FRAME_LINE_INITIALIZER_VERSION,
    )
    ordered = _select_ordered_candidates(
        candidates,
        expected_count=len(active_board_slots),
        maximum_candidates=thresholds.maximum_generic_candidates,
    )
    if ordered is None:
        return None, diagnostic
    homography, projected, p95, pitch_x, pitch_y = _fit_global_template(ordered)
    if (
        homography is None
        or projected is None
        or not math.isfinite(p95)
        or p95 > thresholds.maximum_generic_p95_residual
    ):
        failure_metrics = diagnostic
        if math.isfinite(p95):
            failure_metrics = (*diagnostic, ("p95TemplateResidual", round(p95, 8)))
        return None, failure_metrics
    native_homography = np.asarray(homography, dtype=np.float64)
    native_homography = np.diag([2.0, 2.0, 1.0]) @ native_homography
    native_quads = tuple(_source_quad_from_array(quad * 2.0) for quad in projected)
    if not _ordered_source_quads(native_quads, width=rgb.shape[1], height=rgb.shape[0]):
        return None, (*diagnostic, ("p95TemplateResidual", round(p95, 8)))
    evidence = sum(candidate.evidence for candidate in ordered) / len(ordered)
    metrics = _metrics(
        analysisScale=_ANALYSIS_SCALE,
        detectedFrameCandidateCount=len(candidates),
        detectedLineSegmentCount=line_count,
        expectedBoardCount=len(active_board_slots),
        initializerVersion=GENERIC_FRAME_LINE_INITIALIZER_VERSION,
        meanFrameEvidence=round(evidence, 8),
        p95TemplateResidual=round(p95, 8),
        selectedFrameCandidateCount=len(ordered),
        templateHorizontalPitch=round(pitch_x, 8),
        templateVerticalPitch=round(pitch_y, 8),
    )
    return (
        _GenericInitialization(
            quads=native_quads,
            homography=_homography_payload(native_homography),
            metrics=metrics,
        ),
        metrics,
    )


def _red_mask(rgb: NDArray[np.uint8]) -> NDArray[np.uint8]:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    low = cv2.inRange(hsv, np.array((0, 80, 50)), np.array((18, 255, 255)))
    high = cv2.inRange(hsv, np.array((165, 80, 50)), np.array((179, 255, 255)))
    mask = cast(NDArray[np.uint8], cv2.bitwise_or(low, high))
    return cast(
        NDArray[np.uint8],
        cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), dtype=np.uint8)),
    )


def _gradient_mask(gray: NDArray[np.uint8]) -> NDArray[np.uint8]:
    horizontal = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    vertical = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(horizontal, vertical)
    positive = magnitude[magnitude > 0]
    threshold = max(24.0, float(np.percentile(positive, 70))) if positive.size else 255.0
    return cast(NDArray[np.uint8], np.where(magnitude >= threshold, 255, 0).astype(np.uint8))


def _line_mask(gray: NDArray[np.uint8]) -> tuple[NDArray[np.uint8], int]:
    detector = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
    detected = detector.detect(gray)[0]
    mask = np.zeros_like(gray)
    if detected is None:
        return mask, 0
    minimum_length = max(8.0, min(gray.shape[:2]) * 0.025)
    count = 0
    for raw in detected.reshape(-1, 4):
        x1, y1, x2, y2 = (float(value) for value in raw)
        if math.hypot(x2 - x1, y2 - y1) < minimum_length:
            continue
        cv2.line(
            mask,
            (int(round(x1)), int(round(y1))),
            (int(round(x2)), int(round(y2))),
            255,
            2,
        )
        count += 1
    return mask, count


def _frame_candidates(
    red_mask: NDArray[np.uint8],
    *,
    gradient_mask: NDArray[np.uint8],
    line_mask: NDArray[np.uint8],
    thresholds: StructuredGeometryInitializationThresholds,
) -> tuple[_FrameCandidate, ...]:
    contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    image_area = float(red_mask.shape[0] * red_mask.shape[1])
    red_support = cast(NDArray[np.uint8], cv2.dilate(red_mask, np.ones((3, 3), dtype=np.uint8)))
    gradient_support = cast(
        NDArray[np.uint8], cv2.dilate(gradient_mask, np.ones((3, 3), dtype=np.uint8))
    )
    line_support = cast(NDArray[np.uint8], cv2.dilate(line_mask, np.ones((5, 5), dtype=np.uint8)))
    candidates: list[_FrameCandidate] = []
    for contour in contours:
        hull = cv2.convexHull(contour)
        area = float(cv2.contourArea(hull))
        fraction = area / image_area
        if not (
            thresholds.minimum_candidate_area_fraction
            <= fraction
            <= thresholds.maximum_candidate_area_fraction
        ):
            continue
        perimeter = cv2.arcLength(hull, True)
        approximation = cv2.approxPolyDP(hull, max(1.0, perimeter * 0.025), True)
        if len(approximation) == 4 and cv2.isContourConvex(approximation):
            quad = _order_quad(approximation.reshape(4, 2).astype(np.float32))
        else:
            quad = _order_quad(cv2.boxPoints(cv2.minAreaRect(hull)).astype(np.float32))
        widths = (np.linalg.norm(quad[1] - quad[0]), np.linalg.norm(quad[2] - quad[3]))
        heights = (np.linalg.norm(quad[3] - quad[0]), np.linalg.norm(quad[2] - quad[1]))
        mean_width = float(sum(widths) / 2.0)
        mean_height = float(sum(heights) / 2.0)
        if mean_width <= 0 or mean_height <= 0:
            continue
        aspect = mean_width / mean_height
        if not (
            thresholds.minimum_candidate_aspect_ratio
            <= aspect
            <= thresholds.maximum_candidate_aspect_ratio
        ):
            continue
        red_coverage = _edge_coverage(red_support, quad)
        gradient_coverage = _edge_coverage(gradient_support, quad)
        line_coverage = _edge_coverage(line_support, quad)
        if (
            red_coverage < thresholds.minimum_red_edge_coverage
            or gradient_coverage < thresholds.minimum_gradient_edge_coverage
            or line_coverage < thresholds.minimum_line_edge_coverage
        ):
            continue
        center = quad.mean(axis=0)
        candidates.append(
            _FrameCandidate(
                quad=quad,
                center_x=float(center[0]),
                center_y=float(center[1]),
                area=area,
                red_coverage=red_coverage,
                gradient_coverage=gradient_coverage,
                line_coverage=line_coverage,
            )
        )
    return tuple(
        sorted(
            candidates,
            key=lambda value: (
                value.center_y,
                value.center_x,
                -value.evidence,
            ),
        )
    )


def _select_ordered_candidates(
    candidates: Sequence[_FrameCandidate],
    *,
    expected_count: int,
    maximum_candidates: int,
) -> tuple[_FrameCandidate, ...] | None:
    if len(candidates) < expected_count:
        return None
    bounded = sorted(
        candidates,
        key=lambda value: (-value.evidence, value.center_y, value.center_x),
    )[: max(expected_count, maximum_candidates)]
    best: tuple[float, tuple[_FrameCandidate, ...]] | None = None
    for selected in combinations(bounded, expected_count):
        ordered = _row_major_prefix(selected, expected_count=expected_count)
        score = _grid_score(ordered)
        if score is None:
            continue
        tie_key = tuple(
            round(value, 4)
            for candidate in ordered
            for value in (candidate.center_y, candidate.center_x)
        )
        candidate_value = (score, ordered)
        if best is None or score > best[0] + 1e-9:
            best = candidate_value
        elif best is not None and math.isclose(score, best[0], abs_tol=1e-9):
            best_key = tuple(
                round(value, 4)
                for candidate in best[1]
                for value in (candidate.center_y, candidate.center_x)
            )
            if tie_key < best_key:
                best = candidate_value
    return None if best is None else best[1]


def _row_major_prefix(
    candidates: Sequence[_FrameCandidate],
    *,
    expected_count: int,
) -> tuple[_FrameCandidate, ...]:
    row_counts = tuple(
        min(_PAGE_COLUMNS, max(0, expected_count - row * _PAGE_COLUMNS))
        for row in range(math.ceil(expected_count / _PAGE_COLUMNS))
    )
    remaining = sorted(candidates, key=lambda value: (value.center_y, value.center_x))
    rows: list[tuple[_FrameCandidate, ...]] = []
    offset = 0
    for count in row_counts:
        row = tuple(sorted(remaining[offset : offset + count], key=lambda value: value.center_x))
        rows.append(row)
        offset += count
    return tuple(candidate for row in rows for candidate in row)


def _grid_score(candidates: Sequence[_FrameCandidate]) -> float | None:
    widths = np.asarray([_quad_width(value.quad) for value in candidates])
    heights = np.asarray([_quad_height(value.quad) for value in candidates])
    if np.any(widths <= 1) or np.any(heights <= 1):
        return None
    for index, candidate in enumerate(candidates):
        row, column = divmod(index, _PAGE_COLUMNS)
        if column > 0:
            left = candidates[index - 1]
            if candidate.center_x - left.center_x < 0.45 * float(np.median(widths)):
                return None
        if row > 0 and index - _PAGE_COLUMNS < len(candidates):
            above = candidates[index - _PAGE_COLUMNS]
            if candidate.center_y - above.center_y < 0.45 * float(np.median(heights)):
                return None
    size_penalty = float(np.std(widths) / np.mean(widths) + np.std(heights) / np.mean(heights))
    evidence = sum(candidate.evidence for candidate in candidates) / len(candidates)
    return evidence - 0.18 * size_penalty


def _fit_global_template(
    candidates: Sequence[_FrameCandidate],
) -> tuple[
    NDArray[np.float64] | None,
    tuple[NDArray[np.float32], ...] | None,
    float,
    float,
    float,
]:
    width = float(np.median([_quad_width(value.quad) for value in candidates]))
    height = float(np.median([_quad_height(value.quad) for value in candidates]))
    horizontal_pitches = [
        (candidates[index].center_x - candidates[index - 1].center_x) / width
        for index in range(1, len(candidates))
        if index % _PAGE_COLUMNS != 0
    ]
    vertical_pitches = [
        (candidates[index].center_y - candidates[index - _PAGE_COLUMNS].center_y) / height
        for index in range(_PAGE_COLUMNS, len(candidates))
    ]
    pitch_x = float(np.median(horizontal_pitches)) if horizontal_pitches else 1.35
    pitch_y = float(np.median(vertical_pitches)) if vertical_pitches else 1.55
    pitch_x = min(3.0, max(1.05, pitch_x))
    pitch_y = min(3.0, max(1.05, pitch_y))
    canonical_quads = tuple(
        np.asarray(
            [
                [column * pitch_x, row * pitch_y],
                [column * pitch_x + 1.0, row * pitch_y],
                [column * pitch_x + 1.0, row * pitch_y + 1.0],
                [column * pitch_x, row * pitch_y + 1.0],
            ],
            dtype=np.float32,
        )
        for row, column in (divmod(index, _PAGE_COLUMNS) for index in range(len(candidates)))
    )
    source = np.concatenate(canonical_quads).reshape(-1, 1, 2)
    target = np.concatenate([value.quad for value in candidates]).reshape(-1, 1, 2)
    homography, _ = cv2.findHomography(source, target, method=0)
    if homography is None or not np.isfinite(homography).all() or abs(homography[2, 2]) < 1e-12:
        return None, None, float("inf"), pitch_x, pitch_y
    typed = cast(NDArray[np.float64], homography / homography[2, 2])
    projected = tuple(
        cast(
            NDArray[np.float32],
            cv2.perspectiveTransform(quad.reshape(-1, 1, 2), typed).reshape(4, 2),
        )
        for quad in canonical_quads
    )
    errors = np.concatenate(
        [
            np.linalg.norm(predicted - candidate.quad, axis=1)
            for predicted, candidate in zip(projected, candidates, strict=True)
        ]
    )
    return typed, projected, float(np.percentile(errors, 95)), pitch_x, pitch_y


def _order_quad(points: NDArray[np.float32]) -> NDArray[np.float32]:
    ordered_y = points[np.argsort(points[:, 1])]
    top = ordered_y[:2][np.argsort(ordered_y[:2, 0])]
    bottom = ordered_y[2:][np.argsort(ordered_y[2:, 0])]
    return cast(
        NDArray[np.float32],
        np.asarray([top[0], top[1], bottom[1], bottom[0]], dtype=np.float32),
    )


def _edge_coverage(mask: NDArray[np.uint8], quad: NDArray[np.float32]) -> float:
    height, width = mask.shape
    observed: list[NDArray[np.bool_]] = []
    for first, second in zip(quad, np.roll(quad, -1, axis=0), strict=True):
        length = max(12, int(round(float(np.linalg.norm(second - first)) / 2.0)))
        fractions = np.linspace(0.0, 1.0, num=length)
        points = first[None, :] + (second - first)[None, :] * fractions[:, None]
        xs = np.rint(points[:, 0]).astype(np.intp)
        ys = np.rint(points[:, 1]).astype(np.intp)
        valid = (xs >= 0) & (xs < width) & (ys >= 0) & (ys < height)
        values: NDArray[np.bool_] = np.zeros(length, dtype=bool)
        values[valid] = mask[ys[valid], xs[valid]] > 0
        observed.append(values)
    return float(np.concatenate(observed).mean()) if observed else 0.0


def _quad_width(quad: NDArray[np.float32]) -> float:
    return float((np.linalg.norm(quad[1] - quad[0]) + np.linalg.norm(quad[2] - quad[3])) / 2)


def _quad_height(quad: NDArray[np.float32]) -> float:
    return float((np.linalg.norm(quad[3] - quad[0]) + np.linalg.norm(quad[2] - quad[1])) / 2)


def _ordered_source_quads(quads: Sequence[SourceQuad], *, width: int, height: int) -> bool:
    centres: list[tuple[float, float]] = []
    polygons: list[NDArray[np.float32]] = []
    for quad in quads:
        if any(
            point.x < 0 or point.x > width or point.y < 0 or point.y > height
            for point in quad.corners
        ):
            return False
        polygon = np.asarray([[point.x, point.y] for point in quad.corners], dtype=np.float32)
        if not cv2.isContourConvex(polygon) or abs(cv2.contourArea(polygon)) < 25.0:
            return False
        centres.append((float(polygon[:, 0].mean()), float(polygon[:, 1].mean())))
        polygons.append(polygon)
    for index, center in enumerate(centres):
        row, column = divmod(index, _PAGE_COLUMNS)
        if column > 0 and centres[index - 1][0] >= center[0]:
            return False
        if (
            row > 0
            and index - _PAGE_COLUMNS < len(centres)
            and centres[index - _PAGE_COLUMNS][1] >= center[1]
        ):
            return False
    for first, second in combinations(range(len(polygons)), 2):
        intersection, _ = cv2.intersectConvexConvex(polygons[first], polygons[second])
        if intersection > 2.0:
            return False
    return True


def _source_quad_from_integer_quad(quad: Sequence[Point]) -> SourceQuad:
    points = tuple(SourcePoint(x=float(point.x), y=float(point.y)) for point in quad)
    return SourceQuad(
        corners=cast(
            tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint],
            points,
        )
    )


def _source_quad_from_array(quad: NDArray[np.float32]) -> SourceQuad:
    points = tuple(SourcePoint(x=float(point[0]), y=float(point[1])) for point in quad)
    return SourceQuad(
        corners=cast(
            tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint],
            points,
        )
    )


def _homography_payload(homography: NDArray[np.float64]) -> HomographyPayload:
    normalized = homography / homography[2, 2]
    rows = tuple(tuple(round(float(value), 12) for value in row) for row in normalized)
    return cast(HomographyPayload, rows)


def _metrics(**values: MetricValue) -> tuple[tuple[str, MetricValue], ...]:
    return tuple(sorted(values.items()))


def _has_verified_anchors(profile: Mapping[str, object] | None) -> bool:
    if profile is None:
        return False
    anchors = profile.get("anchors")
    return (
        profile.get("policy") == "verified-page-registration-v1"
        and isinstance(anchors, Sequence)
        and not isinstance(anchors, str | bytes)
        and bool(anchors)
    )


def _mapping_checksum(value: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_json_bytes(dict(value))).hexdigest()


__all__ = [
    "DEFAULT_STRUCTURED_GEOMETRY_INITIALIZATION_THRESHOLDS",
    "GENERIC_FRAME_LINE_INITIALIZER_VERSION",
    "STRUCTURED_GEOMETRY_ENGINE_ID",
    "STRUCTURED_GEOMETRY_GLOBAL_CONFIG_VERSION",
    "STRUCTURED_GEOMETRY_GLOBAL_INITIALIZATION_VERSION",
    "ActiveSlotInitialization",
    "GlobalInitializationMethod",
    "GlobalInitializationResult",
    "GlobalInitializationStatus",
    "StructuredGeometryInitializationError",
    "StructuredGeometryInitializationRequest",
    "StructuredGeometryInitializationThresholds",
    "StructuredOpenCvGeometryEngine",
]
