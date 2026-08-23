"""Scoped admin and reviewer API for deferred board-cell geometry work."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, Response

from game_predictor_api.api.reviewer_security import (
    create_optional_reviewer_session_dependency,
)
from game_predictor_api.application.board_cell_geometry_pending import (
    BoardCellGeometryPendingService,
)
from game_predictor_api.application.image_review_assets import (
    resolve_pending_board_cell_source_asset,
)
from game_predictor_api.application.reviewer_access import (
    ReviewerAccessService,
    ReviewerAccessSession,
)
from game_predictor_api.domain.board_cell_geometry_pending import (
    BoardCellGeometryPendingStatus,
)
from game_predictor_api.domain.image_reviews import ImageReviewGeometryPoint
from game_predictor_api.schemas.board_cell_geometry_pending import (
    BoardCellGeometryCorrectionContextResponse,
    BoardCellGeometryManualPreviewCommand,
    BoardCellGeometryManualResolutionCommand,
    BoardCellGeometryManualResolutionResponse,
    BoardCellGeometryPendingPageResponse,
    BoardCellGeometryPendingResponse,
    to_correction_context_response,
    to_manual_resolution_response,
    to_pending_page_response,
    to_pending_response,
)
from game_predictor_api.schemas.catalog import ErrorResponse

BoardCellGeometryPendingServiceDependency = Callable[..., object]
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Deferred geometry item not found"},
    409: {"model": ErrorResponse, "description": "Deferred geometry state conflict"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}


def create_board_cell_geometry_pending_router(
    service_dependency: BoardCellGeometryPendingServiceDependency,
    reviewer_access_service_dependency: Callable[..., object],
    artifact_root: Path,
) -> APIRouter:
    router = APIRouter(
        prefix="/admin/games/{game_id}/image-imports/{import_job_id}/board-cell-geometry-pending",
        tags=["board-cell-geometry"],
    )
    service_parameter = Depends(service_dependency)
    reviewer_parameter = Depends(
        create_optional_reviewer_session_dependency(reviewer_access_service_dependency)
    )
    reviewer_service_parameter = Depends(reviewer_access_service_dependency)

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

    @router.get(
        "",
        response_model=BoardCellGeometryPendingPageResponse,
        operation_id="listPendingBoardCellGeometry",
        summary="List durable board-cell geometry fallback items",
        responses=ERROR_RESPONSES,
    )
    def list_pending_board_cell_geometry(
        game_id: UUID,
        import_job_id: UUID,
        service: Annotated[BoardCellGeometryPendingService, service_parameter],
        reviewer_session: Annotated[ReviewerAccessSession | None, reviewer_parameter],
        reviewer_access_service: Annotated[
            ReviewerAccessService,
            reviewer_service_parameter,
        ],
        item_status: Annotated[
            BoardCellGeometryPendingStatus | None,
            Query(alias="status"),
        ] = None,
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
    ) -> BoardCellGeometryPendingPageResponse:
        authorize(reviewer_session, reviewer_access_service, game_id, import_job_id)
        return to_pending_page_response(
            service.list(
                game_id=game_id,
                import_job_id=import_job_id,
                status=item_status,
                cursor=cursor,
                limit=limit,
            )
        )

    @router.get(
        "/{pending_id}",
        response_model=BoardCellGeometryPendingResponse,
        operation_id="getPendingBoardCellGeometry",
        summary="Get one durable board-cell geometry fallback item",
        responses=ERROR_RESPONSES,
    )
    def get_pending_board_cell_geometry(
        game_id: UUID,
        import_job_id: UUID,
        pending_id: UUID,
        service: Annotated[BoardCellGeometryPendingService, service_parameter],
        reviewer_session: Annotated[ReviewerAccessSession | None, reviewer_parameter],
        reviewer_access_service: Annotated[
            ReviewerAccessService,
            reviewer_service_parameter,
        ],
    ) -> BoardCellGeometryPendingResponse:
        authorize(reviewer_session, reviewer_access_service, game_id, import_job_id)
        return to_pending_response(
            service.get(
                pending_id,
                game_id=game_id,
                import_job_id=import_job_id,
            )
        )

    @router.get(
        "/{pending_id}/correction-context",
        response_model=BoardCellGeometryCorrectionContextResponse,
        operation_id="getPendingBoardCellGeometryCorrectionContext",
        summary="Get checksum-bound manual correction context",
        responses=ERROR_RESPONSES,
    )
    def get_pending_board_cell_geometry_correction_context(
        game_id: UUID,
        import_job_id: UUID,
        pending_id: UUID,
        service: Annotated[BoardCellGeometryPendingService, service_parameter],
        reviewer_session: Annotated[ReviewerAccessSession | None, reviewer_parameter],
        reviewer_access_service: Annotated[
            ReviewerAccessService,
            reviewer_service_parameter,
        ],
    ) -> BoardCellGeometryCorrectionContextResponse:
        authorize(reviewer_session, reviewer_access_service, game_id, import_job_id)
        return to_correction_context_response(
            service.correction_context(
                pending_id,
                game_id=game_id,
                import_job_id=import_job_id,
            )
        )

    @router.get(
        "/{pending_id}/source",
        response_class=FileResponse,
        operation_id="getPendingBoardCellGeometrySource",
        summary="Read checksum-bound source for manual correction",
        responses=ERROR_RESPONSES,
    )
    def get_pending_board_cell_geometry_source(
        game_id: UUID,
        import_job_id: UUID,
        pending_id: UUID,
        service: Annotated[BoardCellGeometryPendingService, service_parameter],
        reviewer_session: Annotated[ReviewerAccessSession | None, reviewer_parameter],
        reviewer_access_service: Annotated[
            ReviewerAccessService,
            reviewer_service_parameter,
        ],
    ) -> FileResponse:
        authorize(reviewer_session, reviewer_access_service, game_id, import_job_id)
        item = service.get(pending_id, game_id=game_id, import_job_id=import_job_id)
        asset = resolve_pending_board_cell_source_asset(item, artifact_root)
        return FileResponse(
            asset.path,
            media_type=asset.media_type,
            headers={
                "Cache-Control": "private, max-age=31536000, immutable",
                "ETag": f'"{item.source_checksum_sha256}"',
            },
        )

    @router.post(
        "/{pending_id}/geometry-preview",
        response_class=Response,
        operation_id="previewPendingBoardCellGeometryCorrection",
        summary="Preview 15 manual source-direct crops for a deferred board",
        responses={
            **ERROR_RESPONSES,
            200: {
                "content": {"image/png": {}},
                "description": "Five by three contact sheet of manual v19 crops",
            },
        },
    )
    def preview_pending_board_cell_geometry_correction(
        game_id: UUID,
        import_job_id: UUID,
        pending_id: UUID,
        payload: BoardCellGeometryManualPreviewCommand,
        service: Annotated[BoardCellGeometryPendingService, service_parameter],
        reviewer_session: Annotated[ReviewerAccessSession | None, reviewer_parameter],
        reviewer_access_service: Annotated[
            ReviewerAccessService,
            reviewer_service_parameter,
        ],
    ) -> Response:
        authorize(reviewer_session, reviewer_access_service, game_id, import_job_id)
        preview = service.preview_manual_resolution(
            pending_id,
            game_id=game_id,
            import_job_id=import_job_id,
            expected_manifest_checksum_sha256=payload.expected_manifest_checksum_sha256,
            expected_geometry_revision=payload.expected_geometry_revision,
            expected_resolution_revision=payload.expected_resolution_revision,
            corners=tuple(ImageReviewGeometryPoint(x=p.x, y=p.y) for p in payload.corners),
        )
        return Response(
            content=preview.contact_sheet_png,
            media_type="image/png",
            headers={
                "Cache-Control": "no-store",
                "X-Board-Cell-Count": str(len(preview.cells)),
                "X-Board-Cell-Cropper-Version": preview.cropper_version,
            },
        )

    @router.post(
        "/{pending_id}/manual-resolution",
        response_model=BoardCellGeometryManualResolutionResponse,
        operation_id="resolvePendingBoardCellGeometryManually",
        summary="Create one ordinary review item from manual deferred geometry",
        responses=ERROR_RESPONSES,
    )
    def resolve_pending_board_cell_geometry_manually(
        game_id: UUID,
        import_job_id: UUID,
        pending_id: UUID,
        payload: BoardCellGeometryManualResolutionCommand,
        service: Annotated[BoardCellGeometryPendingService, service_parameter],
        reviewer_session: Annotated[ReviewerAccessSession | None, reviewer_parameter],
        reviewer_access_service: Annotated[
            ReviewerAccessService,
            reviewer_service_parameter,
        ],
    ) -> BoardCellGeometryManualResolutionResponse:
        reviewer_actor = authorize(
            reviewer_session,
            reviewer_access_service,
            game_id,
            import_job_id,
        )
        return to_manual_resolution_response(
            service.resolve_manual(
                pending_id,
                game_id=game_id,
                import_job_id=import_job_id,
                expected_manifest_checksum_sha256=payload.expected_manifest_checksum_sha256,
                idempotency_key=payload.idempotency_key,
                expected_geometry_revision=payload.expected_geometry_revision,
                expected_resolution_revision=payload.expected_resolution_revision,
                corners=tuple(
                    ImageReviewGeometryPoint(x=point.x, y=point.y) for point in payload.corners
                ),
                corrected_by=reviewer_actor or payload.corrected_by,
                resolved_at=datetime.now(UTC),
            )
        )

    return router


__all__ = ["create_board_cell_geometry_pending_router"]
