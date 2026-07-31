"""HTTP boundary for preview-bound destructive cleanup operations."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from game_predictor_api.application.cleanup import CleanupService
from game_predictor_api.domain.cleanup import CleanupCommand
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.cleanup import (
    CleanupCommandRequest,
    CleanupPreviewResponse,
    CleanupResultResponse,
)

CleanupServiceDependency = Callable[..., object]
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Cleanup target not found"},
    409: {"model": ErrorResponse, "description": "Cleanup state conflict"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}


def create_cleanup_router(service_dependency: CleanupServiceDependency) -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["cleanup"])
    service_parameter = Depends(service_dependency)

    @router.get(
        "/mobile-releases/{mobile_release_id}/deletion-preview",
        response_model=CleanupPreviewResponse,
        operation_id="previewMobileReleaseDeletion",
        summary="Preview complete deletion of one mobile release",
        responses=ERROR_RESPONSES,
    )
    def preview_mobile_release_deletion(
        mobile_release_id: UUID,
        service: Annotated[CleanupService, service_parameter],
    ) -> CleanupPreviewResponse:
        return CleanupPreviewResponse.from_domain(service.preview_release(mobile_release_id))

    @router.delete(
        "/mobile-releases/{mobile_release_id}",
        response_model=CleanupResultResponse,
        operation_id="deleteMobileRelease",
        summary="Delete one mobile release and its dedicated artifacts",
        responses=ERROR_RESPONSES,
    )
    def delete_mobile_release(
        mobile_release_id: UUID,
        payload: CleanupCommandRequest,
        service: Annotated[CleanupService, service_parameter],
    ) -> CleanupResultResponse:
        return CleanupResultResponse.from_domain(
            service.delete_release(
                mobile_release_id,
                CleanupCommand(
                    preview_token=payload.preview_token,
                    confirmation_target=payload.confirmation_target,
                    confirmed=payload.confirmed,
                ),
            )
        )

    @router.get(
        "/games/{game_id}/layout-data-reset-preview",
        response_model=CleanupPreviewResponse,
        operation_id="previewGameLayoutDataReset",
        summary="Preview reset of all layout workflow data for one game",
        responses=ERROR_RESPONSES,
    )
    def preview_game_layout_data_reset(
        game_id: UUID,
        service: Annotated[CleanupService, service_parameter],
    ) -> CleanupPreviewResponse:
        return CleanupPreviewResponse.from_domain(service.preview_game_reset(game_id))

    @router.delete(
        "/games/{game_id}/layout-data",
        response_model=CleanupResultResponse,
        operation_id="resetGameLayoutData",
        summary="Reset all layout workflow data for one game",
        responses=ERROR_RESPONSES,
    )
    def reset_game_layout_data(
        game_id: UUID,
        payload: CleanupCommandRequest,
        service: Annotated[CleanupService, service_parameter],
    ) -> CleanupResultResponse:
        return CleanupResultResponse.from_domain(
            service.reset_game(
                game_id,
                CleanupCommand(
                    preview_token=payload.preview_token,
                    confirmation_target=payload.confirmation_target,
                    confirmed=payload.confirmed,
                ),
            )
        )

    return router


__all__ = ["create_cleanup_router"]
