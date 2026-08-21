"""Confidence calibration and deterministic active-learning selection."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

import numpy as np
from numpy.typing import ArrayLike, NDArray

CALIBRATION_VERSION = "symbol-temperature-calibration-v2-safe-floor-v1"
CONFIDENCE_POLICY_VERSION = "symbol-confidence-policy-v1"
ACTIVE_LEARNING_VERSION = "whole-layout-active-learning-v1"
CALIBRATION_BIN_COUNT = 10
AUTO_ACCEPT_TARGET_PRECISION = 0.95
AUTO_ACCEPT_MINIMUM_SAMPLES = 20
AUTO_ACCEPT_MINIMUM_CLASS_SAMPLES = 3
AUTO_ACCEPT_MINIMUM_CLASS_PRECISION = 0.90
DEFAULT_ACTIVE_LEARNING_BATCH_SIZE = 30
# A tiny perfect cohort can mathematically prefer a near-zero temperature.
# That turns unknown/blank crops into almost 100% predictions.  Calibration is
# allowed to sharpen only within a conservative range; geometry still has its
# own independent validity gate.
TEMPERATURE_MINIMUM = 0.50
TEMPERATURE_MAXIMUM = 20.0
TEMPERATURE_SEARCH_ITERATIONS = 96

FloatMatrix = NDArray[np.float64]
IntVector = NDArray[np.int64]


class SymbolConfidenceError(ValueError):
    """Stable calibration or selection failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ActiveLearningCell:
    sample_id: str
    cell_index: int
    row_index: int
    column_index: int
    probabilities: tuple[float, ...]
    crop_relative_path: str = ""
    observation_id: str = ""


@dataclass(frozen=True, slots=True)
class ActiveLearningBoard:
    board_id: str
    sequence_number: int
    source_image_id: str
    source_image_checksum: str
    source_group: str
    board_relative_path: str
    cells: tuple[ActiveLearningCell, ...]


def _validated_logits_labels(
    logits: ArrayLike,
    labels: ArrayLike,
) -> tuple[FloatMatrix, IntVector]:
    values = cast(FloatMatrix, np.asarray(logits, dtype=np.float64))
    targets = cast(IntVector, np.asarray(labels, dtype=np.int64))
    if (
        values.ndim != 2
        or targets.ndim != 1
        or values.shape[0] != targets.shape[0]
        or values.shape[0] == 0
        or values.shape[1] < 2
        or np.any(targets < 0)
        or np.any(targets >= values.shape[1])
        or not np.isfinite(values).all()
    ):
        raise SymbolConfidenceError(
            "SYMBOL_CONFIDENCE_INPUT_INVALID",
            "Logits and labels must be finite non-empty N x C and N arrays.",
        )
    return values, targets


def calibrated_probabilities(
    logits: ArrayLike,
    temperature: float,
) -> FloatMatrix:
    """Apply scalar temperature scaling without changing class order."""

    values = cast(FloatMatrix, np.asarray(logits, dtype=np.float64))
    if (
        values.ndim != 2
        or values.shape[0] == 0
        or values.shape[1] < 2
        or not np.isfinite(values).all()
        or not math.isfinite(temperature)
        or temperature <= 0.0
    ):
        raise SymbolConfidenceError(
            "SYMBOL_CONFIDENCE_INPUT_INVALID",
            "Finite non-empty logits and a positive temperature are required.",
        )
    scaled = values / temperature
    scaled -= scaled.max(axis=1, keepdims=True)
    exponentials = np.exp(scaled)
    probabilities = exponentials / exponentials.sum(axis=1, keepdims=True)
    if not np.isfinite(probabilities).all():
        raise SymbolConfidenceError(
            "SYMBOL_CONFIDENCE_OUTPUT_NON_FINITE",
            "Temperature scaling produced non-finite probabilities.",
        )
    return cast(FloatMatrix, probabilities)


def _negative_log_likelihood(
    logits: FloatMatrix,
    labels: IntVector,
    log_temperature: float,
) -> float:
    probabilities = calibrated_probabilities(logits, math.exp(log_temperature))
    selected = probabilities[np.arange(labels.size), labels]
    return float(-np.log(np.clip(selected, 1e-15, 1.0)).mean())


