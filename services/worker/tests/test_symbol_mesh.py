from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from game_predictor_worker.images.symbol_mesh import (
    build_historical_centered_symbol_mesh_v4,
    build_symbol_mesh,
)


def test_real_sequence_316_complete_frame_builds_fifteen_local_crops() -> None:
    root = Path(__file__).resolve().parents[3]
    path = (
        root
        / "artifacts/m5-board-crops"
        / "board-cell-crops-bounding-frame-spike-v1"
        / "92"
        / "92cf1df591c082574088fb81ba6150f436f3dd2ebf381c9ad4c1fdeb8e59aec5"
        / "board-00"
        / "board.png"
    )
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    assert bgr is not None
    result = build_symbol_mesh(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))

    assert result.status == "meshed"
    assert result.reliable_center_count == 15
    assert len(result.cells) == 15
    assert all(cell.rgb.shape == (90, 90, 3) for cell in result.cells)
    assert all(0 <= cell.left < cell.right <= 500 for cell in result.cells)
    assert all(0 <= cell.top < cell.bottom <= 300 for cell in result.cells)
    assert max(cell.right - cell.left for cell in result.cells) < 170


def test_expanded_sequence_192_fails_closed_on_false_outer_column() -> None:
    root = Path(__file__).resolve().parents[3]
    path = (
        root
        / "artifacts/m5-board-crops"
        / "board-cell-crops-v9-safe-context-shifted-overlap-v1"
        / "6f"
        / "6fe281ef6288fb4afc409fe0c1d1b7ce57c4db1c38a79babc5b23d0ad174a911"
        / "board-02"
        / "board.png"
    )
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    assert bgr is not None

    result = build_symbol_mesh(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))

    assert result.status == "fallback"
    assert result.fallback_reason == "SYMBOL_MESH_SPACING_IMPLAUSIBLE"
    assert result.cells == ()


def test_historical_v4_builder_keeps_its_narrow_centered_contract() -> None:
    root = Path(__file__).resolve().parents[3]
    path = (
        root
        / "artifacts/m5-board-crops"
        / "board-cell-crops-bounding-frame-spike-v1"
        / "92"
        / "92cf1df591c082574088fb81ba6150f436f3dd2ebf381c9ad4c1fdeb8e59aec5"
        / "board-00"
        / "board.png"
    )
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    assert bgr is not None

    result = build_historical_centered_symbol_mesh_v4(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))

    assert result.status == "meshed"
    assert max(cell.right - cell.left for cell in result.cells) < 100
    assert result.column_center_source == "raw-slot-medians"


def test_current_mesh_recovers_shifted_columns_from_bright_components() -> None:
    board = np.full((300, 500, 3), (25, 18, 30), dtype=np.uint8)
    expected_columns = [90, 165, 240, 315, 390]
    for row_center in (50, 150, 250):
        for column_center in expected_columns:
            cv2.circle(
                board,
                (column_center, row_center),
                22,
                (250, 195, 30),
                -1,
                cv2.LINE_AA,
            )

    result = build_symbol_mesh(board)

    assert result.status == "meshed"
    assert result.column_center_source == "bright-component-lattice"
    measured_columns = [result.cells[column].center_x for column in range(5)]
    assert measured_columns == pytest.approx(expected_columns, abs=2.0)
