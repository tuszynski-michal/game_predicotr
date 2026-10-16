"""Application grid-training runs (TASK-0996): queue, read, cancel and resume a run job."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from game_predictor_api.application.grid_training_runs import GridTrainingRunService
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.grid_training_cohorts import (
    GridTrainingRunCreate,
    GridTrainingRunList,
    GridTrainingRunView,
)


def create_grid_training_runs_router(dependency: Callable[..., object]) -> APIRouter:
    router = APIRouter(
        prefix="/admin/games/{game_id}",
        tags=["grid-training-runs"],
        responses={
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
        },
    )
    parameter = Depends(dependency)

    def require_actor(request: Request) -> None:
        if getattr(request.state, "local_admin_actor", None) != "local-owner":
            raise HTTPException(403, "A validated local human actor is required.")

    @router.post(
        "/grid-training-runs",
        operation_id="createGridTrainingRun",
        response_model=GridTrainingRunView,
    )
    def create(
        request: Request,
        game_id: UUID,
        command: GridTrainingRunCreate,
        service: Annotated[GridTrainingRunService, parameter],
    ) -> GridTrainingRunView:
        require_actor(request)
        return GridTrainingRunView.model_validate(
            service.create(game_id, command.model_dump(mode="json"))
        )

    @router.get(
        "/grid-training-runs",
        operation_id="listGridTrainingRuns",
        response_model=GridTrainingRunList,
    )
    def list_runs(
        game_id: UUID, service: Annotated[GridTrainingRunService, parameter]
    ) -> GridTrainingRunList:
        return GridTrainingRunList.model_validate(service.list(game_id))

    @router.get(
        "/grid-training-runs/{run_id}",
        operation_id="getGridTrainingRun",
        response_model=GridTrainingRunView,
    )
    def get(
        game_id: UUID, run_id: UUID, service: Annotated[GridTrainingRunService, parameter]
    ) -> GridTrainingRunView:
        return GridTrainingRunView.model_validate(service.get(game_id, run_id))

    @router.post(
        "/grid-training-runs/{run_id}/cancel",
        operation_id="cancelGridTrainingRun",
        response_model=GridTrainingRunView,
    )
    def cancel(
        request: Request,
        game_id: UUID,
        run_id: UUID,
        service: Annotated[GridTrainingRunService, parameter],
    ) -> GridTrainingRunView:
        require_actor(request)
        return GridTrainingRunView.model_validate(service.cancel(game_id, run_id))

    @router.post(
        "/grid-training-runs/{run_id}/resume",
        operation_id="resumeGridTrainingRun",
        response_model=GridTrainingRunView,
    )
    def resume(
        request: Request,
        game_id: UUID,
        run_id: UUID,
        service: Annotated[GridTrainingRunService, parameter],
    ) -> GridTrainingRunView:
        require_actor(request)
        return GridTrainingRunView.model_validate(service.resume(game_id, run_id))

    return router
