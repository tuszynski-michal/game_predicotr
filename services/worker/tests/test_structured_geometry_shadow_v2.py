from __future__ import annotations

import hashlib
from dataclasses import replace
from uuid import UUID

import cv2
import numpy as np
from game_predictor_api.domain.image_geometry_v2 import (
    ActiveBoardSlot,
    NormalizedSourceImage,
    SourcePoint,
    SourceQuad,
    canonical_json_bytes,
)
from game_predictor_worker.images.board_cell_geometry_contract import BoardCellTopology
from game_predictor_worker.images.normalization import (
    CANONICAL_SOURCE_LOADER_VERSION,
    CanonicalSourceFrame,
    rgb_pixel_checksum_sha256,
)
from game_predictor_worker.images.structured_geometry import (
    DEFAULT_STRUCTURED_GEOMETRY_CONFIG_V2,
    ActiveSlotInitialization,
    BoardGeometryDisposition,
    BoardGeometryEvidence,
    BoardGeometryResult,
    GeometryConfidenceComponents,
    GlobalInitializationMethod,
    GlobalInitializationResult,
    GlobalInitializationStatus,
    SourceGeometryResult,
    SourceGeometryStatus,
    evaluate_structured_geometry_shadow_v2,
    evaluate_structured_lattice_shadow_v3,
    structured_lattice_candidate_config_payload,
)


def _frame() -> CanonicalSourceFrame:
    rgb = np.full((300, 500, 3), 224, dtype=np.uint8)
    cv2.rectangle(rgb, (2, 2), (497, 297), (220, 0, 0), 8)
    for column in range(1, 5):
        cv2.line(rgb, (column * 100, 0), (column * 100, 299), (35, 35, 35), 3)
    for row in range(1, 3):
        cv2.line(rgb, (0, row * 100), (499, row * 100), (35, 35, 35), 3)
    for row in range(3):
        for column in range(5):
            cv2.circle(rgb, (column * 100 + 50, row * 100 + 50), 24, (15, 80, 210), -1)
    checksum = rgb_pixel_checksum_sha256(rgb)
    return CanonicalSourceFrame(
        source=NormalizedSourceImage(
            source_checksum_sha256="a" * 64,
            normalized_pixel_checksum_sha256=checksum,
            width=500,
            height=300,
            exif_orientation=None,
            normalization_adapter_version=CANONICAL_SOURCE_LOADER_VERSION,
        ),
        raw_width=500,
        raw_height=300,
        source_mode="RGB",
        orientation_action="none",
        rgb=rgb,
    )


def _quad() -> SourceQuad:
    return SourceQuad(
        corners=(
            SourcePoint(0.0, 0.0),
            SourcePoint(499.0, 0.0),
            SourcePoint(499.0, 299.0),
            SourcePoint(0.0, 299.0),
        )
    )


