"""OpenAPI contracts for the game-wide grid validation queue."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import Field

from game_predictor_api.domain.image_grid_reviews import (
    ImageGridApprovalResult,
    ImageGridReviewCounts,
    ImageGridReviewListItem,
    ImageGridReviewPage,
    ImageGridReviewState,
    ImageGridReviewView,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewGeometryRevision,
    crop_sample_id,
)
from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.schemas.image_reviews import (
    OperationalImageReviewGeometryPoint,
)

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class ImageGridReviewItemResponse(ApiModel):
    review_item_id: UUID
    game_id: UUID
    import_job_id: UUID
    recognized_board_id: UUID
    source_image_id: UUID
    position_index: int = Field(ge=0, le=8)
    sequence_number: int = Field(ge=1)
    source_checksum_sha256: Sha256
    source_width: int = Field(gt=0)
    source_height: int = Field(gt=0)
    geometry_revision: int = Field(ge=0)
    approved_geometry_revision: int | None = Field(default=None, ge=0)
    resolution_revision: int = Field(ge=0)
    grid_rows: int = Field(gt=0)
    grid_columns: int = Field(gt=0)
    geometry: dict[str, object]
    asset_mode: str
    geometry_engine_name: str | None
    geometry_engine_version: str | None
    board_confidence: float = Field(ge=0, le=1)
    reason_codes: tuple[str, ...]
    state: ImageGridReviewState


class ImageGridReviewCountsResponse(ApiModel):
    needs_validation: int = Field(ge=0)
    needs_correction: int = Field(ge=0)
    approved: int = Field(ge=0)
    total: int = Field(ge=0)


class ImageGridReviewPageResponse(ApiModel):
    game_id: UUID
    view: ImageGridReviewView
    import_job_id: UUID | None
    items: tuple[ImageGridReviewItemResponse, ...]
    counts: ImageGridReviewCountsResponse
    previous_cursor: str | None
    next_cursor: str | None


class ImageGridReviewApprovalCommand(ApiModel):
    expected_resolution_revision: int = Field(ge=0)
    expected_geometry_revision: int = Field(ge=0)
    expected_source_checksum_sha256: Sha256
    expected_source_width: int = Field(gt=0)
    expected_source_height: int = Field(gt=0)
    expected_grid_rows: int = Field(gt=0)
    expected_grid_columns: int = Field(gt=0)


class ImageGridReviewApprovalResponse(ApiModel):
    item: ImageGridReviewItemResponse
    changed: bool


class ImageGridReviewGeometryPreviewCommand(ApiModel):
    expected_geometry_revision: int = Field(ge=0)
    expected_resolution_revision: int = Field(ge=0)
    corners: tuple[
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
    ] = Field(description="Source-image outer corners in row-major winding")
    expected_source_checksum_sha256: Sha256
    expected_source_width: int = Field(gt=0)
    expected_source_height: int = Field(gt=0)
    expected_grid_rows: int = Field(gt=0)
    expected_grid_columns: int = Field(gt=0)


class ImageGridReviewGeometryCommand(ImageGridReviewGeometryPreviewCommand):
    idempotency_key: UUID


class ImageGridReviewGeometryCellResponse(ApiModel):
    cell_index: int = Field(ge=0)
    row_index: int = Field(ge=0)
    column_index: int = Field(ge=0)
    crop_sample_id: Sha256
    crop_checksum_sha256: Sha256


class ImageGridReviewGeometryRevisionResponse(ApiModel):
    id: UUID
    review_item_id: UUID
    recognized_board_id: UUID
    revision: int = Field(ge=1)
    idempotency_key: UUID
    command_sha256: Sha256
    decision_checksum_sha256: Sha256 | None
    corners: tuple[
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
    ]
    board_checksum_sha256: Sha256
    cropper_version: str
    grid_rows: int = Field(gt=0)
    grid_columns: int = Field(gt=0)
    cells: tuple[ImageGridReviewGeometryCellResponse, ...] = Field(min_length=1)
    corrected_by: str
    created_at: datetime


class ImageGridReviewGeometryResponse(ApiModel):
    geometry_revision: ImageGridReviewGeometryRevisionResponse
    created: bool


def to_image_grid_review_item_response(
    item: ImageGridReviewListItem,
) -> ImageGridReviewItemResponse:
    return ImageGridReviewItemResponse(
        review_item_id=item.review_item_id,
        game_id=item.game_id,
        import_job_id=item.import_job_id,
        recognized_board_id=item.recognized_board_id,
        source_image_id=item.source_image_id,
        position_index=item.position_index,
        sequence_number=item.sequence_number,
        source_checksum_sha256=item.source_checksum_sha256,
        source_width=item.source_width,
        source_height=item.source_height,
        geometry_revision=item.geometry_revision,
        approved_geometry_revision=item.approved_geometry_revision,
        resolution_revision=item.resolution_revision,
        grid_rows=item.topology.rows,
        grid_columns=item.topology.columns,
        geometry=dict(item.geometry),
        asset_mode=item.asset_mode,
        geometry_engine_name=item.geometry_engine_name,
        geometry_engine_version=item.geometry_engine_version,
        board_confidence=item.board_confidence,
        reason_codes=item.reason_codes,
        state=item.state,
    )


def to_image_grid_review_counts_response(
    counts: ImageGridReviewCounts,
) -> ImageGridReviewCountsResponse:
    return ImageGridReviewCountsResponse(
        needs_validation=counts.needs_validation,
        needs_correction=counts.needs_correction,
        approved=counts.approved,
        total=counts.total,
    )


def to_image_grid_review_page_response(
    *,
    game_id: UUID,
    view: ImageGridReviewView,
    import_job_id: UUID | None,
    page: ImageGridReviewPage,
) -> ImageGridReviewPageResponse:
    return ImageGridReviewPageResponse(
        game_id=game_id,
        view=view,
        import_job_id=import_job_id,
        items=tuple(to_image_grid_review_item_response(item) for item in page.items),
        counts=to_image_grid_review_counts_response(page.counts),
        previous_cursor=page.previous_cursor,
        next_cursor=page.next_cursor,
    )


def to_image_grid_review_approval_response(
    result: ImageGridApprovalResult,
) -> ImageGridReviewApprovalResponse:
    return ImageGridReviewApprovalResponse(
        item=to_image_grid_review_item_response(result.item),
        changed=result.changed,
    )


def to_image_grid_review_geometry_response(
    *,
    revision: ImageReviewGeometryRevision,
    grid_rows: int,
    grid_columns: int,
    created: bool,
) -> ImageGridReviewGeometryResponse:
    return ImageGridReviewGeometryResponse(
        geometry_revision=ImageGridReviewGeometryRevisionResponse(
            id=revision.id,
            review_item_id=revision.review_item_id,
            recognized_board_id=revision.recognized_board_id,
            revision=revision.revision,
            idempotency_key=revision.idempotency_key,
            command_sha256=revision.command_sha256,
            decision_checksum_sha256=revision.decision_checksum_sha256,
            corners=(
                OperationalImageReviewGeometryPoint(
                    x=revision.corners[0].x, y=revision.corners[0].y
                ),
                OperationalImageReviewGeometryPoint(
                    x=revision.corners[1].x, y=revision.corners[1].y
                ),
                OperationalImageReviewGeometryPoint(
                    x=revision.corners[2].x, y=revision.corners[2].y
                ),
                OperationalImageReviewGeometryPoint(
                    x=revision.corners[3].x, y=revision.corners[3].y
                ),
            ),
            board_checksum_sha256=revision.board_checksum_sha256,
            cropper_version=revision.cropper_version,
            grid_rows=grid_rows,
            grid_columns=grid_columns,
            cells=tuple(
                ImageGridReviewGeometryCellResponse(
                    cell_index=cell.row_index * grid_columns + cell.column_index,
                    row_index=cell.row_index,
                    column_index=cell.column_index,
                    crop_sample_id=crop_sample_id(
                        recognized_board_id=revision.recognized_board_id,
                        row_index=cell.row_index,
                        column_index=cell.column_index,
                        cropper_version=revision.cropper_version,
                        crop_relative_path=cell.crop_relative_path,
                        crop_checksum_sha256=cell.crop_checksum_sha256,
                    ),
                    crop_checksum_sha256=cell.crop_checksum_sha256,
                )
                for cell in revision.cells
            ),
            corrected_by=revision.corrected_by,
            created_at=revision.created_at,
        ),
        created=created,
    )


__all__ = [
    "ImageGridReviewApprovalCommand",
    "ImageGridReviewApprovalResponse",
    "ImageGridReviewCountsResponse",
    "ImageGridReviewGeometryCommand",
    "ImageGridReviewGeometryResponse",
    "ImageGridReviewGeometryPreviewCommand",
    "ImageGridReviewItemResponse",
    "ImageGridReviewPageResponse",
    "to_image_grid_review_approval_response",
    "to_image_grid_review_geometry_response",
    "to_image_grid_review_page_response",
]
