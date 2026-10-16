"""Panel control-plane API; game reads and writes remain on the existing API."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Query, Response

from game_predictor_api.application.board_search_panels import (
    PANEL_COOKIE,
    PANEL_COOKIE_PATH,
    PANEL_PROXY_HEADER,
    PANEL_PROXY_INTENT,
    BoardSearchPanelService,
)
from game_predictor_api.application.reviewer_ingress import (
    ReviewerIngressError,
    ReviewerIngressService,
    ensure_online_reviewer_ingress,
)
from game_predictor_api.domain.board_search_shares import (
    BoardSearchShareAuthenticationError,
    BoardSearchShareAuthorizationError,
)
from game_predictor_api.schemas.board_search_panels import (
    BoardSearchPanelContextResponse,
    BoardSearchPanelCreate,
    BoardSearchPanelCreatedResponse,
    BoardSearchPanelListResponse,
    BoardSearchPanelOpen,
    BoardSearchPanelResponse,
)
from game_predictor_api.schemas.catalog import ErrorResponse

ERRORS: dict[int | str, dict[str, object]] = {
    status: {"model": ErrorResponse} for status in (401, 403, 404, 409, 422, 503)
}


def require_panel_proxy(
    intent: Annotated[str | None, Header(alias=PANEL_PROXY_HEADER)] = None,
) -> None:
    if intent != PANEL_PROXY_INTENT:
        raise BoardSearchShareAuthorizationError(
            "BOARD_SEARCH_PANEL_PROXY_REQUIRED", "Use the panel application."
        )


def create_board_search_panels_router(
    service_dependency: Callable[..., object],
    ingress_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(tags=["board-search-panels"], responses=ERRORS)
    service_parameter = Depends(service_dependency, scope="function")
    ingress_parameter = Depends(ingress_dependency)

    @router.post(
        "/admin/board-search-panels",
        status_code=201,
        response_model=BoardSearchPanelCreatedResponse,
        operation_id="createBoardSearchPanel",
    )
    def create(
        payload: BoardSearchPanelCreate,
        service: Annotated[BoardSearchPanelService, service_parameter],
        ingress: Annotated[ReviewerIngressService, ingress_parameter],
    ) -> BoardSearchPanelCreatedResponse:
        service.assert_can_create(
            game_ids=payload.game_ids,
            lifetime_minutes=payload.lifetime_minutes,
            label=payload.label,
        )
        status = ensure_online_reviewer_ingress(ingress)
        created = service.create(
            game_ids=payload.game_ids,
            lifetime_minutes=payload.lifetime_minutes,
            label=payload.label,
        )
        return BoardSearchPanelCreatedResponse(
            panel=BoardSearchPanelResponse.from_view(created.panel, status),
            link_key=created.link_key,
        )

    @router.get(
        "/admin/board-search-panels",
        response_model=BoardSearchPanelListResponse,
        operation_id="listBoardSearchPanels",
    )
    def list_panels(
        service: Annotated[BoardSearchPanelService, service_parameter],
        ingress: Annotated[ReviewerIngressService, ingress_parameter],
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
    ) -> BoardSearchPanelListResponse:
        try:
            status = ingress.status()
        except ReviewerIngressError:
            status = None
        return BoardSearchPanelListResponse(
            panels=[
                BoardSearchPanelResponse.from_view(view, status) for view in service.list(limit)
            ]
        )

    @router.post(
        "/admin/board-search-panels/{panel_id}/revoke",
        response_model=BoardSearchPanelResponse,
        operation_id="revokeBoardSearchPanel",
    )
    def revoke(
        panel_id: UUID, service: Annotated[BoardSearchPanelService, service_parameter]
    ) -> BoardSearchPanelResponse:
        return BoardSearchPanelResponse.from_view(service.revoke(panel_id), None)

    @router.post(
        "/board-search-panels/{panel_id}/open",
        dependencies=[Depends(require_panel_proxy)],
        response_model=BoardSearchPanelContextResponse,
        operation_id="openBoardSearchPanel",
    )
    def open_panel(
        panel_id: UUID,
        payload: BoardSearchPanelOpen,
        response: Response,
        service: Annotated[BoardSearchPanelService, service_parameter],
    ) -> BoardSearchPanelContextResponse:
        view = service.authenticate(panel_id, payload.link_key)
        response.set_cookie(
            PANEL_COOKIE,
            f"{panel_id}.{payload.link_key}",
            max_age=max(0, int((view.expires_at - datetime.now(UTC)).total_seconds())),
            expires=view.expires_at,
            path=PANEL_COOKIE_PATH,
            secure=True,
            httponly=True,
            samesite="strict",
        )
        return BoardSearchPanelContextResponse.from_view(view)

    @router.get(
        "/board-search-panels/{panel_id}/context",
        dependencies=[Depends(require_panel_proxy)],
        response_model=BoardSearchPanelContextResponse,
        operation_id="getBoardSearchPanelContext",
    )
    def context(
        panel_id: UUID,
        service: Annotated[BoardSearchPanelService, service_parameter],
        credential: Annotated[str | None, Cookie(alias=PANEL_COOKIE)] = None,
    ) -> BoardSearchPanelContextResponse:
        prefix = f"{panel_id}."
        if credential is None or not credential.startswith(prefix):
            raise BoardSearchShareAuthenticationError(
                "BOARD_SEARCH_PANEL_ACCESS_INVALID", "Open the matching panel link."
            )
        return BoardSearchPanelContextResponse.from_view(
            service.authenticate(panel_id, credential[len(prefix) :])
        )

    return router
