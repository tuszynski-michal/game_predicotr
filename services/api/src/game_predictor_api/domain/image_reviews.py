"""Domain contracts for the job-local operational image review queue."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import cast
from uuid import UUID

IMAGE_REVIEW_CELL_COUNT = 15
MAX_IMAGE_REVIEW_ALTERNATIVES = 4
MAX_IMAGE_REVIEW_PAGE_SIZE = 50
IMAGE_REVIEW_CURSOR_VERSION = 2
BASE_GEOMETRY_REVISION = 0


class ImageReviewView(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    ALL = "all"


class ImageReviewAction(StrEnum):
    ACCEPTED = "accepted"
    CORRECTED = "corrected"
    REJECTED = "rejected"


class ImageReviewError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


class ImageReviewNotFoundError(ImageReviewError):
    pass


class ImageReviewConflictError(ImageReviewError):
    pass


@dataclass(frozen=True, slots=True)
class ImageReviewAlternative:
    symbol_code: str
    confidence: float


@dataclass(frozen=True, slots=True)
class ImageReviewCell:
    observation_id: UUID
    cell_index: int
    row_index: int
    column_index: int
    crop_sample_id: str
    crop_relative_path: str
    crop_checksum_sha256: str
    predicted_symbol_code: str
    confidence: float
    alternatives: tuple[ImageReviewAlternative, ...]
    current_symbol_code: str


@dataclass(frozen=True, slots=True)
class ImageReviewItem:
    id: UUID
    game_id: UUID
    import_job_id: UUID
    source_image_id: UUID
    recognized_board_id: UUID
    status: str
    source_order_index: int
    position_index: int
    queue_sequence_number: int | None
    suggested_sequence_number: int | None
    source_relative_path: str
    source_checksum_sha256: str
    board_relative_path: str
    board_checksum_sha256: str
    geometry_revision: int
    geometry: Mapping[str, object]
    pipeline_fingerprint: str
    cells: tuple[ImageReviewCell, ...]
    resolved_value: Mapping[str, object] | None
    resolved_by: str | None
    resolved_at: datetime | None
    resolution_revision: int
    created_at: datetime

    @property
    def cursor_key(self) -> tuple[int, int, int, str]:
        sequence = self.queue_sequence_number if self.status != "pending" else 0
        return (
            sequence or 0,
            self.source_order_index,
            self.position_index,
            str(self.id),
        )

    @property
    def queue_order_key(self) -> tuple[int, int, str]:
        return (self.source_order_index, self.position_index, str(self.id))


@dataclass(frozen=True, slots=True)
class ImageReviewCounts:
    pending: int
    accepted: int
    corrected: int
    rejected: int
    superseded: int = 0

    @property
    def completed(self) -> int:
        return self.accepted + self.corrected

    @property
    def total(self) -> int:
        return self.pending + self.accepted + self.corrected + self.rejected + self.superseded


@dataclass(frozen=True, slots=True)
class ImageReviewPage:
    items: tuple[ImageReviewItem, ...]
    counts: ImageReviewCounts
    has_previous: bool
    has_next: bool
    queue_version: int | None = None


@dataclass(frozen=True, slots=True)
class ImageReviewCursor:
    key: tuple[int, int, str]
    queue_version: int


@dataclass(frozen=True, slots=True)
class ImageDatasetCompleteness:
    game_id: UUID
    expected_layout_count: int
    accepted_board_count: int
    unique_sequence_count: int
    missing_sequence_count: int
    duplicate_sequence_count: int
    out_of_range_sequence_count: int
    missing_sequence_numbers: tuple[int, ...]
    missing_sequence_numbers_truncated: bool
    manual_override_count: int

    @property
    def completion_percentage(self) -> float:
        return round(
            min(self.unique_sequence_count, self.expected_layout_count)
            * 100
            / self.expected_layout_count,
            4,
        )


@dataclass(frozen=True, slots=True)
class ImageSequenceSourceCandidate:
    review_item_id: UUID
    recognized_board_id: UUID
    import_job_id: UUID
    sequence_number: int
    source_checksum_sha256: str
    source_relative_path: str
    width: int
    height: int
    board_confidence: float
    sequence_confidence: float
    geometry_revision: int
    automatic_rank: int
    quality_score: float
    selected: bool
    selected_manually: bool


@dataclass(frozen=True, slots=True)
class ImageSequenceSourceSelection:
    game_id: UUID
    sequence_number: int
    candidates: tuple[ImageSequenceSourceCandidate, ...]
    manual_override_review_item_id: UUID | None
    override_revision: int


@dataclass(frozen=True, slots=True)
class ImageReviewResolutionCell:
    cell_index: int
    crop_sample_id: str
    symbol_code: str


@dataclass(frozen=True, slots=True)
class ValidatedImageReviewResolution:
    action: ImageReviewAction
    sequence_number: int | None
    geometry_revision: int
    cells: tuple[ImageReviewResolutionCell, ...]
    rejection_reason: str | None
    resolved_by: str
    resolved_value: Mapping[str, object]
    command_sha256: str


@dataclass(frozen=True, slots=True)
class ImageReviewResolutionEvent:
    id: UUID
    review_item_id: UUID
    revision: int
    idempotency_key: UUID
    action: str
    command_sha256: str
    resolved_value: Mapping[str, object]
    resolved_by: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ImageReviewGeometryPoint:
    x: int
    y: int


@dataclass(frozen=True, slots=True)
class ValidatedImageReviewGeometryCommand:
    corners: tuple[
        ImageReviewGeometryPoint,
        ImageReviewGeometryPoint,
        ImageReviewGeometryPoint,
        ImageReviewGeometryPoint,
    ]
    expected_geometry_revision: int
    expected_resolution_revision: int
    corrected_by: str
    command_sha256: str


@dataclass(frozen=True, slots=True)
class ImageReviewGeometryCellArtifact:
    row_index: int
    column_index: int
    crop_relative_path: str
    crop_checksum_sha256: str


@dataclass(frozen=True, slots=True)
class ImageReviewGeometryArtifacts:
    geometry: Mapping[str, object]
    board_relative_path: str
    board_checksum_sha256: str
    cropper_version: str
    cells: tuple[ImageReviewGeometryCellArtifact, ...]


@dataclass(frozen=True, slots=True)
class ImageReviewGeometryRevision:
    id: UUID
    review_item_id: UUID
    recognized_board_id: UUID
    revision: int
    idempotency_key: UUID
    command_sha256: str
    decision_checksum_sha256: str | None
    corners: tuple[
        ImageReviewGeometryPoint,
        ImageReviewGeometryPoint,
        ImageReviewGeometryPoint,
        ImageReviewGeometryPoint,
    ]
    board_relative_path: str
    board_checksum_sha256: str
    cropper_version: str
    cells: tuple[ImageReviewGeometryCellArtifact, ...]
    corrected_by: str
    created_at: datetime


def canonical_image_review_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError) as error:
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_COMMAND_INVALID",
            "The operational review command is not canonical JSON.",
        ) from error


def crop_sample_id(
    *,
    recognized_board_id: UUID,
    row_index: int,
    column_index: int,
    cropper_version: str,
    crop_relative_path: str,
    crop_checksum_sha256: str,
) -> str:
    return hashlib.sha256(
        canonical_image_review_bytes(
            {
                "columnIndex": column_index,
                "cropChecksumSha256": crop_checksum_sha256,
                "cropRelativePath": crop_relative_path,
                "cropperVersion": cropper_version,
                "recognizedBoardId": str(recognized_board_id),
                "rowIndex": row_index,
                "version": 1,
            }
        )
    ).hexdigest()


def validate_image_review_geometry_command(
    *,
    corners: Sequence[ImageReviewGeometryPoint],
    expected_geometry_revision: int,
    expected_resolution_revision: int,
    corrected_by: str,
) -> ValidatedImageReviewGeometryCommand:
    actor = corrected_by.strip()
    if not actor or len(actor) > 200:
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_GEOMETRY_ACTOR_INVALID",
            "correctedBy must identify the local administrator.",
        )
    if expected_geometry_revision < 0 or expected_resolution_revision < 0:
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_GEOMETRY_REVISION_INVALID",
            "Expected geometry and resolution revisions cannot be negative.",
        )
    if len(corners) != 4:
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_GEOMETRY_CORNERS_INVALID",
            "Geometry correction requires exactly four corners.",
        )
    quad = cast(
        tuple[
            ImageReviewGeometryPoint,
            ImageReviewGeometryPoint,
            ImageReviewGeometryPoint,
            ImageReviewGeometryPoint,
        ],
        tuple(corners),
    )
    if len({(point.x, point.y) for point in quad}) != 4:
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_GEOMETRY_CORNERS_INVALID",
            "Geometry correction corners must be distinct.",
        )
    cross_products = tuple(
        _cross_product(quad[index], quad[(index + 1) % 4], quad[(index + 2) % 4])
        for index in range(4)
    )
    doubled_area = sum(
        quad[index].x * quad[(index + 1) % 4].y - quad[(index + 1) % 4].x * quad[index].y
        for index in range(4)
    )
    if doubled_area < 200 or any(value <= 0 for value in cross_products):
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_GEOMETRY_CORNERS_INVALID",
            "Corners must be ordered top-left, top-right, bottom-right, bottom-left "
            "and form a convex board with non-trivial area.",
        )
    command_value = {
        "correctedBy": actor,
        "corners": [{"x": point.x, "y": point.y} for point in quad],
        "expectedGeometryRevision": expected_geometry_revision,
        "expectedResolutionRevision": expected_resolution_revision,
    }
    return ValidatedImageReviewGeometryCommand(
        corners=quad,
        expected_geometry_revision=expected_geometry_revision,
        expected_resolution_revision=expected_resolution_revision,
        corrected_by=actor,
        command_sha256=hashlib.sha256(canonical_image_review_bytes(command_value)).hexdigest(),
    )


def _cross_product(
    first: ImageReviewGeometryPoint,
    second: ImageReviewGeometryPoint,
    third: ImageReviewGeometryPoint,
) -> int:
    return (second.x - first.x) * (third.y - second.y) - (second.y - first.y) * (third.x - second.x)


def encode_image_review_cursor(
    *,
    game_id: UUID,
    import_job_id: UUID,
    view: ImageReviewView,
    key: tuple[int, int, str],
    queue_version: int,
) -> str:
    payload = canonical_image_review_bytes(
        {
            "gameId": str(game_id),
            "importJobId": str(import_job_id),
            "key": list(key),
            "queueVersion": queue_version,
            "version": IMAGE_REVIEW_CURSOR_VERSION,
            "view": view.value,
        }
    )
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_image_review_cursor(
    value: str,
    *,
    game_id: UUID,
    import_job_id: UUID,
    view: ImageReviewView,
) -> ImageReviewCursor:
    try:
        padding = "=" * (-len(value) % 4)
        payload = json.loads(base64.b64decode(value + padding, altchars=b"-_", validate=True))
        key = payload["key"]
        queue_version = payload["queueVersion"]
        parsed_game_id = UUID(payload["gameId"])
        parsed_job_id = UUID(payload["importJobId"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_CURSOR_INVALID",
            "The operational review cursor is invalid.",
        ) from error
    if (
        not isinstance(payload, dict)
        or payload.get("version") != IMAGE_REVIEW_CURSOR_VERSION
        or payload.get("view") != view.value
        or parsed_game_id != game_id
        or parsed_job_id != import_job_id
        or not isinstance(key, list)
        or len(key) != 3
        or not isinstance(key[0], int)
        or isinstance(key[0], bool)
        or not isinstance(key[1], int)
        or isinstance(key[1], bool)
        or key[0] < 0
        or key[1] < 0
        or not isinstance(key[2], str)
        or not isinstance(queue_version, int)
        or isinstance(queue_version, bool)
        or queue_version < 1
    ):
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_CURSOR_SCOPE_INVALID",
            "The operational review cursor does not belong to this queue.",
        )
    try:
        UUID(key[2])
    except ValueError as error:
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_CURSOR_INVALID",
            "The operational review cursor item identity is invalid.",
        ) from error
    return ImageReviewCursor(
        key=cast(tuple[int, int, str], tuple(key)),
        queue_version=queue_version,
    )


def validate_image_review_resolution(
    *,
    item: ImageReviewItem,
    action: ImageReviewAction,
    sequence_number: int | None,
    geometry_revision: int,
    cells: Sequence[ImageReviewResolutionCell],
    rejection_reason: str | None,
    resolved_by: str,
    active_symbol_codes: Sequence[str],
) -> ValidatedImageReviewResolution:
    actor = resolved_by.strip()
    if not actor or len(actor) > 200:
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_ACTOR_INVALID",
            "resolvedBy must identify the local administrator.",
        )
    if geometry_revision != item.geometry_revision:
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_GEOMETRY_REVISION_CONFLICT",
            "The selected geometry revision is no longer current.",
        )
    if action is ImageReviewAction.REJECTED:
        reason = (rejection_reason or "").strip()
        if not reason or len(reason) > 500 or sequence_number is not None or cells:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_REJECTION_INVALID",
                "Rejected review requires only a non-empty reason.",
            )
        resolved_value: dict[str, object] = {
            "action": action.value,
            "geometryRevision": geometry_revision,
            "reason": reason,
        }
        return _validated_resolution(
            action=action,
            sequence_number=None,
            geometry_revision=geometry_revision,
            cells=(),
            rejection_reason=reason,
            resolved_by=actor,
            resolved_value=resolved_value,
        )
    if (
        not isinstance(sequence_number, int)
        or isinstance(sequence_number, bool)
        or sequence_number < 1
        or len(cells) != IMAGE_REVIEW_CELL_COUNT
        or rejection_reason is not None
    ):
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_BOARD_INVALID",
            "Accepted or corrected review requires a positive number and 15 cells.",
        )
    ordered = tuple(sorted(cells, key=lambda cell: cell.cell_index))
    if [cell.cell_index for cell in ordered] != list(range(IMAGE_REVIEW_CELL_COUNT)):
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_CELLS_INVALID",
            "Operational review cells must contain row-major indexes 0..14 exactly once.",
        )
    active = set(active_symbol_codes)
    expected_by_index = {cell.cell_index: cell for cell in item.cells}
    if (
        len(active) != len(active_symbol_codes)
        or any(cell.symbol_code not in active for cell in ordered)
        or any(
            cell.crop_sample_id != expected_by_index[cell.cell_index].crop_sample_id
            for cell in ordered
        )
    ):
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_CELL_CONTRACT_INVALID",
            "Every cell must reference the current crop and an active game symbol.",
        )
    symbols = [cell.symbol_code for cell in ordered]
    predicted = [cell.predicted_symbol_code for cell in item.cells]
    unchanged = sequence_number == item.suggested_sequence_number and symbols == predicted
    if action is ImageReviewAction.ACCEPTED and not unchanged:
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_ACCEPTED_VALUE_CHANGED",
            "Accepted review must preserve the current OCR and symbol predictions.",
        )
    if action is ImageReviewAction.CORRECTED and unchanged:
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_CORRECTION_EMPTY",
            "Corrected review must change the number or at least one symbol.",
        )
    cell_rows = [
        {
            "cellIndex": cell.cell_index,
            "cropSampleId": cell.crop_sample_id,
            "symbolCode": cell.symbol_code,
        }
        for cell in ordered
    ]
    resolved_value = {
        "action": action.value,
        "cells": cell_rows,
        "geometryRevision": geometry_revision,
        "sequenceNumber": sequence_number,
        "symbolCodes": symbols,
    }
    return _validated_resolution(
        action=action,
        sequence_number=sequence_number,
        geometry_revision=geometry_revision,
        cells=ordered,
        rejection_reason=None,
        resolved_by=actor,
        resolved_value=resolved_value,
    )


def _validated_resolution(
    *,
    action: ImageReviewAction,
    sequence_number: int | None,
    geometry_revision: int,
    cells: tuple[ImageReviewResolutionCell, ...],
    rejection_reason: str | None,
    resolved_by: str,
    resolved_value: Mapping[str, object],
) -> ValidatedImageReviewResolution:
    command_sha256 = hashlib.sha256(
        canonical_image_review_bytes(
            {
                "action": action.value,
                "resolvedBy": resolved_by,
                "resolvedValue": dict(resolved_value),
            }
        )
    ).hexdigest()
    return ValidatedImageReviewResolution(
        action=action,
        sequence_number=sequence_number,
        geometry_revision=geometry_revision,
        cells=cells,
        rejection_reason=rejection_reason,
        resolved_by=resolved_by,
        resolved_value=resolved_value,
        command_sha256=command_sha256,
    )


__all__ = [
    "BASE_GEOMETRY_REVISION",
    "IMAGE_REVIEW_CELL_COUNT",
    "MAX_IMAGE_REVIEW_ALTERNATIVES",
    "MAX_IMAGE_REVIEW_PAGE_SIZE",
    "ImageReviewAction",
    "ImageReviewAlternative",
    "ImageReviewCell",
    "ImageReviewConflictError",
    "ImageReviewCounts",
    "ImageDatasetCompleteness",
    "ImageReviewError",
    "ImageReviewGeometryArtifacts",
    "ImageReviewGeometryCellArtifact",
    "ImageReviewGeometryPoint",
    "ImageReviewGeometryRevision",
    "ImageReviewItem",
    "ImageReviewNotFoundError",
    "ImageReviewPage",
    "ImageSequenceSourceCandidate",
    "ImageSequenceSourceSelection",
    "ImageReviewResolutionCell",
    "ImageReviewResolutionEvent",
    "ImageReviewView",
    "ValidatedImageReviewResolution",
    "ValidatedImageReviewGeometryCommand",
    "canonical_image_review_bytes",
    "crop_sample_id",
    "decode_image_review_cursor",
    "encode_image_review_cursor",
    "validate_image_review_resolution",
    "validate_image_review_geometry_command",
]
