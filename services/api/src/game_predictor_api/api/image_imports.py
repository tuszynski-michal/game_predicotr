"""Loopback-only image folder selection and import creation."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Response, status

from game_predictor_api.application.image_imports import (
    IMAGE_RELATIVE_PATH_HEADER,
    BrowserImageSelectionService,
    BrowserImageUpload,
    ImageFolderSelectionService,
)
from game_predictor_api.application.jobs import JobService
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.image_imports import (
    BrowserImageSelectionCreate,
    BrowserImageSelectionUploadResponse,
    ImageFolderImportCreate,
    ImageFolderImportResponse,
    ImageFolderSelectionResponse,
)
from game_predictor_api.schemas.jobs import JobResponse


def create_image_imports_router(
    selection_service_dependency: Callable[..., object],
    browser_selection_service_dependency: Callable[..., object],
    job_service_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(prefix="/admin/image-imports", tags=["image-imports"])
    selection_parameter = Depends(selection_service_dependency)
    browser_selection_parameter = Depends(browser_selection_service_dependency)
    job_parameter = Depends(job_service_dependency)
    responses: dict[int | str, dict[str, object]] = {
        404: {"model": ErrorResponse, "description": "Game or folder not found"},
        409: {"model": ErrorResponse, "description": "Import conflict"},
        422: {"model": ErrorResponse, "description": "Folder validation error"},
    }

    def upload_response(upload: BrowserImageUpload) -> BrowserImageSelectionUploadResponse:
        return BrowserImageSelectionUploadResponse(
            upload_id=upload.upload_id,
            expected_file_count=upload.expected_file_count,
            uploaded_file_count=len(upload.uploaded_indexes),
            expected_total_bytes=upload.expected_total_bytes,
            uploaded_bytes=upload.uploaded_bytes,
        )

    @router.post(
        "/browser-selections",
        response_model=BrowserImageSelectionUploadResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="createBrowserImageSelection",
        summary="Start a browser-native image folder upload",
        responses=responses,
    )
    def create_browser_selection(
        payload: BrowserImageSelectionCreate,
        service: Annotated[BrowserImageSelectionService, browser_selection_parameter],
    ) -> BrowserImageSelectionUploadResponse:
        return upload_response(
            service.begin(
                display_name=payload.display_name,
                expected_file_count=payload.expected_file_count,
                expected_total_bytes=payload.expected_total_bytes,
            )
        )

    @router.put(
        "/browser-selections/{upload_id}/files/{file_index}",
        response_model=BrowserImageSelectionUploadResponse,
        operation_id="uploadBrowserImageSelectionFile",
        summary="Upload one JPEG from a browser-native folder selection",
        responses=responses,
    )
    def upload_browser_selection_file(
        upload_id: UUID,
        file_index: int,
        relative_path: Annotated[
            str,
            Header(alias=IMAGE_RELATIVE_PATH_HEADER, min_length=1, max_length=1000),
        ],
        payload: Annotated[bytes, Body(media_type="application/octet-stream")],
        service: Annotated[BrowserImageSelectionService, browser_selection_parameter],
    ) -> BrowserImageSelectionUploadResponse:
        return upload_response(
            service.upload_file(
                upload_id,
                file_index,
                relative_path=relative_path,
                content=payload,
            )
        )

    @router.post(
        "/browser-selections/{upload_id}/finalize",
        response_model=ImageFolderSelectionResponse,
        operation_id="finalizeBrowserImageSelection",
        summary="Finalize a browser-native image folder selection",
        responses=responses,
    )
    def finalize_browser_selection(
        upload_id: UUID,
        service: Annotated[BrowserImageSelectionService, browser_selection_parameter],
    ) -> ImageFolderSelectionResponse:
        return ImageFolderSelectionResponse.selected(service.finalize(upload_id))

    @router.delete(
        "/browser-selections/{upload_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        operation_id="cancelBrowserImageSelection",
        summary="Cancel and remove a browser-native image folder selection",
        responses=responses,
    )
    def cancel_browser_selection(
        upload_id: UUID,
        service: Annotated[BrowserImageSelectionService, browser_selection_parameter],
    ) -> Response:
        service.cancel(upload_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

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
