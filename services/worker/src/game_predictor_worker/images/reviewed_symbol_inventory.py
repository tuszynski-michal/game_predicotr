"""Verified M6 inventory built from the owner-accepted v16 crop chain."""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

from .calibrated_symbol_inventory import (
    _corpus_indexes,
    _reviewed_sequences,
    _verify_board,
)
from .rectification import BOARD_COLUMNS, BOARD_ROWS
from .symbol_dataset import (
    REVIEWED_CROPPER_VERSION,
    REVIEWED_INVENTORY_VERSION,
    SymbolCropInventory,
    SymbolCropSample,
    SymbolDatasetError,
    _integer,
    _load_json,
    _mapping,
    _safe_existing_path,
    _sequence,
    _sha256,
    _text,
    _verify_crop,
    calibrated_board_id,
    calibrated_observation_id,
    reviewed_crop_sample_id,
)

REVIEWED_REPORT_SCHEMA = "m5-reviewed-manual-merge-v16-full-preflight-v1"
OWNER_ACCEPTANCE_SCHEMA = "m5-reviewed-manual-merge-v16-owner-acceptance-v1"
GEOMETRY_PROVENANCE_VERSION = 16


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _geometry_provenance_id(
    *,
    report_sha256: str,
    source_checksum: str,
    sequence_number: int,
    position_index: int,
    geometry_route: str,
    analysis_frame_source: str,
    board_checksum: str,
) -> str:
    logical_key = "\0".join(
        (
            "reviewed-v16-geometry-provenance-v1",
            report_sha256,
            source_checksum,
            str(sequence_number),
            str(position_index),
            geometry_route,
            analysis_frame_source,
            board_checksum,
        )
    )
    return hashlib.sha256(logical_key.encode()).hexdigest()


