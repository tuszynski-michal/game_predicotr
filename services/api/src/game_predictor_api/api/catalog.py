"""HTTP boundary for the administrative game and symbol catalog."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.schemas.catalog import (
    ErrorResponse,
    GameCreate,
    GameResponse,
    GameUpdate,
    SymbolCreate,
    SymbolResponse,
    SymbolUpdate,
)

CatalogServiceDependency = Callable[..., object]
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Resource not found"},
    409: {"model": ErrorResponse, "description": "Stable code conflict"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}


def create_catalog_router(
    service_dependency: CatalogServiceDependency,
) -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["catalog"])
    service_parameter = Depends(service_dependency)

    @router.get(
        "/games",
        response_model=list[GameResponse],
        operation_id="listGames",
        summary="List games",
    )
    def list_games(
        service: Annotated[CatalogService, service_parameter],
    ) -> list[GameResponse]:
        return [GameResponse.model_validate(game) for game in service.list_games()]

    @router.post(
        "/games",
        response_model=GameResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="createGame",
        summary="Create game",
        responses=ERROR_RESPONSES,
    )
    def create_game(
        payload: GameCreate,
        service: Annotated[CatalogService, service_parameter],
    ) -> GameResponse:
        return GameResponse.model_validate(
            service.create_game(
                code=payload.code,
                name=payload.name,
                status=payload.status,
            )
        )

    @router.get(
        "/games/{game_id}",
        response_model=GameResponse,
        operation_id="getGame",
        summary="Get game",
        responses=ERROR_RESPONSES,
    )
    def get_game(
        game_id: UUID,
        service: Annotated[CatalogService, service_parameter],
    ) -> GameResponse:
        return GameResponse.model_validate(service.get_game(game_id))

    @router.patch(
        "/games/{game_id}",
        response_model=GameResponse,
        operation_id="updateGame",
        summary="Update game",
        responses=ERROR_RESPONSES,
    )
    def update_game(
        game_id: UUID,
        payload: GameUpdate,
        service: Annotated[CatalogService, service_parameter],
    ) -> GameResponse:
        return GameResponse.model_validate(
            service.update_game(
                game_id,
                name=payload.name,
                status=payload.status,
            )
        )

    @router.delete(
        "/games/{game_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        operation_id="archiveGame",
        summary="Archive game",
        responses=ERROR_RESPONSES,
    )
    def archive_game(
        game_id: UUID,
        service: Annotated[CatalogService, service_parameter],
    ) -> Response:
        service.archive_game(game_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get(
        "/games/{game_id}/symbols",
        response_model=list[SymbolResponse],
        operation_id="listSymbols",
        summary="List game symbols",
        responses=ERROR_RESPONSES,
    )
    def list_symbols(
        game_id: UUID,
        service: Annotated[CatalogService, service_parameter],
    ) -> list[SymbolResponse]:
        return [
            SymbolResponse.model_validate(symbol)
            for symbol in service.list_symbols(game_id)
        ]

    @router.post(
        "/games/{game_id}/symbols",
        response_model=SymbolResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="createSymbol",
        summary="Create game symbol",
        responses=ERROR_RESPONSES,
    )
    def create_symbol(
        game_id: UUID,
        payload: SymbolCreate,
        service: Annotated[CatalogService, service_parameter],
    ) -> SymbolResponse:
        return SymbolResponse.model_validate(
            service.create_symbol(
                game_id,
                mobile_code=payload.mobile_code,
                code=payload.code,
                name=payload.name,
                image_path=payload.image_path,
                is_wildcard=payload.is_wildcard,
                display_order=payload.display_order,
                status=payload.status,
            )
        )

    @router.get(
        "/games/{game_id}/symbols/{symbol_id}",
        response_model=SymbolResponse,
        operation_id="getSymbol",
        summary="Get game symbol",
        responses=ERROR_RESPONSES,
    )
    def get_symbol(
        game_id: UUID,
        symbol_id: UUID,
        service: Annotated[CatalogService, service_parameter],
    ) -> SymbolResponse:
        return SymbolResponse.model_validate(service.get_symbol(game_id, symbol_id))

    @router.patch(
        "/games/{game_id}/symbols/{symbol_id}",
        response_model=SymbolResponse,
        operation_id="updateSymbol",
        summary="Update game symbol",
        responses=ERROR_RESPONSES,
    )
    def update_symbol(
        game_id: UUID,
        symbol_id: UUID,
        payload: SymbolUpdate,
        service: Annotated[CatalogService, service_parameter],
    ) -> SymbolResponse:
        return SymbolResponse.model_validate(
            service.update_symbol(
                game_id,
                symbol_id,
                name=payload.name,
                image_path=payload.image_path,
                update_image_path="image_path" in payload.model_fields_set,
                is_wildcard=payload.is_wildcard,
                display_order=payload.display_order,
                status=payload.status,
            )
        )

    @router.delete(
        "/games/{game_id}/symbols/{symbol_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        operation_id="archiveSymbol",
        summary="Archive game symbol",
        responses=ERROR_RESPONSES,
    )
    def archive_symbol(
        game_id: UUID,
        symbol_id: UUID,
        service: Annotated[CatalogService, service_parameter],
    ) -> Response:
        service.archive_symbol(game_id, symbol_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
