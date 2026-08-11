"""Framework-independent contracts for deterministic image selection runs."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from game_predictor_worker.images.selection.manifest import DEFAULT_SELECTOR_MANIFEST

from game_predictor_api.domain.jobs import Job, JobType, create_job

IMAGE_SELECTION_CONTRACT_VERSION = 1
IMAGE_SELECTION_ORDERING_POLICY = "natural_relative_path_v1"
IMAGE_SELECTION_SELECTOR_FINGERPRINT = DEFAULT_SELECTOR_MANIFEST.fingerprint
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
    MISSING_IMAGE = "missing_image"
    SKIPPED_EXISTING_RANGE = "skipped_existing_range"


class ImageSelectionCandidateDecision(StrEnum):
    ELIGIBLE = "eligible"
    REJECTED = "rejected"
    SELECTED_AUTOMATIC = "selected_automatic"
    SELECTED_MANUAL = "selected_manual"


class ImageSelectionManualResolution(StrEnum):
    SELECTED_IMAGE = "selected_image"
    MISSING_IMAGE = "missing_image"
    DUPLICATE_RANGE = "duplicate_range"


class ImageSelectionSequenceDirection(StrEnum):
    ASCENDING = "ascending"
    DESCENDING = "descending"


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
    sequence_direction: ImageSelectionSequenceDirection = ImageSelectionSequenceDirection.ASCENDING
    first_sequence_number: int | None = None


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
class ImageSelectionManualDecision:
    idempotency_key: UUID
    run_id: UUID
    group_id: UUID
    candidate_id: UUID | None
    resolution: ImageSelectionManualResolution
    range_start: int | None
    range_end: int | None
    revision: int
    payload_sha256: str
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
    sequence_direction: ImageSelectionSequenceDirection = (
        ImageSelectionSequenceDirection.ASCENDING
    ),
    first_sequence_number: int | None = None,
    created_at: datetime | None = None,
) -> ImageSelectionRun:
    if game_id.int == 0 or source_selection_id.int == 0:
        raise ImageSelectionError(
            "IMAGE_SELECTION_CONFIGURATION_INVALID",
            "Game and source selection identifiers must not be nil UUID values.",
        )
    manifest = validate_sha256(input_manifest_sha256, field="inputManifestSha256")
    selector = validate_sha256(selector_fingerprint, field="selectorFingerprint")
    if first_sequence_number is not None and first_sequence_number < 1:
        raise ImageSelectionError(
            "IMAGE_SELECTION_CONFIGURATION_INVALID",
            "The optional first sequence number must be positive.",
        )
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
            "sequence_direction": sequence_direction.value,
            "first_sequence_number": first_sequence_number,
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
        sequence_direction=sequence_direction,
        first_sequence_number=first_sequence_number,
    )


def record_image_selection_output(
    run: ImageSelectionRun,
    *,
    manifest_sha256: str,
    manifest_relative_path: str,
    updated_at: datetime | None = None,
) -> ImageSelectionRun:
    checksum = validate_sha256(manifest_sha256, field="outputManifestSha256")
    relative_path = safe_relative_path(manifest_relative_path)
    if run.output_manifest_sha256 is not None:
        if (
            run.output_manifest_sha256 == checksum
            and run.output_manifest_relative_path == relative_path
        ):
            return run
        raise ImageSelectionConflictError(
            "IMAGE_SELECTION_MANIFEST_MISMATCH",
            "The run already references a different immutable output manifest.",
        )
    return replace(
        run,
        output_manifest_sha256=checksum,
        output_manifest_relative_path=relative_path,
        updated_at=updated_at or datetime.now(UTC),
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
    if (
        decision
        in {
            ImageSelectionCandidateDecision.SELECTED_AUTOMATIC,
            ImageSelectionCandidateDecision.SELECTED_MANUAL,
        }
        and group_id is None
    ):
        _configuration_error("A selected candidate must belong to a group.")
    return relative_path


def create_manual_decision(
    *,
    idempotency_key: UUID,
    group: ImageSelectionGroup,
    candidate: ImageSelectionCandidate,
    range_start: int | None,
    range_end: int | None,
    revision: int,
    created_at: datetime | None = None,
) -> tuple[ImageSelectionGroup, ImageSelectionManualDecision]:
    if idempotency_key.int == 0 or revision < 1:
        _configuration_error("Manual decision identifiers and revision must be valid.")
    if group.status not in {
        ImageSelectionGroupStatus.MANUAL_REQUIRED,
        ImageSelectionGroupStatus.MANUALLY_SELECTED,
        ImageSelectionGroupStatus.MISSING_IMAGE,
    }:
        raise ImageSelectionConflictError(
            "IMAGE_SELECTION_GROUP_NOT_MANUAL",
            "Only a manual-review group can accept a manual representative.",
        )
    if candidate.run_id != group.run_id or candidate.group_id != group.id:
        raise ImageSelectionConflictError(
            "IMAGE_SELECTION_CANDIDATE_MISMATCH",
            "The selected JPEG does not belong to this image-selection group.",
        )
    resolved_start = group.range_start if range_start is None else range_start
    resolved_end = group.range_end if range_end is None else range_end
    validate_image_selection_group(
        group_order=group.group_order,
        range_start=resolved_start,
        range_end=resolved_end,
        fingerprint_sha256=group.fingerprint_sha256,
        board_count_consensus=group.board_count_consensus,
    )
    if resolved_start is None or resolved_end is None:
        raise ImageSelectionError(
            "IMAGE_SELECTION_RANGE_REQUIRED",
            "A positive sequence range is required for an unknown group.",
        )
    payload = {
        "candidateId": str(candidate.id),
        "groupId": str(group.id),
        "rangeEnd": resolved_end,
        "rangeStart": resolved_start,
        "runId": str(group.run_id),
    }
    payload_sha256 = hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    now = created_at or datetime.now(UTC)
    updated_group = replace(
        group,
        range_start=resolved_start,
        range_end=resolved_end,
        status=ImageSelectionGroupStatus.MANUALLY_SELECTED,
        selected_candidate_id=candidate.id,
        updated_at=now,
    )
    return updated_group, ImageSelectionManualDecision(
        idempotency_key=idempotency_key,
        run_id=group.run_id,
        group_id=group.id,
        candidate_id=candidate.id,
        resolution=ImageSelectionManualResolution.SELECTED_IMAGE,
        range_start=resolved_start,
        range_end=resolved_end,
        revision=revision,
        payload_sha256=payload_sha256,
        created_at=now,
    )


def create_missing_image_decision(
    *,
    idempotency_key: UUID,
    group: ImageSelectionGroup,
    range_start: int | None,
    range_end: int | None,
    revision: int,
    created_at: datetime | None = None,
) -> tuple[ImageSelectionGroup, ImageSelectionManualDecision]:
    if idempotency_key.int == 0 or revision < 1:
        _configuration_error("Manual decision identifiers and revision must be valid.")
    if group.status not in {
        ImageSelectionGroupStatus.MANUAL_REQUIRED,
        ImageSelectionGroupStatus.MANUALLY_SELECTED,
        ImageSelectionGroupStatus.MISSING_IMAGE,
    }:
        raise ImageSelectionConflictError(
            "IMAGE_SELECTION_GROUP_NOT_MANUAL",
            "Only a manual-review group can be continued without an image.",
        )
    resolved_start = group.range_start if range_start is None else range_start
    resolved_end = group.range_end if range_end is None else range_end
    validate_image_selection_group(
        group_order=group.group_order,
        range_start=resolved_start,
        range_end=resolved_end,
        fingerprint_sha256=group.fingerprint_sha256,
        board_count_consensus=group.board_count_consensus,
    )
    payload = {
        "candidateId": None,
        "groupId": str(group.id),
        "rangeEnd": resolved_end,
        "rangeStart": resolved_start,
        "resolution": ImageSelectionManualResolution.MISSING_IMAGE.value,
        "runId": str(group.run_id),
    }
    payload_sha256 = hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    now = created_at or datetime.now(UTC)
    updated_group = replace(
        group,
        range_start=resolved_start,
        range_end=resolved_end,
        status=ImageSelectionGroupStatus.MISSING_IMAGE,
        selected_candidate_id=None,
        updated_at=now,
    )
    return updated_group, ImageSelectionManualDecision(
        idempotency_key=idempotency_key,
        run_id=group.run_id,
        group_id=group.id,
        candidate_id=None,
        resolution=ImageSelectionManualResolution.MISSING_IMAGE,
        range_start=resolved_start,
        range_end=resolved_end,
        revision=revision,
        payload_sha256=payload_sha256,
        created_at=now,
    )


def create_duplicate_range_decision(
    *,
    idempotency_key: UUID,
    group: ImageSelectionGroup,
    range_start: int,
    range_end: int,
    revision: int,
    created_at: datetime | None = None,
) -> tuple[ImageSelectionGroup, ImageSelectionManualDecision]:
    if idempotency_key.int == 0 or revision < 1:
        _configuration_error("Manual decision identifiers and revision must be valid.")
    if group.status not in {
        ImageSelectionGroupStatus.MANUAL_REQUIRED,
        ImageSelectionGroupStatus.SKIPPED_EXISTING_RANGE,
    }:
        raise ImageSelectionConflictError(
            "IMAGE_SELECTION_GROUP_NOT_MANUAL",
            "Only an unresolved manual-review group can be discarded as a duplicate.",
        )
    validate_image_selection_group(
        group_order=group.group_order,
        range_start=range_start,
        range_end=range_end,
        fingerprint_sha256=group.fingerprint_sha256,
        board_count_consensus=group.board_count_consensus,
    )
    payload = {
        "candidateId": None,
        "groupId": str(group.id),
        "rangeEnd": range_end,
        "rangeStart": range_start,
        "resolution": ImageSelectionManualResolution.DUPLICATE_RANGE.value,
        "runId": str(group.run_id),
    }
    payload_sha256 = hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    now = created_at or datetime.now(UTC)
    updated_group = replace(
        group,
        range_start=range_start,
        range_end=range_end,
        status=ImageSelectionGroupStatus.SKIPPED_EXISTING_RANGE,
        selected_candidate_id=None,
        updated_at=now,
    )
    return updated_group, ImageSelectionManualDecision(
        idempotency_key=idempotency_key,
        run_id=group.run_id,
        group_id=group.id,
        candidate_id=None,
        resolution=ImageSelectionManualResolution.DUPLICATE_RANGE,
        range_start=range_start,
        range_end=range_end,
        revision=revision,
        payload_sha256=payload_sha256,
        created_at=now,
    )


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
    "ImageSelectionManualDecision",
    "ImageSelectionManualResolution",
    "ImageSelectionNotFoundError",
    "ImageSelectionRun",
    "create_duplicate_range_decision",
    "create_image_selection_run",
    "create_manual_decision",
    "create_missing_image_decision",
    "record_image_selection_output",
    "safe_relative_path",
    "validate_candidate",
    "validate_image_selection_group",
    "validate_sha256",
]
