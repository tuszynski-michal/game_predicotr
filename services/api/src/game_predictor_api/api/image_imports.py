"""Loopback-only image folder selection and import creation."""

from collections.abc import Callable
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Query, Response, status
from game_predictor_worker.images.pipeline_contract import (
    current_pipeline_manifest,
    pipeline_fingerprint,
)

from game_predictor_api.application.image_imports import (
    IMAGE_RELATIVE_PATH_HEADER,
    BrowserImageSelectionService,
    BrowserImageUpload,
    ImageFolderSelectionService,
)
from game_predictor_api.application.iterative_image_imports import (
    IterativeImageImportService,
)
from game_predictor_api.application.jobs import JobService
from game_predictor_api.domain.image_sequence_canonical import ImageSequenceCanonicalService
from game_predictor_api.domain.jobs import JobError
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.image_imports import (
    BrowserImageSelectionCreate,
    BrowserImageSelectionFileUploadResponse,
    BrowserImageSelectionUploadResponse,
    CuratedImageImportBatchCreate,
    CuratedImageImportSourceCreate,
    CuratedImageImportSourceResponse,
    ImageFolderImportCreate,
    ImageFolderImportResponse,
    ImageFolderSelectionResponse,
    ImageSequenceImportPreflightResponse,
)
from game_predictor_api.schemas.jobs import JobResponse


