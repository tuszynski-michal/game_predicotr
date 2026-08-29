"""Read-only API for deterministic partial-board search."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from game_predictor_api.application.board_search import BoardSearchService
from game_predictor_api.domain.board_search import (
    BoardSearchError,
    BoardSearchQueryCell,
    BoardSearchScope,
    validate_board_search_query,
)
from game_predictor_api.schemas.board_search import (
    BoardSearchResponse,
    to_board_search_response,
)
from game_predictor_api.schemas.catalog import ErrorResponse

BoardSearchServiceDependency = Callable[..., object]
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Game not found"},
    409: {"model": ErrorResponse, "description": "Board-search projection not ready"},
    422: {"model": ErrorResponse, "description": "Invalid partial board query"},
}


def create_board_search_router(
    service_dependency: BoardSearchServiceDependency,
) -> APIRouter:
    router = APIRouter(prefix="/admin/games", tags=["board-search"])
    service_parameter = Depends(service_dependency)

    @router.get(
        "/{game_id}/board-search",
        response_model=BoardSearchResponse,
        operation_id="searchGameBoards",
        summary="Find logical boards by a partial symbol pattern",
        responses=ERROR_RESPONSES,
    )
    def search_game_boards(
        game_id: UUID,
        service: Annotated[BoardSearchService, service_parameter],
        cell: Annotated[list[str] | None, Query(alias="cell")] = None,
        scope: BoardSearchScope = BoardSearchScope.ALL_SEARCHABLE,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
    ) -> BoardSearchResponse:
        query = validate_board_search_query(_parse_cells(cell or []))
        results = service.search(
            game_id=game_id,
            cells=query,
            scope=scope,
            limit=limit,
        )
        return to_board_search_response(
            game_id=game_id,
            scope=scope,
            query_cell_count=len(query),
            results=results,
        )

    return router


def _parse_cells(values: list[str]) -> tuple[BoardSearchQueryCell, ...]:
    parsed: list[BoardSearchQueryCell] = []
    for value in values:
        index_text, separator, symbol_code = value.partition(":")
        if not separator or not symbol_code:
            raise BoardSearchError(
                "BOARD_SEARCH_CELL_INVALID",
                "Each board-search cell must use the form cellIndex:symbolCode.",
            )
        try:
            cell_index = int(index_text)
        except ValueError as error:
            raise BoardSearchError(
                "BOARD_SEARCH_CELL_INVALID",
                "Each board-search cell index must be an integer between 0 and 14.",
            ) from error
        parsed.append(
            BoardSearchQueryCell(
                cell_index=cell_index,
                symbol_code=None if symbol_code == "?" else symbol_code,
            )
        )
    return tuple(parsed)


__all__ = ["create_board_search_router"]
