from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.projective_lattice_crops import (
    CELL_OUTPUT_SIZE,
    CROPPER_VERSION,
    FIXED_PADDING_PX,
    build_projective_lattice_crops,
)
from game_predictor_worker.images.symbol_grid_refinement import (
    SymbolCenter,
    rectify_board,
)
from game_predictor_worker.images.symbol_lattice_homography import (
    SymbolLatticeHomography,
)


def test_sequence_29_fixed_padding_uses_only_source_supported_pixels() -> None:
    root = Path(__file__).resolve().parents[3]
    source_bgr = cv2.imread(
        str(root / "examples/imgs/5983122166590934320.jpg"),
        cv2.IMREAD_COLOR,
    )
    assert source_bgr is not None
    expanded_board, _ = rectify_board(
        cv2.cvtColor(source_bgr, cv2.COLOR_BGR2RGB),
        (
            Point(386, 329),
            Point(679, 317),
            Point(669, 459),
            Point(396, 436),
        ),
    )

    result = build_projective_lattice_crops(expanded_board)

    assert result.status == "cropped"
    assert result.fallback_reason is None
    assert result.minimum_support_fraction == 1.0
    assert len(result.cells) == 15
    assert all(cell.rgb.shape == (CELL_OUTPUT_SIZE, CELL_OUTPUT_SIZE, 3) for cell in result.cells)
    assert all(cell.support_fraction == 1.0 for cell in result.cells)
    assert result.cells[0].canonical_bounds == (
        FIXED_PADDING_PX,
        FIXED_PADDING_PX,
        100 - FIXED_PADDING_PX,
        100 - FIXED_PADDING_PX,
    )
    assert result.to_dict()["cropperVersion"] == CROPPER_VERSION


def test_fixed_padding_fails_closed_when_a_cell_needs_pixels_outside_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    centers = tuple(
        SymbolCenter(
            row_index=row,
            column_index=column,
            x=column * 100.0 + 65.0,
            y=row * 100.0 + 50.0,
            confidence=0.9,
        )
        for row in range(3)
        for column in range(5)
    )
    homography = SymbolLatticeHomography(
        status="fitted",
        centers=centers,
        reliable_center_count=15,
        inlier_slots=tuple((row, column) for row in range(3) for column in range(5)),
        row_coverage=3,
        column_coverage=5,
        inlier_median_residual_px=0.0,
        inlier_p95_residual_px=0.0,
        all_center_p95_residual_px=0.0,
        ideal_to_observed_matrix=(
            (1.0, 0.0, 15.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        ),
        virtual_grid_quad=(
            (15.0, 0.0),
            (515.0, 0.0),
            (515.0, 300.0),
            (15.0, 300.0),
        ),
        fallback_reason=None,
    )
    monkeypatch.setattr(
        "game_predictor_worker.images.projective_lattice_crops.estimate_symbol_lattice_homography",
        lambda _: homography,
    )
    board = np.full((300, 500, 3), 120, dtype=np.uint8)

    result = build_projective_lattice_crops(board)

    assert result.status == "fallback"
    assert result.fallback_reason == "PROJECTIVE_LATTICE_CELL_OUTSIDE_SOURCE"
    assert len(result.cells) == 4
