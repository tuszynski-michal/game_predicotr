"""OpenAPI schemas of the D-484 geometry completeness report (TASK-0806).

TASK-0807 adds the persisted gate state (counts, per-image status and operator
exception) and the exception command and response.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from game_predictor_api.domain.image_geometry_completeness import (
    MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE,
    MAX_GEOMETRY_EXCEPTION_REASON_LENGTH,
    GeometryImageState,
    GeometryPositionState,
    SourceImageGeometryStatus,
    encode_geometry_image_cursor,
)
from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.storage.image_geometry_completeness_repository import (
    MAX_IMPORT_SEQUENCE_NUMBERS,
    GeometryCompletenessReport,
    GeometryGateCounts,
    IncompleteGeometryImagePage,
    LowQualityBoardsReport,
)
from game_predictor_api.storage.image_geometry_completeness_state_repository import (
    SourceImageGeometryException,
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
    # Newer import covers the image (TASK-0808); never counted as incomplete.
    superseded: int = Field(ge=0)
    # Image without a live board whose import file failed (TASK-0808).
    import_failed: int = Field(ge=0)


class GeometryCompletenessPositionCountResponse(ApiModel):
    state: GeometryPositionState
    reason_code: str | None
    count: int = Field(ge=0)


class GeometryCompletenessSourceStatusCountResponse(ApiModel):
    image_state: GeometryImageState
    source_status: str = Field(min_length=1)
    count: int = Field(ge=1)


class GeometryGateCountsResponse(ApiModel):
    """Persisted gate state of the images in scope (TASK-0807)."""

    geometry_complete: int = Field(ge=0)
    geometry_incomplete: int = Field(ge=0)
    geometry_exception: int = Field(ge=0)
    # Evaluated, but no live board to cut (superseded, failed import, no geometry).
    outside_gate: int = Field(ge=0)
    # Not evaluated yet (waiting for the state backfill).
    not_evaluated: int = Field(ge=0)
    # Boards not cut into symbol cells and without search evidence.
    withheld_boards: int = Field(ge=0)
    withheld_reason_code: str = Field(min_length=1)


class ImportSequenceOwnershipResponse(ApiModel):
    """Sequence ownership outcome of one import (D-543, TASK-0971).

    ``replaced``: sequences this import took over from a rejected board of
    another image. ``skipped``: sequences another photo owns (a live pending
    board is kept, or a canonical owner wins), so this import's source is only
    an alternative. Counts are exact; the number lists are sorted and capped.
    """

    replaced_count: int = Field(ge=0)
    replaced_sequence_numbers: tuple[int, ...] = Field(max_length=MAX_IMPORT_SEQUENCE_NUMBERS)
    skipped_count: int = Field(ge=0)
    skipped_sequence_numbers: tuple[int, ...] = Field(max_length=MAX_IMPORT_SEQUENCE_NUMBERS)


class ImageGeometryCompletenessResponse(ApiModel):
    game_id: UUID
    import_job_id: UUID | None
    images: GeometryCompletenessImageCountsResponse
    expected_board_count: int = Field(ge=0)
    positions: tuple[GeometryCompletenessPositionCountResponse, ...]
    source_statuses: tuple[GeometryCompletenessSourceStatusCountResponse, ...]
    gate: GeometryGateCountsResponse
    computed_at: datetime
    # Only in the report of one import (``importJobId`` given), else ``null``.
    sequence_ownership: ImportSequenceOwnershipResponse | None = None


class GeometryCompletenessPositionResponse(ApiModel):
    position_index: int = Field(ge=0, le=8)
    sequence_number: int = Field(ge=1)
    state: GeometryPositionState
    reason_code: str | None
    recognized_board_id: UUID | None
    quad: tuple[GeometryCompletenessPointResponse, ...] | None = Field(
        default=None, min_length=4, max_length=4
    )
    # A human approved the board's current geometry (TASK-0961); false
    # without a live board. A `partial` position stays `partial` after a
    # manual qualification (D-449), so this flag tells it was handled.
    human_approved: bool = Field(
        default=False,
        description=(
            "True when a human approved the current geometry of the board at this "
            "position (approvedGeometryRevision == geometryRevision); false without a board."
        ),
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
    # Error code of the failed import file of the image (``None`` when it did not fail).
    import_error_code: str | None
    positions: tuple[GeometryCompletenessPositionResponse, ...] = Field(max_length=9)
    # Persisted gate state (TASK-0807); ``None`` = not evaluated or outside the gate.
    completeness_status: SourceImageGeometryStatus | None
    completeness_evaluated_at: datetime | None
    # ``SOURCE_IMAGE_GEOMETRY_INCOMPLETE`` while the gate withholds the image.
    gate_reason_code: str | None
    exception_reason: str | None
    exception_by: str | None
    exception_at: datetime | None


class IncompleteGeometryImagePageResponse(ApiModel):
    game_id: UUID
    import_job_id: UUID | None
    image_state: GeometryImageState | None
    completeness_status: SourceImageGeometryStatus | None
    # Echo of the `gapsOnly` filter (TASK-0961).
    gaps_only: bool = False
    images: tuple[IncompleteGeometryImageResponse, ...] = Field(
        max_length=MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE
    )
    next_cursor: str | None


class SourceImageGeometryExceptionCommand(ApiModel):
    """Operator exception of one incomplete image (D-484, TASK-0807)."""

    reason: str = Field(min_length=1, max_length=MAX_GEOMETRY_EXCEPTION_REASON_LENGTH)


class SourceImageGeometryExceptionResponse(ApiModel):
    source_image_id: UUID
    completeness_status: SourceImageGeometryStatus | None
    image_state: GeometryImageState
    exception_reason: str | None
    exception_by: str | None
    exception_at: datetime | None
    # Active boards cut and projected by this operation (0 for a withdrawal).
    materialized_review_item_count: int = Field(ge=0)


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


def _gate_counts_response(gate: GeometryGateCounts | None) -> GeometryGateCountsResponse:
    if gate is None:
        gate = GeometryGateCounts(
            geometry_complete=0,
            geometry_incomplete=0,
            geometry_exception=0,
            outside_gate=0,
            not_evaluated=0,
            withheld_boards=0,
        )
    return GeometryGateCountsResponse(
        geometry_complete=gate.geometry_complete,
        geometry_incomplete=gate.geometry_incomplete,
        geometry_exception=gate.geometry_exception,
        outside_gate=gate.outside_gate,
        not_evaluated=gate.not_evaluated,
        withheld_boards=gate.withheld_boards,
        withheld_reason_code=gate.withheld_reason_code,
    )


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
            superseded=report.images.superseded,
            import_failed=report.images.import_failed,
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
        gate=_gate_counts_response(report.gate),
        computed_at=report.computed_at,
        sequence_ownership=(
            None
            if report.sequence_ownership is None
            else ImportSequenceOwnershipResponse(
                replaced_count=report.sequence_ownership.replaced_count,
                replaced_sequence_numbers=report.sequence_ownership.replaced_sequence_numbers,
                skipped_count=report.sequence_ownership.skipped_count,
                skipped_sequence_numbers=report.sequence_ownership.skipped_sequence_numbers,
            )
        ),
    )


def to_incomplete_geometry_image_page_response(
    page: IncompleteGeometryImagePage,
) -> IncompleteGeometryImagePageResponse:
    return IncompleteGeometryImagePageResponse(
        game_id=page.game_id,
        import_job_id=page.import_job_id,
        image_state=page.image_state,
        completeness_status=page.completeness_status,
        gaps_only=page.gaps_only,
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
                import_error_code=image.import_error_code,
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
                        human_approved=position.human_approved,
                    )
                    for position in image.positions
                ),
                completeness_status=image.completeness_status,
                completeness_evaluated_at=image.completeness_evaluated_at,
                gate_reason_code=image.gate_reason_code,
                exception_reason=image.exception_reason,
                exception_by=image.exception_by,
                exception_at=image.exception_at,
            )
            for image in page.images
        ),
        next_cursor=(
            None if page.next_cursor is None else encode_geometry_image_cursor(page.next_cursor)
        ),
    )


def to_source_image_geometry_exception_response(
    value: SourceImageGeometryException,
) -> SourceImageGeometryExceptionResponse:
    return SourceImageGeometryExceptionResponse(
        source_image_id=value.source_image_id,
        completeness_status=value.status,
        image_state=value.image_state,
        exception_reason=value.reason,
        exception_by=value.exception_by,
        exception_at=value.exception_at,
        materialized_review_item_count=value.materialized_review_item_count,
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
    "GeometryGateCountsResponse",
    "GeometryLowQualityBoardResponse",
    "ImageGeometryCompletenessResponse",
    "ImportSequenceOwnershipResponse",
    "ImageGeometryLowQualityBoardsResponse",
    "IncompleteGeometryImagePageResponse",
    "IncompleteGeometryImageResponse",
    "SourceImageGeometryExceptionCommand",
    "SourceImageGeometryExceptionResponse",
    "to_geometry_completeness_response",
    "to_geometry_low_quality_boards_response",
    "to_incomplete_geometry_image_page_response",
    "to_source_image_geometry_exception_response",
]
