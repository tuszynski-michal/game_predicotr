"""Framework-independent contracts for immutable whole-layout review batches."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Final
from uuid import UUID

ACTIVE_LEARNING_VERSION: Final = "whole-layout-active-learning-v1"
REVIEW_ITEM_CELL_COUNT: Final = 15
MAX_REVIEW_BATCH_ITEMS: Final = 100
MAX_REVIEW_PAGE_SIZE: Final = 100
_SHA256_PATTERN: Final = re.compile(r"^[a-f0-9]{64}$")


class ReviewItemStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    CORRECTED = "corrected"
    REJECTED = "rejected"


class ReviewResolutionAction(StrEnum):
    ACCEPT = "accepted"
    CORRECT = "corrected"
    REJECT = "rejected"


class ReviewError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class ReviewNotFoundError(ReviewError):
    """A review batch, item, game or symbol catalog does not exist."""


class ReviewConflictError(ReviewError):
    """An immutable review batch conflicts with persisted state."""


@dataclass(frozen=True, slots=True)
class ReviewItem:
    id: UUID
    review_batch_id: UUID
    board_id: str
    selection_rank: int
    sequence_number: int
    source_image_id: str
    source_image_checksum_sha256: str
    source_group: str
    board_relative_path: str
    status: ReviewItemStatus
    prediction_snapshot: Mapping[str, object]
    created_at: datetime
    resolved_value: Mapping[str, object] | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    resolution_revision: int = 0


@dataclass(frozen=True, slots=True)
class ReviewBatch:
    id: UUID
    game_id: UUID
    source_report_sha256: str
    active_learning_version: str
    model_version: str
    model_artifact_sha256: str
    calibration_report_sha256: str
    dataset_sha256: str
    split_sha256: str
    inventory_sha256: str
    temperature: float
    item_count: int
    source_report: Mapping[str, object]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ReviewItemPage:
    items: tuple[ReviewItem, ...]
    next_after_selection_rank: int | None


@dataclass(frozen=True, slots=True)
class ReviewResolution:
    id: UUID
    review_item_id: UUID
    revision: int
    idempotency_key: UUID
    action: ReviewResolutionAction
    command_sha256: str
    resolved_value: Mapping[str, object]
    resolved_by: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ValidatedReviewResolution:
    action: ReviewResolutionAction
    resolved_value: Mapping[str, object]
    resolved_by: str
    command_sha256: str


@dataclass(frozen=True, slots=True)
class ReviewFeedbackExport:
    id: UUID
    review_batch_id: UUID
    game_id: UUID
    version: int
    source_state_sha256: str
    payload_sha256: str
    sample_count: int
    rejected_item_count: int
    payload: Mapping[str, object]
    created_by: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ValidatedReviewSelection:
    source_report_sha256: str
    active_learning_version: str
    model_version: str
    model_artifact_sha256: str
    calibration_report_sha256: str
    dataset_sha256: str
    split_sha256: str
    inventory_sha256: str
    temperature: float
    source_report: Mapping[str, object]
    item_snapshots: tuple[Mapping[str, object], ...]


def canonical_report_bytes(report: Mapping[str, object]) -> bytes:
    try:
        return (
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode()
    except (TypeError, ValueError) as error:
        raise ReviewError(
            "REVIEW_REPORT_INVALID",
            "The review selection report is not canonical JSON.",
        ) from error


def canonical_review_bytes(value: Mapping[str, object]) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode()
    except (TypeError, ValueError) as error:
        raise ReviewError(
            "REVIEW_RESOLUTION_INVALID",
            "The review value is not canonical JSON.",
        ) from error


def validate_review_resolution(
    *,
    action: ReviewResolutionAction,
    geometry_accepted: bool,
    labels: Sequence[Mapping[str, object]],
    rejection_reason: str | None,
    resolved_by: str,
    prediction_snapshot: Mapping[str, object],
    active_symbol_codes: Sequence[str],
) -> ValidatedReviewResolution:
    actor = resolved_by.strip()
    if not actor or len(actor) > 200:
        raise ReviewError(
            "REVIEW_RESOLVED_BY_INVALID",
            "resolvedBy must identify the local administrator.",
        )
    snapshot_cells = _sequence(prediction_snapshot.get("cells"), "snapshot.cells")
    if len(snapshot_cells) != REVIEW_ITEM_CELL_COUNT:
        raise ReviewConflictError(
            "REVIEW_ITEM_SNAPSHOT_INVALID",
            "The immutable review item does not contain 15 cells.",
        )

    if action is ReviewResolutionAction.REJECT:
        if labels or geometry_accepted:
            raise ReviewError(
                "REVIEW_REJECTION_LABELS_FORBIDDEN",
                "Rejected review items cannot persist labels or accepted geometry.",
            )
        reason = (rejection_reason or "").strip()
        if not reason or len(reason) > 500:
            raise ReviewError(
                "REVIEW_REJECTION_REASON_INVALID",
                "A rejection reason between 1 and 500 characters is required.",
            )
        resolved_value: dict[str, object] = {
            "schemaVersion": 1,
            "geometryAccepted": False,
            "cells": [],
            "rejectionReason": reason,
        }
    else:
        if not geometry_accepted:
            raise ReviewConflictError(
                "REVIEW_GEOMETRY_NOT_ACCEPTED",
                "Geometry must be explicitly accepted before labels are saved.",
            )
        if len(labels) != REVIEW_ITEM_CELL_COUNT:
            raise ReviewError(
                "REVIEW_LABEL_COUNT_INVALID",
                "Accepted or corrected review items require exactly 15 labels.",
            )
        active_symbols = set(active_symbol_codes)
        resolved_cells: list[dict[str, object]] = []
        changed_count = 0
        for index, (raw_label, raw_snapshot_cell) in enumerate(
            zip(labels, snapshot_cells, strict=True)
        ):
            snapshot_cell = _mapping(raw_snapshot_cell, f"snapshot.cells[{index}]")
            cell_index = _integer(raw_label.get("cellIndex"), "cellIndex")
            sample_id = _sha256(raw_label.get("sampleId"), "sampleId")
            symbol_code = _text(raw_label.get("symbolCode"), "symbolCode", maximum=64)
            predicted_symbol = _text(
                snapshot_cell.get("predictedSymbolCode"),
                "predictedSymbolCode",
                maximum=64,
            )
            if (
                cell_index != index
                or _integer(snapshot_cell.get("cellIndex"), "snapshot.cellIndex") != index
                or sample_id != _sha256(snapshot_cell.get("sampleId"), "snapshot.sampleId")
            ):
                raise ReviewConflictError(
                    "REVIEW_LABEL_CELL_MISMATCH",
                    "Labels must match all immutable cells in row-major order.",
                )
            if symbol_code not in active_symbols:
                raise ReviewConflictError(
                    "REVIEW_SYMBOL_NOT_ACTIVE",
                    "A corrected symbol is not active in the review game.",
                    details={"symbolCode": symbol_code},
                )
            changed = symbol_code != predicted_symbol
            changed_count += int(changed)
            resolved_cells.append(
                {
                    "cellIndex": index,
                    "sampleId": sample_id,
                    "symbolCode": symbol_code,
                    "predictedSymbolCode": predicted_symbol,
                    "corrected": changed,
                }
            )
        if action is ReviewResolutionAction.ACCEPT and changed_count:
            raise ReviewError(
                "REVIEW_ACCEPT_CONTAINS_CORRECTIONS",
                "Accepted labels must match every model prediction.",
            )
        if action is ReviewResolutionAction.CORRECT and changed_count == 0:
            raise ReviewError(
                "REVIEW_CORRECTION_EMPTY",
                "Use accepted when no symbol was corrected.",
            )
        resolved_value = {
            "schemaVersion": 1,
            "geometryAccepted": True,
            "cells": resolved_cells,
            "rejectionReason": None,
        }

    command_value = {
        "action": action.value,
        "resolvedBy": actor,
        "resolvedValue": resolved_value,
    }
    return ValidatedReviewResolution(
        action=action,
        resolved_value=resolved_value,
        resolved_by=actor,
        command_sha256=hashlib.sha256(canonical_review_bytes(command_value)).hexdigest(),
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ReviewError("REVIEW_REPORT_INVALID", f"{label} must be an object.")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise ReviewError("REVIEW_REPORT_INVALID", f"{label} must be an array.")
    return value


def _text(value: object, label: str, *, maximum: int = 1000) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ReviewError(
            "REVIEW_REPORT_INVALID",
            f"{label} must be a non-empty string no longer than {maximum}.",
        )
    return value


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ReviewError("REVIEW_REPORT_INVALID", f"{label} must be an integer.")
    return value


def _number(value: object, label: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(value):
        raise ReviewError("REVIEW_REPORT_INVALID", f"{label} must be finite.")
    return float(value)


def _sha256(value: object, label: str) -> str:
    text = _text(value, label, maximum=64)
    if not _SHA256_PATTERN.fullmatch(text):
        raise ReviewError("REVIEW_REPORT_INVALID", f"{label} must be SHA-256.")
    return text


def _relative_path(value: object, label: str) -> str:
    text = _text(value, label)
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or "\\" in text:
        raise ReviewError(
            "REVIEW_REPORT_PATH_UNSAFE",
            f"{label} must be a relative POSIX path.",
        )
    return text


def _probability(value: object, label: str) -> float:
    number = _number(value, label)
    if not 0.0 <= number <= 1.0:
        raise ReviewError(
            "REVIEW_REPORT_INVALID",
            f"{label} must be between zero and one.",
        )
    return number


def _validate_cell(
    raw: object,
    *,
    expected_index: int,
    report_classes: set[str],
    active_symbols: set[str],
) -> None:
    cell = _mapping(raw, f"cells[{expected_index}]")
    row_index, column_index = divmod(expected_index, 5)
    if (
        _integer(cell.get("cellIndex"), "cellIndex") != expected_index
        or _integer(cell.get("rowIndex"), "rowIndex") != row_index
        or _integer(cell.get("columnIndex"), "columnIndex") != column_index
    ):
        raise ReviewError(
            "REVIEW_REPORT_CELL_ORDER_INVALID",
            "Review cells must contain exactly one 5 x 3 row-major grid.",
        )
    _sha256(cell.get("sampleId"), "sampleId")
    _sha256(cell.get("observationId"), "observationId")
    _relative_path(cell.get("cropRelativePath"), "cropRelativePath")
    predicted = _text(cell.get("predictedSymbolCode"), "predictedSymbolCode", maximum=64)
    if predicted not in report_classes or predicted not in active_symbols:
        raise ReviewConflictError(
            "REVIEW_SYMBOL_NOT_ACTIVE",
            "A predicted symbol is not active in the selected game.",
            details={"symbolCode": predicted},
        )
    confidence = _probability(cell.get("confidence"), "confidence")
    _probability(cell.get("entropy"), "entropy")
    alternatives = _sequence(cell.get("alternatives"), "alternatives")
    if not 1 <= len(alternatives) <= 3:
        raise ReviewError(
            "REVIEW_REPORT_ALTERNATIVES_INVALID",
            "Each cell must contain between one and three alternatives.",
        )
    seen: set[str] = set()
    previous_confidence = 1.0
    first_code = ""
    first_confidence = -1.0
    for index, raw_alternative in enumerate(alternatives):
        alternative = _mapping(raw_alternative, f"alternatives[{index}]")
        code = _text(alternative.get("symbolCode"), "symbolCode", maximum=64)
        alternative_confidence = _probability(
            alternative.get("confidence"),
            "alternative.confidence",
        )
        if (
            code in seen
            or code not in report_classes
            or code not in active_symbols
            or alternative_confidence > previous_confidence
        ):
            raise ReviewError(
                "REVIEW_REPORT_ALTERNATIVES_INVALID",
                "Alternatives must be unique active symbols sorted by confidence.",
            )
        if index == 0:
            first_code = code
            first_confidence = alternative_confidence
        seen.add(code)
        previous_confidence = alternative_confidence
    if first_code != predicted or not math.isclose(
        first_confidence,
        confidence,
        abs_tol=1e-8,
    ):
        raise ReviewError(
            "REVIEW_REPORT_PREDICTION_MISMATCH",
            "The first alternative must match the predicted symbol and confidence.",
        )


def validate_review_selection(
    report: Mapping[str, object],
    *,
    source_report_sha256: str,
    active_symbol_codes: Sequence[str],
) -> ValidatedReviewSelection:
    """Validate one immutable TASK-0063 report before persistence."""

    expected_sha256 = _sha256(source_report_sha256, "sourceReportSha256")
    actual_sha256 = hashlib.sha256(canonical_report_bytes(report)).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ReviewConflictError(
            "REVIEW_REPORT_CHECKSUM_MISMATCH",
            "The selection report checksum does not match its canonical payload.",
            details={"expected": expected_sha256, "actual": actual_sha256},
        )
    active_symbols = set(active_symbol_codes)
    report_classes = {
        _text(value, "classes[]", maximum=64)
        for value in _sequence(report.get("classes"), "classes")
    }
    if (
        report.get("schemaVersion") != 1
        or report.get("status") != "ready_for_manual_review"
        or report.get("activeLearningVersion") != ACTIVE_LEARNING_VERSION
        or not report_classes
        or len(report_classes) != len(_sequence(report.get("classes"), "classes"))
        or not report_classes <= active_symbols
    ):
        raise ReviewConflictError(
            "REVIEW_REPORT_CONTRACT_UNSUPPORTED",
            "The active-learning report or class catalog is unsupported.",
        )
    boundary = _mapping(report.get("selectionBoundary"), "selectionBoundary")
    if (
        boundary.get("completePendingBoardsOnly") is not True
        or boundary.get("maximumOneBoardPerSourceUntilAllSourcesCovered") is not True
        or boundary.get("mutatesReviewedLabels") is not False
    ):
        raise ReviewConflictError(
            "REVIEW_REPORT_BOUNDARY_INVALID",
            "The report does not preserve the accepted manual-review boundary.",
        )
    model = _mapping(report.get("model"), "model")
    temperature = _number(model.get("temperature"), "model.temperature")
    if temperature <= 0:
        raise ReviewError(
            "REVIEW_REPORT_INVALID",
            "The calibrated temperature must be positive.",
        )
    boards = _sequence(report.get("selectedBoards"), "selectedBoards")
    selected_count = _integer(report.get("selectedBoardCount"), "selectedBoardCount")
    batch_size = _integer(report.get("batchSize"), "batchSize")
    if (
        selected_count != len(boards)
        or not 1 <= selected_count <= batch_size <= MAX_REVIEW_BATCH_ITEMS
    ):
        raise ReviewError(
            "REVIEW_REPORT_COUNT_INVALID",
            "The selected board count must match the bounded batch.",
        )

    board_ids: set[str] = set()
    sequences: set[int] = set()
    sources: set[str] = set()
    ranks: set[int] = set()
    snapshots: list[Mapping[str, object]] = []
    for index, raw_board in enumerate(boards):
        board = _mapping(raw_board, f"selectedBoards[{index}]")
        board_id = _sha256(board.get("boardId"), "boardId")
        source_checksum = _sha256(
            board.get("sourceImageChecksumSha256"),
            "sourceImageChecksumSha256",
        )
        sequence_number = _integer(board.get("sequenceNumber"), "sequenceNumber")
        selection_rank = _integer(board.get("selectionRank"), "selectionRank")
        if (
            board_id in board_ids
            or source_checksum in sources
            or sequence_number <= 0
            or sequence_number in sequences
            or selection_rank in ranks
        ):
            raise ReviewError(
                "REVIEW_REPORT_BOARD_IDENTITY_INVALID",
                "Boards, sequences, ranks and source images must be unique.",
            )
        _text(board.get("sourceImageId"), "sourceImageId", maximum=200)
        _text(board.get("sourceGroup"), "sourceGroup", maximum=200)
        _relative_path(board.get("boardRelativePath"), "boardRelativePath")
        for score_name in (
            "predictedClassRarityScore",
            "predictionDiversityScore",
            "selectionScore",
            "sourceNoveltyScore",
            "uncertaintyScore",
        ):
            _probability(board.get(score_name), score_name)
        cells = _sequence(board.get("cells"), "cells")
        if len(cells) != REVIEW_ITEM_CELL_COUNT:
            raise ReviewError(
                "REVIEW_REPORT_CELL_COUNT_INVALID",
                "Each review item must contain exactly 15 cells.",
            )
        for cell_index, cell in enumerate(cells):
            _validate_cell(
                cell,
                expected_index=cell_index,
                report_classes=report_classes,
                active_symbols=active_symbols,
            )
        board_ids.add(board_id)
        sources.add(source_checksum)
        sequences.add(sequence_number)
        ranks.add(selection_rank)
        snapshots.append(dict(board))
    if ranks != set(range(1, selected_count + 1)):
        raise ReviewError(
            "REVIEW_REPORT_RANK_INVALID",
            "Selection ranks must be contiguous from one.",
        )
    snapshots.sort(key=lambda value: _integer(value.get("selectionRank"), "selectionRank"))
    return ValidatedReviewSelection(
        source_report_sha256=expected_sha256,
        active_learning_version=ACTIVE_LEARNING_VERSION,
        model_version=_text(model.get("modelVersion"), "modelVersion", maximum=100),
        model_artifact_sha256=_sha256(
            model.get("onnxArtifactSha256"),
            "onnxArtifactSha256",
        ),
        calibration_report_sha256=_sha256(
            report.get("calibrationReportSha256"),
            "calibrationReportSha256",
        ),
        dataset_sha256=_sha256(report.get("datasetSha256"), "datasetSha256"),
        split_sha256=_sha256(report.get("splitSha256"), "splitSha256"),
        inventory_sha256=_sha256(report.get("inventorySha256"), "inventorySha256"),
        temperature=temperature,
        source_report=dict(report),
        item_snapshots=tuple(snapshots),
    )


__all__ = [
    "MAX_REVIEW_PAGE_SIZE",
    "ReviewBatch",
    "ReviewConflictError",
    "ReviewError",
    "ReviewFeedbackExport",
    "ReviewItem",
    "ReviewItemPage",
    "ReviewItemStatus",
    "ReviewNotFoundError",
    "ReviewResolution",
    "ReviewResolutionAction",
    "ValidatedReviewResolution",
    "ValidatedReviewSelection",
    "canonical_review_bytes",
    "canonical_report_bytes",
    "validate_review_resolution",
    "validate_review_selection",
]
