from __future__ import annotations

import numpy as np
import pytest
from game_predictor_worker.images.symbol_vertical_slice import (
    SymbolVerticalSliceError,
    build_review_replay,
    canonical_report_bytes,
    evaluate_probabilities,
    validate_runtime_observation,
)


def _evaluated():
    class_codes = ("cherries", "star")
    labels = np.asarray([index % 2 for index in range(17)], dtype=np.int64)
    probabilities = np.asarray(
        [[0.9, 0.1] if index % 3 else [0.2, 0.8] for index in range(17)],
        dtype=np.float64,
    )
    return evaluate_probabilities(
        sample_ids=[f"{index:064x}" for index in range(17)],
        board_ids=["a" * 64] * 15 + ["b" * 64] * 2,
        cell_indexes=list(range(15)) + [0, 1],
        split_names=["train"] * 17,
        probabilities=probabilities,
        labels=labels,
        class_codes=class_codes,
    )


def test_quality_and_review_replay_keep_partial_board_explicit() -> None:
    samples, metrics = _evaluated()

    replay = build_review_replay(samples)

    assert metrics["sampleCount"] == 17
    assert metrics["macroRecall"] >= 0.0
    assert replay["completeBoardCount"] == 1
    assert replay["resolvedSampleCount"] == 15
    assert replay["correctedBoardCount"] == 1
    assert replay["partialBoardCount"] == 1
    assert replay["partialSampleCount"] == 2
    assert replay["postReviewAccuracy"] == 1.0


def test_prediction_rows_include_deterministic_top_three_order() -> None:
    samples, _ = _evaluated()

    row = samples[1].to_dict(model_version="model-v1")

    assert row["modelVersion"] == "model-v1"
    assert row["alternatives"][0]["symbolCode"] == "cherries"
    assert canonical_report_bytes({"row": row}) == canonical_report_bytes({"row": row})


def test_invalid_cell_index_fails_closed() -> None:
    with pytest.raises(SymbolVerticalSliceError) as error:
        evaluate_probabilities(
            sample_ids=["a" * 64],
            board_ids=["b" * 64],
            cell_indexes=[15],
            split_names=["test"],
            probabilities=np.asarray([[1.0]], dtype=np.float64),
            labels=np.asarray([0], dtype=np.int64),
            class_codes=("star",),
        )

    assert error.value.code == "SYMBOL_VERTICAL_SLICE_CELL_INDEX_INVALID"


def test_runtime_observation_rejects_negative_or_missing_measurement() -> None:
    with pytest.raises(SymbolVerticalSliceError) as error:
        validate_runtime_observation(
            {
                "inferenceMaximumMilliseconds": 1.0,
                "inferenceMedianMilliseconds": 1.0,
                "inferenceMedianMillisecondsPerSample": 0.1,
                "inferenceMinimumMilliseconds": 1.0,
                "inventoryVerificationMilliseconds": -1.0,
                "preprocessingMilliseconds": 1.0,
                "sampleCount": 10,
                "timingRuns": 1,
            }
        )

    assert error.value.code == "SYMBOL_VERTICAL_SLICE_TIMING_INVALID"