def fit_temperature(
    logits: ArrayLike,
    labels: ArrayLike,
) -> float:
    """Fit one temperature with a fixed bounded golden-section search."""

    values, targets = _validated_logits_labels(logits, labels)
    lower = math.log(TEMPERATURE_MINIMUM)
    upper = math.log(TEMPERATURE_MAXIMUM)
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    left = upper - ratio * (upper - lower)
    right = lower + ratio * (upper - lower)
    left_loss = _negative_log_likelihood(values, targets, left)
    right_loss = _negative_log_likelihood(values, targets, right)
    for _ in range(TEMPERATURE_SEARCH_ITERATIONS):
        if left_loss <= right_loss:
            upper = right
            right = left
            right_loss = left_loss
            left = upper - ratio * (upper - lower)
            left_loss = _negative_log_likelihood(values, targets, left)
        else:
            lower = left
            left = right
            left_loss = right_loss
            right = lower + ratio * (upper - lower)
            right_loss = _negative_log_likelihood(values, targets, right)
    fitted = math.exp((lower + upper) / 2.0)
    if _negative_log_likelihood(values, targets, 0.0) <= _negative_log_likelihood(
        values,
        targets,
        math.log(fitted),
    ):
        return 1.0
    return fitted


def _round(value: float) -> float:
    return round(value, 8)


def calibration_metrics(
    probabilities: ArrayLike,
    labels: ArrayLike,
    class_codes: Sequence[str],
    *,
    bin_count: int = CALIBRATION_BIN_COUNT,
) -> dict[str, object]:
    """Return calibration, reliability and per-class quality evidence."""

    values = cast(FloatMatrix, np.asarray(probabilities, dtype=np.float64))
    targets = cast(IntVector, np.asarray(labels, dtype=np.int64))
    if (
        values.ndim != 2
        or targets.ndim != 1
        or values.shape != (targets.size, len(class_codes))
        or targets.size == 0
        or len(set(class_codes)) != len(class_codes)
        or bin_count < 2
        or not np.isfinite(values).all()
        or np.any(values < 0.0)
        or not np.allclose(values.sum(axis=1), 1.0, atol=1e-8)
        or np.any(targets < 0)
        or np.any(targets >= len(class_codes))
    ):
        raise SymbolConfidenceError(
            "SYMBOL_CONFIDENCE_METRICS_INVALID",
            "Probabilities, labels, classes or bin count are invalid.",
        )
    predictions = np.argmax(values, axis=1)
    confidence = np.max(values, axis=1)
    correct = predictions == targets
    selected = values[np.arange(targets.size), targets]
    one_hot = np.eye(len(class_codes), dtype=np.float64)[targets]
    reliability: list[dict[str, object]] = []
    ece = 0.0
    for index in range(bin_count):
        lower = index / bin_count
        upper = (index + 1) / bin_count
        mask = (confidence >= lower) & (
            confidence <= upper if index == bin_count - 1 else confidence < upper
        )
        count = int(mask.sum())
        accuracy = float(correct[mask].mean()) if count else 0.0
        mean_confidence = float(confidence[mask].mean()) if count else 0.0
        ece += (count / targets.size) * abs(accuracy - mean_confidence)
        reliability.append(
            {
                "accuracy": _round(accuracy),
                "count": count,
                "lowerInclusive": _round(lower),
                "meanConfidence": _round(mean_confidence),
                "upperInclusive": index == bin_count - 1,
                "upperValue": _round(upper),
            }
        )
    per_class: list[dict[str, object]] = []
    for class_index, symbol_code in enumerate(class_codes):
        actual = targets == class_index
        predicted = predictions == class_index
        true_positive = int(np.count_nonzero(actual & predicted))
        support = int(actual.sum())
        predicted_count = int(predicted.sum())
        per_class.append(
            {
                "meanConfidenceWhenPredicted": _round(
                    float(confidence[predicted].mean()) if predicted_count else 0.0
                ),
                "precision": _round(true_positive / predicted_count if predicted_count else 0.0),
                "predictedCount": predicted_count,
                "recall": _round(true_positive / support if support else 0.0),
                "support": support,
                "symbolCode": symbol_code,
            }
        )
    return {
        "accuracy": _round(float(correct.mean())),
        "brierScore": _round(float(np.square(values - one_hot).sum(axis=1).mean())),
        "ece": _round(ece),
        "meanConfidence": _round(float(confidence.mean())),
        "negativeLogLikelihood": _round(float(-np.log(np.clip(selected, 1e-15, 1.0)).mean())),
        "perClass": per_class,
        "reliabilityBins": reliability,
        "sampleCount": int(targets.size),
    }


