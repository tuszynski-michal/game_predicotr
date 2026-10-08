"""Read-only API for deterministic partial-board search."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi import Path as ApiPath

from game_predictor_api.application.board_search import BoardSearchService
from game_predictor_api.application.board_search_approximate_win import (
    APPROXIMATE_WIN_SPIN_COUNT_MAX,
    BoardSearchApproximateWinService,
)
from game_predictor_api.application.board_search_board_detail import (
    BoardSearchBoardDetailService,
    BoardSearchBoardViewService,
)
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
from game_predictor_api.schemas.board_search_approximate_win import (
    ApproximateWinResponse,
    BoardSearchBoardDetailResponse,
    BoardSearchBoardRefreshResponse,
    to_approximate_win_response,
    to_board_search_board_detail_response,
)
from game_predictor_api.schemas.catalog import ErrorResponse

BoardSearchServiceDependency = Callable[..., object]
BoardSearchApproximateWinServiceDependency = Callable[..., object]
RULES_VERSION_QUERY = "rulesVersionId"
RULES_VERSION_QUERY_NAMES = frozenset({"rulesversionid", "rules_version_id"})
"""Lower-cased query names of the Admin-only draft preview, refused on the
online share and the management panel (compared with `name.lower()`)."""
RULES_VERSION_QUERY_DESCRIPTION = (
    "Admin-only draft preview (D-535): a draft or published rules version of "
    "this game. Omitted: the latest published rules version."
)
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Game not found"},
    409: {"model": ErrorResponse, "description": "Board-search projection not ready"},
    422: {"model": ErrorResponse, "description": "Invalid partial board query"},
}
APPROXIMATE_WIN_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {
        "model": ErrorResponse,
        "description": "Game, or the selected rules version of this game, not found",
    },
    409: {
        "model": ErrorResponse,
        "description": (
            "Board-search projection not ready, no published rules, an "
            "invalid rules configuration, a board symbol outside the active "
            "rules, or a starting board outside the game's sequence"
        ),
    },
    422: {"model": ErrorResponse, "description": "Invalid range parameters"},
}


BOARD_DETAIL_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Game or board-search document not found"},
    409: {
        "model": ErrorResponse,
        "description": (
            "Projection not ready, no or invalid published rules, a board "
            "symbol outside the rules, or the board changed since the search "
            "document was written"
        ),
    },
    422: {"model": ErrorResponse, "description": "Invalid path parameters"},
}
BOARD_DETAIL_WITH_RULES_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    **BOARD_DETAIL_ERROR_RESPONSES,
    404: {
        "model": ErrorResponse,
        "description": (
            "Game, board-search document or the selected rules version of this game not found"
        ),
    },
}


def create_board_search_router(
    service_dependency: BoardSearchServiceDependency,
    approximate_win_service_dependency: BoardSearchApproximateWinServiceDependency,
    *,
    board_detail_service_dependency: Callable[..., object],
    board_view_service_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(prefix="/admin/games", tags=["board-search"])
    service_parameter = Depends(service_dependency)
    approximate_win_service_parameter = Depends(approximate_win_service_dependency)
    board_detail_service_parameter = Depends(board_detail_service_dependency)
    board_view_service_parameter = Depends(board_view_service_dependency)

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

    @router.get(
        "/{game_id}/board-search/approximate-win",
        response_model=ApproximateWinResponse,
        operation_id="getBoardSearchApproximateWin",
        summary="Calculate a careful, read-only lower-bound payout estimate for a sequence range",
        responses=APPROXIMATE_WIN_ERROR_RESPONSES,
    )
    def get_board_search_approximate_win(
        game_id: UUID,
        service: Annotated[BoardSearchApproximateWinService, approximate_win_service_parameter],
        start_sequence_number: Annotated[int, Query(alias="startSequenceNumber", ge=1)],
        spin_count: Annotated[
            int,
            Query(alias="spinCount", ge=1, le=APPROXIMATE_WIN_SPIN_COUNT_MAX),
        ],
        rules_version_id: Annotated[
            UUID | None,
            Query(alias=RULES_VERSION_QUERY, description=RULES_VERSION_QUERY_DESCRIPTION),
        ] = None,
    ) -> ApproximateWinResponse:
        calculation = service.calculate(
            game_id=game_id,
            start_sequence_number=start_sequence_number,
            requested_spin_count=spin_count,
            rules_version_id=rules_version_id,
        )
        return to_approximate_win_response(calculation)

    @router.get(
        "/{game_id}/board-search/boards/{sequence_number}",
        response_model=BoardSearchBoardDetailResponse,
        operation_id="getBoardSearchBoardDetail",
        summary="Winning paylines, count payouts and cropped-view cell polygons of one board",
        responses=BOARD_DETAIL_WITH_RULES_ERROR_RESPONSES,
    )
    def get_board_search_board_detail(
        game_id: UUID,
        sequence_number: Annotated[int, ApiPath(ge=1)],
        service: Annotated[BoardSearchBoardDetailService, board_detail_service_parameter],
        rules_version_id: Annotated[
            UUID | None,
            Query(alias=RULES_VERSION_QUERY, description=RULES_VERSION_QUERY_DESCRIPTION),
        ] = None,
    ) -> BoardSearchBoardDetailResponse:
        return to_board_search_board_detail_response(
            service.detail(
                game_id=game_id,
                sequence_number=sequence_number,
                rules_version_id=rules_version_id,
            )
        )

    @router.post(
        "/{game_id}/board-search/boards/{sequence_number}/refresh",
        response_model=BoardSearchBoardRefreshResponse,
        operation_id="refreshBoardSearchBoardDocument",
        summary="Rebuild one board's search document from its current records",
        responses=BOARD_DETAIL_ERROR_RESPONSES,
    )
    def refresh_board_search_board_document(
        game_id: UUID,
        sequence_number: Annotated[int, ApiPath(ge=1)],
        service: Annotated[BoardSearchBoardDetailService, board_detail_service_parameter],
    ) -> BoardSearchBoardRefreshResponse:
        result = service.refresh(game_id=game_id, sequence_number=sequence_number)
        return BoardSearchBoardRefreshResponse(
            document_removed=result.document_removed,
            detail=None
            if result.detail is None
            else to_board_search_board_detail_response(result.detail),
        )

    @router.get(
        "/{game_id}/board-search/boards/{sequence_number}/view",
        response_class=Response,
        operation_id="getBoardSearchBoardView",
        summary="Read the checksum-bound cropped WebP view of one board",
        responses=BOARD_DETAIL_ERROR_RESPONSES,
    )
    def get_board_search_board_view(
        game_id: UUID,
        sequence_number: Annotated[int, ApiPath(ge=1)],
        service: Annotated[BoardSearchBoardViewService, board_view_service_parameter],
        expected_checksum_sha256: Annotated[
            str,
            Query(alias="expectedBoardChecksumSha256", pattern=r"^[a-f0-9]{64}$"),
        ],
        view_revision: Annotated[
            str | None,
            Query(alias="viewRevision", pattern=r"^[a-f0-9]{64}$"),
        ] = None,
        if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
    ) -> Response:
        asset = service.view(
            game_id=game_id,
            sequence_number=sequence_number,
            expected_board_checksum_sha256=expected_checksum_sha256,
            expected_view_revision=view_revision,
        )
        etag = f'"{asset.revision}"'
        # Only a URL naming the exact view revision may be cached forever;
        # without it the browser revalidates, so a changed grid is never
        # paired with a stale image.
        headers = {
            "Cache-Control": "private, immutable, max-age=31536000"
            if view_revision is not None
            else "private, no-cache",
            "ETag": etag,
        }
        if if_none_match is not None and etag in {
            value.strip() for value in if_none_match.split(",")
        }:
            return Response(status_code=304, headers=headers)
        return Response(content=asset.content, media_type=asset.media_type, headers=headers)

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


def reject_rules_version_query(request: Request) -> None:
    """Refuse the Admin-only draft preview on shared and management surfaces.

    The online share and the management panel always evaluate the latest
    published rules (D-535); an explicit `rulesVersionId` there is a client
    error, never silently ignored.
    """

    if any(name.lower() in RULES_VERSION_QUERY_NAMES for name in request.query_params):
        raise BoardSearchError(
            "BOARD_SEARCH_RULES_VERSION_NOT_ALLOWED",
            "Selecting a rules version is available only in the local Admin.",
        )


def parse_board_search_cells(values: list[str]) -> tuple[BoardSearchQueryCell, ...]:
    """Parse `cellIndex:symbolCode|?` query values (also used by the online
    share surface, D-471)."""

    return _parse_cells(values)


__all__ = [
    "RULES_VERSION_QUERY",
    "RULES_VERSION_QUERY_NAMES",
    "create_board_search_router",
    "parse_board_search_cells",
    "reject_rules_version_query",
]
