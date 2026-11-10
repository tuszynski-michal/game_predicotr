"""Read-only readiness and actor-guarded durable correction-learning commands."""

from collections.abc import Callable
from typing import Annotated, Any, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.grid_correction_learning import (
    GridCorrectionLearningList,
    GridCorrectionLearningPreview,
    GridCorrectionLearningPreviewCommand,
    GridCorrectionLearningStartCommand,
    GridCorrectionLearningView,
)
from game_predictor_api.schemas.grid_model_evaluations import GridModelEvaluationView


class _LearningService(Protocol):
    """Structural boundary implemented by GridCorrectionLearningService."""

    def ready(self, game_id: UUID, *, recommend_training_mode: bool = False) -> object: ...
    def preview(self, game_id: UUID, command: dict[str, Any]) -> object: ...
    def start(self, game_id: UUID, command: dict[str, Any], actor: str) -> object: ...
    def get(self, game_id: UUID, learning_id: UUID) -> object: ...
    def cancel(self, game_id: UUID, learning_id: UUID, actor: str) -> object: ...
    def resume(self, game_id: UUID, learning_id: UUID, actor: str) -> object: ...
    def evaluation(self, game_id: UUID, learning_id: UUID) -> object: ...
    def list(self, game_id: UUID) -> object: ...


def create_grid_correction_learning_router(dependency: Callable[..., object]) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/admin/games/{game_id}/grid-correction-learning",
        tags=["grid-correction-learning"],
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
        "/ready",
        operation_id="getGridCorrectionLearningReady",
        response_model=GridCorrectionLearningPreview,
        description="Read current corrections. recommendTrainingMode opts into a data-based "
        "mode recommendation; legacy reads retain grid-only. No write or training starts.",
    )
    def ready(
        game_id: UUID,
        service: Annotated[_LearningService, parameter],
        recommendTrainingMode: bool = False,
    ) -> GridCorrectionLearningPreview:
        view = (
            service.ready(game_id, recommend_training_mode=True)
            if recommendTrainingMode
            else service.ready(game_id)
        )
        return GridCorrectionLearningPreview.model_validate(view)

    @router.post(
        "/preview",
        operation_id="previewGridCorrectionLearning",
        response_model=GridCorrectionLearningPreview,
    )
    def preview(
        request: Request,
        game_id: UUID,
        command: GridCorrectionLearningPreviewCommand,
        service: Annotated[_LearningService, parameter],
    ) -> GridCorrectionLearningPreview:
        actor(request)
        return GridCorrectionLearningPreview.model_validate(
            service.preview(
                game_id,
                command.model_dump(
                    mode="json",
                    exclude={"policyVersion", "validationAssignments"}
                    if command.policyVersion is None
                    else None,
                ),
            )
        )

    @router.post(
        "", operation_id="startGridCorrectionLearning", response_model=GridCorrectionLearningView
    )
    def start(
        request: Request,
        game_id: UUID,
        command: GridCorrectionLearningStartCommand,
        service: Annotated[_LearningService, parameter],
    ) -> GridCorrectionLearningView:
        return GridCorrectionLearningView.model_validate(
            service.start(
                game_id,
                command.model_dump(
                    mode="json",
                    exclude={"policyVersion", "validationAssignments"}
                    if command.policyVersion is None
                    else None,
                ),
                actor(request),
            )
        )

    @router.get(
        "", operation_id="listGridCorrectionLearning", response_model=GridCorrectionLearningList
    )
    def list_runs(
        game_id: UUID, service: Annotated[_LearningService, parameter]
    ) -> GridCorrectionLearningList:
        return GridCorrectionLearningList.model_validate(service.list(game_id))

    @router.get(
        "/{learning_id}",
        operation_id="getGridCorrectionLearning",
        response_model=GridCorrectionLearningView,
    )
    def get(
        game_id: UUID, learning_id: UUID, service: Annotated[_LearningService, parameter]
    ) -> GridCorrectionLearningView:
        return GridCorrectionLearningView.model_validate(service.get(game_id, learning_id))

    @router.post(
        "/{learning_id}/cancel",
        operation_id="cancelGridCorrectionLearning",
        response_model=GridCorrectionLearningView,
    )
    def cancel(
        request: Request,
        game_id: UUID,
        learning_id: UUID,
        service: Annotated[_LearningService, parameter],
    ) -> GridCorrectionLearningView:
        return GridCorrectionLearningView.model_validate(
            service.cancel(game_id, learning_id, actor(request))
        )

    @router.post(
        "/{learning_id}/resume",
        operation_id="resumeGridCorrectionLearning",
        response_model=GridCorrectionLearningView,
    )
    def resume(
        request: Request,
        game_id: UUID,
        learning_id: UUID,
        service: Annotated[_LearningService, parameter],
    ) -> GridCorrectionLearningView:
        return GridCorrectionLearningView.model_validate(
            service.resume(game_id, learning_id, actor(request))
        )

    @router.get(
        "/{learning_id}/evaluation",
        operation_id="getGridCorrectionLearningEvaluation",
        response_model=GridModelEvaluationView,
    )
    def evaluation(
        game_id: UUID, learning_id: UUID, service: Annotated[_LearningService, parameter]
    ) -> GridModelEvaluationView:
        return GridModelEvaluationView.model_validate(service.evaluation(game_id, learning_id))

    return router
