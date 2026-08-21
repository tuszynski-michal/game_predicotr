"""Versioned source-space contract for board-cell lattice geometry."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image, UnidentifiedImageError

BOARD_CELL_GEOMETRY_MANIFEST_SCHEMA_VERSION = 1
BOARD_CELL_GEOMETRY_MANIFEST_VERSION = "board-cell-geometry-manifest-v1"
BOARD_CELL_GEOMETRY_VERSION = "board-cell-geometry-v19-multi-point-source-direct-v1"
BOARD_CELL_GEOMETRY_CORPUS_VERSION = "board-cell-geometry-real-corpus-v1"
BOARD_CELL_COORDINATE_SPACE = "source-image-pixels"
BOARD_CELL_CORNER_SEMANTICS = "symbol-lattice-outer-bounds-5x3"
BOARD_ROWS = 3
BOARD_COLUMNS = 5
BOARD_CELL_COUNT = BOARD_ROWS * BOARD_COLUMNS
PAGE_BOARD_COUNT = 9
MIN_RELIABLE_CENTER_COUNT = 10
MIN_INLIER_COUNT = 9
_SHA256_CHARS = frozenset("0123456789abcdef")
_CELL_COORDINATE_TOLERANCE = 0.0002

Point = tuple[float, float]
Quad = tuple[Point, Point, Point, Point]
GridSlot = tuple[int, int]
ManifestPurpose = Literal["regression_corpus", "production"]
EvidenceKind = Literal["automatic", "human_reviewed", "manual_override"]


class BoardCellGeometryContractError(ValueError):
    """Stable failure for malformed or drifted board-cell geometry artifacts."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def canonical_json_bytes(value: object) -> bytes:
    """Return the only byte representation used for geometry content addresses."""

    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode()


@dataclass(frozen=True, slots=True)
class BoardCellQuad:
    row_index: int
    column_index: int
    quad: Quad

    def to_dict(self) -> dict[str, object]:
        return {
            "columnIndex": self.column_index,
            "quad": _quad_dict(self.quad),
            "rowIndex": self.row_index,
        }


@dataclass(frozen=True, slots=True)
class BoardCellGeometryEvidence:
    kind: EvidenceKind
    estimator_version: str
    thresholds_version: str
    locator_version: str | None
    homography_version: str | None
    candidate_center_count: int
    reliable_center_count: int
    inlier_count: int
    inlier_slots: tuple[GridSlot, ...]
    inlier_p95_residual_px: float | None
    decision_checksum_sha256: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "candidateCenterCount": self.candidate_center_count,
            "decisionChecksumSha256": self.decision_checksum_sha256,
            "estimatorVersion": self.estimator_version,
            "homographyVersion": self.homography_version,
            "inlierCount": self.inlier_count,
            "inlierP95ResidualPx": self.inlier_p95_residual_px,
            "inlierSlots": [
                {"columnIndex": column, "rowIndex": row} for row, column in self.inlier_slots
            ],
            "kind": self.kind,
            "locatorVersion": self.locator_version,
            "reliableCenterCount": self.reliable_center_count,
            "thresholdsVersion": self.thresholds_version,
        }


@dataclass(frozen=True, slots=True)
class BoardCellGeometryEntry:
    source_order_index: int
    image_id: str
    source_image_checksum_sha256: str
    source_image_relative_path: str
    source_image_width: int
    source_image_height: int
    source_group: str
    condition_tags: tuple[str, ...]
    sequence_number: int
    position_index: int
    lattice_bounds_quad: Quad
    cells: tuple[BoardCellQuad, ...]
    evidence: BoardCellGeometryEvidence

    def to_dict(self) -> dict[str, object]:
        return {
            "cells": [cell.to_dict() for cell in self.cells],
            "conditionTags": list(self.condition_tags),
            "evidence": self.evidence.to_dict(),
            "imageId": self.image_id,
            "latticeBoundsQuad": _quad_dict(self.lattice_bounds_quad),
            "positionIndex": self.position_index,
            "sequenceNumber": self.sequence_number,
            "sourceGroup": self.source_group,
            "sourceImageChecksumSha256": self.source_image_checksum_sha256,
            "sourceImageHeight": self.source_image_height,
            "sourceImageRelativePath": self.source_image_relative_path,
            "sourceImageWidth": self.source_image_width,
            "sourceOrderIndex": self.source_order_index,
        }


