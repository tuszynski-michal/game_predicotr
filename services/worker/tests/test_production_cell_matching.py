"""Assignment uniqueness must not lose finite costs beside missing-board sentinels."""

from itertools import permutations

import numpy as np
import pytest
from game_predictor_worker.geometry_core.metrics import evaluate_photo, quad_iou
from game_predictor_worker.images.production_cell_evaluation import ambiguous_matching
from numpy.typing import NDArray


def lattice(x: float, y: float = 0.0) -> NDArray[np.float64]:
    return np.asarray(
        [(x + column / 5, y + row / 3) for row in range(4) for column in range(6)], dtype=np.float64
    )


@pytest.mark.parametrize("order", list(permutations(range(3))))
def test_missing_target_does_not_hide_exact_tie(order: tuple[int, ...]) -> None:
    labels = [lattice(0), lattice(10), lattice(100)]
    pool = [lattice(0.07), lattice(0.07), lattice(10.13)]
    predictions = [pool[index] for index in order]
    measured = evaluate_photo("tie", "grid", labels, [(p, True) for p in predictions])
    assert len(measured.matches) == 2
    assert len({m.prediction for m in measured.matches}) == 2
    assert len({m.label for m in measured.matches}) == 2
    assert ambiguous_matching(labels, predictions, measured.matches) == {0}


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("shift", [1e-8, 3e-8])
def test_missing_target_does_not_erase_small_genuine_gap(reverse: bool, shift: float) -> None:
    labels = [lattice(0), lattice(100)]
    predictions = [lattice(0), lattice(shift)]
    if reverse:
        predictions.reverse()
    corners = [0, 5, 23, 18]
    gap = abs(
        quad_iou(predictions[0][corners], labels[0][corners])
        - quad_iou(predictions[1][corners], labels[0][corners])
    )
    assert 1e-14 < gap < np.spacing(1e9)
    measured = evaluate_photo("gap", "grid", labels, [(p, True) for p in predictions])
    assert len(measured.matches) == 1
    assert ambiguous_matching(labels, predictions, measured.matches) == set()


def test_removing_the_only_valid_edge_cannot_be_an_alternative() -> None:
    labels, predictions = [lattice(0), lattice(100)], [lattice(0), lattice(200)]
    measured = evaluate_photo("unique", "grid", labels, [(p, True) for p in predictions])
    assert len(measured.matches) == 1
    assert ambiguous_matching(labels, predictions, measured.matches) == set()


def test_single_prediction_is_not_reused_for_two_equal_targets() -> None:
    labels, predictions = [lattice(0), lattice(0)], [lattice(0)]
    measured = evaluate_photo("one-to-one", "grid", labels, [(p, True) for p in predictions])
    assert len(measured.matches) == 1
    assert ambiguous_matching(labels, predictions, measured.matches) == {0, 1}


@pytest.mark.parametrize("labels,predictions", [([], [lattice(0)]), ([lattice(0)], [])])
def test_empty_side_has_no_alternative(
    labels: list[NDArray[np.float64]], predictions: list[NDArray[np.float64]]
) -> None:
    assert ambiguous_matching(labels, predictions, []) == set()
