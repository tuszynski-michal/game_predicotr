"""Admin HTTP boundary for image-selection run contracts."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from game_predictor_api.application.image_imports import ImageFolderSelectionService
from game_predictor_api.application.image_selections import ImageSelectionService
from game_predictor_api.domain.image_selections import (
    IMAGE_SELECTION_GROUP_PAGE_DEFAULT,
    IMAGE_SELECTION_SELECTOR_FINGERPRINT,
    ImageSelectionGroupStatus,
)
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.image_selections import (
    ImageSelectionCreate,
    ImageSelectionCreateResponse,
    ImageSelectionGroupPageResponse,
    ImageSelectionRunResponse,
    to_image_selection_group_page_response,
    to_image_selection_run_response,
)

ImageSelectionServiceDependency = Callable[..., object]
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Image selection or game not found"},
    409: {"model": ErrorResponse, "description": "Image selection conflict"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}


def create_image_selections_router(
    service_dependency: ImageSelectionServiceDependency,
    folder_selection_service_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(prefix="/admin/image-selections", tags=["image-selections"])
    service_parameter = Depends(service_dependency)
    folder_selection_parameter = Depends(folder_selection_service_dependency)

    @router.post(
        "",
        response_model=ImageSelectionCreateResponse,
        operation_id="createImageSelection",
        summary="Create or return an idempotent image-selection run",
        responses=ERROR_RESPONSES,
    )
    def create_image_selection(
        payload: ImageSelectionCreate,
        service: Annotated[ImageSelectionService, service_parameter],
        folder_selection_service: Annotated[
            ImageFolderSelectionService,
            folder_selection_parameter,
        ],
    ) -> ImageSelectionCreateResponse:
        run, created = folder_selection_service.create_image_selection_run(
            service,
            game_id=payload.game_id,
            selection_token=payload.selection_token,
            selector_fingerprint=IMAGE_SELECTION_SELECTOR_FINGERPRINT,
        )
        return ImageSelectionCreateResponse(
            run=to_image_selection_run_response(run),
            created=created,
        )

    @router.get(
        "/{run_id}",
        response_model=ImageSelectionRunResponse,
        operation_id="getImageSelection",
        summary="Get one durable image-selection run",
        responses=ERROR_RESPONSES,
    )
    def get_image_selection(
        run_id: UUID,
        service: Annotated[ImageSelectionService, service_parameter],
    ) -> ImageSelectionRunResponse:
        return to_image_selection_run_response(service.get_run(run_id))

    @router.get(
        "/{run_id}/groups",
        response_model=ImageSelectionGroupPageResponse,
        operation_id="listImageSelectionGroups",
        summary="List a bounded page of image-selection groups",
        responses=ERROR_RESPONSES,
    )
    def list_image_selection_groups(
        run_id: UUID,
        service: Annotated[ImageSelectionService, service_parameter],
        group_status: Annotated[
            ImageSelectionGroupStatus | None,
            Query(alias="status"),
        ] = None,
        after_group_order: Annotated[
            int,
            Query(alias="afterGroupOrder", ge=-1),
        ] = -1,
        limit: Annotated[int, Query(ge=1, le=100)] = IMAGE_SELECTION_GROUP_PAGE_DEFAULT,
    ) -> ImageSelectionGroupPageResponse:
        return to_image_selection_group_page_response(
            service.list_groups(
                run_id=run_id,
                status=group_status,
                after_group_order=after_group_order,
                limit=limit,
            )
        )

    return router


__all__ = ["create_image_selections_router"]
