"""HTTP boundary for preview-bound destructive cleanup operations."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from game_predictor_api.application.cleanup import CleanupService
from game_predictor_api.domain.cleanup import (
    BoardSourceCleanupSelection,
    CleanupCommand,
)
from game_predictor_api.domain.source_replacement import SourceReplacementError, manifest_csv
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.cleanup import (
    BoardSourceCleanupCommandRequest,
    BoardSourceCleanupPreviewRequest,
    CleanupCommandRequest,
    CleanupPreviewResponse,
    CleanupResultResponse,
)
from game_predictor_api.schemas.source_replacement import (
    SourceReplacementBatchResponse,
    SourceReplacementCandidatePage,
    SourceReplacementCreateRequest,
    SourceReplacementManifestResponse,
    SourceReplacementPreviewRequest,
    SourceReplacementRequestExport,
    SourceRetirementCommand,
    SourceRetirementPreviewRequest,
    SourceRetirementPreviewResponse,
    SourceRetirementResult,
)

CleanupServiceDependency = Callable[..., object]
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Cleanup target not found"},
    409: {"model": ErrorResponse, "description": "Cleanup state conflict"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}


def create_cleanup_router(service_dependency: CleanupServiceDependency) -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["cleanup"])
    service_parameter = Depends(service_dependency)

    @router.get(
        "/mobile-releases/{mobile_release_id}/deletion-preview",
        response_model=CleanupPreviewResponse,
        operation_id="previewMobileReleaseDeletion",
        summary="Preview complete deletion of one mobile release",
        responses=ERROR_RESPONSES,
    )
    def preview_mobile_release_deletion(
        mobile_release_id: UUID,
        service: Annotated[CleanupService, service_parameter],
    ) -> CleanupPreviewResponse:
        return CleanupPreviewResponse.from_domain(service.preview_release(mobile_release_id))

    @router.delete(
        "/mobile-releases/{mobile_release_id}",
        response_model=CleanupResultResponse,
        operation_id="deleteMobileRelease",
        summary="Delete one mobile release and its dedicated artifacts",
        responses=ERROR_RESPONSES,
    )
    def delete_mobile_release(
        mobile_release_id: UUID,
        payload: CleanupCommandRequest,
        service: Annotated[CleanupService, service_parameter],
    ) -> CleanupResultResponse:
        return CleanupResultResponse.from_domain(
            service.delete_release(
                mobile_release_id,
                CleanupCommand(
                    preview_token=payload.preview_token,
                    confirmation_target=payload.confirmation_target,
                    confirmed=payload.confirmed,
                ),
            )
        )

    @router.get(
        "/games/{game_id}/layout-data-reset-preview",
        response_model=CleanupPreviewResponse,
        operation_id="previewGameLayoutDataReset",
        summary="Preview reset of all layout workflow data for one game",
        responses=ERROR_RESPONSES,
    )
    def preview_game_layout_data_reset(
        game_id: UUID,
        service: Annotated[CleanupService, service_parameter],
    ) -> CleanupPreviewResponse:
        return CleanupPreviewResponse.from_domain(service.preview_game_reset(game_id))

    @router.delete(
        "/games/{game_id}/layout-data",
        response_model=CleanupResultResponse,
        operation_id="resetGameLayoutData",
        summary="Reset all layout workflow data for one game",
        responses=ERROR_RESPONSES,
    )
    def reset_game_layout_data(
        game_id: UUID,
        payload: CleanupCommandRequest,
        service: Annotated[CleanupService, service_parameter],
    ) -> CleanupResultResponse:
        return CleanupResultResponse.from_domain(
            service.reset_game(
                game_id,
                CleanupCommand(
                    preview_token=payload.preview_token,
                    confirmation_target=payload.confirmation_target,
                    confirmed=payload.confirmed,
                ),
            )
        )

    @router.post(
        "/games/{game_id}/board-source-cleanup-preview",
        response_model=CleanupPreviewResponse
        | SourceReplacementManifestResponse
        | SourceRetirementPreviewResponse,
        operation_id="previewBoardSourceCleanup",
        summary="Preview deletion of complete image-source ranges selected by board number",
        responses=ERROR_RESPONSES,
    )
    def preview_board_source_cleanup(
        game_id: UUID,
        payload: BoardSourceCleanupPreviewRequest
        | SourceReplacementPreviewRequest
        | SourceRetirementPreviewRequest,
        service: Annotated[CleanupService, service_parameter],
    ) -> (
        CleanupPreviewResponse | SourceReplacementManifestResponse | SourceRetirementPreviewResponse
    ):
        if isinstance(payload, SourceRetirementPreviewRequest):
            return SourceRetirementPreviewResponse.model_validate(
                service.replacement_plans.retirement_preview(game_id, payload)
            )
        if isinstance(payload, SourceReplacementPreviewRequest):
            return SourceReplacementManifestResponse.model_validate(
                service.replacement_plans.preview(game_id, payload.source_ids)
            )
        return CleanupPreviewResponse.from_domain(
            service.preview_board_sources(
                game_id,
                _selection(payload.sequence_numbers),
            )
        )

    @router.delete(
        "/games/{game_id}/board-sources",
        response_model=CleanupResultResponse | SourceRetirementResult,
        operation_id="deleteBoardSourceRanges",
        summary="Delete complete image-source ranges and their dependent board data",
        responses=ERROR_RESPONSES,
    )
    def delete_board_source_ranges(
        game_id: UUID,
        payload: BoardSourceCleanupCommandRequest
        | SourceReplacementCreateRequest
        | SourceRetirementCommand,
        service: Annotated[CleanupService, service_parameter],
    ) -> CleanupResultResponse | SourceRetirementResult:
        if isinstance(payload, SourceRetirementCommand):
            return SourceRetirementResult.model_validate(
                service.replacement_plans.retirement_command(game_id, payload)
            )
        if isinstance(payload, SourceReplacementCreateRequest):
            raise SourceReplacementError(
                "SOURCE_REPLACEMENT_RETIREMENT_NOT_READY",
                "Wycofanie źródeł nie jest jeszcze dostępne.",
            )
        return CleanupResultResponse.from_domain(
            service.delete_board_sources(
                game_id,
                _selection(payload.sequence_numbers),
                CleanupCommand(
                    preview_token=payload.preview_token,
                    confirmation_target=payload.confirmation_target,
                    confirmed=payload.confirmed,
                ),
            )
        )

    @router.get(
        "/games/{game_id}/board-sources/candidates",
        response_model=SourceReplacementCandidatePage,
        operation_id="listSourceReplacementCandidates",
        responses=ERROR_RESPONSES,
    )
    def candidates(
        game_id: UUID,
        service: Annotated[CleanupService, service_parameter],
        offset: int = Query(default=0, ge=0, le=1000000),
    ) -> SourceReplacementCandidatePage:
        return SourceReplacementCandidatePage.model_validate(
            service.replacement_plans.candidates(game_id, offset)
        )

    @router.post(
        "/games/{game_id}/board-sources",
        response_model=SourceReplacementManifestResponse,
        operation_id="planSourceReplacement",
        responses=ERROR_RESPONSES,
    )
    def plan(
        game_id: UUID,
        payload: SourceReplacementCreateRequest,
        service: Annotated[CleanupService, service_parameter],
    ) -> SourceReplacementManifestResponse:
        return SourceReplacementManifestResponse.model_validate(
            service.replacement_plans.create(game_id, payload)
        )

    @router.get(
        "/games/{game_id}/board-sources",
        response_model=list[SourceReplacementBatchResponse],
        operation_id="listSourceReplacementBatches",
        responses=ERROR_RESPONSES,
    )
    def batches(
        game_id: UUID, service: Annotated[CleanupService, service_parameter]
    ) -> list[SourceReplacementBatchResponse]:
        return [
            SourceReplacementBatchResponse.model_validate(row)
            for row in service.replacement_plans.list(game_id)
        ]

    @router.get(
        "/games/{game_id}/board-sources/{batch_id}",
        response_model=SourceReplacementManifestResponse,
        operation_id="getSourceReplacementBatch",
        responses=ERROR_RESPONSES,
    )
    def batch(
        game_id: UUID, batch_id: UUID, service: Annotated[CleanupService, service_parameter]
    ) -> SourceReplacementManifestResponse:
        return SourceReplacementManifestResponse.model_validate(
            service.replacement_plans.get(game_id, batch_id)
        )

    @router.get(
        "/games/{game_id}/board-sources/{batch_id}/export",
        operation_id="exportSourceReplacementBatch",
        responses={200: {"content": {"text/csv": {}, "application/json": {}}}, **ERROR_RESPONSES},
    )
    def export(
        game_id: UUID,
        batch_id: UUID,
        service: Annotated[CleanupService, service_parameter],
        format: str = Query(default="json", pattern="^(json|csv)$"),
    ) -> Response:
        document = service.replacement_plans.get(game_id, batch_id)
        if format == "csv":
            return Response(
                manifest_csv(document),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f'attachment; filename="replacement-{batch_id}.csv"'
                },
            )
        return Response(
            SourceReplacementManifestResponse.model_validate(document).model_dump_json(
                by_alias=True
            ),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="replacement-{batch_id}.json"'},
        )

    @router.get(
        "/games/{game_id}/board-sources/{batch_id}/replacement-request",
        response_model=SourceReplacementRequestExport,
        operation_id="exportSourceReplacementRequest",
        responses=ERROR_RESPONSES,
    )
    def replacement_request(
        game_id: UUID,
        batch_id: UUID,
        service: Annotated[CleanupService, service_parameter],
        entry_ids: Annotated[list[UUID], Query(alias="entryIds", min_length=1, max_length=50)],
    ) -> SourceReplacementRequestExport:
        return SourceReplacementRequestExport.model_validate(
            service.replacement_plans.replacement_request(game_id, batch_id, entry_ids)
        )

    return router


def _selection(sequence_numbers: tuple[int, ...]) -> BoardSourceCleanupSelection:
    return BoardSourceCleanupSelection(tuple(sorted(set(sequence_numbers))))


__all__ = ["create_cleanup_router"]
