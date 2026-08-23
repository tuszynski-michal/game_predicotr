"""Immutable, read-only A/B evidence for board-cell geometry and symbol predictions."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import fmean

import cv2
import numpy as np
from numpy.typing import NDArray

from .board_cell_geometry_contract import canonical_json_bytes

DIAGNOSIS_VERSION = "grid-cropping-vs-symbol-model-diagnosis-v1"
DIAGNOSIS_SCHEMA_VERSION = 1
CELL_COUNT = 15


class GridSymbolDiagnosisError(ValueError):
    """Stable error raised when a diagnostic comparison is not trustworthy."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class CellPrediction:
    symbol_code: str
    confidence: float

    def __post_init__(self) -> None:
        if not self.symbol_code:
            raise GridSymbolDiagnosisError(
                "GRID_SYMBOL_DIAGNOSIS_SYMBOL_INVALID", "A symbol code is required."
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise GridSymbolDiagnosisError(
                "GRID_SYMBOL_DIAGNOSIS_CONFIDENCE_INVALID",
                "Prediction confidence must be within [0, 1].",
            )

    def to_dict(self) -> dict[str, object]:
        return {"confidence": round(self.confidence, 8), "symbolCode": self.symbol_code}


@dataclass(frozen=True, slots=True)
class DiagnosticBoard:
    """One human-resolved board compared under two crop geometries."""

    board_id: str
    sequence_number: int
    position_index: int
    source_checksum_sha256: str
    source_relative_path: str
    staging_label: str
    baseline_geometry_version: str
    baseline_cropper_version: str
    corrected_geometry_version: str
    corrected_cropper_version: str
    baseline_model_fingerprint: str
    comparison_model_fingerprint: str
    expected_symbols: tuple[str, ...]
    baseline_predictions: tuple[CellPrediction, ...]
    corrected_predictions: tuple[CellPrediction, ...]

    def __post_init__(self) -> None:
        if self.sequence_number < 1 or not 0 <= self.position_index <= 8:
            raise GridSymbolDiagnosisError(
                "GRID_SYMBOL_DIAGNOSIS_BOARD_INVALID", "Board sequence or position is invalid."
            )
        if not self.board_id or not self.staging_label:
            raise GridSymbolDiagnosisError(
                "GRID_SYMBOL_DIAGNOSIS_BOARD_INVALID",
                "Board identity and staging label are required.",
            )
        if len(self.source_checksum_sha256) != 64:
            raise GridSymbolDiagnosisError(
                "GRID_SYMBOL_DIAGNOSIS_SOURCE_INVALID", "Source checksum must be SHA-256."
            )
        for values, label in (
            (self.expected_symbols, "expected symbols"),
            (self.baseline_predictions, "baseline predictions"),
            (self.corrected_predictions, "corrected predictions"),
        ):
            if len(values) != CELL_COUNT:
                raise GridSymbolDiagnosisError(
                    "GRID_SYMBOL_DIAGNOSIS_CELL_COUNT_INVALID",
                    f"A board must contain exactly {CELL_COUNT} {label}.",
                )
        if not all(self.expected_symbols):
            raise GridSymbolDiagnosisError(
                "GRID_SYMBOL_DIAGNOSIS_SYMBOL_INVALID", "Expected symbol codes are required."
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "baseline": {
                "cropperVersion": self.baseline_cropper_version,
                "geometryVersion": self.baseline_geometry_version,
                "predictions": [value.to_dict() for value in self.baseline_predictions],
            },
            "boardId": self.board_id,
            "comparison": {
                "cropperVersion": self.corrected_cropper_version,
                "geometryVersion": self.corrected_geometry_version,
                "predictions": [value.to_dict() for value in self.corrected_predictions],
            },
            "comparisonModelFingerprintSha256": self.comparison_model_fingerprint,
            "expectedSymbols": list(self.expected_symbols),
            "positionIndex": self.position_index,
            "sequenceNumber": self.sequence_number,
            "sourceImageChecksumSha256": self.source_checksum_sha256,
            "sourceImageRelativePath": self.source_relative_path,
            "stagingLabel": self.staging_label,
        }


def production_preprocess_rgb(rgb: NDArray[np.uint8], *, input_size: int) -> NDArray[np.float32]:
    """Mirror the production ONNX tensor contract without modifying production code."""

    if input_size < 16 or rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise GridSymbolDiagnosisError(
            "GRID_SYMBOL_DIAGNOSIS_PREPROCESS_INPUT_INVALID",
            "Expected an RGB uint8 crop and a valid model input size.",
        )
    model_rgb = (
        rgb
        if rgb.shape[:2] == (input_size, input_size)
        else cv2.resize(rgb, (input_size, input_size), interpolation=cv2.INTER_AREA)
    )
    normalized = model_rgb.astype(np.float32).transpose(2, 0, 1) / 255.0
    return ((normalized - 0.5) / 0.5).astype(np.float32)


def build_diagnostic_document(
    boards: Sequence[DiagnosticBoard],
    *,
    comparison_model_fingerprint: str,
    excluded_counts: Mapping[str, int] | None = None,
) -> dict[str, object]:
    """Build a canonical report only when every A/B board pins one model."""

    if not boards:
        raise GridSymbolDiagnosisError(
            "GRID_SYMBOL_DIAGNOSIS_EMPTY", "At least one comparable board is required."
        )
    if len(comparison_model_fingerprint) != 64:
        raise GridSymbolDiagnosisError(
            "GRID_SYMBOL_DIAGNOSIS_MODEL_INVALID", "Comparison model fingerprint must be SHA-256."
        )
    ordered = tuple(sorted(boards, key=lambda board: (board.sequence_number, board.board_id)))
    if len({board.board_id for board in ordered}) != len(ordered):
        raise GridSymbolDiagnosisError(
            "GRID_SYMBOL_DIAGNOSIS_BOARD_DUPLICATE", "Diagnostic boards must be unique."
        )
    mismatched = [
        board.board_id
        for board in ordered
        if board.baseline_model_fingerprint != comparison_model_fingerprint
        or board.comparison_model_fingerprint != comparison_model_fingerprint
    ]
    if mismatched:
        raise GridSymbolDiagnosisError(
            "GRID_SYMBOL_DIAGNOSIS_MODEL_MISMATCH",
            "A/B inputs must use the same pinned model fingerprint.",
        )
    baseline = _metrics(ordered, variant="baseline")
    corrected = _metrics(ordered, variant="corrected")
    by_staging = {
        staging: {
            "baseline": _metrics(items, variant="baseline"),
            "corrected": _metrics(items, variant="corrected"),
        }
        for staging, items in _group_by_staging(ordered).items()
    }
    return {
        "boards": [board.to_dict() for board in ordered],
        "comparisonModelFingerprintSha256": comparison_model_fingerprint,
        "excludedBoardCounts": dict(sorted((excluded_counts or {}).items())),
        "schemaVersion": DIAGNOSIS_SCHEMA_VERSION,
        "summary": {
            "baseline": baseline,
            "corrected": corrected,
            "delta": {
                "meanManualCorrectionsPerBoard": round(
                    corrected["meanManualCorrectionsPerBoard"]
                    - baseline["meanManualCorrectionsPerBoard"],
                    8,
                ),
                "symbolAccuracy": round(
                    corrected["symbolAccuracy"] - baseline["symbolAccuracy"], 8
                ),
                "wholeBoardAccuracy": round(
                    corrected["wholeBoardAccuracy"] - baseline["wholeBoardAccuracy"], 8
                ),
            },
            "byStaging": by_staging,
        },
        "version": DIAGNOSIS_VERSION,
    }


def document_checksum_sha256(document: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_json_bytes(document)).hexdigest()


def _group_by_staging(
    boards: Sequence[DiagnosticBoard],
) -> dict[str, tuple[DiagnosticBoard, ...]]:
    grouped: dict[str, list[DiagnosticBoard]] = {}
    for board in boards:
        grouped.setdefault(board.staging_label, []).append(board)
    return {key: tuple(value) for key, value in sorted(grouped.items())}


def _metrics(boards: Sequence[DiagnosticBoard], *, variant: str) -> dict[str, object]:
    predictions = (
        (board.baseline_predictions if variant == "baseline" else board.corrected_predictions)
        for board in boards
    )
    total = 0
    correct = 0
    complete = 0
    corrections: list[int] = []
    correct_confidence: list[float] = []
    incorrect_confidence: list[float] = []
    confusion: Counter[tuple[str, str]] = Counter()
    for board, values in zip(boards, predictions, strict=True):
        board_correct = 0
        for expected, prediction in zip(board.expected_symbols, values, strict=True):
            total += 1
            confusion[(expected, prediction.symbol_code)] += 1
            if expected == prediction.symbol_code:
                correct += 1
                board_correct += 1
                correct_confidence.append(prediction.confidence)
            else:
                incorrect_confidence.append(prediction.confidence)
        corrections.append(CELL_COUNT - board_correct)
        if board_correct == CELL_COUNT:
            complete += 1
    return {
        "boardCount": len(boards),
        "cellCount": total,
        "confidence": {
            "meanCorrect": _mean(correct_confidence),
            "meanIncorrect": _mean(incorrect_confidence),
        },
        "confusion": [
            {"count": count, "expectedSymbolCode": expected, "predictedSymbolCode": predicted}
            for (expected, predicted), count in sorted(confusion.items())
        ],
        "meanManualCorrectionsPerBoard": round(fmean(corrections), 8),
        "symbolAccuracy": round(correct / total, 8),
        "wholeBoardAccuracy": round(complete / len(boards), 8),
    }


def _mean(values: Sequence[float]) -> float | None:
    return None if not values else round(fmean(values), 8)


__all__ = [
    "CELL_COUNT",
    "DIAGNOSIS_SCHEMA_VERSION",
    "DIAGNOSIS_VERSION",
    "CellPrediction",
    "DiagnosticBoard",
    "GridSymbolDiagnosisError",
    "build_diagnostic_document",
    "document_checksum_sha256",
    "production_preprocess_rgb",
]
