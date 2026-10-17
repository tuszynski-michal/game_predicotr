"""HTTP routes of source crop and original-deletion runs (TASK-1047, D-562)."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from game_predictor_api.application.source_crop_runs import SourceCropRunService
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.source_crop_runs import (
    SourceCropPreviewCreate,
    SourceCropRunListResponse,
    SourceCropRunResponse,
    SourceCropRunStart,
)

ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Source crop run not found"},
    409: {"model": ErrorResponse, "description": "Source crop run conflict"},
}


def create_source_crop_runs_router(service_dependency: Callable[..., object]) -> APIRouter:
    router = APIRouter(prefix="/admin/image-storage", tags=["image-storage"])
    service_parameter = Depends(service_dependency)

    @router.post(
        "/source-crop-previews",
        response_model=SourceCropRunResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="createSourceCropPreview",
        summary="Plan a crop or original-deletion run (worker builds the preview)",
        responses=ERROR_RESPONSES,
    )
    def create_source_crop_preview(
        payload: SourceCropPreviewCreate,
        service: Annotated[SourceCropRunService, service_parameter],
    ) -> SourceCropRunResponse:
        return SourceCropRunResponse.from_domain(
            service.create_preview(kind=payload.kind, scope=payload.scope.to_domain())
        )

    @router.post(
        "/source-crop-previews/{preview_id}/start",
        response_model=SourceCropRunResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="startSourceCropRun",
        summary="Execute a reviewed source crop preview after explicit confirmation",
        responses=ERROR_RESPONSES,
    )
    def start_source_crop_run(
        preview_id: UUID,
        payload: SourceCropRunStart,
        service: Annotated[SourceCropRunService, service_parameter],
    ) -> SourceCropRunResponse:
        return SourceCropRunResponse.from_domain(
            service.start(
                preview_id=preview_id,
                manifest_checksum_sha256=payload.manifest_checksum_sha256,
                preview_token=payload.preview_token,
                confirmed=payload.confirmed,
                acknowledge_irreversible=payload.acknowledge_irreversible,
            )
        )

    @router.get(
        "/source-crop-runs",
        response_model=SourceCropRunListResponse,
        operation_id="listSourceCropRuns",
        summary="List the newest source crop runs",
        responses=ERROR_RESPONSES,
    )
    def list_source_crop_runs(
        service: Annotated[SourceCropRunService, service_parameter],
        limit: Annotated[int, Query(ge=1, le=50)] = 10,
    ) -> SourceCropRunListResponse:
        return SourceCropRunListResponse(
            runs=[SourceCropRunResponse.from_domain(run) for run in service.list(limit=limit)]
        )

    @router.get(
        "/source-crop-runs/{run_id}",
        response_model=SourceCropRunResponse,
        operation_id="getSourceCropRun",
        summary="Read one source crop run with its preview and progress",
        responses=ERROR_RESPONSES,
    )
    def get_source_crop_run(
        run_id: UUID,
        service: Annotated[SourceCropRunService, service_parameter],
    ) -> SourceCropRunResponse:
        return SourceCropRunResponse.from_domain(service.get(run_id))

    return router


__all__ = ["create_source_crop_runs_router"]
