"""OpenAPI schemas of the D-484 geometry completeness report (TASK-0806)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from game_predictor_api.domain.image_geometry_completeness import (
    MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE,
    GeometryImageState,
    GeometryPositionState,
    encode_geometry_image_cursor,
)
from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.storage.image_geometry_completeness_repository import (
    GeometryCompletenessReport,
    IncompleteGeometryImagePage,
    LowQualityBoardsReport,
)


class GeometryCompletenessPointResponse(ApiModel):
    """A point in ``exif-normalized-rgb-pixels-v1`` source pixels."""

    x: float
    y: float


class GeometryCompletenessImageCountsResponse(ApiModel):
    total: int = Field(ge=0)
    complete: int = Field(ge=0)
    incomplete: int = Field(ge=0)
    incomplete_missing: int = Field(ge=0)
    incomplete_partial: int = Field(ge=0)
    incomplete_uncertain: int = Field(ge=0)
    no_source_geometry: int = Field(ge=0)


class GeometryCompletenessPositionCountResponse(ApiModel):
    state: GeometryPositionState
    reason_code: str | None
    count: int = Field(ge=0)


class GeometryCompletenessSourceStatusCountResponse(ApiModel):
    image_state: GeometryImageState
    source_status: str = Field(min_length=1)
    count: int = Field(ge=1)


class ImageGeometryCompletenessResponse(ApiModel):
    game_id: UUID
    import_job_id: UUID | None
    images: GeometryCompletenessImageCountsResponse
    expected_board_count: int = Field(ge=0)
    positions: tuple[GeometryCompletenessPositionCountResponse, ...]
    source_statuses: tuple[GeometryCompletenessSourceStatusCountResponse, ...]
    computed_at: datetime


class GeometryCompletenessPositionResponse(ApiModel):
    position_index: int = Field(ge=0, le=8)
    sequence_number: int = Field(ge=1)
    state: GeometryPositionState
    reason_code: str | None
    recognized_board_id: UUID | None
    quad: tuple[GeometryCompletenessPointResponse, ...] | None = Field(
        default=None, min_length=4, max_length=4
    )


class IncompleteGeometryImageResponse(ApiModel):
    source_image_id: UUID
    import_job_id: UUID
    relative_path: str = Field(min_length=1)
    source_status: str = Field(min_length=1)
    image_state: GeometryImageState
    source_revision: int | None = Field(ge=0)
    sequence_range_start: int | None = Field(ge=1)
    sequence_range_end: int | None = Field(ge=1)
    expected_board_count: int | None = Field(ge=1, le=9)
    oriented_width: int | None = Field(ge=1)
    oriented_height: int | None = Field(ge=1)
    # Review item that serves the whole-image preview through the existing
    # source-asset endpoint; ``None`` when the image has no recognized board.
    preview_review_item_id: UUID | None
    positions: tuple[GeometryCompletenessPositionResponse, ...] = Field(max_length=9)


class IncompleteGeometryImagePageResponse(ApiModel):
    game_id: UUID
    import_job_id: UUID | None
    image_state: GeometryImageState | None
    images: tuple[IncompleteGeometryImageResponse, ...] = Field(
        max_length=MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE
    )
    next_cursor: str | None


class GeometryLowQualityBoardResponse(ApiModel):
    recognized_board_id: UUID
    source_image_id: UUID
    import_job_id: UUID
    relative_path: str = Field(min_length=1)
    position_index: int = Field(ge=0, le=8)
    sequence_number: int | None = Field(ge=1)
    low_cell_count: int = Field(ge=1, le=15)
    min_confidence: float = Field(ge=0, le=1)


class ImageGeometryLowQualityBoardsResponse(ApiModel):
    game_id: UUID
    import_job_id: UUID | None
    max_confidence: float = Field(ge=0, le=1)
    min_cells: int = Field(ge=1, le=15)
    total_boards: int = Field(ge=0)
    boards: tuple[GeometryLowQualityBoardResponse, ...] = Field(
        max_length=MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE
    )
    computed_at: datetime


def to_geometry_completeness_response(
    report: GeometryCompletenessReport,
) -> ImageGeometryCompletenessResponse:
    return ImageGeometryCompletenessResponse(
        game_id=report.game_id,
        import_job_id=report.import_job_id,
        images=GeometryCompletenessImageCountsResponse(
            total=report.images.total,
            complete=report.images.complete,
            incomplete=report.images.incomplete,
            incomplete_missing=report.images.incomplete_missing,
            incomplete_partial=report.images.incomplete_partial,
            incomplete_uncertain=report.images.incomplete_uncertain,
            no_source_geometry=report.images.no_source_geometry,
        ),
        expected_board_count=report.expected_board_count,
        positions=tuple(
            GeometryCompletenessPositionCountResponse(
                state=position.state,
                reason_code=position.reason_code,
                count=position.count,
            )
            for position in report.positions
        ),
        source_statuses=tuple(
            GeometryCompletenessSourceStatusCountResponse(
                image_state=item.image_state,
                source_status=item.source_status,
                count=item.count,
            )
            for item in report.source_statuses
        ),
        computed_at=report.computed_at,
    )


def to_incomplete_geometry_image_page_response(
    page: IncompleteGeometryImagePage,
) -> IncompleteGeometryImagePageResponse:
    return IncompleteGeometryImagePageResponse(
        game_id=page.game_id,
        import_job_id=page.import_job_id,
        image_state=page.image_state,
        images=tuple(
            IncompleteGeometryImageResponse(
                source_image_id=image.source_image_id,
                import_job_id=image.import_job_id,
                relative_path=image.relative_path,
                source_status=image.source_status,
                image_state=image.image_state,
                source_revision=image.source_revision,
                sequence_range_start=image.sequence_range_start,
                sequence_range_end=image.sequence_range_end,
                expected_board_count=image.expected_board_count,
                oriented_width=image.oriented_width,
                oriented_height=image.oriented_height,
                preview_review_item_id=image.preview_review_item_id,
                positions=tuple(
                    GeometryCompletenessPositionResponse(
                        position_index=position.position_index,
                        sequence_number=position.sequence_number,
                        state=position.state,
                        reason_code=position.reason_code,
                        recognized_board_id=position.recognized_board_id,
                        quad=(
                            None
                            if position.quad is None
                            else tuple(
                                GeometryCompletenessPointResponse(x=x, y=y)
                                for x, y in position.quad
                            )
                        ),
                    )
                    for position in image.positions
                ),
            )
            for image in page.images
        ),
        next_cursor=(
            None if page.next_cursor is None else encode_geometry_image_cursor(page.next_cursor)
        ),
    )


def to_geometry_low_quality_boards_response(
    report: LowQualityBoardsReport,
) -> ImageGeometryLowQualityBoardsResponse:
    return ImageGeometryLowQualityBoardsResponse(
        game_id=report.game_id,
        import_job_id=report.import_job_id,
        max_confidence=report.max_confidence,
        min_cells=report.min_cells,
        total_boards=report.total_boards,
        boards=tuple(
            GeometryLowQualityBoardResponse(
                recognized_board_id=board.recognized_board_id,
                source_image_id=board.source_image_id,
                import_job_id=board.import_job_id,
                relative_path=board.relative_path,
                position_index=board.position_index,
                sequence_number=board.sequence_number,
                low_cell_count=board.low_cell_count,
                min_confidence=board.min_confidence,
            )
            for board in report.boards
        ),
        computed_at=report.computed_at,
    )


__all__ = [
    "GeometryCompletenessImageCountsResponse",
    "GeometryCompletenessPointResponse",
    "GeometryCompletenessPositionCountResponse",
    "GeometryCompletenessPositionResponse",
    "GeometryCompletenessSourceStatusCountResponse",
    "GeometryLowQualityBoardResponse",
    "ImageGeometryCompletenessResponse",
    "ImageGeometryLowQualityBoardsResponse",
    "IncompleteGeometryImagePageResponse",
    "IncompleteGeometryImageResponse",
    "to_geometry_completeness_response",
    "to_geometry_low_quality_boards_response",
    "to_incomplete_geometry_image_page_response",
]
