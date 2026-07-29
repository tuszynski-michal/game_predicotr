"""HTTP operations for image import jobs."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import FileResponse

from game_predictor_api.application.image_jobs import ImageJobOperationsService
from game_predictor_api.application.image_storage import ImageStorageService
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.image_jobs import (
    ImageJobFileRetryRequest,
    ImageJobOperationsResponse,
)
from game_predictor_api.schemas.image_storage import (
    ImageDiagnosticExportCreationResponse,
    ImageDiagnosticExportResponse,
)

ImageJobServiceDependency = Callable[..., object]
ImageStorageServiceDependency = Callable[..., object]
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Image job or file not found"},
    409: {"model": ErrorResponse, "description": "Image job operation conflict"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}


def create_image_jobs_router(
    service_dependency: ImageJobServiceDependency,
    storage_service_dependency: ImageStorageServiceDependency,
) -> APIRouter:
    router = APIRouter(prefix="/admin/image-jobs", tags=["image-jobs"])
    service_parameter = Depends(service_dependency)
    storage_service_parameter = Depends(storage_service_dependency)

    @router.get(
        "/{job_id}/operations",
        response_model=ImageJobOperationsResponse,
        operation_id="getImageJobOperations",
        summary="Get durable image-job stage and file statistics",
        responses=ERROR_RESPONSES,
    )
    def get_image_job_operations(
        job_id: UUID,
        service: Annotated[ImageJobOperationsService, service_parameter],
        file_limit: Annotated[int, Query(ge=1, le=200)] = 100,
    ) -> ImageJobOperationsResponse:
        return ImageJobOperationsResponse.from_domain(
            service.get_operations(job_id, file_limit=file_limit)
        )

    @router.post(
        "/{job_id}/files/{file_execution_key}/retry",
        response_model=ImageJobOperationsResponse,
        operation_id="retryImageJobFile",
        summary="Retry exactly one failed image stage",
        responses=ERROR_RESPONSES,
    )
    def retry_image_job_file(
        job_id: UUID,
        file_execution_key: Annotated[str, Path(pattern=r"^[0-9a-f]{64}$")],
        payload: ImageJobFileRetryRequest,
        service: Annotated[ImageJobOperationsService, service_parameter],
        file_limit: Annotated[int, Query(ge=1, le=200)] = 100,
    ) -> ImageJobOperationsResponse:
        return ImageJobOperationsResponse.from_domain(
            service.retry_file(
                job_id,
                file_execution_key=file_execution_key,
                expected_stage=payload.expected_stage,
                file_limit=file_limit,
            )
        )

    @router.post(
        "/{job_id}/diagnostic-exports",
        response_model=ImageDiagnosticExportCreationResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="createImageDiagnosticExport",
        summary="Create or reuse an immutable image-job diagnostic export",
        responses=ERROR_RESPONSES,
    )
    def create_image_diagnostic_export(
        job_id: UUID,
        service: Annotated[ImageStorageService, storage_service_parameter],
    ) -> ImageDiagnosticExportCreationResponse:
        return ImageDiagnosticExportCreationResponse.from_domain(
            service.create_diagnostic_export(job_id)
        )

    @router.get(
        "/{job_id}/diagnostic-exports",
        response_model=list[ImageDiagnosticExportResponse],
        operation_id="listImageDiagnosticExports",
        summary="List immutable diagnostic exports for an image job",
        responses=ERROR_RESPONSES,
    )
    def list_image_diagnostic_exports(
        job_id: UUID,
        service: Annotated[ImageStorageService, storage_service_parameter],
    ) -> list[ImageDiagnosticExportResponse]:
        return [
            ImageDiagnosticExportResponse.from_domain(item)
            for item in service.list_diagnostic_exports(job_id)
        ]

    @router.get(
        "/{job_id}/diagnostic-exports/{checksum_sha256}/download",
        response_class=FileResponse,
        operation_id="downloadImageDiagnosticExport",
        summary="Download a checksum-verified image-job diagnostic export",
        responses=ERROR_RESPONSES,
    )
    def download_image_diagnostic_export(
        job_id: UUID,
        checksum_sha256: Annotated[str, Path(pattern=r"^[0-9a-f]{64}$")],
        service: Annotated[ImageStorageService, storage_service_parameter],
    ) -> FileResponse:
        path, _export = service.resolve_diagnostic_export(job_id, checksum_sha256)
        return FileResponse(
            path,
            media_type="application/octet-stream",
            filename=f"image-job-{job_id}-diagnostics-{checksum_sha256[:12]}.json",
        )

    return router


__all__ = ["create_image_jobs_router"]