def _upstream(frame: CanonicalSourceFrame) -> SourceGeometryResult:
    slot = ActiveBoardSlot(range_start=1, range_end=1, position_index=0, sequence_number=1)
    quad = _quad()
    components = GeometryConfidenceComponents(
        global_registration_score=0.95,
        line_coverage_score=0.90,
        intersection_coverage_score=1.0,
        spacing_regularity_score=0.95,
        reprojection_score=0.95,
        border_evidence_score=0.90,
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
    initialization = GlobalInitializationResult(
        status=GlobalInitializationStatus.INITIALIZED,
        method=GlobalInitializationMethod.VERIFIED_PROFILE_ORB_RANSAC,
        engine_id="structured_opencv_v1",
        engine_version="structured-opencv-global-initialization-v1",
        config_checksum_sha256="b" * 64,
        source_checksum_sha256=frame.source.source_checksum_sha256,
        normalized_pixel_checksum_sha256=frame.source.normalized_pixel_checksum_sha256,
        canonical_width=500,
        canonical_height=300,
        topology_rows=3,
        topology_columns=5,
        topology_rules_version_id=UUID("00000000-0000-0000-0000-000000000329"),
        active_board_slots=(0,),
        homography=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        slots=(ActiveSlotInitialization(slot=slot, initial_quad=quad),),
        metrics=(("inlierRatio", 0.5), ("p95ReprojectionError", 0.5)),
        reason_codes=(),
    )
    board = BoardGeometryResult(
        slot=slot,
        disposition=BoardGeometryDisposition.AUTOMATIC,
        initial_quad=quad,
        final_quad=quad,
        ideal_to_source_homography=(
            (99.8, 0.0, 0.0),
            (0.0, 99.66666667, 0.0),
            (0.0, 0.0, 1.0),
        ),
        confidence=components.total,
        confidence_components=components,
        evidence=evidence,
        lines=(),
        reason_codes=(),
    )
    return SourceGeometryResult(
        status=SourceGeometryStatus.READY,
        engine_id="structured_opencv_v1",
        engine_version="structured-opencv-independent-board-refinement-v1",
        config_checksum_sha256="c" * 64,
        source_checksum_sha256=frame.source.source_checksum_sha256,
        normalized_pixel_checksum_sha256=frame.source.normalized_pixel_checksum_sha256,
        canonical_width=500,
        canonical_height=300,
        topology_rows=3,
        topology_columns=5,
        topology_rules_version_id=initialization.topology_rules_version_id,
        active_board_slots=(0,),
        global_initialization=initialization,
        boards=(board,),
        reason_codes=(),
    )


def test_shadow_v2_is_deterministic_checksum_bound_and_measurement_only() -> None:
    frame = _frame()
    upstream = _upstream(frame)

    first = evaluate_structured_geometry_shadow_v2(
        frame,
        upstream,
        config=DEFAULT_STRUCTURED_GEOMETRY_CONFIG_V2,
        game_id=None,
    )
    second = evaluate_structured_geometry_shadow_v2(
        frame,
        upstream,
        config=DEFAULT_STRUCTURED_GEOMETRY_CONFIG_V2,
        game_id=None,
    )
    payload = first.to_payload()

    assert payload == second.to_payload()
    assert payload["candidateRole"] == "measurement_only"
    assert payload["activationAllowed"] is False
    assert payload["geometryOriginPolicy"] == "reuse_v1_final_quad_without_authority"
    assert payload["upstreamResultChecksumSha256"] == upstream.result_checksum_sha256
    assert payload["configChecksumSha256"] == DEFAULT_STRUCTURED_GEOMETRY_CONFIG_V2.checksum_sha256
    assert len(first.boards) == 1
    assert first.boards[0].evaluation_status == "evaluated"
    assert first.boards[0].signal_probe is not None
    assert first.boards[0].signal_probe.probe_coordinate_source == "structured_v1_final_quad"
    assert first.boards[0].evidence is not None
    assert first.boards[0].evidence.reprojection_cell_diagonal_fraction is not None


def test_shadow_v3_is_deterministic_checksum_bound_and_measurement_only() -> None:
    frame = _frame()
    upstream = _upstream(frame)
    config = structured_lattice_candidate_config_payload()
    config_checksum = hashlib.sha256(canonical_json_bytes(config)).hexdigest()
    topology = BoardCellTopology(rows=3, columns=5)

    first = evaluate_structured_lattice_shadow_v3(
        frame,
        upstream,
        config_checksum_sha256=config_checksum,
        topology=topology,
    )
    second = evaluate_structured_lattice_shadow_v3(
        frame,
        upstream,
        config_checksum_sha256=config_checksum,
        topology=topology,
    )
    payload = first.to_payload()

    assert payload == second.to_payload()
    assert payload["candidateRole"] == "measurement_only"
    assert payload["activationAllowed"] is False
    assert payload["geometryOriginPolicy"] == (
        "frame_conditioned_symbol_lattice_without_crop_authority"
    )
    assert payload["upstreamResultChecksumSha256"] == upstream.result_checksum_sha256
    assert payload["configChecksumSha256"] == config_checksum
    assert len(payload["boards"]) == 1


def test_source_geometry_schema_v1_keeps_the_legacy_board_payload() -> None:
    upstream = _upstream(_frame())
    legacy_board = upstream.boards[0]
    quad = legacy_board.final_quad
    assert quad is not None
    role_annotated = replace(
        legacy_board,
        analysis_quad=quad,
        board_frame_quad=quad,
        symbol_grid_quad=quad,
        local_lattice_status="estimated",
        local_lattice_version="ignored-by-schema-v1",
    )
    schema_v1_with_roles = replace(upstream, boards=(role_annotated,))
    board = schema_v1_with_roles.to_payload()["boards"][0]

    assert schema_v1_with_roles.result_checksum_sha256 == upstream.result_checksum_sha256
    assert "analysisQuad" not in board
    assert "boardFrameQuad" not in board
    assert "symbolGridQuad" not in board
    assert "localLatticeStatus" not in board
    assert "localLatticeVersion" not in board


def test_source_geometry_schema_v2_exposes_explicit_geometry_roles() -> None:
    upstream = _upstream(_frame())
    legacy_board = upstream.boards[0]
    quad = legacy_board.final_quad
    assert quad is not None
    board = replace(
        legacy_board,
        analysis_quad=quad,
        board_frame_quad=quad,
        symbol_grid_quad=quad,
        local_lattice_status="estimated",
        local_lattice_version="board-cell-geometry-v19-multi-point-source-direct-v1",
    )
    role_aware = replace(upstream, boards=(board,), schema_version=2)

    payload = role_aware.to_payload()["boards"][0]

    assert payload["analysisQuad"] == quad.to_dict()
    assert payload["boardFrameQuad"] == quad.to_dict()
    assert payload["symbolGridQuad"] == payload["finalQuad"]
    assert payload["localLatticeStatus"] == "estimated"


def test_role_aware_geometry_rejects_a_different_final_quad_alias() -> None:
    upstream = _upstream(_frame())
    legacy_board = upstream.boards[0]
    quad = legacy_board.final_quad
    assert quad is not None
    shifted = SourceQuad(
        corners=(
            SourcePoint(1.0, 0.0),
            SourcePoint(500.0, 0.0),
            SourcePoint(500.0, 299.0),
            SourcePoint(1.0, 299.0),
        )
    )

    try:
        replace(
            legacy_board,
            analysis_quad=quad,
            symbol_grid_quad=shifted,
            local_lattice_status="estimated",
            local_lattice_version="test-v1",
        )
    except ValueError as error:
        assert str(error) == "finalQuad must remain an alias of symbolGridQuad."
    else:
        raise AssertionError("Mismatched geometry aliases must be rejected.")
