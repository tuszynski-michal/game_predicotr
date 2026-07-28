"""Validation for the immutable M5 source corpus and golden annotations."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

from game_predictor_worker.images.image_file import (
    ImageFileError,
    read_jpeg_dimensions,
    sha256_file,
)

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class CorpusValidationError(ValueError):
    """Stable validation failure for a corpus contract."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class CorpusValidationReport:
    corpus_id: str
    image_count: int
    complete_annotation_count: int
    pending_annotation_ids: tuple[str, ...]
    source_group_count: int
    total_size_bytes: int
    ready_for_geometry_benchmark: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "completeAnnotationCount": self.complete_annotation_count,
            "corpusId": self.corpus_id,
            "imageCount": self.image_count,
            "pendingAnnotationIds": list(self.pending_annotation_ids),
            "readyForGeometryBenchmark": self.ready_for_geometry_benchmark,
            "sourceGroupCount": self.source_group_count,
            "status": ("ready" if self.ready_for_geometry_benchmark else "provisional"),
            "totalSizeBytes": self.total_size_bytes,
            "warnings": list(self.warnings),
        }


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CorpusValidationError("M5_CORPUS_INVALID_CONTRACT", f"{label} must be an object.")
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise CorpusValidationError("M5_CORPUS_INVALID_CONTRACT", f"{label} must be an array.")
    return cast(Sequence[object], value)


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CorpusValidationError(
            "M5_CORPUS_INVALID_CONTRACT", f"{label} must be a non-empty string."
        )
    return value


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise CorpusValidationError(
            "M5_CORPUS_INVALID_CONTRACT",
            f"{label} must be an integer greater than or equal to {minimum}.",
        )
    return value


