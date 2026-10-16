"""Explicit capture/assessment commands and canonical approval, with scoped human actors."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from game_predictor_api.api.reviewer_security import create_optional_reviewer_session_dependency
from game_predictor_api.application.grid_quality_measurements import GridQualityMeasurementService
from game_predictor_api.application.image_review_assets import _resolve
from game_predictor_api.application.image_reviews import OperationalImageReviewService
from game_predictor_api.application.reviewer_access import (
    ReviewerAccessService,
    ReviewerAccessSession,
)
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.grid_quality_measurements import (
    GeometryApprovalCommand,
    GeometryApprovalResponse,
    QualityAssessCommand,
    QualityCaptureCommand,
    QualityCommandResponse,
    QualityMeasurementPage,
    QualityMeasurementResponse,
)


def create_grid_quality_measurements_router(
    dependency: Callable[..., object],
    reviewer_dependency: Callable[..., object],
    artifact_root: Path,
) -> APIRouter:
    router = APIRouter(
        prefix="/admin",
        tags=["grid-quality-measurements"],
        responses={
            403: {"model": ErrorResponse, "description": "Validated human scope required"},
            404: {
                "model": ErrorResponse,
                "description": "Frozen measurement or source unavailable",
            },
            409: {
                "model": ErrorResponse,
                "description": "Measurement command, identity or revision conflict",
            },
        },
    )
    parameter = Depends(dependency)
    reviewer_parameter = Depends(create_optional_reviewer_session_dependency(reviewer_dependency))
    access_parameter = Depends(reviewer_dependency)

    def actor(request: Request) -> str:
        if getattr(request.state, "local_admin_actor", None) != "local-owner":
            raise HTTPException(403, "A validated local human actor is required.")
        return "local-owner"

    def available(service: OperationalImageReviewService) -> GridQualityMeasurementService:
        if service.grid_quality_measurements is None:
            raise HTTPException(503, "Grid quality measurements unavailable.")
        return service.grid_quality_measurements

    @router.get(
        "/games/{game_id}/grid-quality-measurements",
        operation_id="listGridQualityMeasurements",
        response_model=QualityMeasurementPage,
    )
    def list_measurements(
        game_id: UUID,
        service: Annotated[OperationalImageReviewService, parameter],
        cursor: UUID | None = None,
        limit: int = Query(default=20, ge=1, le=50),
    ) -> QualityMeasurementPage:
        return QualityMeasurementPage.model_validate(
            available(service).repository.list_measurements(game_id, cursor, limit)
        )

    @router.get(
        "/games/{game_id}/grid-quality-measurements/{measurement_id}",
        operation_id="getGridQualityMeasurement",
        response_model=QualityMeasurementResponse,
    )
    def get_measurement(
        game_id: UUID,
        measurement_id: UUID,
        service: Annotated[OperationalImageReviewService, parameter],
    ) -> QualityMeasurementResponse:
        return QualityMeasurementResponse.model_validate(
            available(service).repository.get(game_id, measurement_id)
        )

    @router.post(
        "/games/{game_id}/grid-quality-measurements/capture",
        operation_id="captureGridQualityMeasurement",
        response_model=QualityCommandResponse,
    )
    def capture(
        request: Request,
        game_id: UUID,
        command: QualityCaptureCommand,
        service: Annotated[OperationalImageReviewService, parameter],
    ) -> QualityCommandResponse:
        return QualityCommandResponse.model_validate(
            available(service).capture(
                game_id, command.model_dump(mode="json", by_alias=True), actor(request)
            )
        )

    @router.post(
        "/games/{game_id}/grid-quality-measurements/{measurement_id}/assess",
        operation_id="assessGridQualityMeasurement",
        response_model=QualityCommandResponse,
    )
    def assess(
        request: Request,
        game_id: UUID,
        measurement_id: UUID,
        command: QualityAssessCommand,
        service: Annotated[OperationalImageReviewService, parameter],
    ) -> QualityCommandResponse:
        return QualityCommandResponse.model_validate(
            available(service).assess(
                game_id,
                measurement_id,
                command.model_dump(mode="json", by_alias=True),
                actor(request),
            )
        )

    @router.get(
        "/games/{game_id}/grid-quality-measurements/{measurement_id}/sources/{source_id}/asset",
        operation_id="getGridQualityMeasurementSource",
        response_class=FileResponse,
    )
    def source_asset(
        game_id: UUID,
        measurement_id: UUID,
        source_id: UUID,
        service: Annotated[OperationalImageReviewService, parameter],
    ) -> FileResponse:
        view = available(service).repository.get(game_id, measurement_id)
        member = next((row for row in view["members"] if row["sourceId"] == str(source_id)), None)
        if member is None or not member["available"] or not view["manifestAvailable"]:
            raise HTTPException(404, "The frozen source image is unavailable.")
        asset = _resolve(
            artifact_root,
            member["source"]["relative_path"],
            member["source"]["checksum_sha256"],
            asset_kind="grid-quality-source",
        )
        return FileResponse(
            asset.path,
            media_type=asset.media_type,
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @router.post(
        "/image-reviews/{review_item_id}/geometry-approvals",
        operation_id="approveOperationalGeometry",
        response_model=GeometryApprovalResponse,
    )
    def approve(
        request: Request,
        review_item_id: UUID,
        command: GeometryApprovalCommand,
        service: Annotated[OperationalImageReviewService, parameter],
        reviewer: Annotated[ReviewerAccessSession | None, reviewer_parameter],
        access: Annotated[ReviewerAccessService, access_parameter],
        game_id: Annotated[UUID, Query(alias="gameId")],
        import_job_id: Annotated[UUID, Query(alias="importJobId")],
    ) -> GeometryApprovalResponse:
        if reviewer is not None:
            access.authorize_scope(reviewer, game_id=game_id, import_job_id=import_job_id)
            human = f"reviewer-session:{reviewer.id}"
        else:
            human = actor(request)
        if service.grid_geometry_approvals is None:
            raise HTTPException(503, "Canonical geometry approvals unavailable.")
        return GeometryApprovalResponse.model_validate(
            service.grid_geometry_approvals.approve(
                game_id,
                import_job_id,
                review_item_id,
                command.model_dump(mode="json", by_alias=True),
                human,
            )
        )

    return router
