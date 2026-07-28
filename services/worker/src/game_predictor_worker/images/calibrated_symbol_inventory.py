"""Verified symbol inventory built only from accepted calibrated M5 crops."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .grid_calibration import PROFILE_SET_VERSION
from .rectification import (
    BOARD_COLUMNS,
    BOARD_HEIGHT,
    BOARD_ROWS,
    BOARD_WIDTH,
    CALIBRATED_CROPPER_VERSION,
    CELL_HEIGHT,
    CELL_WIDTH,
)
from .symbol_dataset import (
    CALIBRATED_INVENTORY_VERSION,
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
    calibrated_crop_sample_id,
    calibrated_observation_id,
)


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _verify_board(path: Path, checksum: str, label: str) -> None:
    try:
        content = path.read_bytes()
        with Image.open(path) as image:
            image.load()
            valid = image.mode == "RGB" and image.size == (BOARD_WIDTH, BOARD_HEIGHT)
    except (OSError, UnidentifiedImageError) as error:
        raise SymbolDatasetError(
            "SYMBOL_DATASET_BOARD_UNREADABLE",
            f"{label} is not a readable board image.",
        ) from error
    if _digest(content) != checksum or not valid:
        raise SymbolDatasetError(
            "SYMBOL_DATASET_BOARD_DRIFT",
            f"{label} checksum or dimensions differ from the calibrated report.",
        )


def _corpus_indexes(
    corpus: Mapping[str, object],
) -> tuple[dict[str, Mapping[str, object]], dict[str, Mapping[str, object]]]:
    by_checksum: dict[str, Mapping[str, object]] = {}
    by_id: dict[str, Mapping[str, object]] = {}
    for index, raw in enumerate(_sequence(corpus.get("images"), "corpus.images")):
        image = _mapping(raw, f"corpus.images[{index}]")
        image_id = _text(image.get("id"), f"corpus.images[{index}].id")
        checksum = _sha256(image.get("sha256"), f"corpus.images[{index}].sha256")
        if image_id in by_id or checksum in by_checksum:
            raise SymbolDatasetError(
                "SYMBOL_DATASET_CORPUS_DUPLICATE",
                "Corpus image identity is duplicated.",
            )
        by_id[image_id] = image
        by_checksum[checksum] = image
    return by_checksum, by_id


def _reviewed_sequences(
    annotations: Mapping[str, object],
    corpus_by_id: Mapping[str, Mapping[str, object]],
) -> dict[tuple[str, int], int]:
    provenance = _mapping(annotations.get("annotationProvenance"), "annotationProvenance")
    if (
        provenance.get("method") != "algorithm-assisted-visual-review"
        or provenance.get("reviewedImageCount") != len(corpus_by_id)
    ):
        raise SymbolDatasetError(
            "SYMBOL_DATASET_GOLDEN_NOT_REVIEWED",
            "Reviewed sequence annotations must cover the complete corpus.",
        )
    result: dict[tuple[str, int], int] = {}
    seen: set[int] = set()
    for image_index, raw_image in enumerate(
        _sequence(annotations.get("images"), "annotations.images")
    ):
        image = _mapping(raw_image, f"annotations.images[{image_index}]")
        image_id = _text(image.get("imageId"), "annotations.imageId")
        if image_id not in corpus_by_id:
            raise SymbolDatasetError(
                "SYMBOL_DATASET_GOLDEN_DRIFT",
                "Reviewed sequence annotation references an unknown image.",
            )
        for index, raw_board in enumerate(_sequence(image.get("boards"), "annotations.boards")):
            board = _mapping(raw_board, f"annotations.boards[{index}]")
            position = _integer(board.get("positionIndex"), "positionIndex")
            sequence = _integer(board.get("sequenceNumber"), "sequenceNumber")
            key = (image_id, position)
            if key in result or sequence <= 0 or sequence in seen:
                raise SymbolDatasetError(
                    "SYMBOL_DATASET_SEQUENCE_AMBIGUOUS",
                    "Reviewed sequence numbers must be positive and unique.",
                )
            result[key] = sequence
            seen.add(sequence)
    if seen != set(range(1, len(seen) + 1)):
        raise SymbolDatasetError(
            "SYMBOL_DATASET_SEQUENCE_AMBIGUOUS",
            "Reviewed sequence numbers must be contiguous from one.",
        )
    return result


def build_calibrated_symbol_crop_inventory(
    corpus_manifest_path: Path,
    golden_annotations_path: Path,
    cell_grid_golden_path: Path,
    profile_path: Path,
    crop_report_path: Path,
    quality_report_path: Path,
    crop_root: Path,
) -> SymbolCropInventory:
    """Verify the complete calibration chain and enumerate 5 x 3 board cells."""

    corpus_bytes, corpus = _load_json(corpus_manifest_path, "SYMBOL_DATASET_CORPUS_INVALID")
    annotations_bytes, annotations = _load_json(
        golden_annotations_path, "SYMBOL_DATASET_GOLDEN_INVALID"
    )
    grid_bytes, grid = _load_json(cell_grid_golden_path, "SYMBOL_DATASET_GRID_INVALID")
    profile_bytes, profiles = _load_json(profile_path, "SYMBOL_DATASET_PROFILE_INVALID")
    crop_bytes, crops = _load_json(crop_report_path, "SYMBOL_DATASET_CROP_REPORT_INVALID")
    quality_bytes, quality = _load_json(
        quality_report_path, "SYMBOL_DATASET_QUALITY_REPORT_INVALID"
    )
    corpus_sha = _digest(corpus_bytes)
    annotations_sha = _digest(annotations_bytes)
    grid_sha = _digest(grid_bytes)
    profile_sha = _digest(profile_bytes)
    crop_sha = _digest(crop_bytes)
    corpus_id = _text(corpus.get("corpusId"), "corpusId")

    if (
        annotations.get("corpusId") != corpus_id
        or grid.get("corpusId") != corpus_id
        or grid.get("status") != "accepted"
        or grid.get("corpusManifestSha256") != corpus_sha
        or grid.get("goldenAnnotationsSha256") != annotations_sha
        or profiles.get("corpusId") != corpus_id
        or profiles.get("status") != "published"
        or profiles.get("profileSetVersion") != PROFILE_SET_VERSION
        or profiles.get("corpusManifestSha256") != corpus_sha
        or profiles.get("goldenSha256") != grid_sha
    ):
        raise SymbolDatasetError(
            "SYMBOL_DATASET_CALIBRATION_CHAIN_DRIFT",
            "Corpus, annotations, grid golden and calibration profiles do not match.",
        )
    if (
        crops.get("cropperVersion") != CALIBRATED_CROPPER_VERSION
        or crops.get("status") != "cropped"
        or crops.get("corpusManifestSha256") != corpus_sha
        or crops.get("calibrationProfileSetVersion") != PROFILE_SET_VERSION
        or crops.get("calibrationProfileSetSha256") != profile_sha
        or quality.get("cropperVersion") != CALIBRATED_CROPPER_VERSION
        or quality.get("status") != "passed"
        or quality.get("trainingAllowed") is not True
        or quality.get("cropReportSha256") != crop_sha
        or quality.get("calibrationProfileSetSha256") != profile_sha
        or quality.get("goldenSha256") != grid_sha
    ):
        raise SymbolDatasetError(
            "SYMBOL_DATASET_CALIBRATED_CROPS_NOT_ACCEPTED",
            "Only the passed calibrated crop report may be inventoried.",
        )

    try:
        crop_base = crop_root.resolve(strict=True)
    except OSError as error:
        raise SymbolDatasetError(
            "SYMBOL_DATASET_CROP_ROOT_NOT_FOUND", "Crop artifact root does not exist."
        ) from error
    corpus_by_checksum, corpus_by_id = _corpus_indexes(corpus)
    sequences = _reviewed_sequences(annotations, corpus_by_id)
    samples: list[SymbolCropSample] = []
    seen_boards: set[str] = set()
    seen_samples: set[str] = set()

    for image_index, raw_image in enumerate(_sequence(crops.get("images"), "crops.images")):
        crop_image = _mapping(raw_image, f"crops.images[{image_index}]")
        if crop_image.get("status") != "cropped":
            raise SymbolDatasetError(
                "SYMBOL_DATASET_CROP_REPORT_UNSUPPORTED",
                "Every calibrated crop source must be complete.",
            )
        source_checksum = _sha256(crop_image.get("sourceChecksumSha256"), "source checksum")
        corpus_image = corpus_by_checksum.get(source_checksum)
        if corpus_image is None:
            raise SymbolDatasetError(
                "SYMBOL_DATASET_CROP_REPORT_DRIFT",
                "Calibrated crop source is outside the corpus.",
            )
        image_id = _text(corpus_image.get("id"), "corpus image id")
        boards = _sequence(crop_image.get("boards"), "crop boards")
        expected = _integer(corpus_image.get("expectedBoardCount"), "expectedBoardCount")
        if len(boards) != expected:
            raise SymbolDatasetError(
                "SYMBOL_DATASET_BOARD_COUNT_MISMATCH",
                "Calibrated board count differs from the corpus.",
            )
        for board_index, raw_board in enumerate(boards):
            board = _mapping(raw_board, f"boards[{board_index}]")
            if _integer(board.get("positionIndex"), "positionIndex") != board_index:
                raise SymbolDatasetError(
                    "SYMBOL_DATASET_BOARD_INDEX_MISMATCH",
                    "Board positions must be contiguous and row-major.",
                )
            sequence_number = sequences.get((image_id, board_index))
            if sequence_number is None:
                raise SymbolDatasetError(
                    "SYMBOL_DATASET_SEQUENCE_AMBIGUOUS",
                    "Calibrated board has no reviewed sequence number.",
                )
            profile = _mapping(board.get("calibrationProfile"), "calibrationProfile")
            profile_id = _sha256(profile.get("profileId"), "profileId")
            profile_version = _integer(profile.get("profileVersion"), "profileVersion")
            if (
                board.get("sourceQuadSource") != "calibration-profile"
                or profile_version <= 0
            ):
                raise SymbolDatasetError(
                    "SYMBOL_DATASET_GEOMETRY_NOT_ACCEPTED",
                    "Every board must carry accepted calibration provenance.",
                )
            board_relative, board_path = _safe_existing_path(
                crop_base, board.get("boardRelativePath"), "boardRelativePath"
            )
            board_checksum = _sha256(board.get("boardChecksumSha256"), "boardChecksumSha256")
            _verify_board(board_path, board_checksum, f"board {image_id}/{board_index}")
            board_id = calibrated_board_id(
                corpus_id=corpus_id,
                source_checksum=source_checksum,
                sequence_number=sequence_number,
                board_index=board_index,
            )
            if board_id in seen_boards:
                raise SymbolDatasetError(
                    "SYMBOL_DATASET_BOARD_DUPLICATE", "A logical board is duplicated."
                )
            seen_boards.add(board_id)
            cells = _sequence(board.get("cells"), "cells")
            if len(cells) != BOARD_ROWS * BOARD_COLUMNS:
                raise SymbolDatasetError(
                    "SYMBOL_DATASET_CELL_COUNT_MISMATCH",
                    "Each calibrated board must contain exactly 15 cells.",
                )
            for cell_index, raw_cell in enumerate(cells):
                cell = _mapping(raw_cell, f"cells[{cell_index}]")
                row, column = divmod(cell_index, BOARD_COLUMNS)
                if (
                    _integer(cell.get("rowIndex"), "rowIndex") != row
                    or _integer(cell.get("columnIndex"), "columnIndex") != column
                    or _integer(cell.get("width"), "width") != CELL_WIDTH
                    or _integer(cell.get("height"), "height") != CELL_HEIGHT
                ):
                    raise SymbolDatasetError(
                        "SYMBOL_DATASET_CELL_INDEX_MISMATCH",
                        "Cell geometry must be 3 x 5 row-major.",
                    )
                crop_relative, crop_path = _safe_existing_path(
                    crop_base, cell.get("relativePath"), "cell.relativePath"
                )
                crop_checksum = _sha256(cell.get("checksumSha256"), "cell.checksumSha256")
                _verify_crop(
                    crop_path,
                    expected_checksum=crop_checksum,
                    label=f"cell {image_id}/{board_index}/{cell_index}",
                )
                observation_id = calibrated_observation_id(
                    corpus_id=corpus_id,
                    source_checksum=source_checksum,
                    sequence_number=sequence_number,
                    board_index=board_index,
                    row_index=row,
                    column_index=column,
                )
                sample_id = calibrated_crop_sample_id(
                    observation_id=observation_id,
                    cropper_version=CALIBRATED_CROPPER_VERSION,
                    profile_id=profile_id,
                    profile_version=profile_version,
                    crop_checksum=crop_checksum,
                )
                if sample_id in seen_samples:
                    raise SymbolDatasetError(
                        "SYMBOL_DATASET_SAMPLE_DUPLICATE",
                        "A calibrated crop sample is duplicated.",
                    )
                seen_samples.add(sample_id)
                samples.append(
                    SymbolCropSample(
                        sample_id=sample_id,
                        source_image_id=image_id,
                        source_image_checksum_sha256=source_checksum,
                        source_image_relative_path=_text(
                            corpus_image.get("relativePath"), "source relativePath"
                        ),
                        source_group=_text(corpus_image.get("sourceGroup"), "sourceGroup"),
                        sequence_number=sequence_number,
                        board_index=board_index,
                        cell_index=cell_index,
                        row_index=row,
                        column_index=column,
                        crop_relative_path=crop_relative,
                        crop_checksum_sha256=crop_checksum,
                        observation_id=observation_id,
                        crop_sample_id=sample_id,
                        board_id=board_id,
                        board_relative_path=board_relative,
                        board_checksum_sha256=board_checksum,
                        calibration_profile_id=profile_id,
                        calibration_profile_version=profile_version,
                    )
                )
    samples.sort(key=lambda sample: (sample.sequence_number, sample.cell_index))
    if len(seen_boards) != 387 or len(samples) != 5805:
        raise SymbolDatasetError(
            "SYMBOL_DATASET_CORPUS_COUNT_MISMATCH",
            "Current calibrated corpus must contain 387 boards and 5805 cells.",
        )
    return SymbolCropInventory(
        corpus_id=corpus_id,
        corpus_manifest_sha256=corpus_sha,
        golden_annotations_sha256=annotations_sha,
        crop_report_sha256=crop_sha,
        samples=tuple(samples),
        inventory_version=CALIBRATED_INVENTORY_VERSION,
        cropper_version=CALIBRATED_CROPPER_VERSION,
        calibration_profile_set_sha256=profile_sha,
        calibration_profile_set_version=PROFILE_SET_VERSION,
        quality_report_sha256=_digest(quality_bytes),
    )
