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
    ImageSelectionDuplicateRangeCommand,
    ImageSelectionGroupCandidatesResponse,
    ImageSelectionGroupDecisionCommand,
    ImageSelectionGroupPageResponse,
    ImageSelectionHandoffResponse,
    ImageSelectionManualApprovalCommand,
    ImageSelectionManualApprovalResponse,
    ImageSelectionManualFileResponse,
    ImageSelectionMissingImageCommand,
    ImageSelectionOutputFileResponse,
    ImageSelectionOutputResponse,
    ImageSelectionRangeConfirmationCommand,
    ImageSelectionRerunCommand,
    ImageSelectionRunPageResponse,
    ImageSelectionRunResponse,
    to_image_selection_candidate_response,
    to_image_selection_group_candidates_response,
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
            sequence_direction=payload.sequence_direction,
            first_sequence_number=payload.first_sequence_number,
        )
        return ImageSelectionCreateResponse(
            run=to_image_selection_run_response(run),
            created=created,
        )

    @router.get(
        "",
        response_model=ImageSelectionRunPageResponse,
        operation_id="listImageSelections",
        summary="List durable image-selection runs for one game",
        responses=ERROR_RESPONSES,
    )
    def list_image_selections(
        service: Annotated[ImageSelectionService, service_parameter],
        game_id: Annotated[UUID, Query(alias="gameId")],
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
    ) -> ImageSelectionRunPageResponse:
        runs, next_offset = service.list_runs(
            game_id=game_id,
            offset=offset,
            limit=limit,
        )
        return ImageSelectionRunPageResponse(
            items=[to_image_selection_run_response(run) for run in runs],
            next_offset=next_offset,
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

    @router.post(
        "/{run_id}/rerun",
        response_model=ImageSelectionCreateResponse,
        operation_id="rerunImageSelection",
        summary="Run the current selector against an existing managed staging",
        responses=ERROR_RESPONSES,
    )
    def rerun_image_selection(
        run_id: UUID,
        service: Annotated[ImageSelectionService, service_parameter],
        payload: Annotated[ImageSelectionRerunCommand | None, Body()] = None,
    ) -> ImageSelectionCreateResponse:
        run, created = service.rerun(
            run_id=run_id,
            selector_fingerprint=IMAGE_SELECTION_SELECTOR_FINGERPRINT,
            first_sequence_number=(None if payload is None else payload.first_sequence_number),
        )
        return ImageSelectionCreateResponse(
            run=to_image_selection_run_response(run),
            created=created,
        )

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

    @router.get(
        "/{run_id}/groups/{group_id}/candidates",
        response_model=ImageSelectionGroupCandidatesResponse,
        operation_id="listImageSelectionGroupCandidates",
        summary="List bounded source candidates identifying one review group",
        responses=ERROR_RESPONSES,
    )
    def list_image_selection_group_candidates(
        run_id: UUID,
        group_id: UUID,
        service: Annotated[ImageSelectionService, service_parameter],
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> ImageSelectionGroupCandidatesResponse:
        return to_image_selection_group_candidates_response(
            group_id=group_id,
            candidates=service.list_group_candidates(
                run_id=run_id,
                group_id=group_id,
                limit=limit,
            ),
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

    @router.get(
        "/{run_id}/groups/{group_id}/candidates/{candidate_id}/file",
        response_class=FileResponse,
        operation_id="getImageSelectionCandidateFile",
        summary="Read one staged or manually uploaded candidate JPEG",
        responses=ERROR_RESPONSES,
    )
    def get_image_selection_candidate_file(
        run_id: UUID,
        group_id: UUID,
        candidate_id: UUID,
        service: Annotated[ImageSelectionService, service_parameter],
    ) -> FileResponse:
        path, file_name = service.get_candidate_file(
            run_id=run_id,
            group_id=group_id,
            candidate_id=candidate_id,
        )
        return FileResponse(path, media_type="image/jpeg", filename=file_name)

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
        "/{run_id}/groups/{group_id}/continue-without-image",
        response_model=ImageSelectionManualApprovalResponse,
        operation_id="continueImageSelectionWithoutImage",
        summary="Resolve one review range without requiring a representative JPEG",
        responses=ERROR_RESPONSES,
    )
    def continue_image_selection_without_image(
        run_id: UUID,
        group_id: UUID,
        payload: ImageSelectionMissingImageCommand,
        service: Annotated[ImageSelectionService, service_parameter],
    ) -> ImageSelectionManualApprovalResponse:
        resolved = service.continue_without_image(
            run_id=run_id,
            group_id=group_id,
            idempotency_key=payload.idempotency_key,
            range_start=payload.range_start,
            range_end=payload.range_end,
        )
        return ImageSelectionManualApprovalResponse(
            group=to_image_selection_group_response(resolved.group),
            decision=to_manual_decision_response(resolved.decision),
        )

    @router.post(
        "/{run_id}/groups/{group_id}/discard-duplicate",
        response_model=ImageSelectionManualApprovalResponse,
        operation_id="discardDuplicateImageSelectionGroup",
        summary="Discard one manual-review group whose range is already resolved",
        responses=ERROR_RESPONSES,
    )
    def discard_duplicate_image_selection_group(
        run_id: UUID,
        group_id: UUID,
        payload: ImageSelectionDuplicateRangeCommand,
        service: Annotated[ImageSelectionService, service_parameter],
    ) -> ImageSelectionManualApprovalResponse:
        discarded = service.discard_duplicate_range(
            run_id=run_id,
            group_id=group_id,
            idempotency_key=payload.idempotency_key,
            range_start=payload.range_start,
            range_end=payload.range_end,
        )
        return ImageSelectionManualApprovalResponse(
            group=to_image_selection_group_response(discarded.group),
            decision=to_manual_decision_response(discarded.decision),
        )

    @router.post(
        "/{run_id}/groups/{group_id}/confirm-range",
        response_model=ImageSelectionManualApprovalResponse,
        operation_id="confirmImageSelectionGroupRange",
        summary="Confirm a range for one automatically represented group",
        responses=ERROR_RESPONSES,
    )
    def confirm_image_selection_group_range(
        run_id: UUID,
        group_id: UUID,
        payload: ImageSelectionRangeConfirmationCommand,
        service: Annotated[ImageSelectionService, service_parameter],
    ) -> ImageSelectionManualApprovalResponse:
        confirmed = service.confirm_automatic_range(
            run_id=run_id,
            group_id=group_id,
            idempotency_key=payload.idempotency_key,
            range_start=payload.range_start,
            range_end=payload.range_end,
        )
        return ImageSelectionManualApprovalResponse(
            group=to_image_selection_group_response(confirmed.group),
            decision=to_manual_decision_response(confirmed.decision),
        )

    @router.post(
        "/{run_id}/groups/{group_id}/reject",
        response_model=ImageSelectionManualApprovalResponse,
        operation_id="rejectImageSelectionReviewGroup",
        summary="Reject one representative- or range-review group",
        responses=ERROR_RESPONSES,
    )
    def reject_image_selection_review_group(
        run_id: UUID,
        group_id: UUID,
        payload: ImageSelectionGroupDecisionCommand,
        service: Annotated[ImageSelectionService, service_parameter],
    ) -> ImageSelectionManualApprovalResponse:
        rejected = service.reject_review_group(
            run_id=run_id,
            group_id=group_id,
            idempotency_key=payload.idempotency_key,
        )
        return ImageSelectionManualApprovalResponse(
            group=to_image_selection_group_response(rejected.group),
            decision=to_manual_decision_response(rejected.decision),
        )

    @router.post(
        "/{run_id}/groups/{group_id}/restore",
        response_model=ImageSelectionManualApprovalResponse,
        operation_id="restoreRejectedImageSelectionGroup",
        summary="Restore one user-rejected group to its prior review queue",
        responses=ERROR_RESPONSES,
    )
    def restore_rejected_image_selection_group(
        run_id: UUID,
        group_id: UUID,
        payload: ImageSelectionGroupDecisionCommand,
        service: Annotated[ImageSelectionService, service_parameter],
    ) -> ImageSelectionManualApprovalResponse:
        restored = service.restore_rejected_group(
            run_id=run_id,
            group_id=group_id,
            idempotency_key=payload.idempotency_key,
        )
        return ImageSelectionManualApprovalResponse(
            group=to_image_selection_group_response(restored.group),
            decision=to_manual_decision_response(restored.decision),
        )

    @router.get(
        "/{run_id}/groups/{group_id}/selected-file",
        response_class=FileResponse,
        operation_id="getImageSelectionSelectedGroupFile",
        summary="Read one selected JPEG as soon as its group is finalized",
        responses=ERROR_RESPONSES,
    )
    def get_image_selection_selected_group_file(
        run_id: UUID,
        group_id: UUID,
        service: Annotated[ImageSelectionService, service_parameter],
    ) -> FileResponse:
        path, file_name = service.get_selected_group_file(
            run_id=run_id,
            group_id=group_id,
        )
        return FileResponse(path, media_type="image/jpeg", filename=file_name)

    @router.get(
        "/{run_id}/output",
        response_model=ImageSelectionOutputResponse,
        operation_id="getImageSelectionOutput",
        summary="List the verified curated JPEG files available for export",
        responses=ERROR_RESPONSES,
    )
    def get_image_selection_output(
        run_id: UUID,
        service: Annotated[ImageSelectionService, service_parameter],
    ) -> ImageSelectionOutputResponse:
        output = service.get_output(run_id)
        return ImageSelectionOutputResponse(
            run_id=output.run_id,
            manifest_sha256=output.manifest_sha256,
            files=[
                ImageSelectionOutputFileResponse(
                    file_name=item.file_name,
                    group_order=item.group_order,
                    range_start=item.range_start,
                    range_end=item.range_end,
                    checksum_sha256=item.checksum_sha256,
                    size_bytes=item.size_bytes,
                    reason_codes=list(item.reason_codes),
                    selection_method=item.selection_method,
                )
                for item in output.files
            ],
        )

    @router.get(
        "/{run_id}/output/{file_name}",
        response_class=FileResponse,
        operation_id="getImageSelectionOutputFile",
        summary="Download one checksum-verified curated JPEG",
        responses=ERROR_RESPONSES,
    )
    def get_image_selection_output_file(
        run_id: UUID,
        file_name: str,
        service: Annotated[ImageSelectionService, service_parameter],
    ) -> FileResponse:
        return FileResponse(
            service.get_output_file(run_id, file_name),
            media_type="image/jpeg",
            filename=file_name,
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