def _wilson_lower_bound(correct: int, total: int, z: float = 1.959963984540054) -> float:
    if total <= 0:
        return 0.0
    proportion = correct / total
    denominator = 1.0 + z * z / total
    centre = proportion + z * z / (2.0 * total)
    radius = z * math.sqrt((proportion * (1.0 - proportion) + z * z / (4.0 * total)) / total)
    return max(0.0, (centre - radius) / denominator)


def threshold_evidence(
    probabilities: ArrayLike,
    labels: ArrayLike,
    class_codes: Sequence[str],
) -> tuple[dict[str, object], ...]:
    """Measure every observable validation confidence threshold."""

    values = cast(FloatMatrix, np.asarray(probabilities, dtype=np.float64))
    targets = cast(IntVector, np.asarray(labels, dtype=np.int64))
    calibration_metrics(values, targets, class_codes)
    predictions = np.argmax(values, axis=1)
    confidence = np.max(values, axis=1)
    thresholds = sorted({1.0, *(float(value) for value in confidence)}, reverse=True)
    rows: list[dict[str, object]] = []
    for threshold in thresholds:
        accepted = confidence >= threshold
        count = int(accepted.sum())
        correct = int(np.count_nonzero(accepted & (predictions == targets)))
        class_rows: list[dict[str, object]] = []
        class_gate = True
        for class_index, symbol_code in enumerate(class_codes):
            predicted_class = accepted & (predictions == class_index)
            class_count = int(predicted_class.sum())
            class_correct = int(np.count_nonzero(predicted_class & (targets == class_index)))
            precision = class_correct / class_count if class_count else 0.0
            if (
                class_count < AUTO_ACCEPT_MINIMUM_CLASS_SAMPLES
                or precision < AUTO_ACCEPT_MINIMUM_CLASS_PRECISION
            ):
                class_gate = False
            class_rows.append(
                {
                    "correctCount": class_correct,
                    "precision": _round(precision),
                    "sampleCount": class_count,
                    "symbolCode": symbol_code,
                }
            )
        precision = correct / count if count else 0.0
        quality_gate = (
            count >= AUTO_ACCEPT_MINIMUM_SAMPLES
            and precision >= AUTO_ACCEPT_TARGET_PRECISION
            and class_gate
        )
        rows.append(
            {
                "classEvidence": class_rows,
                "correctCount": correct,
                "coverage": _round(count / targets.size),
                "precision": _round(precision),
                "qualityGatePassed": quality_gate,
                "sampleCount": count,
                "threshold": _round(threshold),
                "wilson95LowerPrecision": _round(_wilson_lower_bound(correct, count)),
            }
        )
    return tuple(rows)


