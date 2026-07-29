"""Immutable export contracts for verified operational review cohorts."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import cast
from uuid import UUID

from game_predictor_api.domain.image_reviews import (
    IMAGE_REVIEW_CELL_COUNT,
    ImageReviewConflictError,
    ImageReviewCounts,
    ImageReviewItem,
    canonical_image_review_bytes,
)

VERIFIED_COHORT_SCHEMA_VERSION = 1
VERIFIED_COHORT_DATASET_KIND = "verified-image-review-cohort-v1"


@dataclass(frozen=True, slots=True)
class VerifiedCohortSource:
    game_id: UUID
    import_job_id: UUID
    input_state_sha256: str
    boards: tuple[Mapping[str, object], ...]
    board_count: int
    sample_count: int
    pending_item_count: int
    rejected_item_count: int


@dataclass(frozen=True, slots=True)
class ImageVerifiedCohortExport:
    id: UUID
    game_id: UUID
    import_job_id: UUID
    version: int
    input_state_sha256: str
    payload_sha256: str
    artifact_relative_path: str
    board_count: int
    sample_count: int
    pending_item_count: int
    rejected_item_count: int
    created_by: str
    created_at: datetime


def validate_cohort_actor(created_by: str) -> str:
    actor = created_by.strip()
    if not actor or len(actor) > 200:
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_COHORT_ACTOR_INVALID",
            "createdBy must identify the local administrator.",
        )
    return actor


def build_verified_cohort_source(
    *,
    game_id: UUID,
    import_job_id: UUID,
    items: Sequence[ImageReviewItem],
    counts: ImageReviewCounts,
) -> VerifiedCohortSource:
    verified_items = tuple(item for item in items if item.status in {"accepted", "corrected"})
    if counts.total != len(items) or counts.completed != len(verified_items):
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_COHORT_COUNTS_INVALID",
            "The operational review counts do not match the locked cohort state.",
        )
    boards = tuple(_verified_board(item) for item in verified_items)
    if not boards:
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_COHORT_EMPTY",
            "At least one accepted or corrected board is required.",
        )
    ordered = tuple(
        sorted(
            boards,
            key=lambda board: (
                cast(int, board["sequenceNumber"]),
                cast(int, board["sourceOrderIndex"]),
                cast(int, board["positionIndex"]),
                cast(str, board["reviewItemId"]),
            ),
        )
    )
    state = {
        "schemaVersion": VERIFIED_COHORT_SCHEMA_VERSION,
        "gameId": str(game_id),
        "importJobId": str(import_job_id),
        "reviewState": [
            {
                "reviewItemId": str(item.id),
                "status": item.status,
                "resolutionRevision": item.resolution_revision,
                "geometryRevision": item.geometry_revision,
            }
            for item in sorted(items, key=lambda item: str(item.id))
        ],
        "counts": {
            "pending": counts.pending,
            "accepted": counts.accepted,
            "corrected": counts.corrected,
            "rejected": counts.rejected,
        },
        "boards": ordered,
    }
    return VerifiedCohortSource(
        game_id=game_id,
        import_job_id=import_job_id,
        input_state_sha256=hashlib.sha256(canonical_image_review_bytes(state)).hexdigest(),
        boards=ordered,
        board_count=len(ordered),
        sample_count=len(ordered) * IMAGE_REVIEW_CELL_COUNT,
        pending_item_count=counts.pending,
        rejected_item_count=counts.rejected,
    )


def build_verified_cohort_payload(
    source: VerifiedCohortSource,
    *,
    version: int,
) -> tuple[dict[str, object], bytes, str]:
    if version < 1:
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_COHORT_VERSION_INVALID",
            "Verified cohort versions must be positive.",
        )
    payload: dict[str, object] = {
        "schemaVersion": VERIFIED_COHORT_SCHEMA_VERSION,
        "datasetKind": VERIFIED_COHORT_DATASET_KIND,
        "version": version,
        "gameId": str(source.game_id),
        "importJobId": str(source.import_job_id),
        "inputStateSha256": source.input_state_sha256,
        "counts": {
            "boards": source.board_count,
            "samples": source.sample_count,
            "pendingItems": source.pending_item_count,
            "rejectedItems": source.rejected_item_count,
        },
        "boards": source.boards,
    }
    payload_bytes = canonical_image_review_bytes(payload)
    return payload, payload_bytes, hashlib.sha256(payload_bytes).hexdigest()


def _verified_board(item: ImageReviewItem) -> Mapping[str, object]:
    if (
        item.status not in {"accepted", "corrected"}
        or item.resolved_value is None
        or item.queue_sequence_number is None
        or item.queue_sequence_number < 1
        or item.resolved_by is None
        or item.resolved_at is None
        or item.resolution_revision < 1
        or len(item.cells) != IMAGE_REVIEW_CELL_COUNT
    ):
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_COHORT_ITEM_INVALID",
            "Every exported board must be a complete accepted or corrected decision.",
        )
    resolved = item.resolved_value
    if (
        resolved.get("geometryRevision") != item.geometry_revision
        or resolved.get("sequenceNumber") != item.queue_sequence_number
        or resolved.get("action") != item.status
    ):
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_COHORT_DECISION_STALE",
            "The verified decision does not reference the current board revision.",
        )
    resolved_cells = resolved.get("cells")
    if not isinstance(resolved_cells, list) or len(resolved_cells) != IMAGE_REVIEW_CELL_COUNT:
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_COHORT_ITEM_INVALID",
            "The verified decision must contain exactly 15 cells.",
        )
    by_index: dict[int, Mapping[str, object]] = {}
    for raw in resolved_cells:
        if not isinstance(raw, Mapping):
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_COHORT_ITEM_INVALID",
                "The verified decision cell payload is invalid.",
            )
        index = raw.get("cellIndex")
        if not isinstance(index, int) or isinstance(index, bool) or index in by_index:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_COHORT_ITEM_INVALID",
                "The verified decision cells are not unique row-major values.",
            )
        by_index[index] = raw
    if set(by_index) != set(range(IMAGE_REVIEW_CELL_COUNT)):
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_COHORT_ITEM_INVALID",
            "The verified decision cells are not a complete row-major board.",
        )
    cells: list[dict[str, object]] = []
    for cell in item.cells:
        resolved_cell = by_index[cell.cell_index]
        symbol_code = resolved_cell.get("symbolCode")
        sample_id = resolved_cell.get("cropSampleId")
        if (
            not isinstance(symbol_code, str)
            or not symbol_code
            or sample_id != cell.crop_sample_id
            or cell.current_symbol_code != symbol_code
        ):
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_COHORT_CROP_CHANGED",
                "A verified label no longer references the current immutable crop.",
            )
        cells.append(
            {
                "cellIndex": cell.cell_index,
                "rowIndex": cell.row_index,
                "columnIndex": cell.column_index,
                "observationId": str(cell.observation_id),
                "cropSampleId": cell.crop_sample_id,
                "cropRelativePath": _safe_relative_path(cell.crop_relative_path),
                "cropChecksumSha256": cell.crop_checksum_sha256,
                "symbolCode": symbol_code,
            }
        )
    return {
        "reviewItemId": str(item.id),
        "recognizedBoardId": str(item.recognized_board_id),
        "sourceOrderIndex": item.source_order_index,
        "positionIndex": item.position_index,
        "sequenceNumber": item.queue_sequence_number,
        "resolutionRevision": item.resolution_revision,
        "decisionStatus": item.status,
        "resolvedBy": item.resolved_by,
        "resolvedAt": item.resolved_at.isoformat(),
        "geometryRevision": item.geometry_revision,
        "geometry": dict(item.geometry),
        "pipelineFingerprint": item.pipeline_fingerprint,
        "source": {
            "relativePath": _safe_relative_path(item.source_relative_path),
            "checksumSha256": item.source_checksum_sha256,
        },
        "board": {
            "relativePath": _safe_relative_path(item.board_relative_path),
            "checksumSha256": item.board_checksum_sha256,
        },
        "cells": cells,
    }


def _safe_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_COHORT_PATH_UNSAFE",
            "Verified cohort assets must use managed relative POSIX paths.",
        )
    return path.as_posix()


__all__ = [
    "ImageVerifiedCohortExport",
    "VerifiedCohortSource",
    "build_verified_cohort_payload",
    "build_verified_cohort_source",
    "validate_cohort_actor",
]
