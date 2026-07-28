"""OpenAPI schemas for normalized layout import integrity reports."""

from __future__ import annotations

from uuid import UUID

from game_predictor_api.domain.layout_import_reports import (
    LayoutImportIntegrityCheckCode,
    LayoutImportIntegrityCheckStatus,
)
from game_predictor_api.schemas.catalog import ApiModel


class LayoutImportIntegrityCheckResponse(ApiModel):
    code: LayoutImportIntegrityCheckCode
    status: LayoutImportIntegrityCheckStatus
    issue_count: int
    message: str
    sequence_numbers: tuple[int, ...]
    line_numbers: tuple[int, ...]
    truncated: bool


class LayoutImportDuplicateSequenceGroupResponse(ApiModel):
    sequence_number: int
    occurrence_count: int
    line_numbers: tuple[int, ...]
    truncated: bool


class LayoutImportDuplicateSignatureGroupResponse(ApiModel):
    signature: str
    occurrence_count: int
    sequence_numbers: tuple[int, ...]
    line_numbers: tuple[int, ...]
    sequence_numbers_truncated: bool
    line_numbers_truncated: bool


class LayoutImportErrorCodeCountResponse(ApiModel):
    code: str
    count: int


class LayoutImportIntegrityReportResponse(ApiModel):
    validation_job_id: UUID
    import_job_id: UUID
    rules_version_id: UUID
    rows: int
    columns: int
    ready_for_publication: bool
    expected_row_count: int | None
    actual_row_count: int
    valid_row_count: int
    invalid_row_count: int
    min_sequence_number: int | None
    max_sequence_number: int | None
    unique_sequence_count: int
    checks: tuple[LayoutImportIntegrityCheckResponse, ...]
    missing_sequence_count: int
    missing_sequence_numbers: tuple[int, ...]
    missing_sequence_numbers_truncated: bool
    duplicate_sequence_group_count: int
    duplicate_sequence_affected_row_count: int
    duplicate_sequence_excess_row_count: int
    duplicate_sequences: tuple[
        LayoutImportDuplicateSequenceGroupResponse,
        ...,
    ]
    duplicate_sequences_truncated: bool
    duplicate_signature_group_count: int
    duplicate_signature_affected_row_count: int
    duplicate_signature_excess_row_count: int
    duplicate_signatures: tuple[
        LayoutImportDuplicateSignatureGroupResponse,
        ...,
    ]
    duplicate_signatures_truncated: bool
    error_code_counts: tuple[LayoutImportErrorCodeCountResponse, ...]


class LayoutImportNormalizedRowResponse(ApiModel):
    line_number: int
    sequence_number: int | None
    cells: tuple[int, ...] | None
    signature: str | None
    error_code: str | None
    error_message: str | None


class LayoutImportNormalizedRowPageResponse(ApiModel):
    validation_job_id: UUID
    import_job_id: UUID
    rules_version_id: UUID
    rows: int
    columns: int
    items: tuple[LayoutImportNormalizedRowResponse, ...]
    next_after_line_number: int | None


class LayoutImportStagingRejectionResponse(ApiModel):
    validation_job_id: UUID
    import_job_id: UUID
    deleted_normalized_row_count: int
    deleted_raw_row_count: int
