"""OpenAPI contracts for global semi-automatic image-selection runs."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from game_predictor_api.domain.semi_automatic_image_selections import (
    SemiAutomaticSelectionDirection,
    SemiAutomaticSelectionRange,
    SemiAutomaticSelectionRangeStatus,
    SemiAutomaticSelectionRun,
    SemiAutomaticSelectionRunStatus,
)
from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.schemas.jobs import JobResponse

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class SemiAutomaticSelectionCapabilitiesResponse(ApiModel):
    enabled: bool
    filename_verification_enabled: bool
    contract_version: Literal[1]
    range_convention: Literal["seq-inclusive-v1"]
    full_range_size: Literal[9]
    minimum_sequence_number: Literal[1]
    maximum_boards_per_range: Literal[9]
    staging_purpose: Literal["semi_automatic_selection"]
    recognizer_fingerprint: Sha256
    filename_verification_recognizer_fingerprint: Sha256
    grouping_policy_fingerprint: Sha256


class SemiAutomaticSelectionCreate(ApiModel):
    upload_id: UUID
    first_sequence_number: int = Field(ge=1)
    last_sequence_number: int = Field(ge=1)
    direction: SemiAutomaticSelectionDirection = SemiAutomaticSelectionDirection.ASCENDING
    mode: Literal["selection", "filename_verification"] = "selection"


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


class SemiAutomaticSelectionRunResponse(ApiModel):
    id: UUID
    game_id: None = None
    job: JobResponse
    source: SemiAutomaticSelectionSourceResponse
    first_sequence_number: int = Field(ge=1)
    last_sequence_number: int = Field(ge=1)
    direction: SemiAutomaticSelectionDirection
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


def to_run_response(run: SemiAutomaticSelectionRun) -> SemiAutomaticSelectionRunResponse:
    return SemiAutomaticSelectionRunResponse(
        id=run.id,
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
        range_convention="seq-inclusive-v1",
        full_range_size=9,
        expected_ranges_fingerprint=run.expected_ranges_fingerprint,
        recognizer_fingerprint=run.recognizer_fingerprint,
        grouping_policy_fingerprint=run.grouping_policy_fingerprint,
        status=run.status,
        checkpoint=dict(run.checkpoint),
        counters=dict(run.counters),
        diagnostics_relative_path=run.diagnostics_relative_path,
        diagnostics_checksum_sha256=run.diagnostics_checksum_sha256,
        revision=run.revision,
        created_at=run.created_at,
        updated_at=run.updated_at,
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
        file_name=f"seq_{item.range_start}-{item.range_end}.jpg",
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
    )


__all__ = [
    "FilenameRangeVerificationItemResponse",
    "FilenameRangeVerificationPageResponse",
    "SemiAutomaticSelectionCapabilitiesResponse",
    "SemiAutomaticSelectionCreate",
    "SemiAutomaticSelectionCreateResponse",
    "SemiAutomaticSelectionDiagnosticsResponse",
    "SemiAutomaticSelectionOutputAcknowledgement",
    "SemiAutomaticSelectionRangePageResponse",
    "SemiAutomaticSelectionRangeResponse",
    "SemiAutomaticSelectionRunResponse",
    "to_range_response",
    "to_run_response",
]
