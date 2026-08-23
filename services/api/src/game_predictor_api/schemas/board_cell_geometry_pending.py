"""OpenAPI contract for deferred board-cell geometry work."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, cast
from uuid import UUID

from pydantic import Field

from game_predictor_api.application.board_cell_geometry_pending import (
    BoardCellGeometryCorrectionContext,
    BoardCellGeometryManualResolution,
    BoardCellGeometryPendingPage,
)
from game_predictor_api.domain.board_cell_geometry_pending import (
    BoardCellGeometryJobCounts,
    BoardCellGeometryPendingReason,
    BoardCellGeometryPendingStatus,
    ImageBoardGeometryPending,
)
from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.schemas.image_reviews import OperationalImageReviewGeometryPoint

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class BoardCellGeometryJobCountsResponse(ApiModel):
    total: int = Field(ge=0)
    pending: int = Field(ge=0)
    resolved: int = Field(ge=0)
    superseded: int = Field(ge=0)


class BoardCellGeometryPendingResponse(ApiModel):
    id: UUID
    game_id: UUID
    import_job_id: UUID
    source_image_id: UUID
    recognized_board_id: UUID | None
    review_item_id: UUID | None
    sequence_number: int = Field(ge=1)
    position_index: int = Field(ge=0, le=8)
    source_checksum_sha256: Sha256
    source_relative_path: str
    status: BoardCellGeometryPendingStatus
    reason_code: BoardCellGeometryPendingReason
    processing_manifest_checksum_sha256: Sha256
    processing_manifest_relative_path: str
    pipeline_fingerprint_sha256: Sha256
    expected_geometry_revision: int = Field(ge=0)
    expected_review_resolution_revision: int = Field(ge=0)
    resolved_geometry_revision: int | None = Field(default=None, ge=1)
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    superseded_at: datetime | None


class BoardCellGeometryPendingPageResponse(ApiModel):
    items: tuple[BoardCellGeometryPendingResponse, ...]
    counts: BoardCellGeometryJobCountsResponse
    next_cursor: str | None


class BoardCellGeometryCorrectionContextResponse(ApiModel):
    item: BoardCellGeometryPendingResponse
    source_width: int = Field(gt=0)
    source_height: int = Field(gt=0)
    source_order_index: int = Field(ge=0)
    board_quad: tuple[
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
    ]
    suggested_corners: tuple[
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
    ]


class BoardCellGeometryManualPreviewCommand(ApiModel):
    expected_manifest_checksum_sha256: Sha256
    expected_geometry_revision: int = Field(ge=0)
    expected_resolution_revision: int = Field(ge=0)
    corners: tuple[
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
    ]


class BoardCellGeometryManualResolutionCommand(BoardCellGeometryManualPreviewCommand):
    idempotency_key: UUID
    corrected_by: str = Field(min_length=1, max_length=200)


class BoardCellGeometryManualResolutionResponse(ApiModel):
    item: BoardCellGeometryPendingResponse
    review_item_id: UUID | None
    geometry_revision: int | None = Field(default=None, ge=1)
    created: bool


def to_pending_response(value: ImageBoardGeometryPending) -> BoardCellGeometryPendingResponse:
    return BoardCellGeometryPendingResponse(
        id=value.id,
        game_id=value.game_id,
        import_job_id=value.import_job_id,
        source_image_id=value.source_image_id,
        recognized_board_id=value.recognized_board_id,
        review_item_id=value.review_item_id,
        sequence_number=value.sequence_number,
        position_index=value.position_index,
        source_checksum_sha256=value.source_checksum_sha256,
        source_relative_path=value.source_relative_path,
        status=value.status,
        reason_code=value.reason_code,
        processing_manifest_checksum_sha256=value.processing_manifest_checksum_sha256,
        processing_manifest_relative_path=value.processing_manifest_relative_path,
        pipeline_fingerprint_sha256=value.pipeline_fingerprint_sha256,
        expected_geometry_revision=value.expected_geometry_revision,
        expected_review_resolution_revision=value.expected_review_resolution_revision,
        resolved_geometry_revision=value.resolved_geometry_revision,
        created_at=value.created_at,
        updated_at=value.updated_at,
        resolved_at=value.resolved_at,
        superseded_at=value.superseded_at,
    )


def to_counts_response(value: BoardCellGeometryJobCounts) -> BoardCellGeometryJobCountsResponse:
    return BoardCellGeometryJobCountsResponse(
        total=value.total,
        pending=value.pending,
        resolved=value.resolved,
        superseded=value.superseded,
    )


def to_pending_page_response(
    value: BoardCellGeometryPendingPage,
) -> BoardCellGeometryPendingPageResponse:
    return BoardCellGeometryPendingPageResponse(
        items=tuple(to_pending_response(item) for item in value.items),
        counts=to_counts_response(value.counts),
        next_cursor=value.next_cursor,
    )


def to_correction_context_response(
    value: BoardCellGeometryCorrectionContext,
) -> BoardCellGeometryCorrectionContextResponse:
    quad = _quad(value.board_geometry)
    return BoardCellGeometryCorrectionContextResponse(
        item=to_pending_response(value.pending),
        source_width=value.source_width,
        source_height=value.source_height,
        source_order_index=value.source_order_index,
        board_quad=quad,
        suggested_corners=quad,
    )


def to_manual_resolution_response(
    value: BoardCellGeometryManualResolution,
) -> BoardCellGeometryManualResolutionResponse:
    return BoardCellGeometryManualResolutionResponse(
        item=to_pending_response(value.pending),
        review_item_id=value.review_item_id,
        geometry_revision=value.geometry_revision,
        created=value.created,
    )


def _quad(
    geometry: object,
) -> tuple[
    OperationalImageReviewGeometryPoint,
    OperationalImageReviewGeometryPoint,
    OperationalImageReviewGeometryPoint,
    OperationalImageReviewGeometryPoint,
]:
    if not isinstance(geometry, Mapping):
        raise ValueError("The pending board geometry is invalid.")
    raw = geometry.get("quad") or geometry.get("pageBoardQuad")
    if not isinstance(raw, list | tuple) or len(raw) != 4:
        raise ValueError("The pending board quad is unavailable.")
    points: list[OperationalImageReviewGeometryPoint] = []
    for value in raw:
        if not isinstance(value, Mapping):
            raise ValueError("The pending board quad is invalid.")
        points.append(
            OperationalImageReviewGeometryPoint(
                x=round(float(value["x"])),
                y=round(float(value["y"])),
            )
        )
    return cast(
        tuple[
            OperationalImageReviewGeometryPoint,
            OperationalImageReviewGeometryPoint,
            OperationalImageReviewGeometryPoint,
            OperationalImageReviewGeometryPoint,
        ],
        tuple(points),
    )


__all__ = [
    "BoardCellGeometryJobCountsResponse",
    "BoardCellGeometryCorrectionContextResponse",
    "BoardCellGeometryManualPreviewCommand",
    "BoardCellGeometryManualResolutionCommand",
    "BoardCellGeometryManualResolutionResponse",
    "BoardCellGeometryPendingPageResponse",
    "BoardCellGeometryPendingResponse",
    "to_pending_page_response",
    "to_pending_response",
    "to_correction_context_response",
    "to_manual_resolution_response",
]
