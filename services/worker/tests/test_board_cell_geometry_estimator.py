from __future__ import annotations

import json
import math
from pathlib import Path

import cv2
import numpy as np
import pytest
from game_predictor_worker.images.board_cell_geometry_contract import (
    BOARD_CELL_GEOMETRY_VERSION,
    parse_board_cell_geometry_manifest,
)
from game_predictor_worker.images.board_cell_geometry_estimator import (
    ESTIMATOR_VERSION,
    HOMOGRAPHY_VERSION,
    LOCATOR_VERSION,
    THRESHOLDS_VERSION,
    BoardCellGeometryEstimate,
    estimate_board_cell_geometry,
    estimator_thresholds,
)
from game_predictor_worker.images.geometry import Point


def _canonical_board(*, missing_slots: set[tuple[int, int]] | None = None) -> np.ndarray:
    board = np.full((300, 500, 3), (22, 11, 19), dtype=np.uint8)
    missing = missing_slots or set()
    colours = (
        (245, 205, 40),
        (245, 80, 35),
        (70, 120, 245),
        (225, 225, 70),
        (245, 150, 45),
    )
    for row, y in enumerate((50, 150, 250)):
        for column, x in enumerate((50, 150, 250, 350, 450)):
            if (row, column) in missing:
                continue
            cv2.circle(
                board,
                (x, y),
                24,
                colours[(row + column) % len(colours)],
                -1,
                cv2.LINE_AA,
            )
    return board


def _perspective_source(
    board: np.ndarray,
    *,
    target: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]] = (
        (108, 82),
        (788, 116),
        (746, 610),
        (142, 574),
    ),
) -> tuple[np.ndarray, tuple[Point, Point, Point, Point]]:
    source = np.full((700, 900, 3), (8, 8, 12), dtype=np.uint8)
    canonical = np.asarray(((0, 0), (499, 0), (499, 299), (0, 299)), dtype=np.float32)
    target_array = np.asarray(target, dtype=np.float32)
    transform = cv2.getPerspectiveTransform(canonical, target_array)
    warped = cv2.warpPerspective(
        board,
        transform,
        (source.shape[1], source.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )
    support = cv2.warpPerspective(
        np.full(board.shape[:2], 255, dtype=np.uint8),
        transform,
        (source.shape[1], source.shape[0]),
        flags=cv2.INTER_NEAREST,
    )
    source[support > 0] = warped[support > 0]
    quad = tuple(Point(x, y) for x, y in target)
    return source, quad  # type: ignore[return-value]


def _entry_payload(estimate: BoardCellGeometryEstimate) -> dict[str, object]:
    bounds = estimate.lattice_bounds_quad
    evidence = estimate.evidence
    assert bounds is not None
    assert evidence is not None
    return {
        "annotationManifestChecksumSha256": None,
        "boardCount": 1,
        "coordinateSpace": "source-image-pixels",
        "cornerSemantics": "symbol-lattice-outer-bounds-5x3",
        "entries": [
            {
                "cells": [cell.to_dict() for cell in estimate.cells],
                "conditionTags": ["perspective"],
                "evidence": evidence.to_dict(),
                "imageId": "synthetic-v19",
                "latticeBoundsQuad": [{"x": point[0], "y": point[1]} for point in bounds],
                "positionIndex": 0,
                "sequenceNumber": 1,
                "sourceGroup": "synthetic",
                "sourceImageChecksumSha256": "1" * 64,
                "sourceImageHeight": 700,
                "sourceImageRelativePath": "synthetic.jpg",
                "sourceImageWidth": 900,
                "sourceOrderIndex": 0,
            }
        ],
        "geometryVersion": BOARD_CELL_GEOMETRY_VERSION,
        "manifestPurpose": "production",
        "pageGeometryManifestChecksumSha256": "2" * 64,
        "schemaVersion": 1,
        "scopeId": "synthetic-v19",
        "sourceCount": 1,
        "sourceManifestChecksumSha256": "3" * 64,
        "version": "board-cell-geometry-manifest-v1",
    }


def test_v19_estimator_builds_complete_source_space_geometry() -> None:
    source, analysis_quad = _perspective_source(_canonical_board())

    estimate = estimate_board_cell_geometry(source, analysis_quad)

    assert estimate.status == "estimated"
    assert estimate.fallback_reason is None
    assert estimate.lattice_bounds_quad is not None
    assert len(estimate.cells) == 15
    assert estimate.evidence is not None
    assert estimate.evidence.estimator_version == ESTIMATOR_VERSION
    assert estimate.evidence.locator_version == LOCATOR_VERSION
    assert estimate.evidence.homography_version == HOMOGRAPHY_VERSION
    assert estimate.evidence.thresholds_version == THRESHOLDS_VERSION
    assert estimate.evidence.reliable_center_count >= 10
    assert estimate.evidence.inlier_count >= 9
    assert {row for row, _ in estimate.evidence.inlier_slots} == {0, 1, 2}
    assert {column for _, column in estimate.evidence.inlier_slots} == {0, 1, 2, 3, 4}
    parsed = parse_board_cell_geometry_manifest(_entry_payload(estimate))
    assert parsed.entries[0].cells == estimate.cells


def test_v19_estimator_is_deterministic_and_preserves_source_perspective() -> None:
    source, analysis_quad = _perspective_source(_canonical_board())

    first = estimate_board_cell_geometry(source, analysis_quad)
    second = estimate_board_cell_geometry(source, analysis_quad)

    assert first.to_dict() == second.to_dict()
    assert first.lattice_bounds_quad is not None
    top = (
        first.lattice_bounds_quad[1][0] - first.lattice_bounds_quad[0][0],
        first.lattice_bounds_quad[1][1] - first.lattice_bounds_quad[0][1],
    )
    left = (
        first.lattice_bounds_quad[3][0] - first.lattice_bounds_quad[0][0],
        first.lattice_bounds_quad[3][1] - first.lattice_bounds_quad[0][1],
    )
    cosine = (top[0] * left[0] + top[1] * left[1]) / (math.hypot(*top) * math.hypot(*left))
    assert abs(cosine) > 0.03


def test_v19_estimator_fails_closed_without_one_lattice_column() -> None:
    source, analysis_quad = _perspective_source(
        _canonical_board(missing_slots={(0, 4), (1, 4), (2, 4)})
    )

    estimate = estimate_board_cell_geometry(source, analysis_quad)

    assert estimate.status == "needs_review"
    assert estimate.lattice_bounds_quad is None
    assert estimate.cells == ()
    assert estimate.evidence is None
    assert estimate.fallback_reason is not None


def test_v19_global_assignment_ignores_unassigned_bright_distractors() -> None:
    board = _canonical_board()
    cv2.circle(board, (102, 105), 16, (250, 250, 250), -1, cv2.LINE_AA)
    cv2.circle(board, (402, 205), 16, (250, 250, 250), -1, cv2.LINE_AA)
    source, analysis_quad = _perspective_source(board)

    estimate = estimate_board_cell_geometry(source, analysis_quad)

    assert estimate.status == "estimated"
    assert estimate.candidate_center_count > 15
    assert estimate.assigned_candidate_count == 15
    assert estimate.evidence is not None
    assert estimate.evidence.inlier_count == 15


def test_v19_threshold_contract_pins_guarded_ransac() -> None:
    thresholds = estimator_thresholds()

    assert thresholds == {
        "homographyVersion": HOMOGRAPHY_VERSION,
        "locatorVersion": LOCATOR_VERSION,
        "maximumColumnSpacingPx": 135.0,
        "maximumInlierP95ResidualPx": 10.0,
        "maximumRowSpacingPx": 145.0,
        "minimumAssignedComponents": 10,
        "minimumAxisComponentMatches": 8,
        "minimumColumnSpacingPx": 45.0,
        "minimumInliers": 9,
        "minimumReliableCenters": 10,
        "minimumRowSpacingPx": 45.0,
        "ransacReprojectionThresholdPx": 12.0,
        "thresholdsVersion": THRESHOLDS_VERSION,
    }


@pytest.mark.parametrize(
    "target",
    [
        ((108, 82), (788, 116), (746, 610), (142, 574)),
        ((156, 64), (754, 150), (802, 596), (96, 540)),
    ],
)
def test_v19_angle_changes_source_quads_without_changing_row_major_order(
    target: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]],
) -> None:
    source, analysis_quad = _perspective_source(_canonical_board(), target=target)

    estimate = estimate_board_cell_geometry(source, analysis_quad)

    assert estimate.status == "estimated"
    assert [(cell.row_index, cell.column_index) for cell in estimate.cells] == [
        (row, column) for row in range(3) for column in range(5)
    ]


