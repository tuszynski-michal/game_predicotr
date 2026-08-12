"""OpenAPI schemas for durable symbol model training."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from game_predictor_api.domain.symbol_model_iterations import SymbolModelIteration
from game_predictor_api.domain.symbol_model_registry import (
    SymbolModelActivation,
    SymbolModelActivationPreview,
)
from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.schemas.jobs import JobResponse


class SymbolTrainingConfigurationCommand(ApiModel):
    epochs: int = Field(default=40, ge=1, le=500)
    batch_size: int = Field(default=32, ge=1, le=1024)
    learning_rate: float = Field(default=0.001, gt=0, le=1)
    weight_decay: float = Field(default=0.0001, ge=0, le=1)
    seed: int = Field(default=61061, ge=0)
    input_size: int = Field(default=64, ge=16, le=512)


class CreateSymbolTrainingCommand(ApiModel):
    cohort_id: UUID
    idempotency_key: UUID
    configuration: SymbolTrainingConfigurationCommand = Field(
        default_factory=SymbolTrainingConfigurationCommand
    )


class SymbolModelIterationResponse(ApiModel):
    id: UUID
    game_id: UUID
    cohort_id: UUID
    job_id: UUID
    iteration_number: int
    status: str
    configuration_fingerprint: str
    configuration: dict[str, object]
    dataset_manifest_checksum_sha256: str | None
    dataset_manifest_relative_path: str | None
    checkpoint_checksum_sha256: str | None
    checkpoint_relative_path: str | None
    gate_configuration_fingerprint: str | None
    gate_configuration: dict[str, object] | None
    candidate_manifest_checksum_sha256: str | None
    candidate_manifest_relative_path: str | None
    gate_report_checksum_sha256: str | None
    gate_report_relative_path: str | None
    gate_metrics: dict[str, object]
    rejection_reasons: list[str]
    last_completed_epoch: int
    partial_metrics: dict[str, object]
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class CreateSymbolTrainingResponse(ApiModel):
    iteration: SymbolModelIterationResponse
    job: JobResponse
    created: bool


class SymbolModelActivationCommand(ApiModel):
    expected_manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_current_model_iteration_id: UUID | None = None
    idempotency_key: UUID
    actor: str = Field(min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=2000)


class SymbolModelActivationPreviewResponse(ApiModel):
    game_id: UUID
    model_iteration_id: UUID
    candidate_manifest_checksum_sha256: str
    current_model_iteration_id: UUID | None
    action: str
    can_activate: bool


class SymbolModelActivationResponse(ApiModel):
    id: UUID
    game_id: UUID
    model_iteration_id: UUID
    previous_model_iteration_id: UUID | None
    action: str
    activation_number: int
    actor: str
    reason: str | None
    idempotency_key: UUID
    created_at: datetime


class SymbolModelActivationCommandResponse(ApiModel):
    activation: SymbolModelActivationResponse
    created: bool


def to_iteration_response(value: SymbolModelIteration) -> SymbolModelIterationResponse:
    return SymbolModelIterationResponse(
        id=value.id,
        game_id=value.game_id,
        cohort_id=value.cohort_id,
        job_id=value.job_id,
        iteration_number=value.iteration_number,
        status=value.status.value,
        configuration_fingerprint=value.configuration_fingerprint,
        configuration=value.configuration_payload,
        dataset_manifest_checksum_sha256=value.dataset_manifest_checksum_sha256,
        dataset_manifest_relative_path=value.dataset_manifest_relative_path,
        checkpoint_checksum_sha256=value.checkpoint_checksum_sha256,
        checkpoint_relative_path=value.checkpoint_relative_path,
        gate_configuration_fingerprint=value.gate_configuration_fingerprint,
        gate_configuration=value.gate_configuration_payload,
        candidate_manifest_checksum_sha256=value.candidate_manifest_checksum_sha256,
        candidate_manifest_relative_path=value.candidate_manifest_relative_path,
        gate_report_checksum_sha256=value.gate_report_checksum_sha256,
        gate_report_relative_path=value.gate_report_relative_path,
        gate_metrics=value.gate_metrics,
        rejection_reasons=list(value.rejection_reasons),
        last_completed_epoch=value.last_completed_epoch,
        partial_metrics=value.partial_metrics,
        error_code=value.error_code,
        error_message=value.error_message,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


def to_activation_preview_response(
    value: SymbolModelActivationPreview,
) -> SymbolModelActivationPreviewResponse:
    return SymbolModelActivationPreviewResponse(
        game_id=value.game_id,
        model_iteration_id=value.model_iteration_id,
        candidate_manifest_checksum_sha256=value.candidate_manifest_checksum_sha256,
        current_model_iteration_id=value.current_model_iteration_id,
        action=value.action.value,
        can_activate=value.can_activate,
    )


def to_activation_response(value: SymbolModelActivation) -> SymbolModelActivationResponse:
    return SymbolModelActivationResponse(
        id=value.id,
        game_id=value.game_id,
        model_iteration_id=value.model_iteration_id,
        previous_model_iteration_id=value.previous_model_iteration_id,
        action=value.action.value,
        activation_number=value.activation_number,
        actor=value.actor,
        reason=value.reason,
        idempotency_key=value.idempotency_key,
        created_at=value.created_at,
    )


__all__ = [
    "CreateSymbolTrainingCommand",
    "CreateSymbolTrainingResponse",
    "SymbolModelActivationCommand",
    "SymbolModelActivationCommandResponse",
    "SymbolModelActivationPreviewResponse",
    "SymbolModelActivationResponse",
    "SymbolModelIterationResponse",
    "to_iteration_response",
    "to_activation_preview_response",
    "to_activation_response",
]
