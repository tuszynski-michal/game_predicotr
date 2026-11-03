"""Typed source-selection and exact planned-manifest API."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from game_predictor_api.schemas.catalog import ApiModel


class SourceReplacementPreviewRequest(ApiModel):
    mode: Literal["replace_preserve_history"]
    source_ids: list[UUID] = Field(min_length=1, max_length=50)


class SourceReplacementCreateRequest(SourceReplacementPreviewRequest):
    idempotency_key: UUID
    expected_revision: int = Field(ge=0)
    preview_token: str = Field(pattern="^[0-9a-f]{64}$")


class SourceReplacementEntryResponse(ApiModel):
    id: UUID | None = None
    phase: str = "planned"
    revision: int = 0
    scope_digest: str | None = None
    failure_code: str | None = None
    source_ids: list[UUID]
    source_sha256: str
    range_start: int | None
    range_end: int | None
    sequence_numbers: list[int]
    sources: list[dict[str, Any]]
    geometry_revisions: list[dict[str, Any]]
    boards: list[dict[str, Any]]
    pending_slots: list[dict[str, Any]]
    canonical: list[dict[str, Any]]
    pending: list[dict[str, Any]]
    reservations: list[dict[str, Any]]
    retired: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    reasons: list[dict[str, Any]]
    dependencies: dict[str, list[dict[str, Any]]]
    blockers: list[str]


class SourceReplacementManifestResponse(ApiModel):
    schema_version: Literal["source-replacement-manifest-v1"]
    mode: Literal["replace_preserve_history"]
    game_id: UUID
    id: UUID | None = None
    selected_source_ids: list[UUID]
    entries: list[SourceReplacementEntryResponse]
    revision: int
    status: str
    retirement_available: bool = False
    preview_token: str


class SourceReplacementCandidateResponse(ApiModel):
    id: UUID
    checksum_sha256: str
    relative_path: str
    first_sequence: int | None
    last_sequence: int | None


class SourceReplacementCandidatePage(ApiModel):
    items: list[SourceReplacementCandidateResponse]
    next_offset: int | None


class SourceReplacementBatchResponse(ApiModel):
    id: UUID
    revision: int
    status: str
    preview_token: str
    created_at: datetime


class SourceRetirementPreviewRequest(ApiModel):
    mode: Literal["replace_preserve_history"]
    action: Literal["retire"]
    batch_id: UUID
    entry_id: UUID
    expected_revision: int = Field(ge=1)


class SourceRetirementCommand(ApiModel):
    mode: Literal["replace_preserve_history"]
    action: Literal["retire", "cancel"]
    batch_id: UUID
    entry_id: UUID
    expected_revision: int = Field(ge=1)
    idempotency_key: UUID
    confirmed: Literal[True]
    preview_token: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")


class SourceRetirementPreviewResponse(ApiModel):
    game_id: UUID
    batch_id: UUID
    entry_id: UUID
    revision: int
    action: Literal["retire"]
    preview_token: str
    entry: SourceReplacementEntryResponse


class SourceRetirementResult(ApiModel):
    game_id: UUID
    batch_id: UUID
    entry_id: UUID
    revision: int
    phase: Literal["gap_open", "cancelled"]
    scope_digest: str
    created_derivations: list[dict[str, Any]] = Field(default_factory=list)


class ReplacementRequestEntry(ApiModel):
    entry_id: UUID
    revision: int = Field(ge=1)
    digest: str = Field(pattern="^[0-9a-f]{64}$")
    source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    sequence_numbers: list[int]


class ReplacementAllowedRange(ApiModel):
    entry_id: UUID
    sequence_start: int = Field(ge=1)
    sequence_end: int = Field(ge=1)


class SourceReplacementRequestExport(ApiModel):
    schema_version: Literal["source-replacement-request-v1"]
    game_id: UUID
    batch_id: UUID
    entries: list[ReplacementRequestEntry]
    allowed_ranges: list[ReplacementAllowedRange]
    digest: str = Field(pattern="^[0-9a-f]{64}$")


class SourceReplacementStagingFile(ApiModel):
    entry_id: UUID
    file_name: str = Field(min_length=1, max_length=1000)
    checksum_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    range_start: int = Field(ge=1)
    range_end: int = Field(ge=1)
    operation_id: str = Field(min_length=1, max_length=200)


class SourceReplacementStagingSelection(ApiModel):
    request: SourceReplacementRequestExport
    selected_entry_ids: list[UUID] = Field(min_length=1, max_length=50)
    files: list[SourceReplacementStagingFile] = Field(min_length=1, max_length=50)


class SourceReplacementWorkingSlot(ApiModel):
    sequence_number: int
    review_item_id: UUID | None
    pending_geometry_id: UUID | None
    status: str
    canonical: bool


class SourceReplacementReadabilityCell(ApiModel):
    cell_id: UUID
    review_item_id: UUID
    sequence_number: int
    cell_index: int = Field(ge=0, lt=15)
    identity: str
    revision: int = Field(ge=0)


class SourceReplacementWorkingResponse(ApiModel):
    game_id: UUID
    batch_id: UUID
    entry_id: UUID
    revision: int
    phase: str
    source_id: UUID | None
    import_job_id: UUID | None
    slots: list[SourceReplacementWorkingSlot]
    readability: list[SourceReplacementReadabilityCell]
    ready_to_restore: bool


class SourceReplacementReadabilityConfirmation(ApiModel):
    cell_id: UUID
    identity: str
    revision: int = Field(ge=0)
    readable: Literal[True]


class SourceReplacementRestoreCommand(ApiModel):
    batch_id: UUID
    entry_id: UUID
    expected_revision: int = Field(ge=1)
    idempotency_key: UUID
    confirmed: Literal[True]
    actor: str = Field(min_length=1, max_length=200)
    readability: list[SourceReplacementReadabilityConfirmation] = Field(max_length=150)


class SourceReplacementRestoreResponse(ApiModel):
    game_id: UUID
    batch_id: UUID
    entry_id: UUID
    revision: int
    phase: Literal["restored"]
    source_id: UUID
