"""Admin catalogue registration and reads; activation belongs to TASK-0998."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from game_predictor_api.application.grid_model_registry import GridModelRegistryService
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.grid_model_registry import (
    GameGridModelAssignmentResponse,
    GridModelRegisterRequest,
    GridModelVersionResponse,
)


def create_grid_model_registry_router(service_dependency: Callable[..., object]) -> APIRouter:
    router = APIRouter(prefix="/api/v1/admin", tags=["grid-model-registry"])
    dependency = Depends(service_dependency)
    errors: dict[int | str, dict[str, object]] = {
        code: {"model": ErrorResponse} for code in (404, 409, 422)
    }

    @router.get(
        "/grid-model-versions",
        response_model=list[GridModelVersionResponse],
        operation_id="listGridModelVersions",
        responses=errors,
    )
    def list_versions(
        service: Annotated[GridModelRegistryService, dependency],
    ) -> list[GridModelVersionResponse]:
        return [GridModelVersionResponse.model_validate(view) for view in service.list_versions()]

    @router.post(
        "/grid-model-versions",
        response_model=GridModelVersionResponse,
        operation_id="registerGridModelVersion",
        responses=errors,
    )
    def register_version(
        command: GridModelRegisterRequest, service: Annotated[GridModelRegistryService, dependency]
    ) -> GridModelVersionResponse:
        return GridModelVersionResponse.model_validate(
            service.register(
                command.idempotency_key, command.manifest.model_dump(mode="json", by_alias=True)
            )
        )

    @router.get(
        "/games/{game_id}/grid-model-assignment",
        response_model=GameGridModelAssignmentResponse,
        operation_id="getGameGridModelAssignment",
        responses=errors,
    )
    def game_assignment(
        game_id: UUID, service: Annotated[GridModelRegistryService, dependency]
    ) -> GameGridModelAssignmentResponse:
        return GameGridModelAssignmentResponse.model_validate(service.game_assignment(game_id))

    return router