def build_confidence_policy(
    threshold_rows: Sequence[Mapping[str, object]],
    *,
    model_status: str,
    bootstrap_target_met: bool,
) -> dict[str, object]:
    """Fail closed unless both maturity and measured threshold gates pass."""

    def integer(row: Mapping[str, object], key: str) -> int:
        value = row.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            raise SymbolConfidenceError(
                "SYMBOL_CONFIDENCE_THRESHOLD_INVALID",
                f"Threshold evidence {key} must be an integer.",
            )
        return value

    def number(row: Mapping[str, object], key: str) -> float:
        value = row.get(key)
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise SymbolConfidenceError(
                "SYMBOL_CONFIDENCE_THRESHOLD_INVALID",
                f"Threshold evidence {key} must be numeric.",
            )
        return float(value)

    passing = [row for row in threshold_rows if row.get("qualityGatePassed") is True]
    candidate = (
        max(
            passing,
            key=lambda row: (
                integer(row, "sampleCount"),
                -number(row, "threshold"),
            ),
        )
        if passing
        else None
    )
    reason_codes: list[str] = []
    if model_status != "production_candidate":
        reason_codes.append("MODEL_NOT_PRODUCTION_CANDIDATE")
    if not bootstrap_target_met:
        reason_codes.append("BOOTSTRAP_SAMPLE_TARGET_NOT_MET")
    if candidate is None:
        reason_codes.append("VALIDATION_THRESHOLD_GATE_NOT_MET")
    enabled = not reason_codes
    selected_threshold = candidate.get("threshold") if enabled and candidate is not None else None
    return {
        "autoAccept": {
            "enabled": enabled,
            "minimumClassPrecision": AUTO_ACCEPT_MINIMUM_CLASS_PRECISION,
            "minimumClassSamples": AUTO_ACCEPT_MINIMUM_CLASS_SAMPLES,
            "minimumOverallPrecision": AUTO_ACCEPT_TARGET_PRECISION,
            "minimumOverallSamples": AUTO_ACCEPT_MINIMUM_SAMPLES,
            "reasonCodes": reason_codes,
            "threshold": selected_threshold,
        },
        "automaticReject": {
            "enabled": False,
            "reasonCodes": ["HUMAN_DECISION_REQUIRED"],
            "threshold": None,
        },
        "manualReview": {
            "enabled": True,
            "rule": "all_predictions_not_explicitly_auto_accepted",
            "threshold": 0.0 if not enabled else selected_threshold,
        },
        "policyVersion": CONFIDENCE_POLICY_VERSION,
    }


def _entropy(probabilities: FloatMatrix) -> NDArray[np.float64]:
    return cast(
        NDArray[np.float64],
        -np.sum(
            probabilities * np.log(np.clip(probabilities, 1e-15, 1.0)),
            axis=1,
        )
        / math.log(probabilities.shape[1]),
    )


def _jensen_shannon(left: NDArray[np.float64], right: NDArray[np.float64]) -> float:
    middle = (left + right) / 2.0
    left_term = np.sum(left * np.log(np.clip(left / middle, 1e-15, None)))
    right_term = np.sum(right * np.log(np.clip(right / middle, 1e-15, None)))
    return float((left_term + right_term) / (2.0 * math.log(2.0)))


