from __future__ import annotations

import numpy as np
import pytest
from game_predictor_worker.images.geometry import Point, Quad
from game_predictor_worker.images.symbol_grid_refinement import (
    SymbolGridRefinementError,
    locate_symbol_centers,
    rectify_board,
    refine_symbol_grid,
)
from numpy.typing import NDArray


def _quad() -> Quad:
    return (
        Point(50, 50),
        Point(549, 50),
        Point(549, 349),
        Point(50, 349),
    )


def _synthetic_image(*, offset_x: int, offset_y: int) -> NDArray[np.uint8]:
    image = np.full((400, 600, 3), (12, 8, 16), dtype=np.uint8)
    colours = (
        (250, 210, 20),
        (210, 35, 25),
        (35, 80, 240),
        (180, 45, 210),
    )
    yy, xx = np.ogrid[:400, :600]
    for row in range(3):
        for column in range(5):
            center_x = 50 + 50 + column * 100 + offset_x
            center_y = 50 + 50 + row * 100 + offset_y
            mask = (xx - center_x) ** 2 + (yy - center_y) ** 2 <= 25**2
            image[mask] = colours[(row * 5 + column) % len(colours)]
    return image


def test_symbol_centers_refine_a_shifted_regular_lattice() -> None:
    image = _synthetic_image(offset_x=12, offset_y=-8)

    result = refine_symbol_grid(image, _quad())
    repeated = refine_symbol_grid(image, _quad())

    assert result == repeated
    assert result.status == "refined"
    assert result.reliable_center_count == 15
    assert result.inlier_count == 15
    assert result.baseline_median_residual_px is not None
    assert result.refined_median_residual_px is not None
    assert result.refined_p95_residual_px is not None
    assert result.refined_median_residual_px < result.baseline_median_residual_px
    assert result.source_quad != _quad()

    refined_board, _ = rectify_board(image, result.source_quad)
    centers = locate_symbol_centers(refined_board)
    assert max(abs(center.x - (center.column_index + 0.5) * 100) for center in centers) < 2.5
    assert max(abs(center.y - (center.row_index + 0.5) * 100) for center in centers) < 2.5


def test_low_signal_board_falls_back_without_mutating_quad() -> None:
    image = np.zeros((400, 600, 3), dtype=np.uint8)

    result = refine_symbol_grid(image, _quad())

    assert result.status == "fallback"
    assert result.fallback_reason == "SYMBOL_GRID_INSUFFICIENT_CENTERS"
    assert result.reliable_center_count == 0
    assert result.source_quad == _quad()


def test_invalid_quad_is_rejected_before_processing() -> None:
    image = _synthetic_image(offset_x=0, offset_y=0)
    invalid: Quad = (
        Point(-1, 50),
        Point(549, 50),
        Point(549, 349),
        Point(50, 349),
    )

    with pytest.raises(SymbolGridRefinementError) as error:
        refine_symbol_grid(image, invalid)

    assert error.value.code == "SYMBOL_GRID_QUAD_OUT_OF_BOUNDS"
