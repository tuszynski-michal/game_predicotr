"""Loopback-only image folder selection and import creation."""

import hashlib
import json
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
    ImageSelectionPurpose,
)
from game_predictor_api.application.iterative_image_imports import (
    IterativeImageImportService,
)
from game_predictor_api.application.jobs import JobService
from game_predictor_api.domain.image_sequence_canonical import ImageSequenceCanonicalService
from game_predictor_api.domain.jobs import JobConflictError, JobError
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.image_imports import (
    BrowserImageImportPreflightCreate,
    BrowserImageImportPreflightResponse,
    BrowserImageImportStart,
    BrowserImageImportStartResponse,
    BrowserImageSelectionCreate,
    BrowserImageSelectionFileUploadResponse,
    BrowserImageSelectionUploadResponse,
    BrowserReadySelectionResponse,
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

    def browser_preflight(
        *,
        upload_id: UUID,
        game_id: UUID,
        service: BrowserImageSelectionService,
        canonical_service: object | None,
    ) -> BrowserImageImportPreflightResponse:
        if canonical_service is None:
            raise JobError(
                "IMAGE_SEQUENCE_PREFLIGHT_UNAVAILABLE",
                "Canonical sequence preflight is not configured.",
            )
        ready = service.get_ready(upload_id)
        if ready.upload.game_id is not None and ready.upload.game_id != game_id:
            raise JobError(
                "IMAGE_FOLDER_SELECTION_GAME_MISMATCH",
                "The staged folder belongs to a different game.",
            )
        result = cast(ImageSequenceCanonicalService, canonical_service).preflight(
            game_id=game_id,
            manifest=ready.manifest,
        )
        base = ImageSequenceImportPreflightResponse.from_domain(result)
        payload = base.model_dump(mode="json", by_alias=True)
        checksum = hashlib.sha256(
            json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
                "ascii"
            )
        ).hexdigest()
        return BrowserImageImportPreflightResponse(
            **payload,
            upload_id=upload_id,
            display_name=ready.upload.display_name,
            manifest_checksum_sha256=ready.manifest.checksum_sha256,
            preflight_checksum_sha256=checksum,
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

    @router.get(
        "/browser-selections",
        response_model=list[BrowserReadySelectionResponse],
        operation_id="listReadyBrowserImageSelections",
        summary="List finalized browser staging folders ready for layout import",
        responses=responses,
    )
    def list_ready_browser_selections(
        service: Annotated[BrowserImageSelectionService, browser_selection_parameter],
        purpose: Annotated[ImageSelectionPurpose | None, Query()] = None,
    ) -> list[BrowserReadySelectionResponse]:
        if purpose not in {None, ImageSelectionPurpose.LAYOUT_IMPORT}:
            return []
        return [BrowserReadySelectionResponse.from_domain(item) for item in service.list_ready()]

    @router.post(
        "/browser-selections/{upload_id}/preflight",
        response_model=BrowserImageImportPreflightResponse,
        operation_id="previewReadyBrowserImageImport",
        summary="Preview a finalized browser staging folder before creating a job",
        responses=responses,
    )
    def preview_ready_browser_import(
        upload_id: UUID,
        payload: BrowserImageImportPreflightCreate,
        service: Annotated[BrowserImageSelectionService, browser_selection_parameter],
        canonical_service: object | None = canonical_parameter,
    ) -> BrowserImageImportPreflightResponse:
        return browser_preflight(
            upload_id=upload_id,
            game_id=payload.game_id,
            service=service,
            canonical_service=canonical_service,
        )

    @router.post(
        "/browser-selections/{upload_id}/start",
        response_model=BrowserImageImportStartResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="startReadyBrowserImageImport",
        summary="Create an idempotent image import from finalized browser staging",
        responses=responses,
    )
    def start_ready_browser_import(
        upload_id: UUID,
        payload: BrowserImageImportStart,
        service: Annotated[BrowserImageSelectionService, browser_selection_parameter],
        job_service: Annotated[JobService, job_parameter],
        canonical_service: object | None = canonical_parameter,
    ) -> BrowserImageImportStartResponse:
        ready = service.bind_ready_game(upload_id, payload.game_id)
        if ready.manifest.checksum_sha256 != payload.manifest_checksum_sha256:
            raise JobConflictError(
                "IMAGE_SEQUENCE_MANIFEST_CHANGED",
                "The staged manifest changed after preflight.",
            )
        preflight = browser_preflight(
            upload_id=upload_id,
            game_id=payload.game_id,
            service=service,
            canonical_service=canonical_service,
        )
        if preflight.preflight_checksum_sha256 != payload.preflight_checksum_sha256:
            raise JobConflictError(
                "IMAGE_SEQUENCE_PREFLIGHT_STALE",
                "The canonical sequence projection changed after preflight.",
            )
        existing = job_service.get_image_import_by_source_selection(
            game_id=payload.game_id,
            source_selection_id=upload_id,
        )
        if existing is None:
            canonical_numbers = (
                sorted(
                    cast(ImageSequenceCanonicalService, canonical_service).canonical_numbers(
                        payload.game_id
                    )
                )
                if canonical_service is not None
                else None
            )
            try:
                job = job_service.create_image_import_job(
                    game_id=payload.game_id,
                    selection_id=upload_id,
                    source_directory=ready.upload.path,
                    source_display_name=ready.upload.display_name,
                    pipeline_fingerprint=pipeline_fingerprint(current_pipeline_manifest()),
                    canonical_sequence_numbers=canonical_numbers,
                    source_manifest_sha256=ready.manifest.checksum_sha256,
                )
                created = True
            except JobConflictError as error:
                if error.code != "JOB_INPUT_ALREADY_EXISTS":
                    raise
                existing = job_service.get_image_import_by_source_selection(
                    game_id=payload.game_id,
                    source_selection_id=upload_id,
                )
                if existing is None:
                    raise
                job = existing
                created = False
        else:
            expected_manifest = existing.input_payload.get("source_manifest_sha256")
            if expected_manifest not in {None, ready.manifest.checksum_sha256}:
                raise JobConflictError(
                    "IMAGE_SEQUENCE_MANIFEST_CHANGED",
                    "This staging folder was already used with another manifest.",
                )
            job = existing
            created = False
        return BrowserImageImportStartResponse(
            created=created,
            job=JobResponse.from_domain(job),
            preflight=preflight,
        )

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
