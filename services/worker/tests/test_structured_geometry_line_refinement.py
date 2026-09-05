from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import cast

import cv2
import numpy as np
import pytest
from game_predictor_api.domain.board_topology import (
    LEGACY_IMAGE_BOARD_TOPOLOGY,
    BoardTopology,
)
from game_predictor_api.domain.image_geometry_v2 import SourcePoint, SourceQuad
from game_predictor_worker.images.structured_geometry import (
    BoardGeometryDisposition,
    BoardGeometryEvidence,
    BoardGeometryReasonCode,
    BoardLineRefinementResult,
    BoardLineRefiner,
    GeometryConfidenceComponents,
    evaluate_geometry_confidence,
)
from game_predictor_worker.images.structured_geometry.geometry_engine import _cross_slot_violations

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_FALSE_SUCCESS_IMAGE = _REPOSITORY_ROOT / "examples" / "imgs" / "5983122166590934324.jpg"


def _quad(points: tuple[tuple[float, float], ...]) -> SourceQuad:
    corners = cast(
        tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint],
        tuple(SourcePoint(x=x, y=y) for x, y in points),
    )
    return SourceQuad(corners=corners)


def _quad_array(quad: SourceQuad) -> np.ndarray:
    return np.asarray([[point.x, point.y] for point in quad.corners], dtype=np.float32)


def _render_board(
    *,
    missing_vertical: set[int] | None = None,
    missing_horizontal: set[int] | None = None,
    glare: bool = False,
    occlusion: bool = False,
) -> np.ndarray:
    width, height = 500, 300
    image = np.full((height, width, 3), 26, dtype=np.uint8)
    missing_vertical = missing_vertical or set()
    missing_horizontal = missing_horizontal or set()
    cv2.rectangle(image, (3, 3), (width - 4, height - 4), (230, 28, 24), 8)
    for column in range(1, 5):
        if column not in missing_vertical:
            x = round(column * (width - 1) / 5)
            cv2.line(image, (x, 5), (x, height - 6), (214, 214, 214), 4)
    for row in range(1, 3):
        if row not in missing_horizontal:
            y = round(row * (height - 1) / 3)
            cv2.line(image, (5, y), (width - 6, y), (214, 214, 214), 4)
    for row in range(3):
        for column in range(5):
            centre = (
                round((column + 0.5) * width / 5),
                round((row + 0.5) * height / 3),
            )
            cv2.circle(image, centre, 24, (45 + column * 18, 110 + row * 25, 190), 4)
    if glare:
        overlay = image.copy()
        cv2.ellipse(overlay, (305, 72), (120, 34), -8, 0, 360, (250, 250, 250), -1)
        image = cv2.addWeighted(overlay, 0.58, image, 0.42, 0)
    if occlusion:
        hand = np.asarray(
            [[245, 0], [499, 0], [499, 299], [286, 299], [252, 205]],
            dtype=np.int32,
        )
        cv2.fillConvexPoly(image, hand, (75, 58, 46))
    return image


def _project_board(
    board: np.ndarray,
    *,
    target_quad: SourceQuad,
    canvas_size: tuple[int, int] = (720, 560),
) -> np.ndarray:
    canvas_width, canvas_height = canvas_size
    source_height, source_width = board.shape[:2]
    transform = cv2.getPerspectiveTransform(
        np.asarray(
            [
                [0, 0],
                [source_width - 1, 0],
                [source_width - 1, source_height - 1],
                [0, source_height - 1],
            ],
            dtype=np.float32,
        ),
        _quad_array(target_quad),
    )
    projected = cv2.warpPerspective(board, transform, (canvas_width, canvas_height))
    mask = cv2.warpPerspective(
        np.full((source_height, source_width), 255, dtype=np.uint8),
        transform,
        (canvas_width, canvas_height),
    )
    canvas = np.full((canvas_height, canvas_width, 3), 12, dtype=np.uint8)
    canvas[mask > 0] = projected[mask > 0]
    return canvas


def _confidence_components(**changes: float) -> GeometryConfidenceComponents:
    values = {
        "global_registration_score": 0.95,
        "line_coverage_score": 0.95,
        "intersection_coverage_score": 1.0,
        "spacing_regularity_score": 0.95,
        "reprojection_score": 0.95,
        "border_evidence_score": 0.95,
        "slot_order_score": 1.0,
        "source_support_score": 1.0,
    }
    values.update(changes)
    return GeometryConfidenceComponents(**values)


