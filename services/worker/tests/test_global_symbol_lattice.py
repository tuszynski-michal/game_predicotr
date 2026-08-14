from __future__ import annotations

import cv2
import numpy as np
import pytest
from game_predictor_worker.images.global_symbol_lattice import (
    LOCATOR_VERSION,
    locate_global_symbol_lattice,
)
from game_predictor_worker.images.symbol_lattice_homography import (
    GLOBAL_HOMOGRAPHY_VERSION,
    estimate_global_symbol_lattice_homography,
)


def _synthetic_shifted_lattice(*, height: int = 300) -> np.ndarray:
    board = np.full((height, 500, 3), (24, 12, 20), dtype=np.uint8)
    colours = (
        (245, 205, 40),
        (245, 80, 35),
        (70, 120, 245),
        (225, 225, 70),
        (245, 150, 45),
    )
    for row, y in enumerate((70, 150, 230)):
        for column, x in enumerate((90, 170, 250, 330, 410)):
            cv2.circle(
                board,
                (x, y),
                24,
                colours[(row + column) % len(colours)],
                -1,
                cv2.LINE_AA,
            )
    return board


def test_global_candidates_are_assigned_to_shifted_symbol_columns() -> None:
    board = _synthetic_shifted_lattice()

    first = locate_global_symbol_lattice(board)
    second = locate_global_symbol_lattice(board)

    assert first.status == "assigned"
    assert first.fallback_reason is None
    assert first.to_dict() == second.to_dict()
    assert first.to_dict()["locatorVersion"] == LOCATOR_VERSION
    assert first.assigned_candidate_count == 15
    assert first.column_bases == pytest.approx((90, 170, 250, 330, 410), abs=1.0)
    assert first.row_bases == pytest.approx((70, 150, 230), abs=1.0)
    assert first.centers[0].x == pytest.approx(90, abs=3.0)
    assert first.centers[0].x > 75


def test_global_homography_keeps_the_global_locator_provenance() -> None:
    result = estimate_global_symbol_lattice_homography(_synthetic_shifted_lattice())

    assert result.status == "fitted"
    assert result.fallback_reason is None
    assert result.inlier_count == 15
    assert result.to_dict()["homographyVersion"] == GLOBAL_HOMOGRAPHY_VERSION
    assert result.to_dict()["locatorVersion"] == LOCATOR_VERSION
    assert result.global_assigned_candidate_count == 15


def test_global_locator_fails_closed_without_a_complete_lattice() -> None:
    board = np.full((300, 500, 3), (24, 12, 20), dtype=np.uint8)
    cv2.circle(board, (90, 70), 24, (245, 205, 40), -1, cv2.LINE_AA)

    result = locate_global_symbol_lattice(board)

    assert result.status == "fallback"
    assert result.fallback_reason == "GLOBAL_SYMBOL_LATTICE_INSUFFICIENT_COMPONENTS"
    assert result.centers == ()
