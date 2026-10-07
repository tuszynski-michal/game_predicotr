"""OpenAPI contracts for global semi-automatic image-selection runs."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from game_predictor_api.domain.semi_automatic_image_selections import (
    FilenameRangeVerificationReview,
    FilenameRangeVerificationReviewDecision,
    FilenameVerificationHistoryDeletion,
    SemiAutomaticSelectionDirection,
    SemiAutomaticSelectionRange,
    SemiAutomaticSelectionRangeStatus,
    SemiAutomaticSelectionRun,
    SemiAutomaticSelectionRunStatus,
    SemiAutomaticSelectionWorkflowMode,
    SemiAutomaticV7BorderStyle,
    SemiAutomaticV7SelectionMode,
)
from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.schemas.jobs import JobResponse
from game_predictor_api.schemas.v7_selection_delivery import (
    V7ConfirmedRange,
    V7OutputOperationResponse,
    V7OutputReceiptResponse,
    V7PilotSnapshotResponse,
    V7ReviewResponse,
    V7SourceDiagnosticsResponse,
)

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class SemiAutomaticSelectionRecognizerVariantResponse(ApiModel):
    id: Literal["default_v3", "five_anchor_v6"]
    label: str = Field(min_length=1)
    fingerprint: Sha256
    default: bool
    experimental: bool


class SemiAutomaticV7CapabilitiesResponse(ApiModel):
    feedback_trace_version: Literal["v7-selection-feedback-context-v1"] = (
        "v7-selection-feedback-context-v1"
    )
    activation_status: Literal["blocked", "active"]
    start_enabled: bool
    automatic_start_enabled: Literal[False] = False
    manual_confirmation_required: Literal[True] = True
    source_policy: Literal["exact_sources", "operator_selected_local_folder"] = "exact_sources"
    reason: str = Field(min_length=1)
    configuration_version: Literal["v7-selection-configuration-v1", "v7-selection-configuration-v2"]
    default_mode: SemiAutomaticV7SelectionMode
    default_direction: SemiAutomaticSelectionDirection
    default_border_style: SemiAutomaticV7BorderStyle
    border_styles: list[SemiAutomaticV7BorderStyle]


class SemiAutomaticV7SelectionCreate(ApiModel):
    mode: SemiAutomaticV7SelectionMode = SemiAutomaticV7SelectionMode.SEMI_AUTOMATIC
    border_style: SemiAutomaticV7BorderStyle = SemiAutomaticV7BorderStyle.TOP_AND_SIDES
    output_base_directory: str | None = Field(default=None, min_length=1, max_length=1024)


class V7OutputFolderSelectionResponse(ApiModel):
    status: Literal["selected", "cancelled"]
    path: str | None = None


class SemiAutomaticV7SelectionConfigurationResponse(ApiModel):
    version: Literal["v7-selection-configuration-v1", "v7-selection-configuration-v2"]
    pilot: V7PilotSnapshotResponse | None = None
    mode: SemiAutomaticV7SelectionMode
    direction: SemiAutomaticSelectionDirection
    first_sequence_number: int = Field(ge=1)
    last_sequence_number: int = Field(ge=1)
    border_style: SemiAutomaticV7BorderStyle
    localizer_fingerprint: Sha256
    calibration_fingerprint: Sha256
    output_directory: str | None = None


class SemiAutomaticSelectionCapabilitiesResponse(ApiModel):
    enabled: bool
    filename_verification_enabled: bool
    contract_version: Literal[1]
    range_convention: Literal["seq-inclusive-v1"]
    full_range_size: Literal[9]
    minimum_sequence_number: Literal[1]
    maximum_boards_per_range: Literal[9]
    staging_purpose: Literal["semi_automatic_selection"]
    source_mode: Literal["local_folder"] = "local_folder"
    recognizer_fingerprint: Sha256
    selection_recognizer_variants: list[SemiAutomaticSelectionRecognizerVariantResponse]
    filename_verification_recognizer_fingerprint: Sha256
    grouping_policy_fingerprint: Sha256
    v7: SemiAutomaticV7CapabilitiesResponse


class SemiAutomaticSelectionCreate(ApiModel):
    upload_id: UUID | None = None
    selection_token: str | None = Field(default=None, min_length=32, max_length=200)
    first_sequence_number: int = Field(ge=1)
    last_sequence_number: int = Field(ge=1)
    direction: SemiAutomaticSelectionDirection = SemiAutomaticSelectionDirection.ASCENDING
    mode: Literal["selection", "filename_verification", "v7_selection"] = "selection"
    recognizer_variant: Literal["default_v3", "five_anchor_v6"] = "default_v3"
    v7: SemiAutomaticV7SelectionCreate | None = None


class SequenceRangeValueResponse(ApiModel):
    start: int = Field(ge=1)
    end: int = Field(ge=1)


class FilenameRangeVerificationItemResponse(ApiModel):
    source_index: int = Field(ge=0)
    source_relative_path: str
    source_size_bytes: int = Field(ge=1)
    source_checksum_sha256: Sha256
    expected_range: SequenceRangeValueResponse | None
    observed_range: SequenceRangeValueResponse | None
    anchor_positions: list[int]
    verification_status: Literal["verified", "mismatch", "unreadable", "invalid_filename"]
    reason_codes: list[str]
    review_decision: FilenameRangeVerificationReviewDecision | None = None
    review_revision: int | None = Field(default=None, ge=0)


class FilenameRangeVerificationReviewDecisionUpdate(ApiModel):
    decision: FilenameRangeVerificationReviewDecision
    expected_source_checksum_sha256: Sha256
    expected_revision: int = Field(ge=0)


class FilenameRangeVerificationReviewDecisionResponse(ApiModel):
    run_id: UUID
    source_index: int = Field(ge=0)
    source_checksum_sha256: Sha256
    decision: FilenameRangeVerificationReviewDecision
    revision: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class FilenameVerificationHistoryDeletionResponse(ApiModel):
    run_id: UUID
    job_id: UUID


class FilenameRangeVerificationPageResponse(ApiModel):
    items: list[FilenameRangeVerificationItemResponse]
    next_after_source_index: int | None = Field(default=None, ge=0)


class SemiAutomaticSelectionSourceResponse(ApiModel):
    upload_id: UUID
    display_name: str
    manifest_checksum_sha256: Sha256
    source_fingerprint: Sha256
    source_count: int = Field(ge=1)
    source_total_bytes: int = Field(ge=1)


class SemiAutomaticSelectionSourceItemResponse(ApiModel):
    source_index: int = Field(ge=0)
    relative_path: str = Field(min_length=1)
    size_bytes: int = Field(ge=1)
    checksum_sha256: Sha256
    v7_diagnostics: V7SourceDiagnosticsResponse | None = None


class SemiAutomaticSelectionSourcePageResponse(ApiModel):
    items: list[SemiAutomaticSelectionSourceItemResponse]
    next_after_source_index: int | None = Field(default=None, ge=0)


class SemiAutomaticSelectionRunResponse(ApiModel):
    id: UUID
    output_directory: str | None = None
    game_id: None = None
    job: JobResponse
    source: SemiAutomaticSelectionSourceResponse
    first_sequence_number: int = Field(ge=1)
    last_sequence_number: int = Field(ge=1)
    direction: SemiAutomaticSelectionDirection
    workflow_mode: SemiAutomaticSelectionWorkflowMode | None = None
    v7_configuration: SemiAutomaticV7SelectionConfigurationResponse | None = None
    range_convention: Literal["seq-inclusive-v1"]
    full_range_size: Literal[9]
    expected_ranges_fingerprint: Sha256
    recognizer_fingerprint: Sha256
    grouping_policy_fingerprint: Sha256
    status: SemiAutomaticSelectionRunStatus
    checkpoint: dict[str, object]
    counters: dict[str, int]
    diagnostics_relative_path: str | None
    diagnostics_checksum_sha256: Sha256 | None
    revision: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class SemiAutomaticSelectionCreateResponse(ApiModel):
    run: SemiAutomaticSelectionRunResponse
    created: bool


class SemiAutomaticSelectionRunPageResponse(ApiModel):
    items: list[SemiAutomaticSelectionRunResponse]
    next_offset: int | None = Field(default=None, ge=0)


class V7ReviewFolderResponse(ApiModel):
    status: Literal["selected", "cancelled"]
    run_id: UUID | None = None


class SemiAutomaticSelectionRangeResponse(ApiModel):
    id: UUID
    run_id: UUID
    expected_index: int = Field(ge=0)
    range_start: int = Field(ge=1)
    range_end: int = Field(ge=1)
    file_name: str
    status: SemiAutomaticSelectionRangeStatus
    source_index: int | None = Field(default=None, ge=0)
    source_relative_path: str | None
    source_size_bytes: int | None = Field(default=None, ge=1)
    source_checksum_sha256: Sha256 | None
    group_first_source_index: int | None = Field(default=None, ge=0)
    group_last_source_index: int | None = Field(default=None, ge=0)
    range_confidence: float | None = Field(default=None, ge=0, le=1)
    selection_method: str | None
    output_checksum_sha256: Sha256 | None
    revision: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime
    v7_review: V7ReviewResponse | None = None
    v7_projection_fingerprint: Sha256 | None = None
    v7_confirmed_range: V7ConfirmedRange | None = None
    v7_output_owner_operation_id: UUID | None = None
    v7_output_generation: int | None = Field(default=None, ge=0)
    output_operation: V7OutputOperationResponse | None = None
    acknowledgement_receipt: V7OutputReceiptResponse | None = None


class SemiAutomaticSelectionRangePageResponse(ApiModel):
    items: list[SemiAutomaticSelectionRangeResponse]
    next_after_expected_index: int | None = Field(default=None, ge=0)


class SemiAutomaticSelectionDiagnosticsResponse(ApiModel):
    run_id: UUID
    available: bool
    relative_path: str | None
    checksum_sha256: Sha256 | None
    checkpoint: dict[str, object]
    counters: dict[str, int]


class SemiAutomaticSelectionOutputAcknowledgement(ApiModel):
    expected_revision: int = Field(ge=0)
    expected_source_checksum_sha256: Sha256
    output_checksum_sha256: Sha256
    source_index: int | None = Field(default=None, ge=0)


def to_run_response(
    run: SemiAutomaticSelectionRun, *, output_directory: str | None = None
) -> SemiAutomaticSelectionRunResponse:
    return SemiAutomaticSelectionRunResponse(
        id=run.id,
        output_directory=output_directory,
        game_id=None,
        job=JobResponse.from_domain(run.job),
        source=SemiAutomaticSelectionSourceResponse(
            upload_id=run.source.upload_id,
            display_name=run.source.display_name,
            manifest_checksum_sha256=run.source.manifest_checksum_sha256,
            source_fingerprint=run.source.source_fingerprint,
            source_count=run.source.source_count,
            source_total_bytes=run.source.source_total_bytes,
        ),
        first_sequence_number=run.first_sequence_number,
        last_sequence_number=run.last_sequence_number,
        direction=run.direction,
        workflow_mode=run.workflow_mode,
        v7_configuration=(
            None
            if run.v7_configuration is None
            else SemiAutomaticV7SelectionConfigurationResponse.model_validate(
                run.v7_configuration.as_payload()
            )
        ),
        range_convention="seq-inclusive-v1",
        full_range_size=9,
        expected_ranges_fingerprint=run.expected_ranges_fingerprint,
        recognizer_fingerprint=run.recognizer_fingerprint,
        grouping_policy_fingerprint=run.grouping_policy_fingerprint,
        status=run.status,
        checkpoint=_public_run_checkpoint(run),
        counters=dict(run.counters),
        diagnostics_relative_path=run.diagnostics_relative_path,
        diagnostics_checksum_sha256=run.diagnostics_checksum_sha256,
        revision=run.revision,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def _public_run_checkpoint(run: SemiAutomaticSelectionRun) -> dict[str, object]:
    """Keep recovery data private; detailed V7 reads use the paged endpoints."""
    if run.workflow_mode is not SemiAutomaticSelectionWorkflowMode.V7_SELECTION:
        return dict(run.checkpoint)
    result: dict[str, object] = {}
    for key in (
        "schemaVersion",
        "runtimeVersion",
        "localizerFingerprint",
        "calibrationFingerprint",
        "v7ProjectionFingerprint",
    ):
        value = run.checkpoint.get(key)
        if isinstance(value, str) and len(value) <= 512:
            result[key] = value
    scan = run.checkpoint.get("scanState")
    if isinstance(scan, dict):
        result["scanState"] = {
            key: value
            for key in ("schemaVersion", "phase")
            if isinstance(value := scan.get(key), str) and len(value) <= 512
        }
    return result


def to_filename_verification_review_response(
    review: FilenameRangeVerificationReview,
) -> FilenameRangeVerificationReviewDecisionResponse:
    return FilenameRangeVerificationReviewDecisionResponse(
        run_id=review.run_id,
        source_index=review.source_index,
        source_checksum_sha256=review.source_checksum_sha256,
        decision=review.decision,
        revision=review.revision,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


def to_filename_verification_history_deletion_response(
    deletion: FilenameVerificationHistoryDeletion,
) -> FilenameVerificationHistoryDeletionResponse:
    return FilenameVerificationHistoryDeletionResponse(
        run_id=deletion.run_id,
        job_id=deletion.job_id,
    )


def to_range_response(
    item: SemiAutomaticSelectionRange,
) -> SemiAutomaticSelectionRangeResponse:
    return SemiAutomaticSelectionRangeResponse(
        id=item.id,
        run_id=item.run_id,
        expected_index=item.expected_index,
        range_start=item.range_start,
        range_end=item.range_end,
        file_name=(
            f"seq_{item.v7_confirmed_range_start}-{item.v7_confirmed_range_end}.jpg"
            if item.v7_confirmed_range_start is not None
            else f"seq_{item.range_start}-{item.range_end}.jpg"
        ),
        status=item.status,
        source_index=item.source_index,
        source_relative_path=item.source_relative_path,
        source_size_bytes=item.source_size_bytes,
        source_checksum_sha256=item.source_checksum_sha256,
        group_first_source_index=item.group_first_source_index,
        group_last_source_index=item.group_last_source_index,
        range_confidence=item.range_confidence,
        selection_method=item.selection_method,
        output_checksum_sha256=item.output_checksum_sha256,
        revision=item.revision,
        created_at=item.created_at,
        updated_at=item.updated_at,
        v7_review=None
        if item.v7_review is None
        else V7ReviewResponse.model_validate(item.v7_review),
        v7_projection_fingerprint=item.v7_projection_fingerprint,
        v7_confirmed_range=(
            None
            if item.v7_confirmed_range_start is None or item.v7_confirmed_range_end is None
            else V7ConfirmedRange(
                start=item.v7_confirmed_range_start, end=item.v7_confirmed_range_end
            )
        ),
        v7_output_owner_operation_id=item.v7_output_owner_operation_id,
        v7_output_generation=item.v7_output_generation,
        output_operation=(
            None
            if item.output_operation is None
            else V7OutputOperationResponse.model_validate(item.output_operation)
        ),
        acknowledgement_receipt=(
            None
            if item.acknowledgement_receipt is None
            else V7OutputReceiptResponse.model_validate(item.acknowledgement_receipt)
        ),
    )


__all__ = [
    "FilenameRangeVerificationItemResponse",
    "FilenameRangeVerificationPageResponse",
    "FilenameRangeVerificationReviewDecisionResponse",
    "FilenameRangeVerificationReviewDecisionUpdate",
    "FilenameVerificationHistoryDeletionResponse",
    "SemiAutomaticSelectionCapabilitiesResponse",
    "SemiAutomaticSelectionCreate",
    "SemiAutomaticSelectionCreateResponse",
    "SemiAutomaticSelectionDiagnosticsResponse",
    "SemiAutomaticSelectionOutputAcknowledgement",
    "SemiAutomaticSelectionRangePageResponse",
    "SemiAutomaticSelectionRangeResponse",
    "SemiAutomaticSelectionRunResponse",
    "SemiAutomaticSelectionRunPageResponse",
    "to_filename_verification_review_response",
    "to_filename_verification_history_deletion_response",
    "to_range_response",
    "to_run_response",
]
