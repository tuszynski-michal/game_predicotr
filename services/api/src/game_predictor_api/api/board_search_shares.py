"""Local Admin routes for online board-search share sessions (D-471)."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import Response

from game_predictor_api.application.board_search_share_access import (
    SESSION_LIST_LIMIT_MAX,
    BoardSearchShareAccessService,
)
from game_predictor_api.application.board_search_share_corrections import (
    BoardSearchShareCorrectionService,
    CorrectionStatus,
)
from game_predictor_api.application.board_search_share_queries import (
    BoardSearchShareQueryLogService,
)
from game_predictor_api.application.reviewer_ingress import (
    ReviewerIngressError,
    ReviewerIngressService,
    ReviewerIngressStatus,
    ensure_online_reviewer_ingress,
)
from game_predictor_api.domain.board_search_share_queries import (
    QUERY_LOG_PAGE_SIZE_MAX,
    BoardSearchShareQueryKind,
)
from game_predictor_api.schemas.board_search_shares import (
    BoardSearchShareCorrectionBoardResponse,
    BoardSearchShareCorrectionChangeResponse,
    BoardSearchShareCorrectionDetailResponse,
    BoardSearchShareCorrectionPageResponse,
    BoardSearchShareCorrectionReviewRequest,
    BoardSearchShareCreate,
    BoardSearchShareCreatedResponse,
    BoardSearchShareQueryEntryResponse,
    BoardSearchShareQueryPageResponse,
    BoardSearchShareQueryReplayResponse,
    BoardSearchShareSessionListResponse,
    BoardSearchShareSessionResponse,
)
from game_predictor_api.schemas.catalog import ErrorResponse


def create_board_search_shares_admin_router(
    access_service_dependency: Callable[..., object],
    ingress_service_dependency: Callable[..., object],
    query_log_service_dependency: Callable[..., object],
    correction_service_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(prefix="/admin/board-search-shares")
    access_service_parameter = Depends(access_service_dependency)
    ingress_service_parameter = Depends(ingress_service_dependency)
    query_log_parameter = Depends(query_log_service_dependency)
    correction_parameter = Depends(correction_service_dependency, scope="function")

    @router.get(
        "/sessions/{session_id}/corrections",
        response_model=BoardSearchShareCorrectionPageResponse,
        operation_id="listBoardSearchShareCorrections",
        tags=["board-search-shares"],
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def list_corrections(
        session_id: UUID,
        service: Annotated[BoardSearchShareCorrectionService, correction_parameter],
        status: CorrectionStatus = "pending",
        before: Annotated[str | None, Query(max_length=256)] = None,
        limit: Annotated[int, Query(ge=1, le=50)] = 25,
        pattern: Annotated[list[str] | None, Query(max_length=15)] = None,
    ) -> BoardSearchShareCorrectionPageResponse:
        page = service.list_boards(
            session_id, status=status, before=before, limit=limit, pattern=pattern
        )
        return BoardSearchShareCorrectionPageResponse(
            entries=[
                BoardSearchShareCorrectionBoardResponse.from_board(item) for item in page.entries
            ],
            next_cursor=page.next_cursor,
            total_count=page.total_count,
            pending_count=page.pending_count,
        )

    @router.get(
        "/sessions/{session_id}/corrections/{sequence_number}",
        response_model=BoardSearchShareCorrectionDetailResponse,
        operation_id="getBoardSearchShareCorrection",
        tags=["board-search-shares"],
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def correction_detail(
        session_id: UUID,
        sequence_number: Annotated[int, Path(ge=1)],
        service: Annotated[BoardSearchShareCorrectionService, correction_parameter],
        before: Annotated[str | None, Query(max_length=256)] = None,
        limit: Annotated[int, Query(ge=1, le=50)] = 50,
    ) -> BoardSearchShareCorrectionDetailResponse:
        detail = service.detail(session_id, sequence_number, before=before, limit=limit)
        return BoardSearchShareCorrectionDetailResponse(
            board=BoardSearchShareCorrectionBoardResponse.from_board(detail.board),
            board_version=detail.board_version,
            changes=[
                BoardSearchShareCorrectionChangeResponse.from_change(item)
                for item in detail.changes
            ],
            next_cursor=detail.next_cursor,
        )

    @router.post(
        "/sessions/{session_id}/corrections/{sequence_number}/review",
        response_model=BoardSearchShareCorrectionBoardResponse,
        operation_id="reviewBoardSearchShareCorrection",
        tags=["board-search-shares"],
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def review_correction(
        session_id: UUID,
        sequence_number: Annotated[int, Path(ge=1)],
        payload: BoardSearchShareCorrectionReviewRequest,
        service: Annotated[BoardSearchShareCorrectionService, correction_parameter],
    ) -> BoardSearchShareCorrectionBoardResponse:
        return BoardSearchShareCorrectionBoardResponse.from_board(
            service.review(
                session_id,
                sequence_number,
                expected_revision=payload.expected_revision,
                expected_board_version=payload.expected_board_version,
            )
        )

    @router.post(
        "/sessions",
        response_model=BoardSearchShareCreatedResponse,
        status_code=201,
        operation_id="createBoardSearchShareSession",
        summary="Create one online board-search share link with symbol correction",
        tags=["board-search-shares"],
        responses={
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    def create_session(
        payload: BoardSearchShareCreate,
        service: Annotated[BoardSearchShareAccessService, access_service_parameter],
        ingress: Annotated[ReviewerIngressService, ingress_service_parameter],
    ) -> BoardSearchShareCreatedResponse:
        # Validate everything first so an invalid request never starts the
        # public ingress; `create` repeats the checks inside its transaction.
        service.assert_can_create(
            game_id=payload.game_id,
            lifetime_minutes=payload.lifetime_minutes,
            label=payload.label,
        )
        ingress_status = ensure_online_reviewer_ingress(ingress)
        return BoardSearchShareCreatedResponse.from_created(
            service.create(
                game_id=payload.game_id,
                lifetime_minutes=payload.lifetime_minutes,
                label=payload.label,
            ),
            ingress_status,
        )

    @router.get(
        "/sessions",
        response_model=BoardSearchShareSessionListResponse,
        operation_id="listBoardSearchShareSessions",
        summary="List board-search share sessions without secrets",
        tags=["board-search-shares"],
    )
    def list_sessions(
        service: Annotated[BoardSearchShareAccessService, access_service_parameter],
        ingress: Annotated[ReviewerIngressService, ingress_service_parameter],
        game_id: Annotated[UUID | None, Query(alias="gameId")] = None,
        limit: Annotated[int, Query(ge=1, le=SESSION_LIST_LIMIT_MAX)] = SESSION_LIST_LIMIT_MAX,
    ) -> BoardSearchShareSessionListResponse:
        # The list is also where links are stopped: an unreadable ingress
        # status only hides the share URLs, it never hides the links.
        ingress_status: ReviewerIngressStatus | None
        try:
            ingress_status = ingress.status()
        except ReviewerIngressError:
            ingress_status = None
        return BoardSearchShareSessionListResponse(
            sessions=[
                BoardSearchShareSessionResponse.from_view(item, ingress_status)
                for item in service.list_sessions(game_id=game_id, limit=limit)
            ]
        )

    @router.post(
        "/sessions/{session_id}/revoke",
        response_model=BoardSearchShareSessionResponse,
        operation_id="revokeBoardSearchShareSession",
        summary="Immediately stop one board-search share link",
        tags=["board-search-shares"],
        responses={404: {"model": ErrorResponse}},
    )
    def revoke_session(
        session_id: UUID,
        service: Annotated[BoardSearchShareAccessService, access_service_parameter],
    ) -> BoardSearchShareSessionResponse:
        # A safety stop must not depend on the optional public ingress.
        return BoardSearchShareSessionResponse.from_view(service.revoke(session_id), None)

    @router.get(
        "/sessions/{session_id}/queries",
        response_model=BoardSearchShareQueryPageResponse,
        operation_id="listBoardSearchShareQueries",
        summary="Read a share link's query log, newest first (D-472)",
        tags=["board-search-shares"],
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def list_queries(
        session_id: UUID,
        service: Annotated[BoardSearchShareQueryLogService, query_log_parameter],
        before: Annotated[str | None, Query(max_length=256)] = None,
        limit: Annotated[int, Query(ge=1, le=QUERY_LOG_PAGE_SIZE_MAX)] = QUERY_LOG_PAGE_SIZE_MAX,
        kind: Annotated[BoardSearchShareQueryKind | None, Query()] = None,
        group_by_pattern: Annotated[
            bool,
            Query(
                alias="groupByPattern",
                description="With `kind=search`: one entry per searched pattern.",
            ),
        ] = False,
    ) -> BoardSearchShareQueryPageResponse:
        page = service.list(
            session_id=session_id,
            before_cursor=before,
            limit=limit,
            kind=kind,
            group_by_pattern=group_by_pattern,
        )
        return BoardSearchShareQueryPageResponse(
            entries=[BoardSearchShareQueryEntryResponse.from_event(item) for item in page.entries],
            next_cursor=page.next_cursor,
        )

    @router.get(
        "/queries/{event_id}",
        response_model=BoardSearchShareQueryReplayResponse,
        operation_id="getBoardSearchShareQueryReplay",
        summary="Read one query log entry with what is needed to replay it",
        tags=["board-search-shares"],
        responses={404: {"model": ErrorResponse}},
    )
    def get_query_replay(
        event_id: UUID,
        service: Annotated[BoardSearchShareQueryLogService, query_log_parameter],
    ) -> BoardSearchShareQueryReplayResponse:
        return BoardSearchShareQueryReplayResponse.from_replay(service.replay(event_id))

    @router.delete(
        "/queries/{event_id}",
        status_code=204,
        operation_id="deleteBoardSearchShareQuery",
        summary="Delete one query log entry; a search takes its follow-up entries with it",
        tags=["board-search-shares"],
        responses={404: {"model": ErrorResponse}},
    )
    def delete_query(
        event_id: UUID,
        service: Annotated[BoardSearchShareQueryLogService, query_log_parameter],
        whole_pattern: Annotated[
            bool,
            Query(
                alias="wholePattern",
                description="For a search: delete every search of the same pattern.",
            ),
        ] = False,
    ) -> Response:
        service.delete(event_id, whole_pattern=whole_pattern)
        return Response(status_code=204)

    return router


__all__ = ["create_board_search_shares_admin_router"]
