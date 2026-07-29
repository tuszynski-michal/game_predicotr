"""Pure quality and review-replay helpers for the final M6 acceptance slice."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .symbol_confidence import calibration_metrics

VERTICAL_SLICE_VERSION = "classifier-review-vertical-slice-v1"


class SymbolVerticalSliceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class EvaluatedSymbolSample:
    sample_id: str
    board_id: str
    cell_index: int
    split: str
    expected_symbol_code: str
    predicted_symbol_code: str
    confidence: float
    alternatives: tuple[Mapping[str, object], ...]

    def to_dict(self, *, model_version: str) -> dict[str, object]:
        return {
            "alternatives": [dict(value) for value in self.alternatives],
            "boardId": self.board_id,
            "cellIndex": self.cell_index,
            "confidence": round(self.confidence, 8),
            "expectedSymbolCode": self.expected_symbol_code,
            "modelVersion": model_version,
            "predictedSymbolCode": self.predicted_symbol_code,
            "sampleId": self.sample_id,
            "split": self.split,
        }


def canonical_report_bytes(value: Mapping[str, object]) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode()
    except (TypeError, ValueError) as error:
        raise SymbolVerticalSliceError(
            "SYMBOL_VERTICAL_SLICE_REPORT_INVALID",
            "The acceptance report is not canonical JSON.",
        ) from error


def evaluate_probabilities(
    *,
    sample_ids: Sequence[str],
    board_ids: Sequence[str],
    cell_indexes: Sequence[int],
    split_names: Sequence[str],
    probabilities: NDArray[np.float64],
    labels: NDArray[np.int64],
    class_codes: Sequence[str],
) -> tuple[tuple[EvaluatedSymbolSample, ...], dict[str, object]]:
    sample_count = len(sample_ids)
    if (
        sample_count == 0
        or len(board_ids) != sample_count
        or len(cell_indexes) != sample_count
        or len(split_names) != sample_count
        or probabilities.shape != (sample_count, len(class_codes))
        or labels.shape != (sample_count,)
        or len(set(sample_ids)) != sample_count
        or len(set(class_codes)) != len(class_codes)
        or not np.isfinite(probabilities).all()
        or np.any(labels < 0)
        or np.any(labels >= len(class_codes))
    ):
        raise SymbolVerticalSliceError(
            "SYMBOL_VERTICAL_SLICE_SAMPLE_CONTRACT_INVALID",
            "Samples, classes, labels and probabilities must form one complete batch.",
        )
    predictions = np.argmax(probabilities, axis=1)
    results: list[EvaluatedSymbolSample] = []
    for index in range(sample_count):
        cell_index = cell_indexes[index]
        if cell_index < 0 or cell_index >= 15:
            raise SymbolVerticalSliceError(
                "SYMBOL_VERTICAL_SLICE_CELL_INDEX_INVALID",
                "Cell indexes must remain in the row-major range 0..14.",
            )
        ranked = sorted(
            range(len(class_codes)),
            key=lambda class_index: (
                -float(probabilities[index, class_index]),
                class_codes[class_index],
            ),
        )[:3]
        alternatives = tuple(
            {
                "confidence": round(float(probabilities[index, class_index]), 8),
                "symbolCode": class_codes[class_index],
            }
            for class_index in ranked
        )
        results.append(
            EvaluatedSymbolSample(
                sample_id=sample_ids[index],
                board_id=board_ids[index],
                cell_index=cell_index,
                split=split_names[index],
                expected_symbol_code=class_codes[int(labels[index])],
                predicted_symbol_code=class_codes[int(predictions[index])],
                confidence=float(probabilities[index, predictions[index]]),
                alternatives=alternatives,
            )
        )
    metrics = calibration_metrics(probabilities, labels, class_codes)
    recalls = [float(row["recall"]) for row in metrics["perClass"] if isinstance(row, Mapping)]
    metrics["macroRecall"] = round(sum(recalls) / len(recalls), 8)
    return tuple(results), metrics


def build_review_replay(
    samples: Sequence[EvaluatedSymbolSample],
) -> dict[str, object]:
    """Summarize whole-board review without accepting legacy partial boards."""

    grouped: dict[str, list[EvaluatedSymbolSample]] = defaultdict(list)
    for sample in samples:
        grouped[sample.board_id].append(sample)

    accepted_boards = 0
    corrected_boards = 0
    corrected_cells = 0
    complete_sample_count = 0
    partial_board_count = 0
    partial_sample_count = 0
    complete_board_ids: list[str] = []
    for board_id, board_samples in sorted(grouped.items()):
        indexes = {sample.cell_index for sample in board_samples}
        if len(board_samples) != 15 or indexes != set(range(15)):
            partial_board_count += 1
            partial_sample_count += len(board_samples)
            continue
        complete_board_ids.append(board_id)
        complete_sample_count += 15
        board_corrections = sum(
            sample.predicted_symbol_code != sample.expected_symbol_code for sample in board_samples
        )
        corrected_cells += board_corrections
        if board_corrections:
            corrected_boards += 1
        else:
            accepted_boards += 1

    complete_board_count = accepted_boards + corrected_boards
    if complete_board_count == 0:
        raise SymbolVerticalSliceError(
            "SYMBOL_VERTICAL_SLICE_COMPLETE_BOARD_MISSING",
            "At least one complete reviewed board is required.",
        )
    return {
        "acceptedBoardCount": accepted_boards,
        "completeBoardCount": complete_board_count,
        "completeBoardIds": complete_board_ids,
        "correctedBoardCount": corrected_boards,
        "correctedCellCount": corrected_cells,
        "partialBoardCount": partial_board_count,
        "partialSampleCount": partial_sample_count,
        "postReviewAccuracy": 1.0,
        "postReviewMacroRecall": 1.0,
        "resolvedSampleCount": complete_sample_count,
    }


def validate_runtime_observation(value: Mapping[str, object]) -> dict[str, object]:
    required_numbers = (
        "inventoryVerificationMilliseconds",
        "preprocessingMilliseconds",
        "inferenceMedianMilliseconds",
        "inferenceMinimumMilliseconds",
        "inferenceMaximumMilliseconds",
        "inferenceMedianMillisecondsPerSample",
    )
    for key in required_numbers:
        number = value.get(key)
        if (
            not isinstance(number, int | float)
            or isinstance(number, bool)
            or not math.isfinite(float(number))
            or float(number) < 0.0
        ):
            raise SymbolVerticalSliceError(
                "SYMBOL_VERTICAL_SLICE_TIMING_INVALID",
                f"Runtime observation {key} must be finite and non-negative.",
            )
    timing_runs = value.get("timingRuns")
    sample_count = value.get("sampleCount")
    if (
        not isinstance(timing_runs, int)
        or isinstance(timing_runs, bool)
        or timing_runs < 1
        or not isinstance(sample_count, int)
        or isinstance(sample_count, bool)
        or sample_count < 1
    ):
        raise SymbolVerticalSliceError(
            "SYMBOL_VERTICAL_SLICE_TIMING_INVALID",
            "Runtime observation counts must be positive integers.",
        )
    return dict(value)


__all__ = [
    "VERTICAL_SLICE_VERSION",
    "EvaluatedSymbolSample",
    "SymbolVerticalSliceError",
    "build_review_replay",
    "canonical_report_bytes",
    "evaluate_probabilities",
    "validate_runtime_observation",
]
