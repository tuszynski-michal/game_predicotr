"""D-609 cell-cut fraction: node shifts relative to the label cell size."""

import numpy as np
import pytest
from game_predictor_worker.training_core.grid_correction_metrics import (
    CELL_CUT_TOLERANCE,
    cell_cut_fraction,
    evaluate_photo,
)


def lattice(x0=100.0, y0=50.0, width=40.0, height=60.0, shear=0.0):
    return np.array(
        [[x0 + c * width + r * shear, y0 + r * height] for r in range(4) for c in range(6)],
        dtype=np.float64,
    )


def test_identical_lattice_has_no_cut() -> None:
    assert cell_cut_fraction(lattice(), lattice()) == 0.0


def test_shift_is_relative_to_cell_width_and_height() -> None:
    label = lattice()
    moved = label.copy()
    moved[7] += (4.0, 0.0)  # a tenth of the 40 px width
    assert cell_cut_fraction(moved, label) == pytest.approx(0.10)
    moved[7] += (0.0, 15.0)  # a quarter of the 60 px height
    assert cell_cut_fraction(moved, label) == pytest.approx(0.25)


def test_uniform_scale_moves_far_nodes_by_more_than_the_tolerance() -> None:
    label = lattice()
    bigger = label * 1.05  # 5 % larger board shifts the far corner by ~half a cell
    assert cell_cut_fraction(bigger, label) > CELL_CUT_TOLERANCE


def test_board_sheared_like_a_photo_keeps_cell_axes() -> None:
    label = lattice(shear=8.0)
    moved = label.copy()
    moved[:, 0] += 2.0
    assert cell_cut_fraction(moved, label) == pytest.approx(0.05, abs=1e-3)


def test_photo_counts_only_matched_boards_within_cells() -> None:
    label = lattice()
    good, bad = label.copy(), label.copy()
    bad[23] += (12.0, 0.0)  # 30 % of a cell
    within = evaluate_photo("p", "g", [label], [(good, True)], full_geometry=False)
    cut = evaluate_photo("p", "g", [label], [(bad, True)], full_geometry=False)
    missing = evaluate_photo("p", "g", [label], [], full_geometry=False)
    assert (within.boards_within_cells, cut.boards_within_cells) == (1, 0)
    assert missing.boards_within_cells == 0
    assert within.matching.correct == cut.matching.correct == 1
