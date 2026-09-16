"""Immutable cohort and residual analysis for verified v19 symbol crops."""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from statistics import fmean
from typing import Literal, cast

from game_predictor_worker.symbols.training_dataset import (
    DEFAULT_SPLIT_SEED,
    SplitName,
    build_balanced_source_assignments,
)

from .board_cell_geometry_contract import BOARD_CELL_GEOMETRY_VERSION, canonical_json_bytes
from .board_cell_geometry_crops import CROPPER_VERSION
from .grid_symbol_diagnosis import CellPrediction

COHORT_SCHEMA_VERSION = 1
COHORT_VERSION = "v19-symbol-residual-cohort-v1"
EVALUATION_SCHEMA_VERSION = 1
EVALUATION_VERSION = "v19-symbol-residual-evaluation-v1"
PREPROCESSING_VERSION = "rgb-64-float32-chw-minus-one-to-one-v1"
CELL_COUNT = 15
HIGH_CONFIDENCE_THRESHOLD = 0.99
MINIMUM_BOARD_COUNT = 300
REQUIRED_STAGING_COUNT = 6

ResidualClass = Literal["M1", "M2", "P1", "OPEN"]


class V19SymbolResidualError(ValueError):
    """Stable fail-closed error for an untrustworthy residual analysis."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ResidualCell:
    cell_index: int
    symbol_code: str
    crop_checksum_sha256: str
    crop_relative_path: str

    def __post_init__(self) -> None:
        if not 0 <= self.cell_index < CELL_COUNT or not self.symbol_code:
            raise _error("V19_SYMBOL_COHORT_CELL_INVALID", "A cell label or index is invalid.")
        _require_sha256(self.crop_checksum_sha256, "crop checksum")
        relative = PurePosixPath(self.crop_relative_path)
        if (
            not self.crop_relative_path
            or "\\" in self.crop_relative_path
            or relative.is_absolute()
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise _error("V19_SYMBOL_COHORT_CROP_PATH_INVALID", "A crop path is invalid.")

    def to_dict(self) -> dict[str, object]:
        return {
            "cellIndex": self.cell_index,
            "columnIndex": self.cell_index % 5,
            "cropChecksumSha256": self.crop_checksum_sha256,
            "cropRelativePath": self.crop_relative_path,
            "cropSampleId": hashlib.sha256(
                (f"{self.crop_checksum_sha256}\0{self.cell_index}\0{self.symbol_code}").encode()
            ).hexdigest(),
            "rowIndex": self.cell_index // 5,
            "symbolCode": self.symbol_code,
        }


@dataclass(frozen=True, slots=True)
class ResidualBoard:
    board_id: str
    review_item_id: str
    import_job_id: str
    decision_status: Literal["accepted", "corrected"]
    resolution_revision: int
    sequence_number: int
    position_index: int
    staging_label: str
    source_image_id: str
    source_checksum_sha256: str
    source_relative_path: str
    geometry_provenance: Literal["persisted_v19", "read_only_estimated_v19"]
    cells: tuple[ResidualCell, ...]

    def __post_init__(self) -> None:
        if (
            not self.board_id
            or not self.review_item_id
            or not self.import_job_id
            or self.resolution_revision < 1
            or self.sequence_number < 1
            or not 0 <= self.position_index <= 8
            or not self.staging_label
        ):
            raise _error("V19_SYMBOL_COHORT_BOARD_INVALID", "A board identity is invalid.")
        _require_sha256(self.source_checksum_sha256, "source checksum")
        if [cell.cell_index for cell in self.cells] != list(range(CELL_COUNT)):
            raise _error(
                "V19_SYMBOL_COHORT_BOARD_INCOMPLETE",
                "Every board must contain exactly fifteen row-major v19 crops.",
            )

    def to_dict(self, *, split: SplitName) -> dict[str, object]:
        return {
            "boardId": self.board_id,
            "cells": [cell.to_dict() for cell in self.cells],
            "decisionStatus": self.decision_status,
            "geometryProvenance": self.geometry_provenance,
            "geometryVersion": BOARD_CELL_GEOMETRY_VERSION,
            "importJobId": self.import_job_id,
            "positionIndex": self.position_index,
            "resolutionRevision": self.resolution_revision,
            "reviewItemId": self.review_item_id,
            "sequenceNumber": self.sequence_number,
            "source": {
                "checksumSha256": self.source_checksum_sha256,
                "id": self.source_image_id,
                "relativePath": self.source_relative_path,
            },
            "sourceFamily": self.source_checksum_sha256,
            "split": split,
            "stagingLabel": self.staging_label,
        }


@dataclass(frozen=True, slots=True)
class EvaluatedCell:
    board_id: str
    sequence_number: int
    cell_index: int
    staging_label: str
    source_family: str
    expected_symbol: str
    prediction: CellPrediction
    crop_checksum_sha256: str
    preprocessing_parity: bool


def build_cohort_document(
    boards: Sequence[ResidualBoard],
    *,
    game_id: str,
    required_stagings: Sequence[str],
    model: Mapping[str, object],
    training_dataset: Mapping[str, object],
    excluded_counts: Mapping[str, int] | None = None,
    audited_label_conflicts: Sequence[Mapping[str, object]] = (),
    split_seed: str = DEFAULT_SPLIT_SEED,
    minimum_board_count: int = MINIMUM_BOARD_COUNT,
) -> dict[str, object]:
    """Freeze a source-disjoint cohort without accepting uncertain geometry."""

    if len(required_stagings) != REQUIRED_STAGING_COUNT or len(set(required_stagings)) != len(
        required_stagings
    ):
        raise _error(
            "V19_SYMBOL_COHORT_STAGING_SCOPE_INVALID",
            f"The cohort must pin exactly {REQUIRED_STAGING_COUNT} staging labels.",
        )
    allowed = set(required_stagings)
    ordered = tuple(
        sorted(
            (board for board in boards if board.staging_label in allowed),
            key=lambda board: (
                required_stagings.index(board.staging_label),
                board.sequence_number,
                board.board_id,
            ),
        )
    )
    if len(ordered) < minimum_board_count:
        raise _error(
            "V19_SYMBOL_COHORT_TOO_SMALL",
            (
                f"Only {len(ordered)} verified v19 boards are available; "
                f"{minimum_board_count} required."
            ),
        )
    observed_stagings = {board.staging_label for board in ordered}
    if observed_stagings != allowed:
        missing = sorted(allowed - observed_stagings)
        raise _error(
            "V19_SYMBOL_COHORT_STAGING_MISSING",
            f"The verified cohort does not cover staging labels: {', '.join(missing)}.",
        )
    if len({board.board_id for board in ordered}) != len(ordered):
        raise _error("V19_SYMBOL_COHORT_BOARD_DUPLICATE", "A board occurs more than once.")
    if len({board.sequence_number for board in ordered}) != len(ordered):
        raise _error(
            "V19_SYMBOL_COHORT_SEQUENCE_DUPLICATE",
            "The canonical cohort contains duplicate sequence numbers.",
        )
    audited_conflicts = _canonical_audited_label_conflicts(audited_label_conflicts)
    audited_sequences = {cast(int, row["sequenceNumber"]) for row in audited_conflicts}
    if any(board.sequence_number in audited_sequences for board in ordered):
        raise _error(
            "V19_SYMBOL_COHORT_AUDITED_CONFLICT_INCLUDED",
            "A board with an audited label conflict cannot enter the model cohort.",
        )
    crop_labels: dict[str, str] = {}
    raw_class_codes = model.get("classCodes")
    if (
        not isinstance(raw_class_codes, Sequence)
        or isinstance(raw_class_codes, str | bytes)
        or not raw_class_codes
        or any(not isinstance(code, str) or not code for code in raw_class_codes)
    ):
        raise _error("V19_SYMBOL_COHORT_MODEL_INVALID", "The model class catalog is invalid.")
    class_codes = set(cast(Sequence[str], raw_class_codes))
    for board in ordered:
        for cell in board.cells:
            if cell.symbol_code not in class_codes:
                raise _error(
                    "V19_SYMBOL_COHORT_SYMBOL_UNKNOWN",
                    "A human label is absent from the pinned model catalog.",
                )
            prior = crop_labels.setdefault(cell.crop_checksum_sha256, cell.symbol_code)
            if prior != cell.symbol_code:
                raise _error(
                    "V19_SYMBOL_COHORT_LABEL_CONFLICT",
                    "Identical crop bytes have conflicting human labels.",
                )
    sources = sorted({board.source_checksum_sha256 for board in ordered})
    assignments = dict(build_balanced_source_assignments(sources, seed=split_seed))
    split_sources = {
        split: sorted(source for source, assigned in assignments.items() if assigned == split)
        for split in ("train", "validation", "test", "regression")
    }
    if set().union(*map(set, split_sources.values())) != set(sources) or sum(
        len(value) for value in split_sources.values()
    ) != len(sources):
        raise _error("V19_SYMBOL_COHORT_SPLIT_LEAKAGE", "Source-family split is invalid.")
    board_rows = [
        board.to_dict(split=assignments[board.source_checksum_sha256]) for board in ordered
    ]
    return {
        "auditedLabelConflicts": audited_conflicts,
        "boards": board_rows,
        "cropCount": len(ordered) * CELL_COUNT,
        "cropperVersion": CROPPER_VERSION,
        "excludedCounts": dict(sorted((excluded_counts or {}).items())),
        "gameId": game_id,
        "geometryVersion": BOARD_CELL_GEOMETRY_VERSION,
        "model": dict(model),
        "preprocessingVersion": PREPROCESSING_VERSION,
        "schemaVersion": COHORT_SCHEMA_VERSION,
        "scope": {
            "boardCount": len(ordered),
            "minimumBoardCount": minimum_board_count,
            "sourceFamilyCount": len(sources),
            "stagingCount": len(observed_stagings),
            "stagingLabels": list(required_stagings),
        },
        "split": {
            "assignments": dict(sorted(assignments.items())),
            "policyVersion": "source-family-balanced-split-v2",
            "seed": split_seed,
            "sourceFamilies": split_sources,
        },
        "trainingDataset": dict(training_dataset),
        "version": COHORT_VERSION,
    }


def build_evaluation_document(
    cohort: Mapping[str, object],
    cells: Sequence[EvaluatedCell],
) -> dict[str, object]:
    """Classify trustworthy residuals and issue a retrain/no-retrain decision."""

    scope = _mapping(cohort.get("scope"), "scope")
    board_count = _integer(scope.get("boardCount"), "scope.boardCount")
    if cohort.get("version") != COHORT_VERSION or board_count < MINIMUM_BOARD_COUNT:
        raise _error("V19_SYMBOL_EVALUATION_COHORT_INVALID", "Cohort contract is invalid.")
    expected_cell_count = board_count * CELL_COUNT
    if len(cells) != expected_cell_count:
        raise _error(
            "V19_SYMBOL_EVALUATION_INCOMPLETE",
            "Evaluation must contain one result for every frozen crop.",
        )
    identities = {(cell.board_id, cell.cell_index) for cell in cells}
    if len(identities) != len(cells):
        raise _error("V19_SYMBOL_EVALUATION_DUPLICATE", "Evaluation cells repeat.")
    training = _mapping(cohort.get("trainingDataset"), "trainingDataset")
    training_symbols = {
        str(row["symbolCode"]): row
        for row in _mapping_rows(training.get("symbols"), "trainingDataset.symbols")
    }
    training_sources = set(_text_rows(training.get("sourceFamilies"), "sourceFamilies"))
    ordered = tuple(sorted(cells, key=lambda cell: (cell.sequence_number, cell.cell_index)))
    metrics = _metrics(ordered)
    by_staging = {
        label: _metrics(tuple(cell for cell in ordered if cell.staging_label == label))
        for label in sorted({cell.staging_label for cell in ordered})
    }
    by_source_exposure = {
        "seenDuringTraining": _metrics(
            tuple(cell for cell in ordered if cell.source_family in training_sources)
        ),
        "unseenDuringTraining": _metrics(
            tuple(cell for cell in ordered if cell.source_family not in training_sources)
        ),
    }
    parity_failures = [cell for cell in ordered if not cell.preprocessing_parity]
    errors = [cell for cell in ordered if cell.expected_symbol != cell.prediction.symbol_code]
    significant_pairs = _significant_pairs(ordered)
    residuals = [
        _classify_pair(
            expected,
            predicted,
            pair_cells,
            training_symbols=training_symbols,
            training_sources=training_sources,
        )
        for (expected, predicted), pair_cells in significant_pairs
    ]
    audited_conflicts = _mapping_rows(
        cohort.get("auditedLabelConflicts", []), "auditedLabelConflicts"
    )
    if audited_conflicts:
        residuals.append(
            {
                "classification": "OPEN",
                "evidenceCropCount": sum(
                    len(_text_rows(row.get("evidenceCropChecksumsSha256"), "evidence"))
                    for row in audited_conflicts
                ),
                "kind": "audited_label_conflict",
                "sequenceNumbers": sorted(
                    _integer(row.get("sequenceNumber"), "sequenceNumber")
                    for row in audited_conflicts
                ),
                "status": "excluded_from_model_evaluation",
            }
        )
    if parity_failures:
        residuals.insert(
            0,
            {
                "classification": "P1",
                "evidence": {"preprocessingParityFailureCount": len(parity_failures)},
                "kind": "preprocessing_parity",
                "status": "significant",
            },
        )
    significant_recall = [
        row
        for row in cast(list[dict[str, object]], metrics["perClass"])
        if cast(int, row["support"]) >= 20 and cast(float, row["recall"]) < 0.95
    ]
    threshold_triggered = bool(
        cast(float, metrics["errorRate"]) > 0.02 or significant_recall or significant_pairs
    )
    if parity_failures:
        decision = "no-retrain"
        decision_reasons = ["PREPROCESSING_PARITY_MUST_BE_FIXED_FIRST"]
    elif threshold_triggered:
        decision = "retrain"
        decision_reasons = ["VERIFIED_V19_MODEL_RESIDUAL_EXCEEDS_GATE"]
    else:
        decision = "no-retrain"
        decision_reasons = ["VERIFIED_V19_MODEL_RESIDUAL_WITHIN_GATE"]
    high_confidence = [
        _error_row(cell)
        for cell in errors
        if cell.prediction.confidence >= HIGH_CONFIDENCE_THRESHOLD
    ]
    return {
        "cohortChecksumSha256": hashlib.sha256(canonical_json_bytes(cohort)).hexdigest(),
        "decision": {"reasons": decision_reasons, "value": decision},
        "highConfidenceErrors": high_confidence,
        "metrics": metrics,
        "metricsBySourceExposure": by_source_exposure,
        "metricsByStaging": by_staging,
        "preprocessingParity": {
            "failureCount": len(parity_failures),
            "sampleCount": len(ordered),
            "status": "passed" if not parity_failures else "failed",
            "version": PREPROCESSING_VERSION,
        },
        "residuals": residuals,
        "schemaVersion": EVALUATION_SCHEMA_VERSION,
        "variantGroups": _variant_groups(errors),
        "version": EVALUATION_VERSION,
    }


def document_checksum_sha256(document: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_json_bytes(document)).hexdigest()


def _canonical_audited_label_conflicts(
    rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    canonical: list[dict[str, object]] = []
    seen_sequences: set[int] = set()
    for row in rows:
        sequence_number = row.get("sequenceNumber")
        reason = row.get("reason")
        raw_evidence = row.get("evidenceCropChecksumsSha256")
        if (
            isinstance(sequence_number, bool)
            or not isinstance(sequence_number, int)
            or sequence_number < 1
            or sequence_number in seen_sequences
            or reason != "visual_label_or_slot_conflict"
            or not isinstance(raw_evidence, Sequence)
            or isinstance(raw_evidence, str | bytes)
            or not raw_evidence
        ):
            raise _error(
                "V19_SYMBOL_COHORT_AUDIT_INVALID",
                "An audited label conflict is incomplete or duplicated.",
            )
        evidence = sorted({_require_sha256(value, "audit evidence") for value in raw_evidence})
        canonical.append(
            {
                "evidenceCropChecksumsSha256": evidence,
                "reason": reason,
                "sequenceNumber": sequence_number,
            }
        )
        seen_sequences.add(sequence_number)
    return sorted(canonical, key=lambda row: cast(int, row["sequenceNumber"]))


def _metrics(cells: Sequence[EvaluatedCell]) -> dict[str, object]:
    if not cells:
        return {
            "accuracy": None,
            "cellCount": 0,
            "confusion": [],
            "errorCount": 0,
            "errorRate": None,
            "perClass": [],
            "sourceFamilyCount": 0,
            "wholeBoardAccuracy": None,
        }
    correct = sum(cell.expected_symbol == cell.prediction.symbol_code for cell in cells)
    confusion = Counter((cell.expected_symbol, cell.prediction.symbol_code) for cell in cells)
    by_expected = Counter(cell.expected_symbol for cell in cells)
    correct_by_class = Counter(
        cell.expected_symbol
        for cell in cells
        if cell.expected_symbol == cell.prediction.symbol_code
    )
    board_results: dict[str, list[bool]] = {}
    for cell in cells:
        board_results.setdefault(cell.board_id, []).append(
            cell.expected_symbol == cell.prediction.symbol_code
        )
    return {
        "accuracy": round(correct / len(cells), 8),
        "cellCount": len(cells),
        "confidence": {
            "meanCorrect": _mean(
                [
                    cell.prediction.confidence
                    for cell in cells
                    if cell.expected_symbol == cell.prediction.symbol_code
                ]
            ),
            "meanIncorrect": _mean(
                [
                    cell.prediction.confidence
                    for cell in cells
                    if cell.expected_symbol != cell.prediction.symbol_code
                ]
            ),
        },
        "confusion": [
            {"count": count, "expectedSymbolCode": expected, "predictedSymbolCode": predicted}
            for (expected, predicted), count in sorted(confusion.items())
        ],
        "errorCount": len(cells) - correct,
        "errorRate": round(1.0 - correct / len(cells), 8),
        "perClass": [
            {
                "correct": correct_by_class[code],
                "recall": round(correct_by_class[code] / by_expected[code], 8),
                "support": by_expected[code],
                "symbolCode": code,
            }
            for code in sorted(by_expected)
        ],
        "sourceFamilyCount": len({cell.source_family for cell in cells}),
        "wholeBoardAccuracy": round(
            sum(len(values) == CELL_COUNT and all(values) for values in board_results.values())
            / len(board_results),
            8,
        ),
    }


def _significant_pairs(
    cells: Sequence[EvaluatedCell],
) -> list[tuple[tuple[str, str], tuple[EvaluatedCell, ...]]]:
    support = Counter(cell.expected_symbol for cell in cells)
    grouped: dict[tuple[str, str], list[EvaluatedCell]] = {}
    for cell in cells:
        if cell.expected_symbol != cell.prediction.symbol_code:
            grouped.setdefault((cell.expected_symbol, cell.prediction.symbol_code), []).append(cell)
    return [
        (pair, tuple(values))
        for pair, values in sorted(grouped.items())
        if len(values) >= max(2, math.ceil(support[pair[0]] * 0.01))
    ]


def _classify_pair(
    expected: str,
    predicted: str,
    cells: Sequence[EvaluatedCell],
    *,
    training_symbols: Mapping[str, Mapping[str, object]],
    training_sources: set[str],
) -> dict[str, object]:
    parity_failures = sum(not cell.preprocessing_parity for cell in cells)
    unseen = sum(cell.source_family not in training_sources for cell in cells)
    training_row = training_symbols.get(expected, {})
    sample_count = _optional_count(training_row.get("sampleCount"))
    source_count = _optional_count(training_row.get("sourceFamilyCount"))
    if parity_failures:
        classification: ResidualClass = "P1"
    elif unseen / len(cells) >= 0.5:
        classification = "M2"
    elif sample_count >= 10 and source_count >= 4:
        classification = "M1"
    else:
        classification = "OPEN"
    return {
        "classification": classification,
        "errorCount": len(cells),
        "expectedSymbolCode": expected,
        "highConfidenceErrorCount": sum(
            cell.prediction.confidence >= HIGH_CONFIDENCE_THRESHOLD for cell in cells
        ),
        "kind": "symbol_confusion",
        "predictedSymbolCode": predicted,
        "sourceFamilyCount": len({cell.source_family for cell in cells}),
        "status": "significant",
        "trainingSampleCount": sample_count,
        "trainingSourceFamilyCount": source_count,
        "unseenSourceErrorFraction": round(unseen / len(cells), 8),
    }


def _variant_groups(errors: Sequence[EvaluatedCell]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[EvaluatedCell]] = {}
    for cell in errors:
        grouped.setdefault(
            (cell.expected_symbol, cell.prediction.symbol_code, cell.staging_label), []
        ).append(cell)
    return [
        {
            "errorCount": len(values),
            "exampleCropChecksumsSha256": sorted({cell.crop_checksum_sha256 for cell in values})[
                :5
            ],
            "expectedSymbolCode": expected,
            "predictedSymbolCode": predicted,
            "sourceFamilyCount": len({cell.source_family for cell in values}),
            "stagingLabel": staging,
        }
        for (expected, predicted, staging), values in sorted(
            grouped.items(), key=lambda item: (-len(item[1]), item[0])
        )
    ]


def _error_row(cell: EvaluatedCell) -> dict[str, object]:
    return {
        "boardId": cell.board_id,
        "cellIndex": cell.cell_index,
        "confidence": round(cell.prediction.confidence, 8),
        "cropChecksumSha256": cell.crop_checksum_sha256,
        "expectedSymbolCode": cell.expected_symbol,
        "predictedSymbolCode": cell.prediction.symbol_code,
        "sequenceNumber": cell.sequence_number,
        "sourceFamily": cell.source_family,
        "stagingLabel": cell.staging_label,
    }


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise _error("V19_SYMBOL_EVALUATION_COHORT_INVALID", f"{label} must be an object.")
    return cast(Mapping[str, object], value)


def _mapping_rows(value: object, label: str) -> tuple[Mapping[str, object], ...]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise _error("V19_SYMBOL_EVALUATION_COHORT_INVALID", f"{label} must be an array.")
    return tuple(_mapping(row, label) for row in value)


def _text_rows(value: object, label: str) -> tuple[str, ...]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise _error("V19_SYMBOL_EVALUATION_COHORT_INVALID", f"{label} must be an array.")
    if any(not isinstance(row, str) or not row for row in value):
        raise _error("V19_SYMBOL_EVALUATION_COHORT_INVALID", f"{label} is invalid.")
    return tuple(cast(Sequence[str], value))


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _error("V19_SYMBOL_EVALUATION_COHORT_INVALID", f"{label} must be an integer.")
    return value


def _optional_count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _require_sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise _error("V19_SYMBOL_COHORT_CHECKSUM_INVALID", f"{label} must be SHA-256.")
    return value


def _mean(values: Sequence[float]) -> float | None:
    return None if not values else round(fmean(values), 8)


def _error(code: str, message: str) -> V19SymbolResidualError:
    return V19SymbolResidualError(code, message)


__all__ = [
    "CELL_COUNT",
    "COHORT_VERSION",
    "EVALUATION_VERSION",
    "EvaluatedCell",
    "ResidualBoard",
    "ResidualCell",
    "V19SymbolResidualError",
    "build_cohort_document",
    "build_evaluation_document",
    "document_checksum_sha256",
]
