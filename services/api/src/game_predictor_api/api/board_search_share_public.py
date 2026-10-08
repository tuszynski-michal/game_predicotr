"""Public board-search reads and scoped symbol corrections (D-492).

Reachable only through the Reviewer proxy (intent header) with the share
cookie. The game always comes from the authenticated session, never from the
request. Search, range and board-detail queries are recorded in the query
log before any data is returned.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, TypeVar
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, Response
from fastapi import Path as ApiPath

from game_predictor_api.api.board_search import (
    RULES_VERSION_QUERY_NAMES,
    parse_board_search_cells,
)
from game_predictor_api.api.symbol_references import resolve_symbol_reference_asset
from game_predictor_api.application.board_search import BoardSearchService
from game_predictor_api.application.board_search_approximate_win import (
    APPROXIMATE_WIN_SPIN_COUNT_MAX,
    BoardSearchApproximateWinService,
)
from game_predictor_api.application.board_search_board_detail import (
    BoardSearchBoardDetailService,
    BoardSearchBoardViewService,
)
from game_predictor_api.application.board_search_share_access import (
    BoardSearchShareAccessService,
    BoardSearchShareContext,
)
from game_predictor_api.application.board_search_share_corrections import (
    BoardSearchShareCorrectionService,
    ShareCellCorrectionCommand,
    share_cell_version,
)
from game_predictor_api.application.board_search_share_queries import (
    BoardSearchShareQueryLog,
    BoardSearchShareRateLimiter,
    BoardSearchShareRequestKind,
    record_board_search_share_query,
)
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.application.symbol_references import ApprovedSymbolReferenceService
from game_predictor_api.domain.board_search import BoardSearchScope, validate_board_search_query
from game_predictor_api.domain.board_search_share_queries import (
    QUERY_OUTCOME_OK,
    QUERY_STAKE_GROSZE_MAX,
    BoardSearchShareQueryKind,
    approximate_win_query_request,
    approximate_win_query_summary,
    approximate_win_stake_query_request,
    board_detail_query_request,
    board_detail_query_summary,
    build_board_search_share_query_entry,
    search_query_request,
    search_query_summary,
)
from game_predictor_api.domain.board_search_shares import (
    BOARD_SEARCH_SHARE_COOKIE_NAME,
    BOARD_SEARCH_SHARE_COOKIE_PATH,
    BOARD_SEARCH_SHARE_PROXY_HEADER,
    BOARD_SEARCH_SHARE_PROXY_INTENT,
    BoardSearchShareAuthenticationError,
    BoardSearchShareAuthorizationError,
    BoardSearchShareConflictError,
    BoardSearchShareError,
)
from game_predictor_api.domain.catalog import CatalogNotFoundError, SymbolStatus
from game_predictor_api.schemas.board_search import to_board_search_response
from game_predictor_api.schemas.board_search_approximate_win import (
    ApproximateWinResponse,
    to_approximate_win_response,
    to_board_search_board_detail_response,
)
from game_predictor_api.schemas.board_search_shares import (
    BoardSearchShareCellCorrectionRequest,
    BoardSearchShareCellCorrectionResponse,
    BoardSearchSharePublicBoardDetailResponse,
    BoardSearchSharePublicCellResponse,
    BoardSearchSharePublicContextResponse,
    BoardSearchSharePublicSearchResponse,
    BoardSearchSharePublicSymbolResponse,
    BoardSearchShareStakeRecordedResponse,
    BoardSearchShareUnlock,
    to_board_search_share_public_search_response,
)
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.storage.game_storage_routing import game_storage_scope

_T = TypeVar("_T")
# Recipients' browsers may keep images for a day (§4.5); the URLs are bound
# to checksums, so a changed image always gets a new URL.
IMAGE_CACHE_CONTROL = "private, immutable, max-age=86400"
# The game comes only from the session, and the rules are always the
# latest published version: the Admin-only draft preview (`rulesVersionId`,
# TASK-0932) is refused here like a game parameter.
_FORBIDDEN_QUERY_PARAMETERS = frozenset({"gameid", "game_id", *RULES_VERSION_QUERY_NAMES})
# `cellIndex:` (up to 3 characters) plus a catalog symbol code (up to 64).
_MAX_CELL_VALUE_LENGTH = 3 + 64

PUBLIC_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Missing, invalid or expired share access"},
    403: {"model": ErrorResponse, "description": "Not requested through the Reviewer proxy"},
    404: {"model": ErrorResponse, "description": "Board or symbol not found"},
    409: {"model": ErrorResponse, "description": "Data not ready or changed"},
    422: {"model": ErrorResponse, "description": "Invalid parameters"},
    429: {"model": ErrorResponse, "description": "Request limit reached"},
    503: {"model": ErrorResponse, "description": "Sharing disabled or query log unavailable"},
}


def create_board_search_share_public_router(
    *,
    access_service_dependency: Callable[..., object],
    catalog_service_dependency: Callable[..., object],
    symbol_reference_service_dependency: Callable[..., object],
    search_service_dependency: Callable[..., object],
    approximate_win_service_dependency: Callable[..., object],
    board_detail_service_dependency: Callable[..., object],
    board_view_service_dependency: Callable[..., object],
    correction_service_dependency: Callable[..., object],
    query_log: BoardSearchShareQueryLog,
    rate_limiter: BoardSearchShareRateLimiter,
    artifact_root: Path,
) -> APIRouter:
    router = APIRouter(
        prefix="/board-search-shares",
        tags=["board-search-share-public"],
        dependencies=[Depends(_require_share_proxy), Depends(_reject_game_parameter)],
    )
    access_parameter = Depends(access_service_dependency)
    catalog_parameter = Depends(catalog_service_dependency)
    symbol_reference_parameter = Depends(symbol_reference_service_dependency)
    search_parameter = Depends(search_service_dependency)
    approximate_win_parameter = Depends(approximate_win_service_dependency)
    board_detail_parameter = Depends(board_detail_service_dependency)
    board_view_parameter = Depends(board_view_service_dependency)
    correction_parameter = Depends(correction_service_dependency, scope="function")
    token_cookie = Cookie(alias=BOARD_SEARCH_SHARE_COOKIE_NAME)

    def authenticate(
        service: BoardSearchShareAccessService,
        access_token: str | None,
        kind: BoardSearchShareRequestKind,
    ) -> BoardSearchShareContext:
        if access_token is None or not access_token.strip():
            raise BoardSearchShareAuthenticationError(
                "BOARD_SEARCH_SHARE_TOKEN_REQUIRED", "Enter the access code first."
            )
        context = service.authenticate(access_token)
        rate_limiter.consume(context.session_id, kind)
        return context

    def logged(
        context: BoardSearchShareContext,
        kind: BoardSearchShareQueryKind,
        request: dict[str, object],
        compute: Callable[[], _T],
        summarize: Callable[[_T], dict[str, object]],
        *,
        on_recorded: Callable[[UUID | None], None] | None = None,
    ) -> _T:
        """Run one data query in the session's game scope and record it;
        a failed query is recorded with its stable error code."""

        # Validate the entry before the query runs: a request that cannot be
        # recorded must never read data (fail-closed, R5).
        try:
            build_board_search_share_query_entry(
                kind=kind, request=request, result_summary=None, outcome_code=QUERY_OUTCOME_OK
            )
        except ValueError as error:
            raise BoardSearchShareError(
                "BOARD_SEARCH_SHARE_QUERY_INVALID",
                "The query is too large or malformed to be recorded.",
            ) from error
        try:
            with game_storage_scope(context.game_id):
                result = compute()
        except Exception as error:
            code = getattr(error, "code", None)
            record_board_search_share_query(
                query_log,
                context=context,
                entry=build_board_search_share_query_entry(
                    kind=kind,
                    request=request,
                    result_summary=None,
                    outcome_code=code if isinstance(code, str) and code else "INTERNAL_ERROR",
                ),
            )
            raise
        event_id = record_board_search_share_query(
            query_log,
            context=context,
            entry=build_board_search_share_query_entry(
                kind=kind,
                request=request,
                result_summary=summarize(result),
                outcome_code=QUERY_OUTCOME_OK,
            ),
        )
        if on_recorded is not None:
            on_recorded(event_id)
        return result

    @router.post(
        "/sessions/{session_id}/unlock",
        response_model=BoardSearchSharePublicContextResponse,
        operation_id="unlockBoardSearchShareSession",
        summary="Exchange a share link's access code for a session cookie",
        responses=PUBLIC_ERROR_RESPONSES,
    )
    def unlock_session(
        session_id: UUID,
        payload: BoardSearchShareUnlock,
        response: Response,
        service: Annotated[BoardSearchShareAccessService, access_parameter],
        catalog: Annotated[CatalogService, catalog_parameter],
    ) -> BoardSearchSharePublicContextResponse:
        unlocked = service.unlock(session_id=session_id, access_code=payload.access_code)
        context = unlocked.context
        max_age = max(0, int((context.expires_at - datetime.now(UTC)).total_seconds()))
        response.set_cookie(
            key=BOARD_SEARCH_SHARE_COOKIE_NAME,
            value=unlocked.access_token,
            max_age=max_age,
            expires=context.expires_at,
            path=BOARD_SEARCH_SHARE_COOKIE_PATH,
            secure=True,
            httponly=True,
            samesite="strict",
        )
        return _context_response(context, catalog)

    @router.get(
        "/context",
        response_model=BoardSearchSharePublicContextResponse,
        operation_id="getBoardSearchShareContext",
        summary="Read the authenticated share context",
        responses=PUBLIC_ERROR_RESPONSES,
    )
    def get_context(
        service: Annotated[BoardSearchShareAccessService, access_parameter],
        catalog: Annotated[CatalogService, catalog_parameter],
        access_token: Annotated[str | None, token_cookie] = None,
    ) -> BoardSearchSharePublicContextResponse:
        context = authenticate(service, access_token, BoardSearchShareRequestKind.JSON)
        return _context_response(context, catalog)

    @router.get(
        "/symbols",
        response_model=list[BoardSearchSharePublicSymbolResponse],
        operation_id="listBoardSearchShareSymbols",
        summary="List the shared game's symbols",
        responses=PUBLIC_ERROR_RESPONSES,
    )
    def list_symbols(
        service: Annotated[BoardSearchShareAccessService, access_parameter],
        catalog: Annotated[CatalogService, catalog_parameter],
        references: Annotated[ApprovedSymbolReferenceService, symbol_reference_parameter],
        access_token: Annotated[str | None, token_cookie] = None,
    ) -> list[BoardSearchSharePublicSymbolResponse]:
        context = authenticate(service, access_token, BoardSearchShareRequestKind.JSON)
        with game_storage_scope(context.game_id):
            symbols = catalog.list_symbols(context.game_id)
            return [
                BoardSearchSharePublicSymbolResponse(
                    id=symbol.id,
                    mobile_code=symbol.mobile_code,
                    code=symbol.code,
                    name=symbol.name,
                    name_pl=symbol.name_pl,
                    name_en=symbol.name_en,
                    is_wildcard=symbol.is_wildcard,
                    display_order=symbol.display_order,
                    status=symbol.status.value
                    if isinstance(symbol.status, SymbolStatus)
                    else str(symbol.status),
                    image_revision=(
                        _image_revision(references, context.game_id, symbol.id)
                        if symbol.image_path
                        else None
                    ),
                )
                for symbol in symbols
            ]

    @router.get(
        "/symbols/{symbol_id}/image",
        response_class=Response,
        operation_id="getBoardSearchShareSymbolImage",
        summary="Read one checksum-bound symbol image of the shared game",
        responses=PUBLIC_ERROR_RESPONSES,
    )
    def get_symbol_image(
        symbol_id: UUID,
        service: Annotated[BoardSearchShareAccessService, access_parameter],
        references: Annotated[ApprovedSymbolReferenceService, symbol_reference_parameter],
        revision: Annotated[str, Query(pattern=r"^[a-f0-9]{64}$")],
        access_token: Annotated[str | None, token_cookie] = None,
    ) -> Response:
        context = authenticate(service, access_token, BoardSearchShareRequestKind.IMAGE)
        with game_storage_scope(context.game_id):
            reference = references.reference(context.game_id, symbol_id)
        if reference.image_checksum_sha256 != revision:
            raise BoardSearchShareConflictError(
                "BOARD_SEARCH_SHARE_SYMBOL_IMAGE_CHANGED",
                "The symbol image changed; reload the symbols.",
            )
        path = resolve_symbol_reference_asset(
            artifact_root, reference.image_relative_path, reference.image_checksum_sha256
        )
        media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        return Response(
            content=path.read_bytes(),
            media_type=media_type,
            headers={"Cache-Control": IMAGE_CACHE_CONTROL},
        )

    @router.get(
        "/search",
        response_model=BoardSearchSharePublicSearchResponse,
        operation_id="searchBoardSearchShareBoards",
        summary="Find boards of the shared game by a partial symbol pattern",
        responses=PUBLIC_ERROR_RESPONSES,
    )
    def search_boards(
        service: Annotated[BoardSearchShareAccessService, access_parameter],
        search: Annotated[BoardSearchService, search_parameter],
        cell: Annotated[list[str] | None, Query(alias="cell")] = None,
        scope: BoardSearchScope = BoardSearchScope.ALL_SEARCHABLE,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
        access_token: Annotated[str | None, token_cookie] = None,
    ) -> BoardSearchSharePublicSearchResponse:
        context = authenticate(service, access_token, BoardSearchShareRequestKind.JSON)
        values = cell or []
        # A board has 15 cells and symbol codes have at most 64 characters;
        # anything longer is refused before parsing or searching.
        if len(values) > 15 or any(len(value) > _MAX_CELL_VALUE_LENGTH for value in values):
            raise BoardSearchShareError(
                "BOARD_SEARCH_SHARE_QUERY_INVALID",
                "The pattern has too many or too long cells.",
            )
        supplied = parse_board_search_cells(values)
        query = validate_board_search_query(supplied)
        # The log keeps the whole pattern, including `?` cells that carry no
        # evidence and are dropped from scoring, so a replay restores it (R5).
        request = search_query_request(
            cells=[(item.cell_index, item.symbol_code) for item in supplied],
            scope=scope.value,
            limit=limit,
        )
        context_ids: list[UUID | None] = []
        results = logged(
            context,
            BoardSearchShareQueryKind.SEARCH,
            request,
            lambda: search.search(game_id=context.game_id, cells=query, scope=scope, limit=limit),
            lambda found: search_query_summary([result.sequence_number for result in found]),
            on_recorded=context_ids.append,
        )
        response = to_board_search_share_public_search_response(
            to_board_search_response(
                game_id=context.game_id,
                scope=scope,
                query_cell_count=len(query),
                results=results,
            )
        )
        response.search_context_id = context_ids[0]
        return response

    @router.get(
        "/approximate-win",
        response_model=ApproximateWinResponse,
        operation_id="getBoardSearchShareApproximateWin",
        summary="Calculate the approximate win for a range of the shared game",
        responses=PUBLIC_ERROR_RESPONSES,
    )
    def get_approximate_win(
        service: Annotated[BoardSearchShareAccessService, access_parameter],
        approximate_win: Annotated[BoardSearchApproximateWinService, approximate_win_parameter],
        start_sequence_number: Annotated[int, Query(alias="startSequenceNumber", ge=1)],
        spin_count: Annotated[
            int, Query(alias="spinCount", ge=1, le=APPROXIMATE_WIN_SPIN_COUNT_MAX)
        ],
        access_token: Annotated[str | None, token_cookie] = None,
    ) -> ApproximateWinResponse:
        context = authenticate(service, access_token, BoardSearchShareRequestKind.JSON)
        rate_limiter.consume(context.session_id, BoardSearchShareRequestKind.APPROXIMATE_WIN)
        with rate_limiter.calculation_slot(context.session_id):
            calculation = logged(
                context,
                BoardSearchShareQueryKind.APPROXIMATE_WIN,
                approximate_win_query_request(
                    start_sequence_number=start_sequence_number, spin_count=spin_count
                ),
                lambda: approximate_win.calculate(
                    game_id=context.game_id,
                    start_sequence_number=start_sequence_number,
                    requested_spin_count=spin_count,
                ),
                lambda value: approximate_win_query_summary(
                    evaluated_spin_count=value.result.evaluated_spin_count,
                    recognized_payout_credits=value.result.summary.recognized_payout_credits,
                    spin_cost_credits=value.result.summary.spin_cost_credits,
                    balance_credits=value.result.summary.balance_credits,
                    row_count=len(value.result.rows),
                ),
            )
        return to_approximate_win_response(calculation)

    @router.get(
        "/approximate-win/stake",
        response_model=BoardSearchShareStakeRecordedResponse,
        operation_id="recordBoardSearchShareApproximateWinStake",
        summary="Record the stake the recipient views a calculated range at (D-487)",
        responses=PUBLIC_ERROR_RESPONSES,
    )
    def record_approximate_win_stake(
        service: Annotated[BoardSearchShareAccessService, access_parameter],
        start_sequence_number: Annotated[int, Query(alias="startSequenceNumber", ge=1)],
        spin_count: Annotated[
            int, Query(alias="spinCount", ge=1, le=APPROXIMATE_WIN_SPIN_COUNT_MAX)
        ],
        stake_grosze: Annotated[
            int | None,
            Query(
                alias="stakeGrosze",
                ge=1,
                le=QUERY_STAKE_GROSZE_MAX,
                description="Omitted: the base stake of the published rules.",
            ),
        ] = None,
        access_token: Annotated[str | None, token_cookie] = None,
    ) -> BoardSearchShareStakeRecordedResponse:
        # Like every recorded query of this surface it is a GET: the proxy
        # forwards an exact allowlist of read routes. Nothing is calculated.
        context = authenticate(service, access_token, BoardSearchShareRequestKind.JSON)
        record_board_search_share_query(
            query_log,
            context=context,
            entry=build_board_search_share_query_entry(
                kind=BoardSearchShareQueryKind.APPROXIMATE_WIN,
                request=approximate_win_stake_query_request(
                    start_sequence_number=start_sequence_number,
                    spin_count=spin_count,
                    stake_grosze=stake_grosze,
                ),
                result_summary=None,
                outcome_code=QUERY_OUTCOME_OK,
            ),
        )
        return BoardSearchShareStakeRecordedResponse()

    @router.get(
        "/boards/{sequence_number}",
        response_model=BoardSearchSharePublicBoardDetailResponse,
        operation_id="getBoardSearchShareBoardDetail",
        summary="Winning paylines and opaque editable cells of one shared board",
        responses=PUBLIC_ERROR_RESPONSES,
    )
    def get_board_detail(
        sequence_number: Annotated[int, ApiPath(ge=1)],
        service: Annotated[BoardSearchShareAccessService, access_parameter],
        detail_service: Annotated[BoardSearchBoardDetailService, board_detail_parameter],
        access_token: Annotated[str | None, token_cookie] = None,
    ) -> BoardSearchSharePublicBoardDetailResponse:
        context = authenticate(service, access_token, BoardSearchShareRequestKind.JSON)
        detail = logged(
            context,
            BoardSearchShareQueryKind.BOARD_DETAIL,
            board_detail_query_request(sequence_number=sequence_number),
            lambda: detail_service.detail(
                game_id=context.game_id,
                sequence_number=sequence_number,
                include_cells=True,
            ),
            lambda value: board_detail_query_summary(
                payout_credits=value.payout_credits, document_stale=value.document_stale
            ),
        )
        response = to_board_search_board_detail_response(detail)
        return BoardSearchSharePublicBoardDetailResponse(
            **response.model_dump(exclude={"cells"}),
            cells=None
            if detail.cells is None
            else tuple(
                BoardSearchSharePublicCellResponse(
                    cell_index=cell.cell_index,
                    cell_version=share_cell_version(context.game_id, sequence_number, cell),
                    assigned_symbol_code=cell.assigned_symbol_code,
                    review_state=cell.review_state,
                    quality_issue=cell.quality_issue,
                )
                for cell in detail.cells
            ),
        )

    @router.post(
        "/boards/{sequence_number}/cells/{cell_index}/decision",
        response_model=BoardSearchShareCellCorrectionResponse,
        operation_id="correctBoardSearchShareCell",
        summary="Apply and atomically audit one share-scoped symbol correction",
        responses=PUBLIC_ERROR_RESPONSES,
    )
    def correct_cell(
        sequence_number: Annotated[int, ApiPath(ge=1)],
        cell_index: Annotated[int, ApiPath(ge=0, le=14)],
        payload: BoardSearchShareCellCorrectionRequest,
        access: Annotated[BoardSearchShareAccessService, access_parameter],
        corrections: Annotated[BoardSearchShareCorrectionService, correction_parameter],
        access_token: Annotated[str | None, token_cookie] = None,
    ) -> BoardSearchShareCellCorrectionResponse:
        context = authenticate(access, access_token, BoardSearchShareRequestKind.JSON)
        assert access_token is not None
        with game_storage_scope(context.game_id):
            receipt = corrections.correct(
                context,
                access_token,
                ShareCellCorrectionCommand(
                    sequence_number=sequence_number,
                    cell_index=cell_index,
                    operation_id=payload.operation_id,
                    expected_cell_version=payload.expected_cell_version,
                    action=payload.action,
                    target_symbol_code=payload.target_symbol_code,
                    search_context_id=payload.search_context_id,
                    start_sequence_number=payload.start_sequence_number,
                    spin_count=payload.spin_count,
                    stake_grosze=payload.stake_grosze,
                ),
            )
        return BoardSearchShareCellCorrectionResponse.from_receipt(receipt)

    @router.get(
        "/boards/{sequence_number}/view",
        response_class=Response,
        operation_id="getBoardSearchShareBoardView",
        summary="Read the checksum-bound cropped view of one board of the shared game",
        responses=PUBLIC_ERROR_RESPONSES,
    )
    def get_board_view(
        sequence_number: Annotated[int, ApiPath(ge=1)],
        service: Annotated[BoardSearchShareAccessService, access_parameter],
        view_service: Annotated[BoardSearchBoardViewService, board_view_parameter],
        expected_checksum_sha256: Annotated[
            str, Query(alias="expectedBoardChecksumSha256", pattern=r"^[a-f0-9]{64}$")
        ],
        view_revision: Annotated[
            str | None, Query(alias="viewRevision", pattern=r"^[a-f0-9]{64}$")
        ] = None,
        if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
        access_token: Annotated[str | None, token_cookie] = None,
    ) -> Response:
        context = authenticate(service, access_token, BoardSearchShareRequestKind.IMAGE)
        with game_storage_scope(context.game_id):
            asset = view_service.view(
                game_id=context.game_id,
                sequence_number=sequence_number,
                expected_board_checksum_sha256=expected_checksum_sha256,
                expected_view_revision=view_revision,
            )
        etag = f'"{asset.revision}"'
        headers = {
            "Cache-Control": IMAGE_CACHE_CONTROL
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


def _context_response(
    context: BoardSearchShareContext, catalog: CatalogService
) -> BoardSearchSharePublicContextResponse:
    with game_storage_scope(context.game_id):
        game = catalog.get_game(context.game_id)
    return BoardSearchSharePublicContextResponse(
        session_id=context.session_id,
        label=context.label,
        game_name=game.name,
        expires_at=context.expires_at,
    )


def _image_revision(
    references: ApprovedSymbolReferenceService, game_id: UUID, symbol_id: UUID
) -> str | None:
    try:
        return references.reference(game_id, symbol_id).image_checksum_sha256
    except CatalogNotFoundError:
        return None


def _require_share_proxy(
    proxy_intent: Annotated[str | None, Header(alias=BOARD_SEARCH_SHARE_PROXY_HEADER)] = None,
) -> None:
    if proxy_intent != BOARD_SEARCH_SHARE_PROXY_INTENT:
        raise BoardSearchShareAuthorizationError(
            "BOARD_SEARCH_SHARE_PROXY_REQUIRED",
            "The share is available only through the Reviewer application.",
        )


def _reject_game_parameter(request: Request) -> None:
    """The game comes only from the session and the rules are the latest
    published version; a request naming either is refused instead of
    silently ignored."""

    if any(name.lower() in _FORBIDDEN_QUERY_PARAMETERS for name in request.query_params):
        raise BoardSearchShareError(
            "BOARD_SEARCH_SHARE_PARAMETER_FORBIDDEN",
            "The shared game and its rules are fixed by the link and cannot be chosen.",
        )


__all__ = ["IMAGE_CACHE_CONTROL", "create_board_search_share_public_router"]
