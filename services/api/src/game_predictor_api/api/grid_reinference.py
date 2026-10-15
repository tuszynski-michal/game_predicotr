"""Additive routes mounted on the existing operational image-review router."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from game_predictor_api.application.grid_reinference import GridReinferenceService
from game_predictor_api.application.image_reviews import OperationalImageReviewService
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.schemas.grid_reinference import (
    GridReinferenceCommand,
    GridReinferenceFreeze,
    GridReinferenceOperationPage,
    GridReinferencePilotAck,
    GridReinferencePrepare,
    GridReinferenceResponse,
    GridReinferenceResume,
    GridReinferenceStart,
    GridReinferenceTargetPage,
)


def register_grid_reinference_routes(router: APIRouter, dependency: Callable[..., object]) -> None:
    parameter = Depends(dependency)

    def available(service: OperationalImageReviewService) -> GridReinferenceService:
        if service.grid_reinference is None:
            raise JobConflictError(
                "GRID_REINFERENCE_UNAVAILABLE", "Selected grid reinference is not configured."
            )
        return service.grid_reinference

    def execute(
        service: OperationalImageReviewService,
        game_id: UUID,
        operation_id: UUID,
        kind: str,
        command: GridReinferenceCommand,
    ) -> GridReinferenceResponse:
        return GridReinferenceResponse.model_validate(
            available(service).execute(
                game_id,
                operation_id,
                kind,
                command.model_dump(mode="json", by_alias=True),
                "local-admin",
            )
        )

    @router.post(
        "/grid-reinference/{game_id}/prepare",
        response_model=GridReinferenceResponse,
        operation_id="prepareGridReinference",
    )
    def prepare(
        game_id: UUID,
        command: GridReinferencePrepare,
        service: Annotated[OperationalImageReviewService, parameter],
    ) -> GridReinferenceResponse:
        return GridReinferenceResponse.model_validate(
            available(service).prepare(
                game_id,
                command.model_dump(mode="json", by_alias=True),
                "local-admin",
            )
        )

    @router.get(
        "/grid-reinference/{game_id}/operations",
        response_model=GridReinferenceOperationPage,
        operation_id="listGridReinferenceOperations",
    )
    def list_operations(
        game_id: UUID,
        service: Annotated[OperationalImageReviewService, parameter],
        cursor: str | None = None,
        limit: int = Query(default=20, ge=1, le=50),
        compatible_with_operation_id: UUID | None = None,
    ) -> GridReinferenceOperationPage:
        return GridReinferenceOperationPage.model_validate(
            available(service).list_operations(game_id, cursor, limit, compatible_with_operation_id)
        )

    @router.get(
        "/grid-reinference/{game_id}/operations/{operation_id}",
        response_model=GridReinferenceResponse,
        operation_id="getGridReinference",
    )
    def get(
        game_id: UUID,
        operation_id: UUID,
        service: Annotated[OperationalImageReviewService, parameter],
    ) -> GridReinferenceResponse:
        return GridReinferenceResponse.model_validate(available(service).get(game_id, operation_id))

    @router.get(
        "/grid-reinference/{game_id}/operations/{operation_id}/targets",
        response_model=GridReinferenceTargetPage,
        operation_id="getGridReinferenceTargets",
    )
    def targets(
        game_id: UUID,
        operation_id: UUID,
        service: Annotated[OperationalImageReviewService, parameter],
        cursor: str | None = None,
        limit: int = Query(default=100, ge=1, le=100),
    ) -> GridReinferenceTargetPage:
        return GridReinferenceTargetPage.model_validate(
            available(service).targets(game_id, operation_id, cursor, limit)
        )

    @router.post(
        "/grid-reinference/{game_id}/operations/{operation_id}/freeze",
        response_model=GridReinferenceResponse,
        operation_id="freezeGridReinference",
    )
    def freeze(
        game_id: UUID,
        operation_id: UUID,
        command: GridReinferenceFreeze,
        service: Annotated[OperationalImageReviewService, parameter],
    ) -> GridReinferenceResponse:
        return execute(service, game_id, operation_id, "freeze", command)

    @router.post(
        "/grid-reinference/{game_id}/operations/{operation_id}/pilot-ack",
        response_model=GridReinferenceResponse,
        operation_id="acknowledgeGridReinferencePilot",
    )
    def ack(
        game_id: UUID,
        operation_id: UUID,
        command: GridReinferencePilotAck,
        service: Annotated[OperationalImageReviewService, parameter],
    ) -> GridReinferenceResponse:
        return execute(service, game_id, operation_id, "pilot-ack", command)

    @router.post(
        "/grid-reinference/{game_id}/operations/{operation_id}/start",
        response_model=GridReinferenceResponse,
        operation_id="startGridReinference",
    )
    def start(
        game_id: UUID,
        operation_id: UUID,
        command: GridReinferenceStart,
        service: Annotated[OperationalImageReviewService, parameter],
    ) -> GridReinferenceResponse:
        return execute(service, game_id, operation_id, "start", command)

    @router.post(
        "/grid-reinference/{game_id}/operations/{operation_id}/resume",
        response_model=GridReinferenceResponse,
        operation_id="resumeGridReinference",
    )
    def resume(
        game_id: UUID,
        operation_id: UUID,
        command: GridReinferenceResume,
        service: Annotated[OperationalImageReviewService, parameter],
    ) -> GridReinferenceResponse:
        return execute(service, game_id, operation_id, "resume", command)

    @router.post(
        "/grid-reinference/{game_id}/operations/{operation_id}/cancel",
        response_model=GridReinferenceResponse,
        operation_id="cancelGridReinference",
    )
    def cancel(
        game_id: UUID,
        operation_id: UUID,
        command: GridReinferenceCommand,
        service: Annotated[OperationalImageReviewService, parameter],
    ) -> GridReinferenceResponse:
        return execute(service, game_id, operation_id, "cancel", command)
