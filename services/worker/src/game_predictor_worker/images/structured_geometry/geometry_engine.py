"""Source-level orchestration for independent structured board refinement."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from itertools import combinations
from typing import Final, Protocol, cast
from uuid import UUID

import cv2
import numpy as np
from game_predictor_api.domain.image_geometry_v2 import (
    SOURCE_COORDINATE_SPACE,
    ActiveBoardSlot,
    SourceQuad,
    canonical_json_bytes,
)
from numpy.typing import NDArray

from ..normalization import CanonicalSourceFrame
from ..page_geometry_registration import (
    DEFAULT_PAGE_REGISTRATION_THRESHOLDS,
    PageRegistrationThresholds,
)
from ..pipeline_contract import (
    STRUCTURED_OPENCV_INDEPENDENT_BOARD_VERSION,
    STRUCTURED_OPENCV_PINNED_PREFLIGHT_VERSION,
)
from .confidence import (
    DEFAULT_STRUCTURED_GEOMETRY_VALIDATION_THRESHOLDS,
    BoardGeometryDisposition,
    BoardGeometryEvidence,
    BoardGeometryReasonCode,
    GeometryConfidenceComponents,
    GeometryConfidenceDecision,
    StructuredGeometryValidationThresholds,
    evaluate_geometry_confidence,
)
from .global_initialization import (
    DEFAULT_STRUCTURED_GEOMETRY_INITIALIZATION_THRESHOLDS,
    STRUCTURED_GEOMETRY_ENGINE_ID,
    GlobalInitializationMethod,
    GlobalInitializationResult,
    GlobalInitializationStatus,
    StructuredGeometryInitializationError,
    StructuredGeometryInitializationRequest,
    StructuredGeometryInitializationThresholds,
)
from .global_initialization import (
    StructuredOpenCvGeometryEngine as StructuredGeometryGlobalInitializer,
)
from .line_refinement import (
    DEFAULT_STRUCTURED_BOARD_LINE_THRESHOLDS,
    BoardLineRefinementResult,
    BoardLineRefiner,
    RefinedGridLine,
    StructuredBoardLineThresholds,
)

STRUCTURED_SOURCE_GEOMETRY_VERSION: Final = "structured-source-geometry-result-v1"

type MetricValue = bool | float | int | str
type Matrix3x3 = tuple[
    tuple[float, float, float],
    tuple[float, float, float],
    tuple[float, float, float],
]


class SourceGeometryStatus(StrEnum):
    READY = "ready"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"
    NEEDS_MANUAL_CORRECTION = "needs_manual_correction"


class GeometryEngine(Protocol):
    engine_id: str
    version: str

    def detect(
        self,
        source: CanonicalSourceFrame,
        request: StructuredGeometryInitializationRequest,
    ) -> SourceGeometryResult: ...


@dataclass(frozen=True, slots=True)
class BoardGeometryResult:
    slot: ActiveBoardSlot
    disposition: BoardGeometryDisposition
    initial_quad: SourceQuad | None
    final_quad: SourceQuad | None
    ideal_to_source_homography: Matrix3x3 | None
    confidence: float
    confidence_components: GeometryConfidenceComponents
    evidence: BoardGeometryEvidence
    lines: tuple[RefinedGridLine, ...]
    reason_codes: tuple[BoardGeometryReasonCode, ...]

    def __post_init__(self) -> None:
        if not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("Board geometry confidence must be finite and bounded.")
        if self.disposition is BoardGeometryDisposition.AUTOMATIC and (
            self.final_quad is None or self.ideal_to_source_homography is None or self.reason_codes
        ):
            raise ValueError("Automatic board geometry requires a complete reason-free result.")
        if self.final_quad is None and self.ideal_to_source_homography is not None:
            raise ValueError("A board homography cannot exist without its final quad.")

    def to_payload(self) -> dict[str, object]:
        return {
            "confidenceComponents": self.confidence_components.to_payload(),
            "disposition": self.disposition.value,
            "evidence": self.evidence.to_payload(),
            "finalQuad": None if self.final_quad is None else self.final_quad.to_dict(),
            "geometryConfidence": round(self.confidence, 8),
            "idealToSourceHomography": (
                None
                if self.ideal_to_source_homography is None
                else [list(row) for row in self.ideal_to_source_homography]
            ),
            "initialQuad": None if self.initial_quad is None else self.initial_quad.to_dict(),
            "lines": [line.to_payload() for line in self.lines],
            "positionIndex": self.slot.position_index,
            "reasonCodes": [value.value for value in self.reason_codes],
            "sequenceNumber": self.slot.sequence_number,
        }


@dataclass(frozen=True, slots=True)
class SourceGeometryResult:
    status: SourceGeometryStatus
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
    global_initialization: GlobalInitializationResult
    boards: tuple[BoardGeometryResult, ...]
    reason_codes: tuple[str, ...]
    schema_version: int = 1
    coordinate_space: str = SOURCE_COORDINATE_SPACE

    def __post_init__(self) -> None:
        if self.active_board_slots != tuple(range(len(self.active_board_slots))):
            raise ValueError("Source geometry must preserve the attested active-slot prefix.")
        if tuple(board.slot.position_index for board in self.boards) != self.active_board_slots:
            raise ValueError("Source geometry must contain one ordered result per active slot.")
        expected = _source_status(self.boards)
        if self.status is not expected:
            raise ValueError("Source geometry status must aggregate its independent boards.")

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
            "boards": [board.to_payload() for board in self.boards],
            "canonicalHeight": self.canonical_height,
            "canonicalWidth": self.canonical_width,
            "configChecksumSha256": self.config_checksum_sha256,
            "coordinateSpace": self.coordinate_space,
            "engineId": self.engine_id,
            "engineVersion": self.engine_version,
            "globalInitialization": self.global_initialization.to_payload(),
            "normalizedPixelChecksumSha256": self.normalized_pixel_checksum_sha256,
            "reasonCodes": list(self.reason_codes),
            "schemaVersion": self.schema_version,
            "sourceChecksumSha256": self.source_checksum_sha256,
            "status": self.status.value,
            "topology": {
                "columns": self.topology_columns,
                "rows": self.topology_rows,
                "rulesVersionId": str(self.topology_rules_version_id),
            },
        }


class StructuredOpenCvGeometryEngine:
    """Run global initialization and independent local validation per slot."""

    engine_id = STRUCTURED_GEOMETRY_ENGINE_ID
    version = STRUCTURED_OPENCV_INDEPENDENT_BOARD_VERSION

    def __init__(
        self,
        *,
        load_anchor_rgb: Callable[[str], NDArray[np.uint8]],
        engine_version: str = STRUCTURED_OPENCV_INDEPENDENT_BOARD_VERSION,
        initialization_thresholds: StructuredGeometryInitializationThresholds = (
            DEFAULT_STRUCTURED_GEOMETRY_INITIALIZATION_THRESHOLDS
        ),
        registration_thresholds: PageRegistrationThresholds = (
            DEFAULT_PAGE_REGISTRATION_THRESHOLDS
        ),
        line_thresholds: StructuredBoardLineThresholds = (DEFAULT_STRUCTURED_BOARD_LINE_THRESHOLDS),
        validation_thresholds: StructuredGeometryValidationThresholds = (
            DEFAULT_STRUCTURED_GEOMETRY_VALIDATION_THRESHOLDS
        ),
        line_refiner: BoardLineRefiner | None = None,
    ) -> None:
        if engine_version not in {
            STRUCTURED_OPENCV_INDEPENDENT_BOARD_VERSION,
            STRUCTURED_OPENCV_PINNED_PREFLIGHT_VERSION,
        }:
            raise ValueError("Unsupported structured geometry engine version.")
        self.version = engine_version
        self._initializer = StructuredGeometryGlobalInitializer(
            load_anchor_rgb=load_anchor_rgb,
            thresholds=initialization_thresholds,
            registration_thresholds=registration_thresholds,
        )
        self._validation_thresholds = validation_thresholds
        self._refiner = line_refiner or BoardLineRefiner(
            thresholds=line_thresholds,
            validation_thresholds=validation_thresholds,
        )
        self.config_checksum_sha256 = hashlib.sha256(
            canonical_json_bytes(
                {
                    "globalInitializationConfigChecksumSha256": (
                        self._initializer.config_checksum_sha256
                    ),
                    "lineRefinementConfigChecksumSha256": self._refiner.config_checksum_sha256,
                    "version": self.version,
                }
            )
        ).hexdigest()

    def initialize(
        self,
        frame: CanonicalSourceFrame,
        request: StructuredGeometryInitializationRequest,
    ) -> GlobalInitializationResult:
        """Retain the TASK-0310 initialization API for compatibility and tests."""

        if (
            request.pinned_initial_quads is not None
            and self.version != STRUCTURED_OPENCV_PINNED_PREFLIGHT_VERSION
        ):
            raise StructuredGeometryInitializationError(
                "IMAGE_STRUCTURED_GEOMETRY_PINNED_PREFLIGHT_VERSION_UNSUPPORTED",
                "Pinned preflight geometry requires the versioned v2 structured engine.",
            )
        return self._initializer.initialize(frame, request)

    def detect(
        self,
        source: CanonicalSourceFrame,
        request: StructuredGeometryInitializationRequest,
    ) -> SourceGeometryResult:
        initialization = self.initialize(source, request)
        return refine_initialized_source_geometry(
            source=source,
            request=request,
            initialization=initialization,
            engine_id=self.engine_id,
            engine_version=self.version,
            config_checksum_sha256=self.config_checksum_sha256,
            line_refiner=self._refiner,
            validation_thresholds=self._validation_thresholds,
        )


def refine_initialized_source_geometry(
    *,
    source: CanonicalSourceFrame,
    request: StructuredGeometryInitializationRequest,
    initialization: GlobalInitializationResult,
    engine_id: str,
    engine_version: str,
    config_checksum_sha256: str,
    line_refiner: BoardLineRefiner,
    validation_thresholds: StructuredGeometryValidationThresholds = (
        DEFAULT_STRUCTURED_GEOMETRY_VALIDATION_THRESHOLDS
    ),
    initialization_failure_reason: BoardGeometryReasonCode = (
        BoardGeometryReasonCode.GLOBAL_INITIALIZATION_UNAVAILABLE
    ),
) -> SourceGeometryResult:
    """Apply the shared per-board refiner and hard gates to any initializer."""

    if initialization.status is not GlobalInitializationStatus.INITIALIZED:
        boards = tuple(
            _uninitialized_board_result(slot, reason=initialization_failure_reason)
            for slot in request.attested_range.active_slots
        )
        return _source_result(
            request,
            initialization=initialization,
            boards=boards,
            reason_codes=initialization.reason_codes,
            engine_id=engine_id,
            engine_version=engine_version,
            config_checksum_sha256=config_checksum_sha256,
        )

    global_score = _global_registration_score(initialization)
    if initialization.method is GlobalInitializationMethod.PINNED_PAGE_PREFLIGHT:
        refinements = tuple(
            _certified_preflight_refinement(
                initialized.initial_quad,
                topology_rows=request.topology.rows,
                topology_columns=request.topology.columns,
                source_width=source.source.width,
                source_height=source.source.height,
            )
            for initialized in initialization.slots
        )
    else:
        refinements = tuple(
            line_refiner.refine(
                source.rgb,
                initial_quad=initialized.initial_quad,
                topology=request.topology,
                global_registration_score=global_score,
            )
            for initialized in initialization.slots
        )
    order_violations, overlap_violations = _cross_slot_violations(
        refinements,
        maximum_overlap_fraction=validation_thresholds.maximum_overlap_fraction,
    )
    boards = tuple(
        _validated_board_result(
            slot,
            refinement,
            order_valid=index not in order_violations,
            overlap_valid=index not in overlap_violations,
            validation_thresholds=validation_thresholds,
        )
        for index, (slot, refinement) in enumerate(
            zip(request.attested_range.active_slots, refinements, strict=True)
        )
    )
    reason_codes = tuple(
        sorted({reason.value for board in boards for reason in board.reason_codes})
    )
    return _source_result(
        request,
        initialization=initialization,
        boards=boards,
        reason_codes=reason_codes,
        engine_id=engine_id,
        engine_version=engine_version,
        config_checksum_sha256=config_checksum_sha256,
    )


def _certified_preflight_refinement(
    initial_quad: SourceQuad,
    *,
    topology_rows: int,
    topology_columns: int,
    source_width: int,
    source_height: int,
) -> BoardLineRefinementResult:
    """Use the exact hard-gated page quad as final board geometry.

    A pinned page-geometry manifest has already proved the outer red frame,
    source dimensions, row-major order and non-overlap.  Games such as Blazing
    Hot do not draw stable internal 5x3 grid lines, so asking LSD to prove them
    again creates false corrections.  The topology still derives every cell
    deterministically from this checksum-bound outer quad.
    """

    ideal = np.asarray(
        [
            [0.0, 0.0],
            [float(topology_columns), 0.0],
            [float(topology_columns), float(topology_rows)],
            [0.0, float(topology_rows)],
        ],
        dtype=np.float32,
    )
    target = _quad_array(initial_quad).astype(np.float32)
    homography = cast(NDArray[np.float64], cv2.getPerspectiveTransform(ideal, target))
    source_support = _padded_cells_have_source_support(
        homography,
        rows=topology_rows,
        columns=topology_columns,
        source_width=source_width,
        source_height=source_height,
    )
    components = GeometryConfidenceComponents(
        global_registration_score=1.0,
        line_coverage_score=0.0,
        intersection_coverage_score=0.0,
        spacing_regularity_score=1.0,
        reprojection_score=1.0,
        border_evidence_score=1.0,
        slot_order_score=1.0,
        source_support_score=1.0 if source_support else 0.0,
        pinned_preflight_score=1.0,
    )
    return BoardLineRefinementResult(
        initial_quad=initial_quad,
        final_quad=initial_quad,
        ideal_to_source_homography=_matrix_payload(homography),
        evidence=BoardGeometryEvidence(
            observed_vertical_line_indexes=(),
            observed_horizontal_line_indexes=(),
            inferred_vertical_line_indexes=(),
            inferred_horizontal_line_indexes=(),
            external_boundaries_supported=4,
            supported_intersection_count=0,
            inlier_intersection_count=0,
            half_scale_p95_reprojection_error=None,
            homography_available=True,
            padded_cell_source_support_complete=source_support,
            initialization_alignment_valid=True,
            pinned_preflight_certified=True,
        ),
        confidence_components=components,
        lines=(),
        intrinsic_reason_codes=(),
        diagnostics=(("pinnedPreflightCertified", "true"),),
    )


def _padded_cells_have_source_support(
    homography: NDArray[np.float64],
    *,
    rows: int,
    columns: int,
    source_width: int,
    source_height: int,
    padding_fraction: float = 0.08,
) -> bool:
    points = np.asarray(
        [
            [
                [column - padding_fraction, row - padding_fraction],
                [column + 1 + padding_fraction, row - padding_fraction],
                [column + 1 + padding_fraction, row + 1 + padding_fraction],
                [column - padding_fraction, row + 1 + padding_fraction],
            ]
            for row in range(rows)
            for column in range(columns)
        ],
        dtype=np.float32,
    )
    projected = cv2.perspectiveTransform(points, homography).reshape(-1, 2)
    return bool(
        np.isfinite(projected).all()
        and (projected[:, 0] >= 0).all()
        and (projected[:, 0] < source_width).all()
        and (projected[:, 1] >= 0).all()
        and (projected[:, 1] < source_height).all()
    )


def _matrix_payload(value: NDArray[np.float64]) -> Matrix3x3:
    normalized = value / value[2, 2]
    return cast(
        Matrix3x3,
        tuple(tuple(float(cell) for cell in row) for row in normalized),
    )


def _validated_board_result(
    slot: ActiveBoardSlot,
    refinement: BoardLineRefinementResult,
    *,
    order_valid: bool,
    overlap_valid: bool,
    validation_thresholds: StructuredGeometryValidationThresholds,
) -> BoardGeometryResult:
    evidence = replace(
        refinement.evidence,
        slot_order_valid=order_valid,
        overlap_valid=overlap_valid,
    )
    components = replace(
        refinement.confidence_components,
        slot_order_score=1.0 if order_valid and overlap_valid else 0.0,
    )
    if refinement.intrinsic_reason_codes:
        decision = GeometryConfidenceDecision(
            disposition=BoardGeometryDisposition.NEEDS_MANUAL_CORRECTION,
            confidence=components.total,
            reason_codes=refinement.intrinsic_reason_codes,
        )
    else:
        decision = evaluate_geometry_confidence(
            evidence=evidence,
            components=components,
            thresholds=validation_thresholds,
        )
    return BoardGeometryResult(
        slot=slot,
        disposition=decision.disposition,
        initial_quad=refinement.initial_quad,
        final_quad=refinement.final_quad,
        ideal_to_source_homography=refinement.ideal_to_source_homography,
        confidence=decision.confidence,
        confidence_components=components,
        evidence=evidence,
        lines=refinement.lines,
        reason_codes=decision.reason_codes,
    )


def _source_result(
    request: StructuredGeometryInitializationRequest,
    *,
    initialization: GlobalInitializationResult,
    boards: tuple[BoardGeometryResult, ...],
    reason_codes: tuple[str, ...],
    engine_id: str,
    engine_version: str,
    config_checksum_sha256: str,
) -> SourceGeometryResult:
    return SourceGeometryResult(
        status=_source_status(boards),
        engine_id=engine_id,
        engine_version=engine_version,
        config_checksum_sha256=config_checksum_sha256,
        source_checksum_sha256=request.source_checksum_sha256,
        normalized_pixel_checksum_sha256=request.normalized_pixel_checksum_sha256,
        canonical_width=request.canonical_width,
        canonical_height=request.canonical_height,
        topology_rows=request.topology.rows,
        topology_columns=request.topology.columns,
        topology_rules_version_id=request.topology_rules_version_id,
        active_board_slots=request.active_board_slots,
        global_initialization=initialization,
        boards=boards,
        reason_codes=reason_codes,
    )


def _uninitialized_board_result(
    slot: ActiveBoardSlot,
    *,
    reason: BoardGeometryReasonCode = BoardGeometryReasonCode.GLOBAL_INITIALIZATION_UNAVAILABLE,
) -> BoardGeometryResult:
    components = GeometryConfidenceComponents(
        global_registration_score=0.0,
        line_coverage_score=0.0,
        intersection_coverage_score=0.0,
        spacing_regularity_score=0.0,
        reprojection_score=0.0,
        border_evidence_score=0.0,
        slot_order_score=0.0,
        source_support_score=0.0,
    )
    return BoardGeometryResult(
        slot=slot,
        disposition=BoardGeometryDisposition.NEEDS_MANUAL_CORRECTION,
        initial_quad=None,
        final_quad=None,
        ideal_to_source_homography=None,
        confidence=components.total,
        confidence_components=components,
        evidence=BoardGeometryEvidence.empty(),
        lines=(),
        reason_codes=(reason,),
    )


def _source_status(boards: Sequence[BoardGeometryResult]) -> SourceGeometryStatus:
    if any(
        board.disposition is BoardGeometryDisposition.NEEDS_MANUAL_CORRECTION for board in boards
    ):
        return SourceGeometryStatus.NEEDS_MANUAL_CORRECTION
    if any(board.disposition is BoardGeometryDisposition.NEEDS_MANUAL_REVIEW for board in boards):
        return SourceGeometryStatus.NEEDS_MANUAL_REVIEW
    return SourceGeometryStatus.READY


def _global_registration_score(initialization: GlobalInitializationResult) -> float:
    metrics: Mapping[str, MetricValue] = dict(initialization.metrics)
    if initialization.method is GlobalInitializationMethod.PINNED_PAGE_PREFLIGHT:
        return 1.0
    if initialization.method is GlobalInitializationMethod.VERIFIED_PROFILE_ORB_RANSAC:
        ratio = _metric_float(metrics.get("inlierRatio"))
        p95 = _metric_float(metrics.get("p95ReprojectionError"))
        ratio_score = min(1.0, ratio / 0.45)
        reprojection_score = max(0.0, 1.0 - p95 / 5.0)
        return _unit(0.6 * ratio_score + 0.4 * reprojection_score)
    if initialization.method is GlobalInitializationMethod.KEYPOINT_HEATMAPS:
        corner = _metric_float(metrics.get("meanCornerConfidence"))
        presence = _metric_float(metrics.get("minimumActivePresenceConfidence"))
        return _unit(0.75 * corner + 0.25 * presence)
    evidence = _metric_float(metrics.get("meanFrameEvidence"))
    residual = _metric_float(metrics.get("p95TemplateResidual"))
    residual_score = max(0.0, 1.0 - residual / 8.0)
    return _unit(0.65 * evidence + 0.35 * residual_score)


def _cross_slot_violations(
    refinements: Sequence[BoardLineRefinementResult],
    *,
    maximum_overlap_fraction: float,
) -> tuple[set[int], set[int]]:
    order_violations: set[int] = set()
    overlap_violations: set[int] = set()
    final_arrays = [
        None if value.final_quad is None else _quad_array(value.final_quad) for value in refinements
    ]
    initial_centres = np.asarray(
        [_quad_array(value.initial_quad).mean(axis=0) for value in refinements],
        dtype=np.float64,
    )
    for index, final in enumerate(final_arrays):
        if final is None:
            continue
        centre = final.mean(axis=0)
        nearest = int(np.argmin(np.linalg.norm(initial_centres - centre, axis=1)))
        if nearest != index:
            order_violations.update((index, nearest))
        row, column = divmod(index, 3)
        if column > 0 and final_arrays[index - 1] is not None:
            left_centre = cast(NDArray[np.float64], final_arrays[index - 1]).mean(axis=0)
            if float(left_centre[0]) >= float(centre[0]):
                order_violations.update((index - 1, index))
        if row > 0 and index >= 3 and final_arrays[index - 3] is not None:
            upper_centre = cast(NDArray[np.float64], final_arrays[index - 3]).mean(axis=0)
            if float(upper_centre[1]) >= float(centre[1]):
                order_violations.update((index - 3, index))
    for first, second in combinations(range(len(final_arrays)), 2):
        left = final_arrays[first]
        right = final_arrays[second]
        if left is None or right is None:
            continue
        intersection, _ = cv2.intersectConvexConvex(
            left.astype(np.float32), right.astype(np.float32)
        )
        minimum_area = min(
            abs(cv2.contourArea(left.astype(np.float32))),
            abs(cv2.contourArea(right.astype(np.float32))),
        )
        if minimum_area > 0 and intersection / minimum_area > maximum_overlap_fraction:
            overlap_violations.update((first, second))
    return order_violations, overlap_violations


def _quad_array(quad: SourceQuad) -> NDArray[np.float64]:
    return np.asarray([[point.x, point.y] for point in quad.corners], dtype=np.float64)


def _metric_float(value: MetricValue | None) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0.0
    return float(value)


def _unit(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


__all__ = [
    "STRUCTURED_OPENCV_INDEPENDENT_BOARD_VERSION",
    "STRUCTURED_SOURCE_GEOMETRY_VERSION",
    "BoardGeometryResult",
    "GeometryEngine",
    "SourceGeometryResult",
    "SourceGeometryStatus",
    "StructuredOpenCvGeometryEngine",
    "refine_initialized_source_geometry",
]
