"""Admin API for explicit immutable verified cohort exports."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from game_predictor_api.application.image_review_cohorts import VerifiedCohortService
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.image_review_cohorts import (
    VerifiedCohortExportResponse,
    VerifiedCohortFreezeCommand,
    VerifiedCohortFreezeResponse,
    to_verified_cohort_response,
)

VerifiedCohortServiceDependency = Callable[..., object]
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Verified cohort resource not found"},
    409: {"model": ErrorResponse, "description": "Verified cohort conflict"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}


def create_image_review_cohort_router(
    service_dependency: VerifiedCohortServiceDependency,
) -> APIRouter:
    router = APIRouter(
        prefix="/admin/image-review-cohort-exports",
        tags=["image-review-cohorts"],
    )
    service_parameter = Depends(service_dependency)

    @router.post(
        "",
        response_model=VerifiedCohortFreezeResponse,
        operation_id="freezeVerifiedImageReviewCohort",
        summary="Explicitly freeze the current verified board cohort",
        responses=ERROR_RESPONSES,
    )
    def freeze_verified_image_review_cohort(
        payload: VerifiedCohortFreezeCommand,
        service: Annotated[VerifiedCohortService, service_parameter],
        game_id: Annotated[UUID, Query(alias="gameId")],
        import_job_id: Annotated[UUID, Query(alias="importJobId")],
    ) -> VerifiedCohortFreezeResponse:
        export, created = service.freeze(
            game_id=game_id,
            import_job_id=import_job_id,
            created_by=payload.created_by,
        )
        return VerifiedCohortFreezeResponse(
            export=to_verified_cohort_response(export),
            created=created,
        )

    @router.get(
        "",
        response_model=list[VerifiedCohortExportResponse],
        operation_id="listVerifiedImageReviewCohorts",
        summary="List immutable verified cohort export versions",
        responses=ERROR_RESPONSES,
    )
    def list_verified_image_review_cohorts(
        service: Annotated[VerifiedCohortService, service_parameter],
        game_id: Annotated[UUID, Query(alias="gameId")],
        import_job_id: Annotated[UUID, Query(alias="importJobId")],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> list[VerifiedCohortExportResponse]:
        return [
            to_verified_cohort_response(value)
            for value in service.list(
                game_id=game_id,
                import_job_id=import_job_id,
                limit=limit,
            )
        ]

    return router


__all__ = ["create_image_review_cohort_router"]
