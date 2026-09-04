from __future__ import annotations

from dataclasses import replace

import cv2
import numpy as np
import pytest
from game_predictor_api.domain.image_geometry_v2 import SourcePoint, SourceQuad
from game_predictor_worker.images.board_cell_geometry_contract import BoardCellTopology
from game_predictor_worker.images.board_cell_geometry_estimator import (
    estimate_board_cell_geometry,
)
from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.structured_geometry import (
    LATTICE_CONTENT_SAFETY_VERSION,
    STRUCTURED_LATTICE_REFINEMENT_V3_VERSION,
    StructuredLatticeRefinementError,
    evaluate_lattice_content_safety,
    refine_structured_symbol_lattice_v3,
)


def _board(*, omit_last_column: bool = False) -> np.ndarray:
    value = np.full((300, 500, 3), (22, 11, 19), dtype=np.uint8)
    for row, y in enumerate((50, 150, 250)):
        for column, x in enumerate((50, 150, 250, 350, 450)):
            if omit_last_column and column == 4:
                continue
            cv2.circle(
                value,
                (x, y),
                24,
                (245, 205 - row * 20, 40 + column * 20),
                -1,
                cv2.LINE_AA,
            )
    return value


def _source(board: np.ndarray) -> tuple[np.ndarray, SourceQuad]:
    source = np.full((700, 900, 3), (8, 8, 12), dtype=np.uint8)
    canonical = np.asarray(((0, 0), (499, 0), (499, 299), (0, 299)), dtype=np.float32)
    target = np.asarray(((108, 82), (788, 116), (746, 610), (142, 574)), dtype=np.float32)
    transform = cv2.getPerspectiveTransform(canonical, target)
    warped = cv2.warpPerspective(board, transform, (900, 700))
    support = cv2.warpPerspective(np.full((300, 500), 255, np.uint8), transform, (900, 700))
    source[support > 0] = warped[support > 0]
    quad = SourceQuad(corners=tuple(SourcePoint(float(x), float(y)) for x, y in target))  # type: ignore[arg-type]
    return source, quad


def _detector_quad(quad: SourceQuad) -> tuple[Point, Point, Point, Point]:
    return tuple(Point(point.x, point.y) for point in quad.corners)  # type: ignore[return-value]


def test_v3_refines_a_safe_symbol_grid_without_using_the_frame_as_fallback() -> None:
    source, analysis = _source(_board())

    result = refine_structured_symbol_lattice_v3(
        source,
        analysis_quad=analysis,
        board_frame_quad=analysis,
        topology=BoardCellTopology(rows=3, columns=5),
    )

    assert result.status == "estimated"
    assert result.symbol_grid_quad is not None
    assert result.final_quad == result.symbol_grid_quad
    assert result.content_safety.status == "passed"
    assert result.content_safety.version == LATTICE_CONTENT_SAFETY_VERSION
    assert result.local_lattice_version == STRUCTURED_LATTICE_REFINEMENT_V3_VERSION


def test_v3_defers_without_any_fallback_when_lattice_evidence_is_incomplete() -> None:
    source, analysis = _source(_board(omit_last_column=True))

    result = refine_structured_symbol_lattice_v3(
        source,
        analysis_quad=analysis,
        board_frame_quad=analysis,
        topology=BoardCellTopology(rows=3, columns=5),
    )

    assert result.status == "needs_review"
    assert result.symbol_grid_quad is None
    assert result.final_quad is None
    assert result.reason_code is not None


def test_content_safety_rejects_a_component_crossing_a_cell_boundary() -> None:
    source, analysis = _source(_board())
    estimate = estimate_board_cell_geometry(
        source,
        _detector_quad(analysis),
    )
    assert estimate.status == "estimated"
    candidate_index = next(
        index for index in estimate.assigned_candidate_indices if index is not None
    )
    candidates = tuple(
        replace(candidate, left=0, width=120)
        if candidate.candidate_index == candidate_index
        else candidate
        for candidate in estimate.rectified_candidates
    )

    safety = evaluate_lattice_content_safety(replace(estimate, rectified_candidates=candidates))

    assert safety.status == "failed"
    assert safety.reason_code == "content_boundary_conflict"
    assert safety.minimum_clearance_px is not None
    assert safety.minimum_clearance_px < 0


def test_v3_rejects_an_unsupported_topology() -> None:
    source, analysis = _source(_board())

    with pytest.raises(StructuredLatticeRefinementError) as captured:
        refine_structured_symbol_lattice_v3(
            source,
            analysis_quad=analysis,
            board_frame_quad=None,
            topology=BoardCellTopology(rows=2, columns=4),
        )

    assert captured.value.code == "IMAGE_PIPELINE_TOPOLOGY_UNSUPPORTED"


def test_v19_serialized_diagnostics_ignore_v3_private_evidence() -> None:
    source, analysis = _source(_board())
    estimate = estimate_board_cell_geometry(
        source,
        _detector_quad(analysis),
    )

    payload = estimate.to_dict()

    assert "rectifiedCandidates" not in payload
    assert "assignedCandidateIndices" not in payload
    assert "idealToObservedMatrix" not in payload
