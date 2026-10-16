"""Grid model evaluations (TASK-0997): queue, read and re-prove cohort currentness."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from game_predictor_api.application.grid_model_evaluation import GridModelEvaluationService
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.grid_model_evaluations import (
    GridModelEvaluationCreate,
    GridModelEvaluationCurrentnessResult,
    GridModelEvaluationList,
    GridModelEvaluationView,
)


def create_grid_model_evaluations_router(dependency: Callable[..., object]) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/admin/grid-model-evaluations",
        tags=["grid-model-evaluations"],
        responses={
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
        },
    )
    parameter = Depends(dependency)

    def actor(request: Request) -> str:
        value = getattr(request.state, "local_admin_actor", None)
        if value != "local-owner":
            raise HTTPException(403, "A validated local human actor is required.")
        return str(value)

    @router.post(
        "", operation_id="createGridModelEvaluation", response_model=GridModelEvaluationView
    )
    def create(
        request: Request,
        command: GridModelEvaluationCreate,
        service: Annotated[GridModelEvaluationService, parameter],
    ) -> GridModelEvaluationView:
        actor(request)
        return GridModelEvaluationView.model_validate(
            service.create(command.model_dump(mode="json"))
        )

    @router.get("", operation_id="listGridModelEvaluations", response_model=GridModelEvaluationList)
    def list_evaluations(
        service: Annotated[GridModelEvaluationService, parameter],
        version_id: Annotated[UUID, Query(alias="versionId")],
    ) -> GridModelEvaluationList:
        return GridModelEvaluationList.model_validate(service.list(version_id))

    @router.get(
        "/{evaluation_id}",
        operation_id="getGridModelEvaluation",
        response_model=GridModelEvaluationView,
    )
    def get(
        evaluation_id: UUID, service: Annotated[GridModelEvaluationService, parameter]
    ) -> GridModelEvaluationView:
        return GridModelEvaluationView.model_validate(service.get(evaluation_id))

    @router.post(
        "/reports/{report_id}/currentness",
        operation_id="verifyGridModelEvaluationCurrentness",
        response_model=GridModelEvaluationCurrentnessResult,
    )
    def verify(
        request: Request,
        report_id: UUID,
        service: Annotated[GridModelEvaluationService, parameter],
    ) -> GridModelEvaluationCurrentnessResult:
        return GridModelEvaluationCurrentnessResult.model_validate(
            service.verify_currentness(report_id, actor(request))
        )

    return router
