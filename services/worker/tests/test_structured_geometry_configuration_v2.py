from __future__ import annotations

import hashlib
from dataclasses import replace
from uuid import UUID

import pytest
from game_predictor_api.domain.image_geometry_v2 import canonical_json_bytes
from game_predictor_worker.images.structured_geometry import (
    DEFAULT_STRUCTURED_GEOMETRY_CONFIG_V2,
    AdaptiveAnalysisPolicyV2,
    GameGeometryEvidenceProfileV2,
    GeometryCandidateDisposition,
    GeometryConfigV2Error,
    GeometryEvidenceReasonV2,
    GeometryEvidenceThresholdsV2,
    StructuredGeometryConfigV2,
    StructuredGeometryEvidenceV2,
    evaluate_geometry_candidate_v2,
)
from game_predictor_worker.images.structured_geometry.confidence import (
    BoardGeometryDisposition,
    BoardGeometryEvidence,
    GeometryConfidenceComponents,
    StructuredGeometryValidationThresholds,
    evaluate_geometry_confidence,
)


def _evidence(**changes: object) -> StructuredGeometryEvidenceV2:
    values: dict[str, object] = {
        "homography_available": True,
        "padded_cell_source_support_complete": True,
        "initialization_alignment_valid": True,
        "slot_order_valid": True,
        "overlap_valid": True,
        "outer_frame_score": 0.95,
        "known_layout_score": 0.95,
        "lsd_grid_score": 0.90,
        "hough_grid_score": 0.90,
        "vertical_gradient_profile_score": 0.90,
        "horizontal_gradient_profile_score": 0.90,
        "grid_regularity_score": 0.95,
        "symbol_center_support_score": 0.80,
        "reprojection_cell_diagonal_fraction": 0.01,
    }
    values.update(changes)
    return StructuredGeometryEvidenceV2(**values)  # type: ignore[arg-type]


def test_default_config_is_deterministic_and_cannot_authorize_activation() -> None:
    first = StructuredGeometryConfigV2()
    second = StructuredGeometryConfigV2()

    assert first.to_payload() == second.to_payload()
    assert first.checksum_sha256 == second.checksum_sha256
    assert (
        first.checksum_sha256
        == hashlib.sha256(canonical_json_bytes(first.to_payload())).hexdigest()
    )
    assert len(first.checksum_sha256) == 64
    assert first.to_payload()["maturity"] == "experimental_measurement_only"
    assert first.to_payload()["activationAllowed"] is False
    assert first.to_payload()["evidencePolicy"]["lsdIsExclusiveGate"] is False  # type: ignore[index]
    with pytest.raises(GeometryConfigV2Error) as error:
        StructuredGeometryConfigV2(activation_allowed=True)
    assert error.value.code == "IMAGE_STRUCTURED_GEOMETRY_CONFIG_V2_NOT_EXPERIMENTAL"


def test_analysis_scale_is_adaptive_and_preserves_local_roi_when_possible() -> None:
    policy = AdaptiveAnalysisPolicyV2()

    page_limited = policy.resolve_scale(
        source_width=4000,
        source_height=3000,
        smallest_roi_short_edge_px=1000,
    )
    roi_limited = policy.resolve_scale(
        source_width=4000,
        source_height=3000,
        smallest_roi_short_edge_px=300,
    )
    no_upscale = policy.resolve_scale(
        source_width=4000,
        source_height=3000,
        smallest_roi_short_edge_px=100,
    )

    assert page_limited == 0.4
    assert roi_limited == 0.8
    assert roi_limited * 300 >= policy.minimum_local_roi_short_edge_px
    assert no_upscale == 1.0


def test_game_profile_is_explicit_and_changes_the_config_checksum() -> None:
    game_id = UUID("00000000-0000-0000-0000-000000000328")
    profile = GameGeometryEvidenceProfileV2(
        game_id=game_id,
        thresholds=replace(
            GeometryEvidenceThresholdsV2(),
            strong_outer_frame=0.76,
        ),
    )
    configured = StructuredGeometryConfigV2(game_profiles=(profile,))

    assert configured.thresholds_for(game_id) == profile.thresholds
    assert configured.thresholds_for(None) == configured.thresholds
    assert configured.checksum_sha256 != DEFAULT_STRUCTURED_GEOMETRY_CONFIG_V2.checksum_sha256
    with pytest.raises(GeometryConfigV2Error):
        StructuredGeometryConfigV2(game_profiles=(profile, profile))


