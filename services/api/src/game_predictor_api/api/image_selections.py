"""Admin HTTP boundary for image-selection run contracts."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Query
from fastapi.responses import FileResponse

from game_predictor_api.application.image_imports import (
    ImageFolderSelectionService,
    ImageSelectionPurpose,
)
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
    ImageSelectionHandoffResponse,
    ImageSelectionManualApprovalCommand,
    ImageSelectionManualApprovalResponse,
    ImageSelectionManualFileResponse,
    ImageSelectionRunResponse,
    to_image_selection_candidate_response,
    to_image_selection_group_page_response,
    to_image_selection_group_response,
    to_image_selection_run_response,
    to_manual_decision_response,
)

MANUAL_FILE_NAME_HEADER = "X-Image-File-Name"

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

    @router.put(
        "/{run_id}/groups/{group_id}/manual-file",
        response_model=ImageSelectionManualFileResponse,
        operation_id="uploadManualImageSelectionFile",
        summary="Copy one browser-selected JPEG into managed manual-review storage",
        responses=ERROR_RESPONSES,
    )
    def upload_manual_image_selection_file(
        run_id: UUID,
        group_id: UUID,
        display_name: Annotated[
            str,
            Header(alias=MANUAL_FILE_NAME_HEADER, min_length=1, max_length=255),
        ],
        payload: Annotated[bytes, Body(media_type="application/octet-stream")],
        service: Annotated[ImageSelectionService, service_parameter],
    ) -> ImageSelectionManualFileResponse:
        candidate = service.upload_manual_file(
            run_id=run_id,
            group_id=group_id,
            display_name=display_name,
            content=payload,
        )
        return ImageSelectionManualFileResponse(
            candidate=to_image_selection_candidate_response(candidate)
        )

    @router.get(
        "/{run_id}/groups/{group_id}/manual-files/{candidate_id}",
        response_class=FileResponse,
        operation_id="getManualImageSelectionFile",
        summary="Read one managed manual-review JPEG",
        responses=ERROR_RESPONSES,
    )
    def get_manual_image_selection_file(
        run_id: UUID,
        group_id: UUID,
        candidate_id: UUID,
        service: Annotated[ImageSelectionService, service_parameter],
    ) -> FileResponse:
        return FileResponse(
            service.get_manual_file(
                run_id=run_id,
                group_id=group_id,
                candidate_id=candidate_id,
            ),
            media_type="image/jpeg",
            filename="manual-selection.jpg",
        )

    @router.post(
        "/{run_id}/groups/{group_id}/approve",
        response_model=ImageSelectionManualApprovalResponse,
        operation_id="approveManualImageSelection",
        summary="Append one idempotent manual representative decision",
        responses=ERROR_RESPONSES,
    )
    def approve_manual_image_selection(
        run_id: UUID,
        group_id: UUID,
        payload: ImageSelectionManualApprovalCommand,
        service: Annotated[ImageSelectionService, service_parameter],
    ) -> ImageSelectionManualApprovalResponse:
        approved = service.approve_manual_file(
            run_id=run_id,
            group_id=group_id,
            candidate_id=payload.candidate_id,
            idempotency_key=payload.idempotency_key,
            range_start=payload.range_start,
            range_end=payload.range_end,
        )
        return ImageSelectionManualApprovalResponse(
            group=to_image_selection_group_response(approved.group),
            decision=to_manual_decision_response(approved.decision),
        )

    @router.post(
        "/{run_id}/handoff",
        response_model=ImageSelectionHandoffResponse,
        operation_id="handoffImageSelection",
        summary="Verify and hand curated images to the explicit layout import step",
        responses=ERROR_RESPONSES,
    )
    def handoff_image_selection(
        run_id: UUID,
        service: Annotated[ImageSelectionService, service_parameter],
        folder_selection_service: Annotated[
            ImageFolderSelectionService,
            folder_selection_parameter,
        ],
    ) -> ImageSelectionHandoffResponse:
        source = service.prepare_handoff(run_id)
        selection = folder_selection_service.approve(
            source.output_directory,
            display_name=f"Wybrane zdjęcia · {run_id}",
            purpose=ImageSelectionPurpose.LAYOUT_IMPORT,
            game_id=source.run.game_id,
            image_selection_run_id=source.run.id,
            selection_id=source.run.id,
            managed=False,
        )
        return ImageSelectionHandoffResponse(
            run_id=source.run.id,
            game_id=source.run.game_id,
            selection_id=selection.selection_id,
            selection_token=selection.selection_token,
            supported_file_count=source.supported_file_count,
            expires_at=selection.expires_at,
        )

    return router


__all__ = ["create_image_selections_router"]
