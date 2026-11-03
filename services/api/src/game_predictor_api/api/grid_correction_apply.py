"""GET previews never create work; explicit commands require the local human actor."""

from collections.abc import Callable
from typing import Annotated, Any, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.grid_correction_apply import (
    GridCorrectionApplyList,
    GridCorrectionApplyPreview,
    GridCorrectionApplyStartCommand,
    GridCorrectionApplyView,
)


class _ApplyService(Protocol):
    def preview(self, game: UUID, learning: UUID, additional: list[UUID]) -> object: ...
    def start(self, game: UUID, learning: UUID, command: dict[str, Any], actor: str) -> object: ...
    def list(self, game: UUID, learning: UUID) -> object: ...
    def get(self, game: UUID, learning: UUID, identifier: UUID) -> object: ...
    def resume(self, game: UUID, learning: UUID, identifier: UUID, actor: str) -> object: ...


def create_grid_correction_apply_router(dependency: Callable[..., object]) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/admin/games/{game_id}/grid-correction-learning/{learning_id}/apply",
        tags=["grid-correction-learning"],
        responses={code: {"model": ErrorResponse} for code in (403, 404, 409)},
    )
    parameter = Depends(dependency)

    def actor(request: Request) -> str:
        if getattr(request.state, "local_admin_actor", None) != "local-owner":
            raise HTTPException(403, "A validated local human actor is required.")
        return "local-owner"

    @router.get(
        "/preview",
        operation_id="previewGridCorrectionApply",
        response_model=GridCorrectionApplyPreview,
    )
    def preview(
        game_id: UUID,
        learning_id: UUID,
        service: Annotated[_ApplyService, parameter],
        additionalGameIds: Annotated[list[UUID] | None, Query(max_length=7)] = None,
    ) -> GridCorrectionApplyPreview:
        return GridCorrectionApplyPreview.model_validate(
            service.preview(game_id, learning_id, additionalGameIds or [])
        )

    @router.post(
        "", operation_id="startGridCorrectionApply", response_model=GridCorrectionApplyView
    )
    def start(
        request: Request,
        game_id: UUID,
        learning_id: UUID,
        command: GridCorrectionApplyStartCommand,
        service: Annotated[_ApplyService, parameter],
    ) -> GridCorrectionApplyView:
        return GridCorrectionApplyView.model_validate(
            service.start(game_id, learning_id, command.model_dump(mode="json"), actor(request))
        )

    @router.get("", operation_id="listGridCorrectionApply", response_model=GridCorrectionApplyList)
    def list_operations(
        game_id: UUID, learning_id: UUID, service: Annotated[_ApplyService, parameter]
    ) -> GridCorrectionApplyList:
        return GridCorrectionApplyList.model_validate(service.list(game_id, learning_id))

    @router.get(
        "/{apply_id}", operation_id="getGridCorrectionApply", response_model=GridCorrectionApplyView
    )
    def get(
        game_id: UUID,
        learning_id: UUID,
        apply_id: UUID,
        service: Annotated[_ApplyService, parameter],
    ) -> GridCorrectionApplyView:
        return GridCorrectionApplyView.model_validate(service.get(game_id, learning_id, apply_id))

    @router.post(
        "/{apply_id}/resume",
        operation_id="resumeGridCorrectionApply",
        response_model=GridCorrectionApplyView,
    )
    def resume(
        request: Request,
        game_id: UUID,
        learning_id: UUID,
        apply_id: UUID,
        service: Annotated[_ApplyService, parameter],
    ) -> GridCorrectionApplyView:
        return GridCorrectionApplyView.model_validate(
            service.resume(game_id, learning_id, apply_id, actor(request))
        )

    return router
