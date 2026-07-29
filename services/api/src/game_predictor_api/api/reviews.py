"""HTTP boundary for immutable manual-review batches and items."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from game_predictor_api.application.review_assets import (
    resolve_review_board_asset,
    resolve_review_cell_asset,
    resolve_review_source_asset,
)
from game_predictor_api.application.reviews import ReviewService
from game_predictor_api.domain.reviews import ReviewItemStatus
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.reviews import (
    ReviewBatchImport,
    ReviewBatchImportResponse,
    ReviewBatchResponse,
    ReviewFeedbackExportCreate,
    ReviewFeedbackExportCreateResponse,
    ReviewFeedbackExportResponse,
    ReviewItemPageResponse,
    ReviewItemResponse,
    ReviewResolutionCommand,
    ReviewResolutionCommandResponse,
    ReviewResolutionResponse,
    to_review_batch_response,
    to_review_feedback_export_response,
    to_review_item_page_response,
    to_review_item_response,
    to_review_resolution_response,
)

ReviewServiceDependency = Callable[..., object]
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Review resource not found"},
    409: {"model": ErrorResponse, "description": "Immutable review conflict"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}


def create_reviews_router(
    service_dependency: ReviewServiceDependency,
    review_crop_root: Path,
    review_source_root: Path,
) -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["reviews"])
    service_parameter = Depends(service_dependency)

    @router.get(
        "/review-batches",
        response_model=list[ReviewBatchResponse],
        operation_id="listReviewBatches",
        summary="List immutable manual-review batches",
        responses=ERROR_RESPONSES,
    )
    def list_review_batches(
        service: Annotated[ReviewService, service_parameter],
    ) -> list[ReviewBatchResponse]:
        return [to_review_batch_response(batch) for batch in service.list_review_batches()]

    @router.post(
        "/review-batches",
        response_model=ReviewBatchImportResponse,
        operation_id="importReviewBatch",
        summary="Idempotently import one active-learning selection",
        responses=ERROR_RESPONSES,
    )
    def import_review_batch(
        payload: ReviewBatchImport,
        service: Annotated[ReviewService, service_parameter],
    ) -> ReviewBatchImportResponse:
        report = payload.report.model_dump(mode="json", by_alias=True)
        batch, created = service.import_review_batch(
            game_id=payload.game_id,
            source_report_sha256=payload.source_report_sha256,
            report=report,
        )
        return ReviewBatchImportResponse(
            batch=to_review_batch_response(batch),
            created=created,
        )

    @router.get(
        "/review-batches/{review_batch_id}",
        response_model=ReviewBatchResponse,
        operation_id="getReviewBatch",
        summary="Get immutable manual-review batch metadata",
        responses=ERROR_RESPONSES,
    )
    def get_review_batch(
        review_batch_id: UUID,
        service: Annotated[ReviewService, service_parameter],
    ) -> ReviewBatchResponse:
        return to_review_batch_response(service.get_review_batch(review_batch_id))

    @router.get(
        "/review-batches/{review_batch_id}/items",
        response_model=ReviewItemPageResponse,
        operation_id="listReviewItems",
        summary="List one deterministic page of whole-layout review items",
        responses=ERROR_RESPONSES,
    )
    def list_review_items(
        review_batch_id: UUID,
        service: Annotated[ReviewService, service_parameter],
        item_status: Annotated[ReviewItemStatus | None, Query(alias="status")] = None,
        after_selection_rank: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ) -> ReviewItemPageResponse:
        return to_review_item_page_response(
            review_batch_id,
            service.list_review_items(
                review_batch_id=review_batch_id,
                status=item_status,
                after_selection_rank=after_selection_rank,
                limit=limit,
            ),
        )

    @router.get(
        "/review-items/{review_item_id}",
        response_model=ReviewItemResponse,
        operation_id="getReviewItem",
        summary="Get one immutable whole-layout review item",
        responses=ERROR_RESPONSES,
    )
    def get_review_item(
        review_item_id: UUID,
        service: Annotated[ReviewService, service_parameter],
    ) -> ReviewItemResponse:
        return to_review_item_response(service.get_review_item(review_item_id))

    @router.post(
        "/review-items/{review_item_id}/resolution",
        response_model=ReviewResolutionCommandResponse,
        operation_id="resolveReviewItem",
        summary="Atomically append one idempotent review resolution",
        responses=ERROR_RESPONSES,
    )
    def resolve_review_item(
        review_item_id: UUID,
        payload: ReviewResolutionCommand,
        service: Annotated[ReviewService, service_parameter],
    ) -> ReviewResolutionCommandResponse:
        item, resolution, created = service.resolve_review_item(
            review_item_id=review_item_id,
            idempotency_key=payload.idempotency_key,
            expected_revision=payload.expected_revision,
            action=payload.action,
            geometry_accepted=payload.geometry_accepted,
            labels=tuple(
                label.model_dump(mode="json", by_alias=True) for label in payload.labels
            ),
            rejection_reason=payload.rejection_reason,
            resolved_by=payload.resolved_by,
        )
        return ReviewResolutionCommandResponse(
            item=to_review_item_response(item),
            resolution=to_review_resolution_response(resolution),
            created=created,
        )

    @router.get(
        "/review-items/{review_item_id}/resolutions",
        response_model=list[ReviewResolutionResponse],
        operation_id="listReviewResolutions",
        summary="List immutable resolution history for one review item",
        responses=ERROR_RESPONSES,
    )
    def list_review_resolutions(
        review_item_id: UUID,
        service: Annotated[ReviewService, service_parameter],
    ) -> list[ReviewResolutionResponse]:
        return [
            to_review_resolution_response(resolution)
            for resolution in service.list_review_resolutions(review_item_id)
        ]

    @router.post(
        "/review-batches/{review_batch_id}/feedback-exports",
        response_model=ReviewFeedbackExportCreateResponse,
        operation_id="createReviewFeedbackExport",
        summary="Create an immutable versioned labeled-feedback export",
        responses=ERROR_RESPONSES,
    )
    def create_review_feedback_export(
        review_batch_id: UUID,
        payload: ReviewFeedbackExportCreate,
        service: Annotated[ReviewService, service_parameter],
    ) -> ReviewFeedbackExportCreateResponse:
        feedback_export, created = service.create_feedback_export(
            review_batch_id=review_batch_id,
            created_by=payload.created_by,
        )
        return ReviewFeedbackExportCreateResponse(
            feedback_export=to_review_feedback_export_response(feedback_export),
            created=created,
        )

    @router.get(
        "/review-batches/{review_batch_id}/feedback-exports",
        response_model=list[ReviewFeedbackExportResponse],
        operation_id="listReviewFeedbackExports",
        summary="List immutable labeled-feedback exports for one review batch",
        responses=ERROR_RESPONSES,
    )
    def list_review_feedback_exports(
        review_batch_id: UUID,
        service: Annotated[ReviewService, service_parameter],
    ) -> list[ReviewFeedbackExportResponse]:
        return [
            to_review_feedback_export_response(feedback_export)
            for feedback_export in service.list_feedback_exports(review_batch_id)
        ]

    @router.get(
        "/review-feedback-exports/{feedback_export_id}",
        response_model=ReviewFeedbackExportResponse,
        operation_id="getReviewFeedbackExport",
        summary="Get one immutable labeled-feedback export",
        responses=ERROR_RESPONSES,
    )
    def get_review_feedback_export(
        feedback_export_id: UUID,
        service: Annotated[ReviewService, service_parameter],
    ) -> ReviewFeedbackExportResponse:
        return to_review_feedback_export_response(
            service.get_feedback_export(feedback_export_id)
        )

    def image_response(asset_path: Path, media_type: str) -> FileResponse:
        return FileResponse(
            asset_path,
            media_type=media_type,
            headers={"Cache-Control": "private, immutable, max-age=31536000"},
        )

    @router.get(
        "/review-items/{review_item_id}/assets/source",
        response_class=FileResponse,
        operation_id="getReviewSourceAsset",
        summary="Read the checksum-bound source image for one review item",
        responses=ERROR_RESPONSES,
    )
    def get_review_source_asset(
        review_item_id: UUID,
        service: Annotated[ReviewService, service_parameter],
    ) -> FileResponse:
        asset = resolve_review_source_asset(
            service.get_review_item(review_item_id),
            review_source_root,
        )
        return image_response(asset.path, asset.media_type)

    @router.get(
        "/review-items/{review_item_id}/assets/board",
        response_class=FileResponse,
        operation_id="getReviewBoardAsset",
        summary="Read the canonical whole-board image for one review item",
        responses=ERROR_RESPONSES,
    )
    def get_review_board_asset(
        review_item_id: UUID,
        service: Annotated[ReviewService, service_parameter],
    ) -> FileResponse:
        asset = resolve_review_board_asset(
            service.get_review_item(review_item_id),
            review_crop_root,
        )
        return image_response(asset.path, asset.media_type)

    @router.get(
        "/review-items/{review_item_id}/assets/cells/{cell_index}",
        response_class=FileResponse,
        operation_id="getReviewCellAsset",
        summary="Read one canonical cell crop for a review item",
        responses=ERROR_RESPONSES,
    )
    def get_review_cell_asset(
        review_item_id: UUID,
        cell_index: int,
        service: Annotated[ReviewService, service_parameter],
    ) -> FileResponse:
        asset = resolve_review_cell_asset(
            service.get_review_item(review_item_id),
            cell_index,
            review_crop_root,
        )
        return image_response(asset.path, asset.media_type)

    return router


__all__ = ["create_reviews_router"]
