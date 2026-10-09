"""Scoped admin and reviewer API to list, preview and revert geometry corrections.

TASK-0947 (plan D-538). Domain refusals arrive as ``ImageReviewError``
subclasses carrying the blocking code and a Polish message; the application
wide handler maps them to 404 (unknown correction), 409 (blocking code, stale
CAS, idempotency conflict) and 422 (invalid request).
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from game_predictor_api.api.reviewer_security import (
    create_optional_reviewer_session_dependency,
)
from game_predictor_api.application.geometry_correction_reverts import (
    GeometryCorrectionRevertService,
)
from game_predictor_api.application.reviewer_access import (
    ReviewerAccessService,
    ReviewerAccessSession,
)
from game_predictor_api.domain.geometry_correction_reverts import (
    DEFAULT_GEOMETRY_CORRECTION_LIST_LIMIT,
    MAX_GEOMETRY_CORRECTION_LIST_LIMIT,
)
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.geometry_correction_reverts import (
    GeometryCorrectionListResponse,
    GeometryCorrectionRevertCommand,
    GeometryCorrectionRevertPreviewResponse,
    GeometryCorrectionRevertResponse,
    to_geometry_correction_list_response,
    to_geometry_correction_revert_preview_response,
    to_geometry_correction_revert_response,
)
from game_predictor_api.storage.game_storage_routing import game_storage_scope

GeometryCorrectionRevertServiceDependency = Callable[..., object]
_LOCAL_ADMIN_ACTOR = "local-admin"
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Geometry correction not found"},
    409: {"model": ErrorResponse, "description": "Revert blocked or state conflict"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}


def create_geometry_correction_reverts_router(
    service_dependency: GeometryCorrectionRevertServiceDependency,
    reviewer_access_service_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(
        prefix="/admin/games/{game_id}/image-imports/{import_job_id}/geometry-corrections",
        tags=["geometry-corrections"],
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
    ) -> str:
        if reviewer_session is None:
            return _LOCAL_ADMIN_ACTOR
        reviewer_access_service.authorize_scope(
            reviewer_session,
            game_id=game_id,
            import_job_id=import_job_id,
        )
        return f"reviewer-session:{reviewer_session.id}"

    @router.get(
        "",
        response_model=GeometryCorrectionListResponse,
        operation_id="listGeometryCorrections",
        summary="List the latest manual geometry corrections of an import",
        responses=ERROR_RESPONSES,
    )
    def list_geometry_corrections(
        game_id: UUID,
        import_job_id: UUID,
        service: Annotated[GeometryCorrectionRevertService, service_parameter],
        reviewer_session: Annotated[ReviewerAccessSession | None, reviewer_parameter],
        reviewer_access_service: Annotated[ReviewerAccessService, reviewer_service_parameter],
        limit: Annotated[
            int, Query(ge=1, le=MAX_GEOMETRY_CORRECTION_LIST_LIMIT)
        ] = DEFAULT_GEOMETRY_CORRECTION_LIST_LIMIT,
    ) -> GeometryCorrectionListResponse:
        authorize(reviewer_session, reviewer_access_service, game_id, import_job_id)
        with game_storage_scope(game_id):
            return to_geometry_correction_list_response(
                service.list_recent(game_id=game_id, import_job_id=import_job_id, limit=limit)
            )

    @router.get(
        "/{board_geometry_revision_id}/revert-preview",
        response_model=GeometryCorrectionRevertPreviewResponse,
        operation_id="previewGeometryCorrectionRevert",
        summary="Preview the effects of reverting one geometry correction without writing",
        responses=ERROR_RESPONSES,
    )
    def preview_geometry_correction_revert(
        game_id: UUID,
        import_job_id: UUID,
        board_geometry_revision_id: UUID,
        service: Annotated[GeometryCorrectionRevertService, service_parameter],
        reviewer_session: Annotated[ReviewerAccessSession | None, reviewer_parameter],
        reviewer_access_service: Annotated[ReviewerAccessService, reviewer_service_parameter],
    ) -> GeometryCorrectionRevertPreviewResponse:
        authorize(reviewer_session, reviewer_access_service, game_id, import_job_id)
        with game_storage_scope(game_id):
            return to_geometry_correction_revert_preview_response(
                service.preview(
                    game_id=game_id,
                    import_job_id=import_job_id,
                    board_geometry_revision_id=board_geometry_revision_id,
                )
            )

    @router.post(
        "/{board_geometry_revision_id}/revert",
        response_model=GeometryCorrectionRevertResponse,
        operation_id="revertGeometryCorrection",
        summary="Revert one manual geometry correction atomically",
        responses=ERROR_RESPONSES,
    )
    def revert_geometry_correction(
        game_id: UUID,
        import_job_id: UUID,
        board_geometry_revision_id: UUID,
        payload: GeometryCorrectionRevertCommand,
        service: Annotated[GeometryCorrectionRevertService, service_parameter],
        reviewer_session: Annotated[ReviewerAccessSession | None, reviewer_parameter],
        reviewer_access_service: Annotated[ReviewerAccessService, reviewer_service_parameter],
    ) -> GeometryCorrectionRevertResponse:
        actor = authorize(reviewer_session, reviewer_access_service, game_id, import_job_id)
        with game_storage_scope(game_id):
            return to_geometry_correction_revert_response(
                service.revert(
                    game_id=game_id,
                    import_job_id=import_job_id,
                    board_geometry_revision_id=board_geometry_revision_id,
                    idempotency_key=payload.idempotency_key,
                    expected_geometry_revision=payload.expected_geometry_revision,
                    expected_resolution_revision=payload.expected_resolution_revision,
                    actor=actor,
                    reverted_at=datetime.now(UTC),
                )
            )

    return router


__all__ = ["create_geometry_correction_reverts_router"]
