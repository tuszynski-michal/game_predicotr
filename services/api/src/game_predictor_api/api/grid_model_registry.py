"""Admin catalogue registration and reads; activation belongs to TASK-0998."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from game_predictor_api.application.grid_model_registry import GridModelRegistryService
from game_predictor_api.domain.grid_model_registry import GridModelRegistryError
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.grid_model_registry import (
    GameGridModelAssignmentResponse,
    GridModelAssignmentCommand,
    GridModelControlReceipt,
    GridModelDefaultResponse,
    GridModelHistoryEvent,
    GridModelPublishCommand,
    GridModelRegisterRequest,
    GridModelVersionResponse,
)
from game_predictor_api.security.local_admin import ADMIN_ACTOR


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

    @router.post(
        "/grid-model-versions/{version_id}/publish",
        response_model=GridModelControlReceipt,
        operation_id="publishGridModelVersion",
        responses=errors,
    )
    def publish(
        version_id: UUID,
        command: GridModelPublishCommand,
        service: Annotated[GridModelRegistryService, dependency],
    ) -> GridModelControlReceipt:
        return GridModelControlReceipt.model_validate(
            service.control.execute(
                kind="publish",
                key=command.idempotency_key,
                expected_revision=command.expected_revision,
                version_id=version_id,
                evaluation_id=command.evaluation_id,
                actor=ADMIN_ACTOR,
            )
        )

    @router.get(
        "/grid-model-default",
        response_model=GridModelDefaultResponse,
        operation_id="getGridModelDefault",
        responses=errors,
    )
    def default(
        service: Annotated[GridModelRegistryService, dependency],
    ) -> GridModelDefaultResponse:
        return GridModelDefaultResponse.model_validate(service.control.default_view())

    @router.post(
        "/grid-model-default",
        response_model=GridModelControlReceipt,
        operation_id="setGridModelDefault",
        responses=errors,
    )
    def set_default(
        command: GridModelAssignmentCommand,
        service: Annotated[GridModelRegistryService, dependency],
    ) -> GridModelControlReceipt:
        if command.mode != "evaluated":
            raise GridModelRegistryError(
                "GRID_MODEL_COMMAND_INVALID", "Initial transfer is game-scoped only."
            )
        return GridModelControlReceipt.model_validate(
            service.control.execute(
                kind="set_default",
                key=command.idempotency_key,
                expected_revision=command.expected_revision,
                version_id=command.version_id,
                actor=ADMIN_ACTOR,
            )
        )

    @router.post(
        "/games/{game_id}/grid-model-assignment/activate",
        response_model=GridModelControlReceipt,
        operation_id="activateGameGridModel",
        responses=errors,
    )
    def activate(
        game_id: UUID,
        command: GridModelAssignmentCommand,
        service: Annotated[GridModelRegistryService, dependency],
    ) -> GridModelControlReceipt:
        if command.mode == "initial_transfer":
            return GridModelControlReceipt.model_validate(
                service.initial_transfer(
                    game_id=game_id,
                    key=command.idempotency_key,
                    expected_revision=command.expected_revision,
                    version_id=command.version_id,
                    actor=ADMIN_ACTOR,
                )
            )
        return GridModelControlReceipt.model_validate(
            service.control.execute(
                kind="activate",
                key=command.idempotency_key,
                expected_revision=command.expected_revision,
                version_id=command.version_id,
                game_id=game_id,
                actor=ADMIN_ACTOR,
            )
        )

    @router.post(
        "/games/{game_id}/grid-model-assignment/rollback",
        response_model=GridModelControlReceipt,
        operation_id="rollbackGameGridModel",
        responses=errors,
    )
    def rollback(
        game_id: UUID,
        command: GridModelAssignmentCommand,
        service: Annotated[GridModelRegistryService, dependency],
    ) -> GridModelControlReceipt:
        if command.mode != "evaluated":
            raise GridModelRegistryError(
                "GRID_MODEL_COMMAND_INVALID", "Rollback requires evaluated mode."
            )
        return GridModelControlReceipt.model_validate(
            service.control.execute(
                kind="rollback",
                key=command.idempotency_key,
                expected_revision=command.expected_revision,
                version_id=command.version_id,
                game_id=game_id,
                actor=ADMIN_ACTOR,
            )
        )

    @router.get(
        "/grid-model-history",
        response_model=list[GridModelHistoryEvent],
        operation_id="getGridModelHistory",
        responses=errors,
    )
    def history(
        service: Annotated[GridModelRegistryService, dependency],
    ) -> list[GridModelHistoryEvent]:
        return [GridModelHistoryEvent.model_validate(row) for row in service.control.history()]

    @router.get(
        "/games/{game_id}/grid-model-assignment/history",
        response_model=list[GridModelHistoryEvent],
        operation_id="getGameGridModelHistory",
        responses=errors,
    )
    def game_history(
        game_id: UUID,
        service: Annotated[GridModelRegistryService, dependency],
    ) -> list[GridModelHistoryEvent]:
        return [
            GridModelHistoryEvent.model_validate(row) for row in service.control.history(game_id)
        ]

    return router
