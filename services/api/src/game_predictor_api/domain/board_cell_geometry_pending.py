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
        _require_safe_relative_path(self.source_relative_path)

    def payload(self) -> dict[str, object]:
        return {
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


@dataclass(frozen=True, slots=True)
class BoardCellGeometryJobCounts:
    total: int
    pending: int
    resolved: int
    superseded: int

    def __post_init__(self) -> None:
        if min(self.total, self.pending, self.resolved, self.superseded) < 0:
            raise ValueError("Board-cell geometry counters cannot be negative.")
        if self.total != self.pending + self.resolved + self.superseded:
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
    "ImageBoardGeometryPending",
    "board_cell_processing_artifact_relative_path",
]
