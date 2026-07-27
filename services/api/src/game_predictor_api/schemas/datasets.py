"""OpenAPI schemas for dataset staging."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from game_predictor_api.domain.datasets import (
    MAX_GENERATOR_SEED,
    DatasetValidationCheckCode,
    DatasetValidationCheckStatus,
    DatasetVersionStatus,
)
from game_predictor_api.schemas.catalog import ApiModel


class MockDatasetCreate(ApiModel):
    rules_version_id: UUID
    seed: int = Field(ge=0, le=MAX_GENERATOR_SEED)


class DatasetVersionResponse(ApiModel):
    id: UUID
    game_id: UUID
    version: int
    rows: int
    columns: int
    signature_cell_width: int
    layout_count: int
    status: DatasetVersionStatus
    generation_seed: int
    generator_version: str
    source_job_id: UUID | None
    created_at: datetime
    published_at: datetime | None


class DatasetValidationCheckResponse(ApiModel):
    code: DatasetValidationCheckCode
    status: DatasetValidationCheckStatus
    issue_count: int
    message: str
    sequence_numbers: tuple[int, ...]
    mobile_codes: tuple[int, ...]
    truncated: bool


class DuplicateSignatureGroupResponse(ApiModel):
    signature: str
    occurrence_count: int
    sequence_numbers: tuple[int, ...]
    truncated: bool


class DatasetValidationReportResponse(ApiModel):
    dataset_version_id: UUID
    dataset_version: int
    ready_for_publication: bool
    declared_layout_count: int
    actual_layout_count: int
    min_sequence_number: int | None
    max_sequence_number: int | None
    checks: tuple[DatasetValidationCheckResponse, ...]
    duplicate_signature_group_count: int
    duplicate_signature_affected_layout_count: int
    duplicate_signature_excess_layout_count: int
    duplicate_signatures: tuple[DuplicateSignatureGroupResponse, ...]
    duplicate_signatures_truncated: bool
