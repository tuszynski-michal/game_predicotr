"""OpenAPI schemas for versioned grid calibration."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from game_predictor_api.domain.grid_calibration import (
    GeometryCohort,
    GeometryCohortDiagnostics,
    GridCalibrationProfile,
    GridProfileActivation,
    GridProfileActivationPreview,
)
from game_predictor_api.schemas.catalog import ApiModel


class GeometryCohortResponse(ApiModel):
    id: UUID
    game_id: UUID
    cohort_number: int
    manifest_checksum_sha256: str
    sample_count: int
    source_image_count: int
    training_count: int
    validation_count: int
    created_at: datetime


class GridCalibrationProfileResponse(ApiModel):
    id: UUID
    game_id: UUID
    cohort_id: UUID
    profile_number: int
    status: str
    profile_checksum_sha256: str
    gate_metrics: dict[str, object]
    rejection_reasons: list[str]
    created_at: datetime


class CreateGridCalibrationCandidateResponse(ApiModel):
    cohort: GeometryCohortResponse
    profile: GridCalibrationProfileResponse
    created: bool


class GridEndToEndGateSource(ApiModel):
    source_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    quality_angle_bucket: str = Field(min_length=1, max_length=100)
    active_board_count: int = Field(ge=0)


class GridEndToEndGateReportCommand(ApiModel):
    schema_version: Literal["grid-profile-end-to-end-gate-report-v1"]
    policy_version: Literal["v0.10-page-and-cell-production-gate-v1"]
    cohort_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    corpus_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_count: int = Field(ge=0)
    active_board_count: int = Field(ge=0)
    page_registration_ready_board_count: int = Field(ge=0)
    final_cell_grid_ready_board_count: int = Field(ge=0)
    baseline_final_cell_grid_ready_board_count: int = Field(ge=0)
    quality_angle_bucket_counts: dict[str, int]
    invariant_violation_counts: dict[str, int]
    deferral_reason_counts: dict[str, int]
    known_regression_case_count: int = Field(ge=0)
    covered_regression_case_count: int = Field(ge=0)
    regression_corpus_version: str = Field(min_length=1, max_length=200)
    sources: list[GridEndToEndGateSource]

    @model_validator(mode="after")
    def validate_non_negative_counts(self) -> GridEndToEndGateReportCommand:
        mappings = (
            self.quality_angle_bucket_counts,
            self.invariant_violation_counts,
            self.deferral_reason_counts,
        )
        if any(not key or value < 0 for mapping in mappings for key, value in mapping.items()):
            raise ValueError("Gate counter maps require non-empty keys and non-negative values.")
        return self


class CreateGridCalibrationCandidateCommand(ApiModel):
    end_to_end_report: GridEndToEndGateReportCommand | None = None


class GeometryCohortDiagnosticsResponse(ApiModel):
    game_id: UUID
    accepted_geometry_count: int = Field(ge=0)
    corrected_geometry_count: int = Field(ge=0)
    missing_detection_count: int = Field(ge=0)
    incomplete_geometry_count: int = Field(ge=0)
    source_image_count: int = Field(ge=0)
    first_sequence_number: int | None = Field(default=None, ge=1)
    last_sequence_number: int | None = Field(default=None, ge=1)
    eligible_geometry_count: int = Field(default=0, ge=0)
    excluded_geometry_count: int = Field(default=0, ge=0)
    exclusion_reason_counts: dict[str, int] = Field(default_factory=dict)


class GridProfileActivationCommand(ApiModel):
    expected_profile_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_current_profile_id: UUID | None = None
    idempotency_key: UUID
    actor: str = Field(min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=2000)


class GridProfileActivationPreviewResponse(ApiModel):
    game_id: UUID
    profile_id: UUID
    profile_checksum_sha256: str
    current_profile_id: UUID | None
    action: str
    can_activate: bool


class GridProfileActivationResponse(ApiModel):
    id: UUID
    game_id: UUID
    profile_id: UUID
    previous_profile_id: UUID | None
    action: str
    activation_number: int
    actor: str
    reason: str | None
    idempotency_key: UUID
    created_at: datetime


class GridProfileActivationCommandResponse(ApiModel):
    activation: GridProfileActivationResponse
    created: bool


def to_cohort_response(value: GeometryCohort) -> GeometryCohortResponse:
    return GeometryCohortResponse(
        id=value.id,
        game_id=value.game_id,
        cohort_number=value.cohort_number,
        manifest_checksum_sha256=value.manifest_checksum_sha256,
        sample_count=value.sample_count,
        source_image_count=value.source_image_count,
        training_count=value.training_count,
        validation_count=value.validation_count,
        created_at=value.created_at,
    )


def to_diagnostics_response(
    value: GeometryCohortDiagnostics,
) -> GeometryCohortDiagnosticsResponse:
    return GeometryCohortDiagnosticsResponse(
        game_id=value.game_id,
        accepted_geometry_count=value.accepted_geometry_count,
        corrected_geometry_count=value.corrected_geometry_count,
        missing_detection_count=value.missing_detection_count,
        incomplete_geometry_count=value.incomplete_geometry_count,
        source_image_count=value.source_image_count,
        first_sequence_number=value.first_sequence_number,
        last_sequence_number=value.last_sequence_number,
        eligible_geometry_count=value.eligible_geometry_count,
        excluded_geometry_count=value.excluded_geometry_count,
        exclusion_reason_counts=dict(value.exclusion_reason_counts),
    )


def to_profile_response(value: GridCalibrationProfile) -> GridCalibrationProfileResponse:
    return GridCalibrationProfileResponse(
        id=value.id,
        game_id=value.game_id,
        cohort_id=value.cohort_id,
        profile_number=value.profile_number,
        status=value.status.value,
        profile_checksum_sha256=value.profile_checksum_sha256,
        gate_metrics=value.gate_metrics,
        rejection_reasons=list(value.rejection_reasons),
        created_at=value.created_at,
    )


def to_activation_preview_response(
    value: GridProfileActivationPreview,
) -> GridProfileActivationPreviewResponse:
    return GridProfileActivationPreviewResponse(
        game_id=value.game_id,
        profile_id=value.profile_id,
        profile_checksum_sha256=value.profile_checksum_sha256,
        current_profile_id=value.current_profile_id,
        action=value.action.value,
        can_activate=value.can_activate,
    )


def to_activation_response(value: GridProfileActivation) -> GridProfileActivationResponse:
    return GridProfileActivationResponse(
        id=value.id,
        game_id=value.game_id,
        profile_id=value.profile_id,
        previous_profile_id=value.previous_profile_id,
        action=value.action.value,
        activation_number=value.activation_number,
        actor=value.actor,
        reason=value.reason,
        idempotency_key=value.idempotency_key,
        created_at=value.created_at,
    )


__all__ = [
    "CreateGridCalibrationCandidateResponse",
    "CreateGridCalibrationCandidateCommand",
    "GeometryCohortDiagnosticsResponse",
    "GridCalibrationProfileResponse",
    "GridEndToEndGateReportCommand",
    "GridProfileActivationCommand",
    "GridProfileActivationCommandResponse",
    "GridProfileActivationPreviewResponse",
    "GridProfileActivationResponse",
    "to_activation_preview_response",
    "to_activation_response",
    "to_cohort_response",
    "to_diagnostics_response",
    "to_profile_response",
]
