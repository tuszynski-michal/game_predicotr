"""Opt-in Admin routes. Normal jobs endpoints own status, cancellation and retry."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from game_predictor_api.application.grid_shadow import GridShadowService
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.grid_shadow import (
    GridShadowJobCreate,
    GridShadowResultPageResponse,
    GridShadowResultResponse,
    to_grid_shadow_page,
    to_grid_shadow_result,
)
from game_predictor_api.schemas.jobs import JobResponse
from game_predictor_api.storage.game_storage_routing import game_storage_scope


def create_grid_shadow_router(service_dependency: Callable[..., object]) -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["grid-shadow"])
    service_parameter = Depends(service_dependency)
    errors: dict[int | str, dict[str, object]] = {
        code: {"model": ErrorResponse} for code in (404, 409, 422, 503)
    }

    @router.post(
        "/games/{game_id}/grid-shadow-jobs",
        response_model=JobResponse,
        operation_id="startGridShadowJob",
        responses=errors,
    )
    def start_grid_shadow_job(
        game_id: UUID,
        command: GridShadowJobCreate,
        service: Annotated[GridShadowService, service_parameter],
    ) -> JobResponse:
        with game_storage_scope(game_id):
            return JobResponse.from_domain(
                service.start(
                    game_id=game_id,
                    request_id=command.request_id,
                    source_ids=command.source_image_ids,
                )
            )

    @router.get(
        "/games/{game_id}/grid-shadow-results",
        response_model=GridShadowResultPageResponse,
        operation_id="listGridShadowResults",
        responses=errors,
    )
    def list_grid_shadow_results(
        game_id: UUID,
        service: Annotated[GridShadowService, service_parameter],
        source_image_id: Annotated[UUID | None, Query(alias="sourceImageId")] = None,
        cursor: Annotated[str | None, Query(max_length=200)] = None,
        limit: Annotated[int, Query(ge=1, le=20)] = 20,
    ) -> GridShadowResultPageResponse:
        with game_storage_scope(game_id):
            return to_grid_shadow_page(
                service.list(
                    game_id=game_id, source_image_id=source_image_id, cursor=cursor, limit=limit
                )
            )

    @router.get(
        "/games/{game_id}/grid-shadow-results/{result_id}",
        response_model=GridShadowResultResponse,
        operation_id="getGridShadowResult",
        responses=errors,
    )
    def get_grid_shadow_result(
        game_id: UUID, result_id: UUID, service: Annotated[GridShadowService, service_parameter]
    ) -> GridShadowResultResponse:
        with game_storage_scope(game_id):
            return to_grid_shadow_result(service.get(game_id=game_id, result_id=result_id))

    return router
