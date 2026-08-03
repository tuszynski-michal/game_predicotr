"""Framework-independent contracts for deterministic image selection runs."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from game_predictor_api.domain.jobs import Job, JobType, create_job

IMAGE_SELECTION_CONTRACT_VERSION = 1
IMAGE_SELECTION_ORDERING_POLICY = "natural_relative_path_v1"
IMAGE_SELECTION_SELECTOR_FINGERPRINT = hashlib.sha256(
    b"image-selection-staging-contract-v1"
).hexdigest()
IMAGE_SELECTION_GROUP_PAGE_DEFAULT = 25
IMAGE_SELECTION_GROUP_PAGE_MAX = 100

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ImageSelectionError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class ImageSelectionNotFoundError(ImageSelectionError):
    """A requested image-selection resource does not exist."""


class ImageSelectionConflictError(ImageSelectionError):
    """Image-selection state conflicts with a requested operation."""


class ImageSelectionGroupStatus(StrEnum):
    COLLECTING = "collecting"
    AUTO_SELECTED = "auto_selected"
    MANUAL_REQUIRED = "manual_required"
    MANUALLY_SELECTED = "manually_selected"
    SKIPPED_EXISTING_RANGE = "skipped_existing_range"


class ImageSelectionCandidateDecision(StrEnum):
    ELIGIBLE = "eligible"
    REJECTED = "rejected"
    SELECTED_AUTOMATIC = "selected_automatic"
    SELECTED_MANUAL = "selected_manual"


@dataclass(frozen=True, slots=True)
class ImageSelectionRun:
    id: UUID
    game_id: UUID
    job: Job
    source_selection_id: UUID
    input_manifest_sha256: str
    selector_fingerprint: str
    ordering_policy: str
    contract_version: int
    output_manifest_sha256: str | None
    output_manifest_relative_path: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ImageSelectionGroup:
    id: UUID
    run_id: UUID
    group_order: int
    range_start: int | None
    range_end: int | None
    fingerprint_sha256: str | None
    board_count_consensus: int | None
    status: ImageSelectionGroupStatus
    selected_candidate_id: UUID | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ImageSelectionCandidate:
    id: UUID
    run_id: UUID
    group_id: UUID | None
    order_index: int
    source_relative_path: str
    checksum_sha256: str
    width: int
    height: int
    quality_metrics: dict[str, object]
    range_confidence: float | None
    reason_codes: tuple[str, ...]
    decision: ImageSelectionCandidateDecision
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ImageSelectionGroupPage:
    items: tuple[ImageSelectionGroup, ...]
    next_after_group_order: int | None


def create_image_selection_run(
    *,
    game_id: UUID,
    source_selection_id: UUID,
    input_manifest_sha256: str,
    selector_fingerprint: str,
    created_at: datetime | None = None,
) -> ImageSelectionRun:
    if game_id.int == 0 or source_selection_id.int == 0:
        raise ImageSelectionError(
            "IMAGE_SELECTION_CONFIGURATION_INVALID",
            "Game and source selection identifiers must not be nil UUID values.",
        )
    manifest = validate_sha256(input_manifest_sha256, field="inputManifestSha256")
    selector = validate_sha256(selector_fingerprint, field="selectorFingerprint")
    now = created_at or datetime.now(UTC)
    job = create_job(
        JobType.IMAGE_SELECTION,
        game_id=game_id,
        input_payload={
            "schema_version": 1,
            "source_selection_id": str(source_selection_id),
            "input_manifest_sha256": manifest,
            "selector_fingerprint": selector,
            "contract_version": IMAGE_SELECTION_CONTRACT_VERSION,
        },
        created_at=now,
    )
    return ImageSelectionRun(
        id=uuid4(),
        game_id=game_id,
        job=job,
        source_selection_id=source_selection_id,
        input_manifest_sha256=manifest,
        selector_fingerprint=selector,
        ordering_policy=IMAGE_SELECTION_ORDERING_POLICY,
        contract_version=IMAGE_SELECTION_CONTRACT_VERSION,
        output_manifest_sha256=None,
        output_manifest_relative_path=None,
        created_at=now,
        updated_at=now,
    )


def validate_image_selection_group(
    *,
    group_order: int,
    range_start: int | None,
    range_end: int | None,
    fingerprint_sha256: str | None,
    board_count_consensus: int | None,
) -> None:
    if group_order < 0:
        _configuration_error("groupOrder must be non-negative.")
    if (range_start is None) != (range_end is None):
        _configuration_error("A recognized range requires both rangeStart and rangeEnd.")
    if (
        range_start is not None
        and range_end is not None
        and (range_start < 1 or range_end < range_start)
    ):
        raise ImageSelectionError(
            "IMAGE_SELECTION_RANGE_INVALID",
            "A recognized range must be positive and ordered.",
        )
    if fingerprint_sha256 is not None:
        validate_sha256(fingerprint_sha256, field="fingerprintSha256")
    if board_count_consensus is not None and not 1 <= board_count_consensus <= 9:
        _configuration_error("boardCountConsensus must be between 1 and 9.")


def validate_candidate(
    *,
    order_index: int,
    source_relative_path: str,
    checksum_sha256: str,
    width: int,
    height: int,
    range_confidence: float | None,
    decision: ImageSelectionCandidateDecision,
    group_id: UUID | None,
) -> str:
    if order_index < 0:
        _configuration_error("orderIndex must be non-negative.")
    relative_path = safe_relative_path(source_relative_path)
    validate_sha256(checksum_sha256, field="checksumSha256")
    if width < 1 or height < 1:
        _configuration_error("Candidate dimensions must be positive.")
    if range_confidence is not None and not 0 <= range_confidence <= 1:
        _configuration_error("rangeConfidence must be between 0 and 1.")
    if decision in {
        ImageSelectionCandidateDecision.SELECTED_AUTOMATIC,
        ImageSelectionCandidateDecision.SELECTED_MANUAL,
    } and group_id is None:
        _configuration_error("A selected candidate must belong to a group.")
    return relative_path


def validate_sha256(value: str, *, field: str) -> str:
    normalized = value.strip()
    if _SHA256_PATTERN.fullmatch(normalized) is None:
        _configuration_error(f"{field} must be a lowercase SHA-256 value.")
    return normalized


def safe_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in value
        or (path.parts and ":" in path.parts[0])
    ):
        raise ImageSelectionError(
            "IMAGE_SELECTION_PATH_UNSAFE",
            "Image-selection assets must use managed relative POSIX paths.",
        )
    return path.as_posix()


def _configuration_error(message: str) -> None:
    raise ImageSelectionError("IMAGE_SELECTION_CONFIGURATION_INVALID", message)


__all__ = [
    "IMAGE_SELECTION_CONTRACT_VERSION",
    "IMAGE_SELECTION_GROUP_PAGE_DEFAULT",
    "IMAGE_SELECTION_GROUP_PAGE_MAX",
    "IMAGE_SELECTION_ORDERING_POLICY",
    "IMAGE_SELECTION_SELECTOR_FINGERPRINT",
    "ImageSelectionCandidate",
    "ImageSelectionCandidateDecision",
    "ImageSelectionConflictError",
    "ImageSelectionError",
    "ImageSelectionGroup",
    "ImageSelectionGroupPage",
    "ImageSelectionGroupStatus",
    "ImageSelectionNotFoundError",
    "ImageSelectionRun",
    "create_image_selection_run",
    "safe_relative_path",
    "validate_candidate",
    "validate_image_selection_group",
    "validate_sha256",
]
