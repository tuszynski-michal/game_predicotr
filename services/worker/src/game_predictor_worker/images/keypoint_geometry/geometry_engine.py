"""Shadow-only keypoint initializer using the shared geometry hard gates."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final, Protocol

from game_predictor_api.domain.image_geometry_v2 import canonical_json_bytes

from ..normalization import CanonicalSourceFrame
from ..structured_geometry.confidence import (
    DEFAULT_STRUCTURED_GEOMETRY_VALIDATION_THRESHOLDS,
    BoardGeometryReasonCode,
    StructuredGeometryValidationThresholds,
)
from ..structured_geometry.geometry_engine import (
    SourceGeometryResult,
    refine_initialized_source_geometry,
)
from ..structured_geometry.global_initialization import (
    ActiveSlotInitialization,
    GlobalInitializationMethod,
    GlobalInitializationResult,
    GlobalInitializationStatus,
    StructuredGeometryInitializationError,
    StructuredGeometryInitializationRequest,
)
from ..structured_geometry.line_refinement import (
    DEFAULT_STRUCTURED_BOARD_LINE_THRESHOLDS,
    BoardLineRefiner,
    StructuredBoardLineThresholds,
)
from .model import KEYPOINT_GEOMETRY_MODEL_VERSION
from .onnx_adapter import (
    KEYPOINT_ONNX_ADAPTER_VERSION,
    KeypointGeometryPrediction,
)

KEYPOINT_GEOMETRY_ENGINE_ID: Final = "keypoint_geometry_v1"
KEYPOINT_GEOMETRY_ENGINE_VERSION: Final = "keypoint-geometry-fallback-shadow-v1"


class KeypointGeometryPredictor(Protocol):
    artifact_sha256: str

    def predict(
        self,
        source: CanonicalSourceFrame,
        *,
        active_board_slots: tuple[int, ...],
    ) -> KeypointGeometryPrediction: ...


@dataclass(frozen=True, slots=True)
class KeypointGeometryShadowEvaluation:
    primary_result_checksum_sha256: str
    candidate: SourceGeometryResult
    can_replace_primary: bool = False
    rollout_mode: str = "shadow_only"


class KeypointGeometryEngine:
    """Infer initial quads, then reuse the exact Structured OpenCV validators."""

    engine_id = KEYPOINT_GEOMETRY_ENGINE_ID
    version = KEYPOINT_GEOMETRY_ENGINE_VERSION

    def __init__(
        self,
        *,
        predictor: KeypointGeometryPredictor,
        line_thresholds: StructuredBoardLineThresholds = (DEFAULT_STRUCTURED_BOARD_LINE_THRESHOLDS),
        validation_thresholds: StructuredGeometryValidationThresholds = (
            DEFAULT_STRUCTURED_GEOMETRY_VALIDATION_THRESHOLDS
        ),
        line_refiner: BoardLineRefiner | None = None,
    ) -> None:
        self._predictor = predictor
        self._validation_thresholds = validation_thresholds
        self._refiner = line_refiner or BoardLineRefiner(
            thresholds=line_thresholds,
            validation_thresholds=validation_thresholds,
        )
        self.config_checksum_sha256 = hashlib.sha256(
            canonical_json_bytes(
                {
                    "adapterVersion": KEYPOINT_ONNX_ADAPTER_VERSION,
                    "engineVersion": self.version,
                    "lineRefinementConfigChecksumSha256": (self._refiner.config_checksum_sha256),
                    "modelChecksumSha256": predictor.artifact_sha256,
                    "modelVersion": KEYPOINT_GEOMETRY_MODEL_VERSION,
                    "validation": validation_thresholds.to_payload(),
                }
            )
        ).hexdigest()

    def detect(
        self,
        source: CanonicalSourceFrame,
        request: StructuredGeometryInitializationRequest,
    ) -> SourceGeometryResult:
        if (
            request.source_checksum_sha256 != source.source.source_checksum_sha256
            or request.normalized_pixel_checksum_sha256
            != source.source.normalized_pixel_checksum_sha256
            or request.canonical_width != source.source.width
            or request.canonical_height != source.source.height
        ):
            raise StructuredGeometryInitializationError(
                "IMAGE_KEYPOINT_GEOMETRY_SOURCE_MISMATCH",
                "Keypoint geometry request differs from the canonical source frame.",
            )
        prediction = self._predictor.predict(
            source,
            active_board_slots=request.active_board_slots,
        )
        expected_mask = tuple(index in request.active_board_slots for index in range(9))
        if (
            prediction.active_slot_mask != expected_mask
            or tuple(value.position_index for value in prediction.slots)
            != request.active_board_slots
            or prediction.model_checksum_sha256 != self._predictor.artifact_sha256
        ):
            raise StructuredGeometryInitializationError(
                "IMAGE_KEYPOINT_GEOMETRY_PREDICTION_SCOPE_INVALID",
                "Keypoint prediction does not match the attested source scope.",
            )
        initialization = self._initialization(request, prediction=prediction)
        return refine_initialized_source_geometry(
            source=source,
            request=request,
            initialization=initialization,
            engine_id=self.engine_id,
            engine_version=self.version,
            config_checksum_sha256=self.config_checksum_sha256,
            line_refiner=self._refiner,
            validation_thresholds=self._validation_thresholds,
            initialization_failure_reason=(BoardGeometryReasonCode.KEYPOINT_PREDICTION_INCOMPLETE),
        )

    def _initialization(
        self,
        request: StructuredGeometryInitializationRequest,
        *,
        prediction: KeypointGeometryPrediction,
    ) -> GlobalInitializationResult:
        active_slots = tuple(
            ActiveSlotInitialization(
                slot=slot,
                initial_quad=predicted.quad,
            )
            for slot, predicted in zip(
                request.attested_range.active_slots,
                prediction.slots,
                strict=True,
            )
            if predicted.quad is not None
        )
        complete = prediction.complete and len(active_slots) == len(request.active_board_slots)
        corner_confidences = tuple(
            confidence
            for predicted in prediction.slots
            for confidence in predicted.corner_confidences
        )
        metrics: tuple[tuple[str, bool | float | int | str], ...] = (
            ("inactiveFalsePositiveCount", prediction.inactive_false_positive_count),
            (
                "meanCornerConfidence",
                sum(corner_confidences) / len(corner_confidences),
            ),
            (
                "minimumActivePresenceConfidence",
                min(value.presence_confidence for value in prediction.slots),
            ),
            ("modelChecksumSha256", prediction.model_checksum_sha256),
        )
        reasons = tuple(
            sorted({reason for slot in prediction.slots for reason in slot.reason_codes})
        )
        if not complete and not reasons:
            reasons = ("keypoint_prediction_incomplete",)
        return GlobalInitializationResult(
            status=(
                GlobalInitializationStatus.INITIALIZED
                if complete
                else GlobalInitializationStatus.NEEDS_MANUAL_REVIEW
            ),
            method=GlobalInitializationMethod.KEYPOINT_HEATMAPS,
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
            slots=active_slots if complete else (),
            metrics=metrics,
            reason_codes=() if complete else reasons,
        )


class KeypointGeometryShadowRunner:
    """Evaluate a candidate without any API for choosing it as primary."""

    def __init__(self, engine: KeypointGeometryEngine) -> None:
        self._engine = engine

    def evaluate(
        self,
        *,
        primary: SourceGeometryResult,
        source: CanonicalSourceFrame,
        request: StructuredGeometryInitializationRequest,
    ) -> KeypointGeometryShadowEvaluation:
        candidate = self._engine.detect(source, request)
        if (
            candidate.source_checksum_sha256 != primary.source_checksum_sha256
            or candidate.normalized_pixel_checksum_sha256
            != primary.normalized_pixel_checksum_sha256
            or candidate.active_board_slots != primary.active_board_slots
        ):
            raise ValueError("Keypoint shadow candidate is outside the primary result scope.")
        return KeypointGeometryShadowEvaluation(
            primary_result_checksum_sha256=primary.result_checksum_sha256,
            candidate=candidate,
        )


__all__ = [
    "KEYPOINT_GEOMETRY_ENGINE_ID",
    "KEYPOINT_GEOMETRY_ENGINE_VERSION",
    "KeypointGeometryEngine",
    "KeypointGeometryPredictor",
    "KeypointGeometryShadowEvaluation",
    "KeypointGeometryShadowRunner",
]
