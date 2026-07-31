"""Loopback-only image folder selection and import creation."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, status

from game_predictor_api.application.image_imports import ImageFolderSelectionService
from game_predictor_api.application.jobs import JobService
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.image_imports import (
    ImageFolderImportCreate,
    ImageFolderImportResponse,
    ImageFolderSelectionResponse,
)
from game_predictor_api.schemas.jobs import JobResponse


def create_image_imports_router(
    selection_service_dependency: Callable[..., object],
    job_service_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(prefix="/admin/image-imports", tags=["image-imports"])
    selection_parameter = Depends(selection_service_dependency)
    job_parameter = Depends(job_service_dependency)
    responses: dict[int | str, dict[str, object]] = {
        404: {"model": ErrorResponse, "description": "Game or folder not found"},
        409: {"model": ErrorResponse, "description": "Import conflict"},
        422: {"model": ErrorResponse, "description": "Folder validation error"},
    }

    @router.post(
        "/folder-selection",
        response_model=ImageFolderSelectionResponse,
        operation_id="selectLocalImageFolder",
        summary="Open the controlled native Windows folder picker",
        responses=responses,
    )
    def select_folder(
        service: Annotated[ImageFolderSelectionService, selection_parameter],
    ) -> ImageFolderSelectionResponse:
        selected = service.select()
        return (
            ImageFolderSelectionResponse.cancelled()
            if selected is None
            else ImageFolderSelectionResponse.selected(selected)
        )

    @router.post(
        "",
        response_model=ImageFolderImportResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="createImageFolderImport",
        summary="Create an image import from an approved local folder selection",
        responses=responses,
    )
    def create_import(
        payload: ImageFolderImportCreate,
        selection_service: Annotated[
            ImageFolderSelectionService,
            selection_parameter,
        ],
        job_service: Annotated[JobService, job_parameter],
    ) -> ImageFolderImportResponse:
        job = selection_service.create_import_job(
            job_service,
            game_id=payload.game_id,
            selection_token=payload.selection_token,
        )
        return ImageFolderImportResponse(job=JobResponse.from_domain(job))

    return router


__all__ = ["create_image_imports_router"]
