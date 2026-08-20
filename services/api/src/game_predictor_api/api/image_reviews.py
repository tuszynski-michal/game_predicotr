"""HTTP surface for the operational image review workbench."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, Response

from game_predictor_api.api.reviewer_security import (
    create_optional_reviewer_session_dependency,
)
from game_predictor_api.application.image_review_assets import (
    OperationalReviewAsset,
    resolve_operational_board_asset,
    resolve_operational_cell_asset,
    resolve_operational_source_asset,
)
from game_predictor_api.application.image_reviews import (
    OperationalImageReviewService,
)
from game_predictor_api.application.jobs import JobService
from game_predictor_api.application.reviewer_access import (
    ReviewerAccessService,
    ReviewerAccessSession,
)
from game_predictor_api.domain.image_reviews import (
    MAX_IMAGE_REVIEW_PAGE_SIZE,
    ImageReviewGeometryPoint,
    ImageReviewResolutionCell,
    ImageReviewView,
)
from game_predictor_api.domain.jobs import JobError
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.image_reviews import (
    CanonicalImageReviewPageResponse,
    ImageDatasetCompletenessResponse,
    ImageSequenceSourceOverrideCommand,
    ImageSequenceSourceSelectionResponse,
    OperationalImageReviewGeometryCommand,
    OperationalImageReviewGeometryPreviewCommand,
    OperationalImageReviewGeometryResponse,
    OperationalImageReviewItemResponse,
    OperationalImageReviewPageResponse,
    OperationalImageReviewResolutionCommand,
    OperationalImageReviewResolutionEventResponse,
    OperationalImageReviewResolutionResponse,
    PendingGridReinferencePreviewResponse,
    PendingSymbolReinferencePreviewResponse,
    to_canonical_page_response,
    to_image_dataset_completeness_response,
    to_image_sequence_source_selection_response,
    to_operational_event_response,
    to_operational_geometry_revision_response,
    to_operational_item_response,
    to_operational_page_response,
    to_pending_grid_reinference_preview_response,
)
from game_predictor_api.schemas.jobs import JobResponse

OperationalImageReviewServiceDependency = Callable[..., object]
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Operational review resource not found"},
    409: {"model": ErrorResponse, "description": "Operational review conflict"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}


def create_image_reviews_router(
    service_dependency: OperationalImageReviewServiceDependency,
    artifact_root: Path,
    reviewer_access_service_dependency: Callable[..., object],
    job_service_dependency: Callable[..., object] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/admin/image-review-items", tags=["image-reviews"])
    service_parameter = Depends(service_dependency)
    reviewer_parameter = Depends(
        create_optional_reviewer_session_dependency(reviewer_access_service_dependency)
    )

    def authorize(
        reviewer_session: ReviewerAccessSession | None,
        reviewer_access_service: ReviewerAccessService,
        game_id: UUID,
        import_job_id: UUID,
    ) -> str | None:
        if reviewer_session is None:
            return None
        reviewer_access_service.authorize_scope(
            reviewer_session,
            game_id=game_id,
            import_job_id=import_job_id,
        )
        return f"reviewer-session:{reviewer_session.id}"

    reviewer_service_parameter = Depends(reviewer_access_service_dependency)
    job_parameter = None if job_service_dependency is None else Depends(job_service_dependency)

    @router.get(
        "/dataset-completeness/{game_id}",
        response_model=ImageDatasetCompletenessResponse,
        operation_id="getImageDatasetCompleteness",
        summary="Get accepted image sequence completeness for one game",
        responses=ERROR_RESPONSES,
    )
    def get_image_dataset_completeness(
        game_id: UUID,
        service: Annotated[OperationalImageReviewService, service_parameter],
    ) -> ImageDatasetCompletenessResponse:
        return to_image_dataset_completeness_response(service.dataset_completeness(game_id))

    @router.get(
        "/sequence-sources/{game_id}/{sequence_number}",
        response_model=ImageSequenceSourceSelectionResponse,
        operation_id="getImageSequenceSourceSelection",
        summary="Get ranked accepted sources for one game sequence",
        responses=ERROR_RESPONSES,
    )
    def get_image_sequence_source_selection(
        game_id: UUID,
        sequence_number: int,
        service: Annotated[OperationalImageReviewService, service_parameter],
    ) -> ImageSequenceSourceSelectionResponse:
        return to_image_sequence_source_selection_response(
            service.sequence_source_selection(game_id, sequence_number)
        )

    @router.post(
        "/sequence-sources/{game_id}/{sequence_number}/override",
        response_model=ImageSequenceSourceSelectionResponse,
        operation_id="selectImageSequenceSource",
        summary="Select or clear the manual source override for one sequence",
        responses=ERROR_RESPONSES,
    )
    def select_image_sequence_source(
        game_id: UUID,
        sequence_number: int,
        payload: ImageSequenceSourceOverrideCommand,
        service: Annotated[OperationalImageReviewService, service_parameter],
    ) -> ImageSequenceSourceSelectionResponse:
        return to_image_sequence_source_selection_response(
            service.select_sequence_source(
                game_id=game_id,
                sequence_number=sequence_number,
                review_item_id=payload.review_item_id,
                selected_by=payload.selected_by,
            )
        )

    @router.get(
        "",
        response_model=OperationalImageReviewPageResponse,
        operation_id="listOperationalImageReviewItems",
        summary="List one bounded page of job-local image review items",
        responses=ERROR_RESPONSES,
    )
    def list_operational_image_review_items(
        service: Annotated[OperationalImageReviewService, service_parameter],
        reviewer_session: Annotated[ReviewerAccessSession | None, reviewer_parameter],
        reviewer_access_service: Annotated[
            ReviewerAccessService,
            reviewer_service_parameter,
        ],
        game_id: Annotated[UUID, Query(alias="gameId")],
        import_job_id: Annotated[UUID, Query(alias="importJobId")],
        view: ImageReviewView = ImageReviewView.PENDING,
        after_cursor: Annotated[str | None, Query(alias="afterCursor")] = None,
        before_cursor: Annotated[str | None, Query(alias="beforeCursor")] = None,
        sequence_number: Annotated[
            int | None,
            Query(alias="sequenceNumber", ge=1),
        ] = None,
        resume_at_first_pending: Annotated[
            bool,
            Query(alias="resumeAtFirstPending"),
        ] = False,
        limit: Annotated[int, Query(ge=1, le=MAX_IMAGE_REVIEW_PAGE_SIZE)] = 25,
    ) -> OperationalImageReviewPageResponse:
        authorize(reviewer_session, reviewer_access_service, game_id, import_job_id)
        return to_operational_page_response(
            service.list_items(
                game_id=game_id,
                import_job_id=import_job_id,
                view=view,
                after_cursor=after_cursor,
                before_cursor=before_cursor,
                sequence_number=sequence_number,
                resume_at_first_pending=resume_at_first_pending,
                limit=limit,
            )
        )

    @router.get(
        "/canonical/{game_id}",
        response_model=CanonicalImageReviewPageResponse,
        operation_id="listCanonicalImageReviewItems",
        summary="List the game-wide pending review queue in sequence order",
        responses=ERROR_RESPONSES,
    )
    def list_canonical_image_review_items(
        game_id: UUID,
        service: Annotated[OperationalImageReviewService, service_parameter],
        after_sequence: Annotated[
            int | None,
            Query(alias="afterSequence", ge=1),
        ] = None,
        limit: Annotated[int, Query(ge=1, le=MAX_IMAGE_REVIEW_PAGE_SIZE)] = 25,
    ) -> CanonicalImageReviewPageResponse:
        return to_canonical_page_response(
            service.list_canonical_pending_items(
                game_id=game_id,
                after_sequence=after_sequence,
                limit=limit,
            )
        )

    @router.get(
        "/pending-symbol-reinference/preview/{game_id}",
        response_model=PendingSymbolReinferencePreviewResponse,
        operation_id="previewPendingSymbolReinference",
        summary="Preview the explicit pending-only symbol recalculation",
        responses=ERROR_RESPONSES,
    )
    def preview_pending_symbol_reinference(
        game_id: UUID,
        service: Annotated[OperationalImageReviewService, service_parameter],
    ) -> PendingSymbolReinferencePreviewResponse:
        pending = service.canonical_pending_count(game_id)
        counts = service.game_counts(game_id)
        return PendingSymbolReinferencePreviewResponse(
            game_id=game_id,
            pending_count=pending,
            protected_resolved_count=counts.accepted + counts.corrected + counts.rejected,
        )

    @router.post(
        "/pending-symbol-reinference/{game_id}",
        response_model=JobResponse,
        operation_id="startPendingSymbolReinference",
        summary="Start an explicit pending-only symbol recalculation",
        responses=ERROR_RESPONSES,
    )
    def start_pending_symbol_reinference(
        game_id: UUID,
        service: Annotated[OperationalImageReviewService, service_parameter],
        job_service: JobService | None = job_parameter,
    ) -> JobResponse:
        if job_service is None:
            raise JobError(
                "IMAGE_SYMBOL_REINFERENCE_UNAVAILABLE",
                "Pending symbol reinference is not configured.",
            )
        pending = service.canonical_pending_count(game_id)
        if pending == 0:
            raise JobError(
                "IMAGE_SYMBOL_REINFERENCE_EMPTY",
                "There are no pending symbol predictions to recalculate.",
            )
        job = job_service.create_pending_symbol_reinference_job(game_id=game_id)
        return JobResponse.from_domain(job)

    @router.get(
        "/pending-grid-reinference/preview/{game_id}",
        response_model=PendingGridReinferencePreviewResponse,
        operation_id="previewPendingGridReinference",
        summary="Preview pending-only grid and crop recalculation",
        responses=ERROR_RESPONSES,
    )
    def preview_pending_grid_reinference(
        game_id: UUID,
        service: Annotated[OperationalImageReviewService, service_parameter],
    ) -> PendingGridReinferencePreviewResponse:
        return to_pending_grid_reinference_preview_response(
            service.pending_grid_reinference_preview(game_id)
        )

    @router.post(
        "/pending-grid-reinference/{game_id}",
        response_model=JobResponse,
        operation_id="startPendingGridReinference",
        summary="Start pending-only grid and crop recalculation",
        responses=ERROR_RESPONSES,
    )
    def start_pending_grid_reinference(
        game_id: UUID,
        service: Annotated[OperationalImageReviewService, service_parameter],
        job_service: JobService | None = job_parameter,
    ) -> JobResponse:
        if job_service is None:
            raise JobError(
                "IMAGE_GRID_REINFERENCE_UNAVAILABLE",
                "Pending grid reinference is not configured.",
            )
        preview = service.pending_grid_reinference_preview(game_id)
        if preview.pending_board_count == 0:
            raise JobError(
                "IMAGE_GRID_REINFERENCE_EMPTY",
                "There are no pending board geometries to recalculate.",
            )
        return JobResponse.from_domain(
            job_service.create_pending_grid_reinference_job(game_id=game_id)
        )

    @router.post(
        "/{review_item_id}/geometry-preview",
        response_class=Response,
        operation_id="previewOperationalImageReviewGeometry",
        summary="Preview 15 corrected v19 board-cell crops without persistence",
        responses={
            **ERROR_RESPONSES,
            200: {
                "content": {"image/png": {}},
                "description": "Five by three contact sheet of final source-direct crops",
            },
        },
    )
    def preview_operational_image_review_geometry(
        review_item_id: UUID,
        payload: OperationalImageReviewGeometryPreviewCommand,
        service: Annotated[OperationalImageReviewService, service_parameter],
        reviewer_session: Annotated[ReviewerAccessSession | None, reviewer_parameter],
        reviewer_access_service: Annotated[
            ReviewerAccessService,
            reviewer_service_parameter,
        ],
        game_id: Annotated[UUID, Query(alias="gameId")],
        import_job_id: Annotated[UUID, Query(alias="importJobId")],
    ) -> Response:
        authorize(reviewer_session, reviewer_access_service, game_id, import_job_id)
        preview = service.preview_geometry(
            review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
            expected_geometry_revision=payload.expected_geometry_revision,
            expected_resolution_revision=payload.expected_resolution_revision,
            corners=tuple(
                ImageReviewGeometryPoint(x=point.x, y=point.y) for point in payload.corners
            ),
        )
        return Response(
            content=preview.contact_sheet_png,
            media_type="image/png",
            headers={
                "Cache-Control": "no-store",
                "X-Board-Cell-Count": str(len(preview.cells)),
                "X-Board-Cell-Cropper-Fingerprint-Sha256": (preview.cropper_fingerprint_sha256),
                "X-Board-Cell-Cropper-Version": preview.cropper_version,
                "X-Board-Cell-Preview-Kind": "contact-sheet-5x3",
            },
        )

    @router.post(
        "/{review_item_id}/geometry-revisions",
        response_model=OperationalImageReviewGeometryResponse,
        operation_id="createOperationalImageReviewGeometryRevision",
        summary="Persist immutable v19 symbol-lattice geometry and reopen review",
        responses=ERROR_RESPONSES,
    )
    def create_operational_image_review_geometry_revision(
        review_item_id: UUID,
        payload: OperationalImageReviewGeometryCommand,
        service: Annotated[OperationalImageReviewService, service_parameter],
        reviewer_session: Annotated[ReviewerAccessSession | None, reviewer_parameter],
        reviewer_access_service: Annotated[
            ReviewerAccessService,
            reviewer_service_parameter,
        ],
        game_id: Annotated[UUID, Query(alias="gameId")],
        import_job_id: Annotated[UUID, Query(alias="importJobId")],
    ) -> OperationalImageReviewGeometryResponse:
        reviewer_actor = authorize(
            reviewer_session,
            reviewer_access_service,
            game_id,
            import_job_id,
        )
        item, revision, created = service.correct_geometry(
            review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
            idempotency_key=payload.idempotency_key,
            expected_geometry_revision=payload.expected_geometry_revision,
            expected_resolution_revision=payload.expected_resolution_revision,
            corners=tuple(
                ImageReviewGeometryPoint(x=point.x, y=point.y) for point in payload.corners
            ),
            corrected_by=reviewer_actor or payload.corrected_by,
        )
        return OperationalImageReviewGeometryResponse(
            item=to_operational_item_response(item),
            geometry_revision=to_operational_geometry_revision_response(revision),
            created=created,
        )

    @router.get(
        "/{review_item_id}",
        response_model=OperationalImageReviewItemResponse,
        operation_id="getOperationalImageReviewItem",
        summary="Get one job-local image review item with 15 cells",
        responses=ERROR_RESPONSES,
    )
    def get_operational_image_review_item(
        review_item_id: UUID,
        service: Annotated[OperationalImageReviewService, service_parameter],
        reviewer_session: Annotated[ReviewerAccessSession | None, reviewer_parameter],
        reviewer_access_service: Annotated[
            ReviewerAccessService,
            reviewer_service_parameter,
        ],
        game_id: Annotated[UUID, Query(alias="gameId")],
        import_job_id: Annotated[UUID, Query(alias="importJobId")],
    ) -> OperationalImageReviewItemResponse:
        authorize(reviewer_session, reviewer_access_service, game_id, import_job_id)
        return to_operational_item_response(
            service.get_item(
                review_item_id,
                game_id=game_id,
                import_job_id=import_job_id,
            )
        )

    @router.post(
        "/{review_item_id}/resolution",
        response_model=OperationalImageReviewResolutionResponse,
        operation_id="resolveOperationalImageReviewItem",
        summary="Atomically append and materialize one whole-board decision",
        responses=ERROR_RESPONSES,
    )
    def resolve_operational_image_review_item(
        review_item_id: UUID,
        payload: OperationalImageReviewResolutionCommand,
        service: Annotated[OperationalImageReviewService, service_parameter],
        reviewer_session: Annotated[ReviewerAccessSession | None, reviewer_parameter],
        reviewer_access_service: Annotated[
            ReviewerAccessService,
            reviewer_service_parameter,
        ],
        game_id: Annotated[UUID, Query(alias="gameId")],
        import_job_id: Annotated[UUID, Query(alias="importJobId")],
    ) -> OperationalImageReviewResolutionResponse:
        reviewer_actor = authorize(
            reviewer_session,
            reviewer_access_service,
            game_id,
            import_job_id,
        )
        item, event, created = service.resolve_item(
            review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
            idempotency_key=payload.idempotency_key,
            expected_revision=payload.expected_revision,
            action=payload.action,
            sequence_number=payload.sequence_number,
            geometry_revision=payload.geometry_revision,
            cells=tuple(
                ImageReviewResolutionCell(
                    cell_index=cell.cell_index,
                    crop_sample_id=cell.crop_sample_id,
                    symbol_code=cell.symbol_code,
                )
                for cell in payload.cells
            ),
            rejection_reason=payload.rejection_reason,
            resolved_by=reviewer_actor or payload.resolved_by,
        )
        return OperationalImageReviewResolutionResponse(
            item=to_operational_item_response(item),
            event=to_operational_event_response(event),
            created=created,
        )

    @router.get(
        "/{review_item_id}/resolution-events",
        response_model=list[OperationalImageReviewResolutionEventResponse],
        operation_id="listOperationalImageReviewResolutionEvents",
        summary="List append-only operational review decisions",
        responses=ERROR_RESPONSES,
    )
    def list_operational_image_review_resolution_events(
        review_item_id: UUID,
        service: Annotated[OperationalImageReviewService, service_parameter],
        reviewer_session: Annotated[ReviewerAccessSession | None, reviewer_parameter],
        reviewer_access_service: Annotated[
            ReviewerAccessService,
            reviewer_service_parameter,
        ],
        game_id: Annotated[UUID, Query(alias="gameId")],
        import_job_id: Annotated[UUID, Query(alias="importJobId")],
    ) -> list[OperationalImageReviewResolutionEventResponse]:
        authorize(reviewer_session, reviewer_access_service, game_id, import_job_id)
        return [
            to_operational_event_response(event)
            for event in service.list_resolution_events(
                review_item_id,
                game_id=game_id,
                import_job_id=import_job_id,
            )
        ]

    def image_response(asset: OperationalReviewAsset) -> FileResponse:
        return FileResponse(
            asset.path,
            media_type=asset.media_type,
            headers={"Cache-Control": "private, immutable, max-age=31536000"},
        )

    @router.get(
        "/{review_item_id}/assets/source",
        response_class=FileResponse,
        operation_id="getOperationalImageReviewSourceAsset",
        summary="Read the checksum-bound source image",
        responses=ERROR_RESPONSES,
    )
    def get_operational_image_review_source_asset(
        review_item_id: UUID,
        service: Annotated[OperationalImageReviewService, service_parameter],
        reviewer_session: Annotated[ReviewerAccessSession | None, reviewer_parameter],
        reviewer_access_service: Annotated[
            ReviewerAccessService,
            reviewer_service_parameter,
        ],
        game_id: Annotated[UUID, Query(alias="gameId")],
        import_job_id: Annotated[UUID, Query(alias="importJobId")],
    ) -> FileResponse:
        authorize(reviewer_session, reviewer_access_service, game_id, import_job_id)
        item = service.get_item(
            review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
        )
        return image_response(resolve_operational_source_asset(item, artifact_root))

    @router.get(
        "/{review_item_id}/assets/board",
        response_class=FileResponse,
        operation_id="getOperationalImageReviewBoardAsset",
        summary="Read the checksum-bound rectified board image",
        responses=ERROR_RESPONSES,
    )
    def get_operational_image_review_board_asset(
        review_item_id: UUID,
        service: Annotated[OperationalImageReviewService, service_parameter],
        reviewer_session: Annotated[ReviewerAccessSession | None, reviewer_parameter],
        reviewer_access_service: Annotated[
            ReviewerAccessService,
            reviewer_service_parameter,
        ],
        game_id: Annotated[UUID, Query(alias="gameId")],
        import_job_id: Annotated[UUID, Query(alias="importJobId")],
    ) -> FileResponse:
        authorize(reviewer_session, reviewer_access_service, game_id, import_job_id)
        item = service.get_item(
            review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
        )
        return image_response(resolve_operational_board_asset(item, artifact_root))

    @router.get(
        "/{review_item_id}/assets/cells/{cell_index}",
        response_class=FileResponse,
        operation_id="getOperationalImageReviewCellAsset",
        summary="Read one checksum-bound operational cell crop",
        responses=ERROR_RESPONSES,
    )
    def get_operational_image_review_cell_asset(
        review_item_id: UUID,
        cell_index: int,
        service: Annotated[OperationalImageReviewService, service_parameter],
        reviewer_session: Annotated[ReviewerAccessSession | None, reviewer_parameter],
        reviewer_access_service: Annotated[
            ReviewerAccessService,
            reviewer_service_parameter,
        ],
        game_id: Annotated[UUID, Query(alias="gameId")],
        import_job_id: Annotated[UUID, Query(alias="importJobId")],
    ) -> FileResponse:
        authorize(reviewer_session, reviewer_access_service, game_id, import_job_id)
        item = service.get_item(
            review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
        )
        return image_response(resolve_operational_cell_asset(item, cell_index, artifact_root))

    return router


__all__ = ["create_image_reviews_router"]