@dataclass(frozen=True, slots=True)
class BoardCellGeometryManifestV1:
    purpose: ManifestPurpose
    scope_id: str
    source_manifest_checksum_sha256: str
    page_geometry_manifest_checksum_sha256: str | None
    annotation_manifest_checksum_sha256: str | None
    entries: tuple[BoardCellGeometryEntry, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "annotationManifestChecksumSha256": self.annotation_manifest_checksum_sha256,
            "boardCount": len(self.entries),
            "coordinateSpace": BOARD_CELL_COORDINATE_SPACE,
            "cornerSemantics": BOARD_CELL_CORNER_SEMANTICS,
            "entries": [entry.to_dict() for entry in self.entries],
            "geometryVersion": BOARD_CELL_GEOMETRY_VERSION,
            "manifestPurpose": self.purpose,
            "pageGeometryManifestChecksumSha256": (self.page_geometry_manifest_checksum_sha256),
            "schemaVersion": BOARD_CELL_GEOMETRY_MANIFEST_SCHEMA_VERSION,
            "scopeId": self.scope_id,
            "sourceCount": len({entry.source_image_checksum_sha256 for entry in self.entries}),
            "sourceManifestChecksumSha256": self.source_manifest_checksum_sha256,
            "version": BOARD_CELL_GEOMETRY_MANIFEST_VERSION,
        }

    def to_json_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    @property
    def checksum_sha256(self) -> str:
        return hashlib.sha256(self.to_json_bytes()).hexdigest()


def parse_board_cell_geometry_manifest(
    value: object,
) -> BoardCellGeometryManifestV1:
    """Parse the strict v1 envelope and revalidate all derived cell quads."""

    manifest = _mapping(value, "manifest")
    _exact_keys(
        manifest,
        {
            "annotationManifestChecksumSha256",
            "boardCount",
            "coordinateSpace",
            "cornerSemantics",
            "entries",
            "geometryVersion",
            "manifestPurpose",
            "pageGeometryManifestChecksumSha256",
            "schemaVersion",
            "scopeId",
            "sourceCount",
            "sourceManifestChecksumSha256",
            "version",
        },
        "manifest",
    )
    if (
        manifest.get("schemaVersion") != BOARD_CELL_GEOMETRY_MANIFEST_SCHEMA_VERSION
        or manifest.get("version") != BOARD_CELL_GEOMETRY_MANIFEST_VERSION
        or manifest.get("geometryVersion") != BOARD_CELL_GEOMETRY_VERSION
        or manifest.get("coordinateSpace") != BOARD_CELL_COORDINATE_SPACE
        or manifest.get("cornerSemantics") != BOARD_CELL_CORNER_SEMANTICS
    ):
        raise _error("BOARD_CELL_GEOMETRY_VERSION_UNSUPPORTED", "Manifest versions differ.")
    purpose = manifest.get("manifestPurpose")
    if purpose not in {"regression_corpus", "production"}:
        raise _error("BOARD_CELL_GEOMETRY_MANIFEST_INVALID", "Manifest purpose is invalid.")
    page_checksum = _optional_sha256(
        manifest.get("pageGeometryManifestChecksumSha256"),
        "manifest.pageGeometryManifestChecksumSha256",
    )
    annotation_checksum = _optional_sha256(
        manifest.get("annotationManifestChecksumSha256"),
        "manifest.annotationManifestChecksumSha256",
    )
    if (purpose == "production" and page_checksum is None) or (
        purpose == "regression_corpus" and annotation_checksum is None
    ):
        raise _error(
            "BOARD_CELL_GEOMETRY_PROVENANCE_MISSING",
            "Manifest purpose requires its immutable upstream geometry checksum.",
        )
    raw_entries = _sequence(manifest.get("entries"), "manifest.entries")
    entries = tuple(
        _parse_entry(raw, f"manifest.entries[{index}]") for index, raw in enumerate(raw_entries)
    )
    board_count = _integer(manifest.get("boardCount"), "manifest.boardCount", minimum=1)
    source_count = _integer(manifest.get("sourceCount"), "manifest.sourceCount", minimum=1)
    if board_count != len(entries) or source_count != len(
        {entry.source_image_checksum_sha256 for entry in entries}
    ):
        raise _error(
            "BOARD_CELL_GEOMETRY_COUNT_MISMATCH",
            "Manifest counters differ from its entries.",
        )
    expected_order = tuple(
        sorted(
            entries,
            key=lambda entry: (
                entry.source_order_index,
                entry.position_index,
                entry.source_image_checksum_sha256,
            ),
        )
    )
    if entries != expected_order:
        raise _error(
            "BOARD_CELL_GEOMETRY_ORDER_INVALID",
            "Geometry entries must use deterministic source and board order.",
        )
    _validate_entry_identity(entries)
    return BoardCellGeometryManifestV1(
        purpose=cast(ManifestPurpose, purpose),
        scope_id=_text(manifest.get("scopeId"), "manifest.scopeId"),
        source_manifest_checksum_sha256=_sha256(
            manifest.get("sourceManifestChecksumSha256"),
            "manifest.sourceManifestChecksumSha256",
        ),
        page_geometry_manifest_checksum_sha256=page_checksum,
        annotation_manifest_checksum_sha256=annotation_checksum,
        entries=entries,
    )


def load_board_cell_geometry_manifest(content: bytes) -> BoardCellGeometryManifestV1:
    try:
        value: Any = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _error(
            "BOARD_CELL_GEOMETRY_JSON_INVALID",
            "Board-cell geometry manifest is not valid JSON.",
        ) from error
    return parse_board_cell_geometry_manifest(value)


