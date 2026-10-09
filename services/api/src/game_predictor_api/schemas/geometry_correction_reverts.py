"""OpenAPI contract for listing, previewing and reverting geometry corrections."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from game_predictor_api.application.geometry_correction_reverts import (
    GeometryCorrectionEntry,
    GeometryCorrectionRevertPreview,
    GeometryCorrectionRevertResult,
)
from game_predictor_api.domain.geometry_correction_reverts import (
    GeometryCorrectionKind,
    RevertBlockingReason,
)
from game_predictor_api.domain.image_geometry_completeness import SourceImageGeometryStatus
from game_predictor_api.schemas.catalog import ApiModel


class GeometryCorrectionResponse(ApiModel):
    """One manual geometry save of an import with its revert eligibility."""

    board_geometry_revision_id: UUID
    kind: GeometryCorrectionKind
    recognized_board_id: UUID
    review_item_id: UUID
    pending_geometry_id: UUID | None
    source_image_id: UUID
    sequence_number: int = Field(ge=1)
    position_index: int = Field(ge=0, le=8)
    created_at: datetime
    actor: str
    geometry_revision: int = Field(ge=0)
    resolution_revision: int = Field(ge=0)
    revertable: bool
    blocking_reason_code: RevertBlockingReason | None
    blocking_reason_message: str | None


class GeometryCorrectionListResponse(ApiModel):
    items: tuple[GeometryCorrectionResponse, ...]


class GeometryCorrectionRevertPreviewResponse(ApiModel):
    correction: GeometryCorrectionResponse
    removes_board: bool
    removed_cell_count: int = Field(ge=0)
    repointed_board_count: int = Field(ge=0)
    restored_cell_decision_count: int = Field(ge=0)
    reverted_source_geometry_revision_id: UUID
    restored_source_geometry_revision_id: UUID | None
    restored_source_engine_kind: str | None
    restored_source_status: str | None
    expected_geometry_revision: int = Field(ge=0)
    expected_resolution_revision: int = Field(ge=0)


class GeometryCorrectionRevertCommand(ApiModel):
    idempotency_key: UUID
    expected_geometry_revision: int = Field(ge=0)
    expected_resolution_revision: int = Field(ge=0)


class GeometryCorrectionRevertResponse(ApiModel):
    revert_id: UUID
    created: bool
    kind: GeometryCorrectionKind
    board_geometry_revision_id: UUID
    pending_geometry_id: UUID | None
    recognized_board_id: UUID
    review_item_id: UUID
    reverted_source_geometry_revision_id: UUID
    restored_source_geometry_revision_id: UUID
    repointed_board_ids: tuple[UUID, ...]
    removed_cell_count: int = Field(ge=0)
    source_image_geometry_status: SourceImageGeometryStatus | None
    snapshot_checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    created_at: datetime
    restored_geometry_revision: int | None = Field(default=None, ge=1)
    restored_cell_decision_count: int = Field(ge=0)


def to_geometry_correction_response(value: GeometryCorrectionEntry) -> GeometryCorrectionResponse:
    return GeometryCorrectionResponse(
        board_geometry_revision_id=value.board_geometry_revision_id,
        kind=value.kind,
        recognized_board_id=value.recognized_board_id,
        review_item_id=value.review_item_id,
        pending_geometry_id=value.pending_geometry_id,
        source_image_id=value.source_image_id,
        sequence_number=value.sequence_number,
        position_index=value.position_index,
        created_at=value.created_at,
        actor=value.actor,
        geometry_revision=value.geometry_revision,
        resolution_revision=value.resolution_revision,
        revertable=value.revertable,
        blocking_reason_code=value.blocking_reason,
        blocking_reason_message=value.blocking_reason_message,
    )


def to_geometry_correction_list_response(
    values: tuple[GeometryCorrectionEntry, ...],
) -> GeometryCorrectionListResponse:
    return GeometryCorrectionListResponse(
        items=tuple(to_geometry_correction_response(value) for value in values)
    )


def to_geometry_correction_revert_preview_response(
    value: GeometryCorrectionRevertPreview,
) -> GeometryCorrectionRevertPreviewResponse:
    return GeometryCorrectionRevertPreviewResponse(
        correction=to_geometry_correction_response(value.correction),
        removes_board=value.removes_board,
        removed_cell_count=value.removed_cell_count,
        repointed_board_count=value.repointed_board_count,
        restored_cell_decision_count=value.restored_cell_decision_count,
        reverted_source_geometry_revision_id=value.reverted_source_geometry_revision_id,
        restored_source_geometry_revision_id=value.restored_source_geometry_revision_id,
        restored_source_engine_kind=value.restored_source_engine_kind,
        restored_source_status=value.restored_source_status,
        expected_geometry_revision=value.correction.geometry_revision,
        expected_resolution_revision=value.correction.resolution_revision,
    )


def to_geometry_correction_revert_response(
    value: GeometryCorrectionRevertResult,
) -> GeometryCorrectionRevertResponse:
    return GeometryCorrectionRevertResponse(
        revert_id=value.revert_id,
        created=value.created,
        kind=value.kind,
        board_geometry_revision_id=value.board_geometry_revision_id,
        pending_geometry_id=value.pending_geometry_id,
        recognized_board_id=value.recognized_board_id,
        review_item_id=value.review_item_id,
        reverted_source_geometry_revision_id=value.reverted_source_geometry_revision_id,
        restored_source_geometry_revision_id=value.restored_source_geometry_revision_id,
        repointed_board_ids=value.repointed_board_ids,
        removed_cell_count=value.removed_cell_count,
        source_image_geometry_status=value.source_image_geometry_status,
        snapshot_checksum_sha256=value.snapshot_checksum_sha256,
        created_at=value.created_at,
        restored_geometry_revision=value.restored_geometry_revision,
        restored_cell_decision_count=value.restored_cell_decision_count,
    )
