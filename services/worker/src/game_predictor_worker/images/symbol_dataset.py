"""Deterministic inventory and reviewed-label export for M6 symbol crops."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

from PIL import Image, UnidentifiedImageError

from .rectification import (
    BOARD_COLUMNS,
    BOARD_ROWS,
    CALIBRATED_CROPPER_VERSION,
    CELL_HEIGHT,
    CELL_WIDTH,
    CROPPER_VERSION,
)

INVENTORY_VERSION = "symbol-crop-inventory-v1"
CALIBRATED_INVENTORY_VERSION = "symbol-crop-inventory-v2"
REVIEWED_INVENTORY_VERSION = "symbol-crop-inventory-v3"
REVIEWED_CROPPER_VERSION = "board-cell-crops-v16-reviewed-v14-merge-v1"
LABEL_SOURCE_VERSION = "reviewed-cell-labels-v1"
DATASET_VERSION = "labeled-symbol-dataset-v1"


class SymbolDatasetError(ValueError):
    """Stable fatal error for symbol dataset inventory and export."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class SymbolCropSample:
    sample_id: str
    source_image_id: str
    source_image_checksum_sha256: str
    source_image_relative_path: str
    source_group: str
    sequence_number: int
    board_index: int
    cell_index: int
    row_index: int
    column_index: int
    crop_relative_path: str
    crop_checksum_sha256: str
    observation_id: str | None = None
    crop_sample_id: str | None = None
    board_id: str | None = None
    board_relative_path: str | None = None
    board_checksum_sha256: str | None = None
    calibration_profile_id: str | None = None
    calibration_profile_version: int | None = None

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "boardIndex": self.board_index,
            "cellIndex": self.cell_index,
            "columnIndex": self.column_index,
            "cropChecksumSha256": self.crop_checksum_sha256,
            "cropRelativePath": self.crop_relative_path,
            "rowIndex": self.row_index,
            "sampleId": self.sample_id,
            "sequenceNumber": self.sequence_number,
            "sourceGroup": self.source_group,
            "sourceImageChecksumSha256": self.source_image_checksum_sha256,
            "sourceImageId": self.source_image_id,
            "sourceImageRelativePath": self.source_image_relative_path,
        }
        if self.observation_id is not None:
            value.update(
                {
                    "boardChecksumSha256": self.board_checksum_sha256,
                    "boardId": self.board_id,
                    "boardRelativePath": self.board_relative_path,
                    "calibrationProfileId": self.calibration_profile_id,
                    "calibrationProfileVersion": self.calibration_profile_version,
                    "cropSampleId": self.crop_sample_id,
                    "geometryStatus": "accepted",
                    "observationId": self.observation_id,
                }
            )
        return value


@dataclass(frozen=True, slots=True)
class SymbolCropInventory:
    corpus_id: str
    corpus_manifest_sha256: str
    golden_annotations_sha256: str
    crop_report_sha256: str
    samples: tuple[SymbolCropSample, ...]
    inventory_version: str = INVENTORY_VERSION
    cropper_version: str = CROPPER_VERSION
    calibration_profile_set_sha256: str | None = None
    calibration_profile_set_version: str | None = None
    quality_report_sha256: str | None = None
    geometry_report_sha256: str | None = None
    owner_acceptance_sha256: str | None = None

    def to_dict(self) -> dict[str, object]:
        source_groups = sorted({sample.source_group for sample in self.samples})
        value: dict[str, object] = {
            "boardCount": len({sample.sequence_number for sample in self.samples}),
            "cellHeight": CELL_HEIGHT,
            "cellWidth": CELL_WIDTH,
            "corpusId": self.corpus_id,
            "corpusManifestSha256": self.corpus_manifest_sha256,
            "cropReportSha256": self.crop_report_sha256,
            "cropperVersion": self.cropper_version,
            "goldenAnnotationsSha256": self.golden_annotations_sha256,
            "inventoryVersion": self.inventory_version,
            "sampleCount": len(self.samples),
            "samples": [sample.to_dict() for sample in self.samples],
            "schemaVersion": 1,
            "sourceGroupCount": len(source_groups),
            "sourceGroups": source_groups,
            "status": "ready",
        }
        if self.inventory_version == CALIBRATED_INVENTORY_VERSION:
            value.update(
                {
                    "calibrationProfileSetSha256": self.calibration_profile_set_sha256,
                    "calibrationProfileSetVersion": self.calibration_profile_set_version,
                    "qualityReportSha256": self.quality_report_sha256,
                    "trainingAllowed": True,
                }
            )
        elif self.inventory_version == REVIEWED_INVENTORY_VERSION:
            value.update(
                {
                    "geometryReportSha256": self.geometry_report_sha256,
                    "ownerAcceptanceSha256": self.owner_acceptance_sha256,
                    "trainingAllowed": True,
                }
            )
        return value

    def to_json_bytes(self) -> bytes:
        return _json_bytes(self.to_dict())


@dataclass(frozen=True, slots=True)
class ReviewedSymbol:
    symbol_id: str
    symbol_code: str


@dataclass(frozen=True, slots=True)
class ReviewedLabel:
    sample_id: str
    decision: Literal["accepted", "rejected"]
    symbol_id: str | None
    symbol_code: str | None


@dataclass(frozen=True, slots=True)
class ReviewedLabelSource:
    corpus_id: str
    game_id: str
    game_code: str
    review_revision: int
    reviewed_by: str
    symbols: tuple[ReviewedSymbol, ...]
    labels: tuple[ReviewedLabel, ...]


@dataclass(frozen=True, slots=True)
class LabeledSymbolSample:
    sample: SymbolCropSample
    symbol_id: str
    symbol_code: str
    asset_relative_path: str

    def to_dict(self) -> dict[str, object]:
        value = self.sample.to_dict()
        value.update(
            {
                "assetRelativePath": self.asset_relative_path,
                "symbolCode": self.symbol_code,
                "symbolId": self.symbol_id,
            }
        )
        return value


