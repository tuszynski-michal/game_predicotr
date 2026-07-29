"""HTTP inventory for managed local image storage."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends

from game_predictor_api.application.image_storage import ImageStorageService
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.image_storage import ImageStorageInventoryResponse

ImageStorageServiceDependency = Callable[..., object]
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    409: {"model": ErrorResponse, "description": "Managed storage conflict"},
}


def create_image_storage_router(
    service_dependency: ImageStorageServiceDependency,
) -> APIRouter:
    router = APIRouter(prefix="/admin/image-storage", tags=["image-storage"])
    service_parameter = Depends(service_dependency)

    @router.get(
        "",
        response_model=ImageStorageInventoryResponse,
        operation_id="getImageStorageInventory",
        summary="Get read-only managed image storage inventory",
        responses=ERROR_RESPONSES,
    )
    def get_image_storage_inventory(
        service: Annotated[ImageStorageService, service_parameter],
    ) -> ImageStorageInventoryResponse:
        return ImageStorageInventoryResponse.from_domain(service.inventory())

    return router


__all__ = ["create_image_storage_router"]