def _complete_evidence() -> BoardGeometryEvidence:
    return BoardGeometryEvidence(
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


def _refinement(initial: SourceQuad, final: SourceQuad) -> BoardLineRefinementResult:
    return BoardLineRefinementResult(
        initial_quad=initial,
        final_quad=final,
        ideal_to_source_homography=(
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        ),
        evidence=_complete_evidence(),
        confidence_components=_confidence_components(),
        lines=(),
        intrinsic_reason_codes=(),
        diagnostics=(),
    )


def test_clean_perspective_board_refines_six_by_four_lines_independently() -> None:
    target = _quad(((82, 96), (625, 58), (653, 454), (54, 486)))
    initial = _quad(((78, 91), (631, 61), (648, 459), (58, 480)))
    source = _project_board(_render_board(), target_quad=target)

    result = BoardLineRefiner().refine(
        source,
        initial_quad=initial,
        topology=LEGACY_IMAGE_BOARD_TOPOLOGY,
        global_registration_score=0.98,
    )

    assert result.final_quad is not None
    assert result.ideal_to_source_homography is not None
    assert result.evidence.observed_vertical_line_indexes == (0, 1, 2, 3, 4, 5)
    assert result.evidence.observed_horizontal_line_indexes == (0, 1, 2, 3)
    assert result.evidence.supported_intersection_count == 24
    assert result.evidence.inlier_intersection_count >= 18
    assert result.evidence.padded_cell_source_support_complete is True
    assert result.evidence.initialization_alignment_valid is True
    assert len(result.lines) == 10
    decision = evaluate_geometry_confidence(
        evidence=result.evidence,
        components=result.confidence_components,
    )
    assert decision.disposition is BoardGeometryDisposition.AUTOMATIC
    assert (
        result.to_payload()
        == BoardLineRefiner()
        .refine(
            source,
            initial_quad=initial,
            topology=LEGACY_IMAGE_BOARD_TOPOLOGY,
            global_registration_score=0.98,
        )
        .to_payload()
    )


def test_glare_does_not_force_a_rectangle_in_source_coordinates() -> None:
    target = _quad(((72, 124), (622, 62), (675, 432), (44, 500)))
    source = _project_board(_render_board(glare=True), target_quad=target)

    result = BoardLineRefiner().refine(
        source,
        initial_quad=target,
        topology=LEGACY_IMAGE_BOARD_TOPOLOGY,
        global_registration_score=0.96,
    )

    assert result.final_quad is not None
    corners = _quad_array(result.final_quad)
    top = corners[1] - corners[0]
    left = corners[3] - corners[0]
    assert abs(float(np.dot(top, left))) > 1000
    assert result.evidence.supported_intersection_count >= 18
    decision = evaluate_geometry_confidence(
        evidence=result.evidence,
        components=result.confidence_components,
    )
    assert decision.disposition is not BoardGeometryDisposition.NEEDS_MANUAL_CORRECTION


def test_one_missing_internal_line_is_inferred_only_with_complete_outer_boundaries() -> None:
    target = _quad(((82, 96), (625, 58), (653, 454), (54, 486)))
    source = _project_board(_render_board(missing_vertical={2}), target_quad=target)

    result = BoardLineRefiner().refine(
        source,
        initial_quad=target,
        topology=LEGACY_IMAGE_BOARD_TOPOLOGY,
        global_registration_score=0.98,
    )

    assert result.final_quad is not None
    assert result.evidence.observed_vertical_line_indexes == (0, 1, 3, 4, 5)
    assert result.evidence.inferred_vertical_line_indexes == (2,)
    assert result.evidence.external_boundaries_supported == 4
    assert result.evidence.supported_intersection_count == 20
    assert sum(line.inferred for line in result.lines) == 1


@pytest.mark.parametrize(
    ("board", "expected_reason"),
    [
        (
            _render_board(missing_vertical={1, 2, 3}, missing_horizontal={1}),
            BoardGeometryReasonCode.VERTICAL_LINE_COVERAGE_INSUFFICIENT,
        ),
        (
            _render_board(occlusion=True),
            BoardGeometryReasonCode.VERTICAL_LINE_COVERAGE_INSUFFICIENT,
        ),
    ],
)
def test_incomplete_or_occluded_evidence_fails_closed(
    board: np.ndarray,
    expected_reason: BoardGeometryReasonCode,
) -> None:
    target = _quad(((90, 90), (630, 72), (648, 448), (70, 470)))
    source = _project_board(board, target_quad=target)
    refinement = BoardLineRefiner().refine(
        source,
        initial_quad=target,
        topology=LEGACY_IMAGE_BOARD_TOPOLOGY,
        global_registration_score=0.95,
    )

    decision = evaluate_geometry_confidence(
        evidence=refinement.evidence,
        components=refinement.confidence_components,
    )

    assert decision.disposition is BoardGeometryDisposition.NEEDS_MANUAL_CORRECTION
    assert expected_reason in decision.reason_codes


def test_hard_gates_override_high_classifier_independent_confidence() -> None:
    evidence = replace(
        _complete_evidence(),
        observed_vertical_line_indexes=(0, 1, 2, 3),
        supported_intersection_count=16,
        inlier_intersection_count=16,
    )

    decision = evaluate_geometry_confidence(
        evidence=evidence,
        components=_confidence_components(),
    )

    assert decision.disposition is BoardGeometryDisposition.NEEDS_MANUAL_CORRECTION
    assert decision.reason_codes == (
        BoardGeometryReasonCode.VERTICAL_LINE_COVERAGE_INSUFFICIENT,
        BoardGeometryReasonCode.INTERSECTION_COVERAGE_INSUFFICIENT,
    )


def test_slot_order_and_overlap_are_hard_failures() -> None:
    order_decision = evaluate_geometry_confidence(
        evidence=replace(_complete_evidence(), slot_order_valid=False),
        components=_confidence_components(),
    )
    overlap_decision = evaluate_geometry_confidence(
        evidence=replace(_complete_evidence(), overlap_valid=False),
        components=_confidence_components(),
    )

    assert order_decision.disposition is BoardGeometryDisposition.NEEDS_MANUAL_CORRECTION
    assert order_decision.reason_codes == (BoardGeometryReasonCode.SLOT_ORDER_INVALID,)
    assert overlap_decision.disposition is BoardGeometryDisposition.NEEDS_MANUAL_CORRECTION
    assert overlap_decision.reason_codes == (BoardGeometryReasonCode.BOARD_OVERLAP_DETECTED,)


def test_cross_slot_guard_detects_swapped_row_major_slots_and_overlap() -> None:
    first_initial = _quad(((20, 20), (120, 20), (120, 90), (20, 90)))
    second_initial = _quad(((160, 20), (260, 20), (260, 90), (160, 90)))
    swapped = (
        _refinement(first_initial, second_initial),
        _refinement(second_initial, first_initial),
    )
    overlapping = (
        _refinement(first_initial, first_initial),
        _refinement(second_initial, _quad(((111, 20), (211, 20), (211, 90), (111, 90)))),
    )

    swapped_order, swapped_overlap = _cross_slot_violations(
        swapped,
        maximum_overlap_fraction=0.01,
    )
    overlap_order, overlap_slots = _cross_slot_violations(
        overlapping,
        maximum_overlap_fraction=0.01,
    )

    assert swapped_order == {0, 1}
    assert swapped_overlap == set()
    assert overlap_order == set()
    assert overlap_slots == {0, 1}


def test_non_legacy_topology_is_explicitly_rejected_by_v1_refiner() -> None:
    target = _quad(((90, 90), (630, 72), (648, 448), (70, 470)))
    source = _project_board(_render_board(), target_quad=target)

    result = BoardLineRefiner().refine(
        source,
        initial_quad=target,
        topology=BoardTopology(rows=4, columns=4),
        global_registration_score=0.95,
    )

    assert result.final_quad is None
    assert result.intrinsic_reason_codes == (BoardGeometryReasonCode.TOPOLOGY_UNSUPPORTED,)


@pytest.mark.skipif(not _FALSE_SUCCESS_IMAGE.exists(), reason="Local historical corpus unavailable")
def test_historical_false_success_requires_complete_local_line_evidence() -> None:
    source_bgr = cv2.imread(str(_FALSE_SUCCESS_IMAGE), cv2.IMREAD_COLOR)
    assert source_bgr is not None
    source = cv2.cvtColor(source_bgr, cv2.COLOR_BGR2RGB)
    height, width = source.shape[:2]
    deliberately_unrelated_roi = _quad(
        (
            (width * 0.05, height * 0.05),
            (width * 0.28, height * 0.05),
            (width * 0.28, height * 0.24),
            (width * 0.05, height * 0.24),
        )
    )

    refinement = BoardLineRefiner().refine(
        source,
        initial_quad=deliberately_unrelated_roi,
        topology=LEGACY_IMAGE_BOARD_TOPOLOGY,
        global_registration_score=1.0,
    )
    decision = evaluate_geometry_confidence(
        evidence=refinement.evidence,
        components=refinement.confidence_components,
    )

    assert decision.disposition is BoardGeometryDisposition.NEEDS_MANUAL_CORRECTION
    assert decision.reason_codes
