"""Durable fail-closed state for board-cell geometry processing."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final, Literal
from uuid import UUID

from game_predictor_api.domain.jobs import JobError

BOARD_CELL_PROCESSING_MANIFEST_SCHEMA: Final[Literal["board-cell-processing-manifest-v1"]] = (
    "board-cell-processing-manifest-v1"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class BoardCellGeometryPendingStatus(StrEnum):
    PENDING = "pending"
    RESOLVED = "resolved"
    SUPERSEDED = "superseded"
    # TASK-0949 (migration 0153): the operator discarded a cropped or blurred
    # slot. The position counts as a missing board for the gate (W8).
    REJECTED = "rejected"


class BoardRejectionReason(StrEnum):
    """Why an operator rejects a cropped board or a deferred slot (W7)."""

    CROPPED = "cropped"
    BLURRED = "blurred"
    OTHER = "other"


MAX_BOARD_REJECTION_NOTE_LENGTH = 1000


def normalized_rejection_note(reason: BoardRejectionReason, note: str | None) -> str | None:
    """The stored note: required (1-1000 characters) for ``other``, else none.

    Mirrors ``ck_image_board_geometry_pending_rejection``; a note on another
    reason is dropped so a retry with a stray note replays the same command.
    """

    text = None if note is None else note.strip()
    if reason is BoardRejectionReason.OTHER:
        if not text or len(text) > MAX_BOARD_REJECTION_NOTE_LENGTH:
            raise JobError(
                "IMAGE_BOARD_CELL_PENDING_REJECTION_INVALID",
                "Reason 'other' requires a note of 1-"
                f"{MAX_BOARD_REJECTION_NOTE_LENGTH} characters.",
            )
        return text
    if text is not None and len(text) > MAX_BOARD_REJECTION_NOTE_LENGTH:
        raise JobError(
            "IMAGE_BOARD_CELL_PENDING_REJECTION_INVALID",
            f"The note cannot exceed {MAX_BOARD_REJECTION_NOTE_LENGTH} characters.",
        )
    return None


def rejection_command_sha256(
    *,
    pending_id: UUID,
    reason: BoardRejectionReason,
    note: str | None,
    expected_geometry_revision: int,
) -> str:
    """Identity of one slot-rejection command (what an idempotency key binds to)."""

    payload = {
        "action": "rejected",
        "expectedGeometryRevision": expected_geometry_revision,
        "note": note,
        "pendingId": str(pending_id),
        "reason": reason.value,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


class BoardCellGeometryPendingReason(StrEnum):
    INSUFFICIENT_CENTERS = "insufficient_centers"
    INCOMPLETE_LATTICE = "incomplete_lattice"
    RESIDUAL_TOO_HIGH = "residual_too_high"
    SOURCE_UNAVAILABLE = "source_unavailable"


@dataclass(frozen=True, slots=True)
class BoardCellProcessingManifestV1:
    game_id: UUID
    import_job_id: UUID
    source_image_id: UUID
    source_checksum_sha256: str
    source_relative_path: str
    position_index: int
    sequence_number: int
    pipeline_fingerprint_sha256: str
    estimator_version: str
    estimator_fingerprint_sha256: str
    cropper_version: str
    cropper_fingerprint_sha256: str
    expected_geometry_revision: int
    expected_review_resolution_revision: int
    grid_rows: int | None = None
    grid_columns: int | None = None
    topology_rules_version_id: UUID | None = None
    schema_version: Literal["board-cell-processing-manifest-v1"] = (
        BOARD_CELL_PROCESSING_MANIFEST_SCHEMA
    )

    def __post_init__(self) -> None:
        if self.schema_version != BOARD_CELL_PROCESSING_MANIFEST_SCHEMA:
            raise _invalid_manifest("The board-cell processing manifest version is unsupported.")
        for label, value in (
            ("sourceChecksumSha256", self.source_checksum_sha256),
            ("pipelineFingerprintSha256", self.pipeline_fingerprint_sha256),
            ("estimatorFingerprintSha256", self.estimator_fingerprint_sha256),
            ("cropperFingerprintSha256", self.cropper_fingerprint_sha256),
        ):
            if _SHA256.fullmatch(value) is None:
                raise _invalid_manifest(f"{label} must be a lowercase SHA-256 checksum.")
        if not 0 <= self.position_index <= 8:
            raise _invalid_manifest("positionIndex must be between 0 and 8.")
        if self.sequence_number < 1:
            raise _invalid_manifest("sequenceNumber must be positive.")
        if self.expected_geometry_revision < 0 or self.expected_review_resolution_revision < 0:
            raise _invalid_manifest("Pinned revisions cannot be negative.")
        if not self.estimator_version.strip() or not self.cropper_version.strip():
            raise _invalid_manifest("Estimator and cropper versions are required.")
        topology_values = (
            self.grid_rows,
            self.grid_columns,
            self.topology_rules_version_id,
        )
        if any(value is not None for value in topology_values) and not all(
            value is not None for value in topology_values
        ):
            raise _invalid_manifest("Pinned board topology fields must be complete.")
        if self.grid_rows is not None and (
            self.grid_rows < 1
            or self.grid_rows > 32767
            or self.grid_columns is None
            or self.grid_columns < 1
            or self.grid_columns > 32767
        ):
            raise _invalid_manifest("Pinned board topology dimensions are invalid.")
        _require_safe_relative_path(self.source_relative_path)

    def payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "cropperFingerprintSha256": self.cropper_fingerprint_sha256,
            "cropperVersion": self.cropper_version,
            "estimatorFingerprintSha256": self.estimator_fingerprint_sha256,
            "estimatorVersion": self.estimator_version,
            "expectedGeometryRevision": self.expected_geometry_revision,
            "expectedReviewResolutionRevision": self.expected_review_resolution_revision,
            "gameId": str(self.game_id),
            "importJobId": str(self.import_job_id),
            "pipelineFingerprintSha256": self.pipeline_fingerprint_sha256,
            "positionIndex": self.position_index,
            "schemaVersion": self.schema_version,
            "sequenceNumber": self.sequence_number,
            "sourceChecksumSha256": self.source_checksum_sha256,
            "sourceImageId": str(self.source_image_id),
            "sourceRelativePath": self.source_relative_path,
        }
        if self.topology_rules_version_id is not None:
            payload["gridRows"] = self.grid_rows
            payload["gridColumns"] = self.grid_columns
            payload["topologyRulesVersionId"] = str(self.topology_rules_version_id)
        return payload

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.payload(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")

    @property
    def checksum_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class ImageBoardGeometryPending:
    id: UUID
    game_id: UUID
    import_job_id: UUID
    source_image_id: UUID
    recognized_board_id: UUID | None
    review_item_id: UUID | None
    sequence_number: int
    position_index: int
    source_checksum_sha256: str
    source_relative_path: str
    status: BoardCellGeometryPendingStatus
    reason_code: BoardCellGeometryPendingReason
    processing_manifest_checksum_sha256: str
    processing_manifest_relative_path: str
    pipeline_fingerprint_sha256: str
    expected_geometry_revision: int
    expected_review_resolution_revision: int
    resolved_geometry_revision: int | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    superseded_at: datetime | None
    rejection_reason: BoardRejectionReason | None = None
    rejection_note: str | None = None
    rejected_at: datetime | None = None
    rejected_by: str | None = None


@dataclass(frozen=True, slots=True)
class BoardCellGeometryJobCounts:
    total: int
    pending: int
    resolved: int
    superseded: int
    rejected: int = 0

    def __post_init__(self) -> None:
        if min(self.total, self.pending, self.resolved, self.superseded, self.rejected) < 0:
            raise ValueError("Board-cell geometry counters cannot be negative.")
        if self.total != self.pending + self.resolved + self.superseded + self.rejected:
            raise ValueError("Board-cell geometry counters must add up to total.")


def _invalid_manifest(message: str) -> JobError:
    return JobError("IMAGE_BOARD_CELL_MANIFEST_INVALID", message)


def _require_safe_relative_path(value: str) -> None:
    normalized = value.replace("\\", "/")
    if (
        not value.strip()
        or normalized.startswith("/")
        or any(part == ".." for part in normalized.split("/"))
    ):
        raise _invalid_manifest("sourceRelativePath must be a safe relative path.")


def board_cell_processing_artifact_relative_path(checksum_sha256: str) -> str:
    if _SHA256.fullmatch(checksum_sha256) is None:
        raise _invalid_manifest("The manifest checksum is invalid.")
    return f"data/board-cell-processing-manifests/{checksum_sha256[:2]}/{checksum_sha256}.json"


__all__ = [
    "BOARD_CELL_PROCESSING_MANIFEST_SCHEMA",
    "BoardCellGeometryJobCounts",
    "BoardCellGeometryPendingReason",
    "BoardCellGeometryPendingStatus",
    "BoardCellProcessingManifestV1",
    "BoardRejectionReason",
    "ImageBoardGeometryPending",
    "MAX_BOARD_REJECTION_NOTE_LENGTH",
    "board_cell_processing_artifact_relative_path",
    "normalized_rejection_note",
    "rejection_command_sha256",
]
