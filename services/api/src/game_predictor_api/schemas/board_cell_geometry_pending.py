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
    BoardCellGeometryRejection,
)
from game_predictor_api.domain.board_cell_geometry_pending import (
    BoardCellGeometryJobCounts,
    BoardCellGeometryPendingReason,
    BoardCellGeometryPendingStatus,
    BoardRejectionReason,
    ImageBoardGeometryPending,
)
from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.schemas.geometry_qualification import (
    GeometryQualificationPayload,
    GridCorrectionCellSymbolPayload,
    ManualSourceGeometryPoint,
)
from game_predictor_api.schemas.source_lattice_geometry import (
    SourceLatticeNodesPayload,
    lattice_nodes_payload,
)

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class BoardCellGeometryJobCountsResponse(ApiModel):
    total: int = Field(ge=0)
    pending: int = Field(ge=0)
    resolved: int = Field(ge=0)
    superseded: int = Field(ge=0)
    rejected: int = Field(default=0, ge=0)


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
    rejection_reason: BoardRejectionReason | None = None
    rejection_note: str | None = None
    rejected_at: datetime | None = None
    rejected_by: str | None = None


class BoardCellGeometryPendingPageResponse(ApiModel):
    items: tuple[BoardCellGeometryPendingResponse, ...]
    counts: BoardCellGeometryJobCountsResponse
    next_cursor: str | None


class BoardCellGeometryCorrectionContextResponse(ApiModel):
    lattice_nodes: SourceLatticeNodesPayload | None = None
    expected_proposal_checksum_sha256: Sha256 | None = None
    item: BoardCellGeometryPendingResponse
    source_width: int = Field(gt=0)
    source_height: int = Field(gt=0)
    source_order_index: int = Field(ge=0)
    board_quad: tuple[
        ManualSourceGeometryPoint,
        ManualSourceGeometryPoint,
        ManualSourceGeometryPoint,
        ManualSourceGeometryPoint,
    ]
    suggested_corners: tuple[
        ManualSourceGeometryPoint,
        ManualSourceGeometryPoint,
        ManualSourceGeometryPoint,
        ManualSourceGeometryPoint,
    ]


class BoardCellGeometryManualPreviewCommand(ApiModel):
    lattice_nodes: SourceLatticeNodesPayload | None = None
    expected_proposal_checksum_sha256: Sha256 | None = None
    expected_manifest_checksum_sha256: Sha256
    expected_geometry_revision: int = Field(ge=0)
    expected_resolution_revision: int = Field(ge=0)
    corners: tuple[
        ManualSourceGeometryPoint,
        ManualSourceGeometryPoint,
        ManualSourceGeometryPoint,
        ManualSourceGeometryPoint,
    ]
    geometry_qualification: GeometryQualificationPayload | None = None


class BoardCellGeometryManualResolutionCommand(BoardCellGeometryManualPreviewCommand):
    idempotency_key: UUID
    corrected_by: str = Field(min_length=1, max_length=200)
    cell_symbols: tuple[GridCorrectionCellSymbolPayload, ...] = ()


class BoardCellGeometryManualResolutionResponse(ApiModel):
    item: BoardCellGeometryPendingResponse
    review_item_id: UUID | None
    geometry_revision: int | None = Field(default=None, ge=1)
    created: bool


class BoardCellGeometryRejectionCommand(ApiModel):
    """Reject an open deferred slot (TASK-0970); ``note`` is required for ``other``."""

    idempotency_key: UUID
    reason: BoardRejectionReason
    note: str | None = Field(default=None, max_length=1000)
    expected_geometry_revision: int = Field(ge=0)


class BoardCellGeometryRejectionResponse(ApiModel):
    item: BoardCellGeometryPendingResponse
    counts: BoardCellGeometryJobCountsResponse
    created: bool
    # Id of the durable rejection: the "Ostatnie korekty" entry to revert.
    rejection_id: UUID


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
        rejection_reason=value.rejection_reason,
        rejection_note=value.rejection_note,
        rejected_at=value.rejected_at,
        rejected_by=value.rejected_by,
    )


def to_counts_response(value: BoardCellGeometryJobCounts) -> BoardCellGeometryJobCountsResponse:
    return BoardCellGeometryJobCountsResponse(
        total=value.total,
        pending=value.pending,
        resolved=value.resolved,
        superseded=value.superseded,
        rejected=value.rejected,
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
        lattice_nodes=lattice_nodes_payload(value.board_geometry.get("latticeNodes")),
        expected_proposal_checksum_sha256=(
            str(value.board_geometry["neuralProposalChecksumSha256"])
            if isinstance(value.board_geometry.get("neuralProposalChecksumSha256"), str)
            else None
        ),
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


def to_rejection_response(value: BoardCellGeometryRejection) -> BoardCellGeometryRejectionResponse:
    return BoardCellGeometryRejectionResponse(
        item=to_pending_response(value.pending),
        counts=to_counts_response(value.counts),
        created=value.created,
        rejection_id=value.rejection_id,
    )


def _quad(
    geometry: object,
) -> tuple[
    ManualSourceGeometryPoint,
    ManualSourceGeometryPoint,
    ManualSourceGeometryPoint,
    ManualSourceGeometryPoint,
]:
    if not isinstance(geometry, Mapping):
        raise ValueError("The pending board geometry is invalid.")
    raw = geometry.get("quad") or geometry.get("pageBoardQuad")
    if not isinstance(raw, list | tuple) or len(raw) != 4:
        raise ValueError("The pending board quad is unavailable.")
    points: list[ManualSourceGeometryPoint] = []
    for value in raw:
        if not isinstance(value, Mapping):
            raise ValueError("The pending board quad is invalid.")
        points.append(
            ManualSourceGeometryPoint(
                x=round(float(value["x"])),
                y=round(float(value["y"])),
            )
        )
    return cast(
        tuple[
            ManualSourceGeometryPoint,
            ManualSourceGeometryPoint,
            ManualSourceGeometryPoint,
            ManualSourceGeometryPoint,
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
    "BoardCellGeometryRejectionCommand",
    "BoardCellGeometryRejectionResponse",
    "to_pending_page_response",
    "to_pending_response",
    "to_correction_context_response",
    "to_manual_resolution_response",
    "to_rejection_response",
]