@dataclass(frozen=True, slots=True)
class SymbolDatasetExport:
    corpus_id: str
    game_id: str
    game_code: str
    inventory_version: str
    inventory_sha256: str
    corpus_manifest_sha256: str
    golden_annotations_sha256: str
    crop_report_sha256: str
    cropper_version: str
    calibration_profile_set_sha256: str | None
    calibration_profile_set_version: str | None
    quality_report_sha256: str | None
    geometry_report_sha256: str | None
    owner_acceptance_sha256: str | None
    label_source_sha256: str
    review_revision: int
    reviewed_by: str
    samples: tuple[LabeledSymbolSample, ...]
    pending_sample_ids: tuple[str, ...]
    rejected_sample_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        occurrences = Counter(sample.symbol_code for sample in self.samples)
        unique_assets: dict[str, set[str]] = {}
        symbol_ids: dict[str, str] = {}
        for sample in self.samples:
            unique_assets.setdefault(sample.symbol_code, set()).add(
                sample.sample.crop_checksum_sha256
            )
            symbol_ids[sample.symbol_code] = sample.symbol_id
        symbols = [
            {
                "sampleCount": occurrences[code],
                "symbolCode": code,
                "symbolId": symbol_ids[code],
                "uniqueAssetCount": len(unique_assets[code]),
            }
            for code in sorted(occurrences)
        ]
        status = "ready" if self.samples else "waiting_for_labels"
        value: dict[str, object] = {
            "assetCount": len({sample.sample.crop_checksum_sha256 for sample in self.samples}),
            "corpusId": self.corpus_id,
            "corpusManifestSha256": self.corpus_manifest_sha256,
            "cropReportSha256": self.crop_report_sha256,
            "cropperVersion": self.cropper_version,
            "datasetVersion": DATASET_VERSION,
            "gameCode": self.game_code,
            "gameId": self.game_id,
            "goldenAnnotationsSha256": self.golden_annotations_sha256,
            "inventoryVersion": self.inventory_version,
            "inventorySha256": self.inventory_sha256,
            "labelSourceSha256": self.label_source_sha256,
            "labelSourceVersion": LABEL_SOURCE_VERSION,
            "pendingCount": len(self.pending_sample_ids),
            "pendingSampleIds": list(self.pending_sample_ids),
            "rejectedCount": len(self.rejected_sample_ids),
            "rejectedSampleIds": list(self.rejected_sample_ids),
            "reviewRevision": self.review_revision,
            "reviewedBy": self.reviewed_by,
            "sampleCount": len(self.samples),
            "samples": [sample.to_dict() for sample in self.samples],
            "schemaVersion": 1,
            "status": status,
            "symbols": symbols,
        }
        if self.inventory_version == CALIBRATED_INVENTORY_VERSION:
            value.update(
                {
                    "calibrationProfileSetSha256": self.calibration_profile_set_sha256,
                    "calibrationProfileSetVersion": self.calibration_profile_set_version,
                    "qualityReportSha256": self.quality_report_sha256,
                }
            )
        elif self.inventory_version == REVIEWED_INVENTORY_VERSION:
            value.update(
                {
                    "geometryReportSha256": self.geometry_report_sha256,
                    "ownerAcceptanceSha256": self.owner_acceptance_sha256,
                }
            )
        return value

    def to_json_bytes(self) -> bytes:
        return _json_bytes(self.to_dict())


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _load_json(path: Path, code: str) -> tuple[bytes, Mapping[str, object]]:
    try:
        content = path.read_bytes()
        value: Any = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise SymbolDatasetError(code, f"Cannot read {path.name}.") from error
    return content, _mapping(value, path.name)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SymbolDatasetError(
            "SYMBOL_DATASET_INPUT_INVALID",
            f"{label} must be an object.",
        )
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise SymbolDatasetError(
            "SYMBOL_DATASET_INPUT_INVALID",
            f"{label} must be an array.",
        )
    return cast(Sequence[object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SymbolDatasetError(
            "SYMBOL_DATASET_INPUT_INVALID",
            f"{label} must be a non-empty string.",
        )
    return value.strip()


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise SymbolDatasetError(
            "SYMBOL_DATASET_INPUT_INVALID",
            f"{label} must be an integer.",
        )
    return value


def _sha256(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise SymbolDatasetError(
            "SYMBOL_DATASET_INPUT_INVALID",
            f"{label} must be a lowercase SHA-256.",
        )
    return text


def _safe_existing_path(root: Path, value: object, label: str) -> tuple[str, Path]:
    text = _text(value, label)
    relative = PurePosixPath(text)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise SymbolDatasetError(
            "SYMBOL_DATASET_UNSAFE_CROP_PATH",
            f"{label} must be a safe relative POSIX path.",
        )
    try:
        resolved = (root / Path(*relative.parts)).resolve(strict=True)
    except OSError as error:
        raise SymbolDatasetError(
            "SYMBOL_DATASET_CROP_UNREADABLE",
            f"{label} cannot be resolved.",
        ) from error
    if not resolved.is_relative_to(root):
        raise SymbolDatasetError(
            "SYMBOL_DATASET_UNSAFE_CROP_PATH",
            f"{label} escapes the crop root.",
        )
    return text, resolved


def _verify_crop(
    path: Path,
    *,
    expected_checksum: str,
    label: str,
) -> None:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise SymbolDatasetError(
            "SYMBOL_DATASET_CROP_UNREADABLE",
            f"{label} cannot be read.",
        ) from error
    if hashlib.sha256(content).hexdigest() != expected_checksum:
        raise SymbolDatasetError(
            "SYMBOL_DATASET_CROP_CHECKSUM_MISMATCH",
            f"{label} differs from the crop report.",
        )
    try:
        with Image.open(path) as image:
            image.load()
            if image.size != (CELL_WIDTH, CELL_HEIGHT) or image.mode != "RGB":
                raise SymbolDatasetError(
                    "SYMBOL_DATASET_CROP_DIMENSIONS_MISMATCH",
                    f"{label} must be RGB {CELL_WIDTH} x {CELL_HEIGHT}.",
                )
    except (OSError, UnidentifiedImageError) as error:
        raise SymbolDatasetError(
            "SYMBOL_DATASET_CROP_UNREADABLE",
            f"{label} is not a readable PNG.",
        ) from error


def _sample_id(
    *,
    corpus_id: str,
    source_checksum: str,
    sequence_number: int,
    board_index: int,
    row_index: int,
    column_index: int,
    crop_checksum: str,
) -> str:
    logical_key = "\0".join(
        (
            INVENTORY_VERSION,
            corpus_id,
            source_checksum,
            str(sequence_number),
            str(board_index),
            str(row_index),
            str(column_index),
            crop_checksum,
        )
    )
    return hashlib.sha256(logical_key.encode()).hexdigest()


def calibrated_observation_id(
    *,
    corpus_id: str,
    source_checksum: str,
    sequence_number: int,
    board_index: int,
    row_index: int,
    column_index: int,
) -> str:
    logical_key = "\0".join(
        (
            "cell-observation-v1",
            corpus_id,
            source_checksum,
            str(sequence_number),
            str(board_index),
            str(row_index),
            str(column_index),
        )
    )
    return hashlib.sha256(logical_key.encode()).hexdigest()


def calibrated_board_id(
    *,
    corpus_id: str,
    source_checksum: str,
    sequence_number: int,
    board_index: int,
) -> str:
    logical_key = "\0".join(
        (
            "recognized-board-v1",
            corpus_id,
            source_checksum,
            str(sequence_number),
            str(board_index),
        )
    )
    return hashlib.sha256(logical_key.encode()).hexdigest()


def calibrated_crop_sample_id(
    *,
    observation_id: str,
    cropper_version: str,
    profile_id: str,
    profile_version: int,
    crop_checksum: str,
) -> str:
    logical_key = "\0".join(
        (
            CALIBRATED_INVENTORY_VERSION,
            observation_id,
            cropper_version,
            profile_id,
            str(profile_version),
            crop_checksum,
        )
    )
    return hashlib.sha256(logical_key.encode()).hexdigest()


def reviewed_crop_sample_id(
    *,
    observation_id: str,
    cropper_version: str,
    geometry_provenance_id: str,
    geometry_provenance_version: int,
    crop_checksum: str,
) -> str:
    logical_key = "\0".join(
        (
            REVIEWED_INVENTORY_VERSION,
            observation_id,
            cropper_version,
            geometry_provenance_id,
            str(geometry_provenance_version),
            crop_checksum,
        )
    )
    return hashlib.sha256(logical_key.encode()).hexdigest()


def build_symbol_crop_inventory(
    corpus_manifest_path: Path,
    golden_annotations_path: Path,
    crop_report_path: Path,
    crop_root: Path,
) -> SymbolCropInventory:
    """Verify M5 artifacts and enumerate every cell without assigning labels."""

    corpus_bytes, corpus = _load_json(
        corpus_manifest_path,
        "SYMBOL_DATASET_CORPUS_INVALID",
    )
    golden_bytes, golden = _load_json(
        golden_annotations_path,
        "SYMBOL_DATASET_GOLDEN_INVALID",
    )
    crop_bytes, crops = _load_json(
        crop_report_path,
        "SYMBOL_DATASET_CROP_REPORT_INVALID",
    )
    corpus_id = _text(corpus.get("corpusId"), "corpusId")
    provenance = _mapping(
        golden.get("annotationProvenance"),
        "annotationProvenance",
    )
    if (
        golden.get("corpusId") != corpus_id
        or provenance.get("method") != "algorithm-assisted-visual-review"
    ):
        raise SymbolDatasetError(
            "SYMBOL_DATASET_GOLDEN_DRIFT",
            "Golden annotations do not match the reviewed corpus.",
        )
    if crops.get("cropperVersion") != CROPPER_VERSION or crops.get("status") != "cropped":
        raise SymbolDatasetError(
            "SYMBOL_DATASET_CROP_REPORT_UNSUPPORTED",
            "A complete board-cell-crops-v1 report is required.",
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

    corpus_by_checksum: dict[str, Mapping[str, object]] = {}
    corpus_by_id: dict[str, Mapping[str, object]] = {}
    for index, value in enumerate(_sequence(corpus.get("images"), "corpus.images")):
        image = _mapping(value, f"corpus.images[{index}]")
        image_id = _text(image.get("id"), f"corpus.images[{index}].id")
        checksum = _sha256(image.get("sha256"), f"corpus.images[{index}].sha256")
        if checksum in corpus_by_checksum or image_id in corpus_by_id:
            raise SymbolDatasetError(
                "SYMBOL_DATASET_CORPUS_DUPLICATE",
                "Corpus image identity is duplicated.",
            )
        corpus_by_checksum[checksum] = image
        corpus_by_id[image_id] = image
    if provenance.get("reviewedImageCount") != len(corpus_by_id):
        raise SymbolDatasetError(
            "SYMBOL_DATASET_GOLDEN_NOT_REVIEWED",
            "Golden provenance must cover every corpus image.",
        )

    golden_by_id: dict[str, Mapping[str, object]] = {}
    seen_sequences: set[int] = set()
    for index, value in enumerate(_sequence(golden.get("images"), "golden.images")):
        image = _mapping(value, f"golden.images[{index}]")
        image_id = _text(image.get("imageId"), f"golden.images[{index}].imageId")
        if image_id in golden_by_id or image_id not in corpus_by_id:
            raise SymbolDatasetError(
                "SYMBOL_DATASET_GOLDEN_DRIFT",
                "Golden image identity is missing or duplicated.",
            )
        if image.get("status") != "complete":
            raise SymbolDatasetError(
                "SYMBOL_DATASET_GOLDEN_NOT_REVIEWED",
                "Every golden image must be complete.",
            )
        for board_index, board_value in enumerate(
            _sequence(image.get("boards"), f"golden.images[{index}].boards")
        ):
            board = _mapping(
                board_value,
                f"golden.images[{index}].boards[{board_index}]",
            )
            sequence_number = _integer(
                board.get("sequenceNumber"),
                f"golden.images[{index}].boards[{board_index}].sequenceNumber",
            )
            if sequence_number <= 0 or sequence_number in seen_sequences:
                raise SymbolDatasetError(
                    "SYMBOL_DATASET_SEQUENCE_AMBIGUOUS",
                    "Reviewed sequence numbers must be positive and unique.",
                )
            seen_sequences.add(sequence_number)
        golden_by_id[image_id] = image
    if seen_sequences != set(range(1, len(seen_sequences) + 1)):
        raise SymbolDatasetError(
            "SYMBOL_DATASET_SEQUENCE_AMBIGUOUS",
            "Reviewed sequence numbers must be contiguous from one.",
        )

    samples: list[SymbolCropSample] = []
    seen_sample_ids: set[str] = set()
    seen_crop_locations: set[tuple[str, int, int, int]] = set()
    seen_crop_sources: set[str] = set()
    for image_index, value in enumerate(_sequence(crops.get("images"), "crops.images")):
        crop_image = _mapping(value, f"crops.images[{image_index}]")
        if crop_image.get("status") != "cropped":
            raise SymbolDatasetError(
                "SYMBOL_DATASET_CROP_REPORT_UNSUPPORTED",
                "Every crop source must have status cropped.",
            )
        source_checksum = _sha256(
            crop_image.get("sourceChecksumSha256"),
            f"crops.images[{image_index}].sourceChecksumSha256",
        )
        if source_checksum in seen_crop_sources or source_checksum not in corpus_by_checksum:
            raise SymbolDatasetError(
                "SYMBOL_DATASET_CROP_REPORT_DRIFT",
                "Crop source identity is missing or duplicated.",
            )
        seen_crop_sources.add(source_checksum)
        corpus_image = corpus_by_checksum[source_checksum]
        image_id = _text(corpus_image.get("id"), "corpus image id")
        golden_image = golden_by_id.get(image_id)
        if golden_image is None:
            raise SymbolDatasetError(
                "SYMBOL_DATASET_GOLDEN_DRIFT",
                "Crop source has no reviewed golden annotation.",
            )
        golden_boards = _sequence(golden_image.get("boards"), "golden boards")
        crop_boards = _sequence(crop_image.get("boards"), "crop boards")
        expected_count = _integer(
            corpus_image.get("expectedBoardCount"),
            "expectedBoardCount",
        )
        if len(golden_boards) != expected_count or len(crop_boards) != expected_count:
            raise SymbolDatasetError(
                "SYMBOL_DATASET_BOARD_COUNT_MISMATCH",
                "Corpus, golden and crop board counts differ.",
            )
        for board_index, (golden_value, crop_value) in enumerate(
            zip(golden_boards, crop_boards, strict=True)
        ):
            golden_board = _mapping(golden_value, f"golden board {board_index}")
            crop_board = _mapping(crop_value, f"crop board {board_index}")
            position = _integer(crop_board.get("positionIndex"), "positionIndex")
            if (
                position != board_index
                or _integer(golden_board.get("positionIndex"), "golden positionIndex")
                != board_index
            ):
                raise SymbolDatasetError(
                    "SYMBOL_DATASET_BOARD_INDEX_MISMATCH",
                    "Board positions must be contiguous and row-major.",
                )
            sequence_number = _integer(
                golden_board.get("sequenceNumber"),
                "sequenceNumber",
            )
            cells = _sequence(crop_board.get("cells"), "cells")
            if len(cells) != BOARD_ROWS * BOARD_COLUMNS:
                raise SymbolDatasetError(
                    "SYMBOL_DATASET_CELL_COUNT_MISMATCH",
                    "Each board must contain exactly 15 cells.",
                )
            for cell_index, cell_value in enumerate(cells):
                cell = _mapping(cell_value, f"cells[{cell_index}]")
                row_index, column_index = divmod(cell_index, BOARD_COLUMNS)
                if (
                    _integer(cell.get("rowIndex"), "rowIndex") != row_index
                    or _integer(cell.get("columnIndex"), "columnIndex") != column_index
                    or _integer(cell.get("width"), "width") != CELL_WIDTH
                    or _integer(cell.get("height"), "height") != CELL_HEIGHT
                ):
                    raise SymbolDatasetError(
                        "SYMBOL_DATASET_CELL_INDEX_MISMATCH",
                        "Cell geometry must be 3 x 5 row-major.",
                    )
                location = (source_checksum, board_index, row_index, column_index)
                if location in seen_crop_locations:
                    raise SymbolDatasetError(
                        "SYMBOL_DATASET_CELL_DUPLICATE",
                        "A crop location is duplicated.",
                    )
                seen_crop_locations.add(location)
                relative_path, crop_path = _safe_existing_path(
                    crop_base,
                    cell.get("relativePath"),
                    "cell.relativePath",
                )
                crop_checksum = _sha256(
                    cell.get("checksumSha256"),
                    "cell.checksumSha256",
                )
                _verify_crop(
                    crop_path,
                    expected_checksum=crop_checksum,
                    label=f"cell {image_id}/{board_index}/{cell_index}",
                )
                sample_id = _sample_id(
                    corpus_id=corpus_id,
                    source_checksum=source_checksum,
                    sequence_number=sequence_number,
                    board_index=board_index,
                    row_index=row_index,
                    column_index=column_index,
                    crop_checksum=crop_checksum,
                )
                if sample_id in seen_sample_ids:
                    raise SymbolDatasetError(
                        "SYMBOL_DATASET_SAMPLE_DUPLICATE",
                        "A logical sample identity is duplicated.",
                    )
                seen_sample_ids.add(sample_id)
                samples.append(
                    SymbolCropSample(
                        sample_id=sample_id,
                        source_image_id=image_id,
                        source_image_checksum_sha256=source_checksum,
                        source_image_relative_path=_text(
                            corpus_image.get("relativePath"),
                            "source image relativePath",
                        ),
                        source_group=_text(
                            corpus_image.get("sourceGroup"),
                            "sourceGroup",
                        ),
                        sequence_number=sequence_number,
                        board_index=board_index,
                        cell_index=cell_index,
                        row_index=row_index,
                        column_index=column_index,
                        crop_relative_path=relative_path,
                        crop_checksum_sha256=crop_checksum,
                    )
                )

    if seen_crop_sources != set(corpus_by_checksum):
        raise SymbolDatasetError(
            "SYMBOL_DATASET_CROP_REPORT_DRIFT",
            "Crop report does not cover the complete corpus.",
        )
    samples.sort(
        key=lambda sample: (
            sample.sequence_number,
            sample.row_index,
            sample.column_index,
        )
    )
    return SymbolCropInventory(
        corpus_id=corpus_id,
        corpus_manifest_sha256=hashlib.sha256(corpus_bytes).hexdigest(),
        golden_annotations_sha256=hashlib.sha256(golden_bytes).hexdigest(),
        crop_report_sha256=hashlib.sha256(crop_bytes).hexdigest(),
        samples=tuple(samples),
    )


def load_symbol_crop_inventory(path: Path) -> tuple[bytes, SymbolCropInventory]:
    """Load and revalidate a deterministic symbol crop inventory."""
    content, value = _load_json(path, "SYMBOL_DATASET_INVENTORY_INVALID")
    inventory_version = value.get("inventoryVersion")
    if (
        value.get("schemaVersion") != 1
        or inventory_version
        not in {
            INVENTORY_VERSION,
            CALIBRATED_INVENTORY_VERSION,
            REVIEWED_INVENTORY_VERSION,
        }
        or value.get("status") != "ready"
    ):
        raise SymbolDatasetError(
            "SYMBOL_DATASET_INVENTORY_UNSUPPORTED",
            "A ready supported symbol crop inventory is required.",
        )
    if inventory_version == CALIBRATED_INVENTORY_VERSION and (
        value.get("trainingAllowed") is not True
        or value.get("cropperVersion") != CALIBRATED_CROPPER_VERSION
        or value.get("cellWidth") != CELL_WIDTH
        or value.get("cellHeight") != CELL_HEIGHT
    ):
        raise SymbolDatasetError(
            "SYMBOL_DATASET_CALIBRATED_INVENTORY_REQUIRED",
            "A training-approved calibrated symbol crop inventory is required.",
        )
    if inventory_version == REVIEWED_INVENTORY_VERSION and (
        value.get("trainingAllowed") is not True
        or value.get("cropperVersion") != REVIEWED_CROPPER_VERSION
        or value.get("cellWidth") != CELL_WIDTH
        or value.get("cellHeight") != CELL_HEIGHT
        or not value.get("geometryReportSha256")
        or not value.get("ownerAcceptanceSha256")
    ):
        raise SymbolDatasetError(
            "SYMBOL_DATASET_REVIEWED_INVENTORY_REQUIRED",
            "An owner-accepted v16 symbol crop inventory is required.",
        )
    versioned_inventory = inventory_version in {
        CALIBRATED_INVENTORY_VERSION,
        REVIEWED_INVENTORY_VERSION,
    }
    samples: list[SymbolCropSample] = []
    for index, sample_value in enumerate(_sequence(value.get("samples"), "samples")):
        sample = _mapping(sample_value, f"samples[{index}]")
        parsed = SymbolCropSample(
            sample_id=_sha256(sample.get("sampleId"), "sampleId"),
            source_image_id=_text(sample.get("sourceImageId"), "sourceImageId"),
            source_image_checksum_sha256=_sha256(
                sample.get("sourceImageChecksumSha256"),
                "sourceImageChecksumSha256",
            ),
            source_image_relative_path=_text(
                sample.get("sourceImageRelativePath"),
                "sourceImageRelativePath",
            ),
            source_group=_text(sample.get("sourceGroup"), "sourceGroup"),
            sequence_number=_integer(
                sample.get("sequenceNumber"),
                "sequenceNumber",
            ),
            board_index=_integer(sample.get("boardIndex"), "boardIndex"),
            cell_index=_integer(sample.get("cellIndex"), "cellIndex"),
            row_index=_integer(sample.get("rowIndex"), "rowIndex"),
            column_index=_integer(sample.get("columnIndex"), "columnIndex"),
            crop_relative_path=_text(
                sample.get("cropRelativePath"),
                "cropRelativePath",
            ),
            crop_checksum_sha256=_sha256(
                sample.get("cropChecksumSha256"),
                "cropChecksumSha256",
            ),
            observation_id=(
                _sha256(sample.get("observationId"), "observationId")
                if versioned_inventory
                else None
            ),
            crop_sample_id=(
                _sha256(sample.get("cropSampleId"), "cropSampleId")
                if versioned_inventory
                else None
            ),
            board_id=(
                _sha256(sample.get("boardId"), "boardId")
                if versioned_inventory
                else None
            ),
            board_relative_path=(
                _text(sample.get("boardRelativePath"), "boardRelativePath")
                if versioned_inventory
                else None
            ),
            board_checksum_sha256=(
                _sha256(sample.get("boardChecksumSha256"), "boardChecksumSha256")
                if versioned_inventory
                else None
            ),
            calibration_profile_id=(
                _sha256(sample.get("calibrationProfileId"), "calibrationProfileId")
                if versioned_inventory
                else None
            ),
            calibration_profile_version=(
                _integer(sample.get("calibrationProfileVersion"), "calibrationProfileVersion")
                if versioned_inventory
                else None
            ),
        )
        if inventory_version == CALIBRATED_INVENTORY_VERSION:
            expected_sample_id = calibrated_crop_sample_id(
                observation_id=cast(str, parsed.observation_id),
                cropper_version=_text(value.get("cropperVersion"), "cropperVersion"),
                profile_id=cast(str, parsed.calibration_profile_id),
                profile_version=cast(int, parsed.calibration_profile_version),
                crop_checksum=parsed.crop_checksum_sha256,
            )
        elif inventory_version == REVIEWED_INVENTORY_VERSION:
            expected_sample_id = reviewed_crop_sample_id(
                observation_id=cast(str, parsed.observation_id),
                cropper_version=_text(value.get("cropperVersion"), "cropperVersion"),
                geometry_provenance_id=cast(str, parsed.calibration_profile_id),
                geometry_provenance_version=cast(
                    int, parsed.calibration_profile_version
                ),
                crop_checksum=parsed.crop_checksum_sha256,
            )
        else:
            expected_sample_id = _sample_id(
                corpus_id=_text(value.get("corpusId"), "corpusId"),
                source_checksum=parsed.source_image_checksum_sha256,
                sequence_number=parsed.sequence_number,
                board_index=parsed.board_index,
                row_index=parsed.row_index,
                column_index=parsed.column_index,
                crop_checksum=parsed.crop_checksum_sha256,
            )
        if (
            parsed.sequence_number <= 0
            or not 0 <= parsed.board_index <= 8
            or not 0 <= parsed.row_index < BOARD_ROWS
            or not 0 <= parsed.column_index < BOARD_COLUMNS
            or parsed.cell_index != parsed.row_index * BOARD_COLUMNS + parsed.column_index
            or parsed.sample_id != expected_sample_id
            or parsed.crop_sample_id not in {None, parsed.sample_id}
            or (
                versioned_inventory
                and parsed.observation_id
                != calibrated_observation_id(
                    corpus_id=_text(value.get("corpusId"), "corpusId"),
                    source_checksum=parsed.source_image_checksum_sha256,
                    sequence_number=parsed.sequence_number,
                    board_index=parsed.board_index,
                    row_index=parsed.row_index,
                    column_index=parsed.column_index,
                )
            )
            or (
                versioned_inventory
                and parsed.board_id
                != calibrated_board_id(
                    corpus_id=_text(value.get("corpusId"), "corpusId"),
                    source_checksum=parsed.source_image_checksum_sha256,
                    sequence_number=parsed.sequence_number,
                    board_index=parsed.board_index,
                )
            )
            or (
                versioned_inventory
                and sample.get("geometryStatus") != "accepted"
            )
        ):
            raise SymbolDatasetError(
                "SYMBOL_DATASET_INVENTORY_DRIFT",
                "Inventory sample identity or row-major position is invalid.",
            )
        samples.append(parsed)
    if len({sample.sample_id for sample in samples}) != len(samples):
        raise SymbolDatasetError(
            "SYMBOL_DATASET_SAMPLE_DUPLICATE",
            "Inventory sample IDs must be unique.",
        )
    source_groups = sorted({sample.source_group for sample in samples})
    board_cells: dict[tuple[str, int], list[int]] = {}
    board_details: dict[tuple[str, int], tuple[object, ...]] = {}
    for inventory_sample in samples:
        board_key = (
            inventory_sample.source_image_checksum_sha256,
            inventory_sample.board_index,
        )
        board_cells.setdefault(board_key, []).append(inventory_sample.cell_index)
        details = (
            inventory_sample.sequence_number,
            inventory_sample.board_id,
            inventory_sample.board_relative_path,
            inventory_sample.board_checksum_sha256,
            inventory_sample.calibration_profile_id,
            inventory_sample.calibration_profile_version,
        )
        previous_details = board_details.setdefault(board_key, details)
        if previous_details != details:
            raise SymbolDatasetError(
                "SYMBOL_DATASET_INVENTORY_DRIFT",
                "Cells of one board have inconsistent provenance.",
            )
    sequence_numbers = sorted(cast(int, details[0]) for details in board_details.values())
    if (
        value.get("sampleCount") != len(samples)
        or value.get("boardCount") != len(board_details)
        or value.get("sourceGroupCount") != len(source_groups)
        or value.get("sourceGroups") != source_groups
        or (
            versioned_inventory
            and (
                sequence_numbers != list(range(1, len(board_details) + 1))
                or any(
                    sorted(cells) != list(range(BOARD_ROWS * BOARD_COLUMNS))
                    for cells in board_cells.values()
                )
            )
        )
    ):
        raise SymbolDatasetError(
            "SYMBOL_DATASET_INVENTORY_DRIFT",
            "Inventory counts, source groups or board completeness are invalid.",
        )
    return content, SymbolCropInventory(
        corpus_id=_text(value.get("corpusId"), "corpusId"),
        corpus_manifest_sha256=_sha256(
            value.get("corpusManifestSha256"),
            "corpusManifestSha256",
        ),
        golden_annotations_sha256=_sha256(
            value.get("goldenAnnotationsSha256"),
            "goldenAnnotationsSha256",
        ),
        crop_report_sha256=_sha256(
            value.get("cropReportSha256"),
            "cropReportSha256",
        ),
        samples=tuple(samples),
        inventory_version=cast(str, inventory_version),
        cropper_version=_text(value.get("cropperVersion"), "cropperVersion"),
        calibration_profile_set_sha256=(
            _sha256(value.get("calibrationProfileSetSha256"), "calibrationProfileSetSha256")
            if inventory_version == CALIBRATED_INVENTORY_VERSION
            else None
        ),
        calibration_profile_set_version=(
            _text(value.get("calibrationProfileSetVersion"), "calibrationProfileSetVersion")
            if inventory_version == CALIBRATED_INVENTORY_VERSION
            else None
        ),
        quality_report_sha256=(
            _sha256(value.get("qualityReportSha256"), "qualityReportSha256")
            if inventory_version == CALIBRATED_INVENTORY_VERSION
            else None
        ),
        geometry_report_sha256=(
            _sha256(value.get("geometryReportSha256"), "geometryReportSha256")
            if inventory_version == REVIEWED_INVENTORY_VERSION
            else None
        ),
        owner_acceptance_sha256=(
            _sha256(value.get("ownerAcceptanceSha256"), "ownerAcceptanceSha256")
            if inventory_version == REVIEWED_INVENTORY_VERSION
            else None
        ),
    )


def load_reviewed_label_source(path: Path) -> tuple[bytes, ReviewedLabelSource]:
    """Load and validate reviewed-cell-labels-v1."""
    content, value = _load_json(path, "SYMBOL_DATASET_LABEL_SOURCE_INVALID")
    if value.get("schemaVersion") != 1 or value.get("labelSourceVersion") != LABEL_SOURCE_VERSION:
        raise SymbolDatasetError(
            "SYMBOL_DATASET_LABEL_SOURCE_UNSUPPORTED",
            "A reviewed-cell-labels-v1 input is required.",
        )
    symbols: list[ReviewedSymbol] = []
    seen_ids: set[str] = set()
    seen_codes: set[str] = set()
    for index, symbol_value in enumerate(_sequence(value.get("symbols"), "symbols")):
        symbol = _mapping(symbol_value, f"symbols[{index}]")
        symbol_id = _text(symbol.get("symbolId"), f"symbols[{index}].symbolId")
        symbol_code = _text(symbol.get("symbolCode"), f"symbols[{index}].symbolCode")
        if symbol_id in seen_ids or symbol_code in seen_codes:
            raise SymbolDatasetError(
                "SYMBOL_DATASET_SYMBOL_DUPLICATE",
                "Symbol IDs and codes must be unique.",
            )
        seen_ids.add(symbol_id)
        seen_codes.add(symbol_code)
        symbols.append(ReviewedSymbol(symbol_id=symbol_id, symbol_code=symbol_code))
    if not symbols:
        raise SymbolDatasetError(
            "SYMBOL_DATASET_SYMBOLS_EMPTY",
            "At least one reviewed symbol is required.",
        )
    labels: list[ReviewedLabel] = []
    seen_samples: set[str] = set()
    for index, label_value in enumerate(_sequence(value.get("labels"), "labels")):
        label = _mapping(label_value, f"labels[{index}]")
        sample_id = _sha256(label.get("sampleId"), f"labels[{index}].sampleId")
        if sample_id in seen_samples:
            raise SymbolDatasetError(
                "SYMBOL_DATASET_LABEL_DUPLICATE",
                "A sample may have only one reviewed decision.",
            )
        seen_samples.add(sample_id)
        decision = label.get("decision")
        if decision not in {"accepted", "rejected"}:
            raise SymbolDatasetError(
                "SYMBOL_DATASET_LABEL_DECISION_INVALID",
                "Label decision must be accepted or rejected.",
            )
        raw_symbol_id = label.get("symbolId")
        raw_symbol_code = label.get("symbolCode")
        if decision == "accepted":
            reviewed_symbol_id = _text(
                raw_symbol_id,
                f"labels[{index}].symbolId",
            )
            reviewed_symbol_code = _text(
                raw_symbol_code,
                f"labels[{index}].symbolCode",
            )
            if reviewed_symbol_id not in seen_ids or reviewed_symbol_code not in seen_codes:
                raise SymbolDatasetError(
                    "SYMBOL_DATASET_SYMBOL_UNKNOWN",
                    "Accepted label references an unknown symbol.",
                )
            expected = next(symbol for symbol in symbols if symbol.symbol_id == reviewed_symbol_id)
            if expected.symbol_code != reviewed_symbol_code:
                raise SymbolDatasetError(
                    "SYMBOL_DATASET_SYMBOL_CONFLICT",
                    "Symbol ID and code do not identify the same symbol.",
                )
        elif raw_symbol_id is not None or raw_symbol_code is not None:
            raise SymbolDatasetError(
                "SYMBOL_DATASET_REJECTED_HAS_SYMBOL",
                "Rejected labels cannot carry a symbol.",
            )
        else:
            reviewed_symbol_id = None
            reviewed_symbol_code = None
        labels.append(
            ReviewedLabel(
                sample_id=sample_id,
                decision=cast(Literal["accepted", "rejected"], decision),
                symbol_id=reviewed_symbol_id,
                symbol_code=reviewed_symbol_code,
            )
        )
    review_revision = _integer(value.get("reviewRevision"), "reviewRevision")
    if review_revision <= 0:
        raise SymbolDatasetError(
            "SYMBOL_DATASET_INPUT_INVALID",
            "reviewRevision must be positive.",
        )
    return content, ReviewedLabelSource(
        corpus_id=_text(value.get("corpusId"), "corpusId"),
        game_id=_text(value.get("gameId"), "gameId"),
        game_code=_text(value.get("gameCode"), "gameCode"),
        review_revision=review_revision,
        reviewed_by=_text(value.get("reviewedBy"), "reviewedBy"),
        symbols=tuple(symbols),
        labels=tuple(labels),
    )


def _write_immutable(path: Path, source: Path) -> None:
    if path.exists():
        try:
            if path.read_bytes() != source.read_bytes():
                raise SymbolDatasetError(
                    "SYMBOL_DATASET_ASSET_COLLISION",
                    "Existing dataset asset has different content.",
                )
        except OSError as error:
            raise SymbolDatasetError(
                "SYMBOL_DATASET_ASSET_UNREADABLE",
                "Existing dataset asset cannot be read.",
            ) from error
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        shutil.copyfile(source, temporary)
        temporary.replace(path)
    except OSError as error:
        raise SymbolDatasetError(
            "SYMBOL_DATASET_ASSET_WRITE_FAILED",
            "Dataset asset cannot be written.",
        ) from error
    finally:
        if temporary.exists():
            temporary.unlink()


def export_reviewed_symbol_dataset(
    inventory_path: Path,
    label_source_path: Path,
    crop_root: Path,
    artifact_root: Path,
) -> SymbolDatasetExport:
    """Export accepted labels and one immutable binary per unique crop checksum."""

    inventory_bytes, inventory = load_symbol_crop_inventory(inventory_path)
    if inventory.inventory_version not in {
        CALIBRATED_INVENTORY_VERSION,
        REVIEWED_INVENTORY_VERSION,
    }:
        raise SymbolDatasetError(
            "SYMBOL_DATASET_CALIBRATED_INVENTORY_REQUIRED",
            "Dataset export accepts only training-approved versioned crops.",
        )
    label_bytes, label_source = load_reviewed_label_source(label_source_path)
    if label_source.corpus_id != inventory.corpus_id:
        raise SymbolDatasetError(
            "SYMBOL_DATASET_LABEL_SOURCE_DRIFT",
            "Label source and inventory refer to different corpora.",
        )
    try:
        crop_base = crop_root.resolve(strict=True)
    except OSError as error:
        raise SymbolDatasetError(
            "SYMBOL_DATASET_CROP_ROOT_NOT_FOUND",
            "Crop artifact root does not exist.",
        ) from error
    output_base = artifact_root.resolve()
    if output_base == crop_base or output_base.is_relative_to(crop_base):
        raise SymbolDatasetError(
            "SYMBOL_DATASET_OUTPUT_IN_CROP_ROOT",
            "Dataset assets must use a separate artifact root.",
        )
    samples_by_id = {sample.sample_id: sample for sample in inventory.samples}
    labels_by_id = {label.sample_id: label for label in label_source.labels}
    unknown = sorted(set(labels_by_id) - set(samples_by_id))
    if unknown:
        raise SymbolDatasetError(
            "SYMBOL_DATASET_LABEL_SAMPLE_UNKNOWN",
            "Label source references a sample outside the inventory.",
        )

    labeled: list[LabeledSymbolSample] = []
    pending: list[str] = []
    rejected: list[str] = []
    labels_by_asset: dict[str, tuple[str, str]] = {}
    for sample in inventory.samples:
        decision = labels_by_id.get(sample.sample_id)
        if decision is None:
            pending.append(sample.sample_id)
            continue
        if decision.decision == "rejected":
            rejected.append(sample.sample_id)
            continue
        assert decision.symbol_id is not None
        assert decision.symbol_code is not None
        previous = labels_by_asset.get(sample.crop_checksum_sha256)
        current = (decision.symbol_id, decision.symbol_code)
        if previous is not None and previous != current:
            raise SymbolDatasetError(
                "SYMBOL_DATASET_ASSET_LABEL_CONFLICT",
                "Identical crop bytes have conflicting reviewed labels.",
            )
        labels_by_asset[sample.crop_checksum_sha256] = current
        _, source_path = _safe_existing_path(
            crop_base,
            sample.crop_relative_path,
            "sample.cropRelativePath",
        )
        _verify_crop(
            source_path,
            expected_checksum=sample.crop_checksum_sha256,
            label=f"sample {sample.sample_id}",
        )
        asset_relative_path = str(
            PurePosixPath(
                DATASET_VERSION,
                "assets",
                sample.crop_checksum_sha256[:2],
                f"{sample.crop_checksum_sha256}.png",
            )
        )
        target = output_base / Path(*PurePosixPath(asset_relative_path).parts)
        _write_immutable(target, source_path)
        labeled.append(
            LabeledSymbolSample(
                sample=sample,
                symbol_id=decision.symbol_id,
                symbol_code=decision.symbol_code,
                asset_relative_path=asset_relative_path,
            )
        )
    return SymbolDatasetExport(
        corpus_id=inventory.corpus_id,
        game_id=label_source.game_id,
        game_code=label_source.game_code,
        inventory_version=inventory.inventory_version,
        inventory_sha256=hashlib.sha256(inventory_bytes).hexdigest(),
        corpus_manifest_sha256=inventory.corpus_manifest_sha256,
        golden_annotations_sha256=inventory.golden_annotations_sha256,
        crop_report_sha256=inventory.crop_report_sha256,
        cropper_version=inventory.cropper_version,
        calibration_profile_set_sha256=inventory.calibration_profile_set_sha256,
        calibration_profile_set_version=inventory.calibration_profile_set_version,
        quality_report_sha256=inventory.quality_report_sha256,
        geometry_report_sha256=inventory.geometry_report_sha256,
        owner_acceptance_sha256=inventory.owner_acceptance_sha256,
        label_source_sha256=hashlib.sha256(label_bytes).hexdigest(),
        review_revision=label_source.review_revision,
        reviewed_by=label_source.reviewed_by,
        samples=tuple(labeled),
        pending_sample_ids=tuple(pending),
        rejected_sample_ids=tuple(rejected),
    )
