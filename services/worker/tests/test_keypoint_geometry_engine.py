from __future__ import annotations

from typing import cast
from uuid import UUID

import numpy as np
from game_predictor_api.domain.board_topology import LEGACY_IMAGE_BOARD_TOPOLOGY
from game_predictor_api.domain.image_geometry_v2 import (
    AttestedSequenceRange,
    NormalizedSourceImage,
    SourcePoint,
    SourceQuad,
)
from game_predictor_worker.images.keypoint_geometry import (
    KeypointGeometryEngine,
    KeypointGeometryPrediction,
    KeypointGeometryShadowRunner,
    KeypointSlotPrediction,
)
from game_predictor_worker.images.normalization import (
    CanonicalSourceFrame,
    rgb_pixel_checksum_sha256,
)
from game_predictor_worker.images.structured_geometry import (
    BoardGeometryDisposition,
    BoardGeometryEvidence,
    BoardGeometryReasonCode,
    BoardLineRefinementResult,
    BoardLineRefiner,
    GeometryConfidenceComponents,
    SourceGeometryStatus,
    StructuredGeometryInitializationRequest,
)

_RULES_VERSION_ID = UUID("00000000-0000-0000-0000-000000000319")


def _quad() -> SourceQuad:
    return SourceQuad(
        corners=(
            SourcePoint(20, 20),
            SourcePoint(100, 20),
            SourcePoint(100, 80),
            SourcePoint(20, 80),
        )
    )


def _frame() -> CanonicalSourceFrame:
    rgb = np.zeros((100, 120, 3), dtype=np.uint8)
    return CanonicalSourceFrame(
        source=NormalizedSourceImage(
            source_checksum_sha256="a" * 64,
            normalized_pixel_checksum_sha256=rgb_pixel_checksum_sha256(rgb),
            width=120,
            height=100,
            exif_orientation=1,
            normalization_adapter_version="test-keypoint-source-v1",
        ),
        raw_width=120,
        raw_height=100,
        source_mode="RGB",
        orientation_action="identity",
        rgb=rgb,
    )


def _request(frame: CanonicalSourceFrame) -> StructuredGeometryInitializationRequest:
    return StructuredGeometryInitializationRequest.for_frame(
        frame,
        topology=LEGACY_IMAGE_BOARD_TOPOLOGY,
        topology_rules_version_id=_RULES_VERSION_ID,
        attested_range=AttestedSequenceRange(start=1, end=1),
    )


class _Predictor:
    artifact_sha256 = "b" * 64

    def __init__(self, *, complete: bool) -> None:
        self.complete = complete

    def predict(
        self,
        source: CanonicalSourceFrame,
        *,
        active_board_slots: tuple[int, ...],
    ) -> KeypointGeometryPrediction:
        del source
        return KeypointGeometryPrediction(
            slots=(
                KeypointSlotPrediction(
                    position_index=0,
                    quad=_quad() if self.complete else None,
                    presence_confidence=0.99 if self.complete else 0.1,
                    corner_confidences=(0.99, 0.99, 0.99, 0.99),
                    reason_codes=() if self.complete else ("keypoint_active_slot_missing",),
                ),
            ),
            active_slot_mask=tuple(index == 0 for index in range(9)),
            inactive_false_positive_count=0,
            model_checksum_sha256=self.artifact_sha256,
        )


class _PassThroughRefiner:
    config_checksum_sha256 = "c" * 64

    def refine(
        self,
        rgb: np.ndarray,
        *,
        initial_quad: SourceQuad,
        topology: object,
        global_registration_score: float,
    ) -> BoardLineRefinementResult:
        del rgb, topology
        components = GeometryConfidenceComponents(
            global_registration_score=global_registration_score,
            line_coverage_score=1.0,
            intersection_coverage_score=1.0,
            spacing_regularity_score=1.0,
            reprojection_score=1.0,
            border_evidence_score=1.0,
            slot_order_score=1.0,
            source_support_score=1.0,
        )
        evidence = BoardGeometryEvidence(
            observed_vertical_line_indexes=(0, 1, 2, 3, 4, 5),
            observed_horizontal_line_indexes=(0, 1, 2, 3),
            inferred_vertical_line_indexes=(),
            inferred_horizontal_line_indexes=(),
            external_boundaries_supported=4,
            supported_intersection_count=24,
            inlier_intersection_count=24,
            half_scale_p95_reprojection_error=0.5,
            homography_available=True,
            padded_cell_source_support_complete=True,
            initialization_alignment_valid=True,
        )
        return BoardLineRefinementResult(
            initial_quad=initial_quad,
            final_quad=initial_quad,
            ideal_to_source_homography=(
                (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                (0.0, 0.0, 1.0),
            ),
            evidence=evidence,
            confidence_components=components,
            lines=(),
            intrinsic_reason_codes=(),
            diagnostics=(),
        )


def _engine(*, complete: bool) -> KeypointGeometryEngine:
    return KeypointGeometryEngine(
        predictor=_Predictor(complete=complete),
        line_refiner=cast("BoardLineRefiner", _PassThroughRefiner()),
    )


def test_keypoint_initialization_uses_shared_hard_gate_result() -> None:
    frame = _frame()

    result = _engine(complete=True).detect(frame, _request(frame))

    assert result.status is SourceGeometryStatus.READY
    assert result.boards[0].disposition is BoardGeometryDisposition.AUTOMATIC
    assert result.boards[0].final_quad == _quad()
    assert result.global_initialization.homography is None
    assert result.global_initialization.method.value == "keypoint_heatmaps"


def test_incomplete_keypoint_mask_fails_closed_before_refinement() -> None:
    frame = _frame()

    result = _engine(complete=False).detect(frame, _request(frame))

    assert result.status is SourceGeometryStatus.NEEDS_MANUAL_CORRECTION
    assert result.boards[0].final_quad is None
    assert result.boards[0].reason_codes == (
        BoardGeometryReasonCode.KEYPOINT_PREDICTION_INCOMPLETE,
    )


def test_shadow_runner_never_promotes_or_mutates_primary() -> None:
    frame = _frame()
    engine = _engine(complete=True)
    primary = engine.detect(frame, _request(frame))
    checksum_before = primary.result_checksum_sha256

    comparison = KeypointGeometryShadowRunner(engine).evaluate(
        primary=primary,
        source=frame,
        request=_request(frame),
    )

    assert comparison.can_replace_primary is False
    assert comparison.rollout_mode == "shadow_only"
    assert comparison.primary_result_checksum_sha256 == checksum_before
    assert primary.result_checksum_sha256 == checksum_before