def test_v19_real_corpus_estimates_visible_lattices_and_fails_closed_on_occlusion() -> None:
    root = Path(__file__).resolve().parents[3]
    source_root = root / "examples" / "imgs"
    if not (source_root / "5983122166590934317.jpg").is_file():
        pytest.skip("The ignored local M5 source corpus is not present in this checkout.")
    annotations = json.loads(
        (root / "ai_docs" / "quality" / "m5-cell-grid-golden.json").read_text(encoding="utf-8")
    )
    estimated_sequences: set[int] = set()
    failures: dict[int, str | None] = {}
    mean_corner_errors: list[float] = []
    for entry in annotations["entries"]:
        source_bgr = cv2.imread(
            str(source_root / entry["sourceImageRelativePath"]),
            cv2.IMREAD_COLOR,
        )
        assert source_bgr is not None
        source_rgb = cv2.cvtColor(source_bgr, cv2.COLOR_BGR2RGB)
        analysis_quad = tuple(
            Point(int(round(point["x"])), int(round(point["y"])))
            for point in entry["detectedSourceQuad"]
        )
        estimate = estimate_board_cell_geometry(source_rgb, analysis_quad)  # type: ignore[arg-type]
        sequence_number = int(entry["sequenceNumber"])
        if estimate.status == "needs_review":
            failures[sequence_number] = estimate.fallback_reason
            assert estimate.lattice_bounds_quad is None
            assert estimate.cells == ()
            assert estimate.evidence is None
            continue
        estimated_sequences.add(sequence_number)
        assert estimate.lattice_bounds_quad is not None
        expected = np.asarray(
            [(point["x"], point["y"]) for point in entry["sourceQuad"]],
            dtype=np.float64,
        )
        actual = np.asarray(estimate.lattice_bounds_quad, dtype=np.float64)
        mean_corner_errors.append(float(np.mean(np.linalg.norm(actual - expected, axis=1))))

    assert len(estimated_sequences) == 25
    assert failures == {
        37: "SYMBOL_LATTICE_INSUFFICIENT_INLIERS",
        112: "BOARD_CELL_GEOMETRY_INSUFFICIENT_GLOBAL_ASSIGNMENTS",
    }
    assert max(mean_corner_errors) <= 6.25
