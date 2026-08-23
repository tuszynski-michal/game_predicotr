"""Read-only admin API for deferred board-cell geometry work."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from game_predictor_api.application.board_cell_geometry_pending import (
    BoardCellGeometryPendingService,
)
from game_predictor_api.domain.board_cell_geometry_pending import (
    BoardCellGeometryPendingStatus,
)
from game_predictor_api.schemas.board_cell_geometry_pending import (
    BoardCellGeometryPendingPageResponse,
    BoardCellGeometryPendingResponse,
    to_pending_page_response,
    to_pending_response,
)
from game_predictor_api.schemas.catalog import ErrorResponse

BoardCellGeometryPendingServiceDependency = Callable[..., object]
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Deferred geometry item not found"},
    409: {"model": ErrorResponse, "description": "Deferred geometry state conflict"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}


def create_board_cell_geometry_pending_router(
    service_dependency: BoardCellGeometryPendingServiceDependency,
) -> APIRouter:
    router = APIRouter(
        prefix="/admin/games/{game_id}/image-imports/{import_job_id}/board-cell-geometry-pending",
        tags=["board-cell-geometry"],
    )
    service_parameter = Depends(service_dependency)

    @router.get(
        "",
        response_model=BoardCellGeometryPendingPageResponse,
        operation_id="listPendingBoardCellGeometry",
        summary="List durable board-cell geometry fallback items",
        responses=ERROR_RESPONSES,
    )
    def list_pending_board_cell_geometry(
        game_id: UUID,
        import_job_id: UUID,
        service: Annotated[BoardCellGeometryPendingService, service_parameter],
        item_status: Annotated[
            BoardCellGeometryPendingStatus | None,
            Query(alias="status"),
        ] = None,
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
    ) -> BoardCellGeometryPendingPageResponse:
        return to_pending_page_response(
            service.list(
                game_id=game_id,
                import_job_id=import_job_id,
                status=item_status,
                cursor=cursor,
                limit=limit,
            )
        )

    @router.get(
        "/{pending_id}",
        response_model=BoardCellGeometryPendingResponse,
        operation_id="getPendingBoardCellGeometry",
        summary="Get one durable board-cell geometry fallback item",
        responses=ERROR_RESPONSES,
    )
    def get_pending_board_cell_geometry(
        game_id: UUID,
        import_job_id: UUID,
        pending_id: UUID,
        service: Annotated[BoardCellGeometryPendingService, service_parameter],
    ) -> BoardCellGeometryPendingResponse:
        return to_pending_response(
            service.get(
                pending_id,
                game_id=game_id,
                import_job_id=import_job_id,
            )
        )

    return router


__all__ = ["create_board_cell_geometry_pending_router"]