def select_active_learning_boards(
    boards: Sequence[ActiveLearningBoard],
    class_codes: Sequence[str],
    *,
    batch_size: int = DEFAULT_ACTIVE_LEARNING_BATCH_SIZE,
) -> tuple[dict[str, object], ...]:
    """Select complete boards with uncertainty and deterministic diversity."""

    if (
        not boards
        or batch_size <= 0
        or not class_codes
        or len(set(class_codes)) != len(class_codes)
        or len({board.board_id for board in boards}) != len(boards)
    ):
        raise SymbolConfidenceError(
            "SYMBOL_ACTIVE_LEARNING_INPUT_INVALID",
            "Unique boards, classes and a positive batch size are required.",
        )
    parsed: dict[str, tuple[ActiveLearningBoard, FloatMatrix]] = {}
    predicted_counts: Counter[int] = Counter()
    for board in boards:
        if (
            board.sequence_number <= 0
            or len(board.cells) != 15
            or sorted(cell.cell_index for cell in board.cells) != list(range(15))
            or any(
                cell.row_index * 5 + cell.column_index != cell.cell_index for cell in board.cells
            )
        ):
            raise SymbolConfidenceError(
                "SYMBOL_ACTIVE_LEARNING_BOARD_INCOMPLETE",
                "Every candidate board must contain exactly 15 row-major cells.",
            )
        probabilities = np.asarray(
            [cell.probabilities for cell in sorted(board.cells, key=lambda item: item.cell_index)],
            dtype=np.float64,
        )
        if (
            probabilities.shape != (15, len(class_codes))
            or not np.isfinite(probabilities).all()
            or np.any(probabilities < 0.0)
            or not np.allclose(probabilities.sum(axis=1), 1.0, atol=1e-8)
        ):
            raise SymbolConfidenceError(
                "SYMBOL_ACTIVE_LEARNING_PROBABILITIES_INVALID",
                "Every cell must contain one finite normalized class vector.",
            )
        predicted_counts.update(int(value) for value in np.argmax(probabilities, axis=1))
        parsed[board.board_id] = (board, probabilities)

    maximum_predicted_count = max(predicted_counts.values())
    selected: list[dict[str, object]] = []
    selected_representations: list[NDArray[np.float64]] = []
    selected_sources: set[str] = set()
    remaining = set(parsed)
    while remaining and len(selected) < min(batch_size, len(boards)):
        unseen_source_exists = any(
            parsed[board_id][0].source_image_checksum not in selected_sources
            for board_id in remaining
        )
        candidates: list[tuple[float, int, str, dict[str, object], NDArray[np.float64], str]] = []
        for board_id in remaining:
            board, probabilities = parsed[board_id]
            if unseen_source_exists and board.source_image_checksum in selected_sources:
                continue
            entropies = _entropy(probabilities)
            uncertainty = float(np.mean(np.sort(entropies)[-5:]))
            representation = probabilities.mean(axis=0)
            diversity = (
                1.0
                if not selected_representations
                else min(
                    _jensen_shannon(representation, previous)
                    for previous in selected_representations
                )
            )
            predicted = np.argmax(probabilities, axis=1)
            rarity = float(
                np.mean(
                    [
                        1.0 - predicted_counts[int(value)] / maximum_predicted_count
                        for value in predicted
                    ]
                )
            )
            source_novelty = 1.0 if board.source_image_checksum not in selected_sources else 0.0
            score = 0.65 * uncertainty + 0.15 * diversity + 0.15 * source_novelty + 0.05 * rarity
            cells = []
            ordered_cells = sorted(board.cells, key=lambda item: item.cell_index)
            for cell, vector, entropy in zip(
                ordered_cells,
                probabilities,
                entropies,
                strict=True,
            ):
                order = np.argsort(-vector, kind="stable")[:3]
                cells.append(
                    {
                        "alternatives": [
                            {
                                "confidence": _round(float(vector[index])),
                                "symbolCode": class_codes[int(index)],
                            }
                            for index in order
                        ],
                        "cellIndex": cell.cell_index,
                        "columnIndex": cell.column_index,
                        "confidence": _round(float(vector[order[0]])),
                        "cropRelativePath": cell.crop_relative_path,
                        "entropy": _round(float(entropy)),
                        "observationId": cell.observation_id,
                        "predictedSymbolCode": class_codes[int(order[0])],
                        "rowIndex": cell.row_index,
                        "sampleId": cell.sample_id,
                    }
                )
            row: dict[str, object] = {
                "boardId": board.board_id,
                "boardRelativePath": board.board_relative_path,
                "cells": cells,
                "predictedClassRarityScore": _round(rarity),
                "predictionDiversityScore": _round(diversity),
                "selectionScore": _round(score),
                "sequenceNumber": board.sequence_number,
                "sourceGroup": board.source_group,
                "sourceImageChecksumSha256": board.source_image_checksum,
                "sourceImageId": board.source_image_id,
                "sourceNoveltyScore": _round(source_novelty),
                "uncertaintyScore": _round(uncertainty),
            }
            candidates.append(
                (
                    score,
                    board.sequence_number,
                    board_id,
                    row,
                    representation,
                    board.source_image_checksum,
                )
            )
        _, _, chosen_id, row, representation, source_checksum = min(
            candidates,
            key=lambda value: (-value[0], value[1], value[2]),
        )
        row["selectionRank"] = len(selected) + 1
        selected.append(row)
        selected_representations.append(representation)
        selected_sources.add(source_checksum)
        remaining.remove(chosen_id)
    return tuple(selected)


__all__ = [
    "ACTIVE_LEARNING_VERSION",
    "AUTO_ACCEPT_MINIMUM_CLASS_PRECISION",
    "AUTO_ACCEPT_MINIMUM_CLASS_SAMPLES",
    "AUTO_ACCEPT_MINIMUM_SAMPLES",
    "AUTO_ACCEPT_TARGET_PRECISION",
    "ActiveLearningBoard",
    "ActiveLearningCell",
    "CALIBRATION_VERSION",
    "CONFIDENCE_POLICY_VERSION",
    "DEFAULT_ACTIVE_LEARNING_BATCH_SIZE",
    "SymbolConfidenceError",
    "build_confidence_policy",
    "calibrated_probabilities",
    "calibration_metrics",
    "fit_temperature",
    "select_active_learning_boards",
    "threshold_evidence",
]
