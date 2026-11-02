"""CPU regressions for partial controls, matching and photo/game macro selection."""

from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from game_predictor_worker.training_core.grid_correction_metrics import (
    CorrectionControlPhoto,
    aggregate_checkpoint_metrics,
    checkpoint_metrics,
    evaluate_photo,
    measure,
    measure_role,
    selection_key,
)
from game_predictor_worker.training_core.grid_evaluation import input_sha256


def nodes(x: float = 0) -> np.ndarray[Any, Any]:
    return np.array([(x + col * 10, row * 10) for row in range(4) for col in range(6)], dtype=float)


def test_matching_is_one_to_one_and_missing_costs_one() -> None:
    result = evaluate_photo("p", "g", [nodes(), nodes()], [(nodes(), True)], full_geometry=False)
    assert result.matching.matched == result.matching.correct == 1
    assert result.normalized_error == 0.5
    assert measure([result])["board_correct_rate"] == 0.5


def test_partial_excludes_unlabelled_false_and_duplicate_claims() -> None:
    result = evaluate_photo(
        "p",
        "g",
        [nodes()],
        [(nodes(), True), (nodes(), True), (nodes(500), True)],
        full_geometry=False,
    )
    metrics = measure([result])
    assert metrics["boards_correct"] == 1
    assert metrics["normalized_error"] == 0
    for key in (
        "false_boards",
        "duplicate_predictions",
        "photo_complete_correct",
        "photo_complete_correct_rate",
    ):
        assert metrics[key] is None
    assert result.as_dict()["complete_correct"] is None


def test_full_counts_false_duplicates_and_strict_completeness() -> None:
    labels = [nodes(index * 100) for index in range(9)]
    result = evaluate_photo(
        "p",
        "g",
        labels,
        [(label, True) for label in labels] + [(nodes(), True), (nodes(1000), True)],
        full_geometry=True,
    )
    metrics = measure([result])
    assert metrics["boards_correct"] == 9
    assert metrics["false_boards"] == metrics["duplicate_predictions"] == 1
    assert metrics["photo_complete_correct"] == 0


def test_bbox_normalization_differs_from_legacy_tl_br_diagonal() -> None:
    label = nodes()
    angle = np.pi / 4
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    label = label @ rotation
    result = evaluate_photo("p", "g", [label], [(label + [1, 0], True)], full_geometry=False)
    assert result.normalized_error == pytest.approx(1 / np.linalg.norm(np.ptp(label, axis=0)))
    assert result.normalized_error != pytest.approx(result.matching.matches[0].nme)


def test_invalid_or_absent_prediction_has_maximum_cost_and_valid_error_is_clamped() -> None:
    label = nodes()
    invalid = evaluate_photo("p", "g", [label], [(label, False)], full_geometry=False)
    missing = evaluate_photo("p", "g", [label], [], full_geometry=False)
    distorted = label.copy()
    distorted[1:5] += 10000
    large = evaluate_photo("p", "g", [label], [(distorted, True)], full_geometry=False)
    assert invalid.normalized_error == missing.normalized_error == large.normalized_error == 1


def test_photo_macro_then_equal_game_weights_and_earliest_checkpoint() -> None:
    many = evaluate_photo("many", "g", [nodes()] * 9, [(nodes(), True)] * 9, full_geometry=True)
    few = evaluate_photo("few", "g", [nodes()], [], full_geometry=False)
    metrics = checkpoint_metrics([many, few])
    assert metrics == {"boardCorrectRate": 0.5, "normalizedError": 0.5}
    combined = aggregate_checkpoint_metrics([metrics, checkpoint_metrics([many] * 8)])
    assert combined == {"boardCorrectRate": 0.75, "normalizedError": 0.25}
    assert selection_key(combined, 1) > selection_key(combined, 2)
    assert selection_key({"boardCorrectRate": 0.8, "normalizedError": 0.9}, 99) > selection_key(
        combined, 1
    )
    assert selection_key({"boardCorrectRate": 0.75, "normalizedError": 0.2}, 99) > selection_key(
        combined, 1
    )


def test_measure_role_uses_identical_original_once_and_legacy_input_identity() -> None:
    frame = np.zeros((40, 60, 3))
    loads = []

    def load() -> np.ndarray[Any, Any]:
        loads.append(True)
        return frame

    class Engine:
        def analyse(self, rgb: Any) -> list[Any]:
            assert rgb is frame
            return [SimpleNamespace(nodes=nodes())]

    photos = [CorrectionControlPhoto("p", "g", "a" * 64, (nodes(),), load, False)]
    summary, details = measure_role(photos, Engine(), Engine())
    assert loads == [True]
    assert summary["inputSha256"] == input_sha256(photos)
    assert summary["base"] == summary["candidate"]
    assert summary["recordings"][0]["base"] == summary["base"]
    assert details[0]["sourceId"] == "p"
    assert details[0]["base"]["false_boards"] is None
    with pytest.raises(ValueError, match="once"):
        measure_role(photos * 2, Engine(), Engine())


def test_missing_validation_and_malformed_labels_cannot_select_checkpoint() -> None:
    with pytest.raises(ValueError):
        checkpoint_metrics([])
    with pytest.raises(ValueError):
        aggregate_checkpoint_metrics([])
    with pytest.raises(ValueError):
        selection_key({"boardCorrectRate": float("nan"), "normalizedError": 0}, 1)
    with pytest.raises(ValueError):
        evaluate_photo("p", "g", [], [], full_geometry=False)
    with pytest.raises(ValueError):
        evaluate_photo("p", "g", [nodes()], [], full_geometry=True)
