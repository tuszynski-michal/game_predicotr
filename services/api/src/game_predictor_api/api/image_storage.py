"""HTTP inventory for managed local image storage."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from game_predictor_api.application.image_storage import ImageStorageService
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.image_storage import (
    ImageStorageInventoryResponse,
    StorageGcPreviewResponse,
    StorageGcRunCreate,
    StorageGcRunResponse,
)
from game_predictor_api.schemas.jobs import JobResponse

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

    @router.post(
        "/inventory-refresh",
        response_model=JobResponse,
        operation_id="refreshImageStorageInventory",
        summary="Refresh the bounded managed image storage inventory",
        responses=ERROR_RESPONSES,
    )
    def refresh_image_storage_inventory(
        service: Annotated[ImageStorageService, service_parameter],
    ) -> JobResponse:
        return JobResponse.from_domain(service.refresh_inventory())

    @router.post(
        "/gc-previews",
        response_model=StorageGcPreviewResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="createStorageGcPreview",
        summary="Create an immutable dry-run manifest for safe storage cleanup",
        responses=ERROR_RESPONSES,
    )
    def create_storage_gc_preview(
        service: Annotated[ImageStorageService, service_parameter],
    ) -> StorageGcPreviewResponse:
        return StorageGcPreviewResponse.from_domain(service.create_gc_preview())

    @router.post(
        "/gc-runs",
        response_model=StorageGcRunResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="startStorageGcRun",
        summary="Start a confirmed durable storage cleanup run",
        responses=ERROR_RESPONSES,
    )
    def start_storage_gc_run(
        payload: StorageGcRunCreate,
        service: Annotated[ImageStorageService, service_parameter],
    ) -> StorageGcRunResponse:
        return StorageGcRunResponse.from_domain(
            service.start_gc(
                preview_id=payload.preview_id,
                manifest_checksum_sha256=payload.manifest_checksum_sha256,
                preview_token=payload.preview_token,
                confirmed=payload.confirmed,
            )
        )

    @router.get(
        "/gc-runs/{run_id}",
        response_model=StorageGcRunResponse,
        operation_id="getStorageGcRun",
        summary="Read durable storage cleanup progress",
        responses=ERROR_RESPONSES,
    )
    def get_storage_gc_run(
        run_id: UUID,
        service: Annotated[ImageStorageService, service_parameter],
    ) -> StorageGcRunResponse:
        return StorageGcRunResponse.from_domain(service.get_gc_run(run_id))

    return router


__all__ = ["create_image_storage_router"]