def build_reviewed_symbol_crop_inventory(
    corpus_manifest_path: Path,
    golden_annotations_path: Path,
    geometry_report_path: Path,
    owner_acceptance_path: Path,
    crop_root: Path,
) -> SymbolCropInventory:
    """Verify the accepted v16 chain and enumerate all row-major cell crops."""

    corpus_bytes, corpus = _load_json(corpus_manifest_path, "SYMBOL_DATASET_CORPUS_INVALID")
    annotations_bytes, annotations = _load_json(
        golden_annotations_path, "SYMBOL_DATASET_GOLDEN_INVALID"
    )
    report_bytes, report = _load_json(geometry_report_path, "SYMBOL_DATASET_CROP_REPORT_INVALID")
    acceptance_bytes, acceptance = _load_json(
        owner_acceptance_path, "SYMBOL_DATASET_OWNER_ACCEPTANCE_INVALID"
    )
    corpus_sha = _digest(corpus_bytes)
    annotations_sha = _digest(annotations_bytes)
    report_sha = _digest(report_bytes)
    acceptance_sha = _digest(acceptance_bytes)
    corpus_id = _text(corpus.get("corpusId"), "corpusId")

    if (
        annotations.get("corpusId") != corpus_id
        or report.get("schemaVersion") != REVIEWED_REPORT_SCHEMA
        or report.get("candidate") != "v16-reviewed"
        or report.get("cropperVersion") != REVIEWED_CROPPER_VERSION
        or report.get("manifestSha256") != corpus_sha
        or report.get("status") != "waiting_for_owner_review"
        or report.get("technicalPassed") is not True
        or report.get("fullCorpusGenerated") is not True
        or report.get("trainingAllowed") is not False
        or report.get("imageCount") != 43
        or report.get("boardCount") != 387
        or report.get("processedCount") != 387
        or report.get("cellCount") != 5805
        or report.get("fallbackCount") != 0
    ):
        raise SymbolDatasetError(
            "SYMBOL_DATASET_REVIEWED_CHAIN_DRIFT",
            "The v16 report is not the complete technically passed corpus.",
        )
    if (
        acceptance.get("schemaVersion") != OWNER_ACCEPTANCE_SCHEMA
        or acceptance.get("status") != "accepted"
        or acceptance.get("trainingAllowed") is not True
        or acceptance.get("ownerDecision") != "continue_with_complete_v16_corpus"
        or acceptance.get("fullReportSha256") != report_sha
        or acceptance.get("boardCount") != 387
        or acceptance.get("cellCount") != 5805
        or acceptance.get("fallbackCount") != 0
        or acceptance.get("manualOverrideCount") != report.get("manualOverrideCount")
        or acceptance.get("reusedV14BoardCount") != report.get("reusedV14BoardCount")
    ):
        raise SymbolDatasetError(
            "SYMBOL_DATASET_OWNER_ACCEPTANCE_DRIFT",
            "The owner acceptance does not authorize this exact v16 report.",
        )

    try:
        crop_base = crop_root.resolve(strict=True)
    except OSError as error:
        raise SymbolDatasetError(
            "SYMBOL_DATASET_CROP_ROOT_NOT_FOUND",
            "Crop artifact root does not exist.",
        ) from error
    if not crop_base.is_dir():
        raise SymbolDatasetError(
            "SYMBOL_DATASET_CROP_ROOT_NOT_DIRECTORY",
            "Crop artifact root must be a directory.",
        )

    corpus_by_checksum, corpus_by_id = _corpus_indexes(corpus)
    sequences = _reviewed_sequences(annotations, corpus_by_id)
    entries = _sequence(report.get("entries"), "report.entries")
    execution_order = [
        _integer(value, f"executionOrder[{index}]")
        for index, value in enumerate(
            _sequence(report.get("executionOrder"), "report.executionOrder")
        )
    ]
    if execution_order != list(range(1, 388)) or len(entries) != 387:
        raise SymbolDatasetError(
            "SYMBOL_DATASET_SEQUENCE_AMBIGUOUS",
            "The v16 report must cover sequences 1 through 387 exactly once.",
        )

    samples: list[SymbolCropSample] = []
    seen_boards: set[str] = set()
    seen_samples: set[str] = set()
    seen_entry_keys: set[tuple[str, int]] = set()
    boards_per_source: Counter[str] = Counter()

    for entry_index, raw_entry in enumerate(entries):
        entry = _mapping(raw_entry, f"report.entries[{entry_index}]")
        if entry.get("status") != "cropped" or entry.get("fallbackReason") is not None:
            raise SymbolDatasetError(
                "SYMBOL_DATASET_GEOMETRY_NOT_ACCEPTED",
                "Every v16 board must be cropped without a fallback.",
            )
        source_checksum = _sha256(entry.get("sourceChecksumSha256"), "sourceChecksumSha256")
        corpus_image = corpus_by_checksum.get(source_checksum)
        if corpus_image is None:
            raise SymbolDatasetError(
                "SYMBOL_DATASET_CROP_REPORT_DRIFT",
                "A v16 board references an image outside the corpus.",
            )
        source_image_id = _text(entry.get("sourceImageId"), "sourceImageId")
        corpus_image_id = _text(corpus_image.get("id"), "corpus image id")
        position_index = _integer(entry.get("positionIndex"), "positionIndex")
        sequence_number = _integer(entry.get("sequenceNumber"), "sequenceNumber")
        entry_key = (source_checksum, position_index)
        if (
            source_image_id != corpus_image_id
            or entry_key in seen_entry_keys
            or sequences.get((source_image_id, position_index)) != sequence_number
        ):
            raise SymbolDatasetError(
                "SYMBOL_DATASET_CROP_REPORT_DRIFT",
                "V16 source, position or reviewed sequence provenance differs.",
            )
        seen_entry_keys.add(entry_key)
        boards_per_source[source_checksum] += 1

        board_relative, board_path = _safe_existing_path(
            crop_base, entry.get("boardRelativePath"), "boardRelativePath"
        )
        board_checksum = _sha256(entry.get("boardChecksumSha256"), "boardChecksumSha256")
        _verify_board(
            board_path,
            board_checksum,
            f"board {source_image_id}/{position_index}",
        )
        board_id = calibrated_board_id(
            corpus_id=corpus_id,
            source_checksum=source_checksum,
            sequence_number=sequence_number,
            board_index=position_index,
        )
        if board_id in seen_boards:
            raise SymbolDatasetError(
                "SYMBOL_DATASET_BOARD_DUPLICATE",
                "A logical v16 board is duplicated.",
            )
        seen_boards.add(board_id)
        analysis_frame_source = _text(entry.get("analysisFrameSource"), "analysisFrameSource")
        raw_geometry_route = entry.get("geometryRoute")
        if raw_geometry_route is None and analysis_frame_source == "human-reviewed-source-quad":
            geometry_route = "manual-reviewed-source-quad"
        else:
            geometry_route = _text(raw_geometry_route, "geometryRoute")
        geometry_id = _geometry_provenance_id(
            report_sha256=report_sha,
            source_checksum=source_checksum,
            sequence_number=sequence_number,
            position_index=position_index,
            geometry_route=geometry_route,
            analysis_frame_source=analysis_frame_source,
            board_checksum=board_checksum,
        )

        cells = _sequence(entry.get("cells"), "cells")
        if len(cells) != BOARD_ROWS * BOARD_COLUMNS:
            raise SymbolDatasetError(
                "SYMBOL_DATASET_CELL_COUNT_MISMATCH",
                "Each v16 board must contain exactly 15 cells.",
            )
        for cell_index, raw_cell in enumerate(cells):
            cell = _mapping(raw_cell, f"cells[{cell_index}]")
            row_index, column_index = divmod(cell_index, BOARD_COLUMNS)
            if (
                _integer(cell.get("rowIndex"), "rowIndex") != row_index
                or _integer(cell.get("columnIndex"), "columnIndex") != column_index
                or cell.get("supportFraction") != 1.0
            ):
                raise SymbolDatasetError(
                    "SYMBOL_DATASET_CELL_INDEX_MISMATCH",
                    "V16 cells must be complete and ordered as a 5 x 3 board.",
                )
            crop_relative, crop_path = _safe_existing_path(
                crop_base, cell.get("relativePath"), "cell.relativePath"
            )
            crop_checksum = _sha256(cell.get("checksumSha256"), "cell.checksumSha256")
            _verify_crop(
                crop_path,
                expected_checksum=crop_checksum,
                label=f"cell {source_image_id}/{position_index}/{cell_index}",
            )
            observation_id = calibrated_observation_id(
                corpus_id=corpus_id,
                source_checksum=source_checksum,
                sequence_number=sequence_number,
                board_index=position_index,
                row_index=row_index,
                column_index=column_index,
            )
            sample_id = reviewed_crop_sample_id(
                observation_id=observation_id,
                cropper_version=REVIEWED_CROPPER_VERSION,
                geometry_provenance_id=geometry_id,
                geometry_provenance_version=GEOMETRY_PROVENANCE_VERSION,
                crop_checksum=crop_checksum,
            )
            if sample_id in seen_samples:
                raise SymbolDatasetError(
                    "SYMBOL_DATASET_SAMPLE_DUPLICATE",
                    "A reviewed v16 crop sample is duplicated.",
                )
            seen_samples.add(sample_id)
            samples.append(
                SymbolCropSample(
                    sample_id=sample_id,
                    source_image_id=source_image_id,
                    source_image_checksum_sha256=source_checksum,
                    source_image_relative_path=_text(
                        corpus_image.get("relativePath"), "source relativePath"
                    ),
                    source_group=_text(corpus_image.get("sourceGroup"), "sourceGroup"),
                    sequence_number=sequence_number,
                    board_index=position_index,
                    cell_index=cell_index,
                    row_index=row_index,
                    column_index=column_index,
                    crop_relative_path=crop_relative,
                    crop_checksum_sha256=crop_checksum,
                    observation_id=observation_id,
                    crop_sample_id=sample_id,
                    board_id=board_id,
                    board_relative_path=board_relative,
                    board_checksum_sha256=board_checksum,
                    # The v1 label/review contract retains these compatibility
                    # names; for v3 they carry immutable geometry provenance.
                    calibration_profile_id=geometry_id,
                    calibration_profile_version=GEOMETRY_PROVENANCE_VERSION,
                )
            )

    expected_source_keys = set(corpus_by_checksum)
    if set(boards_per_source) != expected_source_keys or any(
        boards_per_source[checksum]
        != _integer(image.get("expectedBoardCount"), "expectedBoardCount")
        for checksum, image in corpus_by_checksum.items()
    ):
        raise SymbolDatasetError(
            "SYMBOL_DATASET_BOARD_COUNT_MISMATCH",
            "V16 boards do not cover every corpus image exactly.",
        )
    samples.sort(key=lambda sample: (sample.sequence_number, sample.cell_index))
    if len(seen_boards) != 387 or len(samples) != 5805:
        raise SymbolDatasetError(
            "SYMBOL_DATASET_CORPUS_COUNT_MISMATCH",
            "The accepted v16 corpus must contain 387 boards and 5805 cells.",
        )
    return SymbolCropInventory(
        corpus_id=corpus_id,
        corpus_manifest_sha256=corpus_sha,
        golden_annotations_sha256=annotations_sha,
        crop_report_sha256=report_sha,
        samples=tuple(samples),
        inventory_version=REVIEWED_INVENTORY_VERSION,
        cropper_version=REVIEWED_CROPPER_VERSION,
        geometry_report_sha256=report_sha,
        owner_acceptance_sha256=acceptance_sha,
    )


__all__ = [
    "GEOMETRY_PROVENANCE_VERSION",
    "OWNER_ACCEPTANCE_SCHEMA",
    "REVIEWED_REPORT_SCHEMA",
    "build_reviewed_symbol_crop_inventory",
]
