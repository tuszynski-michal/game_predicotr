from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.symbol_grid_refinement import (
    SymbolCenter,
    rectify_board,
)
from game_predictor_worker.images.symbol_lattice_homography import (
    HOMOGRAPHY_VERSION,
    estimate_symbol_lattice_homography,
    fit_symbol_lattice_homography,
    ideal_lattice_points,
)


def _synthetic_centers(
    matrix: np.ndarray,
    *,
    corrupt_slots: set[tuple[int, int]] | None = None,
) -> tuple[SymbolCenter, ...]:
    observed = cv2.perspectiveTransform(
        ideal_lattice_points().astype(np.float64).reshape((-1, 1, 2)),
        matrix.astype(np.float64),
    ).reshape((-1, 2))
    noise = np.asarray(
        [
            (-0.7, 0.4),
            (0.3, -0.5),
            (0.6, 0.2),
            (-0.4, -0.6),
            (0.2, 0.5),
        ]
        * 3,
        dtype=np.float64,
    )
    observed += noise
    corrupt = corrupt_slots or set()
    centers: list[SymbolCenter] = []
    for row in range(3):
        for column in range(5):
            index = row * 5 + column
            x, y = observed[index]
            if (row, column) in corrupt:
                x += 58.0
                y -= 46.0
            centers.append(
                SymbolCenter(
                    row_index=row,
                    column_index=column,
                    x=float(x),
                    y=float(y),
                    confidence=0.9,
                )
            )
    return tuple(centers)


def test_full_lattice_ransac_rejects_corrupt_corner_symbols() -> None:
    expected = np.asarray(
        (
            (0.91, 0.025, 16.0),
            (-0.015, 0.90, 13.0),
            (0.00008, -0.00006, 1.0),
        ),
        dtype=np.float64,
    )
    centers = _synthetic_centers(
        expected,
        corrupt_slots={(0, 0), (2, 4)},
    )

    result = fit_symbol_lattice_homography(centers)

    assert result.status == "fitted"
    assert result.fallback_reason is None
    assert result.inlier_count == 13
    assert (0, 0) not in result.inlier_slots
    assert (2, 4) not in result.inlier_slots
    assert result.row_coverage == 3
    assert result.column_coverage == 5
    assert result.ideal_to_observed_matrix is not None
    assert np.asarray(result.ideal_to_observed_matrix) == pytest.approx(
        expected,
        abs=1.5,
    )


def test_fit_fails_closed_when_reliable_centers_do_not_cover_every_column() -> None:
    identity = np.eye(3, dtype=np.float64)
    centers = tuple(center for center in _synthetic_centers(identity) if center.column_index != 4)

    result = fit_symbol_lattice_homography(centers)

    assert result.status == "fallback"
    assert result.fallback_reason == "SYMBOL_LATTICE_INSUFFICIENT_COVERAGE"
    assert result.ideal_to_observed_matrix is None
    assert result.virtual_grid_quad is None


def test_fit_fails_closed_when_virtual_grid_leaves_expanded_frame() -> None:
    translated = np.asarray(
        (
            (0.90, 0.0, 80.0),
            (0.0, 0.90, 20.0),
            (0.0, 0.0, 1.0),
        ),
        dtype=np.float64,
    )

    result = fit_symbol_lattice_homography(_synthetic_centers(translated))

    assert result.status == "fallback"
    assert result.fallback_reason == "SYMBOL_LATTICE_VIRTUAL_GRID_IMPLAUSIBLE"
    assert result.ideal_to_observed_matrix is None
    assert result.virtual_grid_quad is None


def test_sequence_29_derives_virtual_corners_from_complete_symbol_lattice() -> None:
    root = Path(__file__).resolve().parents[3]
    source_bgr = cv2.imread(
        str(root / "examples/imgs/5983122166590934320.jpg"),
        cv2.IMREAD_COLOR,
    )
    assert source_bgr is not None
    board_rgb, _ = rectify_board(
        cv2.cvtColor(source_bgr, cv2.COLOR_BGR2RGB),
        (
            Point(386, 329),
            Point(679, 317),
            Point(669, 459),
            Point(396, 436),
        ),
    )

    first = estimate_symbol_lattice_homography(board_rgb)
    second = estimate_symbol_lattice_homography(board_rgb)

    assert first.status == "fitted"
    assert first.to_dict() == second.to_dict()
    assert first.to_dict()["homographyVersion"] == HOMOGRAPHY_VERSION
    assert first.reliable_center_count == 14
    assert first.inlier_count == 13
    assert first.row_coverage == 3
    assert first.column_coverage == 5
    assert first.inlier_p95_residual_px == pytest.approx(7.6869, abs=0.001)
    assert first.virtual_grid_quad is not None
    assert np.asarray(first.virtual_grid_quad) == pytest.approx(
        np.asarray(
            (
                (1.5127, 4.1743),
                (476.5020, 22.3797),
                (470.9365, 287.7535),
                (30.8164, 309.6661),
            )
        ),
        abs=0.01,
    )