def _number(value: object, label: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise CorpusValidationError("M5_CORPUS_INVALID_CONTRACT", f"{label} must be a number.")
    return float(value)


def _load_json(path: Path, label: str) -> Mapping[str, object]:
    try:
        value: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CorpusValidationError(
            "M5_CORPUS_INVALID_JSON", f"Cannot read {label}: {path}."
        ) from error
    return _mapping(value, label)


def _safe_relative_path(root: Path, value: object, label: str) -> Path:
    text = _string(value, label)
    path = PurePosixPath(text)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise CorpusValidationError(
            "M5_CORPUS_UNSAFE_PATH", f"{label} must be a safe relative POSIX path."
        )
    resolved_root = root.resolve()
    resolved = (resolved_root / Path(*path.parts)).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise CorpusValidationError("M5_CORPUS_UNSAFE_PATH", f"{label} escapes its root.")
    return resolved


def _validate_point(value: object, label: str, width: int, height: int) -> None:
    point = _mapping(value, label)
    x = _number(point.get("x"), f"{label}.x")
    y = _number(point.get("y"), f"{label}.y")
    if not 0 <= x <= width or not 0 <= y <= height:
        raise CorpusValidationError(
            "M5_CORPUS_GEOMETRY_OUT_OF_BOUNDS", f"{label} is outside the source image."
        )


def _validate_quad(value: object, label: str, width: int, height: int) -> None:
    quad = _sequence(value, label)
    if len(quad) != 4:
        raise CorpusValidationError(
            "M5_CORPUS_INVALID_GEOMETRY", f"{label} must contain four points."
        )
    for index, point in enumerate(quad):
        _validate_point(point, f"{label}[{index}]", width, height)


def _validate_box(value: object, label: str, width: int, height: int) -> None:
    box = _mapping(value, label)
    x = _number(box.get("x"), f"{label}.x")
    y = _number(box.get("y"), f"{label}.y")
    box_width = _number(box.get("width"), f"{label}.width")
    box_height = _number(box.get("height"), f"{label}.height")
    if (
        x < 0
        or y < 0
        or box_width <= 0
        or box_height <= 0
        or x + box_width > width
        or y + box_height > height
    ):
        raise CorpusValidationError(
            "M5_CORPUS_GEOMETRY_OUT_OF_BOUNDS", f"{label} is outside the source image."
        )


def _validate_complete_geometry(
    annotation: Mapping[str, object],
    image: Mapping[str, object],
) -> None:
    image_id = _string(image.get("id"), "image.id")
    width = _integer(image.get("width"), f"{image_id}.width", minimum=1)
    height = _integer(image.get("height"), f"{image_id}.height", minimum=1)
    _validate_quad(annotation.get("pageQuad"), f"{image_id}.pageQuad", width, height)
    boards = _sequence(annotation.get("boards"), f"{image_id}.boards")
    expected_board_count = _integer(
        image.get("expectedBoardCount"),
        f"{image_id}.expectedBoardCount",
        minimum=1,
    )
    if len(boards) != expected_board_count:
        raise CorpusValidationError(
            "M5_CORPUS_INVALID_GEOMETRY",
            f"{image_id}.boards must match expectedBoardCount.",
        )
    observed_positions: set[int] = set()
    sequence_numbers = [
        _integer(value, f"{image_id}.sequenceNumbers", minimum=1)
        for value in _sequence(annotation.get("sequenceNumbers"), f"{image_id}.sequenceNumbers")
    ]
    for board_value in boards:
        board = _mapping(board_value, f"{image_id}.board")
        position = _integer(board.get("positionIndex"), f"{image_id}.positionIndex")
        if position >= expected_board_count or position in observed_positions:
            raise CorpusValidationError(
                "M5_CORPUS_INVALID_BOARD_INDEX",
                f"{image_id} has an invalid or duplicate board position {position}.",
            )
        observed_positions.add(position)
        if (
            _integer(board.get("sequenceNumber"), f"{image_id}.sequenceNumber", minimum=1)
            != (sequence_numbers[position])
        ):
            raise CorpusValidationError(
                "M5_CORPUS_SEQUENCE_MISMATCH",
                f"{image_id} board {position} has a mismatched sequence number.",
            )
        _validate_quad(
            board.get("boardQuad"),
            f"{image_id}.boards[{position}].boardQuad",
            width,
            height,
        )
        _validate_box(
            board.get("numberBox"),
            f"{image_id}.boards[{position}].numberBox",
            width,
            height,
        )
    if observed_positions != set(range(expected_board_count)):
        raise CorpusValidationError(
            "M5_CORPUS_INVALID_BOARD_INDEX",
            f"{image_id} board positions are not contiguous from zero.",
        )


def validate_corpus(
    repository_root: Path,
    manifest_path: Path,
    annotations_path: Path,
) -> CorpusValidationReport:
    manifest = _load_json(manifest_path, "manifest")
    annotations = _load_json(annotations_path, "annotations")
    if manifest.get("schemaVersion") != 1 or annotations.get("schemaVersion") != 1:
        raise CorpusValidationError(
            "M5_CORPUS_UNSUPPORTED_SCHEMA", "Manifest and annotations must use schema version 1."
        )
    corpus_id = _string(manifest.get("corpusId"), "manifest.corpusId")
    if annotations.get("corpusId") != corpus_id:
        raise CorpusValidationError(
            "M5_CORPUS_ID_MISMATCH", "Manifest and annotations use different corpus IDs."
        )
    if annotations.get("coordinateSystem") != "source-image-pixels-before-normalization":
        raise CorpusValidationError(
            "M5_CORPUS_INVALID_CONTRACT", "Annotations use an unsupported coordinate system."
        )
    provenance = _mapping(
        annotations.get("annotationProvenance"),
        "annotations.annotationProvenance",
    )
    if provenance.get("method") != "algorithm-assisted-visual-review":
        raise CorpusValidationError(
            "M5_CORPUS_INVALID_CONTRACT",
            "Annotations must declare the accepted visual-review method.",
        )

    corpus_root = _safe_relative_path(repository_root, manifest.get("rootPath"), "rootPath")
    image_values = _sequence(manifest.get("images"), "manifest.images")
    expected_count = _integer(manifest.get("imageCount"), "manifest.imageCount", minimum=1)
    if len(image_values) != expected_count:
        raise CorpusValidationError(
            "M5_CORPUS_IMAGE_COUNT_MISMATCH", "imageCount does not match manifest.images."
        )
    if (
        _integer(
            provenance.get("reviewedImageCount"),
            "annotationProvenance.reviewedImageCount",
            minimum=1,
        )
        != expected_count
    ):
        raise CorpusValidationError(
            "M5_CORPUS_ANNOTATION_REVIEW_COUNT_MISMATCH",
            "Annotation review count does not match the corpus.",
        )

    images_by_id: dict[str, Mapping[str, object]] = {}
    observed_paths: set[Path] = set()
    observed_checksums: set[str] = set()
    source_group_splits: dict[str, str] = {}
    total_size = 0
    previous_sequence_end: int | None = None
    for image_index, image_value in enumerate(image_values):
        image = _mapping(image_value, "manifest.image")
        image_id = _string(image.get("id"), "image.id")
        if image_id in images_by_id:
            raise CorpusValidationError(
                "M5_CORPUS_DUPLICATE_ID", f"Duplicate image ID: {image_id}."
            )
        image_path = _safe_relative_path(
            corpus_root, image.get("relativePath"), f"{image_id}.relativePath"
        )
        if image_path in observed_paths:
            raise CorpusValidationError(
                "M5_CORPUS_DUPLICATE_PATH", f"Duplicate image path: {image_path.name}."
            )
        if not image_path.is_file():
            raise CorpusValidationError(
                "M5_CORPUS_IMAGE_MISSING", f"Image is missing: {image_path}."
            )
        expected_sha256 = _string(image.get("sha256"), f"{image_id}.sha256")
        if SHA256_PATTERN.fullmatch(expected_sha256) is None:
            raise CorpusValidationError(
                "M5_CORPUS_INVALID_CHECKSUM", f"{image_id} has an invalid SHA-256."
            )
        if expected_sha256 in observed_checksums:
            raise CorpusValidationError(
                "M5_CORPUS_DUPLICATE_CONTENT", f"{image_id} duplicates another image."
            )
        try:
            actual_sha256 = sha256_file(image_path)
        except ImageFileError as error:
            raise CorpusValidationError(
                "M5_CORPUS_IMAGE_READ_FAILED", f"Cannot read image: {image_path}."
            ) from error
        if actual_sha256 != expected_sha256:
            raise CorpusValidationError(
                "M5_CORPUS_CHECKSUM_MISMATCH", f"{image_id} checksum does not match."
            )
        size = _integer(image.get("sizeBytes"), f"{image_id}.sizeBytes", minimum=1)
        if image_path.stat().st_size != size:
            raise CorpusValidationError(
                "M5_CORPUS_SIZE_MISMATCH", f"{image_id} size does not match."
            )
        try:
            width, height = read_jpeg_dimensions(image_path)
        except ImageFileError as error:
            raise CorpusValidationError(
                "M5_CORPUS_UNSUPPORTED_IMAGE",
                f"Cannot read JPEG dimensions: {image_path.name}.",
            ) from error
        if width != _integer(
            image.get("width"), f"{image_id}.width", minimum=1
        ) or height != _integer(image.get("height"), f"{image_id}.height", minimum=1):
            raise CorpusValidationError(
                "M5_CORPUS_DIMENSION_MISMATCH", f"{image_id} dimensions do not match."
            )
        source_group = _string(image.get("sourceGroup"), f"{image_id}.sourceGroup")
        split = _string(image.get("split"), f"{image_id}.split")
        previous_split = source_group_splits.setdefault(source_group, split)
        if previous_split != split:
            raise CorpusValidationError(
                "M5_CORPUS_SOURCE_LEAKAGE",
                f"Source group {source_group} occurs in multiple splits.",
            )
        start = _integer(
            image.get("expectedSequenceStart"), f"{image_id}.expectedSequenceStart", minimum=1
        )
        end = _integer(
            image.get("expectedSequenceEnd"), f"{image_id}.expectedSequenceEnd", minimum=1
        )
        board_count = _integer(
            image.get("expectedBoardCount"), f"{image_id}.expectedBoardCount", minimum=1
        )
        if board_count > 9 or end - start + 1 != board_count:
            raise CorpusValidationError(
                "M5_CORPUS_SEQUENCE_MISMATCH",
                f"{image_id} sequence range does not match expectedBoardCount.",
            )
        if board_count < 9 and image_index != len(image_values) - 1:
            raise CorpusValidationError(
                "M5_CORPUS_PARTIAL_PAGE_NOT_FINAL",
                f"{image_id} is partial but is not the final corpus page.",
            )
        if previous_sequence_end is not None and start != previous_sequence_end + 1:
            raise CorpusValidationError(
                "M5_CORPUS_SEQUENCE_MISMATCH",
                f"{image_id} does not continue the previous sequence range.",
            )
        previous_sequence_end = end
        images_by_id[image_id] = image
        observed_paths.add(image_path)
        observed_checksums.add(expected_sha256)
        total_size += size

    annotation_values = _sequence(annotations.get("images"), "annotations.images")
    annotations_by_id: dict[str, Mapping[str, object]] = {}
    pending: list[str] = []
    complete_count = 0
    for annotation_value in annotation_values:
        annotation = _mapping(annotation_value, "annotations.image")
        image_id = _string(annotation.get("imageId"), "annotation.imageId")
        if image_id in annotations_by_id:
            raise CorpusValidationError(
                "M5_CORPUS_DUPLICATE_ANNOTATION", f"Duplicate annotation: {image_id}."
            )
        matched_image = images_by_id.get(image_id)
        if matched_image is None:
            raise CorpusValidationError(
                "M5_CORPUS_UNKNOWN_IMAGE", f"Annotation references unknown image: {image_id}."
            )
        start = _integer(
            matched_image.get("expectedSequenceStart"),
            f"{image_id}.expectedSequenceStart",
            minimum=1,
        )
        end = _integer(
            matched_image.get("expectedSequenceEnd"),
            f"{image_id}.expectedSequenceEnd",
            minimum=1,
        )
        sequence_numbers = [
            _integer(value, f"{image_id}.sequenceNumbers", minimum=1)
            for value in _sequence(annotation.get("sequenceNumbers"), f"{image_id}.sequenceNumbers")
        ]
        if sequence_numbers != list(range(start, end + 1)):
            raise CorpusValidationError(
                "M5_CORPUS_SEQUENCE_MISMATCH",
                f"{image_id} annotations do not match the expected sequence.",
            )
        status = _string(annotation.get("status"), f"{image_id}.status")
        if status == "complete":
            _validate_complete_geometry(annotation, matched_image)
            complete_count += 1
        elif status == "sequence_only":
            pending.append(image_id)
        else:
            raise CorpusValidationError(
                "M5_CORPUS_INVALID_ANNOTATION_STATUS",
                f"{image_id} has unsupported annotation status {status}.",
            )
        annotations_by_id[image_id] = annotation
    if annotations_by_id.keys() != images_by_id.keys():
        missing = sorted(images_by_id.keys() - annotations_by_id.keys())
        raise CorpusValidationError(
            "M5_CORPUS_ANNOTATION_MISSING", f"Missing annotations: {', '.join(missing)}."
        )

    declared_source_groups = _integer(
        manifest.get("sourceGroupCount"), "manifest.sourceGroupCount", minimum=1
    )
    if declared_source_groups != len(source_group_splits):
        raise CorpusValidationError(
            "M5_CORPUS_SOURCE_GROUP_COUNT_MISMATCH",
            "sourceGroupCount does not match the manifest.",
        )
    warnings: list[str] = []
    if expected_count < 20:
        warnings.append("Corpus contains fewer than the original 20-image target.")
    if len(source_group_splits) == 1:
        warnings.append("Corpus contains only one source group.")
    if manifest.get("status") != "accepted":
        warnings.append("Corpus manifest is not accepted.")
    ready = not pending and manifest.get("status") == "accepted"
    return CorpusValidationReport(
        corpus_id=corpus_id,
        image_count=expected_count,
        complete_annotation_count=complete_count,
        pending_annotation_ids=tuple(sorted(pending)),
        source_group_count=len(source_group_splits),
        total_size_bytes=total_size,
        ready_for_geometry_benchmark=ready,
        warnings=tuple(warnings),
    )
