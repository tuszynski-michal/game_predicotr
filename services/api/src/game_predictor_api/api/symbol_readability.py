"""Additive independent quality routes in the existing symbol review area."""

from collections.abc import Callable
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.symbol_readability import (
    ReadabilityCommandRequest,
    ReadabilityLabelRequest,
    ReadabilityModelResponse,
    ReadabilityPageResponse,
    ReadabilityRunResponse,
    ReadabilityStartRequest,
    ReadabilityWorkspaceResponse,
)
from game_predictor_api.storage.symbol_readability import SqlAlchemyReadabilityRepository


def create_symbol_readability_router(dependency: Callable[..., object]) -> APIRouter:
    router = APIRouter(
        prefix="/admin/games/{game_id}/symbol-cell-reviews/readability",
        tags=["symbol-cell-reviews"],
        responses={409: {"model": ErrorResponse, "description": "Quality workflow conflict"}},
    )
    service = Depends(dependency)

    @router.get(
        "/runs", response_model=ReadabilityWorkspaceResponse, operation_id="getReadabilityWorkspace"
    )
    def workspace(
        game_id: UUID, repository: Annotated[SqlAlchemyReadabilityRepository, service]
    ) -> object:
        return repository.workspace(game_id)

    @router.post("/runs", response_model=ReadabilityRunResponse, operation_id="startReadabilityRun")
    def start(
        game_id: UUID,
        request: ReadabilityStartRequest,
        repository: Annotated[SqlAlchemyReadabilityRepository, service],
    ) -> object:
        return repository.start(game_id, request)

    @router.get(
        "/runs/{run_id}/items",
        response_model=ReadabilityPageResponse,
        operation_id="listReadabilityItems",
    )
    def items(
        game_id: UUID,
        run_id: UUID,
        repository: Annotated[SqlAlchemyReadabilityRepository, service],
        offset: Annotated[int, Query(ge=0)] = 0,
        state: Literal["pending", "readable", "unreadable", "skipped", "stale", "error"]
        | None = None,
        historical: bool | None = None,
        problem: Literal["overlap", "unreadable"] | None = None,
    ) -> object:
        return repository.page(
            game_id, run_id, offset=offset, state=state, historical=historical, problem=problem
        )

    @router.post(
        "/runs/{run_id}/labels",
        response_model=ReadabilityRunResponse,
        operation_id="labelReadabilityItems",
    )
    def labels(
        game_id: UUID,
        run_id: UUID,
        request: ReadabilityLabelRequest,
        repository: Annotated[SqlAlchemyReadabilityRepository, service],
    ) -> object:
        return repository.label(game_id, run_id, request)

    @router.post(
        "/runs/{run_id}/fit",
        response_model=ReadabilityModelResponse,
        operation_id="fitReadabilityPilot",
    )
    def fit(
        game_id: UUID,
        run_id: UUID,
        request: ReadabilityCommandRequest,
        repository: Annotated[SqlAlchemyReadabilityRepository, service],
    ) -> object:
        return repository.fit(game_id, run_id, request)

    @router.post(
        "/models/{model_id}/accept",
        response_model=ReadabilityModelResponse,
        operation_id="acceptReadabilityModel",
    )
    def accept(
        game_id: UUID,
        model_id: UUID,
        request: ReadabilityCommandRequest,
        repository: Annotated[SqlAlchemyReadabilityRepository, service],
    ) -> object:
        return repository.accept(game_id, model_id, request)

    @router.get(
        "/runs/{run_id}/export", operation_id="exportReadabilityCsv", response_class=Response
    )
    def export(
        game_id: UUID, run_id: UUID, repository: Annotated[SqlAlchemyReadabilityRepository, service]
    ) -> Response:
        return Response(
            repository.csv(game_id, run_id),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="readability-{run_id}.csv"'},
        )

    return router
