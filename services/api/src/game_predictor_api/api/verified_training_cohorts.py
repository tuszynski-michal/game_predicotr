"""Admin API for previewing and freezing cumulative training cohorts."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from game_predictor_api.application.verified_training_cohorts import (
    VerifiedTrainingCohortService,
)
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.verified_training_cohorts import (
    ModelQualityResponse,
    VerifiedTrainingCohortFreezeCommand,
    VerifiedTrainingCohortFreezeResponse,
    VerifiedTrainingCohortPreviewResponse,
    to_cohort_response,
    to_model_quality_response,
    to_preview_response,
)

VerifiedTrainingCohortServiceDependency = Callable[..., object]
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Training cohort resource not found"},
    409: {"model": ErrorResponse, "description": "Training cohort conflict"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}


def create_verified_training_cohort_router(
    service_dependency: VerifiedTrainingCohortServiceDependency,
) -> APIRouter:
    router = APIRouter(
        prefix="/admin/games/{game_id}",
        tags=["verified-training-cohorts"],
    )
    service_parameter = Depends(service_dependency)

    @router.get(
        "/model-quality",
        response_model=ModelQualityResponse,
        operation_id="getModelQuality",
        summary="Read model and verified-data readiness for one game",
        responses=ERROR_RESPONSES,
    )
    def get_model_quality(
        game_id: UUID,
        service: Annotated[VerifiedTrainingCohortService, service_parameter],
    ) -> ModelQualityResponse:
        return to_model_quality_response(service.model_quality(game_id=game_id))

    @router.get(
        "/verified-training-cohorts/preview",
        response_model=VerifiedTrainingCohortPreviewResponse,
        operation_id="previewVerifiedTrainingCohort",
        summary="Preview the cumulative human-verified training cohort",
        responses=ERROR_RESPONSES,
    )
    def preview_verified_training_cohort(
        game_id: UUID,
        service: Annotated[VerifiedTrainingCohortService, service_parameter],
    ) -> VerifiedTrainingCohortPreviewResponse:
        return to_preview_response(service.preview(game_id=game_id))

    @router.post(
        "/verified-training-cohorts",
        response_model=VerifiedTrainingCohortFreezeResponse,
        operation_id="freezeVerifiedTrainingCohort",
        summary="Freeze an immutable cumulative human-verified training cohort",
        responses=ERROR_RESPONSES,
    )
    def freeze_verified_training_cohort(
        game_id: UUID,
        payload: VerifiedTrainingCohortFreezeCommand,
        service: Annotated[VerifiedTrainingCohortService, service_parameter],
    ) -> VerifiedTrainingCohortFreezeResponse:
        cohort, created = service.freeze(
            game_id=game_id,
            idempotency_key=payload.idempotency_key,
            created_by=payload.created_by,
            expected_manifest_checksum_sha256=(payload.expected_manifest_checksum_sha256),
        )
        return VerifiedTrainingCohortFreezeResponse(
            cohort=to_cohort_response(cohort),
            created=created,
        )

    return router


__all__ = ["create_verified_training_cohort_router"]
