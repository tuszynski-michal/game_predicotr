"""Independent cell-grid golden review and historical cropper baseline."""

from __future__ import annotations

import hashlib
import json
import math
import threading
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

import numpy as np
from PIL import Image, UnidentifiedImageError

from .grid_quality import metric_summary, project_points, quad_to_canonical_matrix
from .rectification import (
    BOARD_COLUMNS,
    BOARD_HEIGHT,
    BOARD_ROWS,
    BOARD_WIDTH,
    CELL_HEIGHT,
    CELL_WIDTH,
    CROPPER_VERSION,
    MARGIN_X,
    MARGIN_Y,
)

GOLDEN_VERSION = "cell-grid-golden-v1"
SELECTION_VERSION = "cell-grid-stratified-v1"
BASELINE_VERSION = "cell-grid-v1-baseline-v1"
OBSERVATION_ID_VERSION = "cell-grid-observation-v1"
COORDINATE_SYSTEM = "rectified-board-pixels-500x300"
SOURCE_COORDINATE_SYSTEM = "source-image-pixels"
GEOMETRY_VERSION = "source-quad-perspective-grid-v1"
SUGGESTION_VERSION = "detected-source-quad-v1"
REVIEW_BOARD_COUNT = 27
REVIEW_PER_POSITION = 3
MIN_QUAD_EDGE = 20.0
MIN_QUAD_AREA = 1_000.0
SUGGESTED_VERTICAL_LINES = (100, 200, 300, 400)
SUGGESTED_HORIZONTAL_LINES = (100, 200)
V1_VERTICAL_LINES = tuple(MARGIN_X + index * CELL_WIDTH for index in range(1, BOARD_COLUMNS))
V1_HORIZONTAL_LINES = tuple(MARGIN_Y + index * CELL_HEIGHT for index in range(1, BOARD_ROWS))
_SHA256_CHARS = frozenset("0123456789abcdef")

ReviewStatus = Literal["pending", "accepted"]
LineSource = Literal[
    "detected-quad-suggestion",
    "human-draft",
    "human-confirmed-detected-quad",
    "human-adjusted",
]
Point = tuple[float, float]
Quad = tuple[Point, Point, Point, Point]


