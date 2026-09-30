"""Local Admin routes for online board-search share sessions (D-471)."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from game_predictor_api.application.board_search_share_access import (
    SESSION_LIST_LIMIT_MAX,
    BoardSearchShareAccessService,
)
from game_predictor_api.application.reviewer_ingress import (
    ReviewerIngressService,
    ensure_online_reviewer_ingress,
)
from game_predictor_api.schemas.board_search_shares import (
    BoardSearchShareCreate,
    BoardSearchShareCreatedResponse,
    BoardSearchShareSessionListResponse,
    BoardSearchShareSessionResponse,
)
from game_predictor_api.schemas.catalog import ErrorResponse


def create_board_search_shares_admin_router(
    access_service_dependency: Callable[..., object],
    ingress_service_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(prefix="/admin/board-search-shares")
    access_service_parameter = Depends(access_service_dependency)
    ingress_service_parameter = Depends(ingress_service_dependency)

    @router.post(
        "/sessions",
        response_model=BoardSearchShareCreatedResponse,
        status_code=201,
        operation_id="createBoardSearchShareSession",
        summary="Create one online read-only board-search share link",
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
        ingress_status = ingress.status()
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

    return router


__all__ = ["create_board_search_shares_admin_router"]