def test_missing_lsd_is_not_an_exclusive_failure_with_three_independent_core_signals() -> None:
    decision = evaluate_geometry_candidate_v2(
        _evidence(
            lsd_grid_score=0.0,
            hough_grid_score=0.40,
            vertical_gradient_profile_score=0.95,
            horizontal_gradient_profile_score=0.95,
        )
    )

    assert decision.disposition is GeometryCandidateDisposition.AUTOMATIC_CANDIDATE
    assert decision.reason_codes == ()
    assert {"outer_frame", "known_layout", "grid_regularity"}.issubset(
        decision.strong_evidence_families
    )


def test_lsd_alone_cannot_create_an_automatic_candidate() -> None:
    decision = evaluate_geometry_candidate_v2(
        _evidence(
            outer_frame_score=0.10,
            known_layout_score=0.10,
            lsd_grid_score=1.0,
            hough_grid_score=0.10,
            vertical_gradient_profile_score=0.10,
            horizontal_gradient_profile_score=0.10,
            grid_regularity_score=0.10,
            symbol_center_support_score=0.10,
        )
    )

    assert decision.disposition is GeometryCandidateDisposition.NEEDS_MANUAL_CORRECTION
    assert decision.reason_codes == (GeometryEvidenceReasonV2.INDEPENDENT_EVIDENCE_INSUFFICIENT,)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"homography_available": False}, GeometryEvidenceReasonV2.HOMOGRAPHY_UNAVAILABLE),
        (
            {"padded_cell_source_support_complete": False},
            GeometryEvidenceReasonV2.SOURCE_SUPPORT_INCOMPLETE,
        ),
        (
            {"initialization_alignment_valid": False},
            GeometryEvidenceReasonV2.INITIALIZATION_ALIGNMENT_FAILED,
        ),
        ({"slot_order_valid": False}, GeometryEvidenceReasonV2.SLOT_ORDER_INVALID),
        ({"overlap_valid": False}, GeometryEvidenceReasonV2.BOARD_OVERLAP_DETECTED),
    ],
)
def test_safety_invariants_always_fail_closed(
    change: dict[str, object],
    reason: GeometryEvidenceReasonV2,
) -> None:
    decision = evaluate_geometry_candidate_v2(_evidence(**change))

    assert decision.disposition is GeometryCandidateDisposition.NEEDS_MANUAL_CORRECTION
    assert reason in decision.reason_codes


def test_reprojection_is_normalized_to_cell_diagonal() -> None:
    accepted = evaluate_geometry_candidate_v2(_evidence(reprojection_cell_diagonal_fraction=0.039))
    rejected = evaluate_geometry_candidate_v2(_evidence(reprojection_cell_diagonal_fraction=0.041))

    assert accepted.disposition is not GeometryCandidateDisposition.NEEDS_MANUAL_CORRECTION
    assert rejected.reason_codes == (GeometryEvidenceReasonV2.REPROJECTION_ERROR_EXCEEDED,)


def test_production_v1_policy_remains_strict_and_unchanged() -> None:
    thresholds = StructuredGeometryValidationThresholds()
    evidence = BoardGeometryEvidence(
        observed_vertical_line_indexes=(0, 1, 2, 3),
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
    components = GeometryConfidenceComponents(
        global_registration_score=1.0,
        line_coverage_score=1.0,
        intersection_coverage_score=1.0,
        spacing_regularity_score=1.0,
        reprojection_score=1.0,
        border_evidence_score=1.0,
        slot_order_score=1.0,
        source_support_score=1.0,
    )

    decision = evaluate_geometry_confidence(
        evidence=evidence,
        components=components,
        thresholds=thresholds,
    )

    assert thresholds.minimum_vertical_lines == 5
    assert thresholds.maximum_half_scale_p95_reprojection_error == 2.5
    assert decision.disposition is BoardGeometryDisposition.NEEDS_MANUAL_CORRECTION