def load_real_board_cell_geometry_corpus(
    repository_root: Path,
    descriptor_path: Path,
    *,
    verify_source_images: bool = True,
) -> BoardCellGeometryManifestV1:
    """Adapt the accepted 27-board owner golden into the strict v19 contract."""

    root = repository_root.resolve(strict=True)
    descriptor = _load_json(descriptor_path, "corpusDescriptor")
    _exact_keys(
        descriptor,
        {
            "annotationManifest",
            "coordinateSpace",
            "cornerSemantics",
            "expectedBoardCount",
            "expectedBoardsPerPosition",
            "expectedManifestChecksumSha256",
            "expectedSourceGroupCount",
            "geometryVersion",
            "schemaVersion",
            "scopeId",
            "sourceManifest",
            "version",
        },
        "corpusDescriptor",
    )
    if (
        descriptor.get("schemaVersion") != 1
        or descriptor.get("version") != BOARD_CELL_GEOMETRY_CORPUS_VERSION
        or descriptor.get("geometryVersion") != BOARD_CELL_GEOMETRY_VERSION
        or descriptor.get("coordinateSpace") != BOARD_CELL_COORDINATE_SPACE
        or descriptor.get("cornerSemantics") != BOARD_CELL_CORNER_SEMANTICS
    ):
        raise _error(
            "BOARD_CELL_GEOMETRY_CORPUS_UNSUPPORTED",
            "The real-corpus descriptor versions or semantics differ.",
        )
    source_bytes, source_manifest = _load_checked_reference(
        root,
        descriptor.get("sourceManifest"),
        "corpusDescriptor.sourceManifest",
    )
    annotation_bytes, annotations = _load_checked_reference(
        root,
        descriptor.get("annotationManifest"),
        "corpusDescriptor.annotationManifest",
    )
    images = _source_images(source_manifest)
    source_root = _safe_path(
        root,
        source_manifest.get("rootPath"),
        "sourceManifest.rootPath",
        directory=True,
    )
    entries = _real_corpus_entries(
        annotations,
        images,
        source_root=source_root,
        verify_source_images=verify_source_images,
    )
    expected_count = _integer(
        descriptor.get("expectedBoardCount"),
        "corpusDescriptor.expectedBoardCount",
        minimum=1,
    )
    expected_per_position = _integer(
        descriptor.get("expectedBoardsPerPosition"),
        "corpusDescriptor.expectedBoardsPerPosition",
        minimum=1,
    )
    expected_source_groups = _integer(
        descriptor.get("expectedSourceGroupCount"),
        "corpusDescriptor.expectedSourceGroupCount",
        minimum=1,
    )
    position_counts = Counter(entry.position_index for entry in entries)
    if (
        len(entries) != expected_count
        or any(position_counts[position] != expected_per_position for position in range(9))
        or len({entry.source_group for entry in entries}) != expected_source_groups
    ):
        raise _error(
            "BOARD_CELL_GEOMETRY_CORPUS_INCOMPLETE",
            "The owner-reviewed corpus does not have the pinned coverage.",
        )
    manifest = BoardCellGeometryManifestV1(
        purpose="regression_corpus",
        scope_id=_text(descriptor.get("scopeId"), "corpusDescriptor.scopeId"),
        source_manifest_checksum_sha256=hashlib.sha256(source_bytes).hexdigest(),
        page_geometry_manifest_checksum_sha256=None,
        annotation_manifest_checksum_sha256=hashlib.sha256(annotation_bytes).hexdigest(),
        entries=entries,
    )
    validated = parse_board_cell_geometry_manifest(manifest.to_dict())
    expected_manifest_checksum = _sha256(
        descriptor.get("expectedManifestChecksumSha256"),
        "corpusDescriptor.expectedManifestChecksumSha256",
    )
    if validated.checksum_sha256 != expected_manifest_checksum:
        raise _error(
            "BOARD_CELL_GEOMETRY_CORPUS_MANIFEST_DRIFT",
            "The derived v19 corpus manifest changed without a reviewed descriptor update.",
        )
    return validated


def write_content_addressed_manifest(
    manifest: BoardCellGeometryManifestV1,
    output_directory: Path,
) -> Path:
    """Persist one immutable manifest under its canonical SHA-256 filename."""

    content = manifest.to_json_bytes()
    checksum = hashlib.sha256(content).hexdigest()
    output_directory.mkdir(parents=True, exist_ok=True)
    output = output_directory / f"{checksum}.json"
    if output.exists():
        if output.read_bytes() != content:
            raise _error(
                "BOARD_CELL_GEOMETRY_MANIFEST_COLLISION",
                "A content-addressed geometry manifest has different bytes.",
            )
        return output
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{checksum}.",
        suffix=".tmp",
        dir=output_directory,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, output)
        except FileExistsError:
            if output.read_bytes() != content:
                raise _error(
                    "BOARD_CELL_GEOMETRY_MANIFEST_COLLISION",
                    "A content-addressed geometry manifest has different bytes.",
                ) from None
        finally:
            temporary.unlink(missing_ok=True)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise _error(
            "BOARD_CELL_GEOMETRY_MANIFEST_WRITE_FAILED",
            "The geometry manifest could not be written atomically.",
        ) from error
    return output


