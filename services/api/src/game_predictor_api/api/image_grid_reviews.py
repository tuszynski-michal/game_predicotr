"""Local Admin HTTP surface for grid validation."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, Response

from game_predictor_api.application.image_geometry_rollout import ImageGeometryRolloutService
from game_predictor_api.application.image_grid_reviews import (
    DEFAULT_IMAGE_GRID_REVIEW_PAGE_SIZE,
    MAX_IMAGE_GRID_REVIEW_PAGE_SIZE,
    ImageGridReviewService,
)
from game_predictor_api.application.image_review_assets import (
    resolve_grid_review_source_asset,
)
from game_predictor_api.application.image_reviews import OperationalImageReviewService
from game_predictor_api.application.virtual_grid_geometry import VirtualGridGeometryService
from game_predictor_api.domain.image_grid_reviews import (
    ImageGridReviewError,
    ImageGridReviewSourceAsset,
    ImageGridReviewView,
)
from game_predictor_api.domain.image_reviews import ImageReviewGeometryPoint
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.image_geometry_rollout import (
    ImageGeometryRolloutStartResponse,
    ImageGeometryRolloutStatusResponse,
    to_image_geometry_rollout_start_response,
    to_image_geometry_rollout_status_response,
)
from game_predictor_api.schemas.image_grid_reviews import (
    ImageGridReviewApprovalCommand,
    ImageGridReviewApprovalResponse,
    ImageGridReviewGeometryCommand,
    ImageGridReviewGeometryPreviewCommand,
    ImageGridReviewGeometryResponse,
    ImageGridReviewPageResponse,
    to_image_grid_review_approval_response,
    to_image_grid_review_geometry_response,
    to_image_grid_review_page_response,
    to_virtual_grid_review_geometry_response,
)

ImageGridReviewServiceDependency = Callable[..., object]
OperationalImageReviewServiceDependency = Callable[..., object]
ImageGeometryRolloutServiceDependency = Callable[..., object]
VirtualGridGeometryServiceDependency = Callable[..., object]
_LOCAL_ADMIN_ACTOR = "local-admin"
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Current grid review resource not found"},
    409: {"model": ErrorResponse, "description": "Grid review cursor or revision conflict"},
    422: {"model": ErrorResponse, "description": "Invalid grid review command"},
}


def create_image_grid_reviews_router(
    service_dependency: ImageGridReviewServiceDependency,
    operational_service_dependency: OperationalImageReviewServiceDependency,
    rollout_service_dependency: ImageGeometryRolloutServiceDependency,
    virtual_geometry_service_dependency: VirtualGridGeometryServiceDependency,
    artifact_root: Path,
) -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["image-grid-reviews"])
    service_parameter = Depends(service_dependency)
    operational_service_parameter = Depends(operational_service_dependency)
    rollout_service_parameter = Depends(rollout_service_dependency)
    virtual_geometry_service_parameter = Depends(virtual_geometry_service_dependency)

    @router.get(
        "/games/{game_id}/image-geometry-rollout",
        response_model=ImageGeometryRolloutStatusResponse,
        operation_id="getImageGeometryRolloutStatus",
        summary="Get bounded virtual-geometry rollout validation status",
        responses=ERROR_RESPONSES,
    )
    def get_image_geometry_rollout_status(
        game_id: UUID,
        service: Annotated[ImageGeometryRolloutService, rollout_service_parameter],
    ) -> ImageGeometryRolloutStatusResponse:
        return to_image_geometry_rollout_status_response(service.status(game_id))

    @router.post(
        "/games/{game_id}/image-geometry-rollout",
        response_model=ImageGeometryRolloutStartResponse,
        status_code=202,
        operation_id="startImageGeometryRolloutBackfill",
        summary="Start or resume bounded virtual-geometry rollout validation",
        responses=ERROR_RESPONSES,
    )
    def start_image_geometry_rollout_backfill(
        game_id: UUID,
        service: Annotated[ImageGeometryRolloutService, rollout_service_parameter],
    ) -> ImageGeometryRolloutStartResponse:
        return to_image_geometry_rollout_start_response(service.start(game_id))

    @router.get(
        "/games/{game_id}/grid-reviews",
        response_model=ImageGridReviewPageResponse,
        operation_id="listImageGridReviews",
        summary="List current game-wide board geometries with bounded keyset pagination",
        responses=ERROR_RESPONSES,
    )
    def list_image_grid_reviews(
        game_id: UUID,
        service: Annotated[ImageGridReviewService, service_parameter],
        view: ImageGridReviewView = ImageGridReviewView.NEEDS_VALIDATION,
        import_job_id: Annotated[UUID | None, Query(alias="importJobId")] = None,
        source_image_id: Annotated[UUID | None, Query(alias="sourceImageId")] = None,
        after_cursor: Annotated[str | None, Query(alias="afterCursor")] = None,
        before_cursor: Annotated[str | None, Query(alias="beforeCursor")] = None,
        limit: Annotated[
            int,
            Query(ge=1, le=MAX_IMAGE_GRID_REVIEW_PAGE_SIZE),
        ] = DEFAULT_IMAGE_GRID_REVIEW_PAGE_SIZE,
    ) -> ImageGridReviewPageResponse:
        return to_image_grid_review_page_response(
            game_id=game_id,
            view=view,
            import_job_id=import_job_id,
            page=service.list(
                game_id=game_id,
                view=view,
                import_job_id=import_job_id,
                source_image_id=source_image_id,
                after_cursor=after_cursor,
                before_cursor=before_cursor,
                limit=limit,
            ),
        )

    @router.get(
        "/image-reviews/{review_item_id}/source-asset",
        response_class=FileResponse,
        operation_id="getImageGridReviewSourceAsset",
        summary="Read one current checksum-bound source image for grid validation",
        responses=ERROR_RESPONSES,
    )
    def get_image_grid_review_source_asset(
        review_item_id: UUID,
        service: Annotated[ImageGridReviewService, service_parameter],
        game_id: Annotated[UUID, Query(alias="gameId")],
        expected_source_checksum_sha256: Annotated[
            str,
            Query(alias="expectedSourceChecksumSha256"),
        ],
    ) -> FileResponse:
        item = service.source_asset(
            game_id=game_id,
            review_item_id=review_item_id,
            expected_source_checksum_sha256=expected_source_checksum_sha256,
        )
        asset = resolve_grid_review_source_asset(item, artifact_root)
        return FileResponse(
            asset.path,
            media_type=asset.media_type,
            headers={"Cache-Control": "private, immutable, max-age=31536000"},
        )

    @router.post(
        "/image-reviews/{review_item_id}/geometry-approval",
        response_model=ImageGridReviewApprovalResponse,
        operation_id="approveImageGridReviewGeometry",
        summary="Approve one exact current board geometry revision",
        responses=ERROR_RESPONSES,
    )
    def approve_image_grid_review_geometry(
        review_item_id: UUID,
        payload: ImageGridReviewApprovalCommand,
        service: Annotated[ImageGridReviewService, service_parameter],
        game_id: Annotated[UUID, Query(alias="gameId")],
    ) -> ImageGridReviewApprovalResponse:
        return to_image_grid_review_approval_response(
            service.approve(
                game_id=game_id,
                review_item_id=review_item_id,
                expected_resolution_revision=payload.expected_resolution_revision,
                expected_geometry_revision=payload.expected_geometry_revision,
                expected_source_checksum_sha256=payload.expected_source_checksum_sha256,
                expected_source_width=payload.expected_source_width,
                expected_source_height=payload.expected_source_height,
                expected_grid_rows=payload.expected_grid_rows,
                expected_grid_columns=payload.expected_grid_columns,
                actor=_LOCAL_ADMIN_ACTOR,
            )
        )

    @router.post(
        "/image-reviews/{review_item_id}/geometry-preview",
        response_class=Response,
        operation_id="previewImageGridReviewGeometry",
        summary="Preview corrected topology-aware board-cell crops without persistence",
        responses={
            **ERROR_RESPONSES,
            200: {"content": {"image/png": {}}, "description": "Board-cell contact sheet"},
        },
    )
    def preview_image_grid_review_geometry(
        review_item_id: UUID,
        payload: ImageGridReviewGeometryPreviewCommand,
        service: Annotated[ImageGridReviewService, service_parameter],
        operational_service: Annotated[
            OperationalImageReviewService,
            operational_service_parameter,
        ],
        virtual_service: Annotated[
            VirtualGridGeometryService,
            virtual_geometry_service_parameter,
        ],
        game_id: Annotated[UUID, Query(alias="gameId")],
        import_job_id: Annotated[UUID, Query(alias="importJobId")],
    ) -> Response:
        source = _require_expected_source(service, game_id, review_item_id, payload)
        corners = tuple(ImageReviewGeometryPoint(x=point.x, y=point.y) for point in payload.corners)
        if source.asset_mode == "virtual_source":
            virtual_preview = virtual_service.preview(
                game_id=game_id,
                import_job_id=import_job_id,
                review_item_id=review_item_id,
                expected_geometry_revision=payload.expected_geometry_revision,
                expected_resolution_revision=payload.expected_resolution_revision,
                expected_source_checksum_sha256=payload.expected_source_checksum_sha256,
                expected_source_width=payload.expected_source_width,
                expected_source_height=payload.expected_source_height,
                expected_grid_rows=payload.expected_grid_rows,
                expected_grid_columns=payload.expected_grid_columns,
                corners=corners,
            )
            return Response(
                content=virtual_preview.contact_sheet_png,
                media_type="image/png",
                headers={
                    "Cache-Control": "no-store",
                    "X-Board-Cell-Count": str(len(virtual_preview.cells)),
                    "X-Board-Grid-Rows": str(source.topology.rows),
                    "X-Board-Grid-Columns": str(source.topology.columns),
                    "X-Board-Cell-Cropper-Version": virtual_preview.cropper_version,
                },
            )
        legacy_preview = operational_service.preview_geometry(
            review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
            expected_geometry_revision=payload.expected_geometry_revision,
            expected_resolution_revision=payload.expected_resolution_revision,
            corners=corners,
        )
        return Response(
            content=legacy_preview.contact_sheet_png,
            media_type="image/png",
            headers={
                "Cache-Control": "no-store",
                "X-Board-Cell-Count": str(len(legacy_preview.cells)),
                "X-Board-Grid-Rows": str(source.topology.rows),
                "X-Board-Grid-Columns": str(source.topology.columns),
                "X-Board-Cell-Cropper-Fingerprint-Sha256": (
                    legacy_preview.cropper_fingerprint_sha256
                ),
                "X-Board-Cell-Cropper-Version": legacy_preview.cropper_version,
            },
        )

    @router.post(
        "/image-reviews/{review_item_id}/geometry-revisions",
        response_model=ImageGridReviewGeometryResponse,
        operation_id="createImageGridReviewGeometryRevision",
        summary="Persist and approve one topology-aware geometry revision",
        responses=ERROR_RESPONSES,
    )
    def create_image_grid_review_geometry_revision(
        review_item_id: UUID,
        payload: ImageGridReviewGeometryCommand,
        service: Annotated[ImageGridReviewService, service_parameter],
        operational_service: Annotated[
            OperationalImageReviewService,
            operational_service_parameter,
        ],
        virtual_service: Annotated[
            VirtualGridGeometryService,
            virtual_geometry_service_parameter,
        ],
        game_id: Annotated[UUID, Query(alias="gameId")],
        import_job_id: Annotated[UUID, Query(alias="importJobId")],
    ) -> ImageGridReviewGeometryResponse:
        source = _require_expected_source(service, game_id, review_item_id, payload)
        corners = tuple(ImageReviewGeometryPoint(x=point.x, y=point.y) for point in payload.corners)
        if source.asset_mode == "virtual_source":
            result = virtual_service.save(
                game_id=game_id,
                import_job_id=import_job_id,
                review_item_id=review_item_id,
                idempotency_key=payload.idempotency_key,
                expected_geometry_revision=payload.expected_geometry_revision,
                expected_resolution_revision=payload.expected_resolution_revision,
                expected_source_checksum_sha256=payload.expected_source_checksum_sha256,
                expected_source_width=payload.expected_source_width,
                expected_source_height=payload.expected_source_height,
                expected_grid_rows=payload.expected_grid_rows,
                expected_grid_columns=payload.expected_grid_columns,
                corners=corners,
                actor=_LOCAL_ADMIN_ACTOR,
                created_at=datetime.now(UTC),
            )
            return to_virtual_grid_review_geometry_response(
                result,
                grid_rows=source.topology.rows,
                grid_columns=source.topology.columns,
            )
        _item, revision, created = operational_service.correct_geometry(
            review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
            idempotency_key=payload.idempotency_key,
            expected_geometry_revision=payload.expected_geometry_revision,
            expected_resolution_revision=payload.expected_resolution_revision,
            corners=corners,
            corrected_by=_LOCAL_ADMIN_ACTOR,
        )
        return to_image_grid_review_geometry_response(
            revision=revision,
            grid_rows=source.topology.rows,
            grid_columns=source.topology.columns,
            created=created,
        )

    return router


def _require_expected_source(
    service: ImageGridReviewService,
    game_id: UUID,
    review_item_id: UUID,
    payload: ImageGridReviewGeometryPreviewCommand,
) -> ImageGridReviewSourceAsset:
    source = service.source_asset(
        game_id=game_id,
        review_item_id=review_item_id,
        expected_source_checksum_sha256=payload.expected_source_checksum_sha256,
    )
    if (
        source.source_width != payload.expected_source_width
        or source.source_height != payload.expected_source_height
    ):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_SOURCE_DRIFT",
            "The source image dimensions changed after the grid review was loaded.",
        )
    if (
        source.topology.rows != payload.expected_grid_rows
        or source.topology.columns != payload.expected_grid_columns
    ):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_TOPOLOGY_CONFLICT",
            "The board topology changed after the grid review was loaded.",
        )
    return source


__all__ = ["create_image_grid_reviews_router"]
