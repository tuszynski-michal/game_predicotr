"""Local Admin HTTP boundary for semi-automatic image selection."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from game_predictor_api.application.semi_automatic_image_selections import (
    SemiAutomaticImageSelectionService,
)
from game_predictor_api.domain.semi_automatic_image_selections import (
    SemiAutomaticSelectionWorkflowMode,
)
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.semi_automatic_image_selections import (
    FilenameRangeVerificationItemResponse,
    FilenameRangeVerificationPageResponse,
    FilenameRangeVerificationReviewDecisionResponse,
    FilenameRangeVerificationReviewDecisionUpdate,
    SemiAutomaticSelectionCapabilitiesResponse,
    SemiAutomaticSelectionCreate,
    SemiAutomaticSelectionCreateResponse,
    SemiAutomaticSelectionDiagnosticsResponse,
    SemiAutomaticSelectionOutputAcknowledgement,
    SemiAutomaticSelectionRangePageResponse,
    SemiAutomaticSelectionRangeResponse,
    SemiAutomaticSelectionRunPageResponse,
    SemiAutomaticSelectionRunResponse,
    to_filename_verification_review_response,
    to_range_response,
    to_run_response,
)

ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Run, range, or source not found"},
    409: {"model": ErrorResponse, "description": "Durable selection conflict"},
    422: {"model": ErrorResponse, "description": "Invalid selection input"},
}


def create_semi_automatic_image_selections_router(
    service_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(
        prefix="/admin/semi-automatic-image-selections",
        tags=["semi-automatic-image-selections"],
    )
    service_parameter = Depends(service_dependency)

    @router.get(
        "/capabilities",
        response_model=SemiAutomaticSelectionCapabilitiesResponse,
        operation_id="getSemiAutomaticImageSelectionCapabilities",
    )
    def capabilities(
        service: Annotated[SemiAutomaticImageSelectionService, service_parameter],
    ) -> SemiAutomaticSelectionCapabilitiesResponse:
        return SemiAutomaticSelectionCapabilitiesResponse.model_validate(service.capabilities())

    @router.post(
        "",
        response_model=SemiAutomaticSelectionCreateResponse,
        operation_id="createSemiAutomaticImageSelection",
        responses=ERROR_RESPONSES,
    )
    def create_run(
        payload: SemiAutomaticSelectionCreate,
        service: Annotated[SemiAutomaticImageSelectionService, service_parameter],
    ) -> SemiAutomaticSelectionCreateResponse:
        run, created = service.create(
            upload_id=payload.upload_id,
            first_sequence_number=payload.first_sequence_number,
            last_sequence_number=payload.last_sequence_number,
            direction=payload.direction,
            mode=payload.mode,
        )
        return SemiAutomaticSelectionCreateResponse(run=to_run_response(run), created=created)

    @router.get(
        "",
        response_model=SemiAutomaticSelectionRunPageResponse,
        operation_id="listSemiAutomaticImageSelections",
        responses=ERROR_RESPONSES,
    )
    def list_runs(
        service: Annotated[SemiAutomaticImageSelectionService, service_parameter],
        workflow_mode: Annotated[SemiAutomaticSelectionWorkflowMode, Query(alias="workflowMode")],
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> SemiAutomaticSelectionRunPageResponse:
        runs, next_offset = service.list_runs(
            workflow_mode=workflow_mode,
            offset=offset,
            limit=limit,
        )
        return SemiAutomaticSelectionRunPageResponse(
            items=[to_run_response(run) for run in runs],
            next_offset=next_offset,
        )

    @router.get(
        "/{run_id}",
        response_model=SemiAutomaticSelectionRunResponse,
        operation_id="getSemiAutomaticImageSelection",
        responses=ERROR_RESPONSES,
    )
    def get_run(
        run_id: UUID,
        service: Annotated[SemiAutomaticImageSelectionService, service_parameter],
    ) -> SemiAutomaticSelectionRunResponse:
        return to_run_response(service.get(run_id))

    @router.get(
        "/{run_id}/ranges",
        response_model=SemiAutomaticSelectionRangePageResponse,
        operation_id="listSemiAutomaticImageSelectionRanges",
        responses=ERROR_RESPONSES,
    )
    def list_ranges(
        run_id: UUID,
        service: Annotated[SemiAutomaticImageSelectionService, service_parameter],
        after_expected_index: Annotated[int | None, Query(ge=0)] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> SemiAutomaticSelectionRangePageResponse:
        items = service.list_ranges(
            run_id,
            after_expected_index=after_expected_index,
            limit=limit,
        )
        return SemiAutomaticSelectionRangePageResponse(
            items=[to_range_response(item) for item in items],
            next_after_expected_index=(items[-1].expected_index if len(items) == limit else None),
        )

    @router.get(
        "/{run_id}/filename-verifications",
        response_model=FilenameRangeVerificationPageResponse,
        operation_id="listSemiAutomaticFilenameRangeVerifications",
        responses=ERROR_RESPONSES,
    )
    def list_filename_verifications(
        run_id: UUID,
        service: Annotated[SemiAutomaticImageSelectionService, service_parameter],
        after_source_index: Annotated[int | None, Query(ge=0)] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> FilenameRangeVerificationPageResponse:
        items = service.list_filename_verification_items(
            run_id,
            after_source_index=after_source_index,
            limit=limit,
        )
        responses = [FilenameRangeVerificationItemResponse.model_validate(item) for item in items]
        return FilenameRangeVerificationPageResponse(
            items=responses,
            next_after_source_index=(
                responses[-1].source_index if len(responses) == limit else None
            ),
        )

    @router.put(
        "/{run_id}/filename-verifications/{source_index}/review-decision",
        response_model=FilenameRangeVerificationReviewDecisionResponse,
        operation_id="decideSemiAutomaticFilenameRangeVerification",
        responses=ERROR_RESPONSES,
    )
    def decide_filename_verification(
        run_id: UUID,
        source_index: int,
        payload: FilenameRangeVerificationReviewDecisionUpdate,
        service: Annotated[SemiAutomaticImageSelectionService, service_parameter],
    ) -> FilenameRangeVerificationReviewDecisionResponse:
        review = service.decide_filename_verification(
            run_id,
            source_index,
            decision=payload.decision,
            expected_source_checksum_sha256=payload.expected_source_checksum_sha256,
            expected_revision=payload.expected_revision,
        )
        return to_filename_verification_review_response(review)

    @router.get(
        "/{run_id}/diagnostics",
        response_model=SemiAutomaticSelectionDiagnosticsResponse,
        operation_id="getSemiAutomaticImageSelectionDiagnostics",
        responses=ERROR_RESPONSES,
    )
    def diagnostics(
        run_id: UUID,
        service: Annotated[SemiAutomaticImageSelectionService, service_parameter],
    ) -> SemiAutomaticSelectionDiagnosticsResponse:
        run = service.get(run_id)
        return SemiAutomaticSelectionDiagnosticsResponse(
            run_id=run.id,
            available=(
                run.diagnostics_relative_path is not None
                and run.diagnostics_checksum_sha256 is not None
            ),
            relative_path=run.diagnostics_relative_path,
            checksum_sha256=run.diagnostics_checksum_sha256,
            checkpoint=dict(run.checkpoint),
            counters=dict(run.counters),
        )

    @router.get(
        "/{run_id}/sources/{source_index}/asset",
        response_class=FileResponse,
        operation_id="getSemiAutomaticImageSelectionSourceAsset",
        responses=ERROR_RESPONSES,
    )
    def source_asset(
        run_id: UUID,
        source_index: int,
        expected_checksum_sha256: Annotated[str, Query(pattern=r"^[0-9a-f]{64}$")],
        service: Annotated[SemiAutomaticImageSelectionService, service_parameter],
    ) -> FileResponse:
        path, file_name = service.source_asset(
            run_id,
            source_index,
            expected_checksum_sha256=expected_checksum_sha256,
        )
        return FileResponse(path, media_type="image/jpeg", filename=file_name)

    @router.post(
        "/{run_id}/pause",
        response_model=SemiAutomaticSelectionRunResponse,
        operation_id="pauseSemiAutomaticImageSelection",
        responses=ERROR_RESPONSES,
    )
    def pause(
        run_id: UUID,
        service: Annotated[SemiAutomaticImageSelectionService, service_parameter],
    ) -> SemiAutomaticSelectionRunResponse:
        return to_run_response(service.pause(run_id))

    @router.post(
        "/{run_id}/resume",
        response_model=SemiAutomaticSelectionRunResponse,
        operation_id="resumeSemiAutomaticImageSelection",
        responses=ERROR_RESPONSES,
    )
    def resume(
        run_id: UUID,
        service: Annotated[SemiAutomaticImageSelectionService, service_parameter],
    ) -> SemiAutomaticSelectionRunResponse:
        return to_run_response(service.resume(run_id))

    @router.post(
        "/{run_id}/cancel",
        response_model=SemiAutomaticSelectionRunResponse,
        operation_id="cancelSemiAutomaticImageSelection",
        responses=ERROR_RESPONSES,
    )
    def cancel(
        run_id: UUID,
        service: Annotated[SemiAutomaticImageSelectionService, service_parameter],
    ) -> SemiAutomaticSelectionRunResponse:
        return to_run_response(service.cancel(run_id))

    @router.post(
        "/{run_id}/ranges/{expected_index}/output-acknowledgements",
        response_model=SemiAutomaticSelectionRangeResponse,
        operation_id="acknowledgeSemiAutomaticImageSelectionOutput",
        responses=ERROR_RESPONSES,
    )
    def acknowledge(
        run_id: UUID,
        expected_index: int,
        payload: SemiAutomaticSelectionOutputAcknowledgement,
        service: Annotated[SemiAutomaticImageSelectionService, service_parameter],
    ) -> SemiAutomaticSelectionRangeResponse:
        return to_range_response(
            service.acknowledge_output(
                run_id,
                expected_index,
                expected_revision=payload.expected_revision,
                expected_source_checksum_sha256=payload.expected_source_checksum_sha256,
                output_checksum_sha256=payload.output_checksum_sha256,
                source_index=payload.source_index,
            )
        )

    return router


__all__ = ["create_semi_automatic_image_selections_router"]
