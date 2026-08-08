"""OpenAPI schemas for cumulative verified training cohorts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import Field

from game_predictor_api.domain.verified_training_cohorts import (
    ModelQualitySummary,
    VerifiedTrainingCohort,
    VerifiedTrainingCohortSource,
)
from game_predictor_api.schemas.catalog import ApiModel

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class VerifiedTrainingCohortFreezeCommand(ApiModel):
    idempotency_key: UUID
    created_by: str = Field(min_length=1, max_length=200)
    expected_manifest_checksum_sha256: Sha256


class VerifiedTrainingCohortPreviewResponse(ApiModel):
    game_id: UUID
    manifest_schema_version: int = Field(ge=1)
    manifest_checksum_sha256: Sha256
    resolved_layout_count: int = Field(ge=0)
    cell_sample_count: int = Field(ge=0)
    source_image_count: int = Field(ge=0)
    pending_item_count: int = Field(ge=0)
    rejected_item_count: int = Field(ge=0)
    incomplete_item_count: int = Field(ge=0)
    protected_item_count: int = Field(ge=0)
    warnings: list[str]


class SymbolTrainingCoverageResponse(ApiModel):
    symbol_code: str
    sample_count: int = Field(ge=0)


class ModelQualityAdvisoryThresholdResponse(ApiModel):
    layout_count: int = Field(ge=1)
    reached: bool


class ActiveSymbolModelResponse(ApiModel):
    version: str
    checksum_sha256: Sha256


class VerifiedTrainingCohortResponse(ApiModel):
    id: UUID
    game_id: UUID
    iteration_number: int = Field(ge=1)
    manifest_schema_version: int = Field(ge=1)
    manifest_checksum_sha256: Sha256
    resolved_layout_count: int = Field(ge=1)
    cell_sample_count: int = Field(ge=15)
    source_image_count: int = Field(ge=1)
    pending_item_count: int = Field(ge=0)
    rejected_item_count: int = Field(ge=0)
    incomplete_item_count: int = Field(ge=0)
    artifact_relative_path: str
    created_by: str
    created_at: datetime


class VerifiedTrainingCohortFreezeResponse(ApiModel):
    cohort: VerifiedTrainingCohortResponse
    created: bool


class ModelQualityResponse(ApiModel):
    game_id: UUID
    active_model: ActiveSymbolModelResponse | None
    latest_cohort: VerifiedTrainingCohortResponse | None
    manifest_checksum_sha256: Sha256
    resolved_layout_count: int = Field(ge=0)
    new_verified_layout_count: int = Field(ge=0)
    cell_sample_count: int = Field(ge=0)
    source_image_count: int = Field(ge=0)
    pending_item_count: int = Field(ge=0)
    rejected_item_count: int = Field(ge=0)
    incomplete_item_count: int = Field(ge=0)
    protected_item_count: int = Field(ge=0)
    symbol_coverage: list[SymbolTrainingCoverageResponse]
    advisory_thresholds: list[ModelQualityAdvisoryThresholdResponse]
    warnings: list[str]
    active_heavy_job: bool
    can_freeze: bool


def to_preview_response(
    value: VerifiedTrainingCohortSource,
) -> VerifiedTrainingCohortPreviewResponse:
    return VerifiedTrainingCohortPreviewResponse(
        game_id=value.game_id,
        manifest_schema_version=1,
        manifest_checksum_sha256=value.manifest_checksum_sha256,
        resolved_layout_count=value.resolved_layout_count,
        cell_sample_count=value.cell_sample_count,
        source_image_count=value.source_image_count,
        pending_item_count=value.pending_item_count,
        rejected_item_count=value.rejected_item_count,
        incomplete_item_count=value.incomplete_item_count,
        protected_item_count=(
            value.resolved_layout_count + value.rejected_item_count + value.incomplete_item_count
        ),
        warnings=list(value.warnings),
    )


def to_model_quality_response(value: ModelQualitySummary) -> ModelQualityResponse:
    active_model = None
    if value.active_model_version is not None and value.active_model_checksum_sha256 is not None:
        active_model = ActiveSymbolModelResponse(
            version=value.active_model_version,
            checksum_sha256=value.active_model_checksum_sha256,
        )
    return ModelQualityResponse(
        game_id=value.game_id,
        active_model=active_model,
        latest_cohort=(
            None if value.latest_cohort is None else to_cohort_response(value.latest_cohort)
        ),
        manifest_checksum_sha256=value.manifest_checksum_sha256,
        resolved_layout_count=value.resolved_layout_count,
        new_verified_layout_count=value.new_verified_layout_count,
        cell_sample_count=value.cell_sample_count,
        source_image_count=value.source_image_count,
        pending_item_count=value.pending_item_count,
        rejected_item_count=value.rejected_item_count,
        incomplete_item_count=value.incomplete_item_count,
        protected_item_count=value.protected_item_count,
        symbol_coverage=[
            SymbolTrainingCoverageResponse(
                symbol_code=coverage.symbol_code,
                sample_count=coverage.sample_count,
            )
            for coverage in value.symbol_coverage
        ],
        advisory_thresholds=[
            ModelQualityAdvisoryThresholdResponse(
                layout_count=threshold.layout_count,
                reached=threshold.reached,
            )
            for threshold in value.advisory_thresholds
        ],
        warnings=list(value.warnings),
        active_heavy_job=value.active_heavy_job,
        can_freeze=value.can_freeze,
    )


def to_cohort_response(
    value: VerifiedTrainingCohort,
) -> VerifiedTrainingCohortResponse:
    return VerifiedTrainingCohortResponse(
        id=value.id,
        game_id=value.game_id,
        iteration_number=value.iteration_number,
        manifest_schema_version=value.manifest_schema_version,
        manifest_checksum_sha256=value.manifest_checksum_sha256,
        resolved_layout_count=value.resolved_layout_count,
        cell_sample_count=value.cell_sample_count,
        source_image_count=value.source_image_count,
        pending_item_count=value.pending_item_count,
        rejected_item_count=value.rejected_item_count,
        incomplete_item_count=value.incomplete_item_count,
        artifact_relative_path=value.artifact_relative_path,
        created_by=value.created_by,
        created_at=value.created_at,
    )


__all__ = [
    "ActiveSymbolModelResponse",
    "ModelQualityAdvisoryThresholdResponse",
    "ModelQualityResponse",
    "SymbolTrainingCoverageResponse",
    "VerifiedTrainingCohortFreezeCommand",
    "VerifiedTrainingCohortFreezeResponse",
    "VerifiedTrainingCohortPreviewResponse",
    "VerifiedTrainingCohortResponse",
    "to_cohort_response",
    "to_model_quality_response",
    "to_preview_response",
]
