"""OpenAPI contracts for image-selection runs and bounded group pages."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from game_predictor_worker.images.selection.manifest import selector_manifest_for_fingerprint
from game_predictor_worker.images.selection.sequence_bounds import SequenceBounds
from pydantic import Field

from game_predictor_api.application.image_selections import ImageSelectionRecoveryPreview
from game_predictor_api.domain.image_selections import (
    ImageSelectionCandidate,
    ImageSelectionExecutionMode,
    ImageSelectionGroup,
    ImageSelectionGroupPage,
    ImageSelectionGroupStatus,
    ImageSelectionManualDecision,
    ImageSelectionManualResolution,
    ImageSelectionRun,
    ImageSelectionSequenceDirection,
)
from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.schemas.jobs import JobResponse

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ImageSelectionCreate(ApiModel):
    game_id: UUID
    selection_token: str = Field(min_length=32, max_length=200)
    contract_version: Literal[1] = 1
    sequence_direction: ImageSelectionSequenceDirection = ImageSelectionSequenceDirection.ASCENDING
    first_sequence_number: int = Field(ge=1)


class ImageSelectionRerunCommand(ApiModel):
    first_sequence_number: int | None = Field(default=None, ge=1)
    last_sequence_number: int | None = Field(default=None, ge=1)


class ImageSelectionRunResponse(ApiModel):
    id: UUID
    game_id: UUID
    job: JobResponse
    source_selection_id: UUID
    input_manifest_sha256: Sha256
    selector_fingerprint: Sha256
    selector_version: str = Field(min_length=1, max_length=100)
    ordering_policy: str = Field(pattern=r"^natural_relative_path_v1$")
    contract_version: int = Field(ge=1, le=1)
    output_manifest_sha256: Sha256 | None
    output_manifest_relative_path: str | None
    created_at: datetime
    updated_at: datetime
    sequence_direction: ImageSelectionSequenceDirection
    first_sequence_number: int | None = Field(default=None, ge=1)
    last_sequence_number: int | None = Field(default=None, ge=1)
    expected_group_count: int | None = Field(default=None, ge=1)
    sequence_range_start: int | None = Field(default=None, ge=1)
    sequence_range_end: int | None = Field(default=None, ge=1)
    execution_mode: ImageSelectionExecutionMode
    source_run_id: UUID | None
    source_snapshot_sha256: Sha256 | None


class ImageSelectionCreateResponse(ApiModel):
    run: ImageSelectionRunResponse
    created: bool


class ImageSelectionRecoveryCommand(ApiModel):
    expected_source_snapshot_sha256: Sha256
    last_sequence_number: int | None = Field(default=None, ge=1)


class ImageSelectionRecoveryPreviewResponse(ApiModel):
    source_run_id: UUID
    source_snapshot_sha256: Sha256
    problem_group_count: int = Field(ge=1)
    candidate_count: int = Field(ge=1)
    block_count: int = Field(ge=1)
    selector_fingerprint: Sha256
    selector_version: str = Field(min_length=1, max_length=100)


class ImageSelectionRecoveryCreateResponse(ApiModel):
    run: ImageSelectionRunResponse
    created: bool
    preview: ImageSelectionRecoveryPreviewResponse


def to_image_selection_recovery_preview_response(
    preview: ImageSelectionRecoveryPreview,
) -> ImageSelectionRecoveryPreviewResponse:
    return ImageSelectionRecoveryPreviewResponse(
        source_run_id=preview.source_run_id,
        source_snapshot_sha256=preview.source_snapshot_sha256,
        problem_group_count=preview.problem_group_count,
        candidate_count=preview.candidate_count,
        block_count=preview.block_count,
        selector_fingerprint=preview.selector_fingerprint,
        selector_version=preview.selector_version,
    )


class ImageSelectionRunPageResponse(ApiModel):
    items: list[ImageSelectionRunResponse]
    next_offset: int | None = Field(default=None, ge=0)


class ImageSelectionHandoffResponse(ApiModel):
    run_id: UUID
    game_id: UUID
    selection_id: UUID
    selection_token: str = Field(min_length=32, max_length=200)
    supported_file_count: int = Field(ge=0)
    expires_at: datetime
    target_section: Literal["imports"] = "imports"


class ImageSelectionOutputFileResponse(ApiModel):
    file_name: str = Field(pattern=r"^(?:seq_[1-9][0-9]*-[1-9][0-9]*|selection_[0-9]+)\.jpg$")
    group_order: int = Field(ge=0)
    range_start: int | None = Field(default=None, ge=1)
    range_end: int | None = Field(default=None, ge=1)
    checksum_sha256: Sha256
    size_bytes: int = Field(ge=1)
    reason_codes: list[str]
    selection_method: Literal["automatic", "manual"]


class ImageSelectionOutputResponse(ApiModel):
    run_id: UUID
    manifest_sha256: Sha256
    files: list[ImageSelectionOutputFileResponse]


class ImageSelectionGroupResponse(ApiModel):
    id: UUID
    run_id: UUID
    group_order: int = Field(ge=0)
    range_start: int | None = Field(default=None, ge=1)
    range_end: int | None = Field(default=None, ge=1)
    fingerprint_sha256: Sha256 | None
    board_count_consensus: int | None = Field(default=None, ge=1, le=9)
    status: ImageSelectionGroupStatus
    selected_candidate_id: UUID | None
    rejection_origin_status: ImageSelectionGroupStatus | None
    origin_group_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ImageSelectionGroupPageResponse(ApiModel):
    items: list[ImageSelectionGroupResponse]
    next_after_group_order: int | None = Field(default=None, ge=0)


class ImageSelectionCandidateResponse(ApiModel):
    id: UUID
    run_id: UUID
    group_id: UUID | None
    order_index: int = Field(ge=0)
    checksum_sha256: Sha256
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    display_name: str


class ImageSelectionGroupCandidatesResponse(ApiModel):
    group_id: UUID
    source_count: int = Field(ge=1)
    items: list[ImageSelectionCandidateResponse]


class ImageSelectionManualFileResponse(ApiModel):
    candidate: ImageSelectionCandidateResponse


class ImageSelectionManualApprovalCommand(ApiModel):
    candidate_id: UUID
    idempotency_key: UUID
    range_start: int | None = Field(default=None, ge=1)
    range_end: int | None = Field(default=None, ge=1)


class ImageSelectionMissingImageCommand(ApiModel):
    idempotency_key: UUID
    range_start: int | None = Field(default=None, ge=1)
    range_end: int | None = Field(default=None, ge=1)


class ImageSelectionDuplicateRangeCommand(ApiModel):
    idempotency_key: UUID
    range_start: int = Field(ge=1)
    range_end: int = Field(ge=1)


class ImageSelectionRangeConfirmationCommand(ApiModel):
    idempotency_key: UUID
    candidate_id: UUID | None = None
    range_start: int = Field(ge=1)
    range_end: int | None = Field(default=None, ge=1)


class ImageSelectionGroupDecisionCommand(ApiModel):
    idempotency_key: UUID


class ImageSelectionManualDecisionResponse(ApiModel):
    idempotency_key: UUID
    run_id: UUID
    group_id: UUID
    candidate_id: UUID | None
    resolution: ImageSelectionManualResolution
    range_start: int | None = Field(default=None, ge=1)
    range_end: int | None = Field(default=None, ge=1)
    revision: int = Field(ge=1)
    created_at: datetime


class ImageSelectionManualApprovalResponse(ApiModel):
    group: ImageSelectionGroupResponse
    decision: ImageSelectionManualDecisionResponse


def to_image_selection_run_response(
    run: ImageSelectionRun,
    sequence_range: tuple[int, int] | None = None,
) -> ImageSelectionRunResponse:
    selector_manifest = selector_manifest_for_fingerprint(run.selector_fingerprint)
    bounds = (
        None
        if run.first_sequence_number is None or run.last_sequence_number is None
        else SequenceBounds(
            run.first_sequence_number,
            run.last_sequence_number,
            run.sequence_direction.value,
        )
    )
    return ImageSelectionRunResponse(
        id=run.id,
        game_id=run.game_id,
        job=JobResponse.from_domain(run.job),
        source_selection_id=run.source_selection_id,
        input_manifest_sha256=run.input_manifest_sha256,
        selector_fingerprint=run.selector_fingerprint,
        selector_version=(
            selector_manifest.algorithm_version if selector_manifest is not None else "unknown"
        ),
        ordering_policy=run.ordering_policy,
        contract_version=run.contract_version,
        output_manifest_sha256=run.output_manifest_sha256,
        output_manifest_relative_path=run.output_manifest_relative_path,
        created_at=run.created_at,
        updated_at=run.updated_at,
        sequence_direction=run.sequence_direction,
        first_sequence_number=run.first_sequence_number,
        last_sequence_number=run.last_sequence_number,
        expected_group_count=None if bounds is None else bounds.expected_group_count,
        sequence_range_start=None if sequence_range is None else sequence_range[0],
        sequence_range_end=None if sequence_range is None else sequence_range[1],
        execution_mode=run.execution_mode,
        source_run_id=run.source_run_id,
        source_snapshot_sha256=run.source_snapshot_sha256,
    )


def to_image_selection_group_response(
    group: ImageSelectionGroup,
) -> ImageSelectionGroupResponse:
    return ImageSelectionGroupResponse(
        id=group.id,
        run_id=group.run_id,
        group_order=group.group_order,
        range_start=group.range_start,
        range_end=group.range_end,
        fingerprint_sha256=group.fingerprint_sha256,
        board_count_consensus=group.board_count_consensus,
        status=group.status,
        selected_candidate_id=group.selected_candidate_id,
        rejection_origin_status=group.rejection_origin_status,
        origin_group_id=group.origin_group_id,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


def to_image_selection_group_page_response(
    page: ImageSelectionGroupPage,
) -> ImageSelectionGroupPageResponse:
    return ImageSelectionGroupPageResponse(
        items=[to_image_selection_group_response(item) for item in page.items],
        next_after_group_order=page.next_after_group_order,
    )


def to_image_selection_candidate_response(
    candidate: ImageSelectionCandidate,
) -> ImageSelectionCandidateResponse:
    display_name = candidate.quality_metrics.get("displayName")
    original_path = candidate.quality_metrics.get("sourceOriginalRelativePath")
    fallback_path = (
        original_path if isinstance(original_path, str) else candidate.source_relative_path
    )
    return ImageSelectionCandidateResponse(
        id=candidate.id,
        run_id=candidate.run_id,
        group_id=candidate.group_id,
        order_index=candidate.order_index,
        checksum_sha256=candidate.checksum_sha256,
        width=candidate.width,
        height=candidate.height,
        display_name=(display_name if isinstance(display_name, str) else Path(fallback_path).name),
    )


def to_image_selection_group_candidates_response(
    *,
    group_id: UUID,
    candidates: Sequence[ImageSelectionCandidate],
) -> ImageSelectionGroupCandidatesResponse:
    items = tuple(candidates)
    source_count_value = items[0].quality_metrics.get("groupSourceCount") if items else None
    source_count = (
        source_count_value
        if isinstance(source_count_value, int) and source_count_value >= 1
        else max(1, len(items))
    )
    return ImageSelectionGroupCandidatesResponse(
        group_id=group_id,
        source_count=source_count,
        items=[to_image_selection_candidate_response(item) for item in items],
    )


def to_manual_decision_response(
    decision: ImageSelectionManualDecision,
) -> ImageSelectionManualDecisionResponse:
    return ImageSelectionManualDecisionResponse(
        idempotency_key=decision.idempotency_key,
        run_id=decision.run_id,
        group_id=decision.group_id,
        candidate_id=decision.candidate_id,
        resolution=decision.resolution,
        range_start=decision.range_start,
        range_end=decision.range_end,
        revision=decision.revision,
        created_at=decision.created_at,
    )


__all__ = [
    "ImageSelectionCreate",
    "ImageSelectionCreateResponse",
    "ImageSelectionCandidateResponse",
    "ImageSelectionGroupPageResponse",
    "ImageSelectionGroupDecisionCommand",
    "ImageSelectionGroupCandidatesResponse",
    "ImageSelectionGroupResponse",
    "ImageSelectionRunResponse",
    "ImageSelectionRunPageResponse",
    "ImageSelectionHandoffResponse",
    "ImageSelectionManualApprovalCommand",
    "ImageSelectionManualApprovalResponse",
    "ImageSelectionDuplicateRangeCommand",
    "ImageSelectionManualDecisionResponse",
    "ImageSelectionManualFileResponse",
    "ImageSelectionMissingImageCommand",
    "ImageSelectionOutputFileResponse",
    "ImageSelectionOutputResponse",
    "ImageSelectionRangeConfirmationCommand",
    "ImageSelectionRecoveryCommand",
    "ImageSelectionRecoveryCreateResponse",
    "ImageSelectionRecoveryPreviewResponse",
    "to_image_selection_candidate_response",
    "to_image_selection_group_candidates_response",
    "to_image_selection_group_page_response",
    "to_image_selection_group_response",
    "to_image_selection_run_response",
    "to_image_selection_recovery_preview_response",
    "to_manual_decision_response",
]
