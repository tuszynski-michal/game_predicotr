"""HTTP boundary of super game series (TASK-0933, D-535)."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from game_predictor_api.application.super_game_series import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    SuperGameSeriesFilter,
    SuperGameSeriesService,
)
from game_predictor_api.domain.super_game_series import RunVerification, SeriesCompleteness
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.super_game_series import (
    SuperGameSeriesBoardsResponse,
    SuperGameSeriesDeriveResponse,
    SuperGameSeriesListResponse,
    SuperGameSeriesResponse,
    SuperGameStateResponse,
    SuperSymbolUpdate,
)

SuperGameSeriesServiceDependency = Callable[..., object]
_LOCAL_ADMIN_ACTOR = "local-admin"
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Game or series not found"},
    409: {"model": ErrorResponse, "description": "Revision conflict or projection not ready"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}


def create_super_game_series_router(
    service_dependency: SuperGameSeriesServiceDependency,
) -> APIRouter:
    router = APIRouter(prefix="/admin/games", tags=["super-game-series"])
    service_parameter = Depends(service_dependency)

    @router.get(
        "/{game_id}/super-game-series",
        response_model=SuperGameSeriesListResponse,
        operation_id="listSuperGameSeries",
        summary="List published super game series of a game",
        responses=ERROR_RESPONSES,
    )
    def list_series(
        game_id: UUID,
        service: Annotated[SuperGameSeriesService, service_parameter],
        completeness: Annotated[SeriesCompleteness | None, Query()] = None,
        run_verification: Annotated[RunVerification | None, Query(alias="runVerification")] = None,
        defined: Annotated[bool | None, Query()] = None,
        cursor: Annotated[str | None, Query(max_length=9, pattern=r"^[0-9]+$")] = None,
        limit: Annotated[int, Query(ge=1, le=MAX_LIST_LIMIT)] = DEFAULT_LIST_LIMIT,
    ) -> SuperGameSeriesListResponse:
        page = service.list(
            game_id,
            filters=SuperGameSeriesFilter(
                completeness=completeness, run_verification=run_verification, defined=defined
            ),
            cursor=cursor,
            limit=limit,
        )
        return SuperGameSeriesListResponse.from_domain(page)

    @router.get(
        "/{game_id}/super-game-series/state",
        response_model=SuperGameStateResponse,
        operation_id="getSuperGameSeriesState",
        summary="Freshness of the published super game series",
        responses=ERROR_RESPONSES,
    )
    def get_state(
        game_id: UUID,
        service: Annotated[SuperGameSeriesService, service_parameter],
    ) -> SuperGameStateResponse:
        return SuperGameStateResponse.from_domain(service.state(game_id))

    @router.post(
        "/{game_id}/super-game-series/derive",
        response_model=SuperGameSeriesDeriveResponse,
        status_code=status.HTTP_202_ACCEPTED,
        operation_id="deriveSuperGameSeries",
        summary="Queue (or reuse the queued) super game series derivation job",
        responses=ERROR_RESPONSES,
    )
    def derive(
        game_id: UUID,
        service: Annotated[SuperGameSeriesService, service_parameter],
    ) -> SuperGameSeriesDeriveResponse:
        return SuperGameSeriesDeriveResponse.from_domain(service.request_derive(game_id))

    @router.get(
        "/{game_id}/super-game-series/{series_id}/boards",
        response_model=SuperGameSeriesBoardsResponse,
        operation_id="listSuperGameSeriesBoards",
        summary="Boards of one series from the trigger to the last spin",
        responses=ERROR_RESPONSES,
    )
    def boards(
        game_id: UUID,
        series_id: UUID,
        service: Annotated[SuperGameSeriesService, service_parameter],
    ) -> SuperGameSeriesBoardsResponse:
        return SuperGameSeriesBoardsResponse.from_domain(service.boards(game_id, series_id))

    @router.put(
        "/{game_id}/super-game-series/{series_id}/super-symbol",
        response_model=SuperGameSeriesResponse,
        operation_id="setSuperGameSeriesSuperSymbol",
        summary="Define or clear the super symbol of a series (compare-and-set)",
        responses=ERROR_RESPONSES,
    )
    def set_super_symbol(
        game_id: UUID,
        series_id: UUID,
        payload: SuperSymbolUpdate,
        service: Annotated[SuperGameSeriesService, service_parameter],
    ) -> SuperGameSeriesResponse:
        record = service.set_super_symbol(
            game_id,
            series_id,
            symbol_id=payload.symbol_id,
            expected_revision=payload.expected_revision,
            actor=_LOCAL_ADMIN_ACTOR,
        )
        return SuperGameSeriesResponse.from_domain(record)

    return router


__all__ = ["create_super_game_series_router"]
