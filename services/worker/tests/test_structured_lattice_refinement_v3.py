from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

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
    STRUCTURED_LATTICE_ACCEPTANCE_REPORT_CHECKSUM_SHA256,
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
    candidate_index = estimate.assigned_candidate_indices[1]
    assert candidate_index is not None
    candidates = tuple(
        replace(
            candidate,
            touches_border=False,
            core_left=84.0,
            core_top=32.0,
            core_width=32.0,
            core_height=36.0,
        )
        if candidate.candidate_index == candidate_index
        else candidate
        for candidate in estimate.rectified_candidates
    )

    safety = evaluate_lattice_content_safety(replace(estimate, rectified_candidates=candidates))

    assert safety.status == "failed"
    assert safety.reason_code == "content_boundary_conflict"
    assert safety.minimum_clearance_px is not None
    assert safety.minimum_clearance_px < 0


def test_content_safety_allows_extra_background_at_the_outer_lattice_edge() -> None:
    source, analysis = _source(_board())
    estimate = estimate_board_cell_geometry(source, _detector_quad(analysis))
    assert estimate.status == "estimated"
    candidate_index = estimate.assigned_candidate_indices[0]
    assert candidate_index is not None
    candidates = tuple(
        replace(
            candidate,
            touches_border=False,
            core_left=-8.0,
            core_top=-6.0,
            core_width=48.0,
            core_height=46.0,
        )
        if candidate.candidate_index == candidate_index
        else candidate
        for candidate in estimate.rectified_candidates
    )

    safety = evaluate_lattice_content_safety(replace(estimate, rectified_candidates=candidates))

    assert safety.status == "passed"
    assert safety.reason_code is None


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

    candidate_payload = estimate.rectified_candidates[0].to_dict()
    assert not any(key.startswith("core") for key in candidate_payload)


def test_active_config_is_bound_to_the_accepted_real_image_report() -> None:
    report_path = (
        Path(__file__).resolve().parents[3]
        / "ai_docs"
        / "quality"
        / "STRUCTURED_LATTICE_V3_ACCEPTANCE.json"
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    acceptance_passed = report.pop("acceptancePassed")
    report.pop("evaluationMilliseconds")
    checksum = report.pop("reportChecksumSha256")
    canonical = json.dumps(
        report,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")

    assert report["reportVersion"] == "structured-lattice-v3-real-manual-acceptance-v1"
    assert acceptance_passed is True
    assert checksum == hashlib.sha256(canonical).hexdigest()
    assert checksum == STRUCTURED_LATTICE_ACCEPTANCE_REPORT_CHECKSUM_SHA256
    golden = report["goldenRegressions"]
    assert golden["19999-20007"]["passed"] is True
    assert golden["20026-20034"]["passed"] is True