def _real_corpus_entries(
    annotations: Mapping[str, object],
    images: Mapping[str, Mapping[str, object]],
    *,
    source_root: Path,
    verify_source_images: bool,
) -> tuple[BoardCellGeometryEntry, ...]:
    if (
        annotations.get("goldenVersion") != "cell-grid-golden-v1"
        or annotations.get("geometryVersion") != "source-quad-perspective-grid-v1"
        or annotations.get("coordinateSystem") != BOARD_CELL_COORDINATE_SPACE
        or annotations.get("status") != "accepted"
    ):
        raise _error(
            "BOARD_CELL_GEOMETRY_CORPUS_SOURCE_INVALID",
            "The source golden is not the accepted perspective-grid review.",
        )
    entries: list[BoardCellGeometryEntry] = []
    for index, raw in enumerate(_sequence(annotations.get("entries"), "annotations.entries")):
        value = _mapping(raw, f"annotations.entries[{index}]")
        image_id = _text(value.get("imageId"), f"annotations.entries[{index}].imageId")
        image = images.get(image_id)
        if image is None:
            raise _error(
                "BOARD_CELL_GEOMETRY_CORPUS_SOURCE_INVALID",
                f"The source manifest has no {image_id} image.",
            )
        source_checksum = _sha256(
            value.get("sourceImageChecksumSha256"),
            f"annotations.entries[{index}].sourceImageChecksumSha256",
        )
        source_relative_path = _safe_relative_path_text(
            value.get("sourceImageRelativePath"),
            f"annotations.entries[{index}].sourceImageRelativePath",
        )
        source_width = _integer(
            value.get("sourceImageWidth"),
            f"annotations.entries[{index}].sourceImageWidth",
            minimum=1,
        )
        source_height = _integer(
            value.get("sourceImageHeight"),
            f"annotations.entries[{index}].sourceImageHeight",
            minimum=1,
        )
        if (
            image.get("sha256") != source_checksum
            or image.get("relativePath") != source_relative_path
            or image.get("width") != source_width
            or image.get("height") != source_height
        ):
            raise _error(
                "BOARD_CELL_GEOMETRY_CORPUS_SOURCE_DRIFT",
                f"The source chain differs for {image_id}.",
            )
        if verify_source_images:
            _verify_source_image(
                source_root,
                source_relative_path,
                expected_checksum=source_checksum,
                expected_width=source_width,
                expected_height=source_height,
            )
        if value.get("reviewStatus") != "accepted" or not str(
            value.get("lineSource", "")
        ).startswith("human-"):
            raise _error(
                "BOARD_CELL_GEOMETRY_CORPUS_UNREVIEWED",
                f"Geometry {image_id} was not accepted by the owner.",
            )
        lattice_bounds = _parse_quad(
            value.get("sourceQuad"),
            f"annotations.entries[{index}].sourceQuad",
            image_width=source_width,
            image_height=source_height,
        )
        cells = _derive_cell_quads(lattice_bounds)
        decision_checksum = hashlib.sha256(canonical_json_bytes(value)).hexdigest()
        condition_tags = tuple(
            sorted(
                _text(tag, f"sourceManifest.{image_id}.conditionTags")
                for tag in _sequence(image.get("conditionTags"), "conditionTags")
            )
        )
        entries.append(
            BoardCellGeometryEntry(
                source_order_index=_integer(
                    value.get("selectionIndex"),
                    f"annotations.entries[{index}].selectionIndex",
                ),
                image_id=image_id,
                source_image_checksum_sha256=source_checksum,
                source_image_relative_path=source_relative_path,
                source_image_width=source_width,
                source_image_height=source_height,
                source_group=_text(image.get("sourceGroup"), f"sourceManifest.{image_id}"),
                condition_tags=condition_tags,
                sequence_number=_integer(
                    value.get("sequenceNumber"),
                    f"annotations.entries[{index}].sequenceNumber",
                    minimum=1,
                ),
                position_index=_integer(
                    value.get("boardPosition"),
                    f"annotations.entries[{index}].boardPosition",
                    maximum=PAGE_BOARD_COUNT - 1,
                ),
                lattice_bounds_quad=lattice_bounds,
                cells=cells,
                evidence=BoardCellGeometryEvidence(
                    kind="human_reviewed",
                    estimator_version="human-reviewed-cell-grid-golden-v1",
                    thresholds_version="human-reviewed-cell-grid-golden-v1",
                    locator_version=None,
                    homography_version=None,
                    candidate_center_count=0,
                    reliable_center_count=0,
                    inlier_count=0,
                    inlier_slots=(),
                    inlier_p95_residual_px=None,
                    decision_checksum_sha256=decision_checksum,
                ),
            )
        )
    return tuple(
        sorted(entries, key=lambda entry: (entry.source_order_index, entry.position_index))
    )