class CellGridGoldenError(ValueError):
    """Stable failure for the independent cell-grid review workflow."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _quad_dict(quad: Quad) -> list[dict[str, float]]:
    return [{"x": point[0], "y": point[1]} for point in quad]


@dataclass(frozen=True, slots=True)
class BoardCandidate:
    observation_id: str
    image_id: str
    source_image_checksum_sha256: str
    source_image_relative_path: str
    source_image_width: int
    source_image_height: int
    source_group: str
    condition_tags: tuple[str, ...]
    sequence_number: int
    board_position: int
    board_relative_path: str
    board_checksum_sha256: str
    detected_source_quad: Quad

    def immutable_dict(self, selection_index: int) -> dict[str, object]:
        return {
            "boardChecksumSha256": self.board_checksum_sha256,
            "boardHeight": BOARD_HEIGHT,
            "boardPosition": self.board_position,
            "boardRelativePath": self.board_relative_path,
            "boardWidth": BOARD_WIDTH,
            "conditionTags": list(self.condition_tags),
            "imageId": self.image_id,
            "observationId": self.observation_id,
            "selectionIndex": selection_index,
            "sequenceNumber": self.sequence_number,
            "sourceGroup": self.source_group,
            "sourceImageChecksumSha256": self.source_image_checksum_sha256,
            "sourceImageHeight": self.source_image_height,
            "sourceImageRelativePath": self.source_image_relative_path,
            "sourceImageWidth": self.source_image_width,
            "detectedSourceQuad": _quad_dict(self.detected_source_quad),
        }


@dataclass(frozen=True, slots=True)
class GridReviewEntry:
    selection_index: int
    candidate: BoardCandidate
    source_quad: Quad
    v1_cut_cell_indexes: tuple[int, ...]
    v1_impact_reviewed: bool
    review_status: ReviewStatus
    reviewed_by: str | None
    decision_revision: int
    line_source: LineSource

    def to_dict(self) -> dict[str, object]:
        value = self.candidate.immutable_dict(self.selection_index)
        value.update(
            {
                "decisionRevision": self.decision_revision,
                "lineSource": self.line_source,
                "reviewStatus": self.review_status,
                "reviewedBy": self.reviewed_by,
                "suggestionVersion": SUGGESTION_VERSION,
                "sourceQuad": _quad_dict(self.source_quad),
                "v1CutCellIndexes": list(self.v1_cut_cell_indexes),
                "v1ImpactReviewed": self.v1_impact_reviewed,
            }
        )
        return value


@dataclass(frozen=True, slots=True)
class CellGridGolden:
    corpus_id: str
    corpus_manifest_sha256: str
    golden_annotations_sha256: str
    crop_report_sha256: str
    source_groups: tuple[str, ...]
    review_revision: int
    entries: tuple[GridReviewEntry, ...]

    def to_dict(self) -> dict[str, object]:
        accepted_count = sum(entry.review_status == "accepted" for entry in self.entries)
        position_counts = Counter(entry.candidate.board_position for entry in self.entries)
        source_group_counts = Counter(entry.candidate.source_group for entry in self.entries)
        return {
            "canonicalBoard": {
                "coordinateSystem": COORDINATE_SYSTEM,
                "height": BOARD_HEIGHT,
                "horizontalLines": list(SUGGESTED_HORIZONTAL_LINES),
                "verticalLines": list(SUGGESTED_VERTICAL_LINES),
                "width": BOARD_WIDTH,
            },
            "coordinateSystem": SOURCE_COORDINATE_SYSTEM,
            "corpusId": self.corpus_id,
            "corpusManifestSha256": self.corpus_manifest_sha256,
            "cropReportSha256": self.crop_report_sha256,
            "entries": [entry.to_dict() for entry in self.entries],
            "goldenAnnotationsSha256": self.golden_annotations_sha256,
            "goldenVersion": GOLDEN_VERSION,
            "geometryVersion": GEOMETRY_VERSION,
            "reviewRevision": self.review_revision,
            "schemaVersion": 1,
            "selection": {
                "boardCount": len(self.entries),
                "boardsPerPosition": REVIEW_PER_POSITION,
                "positionCounts": [
                    {
                        "boardCount": position_counts[position],
                        "boardPosition": position,
                    }
                    for position in range(9)
                ],
                "selectionVersion": SELECTION_VERSION,
                "sourceGroupCounts": [
                    {
                        "boardCount": source_group_counts[source_group],
                        "sourceGroup": source_group,
                    }
                    for source_group in self.source_groups
                ],
                "sourceGroups": list(self.source_groups),
            },
            "status": ("accepted" if accepted_count == len(self.entries) else "pending_review"),
            "summary": {
                "acceptedCount": accepted_count,
                "pendingCount": len(self.entries) - accepted_count,
                "totalCount": len(self.entries),
            },
        }

    def to_json_bytes(self) -> bytes:
        return _json_bytes(self.to_dict())


@dataclass(frozen=True, slots=True)
class _SourceBundle:
    corpus_id: str
    corpus_manifest_sha256: str
    golden_annotations_sha256: str
    crop_report_sha256: str
    source_groups: tuple[str, ...]
    candidates: tuple[BoardCandidate, ...]


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CellGridGoldenError(
            "CELL_GRID_CONTRACT_INVALID",
            f"{label} must be an object.",
        )
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise CellGridGoldenError(
            "CELL_GRID_CONTRACT_INVALID",
            f"{label} must be an array.",
        )
    return cast(Sequence[object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CellGridGoldenError(
            "CELL_GRID_CONTRACT_INVALID",
            f"{label} must be a non-empty string.",
        )
    return value


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise CellGridGoldenError(
            "CELL_GRID_CONTRACT_INVALID",
            f"{label} must be an integer greater than or equal to {minimum}.",
        )
    return value


def _number(value: object, label: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(value):
        raise CellGridGoldenError(
            "CELL_GRID_CONTRACT_INVALID",
            f"{label} must be a finite number.",
        )
    return round(float(value), 4)


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise CellGridGoldenError(
            "CELL_GRID_CONTRACT_INVALID",
            f"{label} must be a boolean.",
        )
    return value


def _source_quad(
    value: object,
    label: str,
    *,
    image_width: int,
    image_height: int,
) -> Quad:
    values = _sequence(value, label)
    if len(values) != 4:
        raise CellGridGoldenError(
            "CELL_GRID_QUAD_INVALID",
            f"{label} must contain top-left, top-right, bottom-right and bottom-left.",
        )
    points: list[Point] = []
    for index, raw_point in enumerate(values):
        point = _mapping(raw_point, f"{label}[{index}]")
        x = _number(point.get("x"), f"{label}[{index}].x")
        y = _number(point.get("y"), f"{label}[{index}].y")
        if not 0 <= x <= image_width - 1 or not 0 <= y <= image_height - 1:
            raise CellGridGoldenError(
                "CELL_GRID_QUAD_INVALID",
                f"{label}[{index}] is outside the source image.",
            )
        points.append((x, y))
    quad = cast(Quad, tuple(points))
    edges = [
        math.hypot(
            quad[(index + 1) % 4][0] - quad[index][0],
            quad[(index + 1) % 4][1] - quad[index][1],
        )
        for index in range(4)
    ]
    crosses = []
    for index in range(4):
        first = quad[index]
        second = quad[(index + 1) % 4]
        third = quad[(index + 2) % 4]
        crosses.append(
            (second[0] - first[0]) * (third[1] - second[1])
            - (second[1] - first[1]) * (third[0] - second[0])
        )
    area = abs(
        sum(
            quad[index][0] * quad[(index + 1) % 4][1] - quad[(index + 1) % 4][0] * quad[index][1]
            for index in range(4)
        )
        / 2
    )
    left_center = (quad[0][0] + quad[3][0]) / 2
    right_center = (quad[1][0] + quad[2][0]) / 2
    top_center = (quad[0][1] + quad[1][1]) / 2
    bottom_center = (quad[2][1] + quad[3][1]) / 2
    if (
        min(edges) < MIN_QUAD_EDGE
        or area < MIN_QUAD_AREA
        or not all(cross > 0 for cross in crosses)
        or left_center >= right_center
        or top_center >= bottom_center
    ):
        raise CellGridGoldenError(
            "CELL_GRID_QUAD_INVALID",
            f"{label} must be an ordered convex board quad with sufficient area.",
        )
    return quad


def _sha256(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(character not in _SHA256_CHARS for character in text):
        raise CellGridGoldenError(
            "CELL_GRID_CONTRACT_INVALID",
            f"{label} must be a lowercase SHA-256.",
        )
    return text


def _load_json(path: Path, label: str) -> tuple[bytes, Mapping[str, object]]:
    try:
        content = path.read_bytes()
        value: Any = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise CellGridGoldenError(
            "CELL_GRID_JSON_INVALID",
            f"{label} cannot be read.",
        ) from error
    return content, _mapping(value, label)


def _safe_relative_path(
    root: Path,
    value: object,
    label: str,
    *,
    must_exist: bool = True,
) -> tuple[str, Path]:
    text = _text(value, label)
    relative = PurePosixPath(text)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise CellGridGoldenError(
            "CELL_GRID_PATH_UNSAFE",
            f"{label} must be a safe relative POSIX path.",
        )
    base = root.resolve(strict=True)
    candidate = base / Path(*relative.parts)
    try:
        resolved = candidate.resolve(strict=must_exist)
    except OSError as error:
        raise CellGridGoldenError(
            "CELL_GRID_ARTIFACT_MISSING",
            f"{label} cannot be resolved.",
        ) from error
    if not resolved.is_relative_to(base):
        raise CellGridGoldenError(
            "CELL_GRID_PATH_UNSAFE",
            f"{label} escapes its root.",
        )
    return text, resolved


def _verify_checksum(path: Path, expected: str, label: str) -> None:
    try:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise CellGridGoldenError(
            "CELL_GRID_ARTIFACT_UNREADABLE",
            f"{label} cannot be read.",
        ) from error
    if actual != expected:
        raise CellGridGoldenError(
            "CELL_GRID_ARTIFACT_DRIFT",
            f"{label} checksum differs from its source contract.",
        )


def _verify_source_image(
    path: Path,
    expected_checksum: str,
    expected_width: int,
    expected_height: int,
    label: str,
) -> None:
    _verify_checksum(path, expected_checksum, label)
    try:
        with Image.open(path) as image:
            image.load()
            size = image.size
    except (OSError, UnidentifiedImageError) as error:
        raise CellGridGoldenError(
            "CELL_GRID_SOURCE_IMAGE_UNREADABLE",
            f"{label} is not a readable image.",
        ) from error
    if size != (expected_width, expected_height):
        raise CellGridGoldenError(
            "CELL_GRID_SOURCE_IMAGE_INVALID",
            f"{label} dimensions differ from the corpus manifest.",
        )


def _verify_board(path: Path, expected_checksum: str, label: str) -> None:
    _verify_checksum(path, expected_checksum, label)
    try:
        with Image.open(path) as image:
            image.load()
            valid = image.mode == "RGB" and image.size == (BOARD_WIDTH, BOARD_HEIGHT)
    except (OSError, UnidentifiedImageError) as error:
        raise CellGridGoldenError(
            "CELL_GRID_BOARD_UNREADABLE",
            f"{label} is not a readable board image.",
        ) from error
    if not valid:
        raise CellGridGoldenError(
            "CELL_GRID_BOARD_INVALID",
            f"{label} must be RGB {BOARD_WIDTH}x{BOARD_HEIGHT}.",
        )


def _observation_id(
    *,
    corpus_id: str,
    source_checksum: str,
    sequence_number: int,
    board_position: int,
) -> str:
    logical = "\0".join(
        (
            OBSERVATION_ID_VERSION,
            corpus_id,
            source_checksum,
            str(sequence_number),
            str(board_position),
        )
    )
    return hashlib.sha256(logical.encode()).hexdigest()


def _load_source_bundle(
    repository_root: Path,
    manifest_path: Path,
    annotations_path: Path,
    crop_report_path: Path,
    crop_root: Path,
) -> _SourceBundle:
    manifest_bytes, manifest = _load_json(manifest_path, "corpusManifest")
    annotations_bytes, annotations = _load_json(
        annotations_path,
        "goldenAnnotations",
    )
    crop_report_bytes, crop_report = _load_json(crop_report_path, "cropReport")
    corpus_id = _text(manifest.get("corpusId"), "corpusManifest.corpusId")
    if annotations.get("corpusId") != corpus_id:
        raise CellGridGoldenError(
            "CELL_GRID_SOURCE_DRIFT",
            "Golden annotations use another corpus.",
        )
    if annotations.get("coordinateSystem") != "source-image-pixels-before-normalization":
        raise CellGridGoldenError(
            "CELL_GRID_SOURCE_DRIFT",
            "Golden annotations use an unsupported coordinate system.",
        )
    if crop_report.get("cropperVersion") != CROPPER_VERSION:
        raise CellGridGoldenError(
            "CELL_GRID_CROP_REPORT_UNSUPPORTED",
            "Historical board-cell-crops-v1 report is required.",
        )
    if crop_report.get("status") != "cropped":
        raise CellGridGoldenError(
            "CELL_GRID_CROP_REPORT_INCOMPLETE",
            "Crop report must contain complete rectified boards.",
        )

    try:
        repository_base = repository_root.resolve(strict=True)
        crop_base = crop_root.resolve(strict=True)
    except OSError as error:
        raise CellGridGoldenError(
            "CELL_GRID_ROOT_MISSING",
            "Repository or board artifact root does not exist.",
        ) from error
    if not repository_base.is_dir() or not crop_base.is_dir():
        raise CellGridGoldenError(
            "CELL_GRID_ROOT_INVALID",
            "Repository and board artifact roots must be directories.",
        )
    _, source_root = _safe_relative_path(
        repository_base,
        manifest.get("rootPath"),
        "corpusManifest.rootPath",
    )
    if not source_root.is_dir():
        raise CellGridGoldenError(
            "CELL_GRID_SOURCE_ROOT_INVALID",
            "Corpus source root must be a directory.",
        )

    annotations_by_id: dict[str, Mapping[str, object]] = {}
    for index, value in enumerate(_sequence(annotations.get("images"), "goldenAnnotations.images")):
        item = _mapping(value, f"goldenAnnotations.images[{index}]")
        image_id = _text(item.get("imageId"), f"goldenAnnotations.images[{index}].imageId")
        if image_id in annotations_by_id:
            raise CellGridGoldenError(
                "CELL_GRID_SOURCE_DRIFT",
                "Golden annotations contain a duplicate image ID.",
            )
        if item.get("status") != "complete":
            raise CellGridGoldenError(
                "CELL_GRID_SOURCE_INCOMPLETE",
                "Cell-grid selection requires complete board annotations.",
            )
        annotations_by_id[image_id] = item

    crops_by_source: dict[str, Mapping[str, object]] = {}
    for index, value in enumerate(_sequence(crop_report.get("images"), "cropReport.images")):
        item = _mapping(value, f"cropReport.images[{index}]")
        checksum = _sha256(
            item.get("sourceChecksumSha256"),
            f"cropReport.images[{index}].sourceChecksumSha256",
        )
        if checksum in crops_by_source:
            raise CellGridGoldenError(
                "CELL_GRID_SOURCE_DRIFT",
                "Crop report contains a duplicate source image.",
            )
        if item.get("status") != "cropped":
            raise CellGridGoldenError(
                "CELL_GRID_CROP_REPORT_INCOMPLETE",
                "Every selected source must contain rectified boards.",
            )
        crops_by_source[checksum] = item

    candidates: list[BoardCandidate] = []
    source_groups: set[str] = set()
    seen_observations: set[str] = set()
    manifest_images = _sequence(manifest.get("images"), "corpusManifest.images")
    if _integer(manifest.get("imageCount"), "corpusManifest.imageCount", minimum=1) != len(
        manifest_images
    ):
        raise CellGridGoldenError(
            "CELL_GRID_SOURCE_DRIFT",
            "Corpus imageCount differs from its images array.",
        )
    for image_index, value in enumerate(manifest_images):
        image = _mapping(value, f"corpusManifest.images[{image_index}]")
        image_id = _text(image.get("id"), f"corpusManifest.images[{image_index}].id")
        source_checksum = _sha256(
            image.get("sha256"),
            f"corpusManifest.images[{image_index}].sha256",
        )
        source_width = _integer(
            image.get("width"),
            f"corpusManifest.images[{image_index}].width",
            minimum=1,
        )
        source_height = _integer(
            image.get("height"),
            f"corpusManifest.images[{image_index}].height",
            minimum=1,
        )
        source_relative, source_path = _safe_relative_path(
            source_root,
            image.get("relativePath"),
            f"corpusManifest.images[{image_index}].relativePath",
        )
        _verify_source_image(
            source_path,
            source_checksum,
            source_width,
            source_height,
            f"source image {image_id}",
        )
        source_group = _text(
            image.get("sourceGroup"),
            f"corpusManifest.images[{image_index}].sourceGroup",
        )
        source_groups.add(source_group)
        condition_tags = tuple(
            sorted(
                _text(tag, f"corpusManifest.images[{image_index}].conditionTags")
                for tag in _sequence(
                    image.get("conditionTags"),
                    f"corpusManifest.images[{image_index}].conditionTags",
                )
            )
        )
        annotation = annotations_by_id.get(image_id)
        crop_image = crops_by_source.get(source_checksum)
        if annotation is None or crop_image is None:
            raise CellGridGoldenError(
                "CELL_GRID_SOURCE_DRIFT",
                f"Source chain is incomplete for {image_id}.",
            )
        boards_by_position: dict[int, Mapping[str, object]] = {}
        for board_index, board_value in enumerate(
            _sequence(crop_image.get("boards"), f"cropReport.{image_id}.boards")
        ):
            board = _mapping(board_value, f"cropReport.{image_id}.boards[{board_index}]")
            position = _integer(
                board.get("positionIndex"),
                f"cropReport.{image_id}.boards[{board_index}].positionIndex",
            )
            if position in boards_by_position:
                raise CellGridGoldenError(
                    "CELL_GRID_SOURCE_DRIFT",
                    f"Crop report duplicates board position {position} for {image_id}.",
                )
            boards_by_position[position] = board
        annotation_boards = _sequence(
            annotation.get("boards"),
            f"goldenAnnotations.{image_id}.boards",
        )
        for annotation_index, annotation_board_value in enumerate(annotation_boards):
            annotation_board = _mapping(
                annotation_board_value,
                f"goldenAnnotations.{image_id}.boards[{annotation_index}]",
            )
            position = _integer(
                annotation_board.get("positionIndex"),
                f"goldenAnnotations.{image_id}.boards[{annotation_index}].positionIndex",
            )
            if position > 8:
                raise CellGridGoldenError(
                    "CELL_GRID_SOURCE_DRIFT",
                    f"Board position {position} is outside the supported 3x3 page.",
                )
            rectified_board = boards_by_position.get(position)
            if rectified_board is None:
                raise CellGridGoldenError(
                    "CELL_GRID_SOURCE_DRIFT",
                    f"Rectified board {position} is missing for {image_id}.",
                )
            sequence_number = _integer(
                annotation_board.get("sequenceNumber"),
                f"goldenAnnotations.{image_id}.boards[{annotation_index}].sequenceNumber",
                minimum=1,
            )
            board_relative, board_path = _safe_relative_path(
                crop_base,
                rectified_board.get("boardRelativePath"),
                f"cropReport.{image_id}.boards[{position}].boardRelativePath",
            )
            board_checksum = _sha256(
                rectified_board.get("boardChecksumSha256"),
                f"cropReport.{image_id}.boards[{position}].boardChecksumSha256",
            )
            detected_source_quad = _source_quad(
                rectified_board.get("sourceQuad"),
                f"cropReport.{image_id}.boards[{position}].sourceQuad",
                image_width=source_width,
                image_height=source_height,
            )
            _verify_board(board_path, board_checksum, f"rectified board {image_id}/{position}")
            observation_id = _observation_id(
                corpus_id=corpus_id,
                source_checksum=source_checksum,
                sequence_number=sequence_number,
                board_position=position,
            )
            if observation_id in seen_observations:
                raise CellGridGoldenError(
                    "CELL_GRID_SOURCE_DRIFT",
                    "Stable board observation is duplicated.",
                )
            seen_observations.add(observation_id)
            candidates.append(
                BoardCandidate(
                    observation_id=observation_id,
                    image_id=image_id,
                    source_image_checksum_sha256=source_checksum,
                    source_image_relative_path=source_relative,
                    source_image_width=source_width,
                    source_image_height=source_height,
                    source_group=source_group,
                    condition_tags=condition_tags,
                    sequence_number=sequence_number,
                    board_position=position,
                    board_relative_path=board_relative,
                    board_checksum_sha256=board_checksum,
                    detected_source_quad=detected_source_quad,
                )
            )

    if len(candidates) != _integer(
        crop_report.get("boardCount"),
        "cropReport.boardCount",
        minimum=1,
    ):
        raise CellGridGoldenError(
            "CELL_GRID_SOURCE_DRIFT",
            "Candidate count differs from crop report boardCount.",
        )
    if len(source_groups) < 2:
        raise CellGridGoldenError(
            "CELL_GRID_SOURCE_GROUPS_INSUFFICIENT",
            "At least two source groups are required for the independent golden.",
        )
    return _SourceBundle(
        corpus_id=corpus_id,
        corpus_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        golden_annotations_sha256=hashlib.sha256(annotations_bytes).hexdigest(),
        crop_report_sha256=hashlib.sha256(crop_report_bytes).hexdigest(),
        source_groups=tuple(sorted(source_groups)),
        candidates=tuple(candidates),
    )


def _selection_rank(
    candidate: BoardCandidate,
    *,
    used_image_ids: set[str],
    covered_tags: set[str],
) -> tuple[int, int, str]:
    fingerprint = hashlib.sha256(
        f"{SELECTION_VERSION}\0{candidate.observation_id}".encode()
    ).hexdigest()
    return (
        int(candidate.image_id in used_image_ids),
        -len(set(candidate.condition_tags) - covered_tags),
        fingerprint,
    )


def _select_candidates(bundle: _SourceBundle) -> tuple[BoardCandidate, ...]:
    if len(bundle.source_groups) > REVIEW_PER_POSITION:
        raise CellGridGoldenError(
            "CELL_GRID_SOURCE_GROUPS_UNSUPPORTED",
            "The review sample cannot cover more source groups than boards per position.",
        )
    selected: list[BoardCandidate] = []
    selected_ids: set[str] = set()
    used_image_ids: set[str] = set()
    covered_tags: set[str] = set()
    for position in range(9):
        position_candidates = [
            candidate for candidate in bundle.candidates if candidate.board_position == position
        ]
        position_selected: list[BoardCandidate] = []
        for source_group in bundle.source_groups:
            pool = [
                candidate
                for candidate in position_candidates
                if candidate.source_group == source_group
                and candidate.observation_id not in selected_ids
            ]
            if not pool:
                raise CellGridGoldenError(
                    "CELL_GRID_POSITION_COVERAGE_INSUFFICIENT",
                    f"Board position {position} has no candidate for {source_group}.",
                )
            choice = min(
                pool,
                key=lambda candidate: _selection_rank(
                    candidate,
                    used_image_ids=used_image_ids,
                    covered_tags=covered_tags,
                ),
            )
            position_selected.append(choice)
            selected_ids.add(choice.observation_id)
            used_image_ids.add(choice.image_id)
            covered_tags.update(choice.condition_tags)
        while len(position_selected) < REVIEW_PER_POSITION:
            pool = [
                candidate
                for candidate in position_candidates
                if candidate.observation_id not in selected_ids
            ]
            if not pool:
                raise CellGridGoldenError(
                    "CELL_GRID_POSITION_COVERAGE_INSUFFICIENT",
                    f"Board position {position} has fewer than {REVIEW_PER_POSITION} candidates.",
                )
            choice = min(
                pool,
                key=lambda candidate: _selection_rank(
                    candidate,
                    used_image_ids=used_image_ids,
                    covered_tags=covered_tags,
                ),
            )
            position_selected.append(choice)
            selected_ids.add(choice.observation_id)
            used_image_ids.add(choice.image_id)
            covered_tags.update(choice.condition_tags)
        selected.extend(position_selected)
    selected.sort(
        key=lambda candidate: (
            candidate.sequence_number,
            candidate.board_position,
            candidate.observation_id,
        )
    )
    if len(selected) != REVIEW_BOARD_COUNT:
        raise CellGridGoldenError(
            "CELL_GRID_SELECTION_COUNT_INVALID",
            f"Selection must contain exactly {REVIEW_BOARD_COUNT} boards.",
        )
    return tuple(selected)


def _initial_golden(bundle: _SourceBundle) -> CellGridGolden:
    selected = _select_candidates(bundle)
    all_cells = tuple(range(BOARD_ROWS * BOARD_COLUMNS))
    entries = tuple(
        GridReviewEntry(
            selection_index=index,
            candidate=candidate,
            source_quad=candidate.detected_source_quad,
            v1_cut_cell_indexes=all_cells,
            v1_impact_reviewed=False,
            review_status="pending",
            reviewed_by=None,
            decision_revision=0,
            line_source="detected-quad-suggestion",
        )
        for index, candidate in enumerate(selected)
    )
    return CellGridGolden(
        corpus_id=bundle.corpus_id,
        corpus_manifest_sha256=bundle.corpus_manifest_sha256,
        golden_annotations_sha256=bundle.golden_annotations_sha256,
        crop_report_sha256=bundle.crop_report_sha256,
        source_groups=bundle.source_groups,
        review_revision=0,
        entries=entries,
    )


def _cut_cells(value: object, label: str) -> tuple[int, ...]:
    cells = tuple(
        _integer(item, f"{label}[{index}]") for index, item in enumerate(_sequence(value, label))
    )
    if tuple(sorted(set(cells))) != cells or any(
        cell >= BOARD_ROWS * BOARD_COLUMNS for cell in cells
    ):
        raise CellGridGoldenError(
            "CELL_GRID_V1_IMPACT_INVALID",
            f"{label} must be unique sorted cell indexes from 0 to 14.",
        )
    return cells


def _parse_existing_golden(
    value: Mapping[str, object],
    bundle: _SourceBundle,
) -> CellGridGolden:
    expected_selected = _select_candidates(bundle)
    expected_fingerprints = {
        "corpusId": bundle.corpus_id,
        "corpusManifestSha256": bundle.corpus_manifest_sha256,
        "cropReportSha256": bundle.crop_report_sha256,
        "goldenAnnotationsSha256": bundle.golden_annotations_sha256,
    }
    if (
        value.get("schemaVersion") != 1
        or value.get("goldenVersion") != GOLDEN_VERSION
        or value.get("geometryVersion") != GEOMETRY_VERSION
        or value.get("coordinateSystem") != SOURCE_COORDINATE_SYSTEM
        or value.get("canonicalBoard") != _initial_golden(bundle).to_dict()["canonicalBoard"]
    ):
        raise CellGridGoldenError(
            "CELL_GRID_GOLDEN_UNSUPPORTED",
            "Existing golden uses an unsupported contract.",
        )
    for field, expected_fingerprint in expected_fingerprints.items():
        if value.get(field) != expected_fingerprint:
            raise CellGridGoldenError(
                "CELL_GRID_SOURCE_DRIFT",
                f"Existing golden {field} differs from current source inputs.",
            )
    selection = _mapping(value.get("selection"), "golden.selection")
    expected_selection = _mapping(
        _initial_golden(bundle).to_dict()["selection"],
        "generated.selection",
    )
    if selection != expected_selection:
        raise CellGridGoldenError(
            "CELL_GRID_SELECTION_DRIFT",
            "Existing golden selection metadata differs from current policy.",
        )
    raw_entries = _sequence(value.get("entries"), "golden.entries")
    if len(raw_entries) != len(expected_selected):
        raise CellGridGoldenError(
            "CELL_GRID_SELECTION_DRIFT",
            "Existing golden entry count differs from deterministic selection.",
        )
    entries: list[GridReviewEntry] = []
    for index, (raw, expected_candidate) in enumerate(
        zip(raw_entries, expected_selected, strict=True)
    ):
        item = _mapping(raw, f"golden.entries[{index}]")
        immutable = expected_candidate.immutable_dict(index)
        if any(item.get(key) != expected_value for key, expected_value in immutable.items()):
            raise CellGridGoldenError(
                "CELL_GRID_SELECTION_DRIFT",
                f"Existing golden entry {index} differs from deterministic selection.",
            )
        if item.get("suggestionVersion") != SUGGESTION_VERSION:
            raise CellGridGoldenError(
                "CELL_GRID_GOLDEN_UNSUPPORTED",
                "Existing golden uses an unsupported suggestion version.",
            )
        review_status = item.get("reviewStatus")
        if review_status not in {"pending", "accepted"}:
            raise CellGridGoldenError(
                "CELL_GRID_REVIEW_STATUS_INVALID",
                f"golden.entries[{index}].reviewStatus is invalid.",
            )
        line_source = item.get("lineSource")
        if line_source not in {
            "detected-quad-suggestion",
            "human-draft",
            "human-confirmed-detected-quad",
            "human-adjusted",
        }:
            raise CellGridGoldenError(
                "CELL_GRID_LINE_SOURCE_INVALID",
                f"golden.entries[{index}].lineSource is invalid.",
            )
        reviewed_by = _optional_text(
            item.get("reviewedBy"),
            f"golden.entries[{index}].reviewedBy",
        )
        impact_reviewed = _boolean(
            item.get("v1ImpactReviewed"),
            f"golden.entries[{index}].v1ImpactReviewed",
        )
        if review_status == "accepted" and (reviewed_by is None or not impact_reviewed):
            raise CellGridGoldenError(
                "CELL_GRID_ACCEPTANCE_INVALID",
                "Accepted entries require reviewer identity and reviewed v1 impact.",
            )
        if review_status == "pending" and reviewed_by is not None:
            raise CellGridGoldenError(
                "CELL_GRID_ACCEPTANCE_INVALID",
                "Pending entries cannot carry an accepted reviewer identity.",
            )
        entries.append(
            GridReviewEntry(
                selection_index=index,
                candidate=expected_candidate,
                source_quad=_source_quad(
                    item.get("sourceQuad"),
                    f"golden.entries[{index}].sourceQuad",
                    image_width=expected_candidate.source_image_width,
                    image_height=expected_candidate.source_image_height,
                ),
                v1_cut_cell_indexes=_cut_cells(
                    item.get("v1CutCellIndexes"),
                    f"golden.entries[{index}].v1CutCellIndexes",
                ),
                v1_impact_reviewed=impact_reviewed,
                review_status=cast(ReviewStatus, review_status),
                reviewed_by=reviewed_by,
                decision_revision=_integer(
                    item.get("decisionRevision"),
                    f"golden.entries[{index}].decisionRevision",
                ),
                line_source=cast(LineSource, line_source),
            )
        )
    golden = CellGridGolden(
        corpus_id=bundle.corpus_id,
        corpus_manifest_sha256=bundle.corpus_manifest_sha256,
        golden_annotations_sha256=bundle.golden_annotations_sha256,
        crop_report_sha256=bundle.crop_report_sha256,
        source_groups=bundle.source_groups,
        review_revision=_integer(value.get("reviewRevision"), "golden.reviewRevision"),
        entries=tuple(entries),
    )
    declared_summary = _mapping(value.get("summary"), "golden.summary")
    actual_summary = _mapping(golden.to_dict()["summary"], "generated.summary")
    if declared_summary != actual_summary or value.get("status") != golden.to_dict()["status"]:
        raise CellGridGoldenError(
            "CELL_GRID_GOLDEN_SUMMARY_DRIFT",
            "Existing golden summary differs from its entries.",
        )
    return golden


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    except OSError as error:
        raise CellGridGoldenError(
            "CELL_GRID_WRITE_FAILED",
            f"Cannot atomically write {path.name}.",
        ) from error
    finally:
        if temporary.exists():
            temporary.unlink()


def _reviewer(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 100:
        raise CellGridGoldenError(
            "CELL_GRID_REVIEWER_INVALID",
            "Reviewer must contain 1-100 characters.",
        )
    return normalized


def _is_pristine_legacy_axis_golden(
    value: Mapping[str, object],
    bundle: _SourceBundle,
) -> bool:
    if (
        value.get("schemaVersion") != 1
        or value.get("goldenVersion") != GOLDEN_VERSION
        or value.get("coordinateSystem") != COORDINATE_SYSTEM
        or value.get("geometryVersion") is not None
        or value.get("reviewRevision") != 0
        or value.get("corpusId") != bundle.corpus_id
        or value.get("corpusManifestSha256") != bundle.corpus_manifest_sha256
        or value.get("goldenAnnotationsSha256") != bundle.golden_annotations_sha256
        or value.get("cropReportSha256") != bundle.crop_report_sha256
    ):
        return False
    raw_entries = value.get("entries")
    if not isinstance(raw_entries, list) or len(raw_entries) != REVIEW_BOARD_COUNT:
        return False
    for item in raw_entries:
        if (
            not isinstance(item, dict)
            or item.get("reviewStatus") != "pending"
            or item.get("reviewedBy") is not None
            or item.get("decisionRevision") != 0
            or item.get("lineSource") != "equal-grid-suggestion"
            or item.get("verticalLines") != list(SUGGESTED_VERTICAL_LINES)
            or item.get("horizontalLines") != list(SUGGESTED_HORIZONTAL_LINES)
            or item.get("v1ImpactReviewed") is not False
        ):
            return False
    return True


class CellGridGoldenReview:
    """Thread-safe review state with deterministic source revalidation."""

    def __init__(
        self,
        *,
        repository_root: Path,
        manifest_path: Path,
        annotations_path: Path,
        crop_report_path: Path,
        crop_root: Path,
        output_path: Path,
    ) -> None:
        self.repository_root = repository_root.resolve(strict=True)
        self.manifest_path = manifest_path.resolve(strict=True)
        self.annotations_path = annotations_path.resolve(strict=True)
        self.crop_report_path = crop_report_path.resolve(strict=True)
        self.crop_root = crop_root.resolve(strict=True)
        self.output_path = output_path.resolve()
        _, manifest = _load_json(self.manifest_path, "corpusManifest")
        _, self.source_root = _safe_relative_path(
            self.repository_root,
            manifest.get("rootPath"),
            "corpusManifest.rootPath",
        )
        if self.output_path == self.crop_root or self.output_path.is_relative_to(self.crop_root):
            raise CellGridGoldenError(
                "CELL_GRID_OUTPUT_IN_CROP_ROOT",
                "Golden review data must be outside immutable board artifacts.",
            )
        self._lock = threading.RLock()
        bundle = _load_source_bundle(
            self.repository_root,
            self.manifest_path,
            self.annotations_path,
            self.crop_report_path,
            self.crop_root,
        )
        if self.output_path.exists():
            _, existing = _load_json(self.output_path, "cellGridGolden")
            if _is_pristine_legacy_axis_golden(existing, bundle):
                self._golden = _initial_golden(bundle)
                self._save()
            else:
                self._golden = _parse_existing_golden(existing, bundle)
        else:
            self._golden = _initial_golden(bundle)
            self._save()

    @property
    def golden(self) -> CellGridGolden:
        return self._golden

    def state(
        self,
        *,
        offset: int = 0,
        limit: int = 1,
        status: Literal["all", "pending", "accepted"] = "pending",
    ) -> dict[str, object]:
        if offset < 0 or not 1 <= limit <= 100:
            raise CellGridGoldenError(
                "CELL_GRID_PAGE_INVALID",
                "offset must be non-negative and limit must be between 1 and 100.",
            )
        if status not in {"all", "pending", "accepted"}:
            raise CellGridGoldenError(
                "CELL_GRID_FILTER_INVALID",
                "Unknown review status.",
            )
        with self._lock:
            filtered = [
                entry
                for entry in self._golden.entries
                if status == "all" or entry.review_status == status
            ]
            page = filtered[offset : offset + limit]
            return {
                "filter": status,
                "grid": {
                    "boardHeight": BOARD_HEIGHT,
                    "boardWidth": BOARD_WIDTH,
                    "columns": BOARD_COLUMNS,
                    "horizontalSuggestions": list(SUGGESTED_HORIZONTAL_LINES),
                    "minQuadArea": MIN_QUAD_AREA,
                    "minQuadEdge": MIN_QUAD_EDGE,
                    "rows": BOARD_ROWS,
                    "verticalSuggestions": list(SUGGESTED_VERTICAL_LINES),
                },
                "limit": limit,
                "offset": offset,
                "pageCount": len(page),
                "progress": self.progress(),
                "samples": [self._entry_payload(entry) for entry in page],
                "totalFiltered": len(filtered),
            }

    def progress(self) -> dict[str, int]:
        accepted = sum(entry.review_status == "accepted" for entry in self._golden.entries)
        return {
            "accepted": accepted,
            "pending": len(self._golden.entries) - accepted,
            "total": len(self._golden.entries),
        }

    def save_draft(
        self,
        *,
        observation_id: str,
        source_quad: object,
        v1_cut_cell_indexes: Iterable[int],
        v1_impact_reviewed: bool,
    ) -> bool:
        with self._lock:
            index, current = self._entry(observation_id)
            if current.review_status == "accepted":
                raise CellGridGoldenError(
                    "CELL_GRID_REOPEN_REQUIRED",
                    "Reopen an accepted board before editing its draft.",
                )
            updated = replace(
                current,
                source_quad=_source_quad(
                    source_quad,
                    "sourceQuad",
                    image_width=current.candidate.source_image_width,
                    image_height=current.candidate.source_image_height,
                ),
                v1_cut_cell_indexes=_cut_cells(
                    sorted(set(v1_cut_cell_indexes)),
                    "v1CutCellIndexes",
                ),
                v1_impact_reviewed=v1_impact_reviewed,
                line_source="human-draft",
                decision_revision=current.decision_revision + 1,
            )
            if replace(updated, decision_revision=current.decision_revision) == current:
                return False
            self._replace_entry(index, updated)
            return True

    def accept(
        self,
        *,
        observation_id: str,
        source_quad: object,
        v1_cut_cell_indexes: Iterable[int],
        v1_impact_reviewed: bool,
        reviewed_by: str,
    ) -> bool:
        reviewer = _reviewer(reviewed_by)
        cut_cells = _cut_cells(
            sorted(set(v1_cut_cell_indexes)),
            "v1CutCellIndexes",
        )
        if not v1_impact_reviewed:
            raise CellGridGoldenError(
                "CELL_GRID_V1_IMPACT_NOT_REVIEWED",
                "Confirm the historical v1 symbol-cut assessment before acceptance.",
            )
        with self._lock:
            index, current = self._entry(observation_id)
            accepted_quad = _source_quad(
                source_quad,
                "sourceQuad",
                image_width=current.candidate.source_image_width,
                image_height=current.candidate.source_image_height,
            )
            line_source: LineSource = (
                "human-confirmed-detected-quad"
                if accepted_quad == current.candidate.detected_source_quad
                else "human-adjusted"
            )
            accepted = replace(
                current,
                source_quad=accepted_quad,
                v1_cut_cell_indexes=cut_cells,
                v1_impact_reviewed=True,
                review_status="accepted",
                reviewed_by=reviewer,
                line_source=line_source,
                decision_revision=current.decision_revision + 1,
            )
            if replace(accepted, decision_revision=current.decision_revision) == current:
                return False
            self._replace_entry(index, accepted)
            return True

    def reopen(self, observation_id: str) -> bool:
        with self._lock:
            index, current = self._entry(observation_id)
            if current.review_status == "pending":
                return False
            reopened = replace(
                current,
                review_status="pending",
                reviewed_by=None,
                line_source="human-draft",
                decision_revision=current.decision_revision + 1,
            )
            self._replace_entry(index, reopened)
            return True

    def resolve_board(self, observation_id: str) -> tuple[Path, str]:
        _, entry = self._entry(observation_id)
        _, path = _safe_relative_path(
            self.crop_root,
            entry.candidate.board_relative_path,
            "entry.boardRelativePath",
        )
        _verify_board(
            path,
            entry.candidate.board_checksum_sha256,
            f"rectified board {observation_id}",
        )
        return path, entry.candidate.board_checksum_sha256

    def resolve_source(self, observation_id: str) -> tuple[Path, str]:
        _, entry = self._entry(observation_id)
        _, path = _safe_relative_path(
            self.source_root,
            entry.candidate.source_image_relative_path,
            "entry.sourceImageRelativePath",
        )
        _verify_source_image(
            path,
            entry.candidate.source_image_checksum_sha256,
            entry.candidate.source_image_width,
            entry.candidate.source_image_height,
            f"source image {entry.candidate.image_id}",
        )
        return path, entry.candidate.source_image_checksum_sha256

    def _entry(self, observation_id: str) -> tuple[int, GridReviewEntry]:
        for index, entry in enumerate(self._golden.entries):
            if entry.candidate.observation_id == observation_id:
                return index, entry
        raise CellGridGoldenError(
            "CELL_GRID_OBSERVATION_UNKNOWN",
            "Unknown board observation.",
        )

    def _replace_entry(self, index: int, entry: GridReviewEntry) -> None:
        entries = list(self._golden.entries)
        entries[index] = entry
        self._golden = replace(
            self._golden,
            review_revision=self._golden.review_revision + 1,
            entries=tuple(entries),
        )
        self._save()

    def _entry_payload(self, entry: GridReviewEntry) -> dict[str, object]:
        value = entry.to_dict()
        value["boardUrl"] = f"/api/boards/{entry.candidate.observation_id}"
        value["sourceImageUrl"] = f"/api/sources/{entry.candidate.observation_id}"
        return value

    def _save(self) -> None:
        _write_atomic(self.output_path, self._golden.to_json_bytes())


def build_v1_baseline_report(review: CellGridGoldenReview) -> dict[str, object]:
    """Measure historical quad and global-margin v1 against the accepted golden."""

    golden = review.golden
    pending = [
        entry.candidate.observation_id
        for entry in golden.entries
        if entry.review_status != "accepted"
    ]
    if pending:
        raise CellGridGoldenError(
            "CELL_GRID_BASELINE_REVIEW_INCOMPLETE",
            f"All {len(golden.entries)} boards must be accepted before baseline generation.",
        )
    golden_bytes = golden.to_json_bytes()
    line_errors: list[dict[str, object]] = []
    quad_errors: list[dict[str, object]] = []
    grouped_axis: dict[str, list[float]] = {"horizontal": [], "vertical": []}
    grouped_position: dict[int, list[float]] = {position: [] for position in range(9)}
    grouped_source: dict[str, list[float]] = {
        source_group: [] for source_group in golden.source_groups
    }
    all_errors: list[float] = []
    all_corner_errors: list[float] = []
    affected_boards: list[dict[str, object]] = []
    for entry in golden.entries:
        candidate = entry.candidate
        detected_matrix = quad_to_canonical_matrix(
            candidate.detected_source_quad,
            board_width=BOARD_WIDTH,
            board_height=BOARD_HEIGHT,
        )
        golden_matrix = quad_to_canonical_matrix(
            entry.source_quad,
            board_width=BOARD_WIDTH,
            board_height=BOARD_HEIGHT,
        )
        correction = golden_matrix @ np.linalg.inv(detected_matrix)
        for corner_index, (detected, expected_point) in enumerate(
            zip(
                candidate.detected_source_quad,
                entry.source_quad,
                strict=True,
            )
        ):
            corner_error = round(math.dist(detected, expected_point), 4)
            all_corner_errors.append(corner_error)
            quad_errors.append(
                {
                    "absoluteErrorPx": corner_error,
                    "boardPosition": candidate.board_position,
                    "cornerIndex": corner_index,
                    "detectedPoint": {"x": detected[0], "y": detected[1]},
                    "expectedPoint": {
                        "x": expected_point[0],
                        "y": expected_point[1],
                    },
                    "observationId": candidate.observation_id,
                    "sequenceNumber": candidate.sequence_number,
                    "sourceGroup": candidate.source_group,
                }
            )
        for axis, expected_lines, historical_lines in (
            ("vertical", SUGGESTED_VERTICAL_LINES, V1_VERTICAL_LINES),
            ("horizontal", SUGGESTED_HORIZONTAL_LINES, V1_HORIZONTAL_LINES),
        ):
            for line_index, (expected_coordinate, historical) in enumerate(
                zip(expected_lines, historical_lines, strict=True)
            ):
                historical_endpoints: tuple[Point, Point] = (
                    (
                        (float(historical), 0.0),
                        (float(historical), float(BOARD_HEIGHT - 1)),
                    )
                    if axis == "vertical"
                    else (
                        (0.0, float(historical)),
                        (float(BOARD_WIDTH - 1), float(historical)),
                    )
                )
                projected_endpoints = project_points(
                    historical_endpoints,
                    correction,
                )
                coordinate_index = 0 if axis == "vertical" else 1
                endpoint_errors = tuple(
                    round(abs(point[coordinate_index] - expected_coordinate), 4)
                    for point in projected_endpoints
                )
                error = round(sum(endpoint_errors) / len(endpoint_errors), 4)
                all_errors.append(error)
                grouped_axis[axis].append(error)
                grouped_position[candidate.board_position].append(error)
                grouped_source[candidate.source_group].append(error)
                line_errors.append(
                    {
                        "absoluteErrorPx": error,
                        "axis": axis,
                        "boardPosition": candidate.board_position,
                        "endpointAbsoluteErrorsPx": list(endpoint_errors),
                        "expectedCoordinate": expected_coordinate,
                        "historicalV1Coordinate": historical,
                        "lineIndex": line_index,
                        "observationId": candidate.observation_id,
                        "projectedEndpoints": [
                            {"x": point[0], "y": point[1]} for point in projected_endpoints
                        ],
                        "sequenceNumber": candidate.sequence_number,
                        "sourceGroup": candidate.source_group,
                    }
                )
        if entry.v1_cut_cell_indexes:
            affected_boards.append(
                {
                    "boardPosition": candidate.board_position,
                    "cellIndexes": list(entry.v1_cut_cell_indexes),
                    "cells": [
                        {
                            "cellIndex": cell_index,
                            "columnIndex": cell_index % BOARD_COLUMNS,
                            "rowIndex": cell_index // BOARD_COLUMNS,
                        }
                        for cell_index in entry.v1_cut_cell_indexes
                    ],
                    "observationId": candidate.observation_id,
                    "sequenceNumber": candidate.sequence_number,
                    "sourceGroup": candidate.source_group,
                }
            )
    return {
        "affectedBoardCount": len(affected_boards),
        "affectedCellObservationCount": sum(
            len(cast(list[object], board["cellIndexes"])) for board in affected_boards
        ),
        "baselineVersion": BASELINE_VERSION,
        "cropperVersion": CROPPER_VERSION,
        "goldenAcceptedEntryCount": len(golden.entries),
        "goldenSha256": hashlib.sha256(golden_bytes).hexdigest(),
        "goldenVersion": GOLDEN_VERSION,
        "geometryVersion": GEOMETRY_VERSION,
        "historicalGrid": {
            "horizontalLines": list(V1_HORIZONTAL_LINES),
            "marginX": MARGIN_X,
            "marginY": MARGIN_Y,
            "verticalLines": list(V1_VERTICAL_LINES),
        },
        "lineErrors": line_errors,
        "quadErrors": quad_errors,
        "percentileMethod": "linear-r7",
        "schemaVersion": 1,
        "status": "historical_cropper_rejected",
        "summary": {
            "byAxis": [
                {"axis": axis, **metric_summary(values)}
                for axis, values in sorted(grouped_axis.items())
            ],
            "byBoardPosition": [
                {
                    "boardPosition": position,
                    **metric_summary(grouped_position[position]),
                }
                for position in range(9)
            ],
            "bySourceGroup": [
                {
                    "sourceGroup": source_group,
                    **metric_summary(grouped_source[source_group]),
                }
                for source_group in golden.source_groups
            ],
            "overall": metric_summary(all_errors),
            "quadCornersOverall": metric_summary(all_corner_errors),
        },
        "trainingAllowed": False,
        "v1SymbolImpact": affected_boards,
    }


def baseline_report_bytes(review: CellGridGoldenReview) -> bytes:
    return _json_bytes(build_v1_baseline_report(review))


__all__ = [
    "BASELINE_VERSION",
    "COORDINATE_SYSTEM",
    "GOLDEN_VERSION",
    "REVIEW_BOARD_COUNT",
    "SELECTION_VERSION",
    "SUGGESTED_HORIZONTAL_LINES",
    "SUGGESTED_VERTICAL_LINES",
    "CellGridGolden",
    "CellGridGoldenError",
    "CellGridGoldenReview",
    "GridReviewEntry",
    "baseline_report_bytes",
    "build_v1_baseline_report",
]
