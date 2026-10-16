"""Bounded explicit cohort commands; GET routes expose stored metadata only."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from game_predictor_api.application.grid_training_cohorts import GridTrainingCohortService
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.grid_training_cohorts import (
    GridCohortCommandResponse,
    GridCohortEligibility,
    GridCohortFreezeCommand,
    GridCohortHeader,
    GridCohortList,
    GridCohortMembers,
    GridCohortPageCommand,
    GridCohortPrepareCommand,
    GridCohortRevisionCommand,
    GridSourceIdentityCompleteCommand,
    GridSourceIdentityResponse,
)


def create_grid_training_cohorts_router(dependency: Callable[..., object]) -> APIRouter:
    router = APIRouter(
        prefix="/admin/games/{game_id}",
        tags=["grid-training-cohorts"],
        responses={
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
        },
    )
    parameter = Depends(dependency)

    def actor(request: Request) -> str:
        if getattr(request.state, "local_admin_actor", None) != "local-owner":
            raise HTTPException(403, "A validated local human actor is required.")
        return "local-owner"

    @router.get(
        "/grid-training-cohorts",
        operation_id="listGridTrainingCohorts",
        response_model=GridCohortList,
    )
    def list_cohorts(
        game_id: UUID,
        service: Annotated[GridTrainingCohortService, parameter],
        cursor: UUID | None = None,
        limit: int = Query(20, ge=1, le=50),
    ) -> GridCohortList:
        return GridCohortList.model_validate(service.list(game_id, cursor, limit))

    @router.post(
        "/grid-training-cohorts/prepare",
        operation_id="prepareGridTrainingCohort",
        response_model=GridCohortCommandResponse,
    )
    def prepare(
        request: Request,
        game_id: UUID,
        command: GridCohortPrepareCommand,
        service: Annotated[GridTrainingCohortService, parameter],
    ) -> GridCohortCommandResponse:
        return GridCohortCommandResponse.model_validate(
            service.prepare(game_id, command.model_dump(mode="json", by_alias=True), actor(request))
        )

    @router.get(
        "/grid-training-cohorts/{cohort_id}",
        operation_id="getGridTrainingCohort",
        response_model=GridCohortHeader,
    )
    def get(
        game_id: UUID, cohort_id: UUID, service: Annotated[GridTrainingCohortService, parameter]
    ) -> GridCohortHeader:
        return GridCohortHeader.model_validate(service.get(game_id, cohort_id))

    @router.get(
        "/grid-training-cohorts/{cohort_id}/members",
        operation_id="getGridTrainingCohortMembers",
        response_model=GridCohortMembers,
    )
    def members(
        game_id: UUID,
        cohort_id: UUID,
        service: Annotated[GridTrainingCohortService, parameter],
        cursor: int | None = Query(None, ge=0),
        limit: int = Query(200, ge=1, le=200),
    ) -> GridCohortMembers:
        return GridCohortMembers.model_validate(service.members(game_id, cohort_id, cursor, limit))

    @router.get(
        "/grid-training-cohorts/{cohort_id}/eligibility",
        operation_id="getGridTrainingCohortEligibility",
        response_model=GridCohortEligibility,
    )
    def eligibility(
        game_id: UUID, cohort_id: UUID, service: Annotated[GridTrainingCohortService, parameter]
    ) -> GridCohortEligibility:
        return GridCohortEligibility.model_validate(service.eligibility(game_id, cohort_id))

    @router.post(
        "/grid-training-cohorts/{cohort_id}/prepare-page",
        operation_id="prepareGridTrainingCohortPage",
        response_model=GridCohortCommandResponse,
    )
    def prepare_page(
        request: Request,
        game_id: UUID,
        cohort_id: UUID,
        command: GridCohortPageCommand,
        service: Annotated[GridTrainingCohortService, parameter],
    ) -> GridCohortCommandResponse:
        return GridCohortCommandResponse.model_validate(
            service.command(
                game_id,
                cohort_id,
                "prepare-page",
                command.model_dump(mode="json", by_alias=True),
                actor(request),
            )
        )

    @router.post(
        "/grid-training-cohorts/{cohort_id}/materialize-page",
        operation_id="materializeGridTrainingCohortPage",
        response_model=GridCohortCommandResponse,
    )
    def materialize_page(
        request: Request,
        game_id: UUID,
        cohort_id: UUID,
        command: GridCohortPageCommand,
        service: Annotated[GridTrainingCohortService, parameter],
    ) -> GridCohortCommandResponse:
        return GridCohortCommandResponse.model_validate(
            service.command(
                game_id,
                cohort_id,
                "materialize-page",
                command.model_dump(mode="json", by_alias=True),
                actor(request),
            )
        )

    @router.post(
        "/grid-training-cohorts/{cohort_id}/freeze",
        operation_id="freezeGridTrainingCohort",
        response_model=GridCohortCommandResponse,
    )
    def freeze(
        request: Request,
        game_id: UUID,
        cohort_id: UUID,
        command: GridCohortFreezeCommand,
        service: Annotated[GridTrainingCohortService, parameter],
    ) -> GridCohortCommandResponse:
        return GridCohortCommandResponse.model_validate(
            service.command(
                game_id,
                cohort_id,
                "freeze",
                command.model_dump(mode="json", by_alias=True),
                actor(request),
            )
        )

    @router.post(
        "/grid-training-cohorts/{cohort_id}/cancel",
        operation_id="cancelGridTrainingCohort",
        response_model=GridCohortCommandResponse,
    )
    def cancel(
        request: Request,
        game_id: UUID,
        cohort_id: UUID,
        command: GridCohortRevisionCommand,
        service: Annotated[GridTrainingCohortService, parameter],
    ) -> GridCohortCommandResponse:
        return GridCohortCommandResponse.model_validate(
            service.command(
                game_id,
                cohort_id,
                "cancel",
                command.model_dump(mode="json", by_alias=True),
                actor(request),
            )
        )

    @router.post(
        "/grid-source-identities/complete",
        operation_id="completeGridSourceIdentities",
        response_model=GridSourceIdentityResponse,
    )
    def complete(
        request: Request,
        game_id: UUID,
        command: GridSourceIdentityCompleteCommand,
        service: Annotated[GridTrainingCohortService, parameter],
    ) -> GridSourceIdentityResponse:
        return GridSourceIdentityResponse.model_validate(
            service.complete_identities(
                game_id, command.model_dump(mode="json", by_alias=True), actor(request)
            )
        )

    return router