def _source_images(manifest: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    images: dict[str, Mapping[str, object]] = {}
    values = _sequence(manifest.get("images"), "sourceManifest.images")
    if _integer(manifest.get("imageCount"), "sourceManifest.imageCount", minimum=1) != len(values):
        raise _error("BOARD_CELL_GEOMETRY_CORPUS_SOURCE_INVALID", "imageCount differs.")
    for index, raw in enumerate(values):
        value = _mapping(raw, f"sourceManifest.images[{index}]")
        image_id = _text(value.get("id"), f"sourceManifest.images[{index}].id")
        if image_id in images:
            raise _error(
                "BOARD_CELL_GEOMETRY_CORPUS_SOURCE_INVALID",
                f"Duplicate source image {image_id}.",
            )
        images[image_id] = value
    return images


def _parse_entry(value: object, label: str) -> BoardCellGeometryEntry:
    entry = _mapping(value, label)
    _exact_keys(
        entry,
        {
            "cells",
            "conditionTags",
            "evidence",
            "imageId",
            "latticeBoundsQuad",
            "positionIndex",
            "sequenceNumber",
            "sourceGroup",
            "sourceImageChecksumSha256",
            "sourceImageHeight",
            "sourceImageRelativePath",
            "sourceImageWidth",
            "sourceOrderIndex",
        },
        label,
    )
    width = _integer(entry.get("sourceImageWidth"), f"{label}.sourceImageWidth", minimum=1)
    height = _integer(entry.get("sourceImageHeight"), f"{label}.sourceImageHeight", minimum=1)
    bounds = _parse_quad(
        entry.get("latticeBoundsQuad"),
        f"{label}.latticeBoundsQuad",
        image_width=width,
        image_height=height,
    )
    cells = _parse_cells(
        entry.get("cells"),
        f"{label}.cells",
        lattice_bounds=bounds,
        image_width=width,
        image_height=height,
    )
    tags = tuple(
        _text(tag, f"{label}.conditionTags")
        for tag in _sequence(entry.get("conditionTags"), f"{label}.conditionTags")
    )
    if tags != tuple(sorted(set(tags))):
        raise _error(
            "BOARD_CELL_GEOMETRY_TAGS_INVALID",
            f"{label}.conditionTags must be sorted and unique.",
        )
    return BoardCellGeometryEntry(
        source_order_index=_integer(entry.get("sourceOrderIndex"), f"{label}.sourceOrderIndex"),
        image_id=_text(entry.get("imageId"), f"{label}.imageId"),
        source_image_checksum_sha256=_sha256(
            entry.get("sourceImageChecksumSha256"), f"{label}.sourceImageChecksumSha256"
        ),
        source_image_relative_path=_safe_relative_path_text(
            entry.get("sourceImageRelativePath"), f"{label}.sourceImageRelativePath"
        ),
        source_image_width=width,
        source_image_height=height,
        source_group=_text(entry.get("sourceGroup"), f"{label}.sourceGroup"),
        condition_tags=tags,
        sequence_number=_integer(entry.get("sequenceNumber"), f"{label}.sequenceNumber", minimum=1),
        position_index=_integer(
            entry.get("positionIndex"),
            f"{label}.positionIndex",
            maximum=PAGE_BOARD_COUNT - 1,
        ),
        lattice_bounds_quad=bounds,
        cells=cells,
        evidence=_parse_evidence(entry.get("evidence"), f"{label}.evidence"),
    )


def _parse_evidence(value: object, label: str) -> BoardCellGeometryEvidence:
    evidence = _mapping(value, label)
    _exact_keys(
        evidence,
        {
            "candidateCenterCount",
            "decisionChecksumSha256",
            "estimatorVersion",
            "homographyVersion",
            "inlierCount",
            "inlierP95ResidualPx",
            "inlierSlots",
            "kind",
            "locatorVersion",
            "reliableCenterCount",
            "thresholdsVersion",
        },
        label,
    )
    kind = evidence.get("kind")
    if kind not in {"automatic", "human_reviewed", "manual_override"}:
        raise _error("BOARD_CELL_GEOMETRY_EVIDENCE_INVALID", f"{label}.kind is invalid.")
    candidate_count = _integer(
        evidence.get("candidateCenterCount"), f"{label}.candidateCenterCount"
    )
    reliable_count = _integer(evidence.get("reliableCenterCount"), f"{label}.reliableCenterCount")
    inlier_count = _integer(evidence.get("inlierCount"), f"{label}.inlierCount")
    slots = tuple(
        _parse_slot(raw, f"{label}.inlierSlots[{index}]")
        for index, raw in enumerate(_sequence(evidence.get("inlierSlots"), f"{label}.inlierSlots"))
    )
    if len(set(slots)) != len(slots) or tuple(sorted(slots)) != slots:
        raise _error(
            "BOARD_CELL_GEOMETRY_EVIDENCE_INVALID",
            f"{label}.inlierSlots must be sorted and unique.",
        )
    residual = _optional_number(evidence.get("inlierP95ResidualPx"), f"{label}.inlierP95ResidualPx")
    decision_checksum = _optional_sha256(
        evidence.get("decisionChecksumSha256"), f"{label}.decisionChecksumSha256"
    )
    locator_version = _optional_text(evidence.get("locatorVersion"), f"{label}.locatorVersion")
    homography_version = _optional_text(
        evidence.get("homographyVersion"), f"{label}.homographyVersion"
    )
    if kind == "automatic":
        if (
            candidate_count < reliable_count
            or reliable_count < inlier_count
            or reliable_count < MIN_RELIABLE_CENTER_COUNT
            or inlier_count != len(slots)
            or inlier_count < MIN_INLIER_COUNT
            or {row for row, _ in slots} != set(range(BOARD_ROWS))
            or {column for _, column in slots} != set(range(BOARD_COLUMNS))
            or residual is None
            or locator_version is None
            or homography_version is None
            or decision_checksum is not None
        ):
            raise _error(
                "BOARD_CELL_GEOMETRY_AUTOMATIC_EVIDENCE_INSUFFICIENT",
                "Automatic geometry lacks the required multi-point evidence.",
            )
    elif (
        candidate_count != 0
        or reliable_count != 0
        or inlier_count != 0
        or slots
        or residual is not None
        or locator_version is not None
        or homography_version is not None
        or decision_checksum is None
    ):
        raise _error(
            "BOARD_CELL_GEOMETRY_HUMAN_EVIDENCE_INVALID",
            "Human geometry must carry a decision checksum, not synthetic RANSAC evidence.",
        )
    return BoardCellGeometryEvidence(
        kind=cast(EvidenceKind, kind),
        estimator_version=_text(evidence.get("estimatorVersion"), f"{label}.estimatorVersion"),
        thresholds_version=_text(evidence.get("thresholdsVersion"), f"{label}.thresholdsVersion"),
        locator_version=locator_version,
        homography_version=homography_version,
        candidate_center_count=candidate_count,
        reliable_center_count=reliable_count,
        inlier_count=inlier_count,
        inlier_slots=slots,
        inlier_p95_residual_px=residual,
        decision_checksum_sha256=decision_checksum,
    )


def _parse_cells(
    value: object,
    label: str,
    *,
    lattice_bounds: Quad,
    image_width: int,
    image_height: int,
) -> tuple[BoardCellQuad, ...]:
    values = _sequence(value, label)
    if len(values) != BOARD_CELL_COUNT:
        raise _error(
            "BOARD_CELL_GEOMETRY_CELL_COUNT_INVALID",
            f"{label} must contain exactly {BOARD_CELL_COUNT} cells.",
        )
    expected = _derive_cell_quads(lattice_bounds)
    cells: list[BoardCellQuad] = []
    for index, raw in enumerate(values):
        item = _mapping(raw, f"{label}[{index}]")
        _exact_keys(item, {"columnIndex", "quad", "rowIndex"}, f"{label}[{index}]")
        row = _integer(item.get("rowIndex"), f"{label}[{index}].rowIndex", maximum=2)
        column = _integer(item.get("columnIndex"), f"{label}[{index}].columnIndex", maximum=4)
        if (row, column) != divmod(index, BOARD_COLUMNS):
            raise _error(
                "BOARD_CELL_GEOMETRY_CELL_ORDER_INVALID",
                f"{label} must use complete 3x5 row-major order.",
            )
        quad = _parse_quad(
            item.get("quad"),
            f"{label}[{index}].quad",
            image_width=image_width,
            image_height=image_height,
        )
        if not _quads_close(quad, expected[index].quad):
            raise _error(
                "BOARD_CELL_GEOMETRY_CELL_DERIVATION_MISMATCH",
                f"{label}[{index}] does not derive from latticeBoundsQuad.",
            )
        cells.append(BoardCellQuad(row_index=row, column_index=column, quad=quad))
    return tuple(cells)


def _derive_cell_quads(lattice_bounds: Quad) -> tuple[BoardCellQuad, ...]:
    canonical = np.asarray(
        [[0.0, 0.0], [float(BOARD_COLUMNS), 0.0], [float(BOARD_COLUMNS), 3.0], [0.0, 3.0]],
        dtype=np.float32,
    )
    source = np.asarray(lattice_bounds, dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(canonical, source)
    cells: list[BoardCellQuad] = []
    for row in range(BOARD_ROWS):
        for column in range(BOARD_COLUMNS):
            logical = np.asarray(
                [
                    [float(column), float(row)],
                    [float(column + 1), float(row)],
                    [float(column + 1), float(row + 1)],
                    [float(column), float(row + 1)],
                ],
                dtype=np.float32,
            )
            projected = cast(
                NDArray[np.float32],
                cv2.perspectiveTransform(logical.reshape((-1, 1, 2)), matrix).reshape((-1, 2)),
            )
            quad = cast(
                Quad,
                tuple(
                    (round(float(point[0]), 4), round(float(point[1]), 4)) for point in projected
                ),
            )
            cells.append(BoardCellQuad(row_index=row, column_index=column, quad=quad))
    return tuple(cells)


def derive_board_cell_quads(
    lattice_bounds: Quad,
    *,
    source_image_width: int,
    source_image_height: int,
) -> tuple[BoardCellQuad, ...]:
    """Validate source-space lattice bounds and derive the canonical 3 x 5 cells."""

    width = _integer(source_image_width, "sourceImageWidth", minimum=1)
    height = _integer(source_image_height, "sourceImageHeight", minimum=1)
    validated = _parse_quad(
        _quad_dict(lattice_bounds),
        "latticeBoundsQuad",
        image_width=width,
        image_height=height,
    )
    return _derive_cell_quads(validated)


def _parse_quad(
    value: object,
    label: str,
    *,
    image_width: int,
    image_height: int,
) -> Quad:
    values = _sequence(value, label)
    if len(values) != 4:
        raise _error(
            "BOARD_CELL_GEOMETRY_QUAD_INVALID",
            f"{label} must contain TL, TR, BR and BL.",
        )
    points: list[Point] = []
    for index, raw in enumerate(values):
        item = _mapping(raw, f"{label}[{index}]")
        _exact_keys(item, {"x", "y"}, f"{label}[{index}]")
        x = _number(item.get("x"), f"{label}[{index}].x")
        y = _number(item.get("y"), f"{label}[{index}].y")
        if not 0 <= x < image_width or not 0 <= y < image_height:
            raise _error(
                "BOARD_CELL_GEOMETRY_QUAD_OUT_OF_BOUNDS",
                f"{label}[{index}] lies outside the source image.",
            )
        points.append((x, y))
    quad = cast(Quad, tuple(points))
    crosses = []
    for index in range(4):
        first, second, third = quad[index], quad[(index + 1) % 4], quad[(index + 2) % 4]
        crosses.append(
            (second[0] - first[0]) * (third[1] - second[1])
            - (second[1] - first[1]) * (third[0] - second[0])
        )
    area = abs(
        sum(
            quad[index][0] * quad[(index + 1) % 4][1] - quad[(index + 1) % 4][0] * quad[index][1]
            for index in range(4)
        )
        / 2.0
    )
    if (
        area <= 16.0
        or not all(cross > 0 for cross in crosses)
        or (quad[0][0] + quad[3][0]) >= (quad[1][0] + quad[2][0])
        or (quad[0][1] + quad[1][1]) >= (quad[2][1] + quad[3][1])
    ):
        raise _error(
            "BOARD_CELL_GEOMETRY_QUAD_INVALID",
            f"{label} must be an ordered convex perspective quad.",
        )
    return quad


def _validate_entry_identity(entries: tuple[BoardCellGeometryEntry, ...]) -> None:
    seen_source_positions: set[tuple[str, int]] = set()
    seen_order_positions: set[tuple[int, int]] = set()
    seen_sequences: set[int] = set()
    source_metadata: dict[str, tuple[str, int, int]] = {}
    for entry in entries:
        source_position = (entry.source_image_checksum_sha256, entry.position_index)
        order_position = (entry.source_order_index, entry.position_index)
        if (
            source_position in seen_source_positions
            or order_position in seen_order_positions
            or entry.sequence_number in seen_sequences
        ):
            raise _error(
                "BOARD_CELL_GEOMETRY_IDENTITY_DUPLICATE",
                "Geometry entries duplicate a source position, order position or sequence.",
            )
        seen_source_positions.add(source_position)
        seen_order_positions.add(order_position)
        seen_sequences.add(entry.sequence_number)
        metadata = (
            entry.source_image_relative_path,
            entry.source_image_width,
            entry.source_image_height,
        )
        existing = source_metadata.setdefault(entry.source_image_checksum_sha256, metadata)
        if existing != metadata:
            raise _error(
                "BOARD_CELL_GEOMETRY_SOURCE_METADATA_MISMATCH",
                "One source checksum has conflicting path or dimensions.",
            )


def _load_checked_reference(
    root: Path,
    value: object,
    label: str,
) -> tuple[bytes, Mapping[str, object]]:
    reference = _mapping(value, label)
    _exact_keys(reference, {"relativePath", "sha256"}, label)
    path = _safe_path(root, reference.get("relativePath"), f"{label}.relativePath")
    expected = _sha256(reference.get("sha256"), f"{label}.sha256")
    try:
        content = path.read_bytes()
    except OSError as error:
        raise _error(
            "BOARD_CELL_GEOMETRY_ARTIFACT_UNREADABLE", f"{label} is unreadable."
        ) from error
    if hashlib.sha256(content).hexdigest() != expected:
        raise _error("BOARD_CELL_GEOMETRY_ARTIFACT_DRIFT", f"{label} checksum differs.")
    try:
        payload: Any = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _error("BOARD_CELL_GEOMETRY_JSON_INVALID", f"{label} is invalid JSON.") from error
    return content, _mapping(payload, label)


def _load_json(path: Path, label: str) -> Mapping[str, object]:
    try:
        payload: Any = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _error("BOARD_CELL_GEOMETRY_JSON_INVALID", f"{label} is invalid JSON.") from error
    return _mapping(payload, label)


def _verify_source_image(
    source_root: Path,
    relative_path: str,
    *,
    expected_checksum: str,
    expected_width: int,
    expected_height: int,
) -> None:
    path = _safe_path(source_root, relative_path, "sourceImageRelativePath")
    try:
        content = path.read_bytes()
        with Image.open(path) as image:
            image.load()
            dimensions = image.size
    except (OSError, UnidentifiedImageError) as error:
        raise _error(
            "BOARD_CELL_GEOMETRY_SOURCE_UNREADABLE", "A corpus source image is unreadable."
        ) from error
    if hashlib.sha256(content).hexdigest() != expected_checksum:
        raise _error("BOARD_CELL_GEOMETRY_SOURCE_DRIFT", "A corpus source checksum differs.")
    if dimensions != (expected_width, expected_height):
        raise _error("BOARD_CELL_GEOMETRY_SOURCE_DRIFT", "Corpus source dimensions differ.")


def _safe_path(root: Path, value: object, label: str, *, directory: bool = False) -> Path:
    relative = _safe_relative_path_text(value, label)
    base = root.resolve(strict=True)
    try:
        resolved = (base / Path(*PurePosixPath(relative).parts)).resolve(strict=True)
    except OSError as error:
        raise _error("BOARD_CELL_GEOMETRY_ARTIFACT_MISSING", f"{label} is missing.") from error
    if not resolved.is_relative_to(base) or (directory and not resolved.is_dir()):
        raise _error("BOARD_CELL_GEOMETRY_PATH_UNSAFE", f"{label} escapes its root.")
    return resolved


def _safe_relative_path_text(value: object, label: str) -> str:
    text = _text(value, label)
    relative = PurePosixPath(text)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise _error("BOARD_CELL_GEOMETRY_PATH_UNSAFE", f"{label} must be a safe POSIX path.")
    return text


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise _error("BOARD_CELL_GEOMETRY_CONTRACT_INVALID", f"{label} must be an object.")
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise _error("BOARD_CELL_GEOMETRY_CONTRACT_INVALID", f"{label} must be an array.")
    return cast(Sequence[object], value)


def _exact_keys(value: Mapping[str, object], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise _error(
            "BOARD_CELL_GEOMETRY_CONTRACT_INVALID",
            f"{label} fields differ from the pinned v1 contract.",
        )


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise _error("BOARD_CELL_GEOMETRY_CONTRACT_INVALID", f"{label} must be text.")
    return value


def _optional_text(value: object, label: str) -> str | None:
    return None if value is None else _text(value, label)


def _integer(
    value: object,
    label: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < minimum
        or (maximum is not None and value > maximum)
    ):
        raise _error("BOARD_CELL_GEOMETRY_CONTRACT_INVALID", f"{label} is invalid.")
    return value


def _number(value: object, label: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(value):
        raise _error("BOARD_CELL_GEOMETRY_CONTRACT_INVALID", f"{label} must be finite.")
    return round(float(value), 4)


def _optional_number(value: object, label: str) -> float | None:
    if value is None:
        return None
    number = _number(value, label)
    if number < 0:
        raise _error("BOARD_CELL_GEOMETRY_CONTRACT_INVALID", f"{label} cannot be negative.")
    return number


def _sha256(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(character not in _SHA256_CHARS for character in text):
        raise _error("BOARD_CELL_GEOMETRY_CONTRACT_INVALID", f"{label} is not SHA-256.")
    return text


def _optional_sha256(value: object, label: str) -> str | None:
    return None if value is None else _sha256(value, label)


def _parse_slot(value: object, label: str) -> GridSlot:
    slot = _mapping(value, label)
    _exact_keys(slot, {"columnIndex", "rowIndex"}, label)
    return (
        _integer(slot.get("rowIndex"), f"{label}.rowIndex", maximum=BOARD_ROWS - 1),
        _integer(slot.get("columnIndex"), f"{label}.columnIndex", maximum=BOARD_COLUMNS - 1),
    )


def _quad_dict(quad: Quad) -> list[dict[str, float]]:
    return [{"x": point[0], "y": point[1]} for point in quad]


def _quads_close(first: Quad, second: Quad) -> bool:
    return all(
        abs(first_point[axis] - second_point[axis]) <= _CELL_COORDINATE_TOLERANCE
        for first_point, second_point in zip(first, second, strict=True)
        for axis in (0, 1)
    )


def _error(code: str, message: str) -> BoardCellGeometryContractError:
    return BoardCellGeometryContractError(code, message)


__all__ = [
    "BOARD_CELL_COORDINATE_SPACE",
    "BOARD_CELL_CORNER_SEMANTICS",
    "BOARD_CELL_COUNT",
    "BOARD_CELL_GEOMETRY_CORPUS_VERSION",
    "BOARD_CELL_GEOMETRY_MANIFEST_SCHEMA_VERSION",
    "BOARD_CELL_GEOMETRY_MANIFEST_VERSION",
    "BOARD_CELL_GEOMETRY_VERSION",
    "BOARD_COLUMNS",
    "BOARD_ROWS",
    "BoardCellGeometryContractError",
    "BoardCellGeometryEntry",
    "BoardCellGeometryEvidence",
    "BoardCellGeometryManifestV1",
    "BoardCellQuad",
    "canonical_json_bytes",
    "derive_board_cell_quads",
    "load_board_cell_geometry_manifest",
    "load_real_board_cell_geometry_corpus",
    "parse_board_cell_geometry_manifest",
    "write_content_addressed_manifest",
]
