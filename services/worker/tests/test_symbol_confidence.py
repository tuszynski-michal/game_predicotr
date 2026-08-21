from __future__ import annotations

import numpy as np
import pytest
from game_predictor_worker.images.symbol_confidence import (
    ActiveLearningBoard,
    ActiveLearningCell,
    SymbolConfidenceError,
    TEMPERATURE_MINIMUM,
    build_confidence_policy,
    calibrated_probabilities,
    calibration_metrics,
    fit_temperature,
    select_active_learning_boards,
    threshold_evidence,
)


def test_temperature_reduces_validation_nll_without_changing_top_one() -> None:
    logits = np.asarray(
        [
            [8.0, 0.0],
            [8.0, 0.0],
            [8.0, 0.0],
            [0.0, 8.0],
            [0.0, 8.0],
            [0.0, 8.0],
        ],
        dtype=np.float64,
    )
    labels = np.asarray([0, 0, 1, 1, 1, 0], dtype=np.int64)

    temperature = fit_temperature(logits, labels)
    before = calibration_metrics(
        calibrated_probabilities(logits, 1.0),
        labels,
        ("left", "right"),
    )
    after_probabilities = calibrated_probabilities(logits, temperature)
    after = calibration_metrics(after_probabilities, labels, ("left", "right"))

    assert temperature > 1.0
    assert after["negativeLogLikelihood"] < before["negativeLogLikelihood"]
    assert np.array_equal(
        np.argmax(after_probabilities, axis=1),
        np.argmax(logits, axis=1),
    )


def test_perfect_small_cohort_cannot_calibrate_to_near_zero_temperature() -> None:
    logits = np.asarray([[12.0, 0.0], [0.0, 12.0]], dtype=np.float64)

    temperature = fit_temperature(logits, np.asarray([0, 1], dtype=np.int64))

    assert temperature >= TEMPERATURE_MINIMUM


def test_metrics_expose_reliability_and_each_class() -> None:
    probabilities = np.asarray(
        [[0.8, 0.2], [0.4, 0.6], [0.7, 0.3], [0.1, 0.9]],
        dtype=np.float64,
    )
    metrics = calibration_metrics(
        probabilities,
        np.asarray([0, 1, 1, 1], dtype=np.int64),
        ("a", "b"),
    )

    assert metrics["sampleCount"] == 4
    assert metrics["accuracy"] == 0.75
    assert len(metrics["reliabilityBins"]) == 10
    assert [row["symbolCode"] for row in metrics["perClass"]] == ["a", "b"]


def test_bootstrap_policy_fails_closed_even_for_strong_threshold() -> None:
    class_codes = tuple(f"c{index}" for index in range(8))
    labels = np.repeat(np.arange(8, dtype=np.int64), 3)
    probabilities = np.full((24, 8), 0.01 / 7.0, dtype=np.float64)
    probabilities[np.arange(24), labels] = 0.99
    rows = threshold_evidence(probabilities, labels, class_codes)

    bootstrap = build_confidence_policy(
        rows,
        model_status="bootstrap",
        bootstrap_target_met=False,
    )
    mature = build_confidence_policy(
        rows,
        model_status="production_candidate",
        bootstrap_target_met=True,
    )

    assert bootstrap["autoAccept"]["enabled"] is False
    assert bootstrap["automaticReject"]["enabled"] is False
    assert bootstrap["manualReview"]["threshold"] == 0.0
    assert mature["autoAccept"]["enabled"] is True
    assert mature["autoAccept"]["threshold"] == 0.99


def _board(
    board_id: str,
    sequence_number: int,
    source: str,
    probability: tuple[float, float],
) -> ActiveLearningBoard:
    return ActiveLearningBoard(
        board_id=board_id,
        sequence_number=sequence_number,
        source_image_id=f"id-{source}",
        source_image_checksum=source * 64,
        source_group="fixture",
        board_relative_path=f"boards/{board_id}.png",
        cells=tuple(
            ActiveLearningCell(
                sample_id=f"{board_id}-{index}",
                cell_index=index,
                row_index=index // 5,
                column_index=index % 5,
                probabilities=probability,
            )
            for index in range(15)
        ),
    )


def test_active_learning_is_deterministic_and_uses_new_sources_first() -> None:
    boards = (
        _board("uncertain-a", 3, "a", (0.5, 0.5)),
        _board("uncertain-a-second", 1, "a", (0.51, 0.49)),
        _board("certain-b", 2, "b", (0.99, 0.01)),
    )

    first = select_active_learning_boards(boards, ("left", "right"), batch_size=2)
    second = select_active_learning_boards(boards, ("left", "right"), batch_size=2)

    assert first == second
    assert [row["boardId"] for row in first] == ["uncertain-a", "certain-b"]
    assert len({row["sourceImageChecksumSha256"] for row in first}) == 2
    assert all(len(row["cells"]) == 15 for row in first)


def test_active_learning_stable_tie_uses_sequence_number() -> None:
    boards = (
        _board("later", 2, "a", (0.5, 0.5)),
        _board("earlier", 1, "b", (0.5, 0.5)),
    )

    selected = select_active_learning_boards(boards, ("left", "right"), batch_size=1)

    assert selected[0]["boardId"] == "earlier"


def test_incomplete_board_and_invalid_calibration_fail_closed() -> None:
    incomplete = _board("broken", 1, "a", (0.5, 0.5))
    incomplete = ActiveLearningBoard(
        board_id=incomplete.board_id,
        sequence_number=incomplete.sequence_number,
        source_image_id=incomplete.source_image_id,
        source_image_checksum=incomplete.source_image_checksum,
        source_group=incomplete.source_group,
        board_relative_path=incomplete.board_relative_path,
        cells=incomplete.cells[:-1],
    )

    with pytest.raises(SymbolConfidenceError) as selection_error:
        select_active_learning_boards((incomplete,), ("left", "right"))
    with pytest.raises(SymbolConfidenceError) as calibration_error:
        fit_temperature(
            np.asarray([[np.nan, 0.0]]),
            np.asarray([0], dtype=np.int64),
        )

    assert selection_error.value.code == "SYMBOL_ACTIVE_LEARNING_BOARD_INCOMPLETE"
    assert calibration_error.value.code == "SYMBOL_CONFIDENCE_INPUT_INVALID"