def create_image_imports_router(
    selection_service_dependency: Callable[..., object],
    browser_selection_service_dependency: Callable[..., object],
    job_service_dependency: Callable[..., object],
    iterative_import_service_dependency: Callable[..., object],
    image_sequence_canonical_service_dependency: Callable[..., object] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/admin/image-imports", tags=["image-imports"])
    selection_parameter = Depends(selection_service_dependency)
    browser_selection_parameter = Depends(browser_selection_service_dependency)
    job_parameter = Depends(job_service_dependency)
    iterative_import_parameter = Depends(iterative_import_service_dependency)
    canonical_parameter = (
        None
        if image_sequence_canonical_service_dependency is None
        else Depends(image_sequence_canonical_service_dependency)
    )
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
            uploaded_file_indexes=sorted(upload.uploaded_indexes),
            expected_total_bytes=upload.expected_total_bytes,
            uploaded_bytes=upload.uploaded_bytes,
            purpose=upload.purpose,
            game_id=upload.game_id,
        )

    def file_upload_response(
        upload: BrowserImageUpload,
    ) -> BrowserImageSelectionFileUploadResponse:
        return BrowserImageSelectionFileUploadResponse(
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
                purpose=payload.purpose,
                game_id=payload.game_id,
            )
        )

    @router.get(
        "/browser-selections/{upload_id}",
        response_model=BrowserImageSelectionUploadResponse,
        operation_id="getBrowserImageSelection",
        summary="Restore progress for an unfinished browser folder upload",
        responses=responses,
    )
    def get_browser_selection(
        upload_id: UUID,
        service: Annotated[BrowserImageSelectionService, browser_selection_parameter],
    ) -> BrowserImageSelectionUploadResponse:
        return upload_response(service.get(upload_id))

    @router.put(
        "/browser-selections/{upload_id}/files/{file_index}",
        response_model=BrowserImageSelectionFileUploadResponse,
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
    ) -> BrowserImageSelectionFileUploadResponse:
        return file_upload_response(
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
        canonical_service: object | None = canonical_parameter,
    ) -> ImageFolderImportResponse:
        canonical_numbers: list[int] | None = None
        if canonical_service is not None:
            get_numbers = getattr(canonical_service, "canonical_numbers", None)
            if callable(get_numbers):
                canonical_numbers = sorted(set(get_numbers(payload.game_id)))
        job = selection_service.create_import_job(
            job_service,
            game_id=payload.game_id,
            selection_token=payload.selection_token,
            canonical_sequence_numbers=canonical_numbers,
        )
        return ImageFolderImportResponse(job=JobResponse.from_domain(job))

    @router.post(
        "/preflight",
        response_model=ImageSequenceImportPreflightResponse,
        operation_id="previewImageSequenceImport",
        summary="Preview reuse of already resolved seq_* ranges",
        responses=responses,
    )
    def preflight_import(
        payload: ImageFolderImportCreate,
        selection_service: Annotated[
            ImageFolderSelectionService,
            selection_parameter,
        ],
        canonical_service: object | None = canonical_parameter,
    ) -> ImageSequenceImportPreflightResponse:
        if canonical_service is None:
            raise JobError(
                "IMAGE_SEQUENCE_PREFLIGHT_UNAVAILABLE",
                "Canonical sequence preflight is not configured.",
            )
        selected = selection_service.get_for_import(
            game_id=payload.game_id,
            selection_token=payload.selection_token,
        )
        # Keep this annotation-free at the transport boundary so custom test
        # dependencies can provide the same small service contract.
        result = cast(ImageSequenceCanonicalService, canonical_service).preflight(
            game_id=payload.game_id,
            source_directory=selected.path,
        )
        return ImageSequenceImportPreflightResponse.from_domain(result)

    @router.post(
        "/{source_job_id}/reprocess",
        response_model=ImageFolderImportResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="reprocessManagedImageImport",
        summary="Reprocess an image import from its preserved managed originals",
        responses=responses,
    )
    def reprocess_import(
        source_job_id: UUID,
        job_service: Annotated[JobService, job_parameter],
    ) -> ImageFolderImportResponse:
        job = job_service.create_managed_image_reprocess_job(
            source_job_id,
            pipeline_fingerprint=pipeline_fingerprint(current_pipeline_manifest()),
        )
        return ImageFolderImportResponse(job=JobResponse.from_domain(job))

    @router.post(
        "/curated-sources",
        response_model=CuratedImageImportSourceResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="registerCuratedImageImportSource",
        summary="Register verified image-selection output for incremental import",
        responses=responses,
    )
    def register_curated_source(
        payload: CuratedImageImportSourceCreate,
        service: Annotated[IterativeImageImportService, iterative_import_parameter],
    ) -> CuratedImageImportSourceResponse:
        return CuratedImageImportSourceResponse.from_domain(
            service.register_source(
                game_id=payload.game_id,
                image_selection_run_id=payload.image_selection_run_id,
            )
        )

    @router.get(
        "/curated-sources",
        response_model=list[CuratedImageImportSourceResponse],
        operation_id="listCuratedImageImportSources",
        summary="List incremental curated sources for one game",
        responses=responses,
    )
    def list_curated_sources(
        game_id: Annotated[UUID, Query(alias="gameId")],
        service: Annotated[IterativeImageImportService, iterative_import_parameter],
    ) -> list[CuratedImageImportSourceResponse]:
        return [
            CuratedImageImportSourceResponse.from_domain(item)
            for item in service.list_sources(game_id=game_id)
        ]

    @router.get(
        "/curated-sources/{source_id}",
        response_model=CuratedImageImportSourceResponse,
        operation_id="getCuratedImageImportSource",
        summary="Get durable progress for one incremental curated source",
        responses=responses,
    )
    def get_curated_source(
        source_id: UUID,
        service: Annotated[IterativeImageImportService, iterative_import_parameter],
    ) -> CuratedImageImportSourceResponse:
        return CuratedImageImportSourceResponse.from_domain(service.get_source(source_id))

    @router.post(
        "/curated-sources/{source_id}/batches",
        response_model=CuratedImageImportSourceResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="createNextCuratedImageImportBatch",
        summary="Atomically reserve and import the next N curated images",
        responses=responses,
    )
    def create_next_curated_batch(
        source_id: UUID,
        payload: CuratedImageImportBatchCreate,
        service: Annotated[IterativeImageImportService, iterative_import_parameter],
    ) -> CuratedImageImportSourceResponse:
        return CuratedImageImportSourceResponse.from_domain(
            service.create_next_batch(source_id, requested_count=payload.image_count)
        )

    return router


__all__ = ["create_image_imports_router"]
