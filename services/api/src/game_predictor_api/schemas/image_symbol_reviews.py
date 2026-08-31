"""OpenAPI responses for bounded, local-only symbol-cell review reads."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from pydantic import Field, model_validator

from game_predictor_api.application.image_symbol_review_backfill import (
    SymbolCellReviewProjectionStart,
    SymbolCellReviewProjectionStatus,
)
from game_predictor_api.application.image_symbol_review_bulk_operations import (
    MAX_EXPLICIT_SYMBOL_CELL_REVIEW_TARGETS,
    SymbolCellReviewBulkExplicitTarget,
    SymbolCellReviewBulkFilterSelection,
    SymbolCellReviewBulkOperation,
    SymbolCellReviewBulkPreview,
    SymbolCellReviewBulkRequest,
)
from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationResult,
)
from game_predictor_api.application.unreadable_board_reviews import (
    UnreadableBoardReviewDetail,
    UnreadableBoardReviewPage,
)
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewAction,
    SymbolCellReviewCounts,
    SymbolCellReviewCountSnapshot,
    SymbolCellReviewFilterState,
    SymbolCellReviewListItem,
    SymbolCellReviewPage,
)
from game_predictor_api.schemas.catalog import ApiModel


class SymbolCellReviewCountsResponse(ApiModel):
    all_count: int = Field(ge=0)
    approved_count: int = Field(ge=0)
    pending_count: int = Field(ge=0)


class SymbolCellReviewListItemResponse(ApiModel):
    id: UUID
    review_item_id: UUID
    recognized_board_id: UUID
    import_job_id: UUID
    sequence_number: int = Field(ge=1)
    cell_index: int = Field(ge=0, le=14)
    row_index: int = Field(ge=0, le=2)
    column_index: int = Field(ge=0, le=4)
    assigned_symbol_id: UUID | None
    assigned_symbol_code: str | None
    assigned_symbol_name: str | None
    prediction_symbol_code: str | None
    review_state: str
    has_grid_issue: bool
    quality_issue: str | None
    is_unknown: bool
    crop_approval_state: str
    revision: int = Field(ge=0)
    geometry_revision: int = Field(ge=0)
    crop_sample_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    crop_checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    board_status: str
    prediction_confidence: float | None = Field(default=None, ge=0, le=1)
    asset_mode: Literal["legacy_file", "virtual_source"] = "legacy_file"
    render_spec_checksum_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )


class SymbolCellReviewPageResponse(ApiModel):
    items: tuple[SymbolCellReviewListItemResponse, ...]
    catalog_revision: int = Field(ge=0)
    next_cursor: str | None
    previous_cursor: str | None


class SymbolCellReviewCountSnapshotResponse(ApiModel):
    counts: SymbolCellReviewCountsResponse
    catalog_revision: int = Field(ge=0)


class VirtualCellPreviewTargetRequest(ApiModel):
    cell_review_id: UUID
    expected_revision: int = Field(ge=0)
    expected_render_spec_checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class VirtualCellPreviewBatchRequest(ApiModel):
    preview_size: int = Field(default=100, ge=32, le=256)
    extraction_mode: Literal["direct_perspective_cell_v1"] = "direct_perspective_cell_v1"
    cells: tuple[VirtualCellPreviewTargetRequest, ...] = Field(min_length=1, max_length=100)


class VirtualCellPreviewTileResponse(ApiModel):
    cell_review_id: UUID
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(ge=1)
    height: int = Field(ge=1)


class VirtualCellPreviewBatchResponse(ApiModel):
    batch_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    atlas_url: str
    atlas_checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    tiles: tuple[VirtualCellPreviewTileResponse, ...]
    expires_at: datetime


class SymbolCellReviewProjectionStatusResponse(ApiModel):
    game_id: UUID
    status: Literal["not_started", "rebuilding", "ready", "failed"]
    expected_board_count: int = Field(ge=0)
    expected_cell_count: int = Field(ge=0)
    processed_board_count: int = Field(ge=0)
    persisted_cell_count: int = Field(ge=0)
    missing_sequence_count: int = Field(ge=0)
    invalid_crop_count: int = Field(ge=0)
    invalid_geometry_count: int = Field(ge=0)
    failure_message: str | None
    sample_problem_review_item_ids: tuple[UUID, ...]
    active_job_id: UUID | None
    table_bytes_before: int | None = Field(default=None, ge=0)
    index_bytes_before: int | None = Field(default=None, ge=0)
    table_bytes_current: int | None = Field(default=None, ge=0)
    index_bytes_current: int | None = Field(default=None, ge=0)
    database_free_bytes_current: int | None = Field(default=None, ge=0)


class SymbolCellReviewProjectionStartResponse(ApiModel):
    projection: SymbolCellReviewProjectionStatusResponse
    job_id: UUID | None
    created: bool


class SymbolCellReviewBulkExplicitTargetRequest(ApiModel):
    cell_review_id: UUID
    expected_revision: int = Field(ge=0)
    expected_geometry_revision: int = Field(ge=0)
    expected_crop_sample_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_crop_checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class SymbolCellReviewBulkExplicitSelectionRequest(ApiModel):
    kind: Literal["explicit"]
    targets: tuple[SymbolCellReviewBulkExplicitTargetRequest, ...] = Field(
        min_length=1,
        max_length=MAX_EXPLICIT_SYMBOL_CELL_REVIEW_TARGETS,
    )


class SymbolCellReviewBulkFilterSelectionRequest(ApiModel):
    kind: Literal["filter"]
    symbol_id: UUID | Literal["unknown"]
    state: SymbolCellReviewFilterState = SymbolCellReviewFilterState.ALL
    min_confidence: float | None = Field(default=None, ge=0, le=1)
    max_confidence: float | None = Field(default=None, ge=0, le=1)
    catalog_revision: int = Field(ge=0)
    excluded_cell_review_ids: tuple[UUID, ...] = Field(
        default=(),
        max_length=MAX_EXPLICIT_SYMBOL_CELL_REVIEW_TARGETS,
    )

    @model_validator(mode="after")
    def validate_confidence_range(self) -> SymbolCellReviewBulkFilterSelectionRequest:
        if (
            self.min_confidence is not None
            and self.max_confidence is not None
            and self.min_confidence > self.max_confidence
        ):
            raise ValueError("minConfidence cannot be greater than maxConfidence.")
        return self


SymbolCellReviewBulkSelectionRequest = Annotated[
    SymbolCellReviewBulkExplicitSelectionRequest | SymbolCellReviewBulkFilterSelectionRequest,
    Field(discriminator="kind"),
]


class SymbolCellReviewBulkOperationRequest(ApiModel):
    action: SymbolCellReviewAction
    target_symbol_id: UUID | None = None
    selection: SymbolCellReviewBulkSelectionRequest

    @model_validator(mode="after")
    def validate_action_target(self) -> SymbolCellReviewBulkOperationRequest:
        if self.action is SymbolCellReviewAction.REASSIGN and self.target_symbol_id is None:
            raise ValueError("targetSymbolId is required for reassign.")
        if self.action is not SymbolCellReviewAction.REASSIGN and self.target_symbol_id is not None:
            raise ValueError("targetSymbolId is allowed only for reassign.")
        return self


class SymbolCellReviewBulkOperationStartRequest(SymbolCellReviewBulkOperationRequest):
    idempotency_key: UUID


class SymbolCellReviewBulkPreviewResponse(ApiModel):
    action: SymbolCellReviewAction
    selection_kind: str
    catalog_revision: int = Field(ge=0)
    target_count: int = Field(ge=0)
    board_count: int = Field(ge=0)
    target_symbol_id: UUID | None


class SymbolCellReviewBulkOperationResponse(ApiModel):
    id: UUID
    job_id: UUID
    game_id: UUID
    action: SymbolCellReviewAction
    target_symbol_id: UUID | None
    selection_kind: str
    status: str
    catalog_revision: int | None = Field(default=None, ge=0)
    target_count: int = Field(ge=0)
    applied_count: int = Field(ge=0)
    conflict_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    pending_count: int = Field(ge=0)
    error_code: str | None
    error_message: str | None
    command_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class SymbolCellReviewBulkOperationStartResponse(ApiModel):
    operation: SymbolCellReviewBulkOperationResponse
    created: bool


class SymbolCellReviewMutationRequest(ApiModel):
    action: SymbolCellReviewAction
    expected_revision: int = Field(ge=0)
    expected_geometry_revision: int = Field(ge=0)
    expected_crop_sample_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_crop_checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    target_symbol_id: UUID | None = None

    @model_validator(mode="after")
    def validate_action_target(self) -> SymbolCellReviewMutationRequest:
        if self.action is SymbolCellReviewAction.REASSIGN and self.target_symbol_id is None:
            raise ValueError("targetSymbolId is required for reassign.")
        if self.action is not SymbolCellReviewAction.REASSIGN and self.target_symbol_id is not None:
            raise ValueError("targetSymbolId is allowed only for reassign.")
        return self


class SymbolCellReviewMutationResponse(ApiModel):
    cell_review_id: UUID
    review_item_id: UUID
    sequence_number: int = Field(ge=1)
    cell_revision: int = Field(ge=0)
    review_state: str
    assigned_symbol_id: UUID | None
    has_grid_issue: bool
    quality_issue: str | None
    board_status: str
    board_resolution_action: str | None
    board_reopened: bool
    catalog_revision: int = Field(ge=0)


class UnreadableBoardReviewListItemResponse(ApiModel):
    review_item_id: UUID
    recognized_board_id: UUID
    import_job_id: UUID
    sequence_number: int = Field(ge=1)
    board_status: str
    grid_rows: int = Field(ge=1)
    grid_columns: int = Field(ge=1)
    unreadable_count: int = Field(ge=1)
    pending_unreadable_count: int = Field(ge=0)


class UnreadableBoardReviewPageResponse(ApiModel):
    items: tuple[UnreadableBoardReviewListItemResponse, ...]
    next_cursor: str | None


class UnreadableBoardReviewCellResponse(ApiModel):
    cell_review_id: UUID
    cell_index: int = Field(ge=0)
    row_index: int = Field(ge=0)
    column_index: int = Field(ge=0)
    assigned_symbol_id: UUID | None
    assigned_symbol_code: str | None
    assigned_symbol_name: str | None
    prediction_symbol_code: str | None
    review_state: str
    quality_issue: str | None
    revision: int = Field(ge=0)
    geometry_revision: int = Field(ge=0)
    crop_sample_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    crop_checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class UnreadableBoardReviewDetailResponse(ApiModel):
    review_item_id: UUID
    recognized_board_id: UUID
    import_job_id: UUID
    sequence_number: int = Field(ge=1)
    board_status: str
    grid_rows: int = Field(ge=1)
    grid_columns: int = Field(ge=1)
    cells: tuple[UnreadableBoardReviewCellResponse, ...]


class UnreadableSymbolAssignmentRequest(ApiModel):
    kind: Literal["symbol"]
    symbol_id: UUID


class UnreadableUnknownAssignmentRequest(ApiModel):
    kind: Literal["unknown"]


UnreadableCellAssignmentRequest = Annotated[
    UnreadableSymbolAssignmentRequest | UnreadableUnknownAssignmentRequest,
    Field(discriminator="kind"),
]


class ResolveUnreadableCellRequest(ApiModel):
    assignment: UnreadableCellAssignmentRequest
    expected_revision: int = Field(ge=0)
    expected_geometry_revision: int = Field(ge=0)
    expected_crop_sample_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_crop_checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def to_symbol_cell_review_page_response(
    page: SymbolCellReviewPage,
) -> SymbolCellReviewPageResponse:
    return SymbolCellReviewPageResponse(
        items=tuple(_to_item_response(item) for item in page.items),
        catalog_revision=page.catalog_revision,
        next_cursor=page.next_cursor,
        previous_cursor=page.previous_cursor,
    )


def to_symbol_cell_review_count_snapshot_response(
    snapshot: SymbolCellReviewCountSnapshot,
) -> SymbolCellReviewCountSnapshotResponse:
    return SymbolCellReviewCountSnapshotResponse(
        counts=_to_counts_response(snapshot.counts),
        catalog_revision=snapshot.catalog_revision,
    )


def to_symbol_cell_review_mutation_response(
    result: SymbolCellReviewMutationResult,
) -> SymbolCellReviewMutationResponse:
    return SymbolCellReviewMutationResponse(
        cell_review_id=result.cell_review_id,
        review_item_id=result.review_item_id,
        sequence_number=result.sequence_number,
        cell_revision=result.cell_revision,
        review_state=result.review_state.value,
        assigned_symbol_id=result.assigned_symbol_id,
        has_grid_issue=result.has_grid_issue,
        quality_issue=(None if result.quality_issue is None else result.quality_issue.value),
        board_status=result.board_status,
        board_resolution_action=result.board_resolution_action,
        board_reopened=result.board_reopened,
        catalog_revision=result.catalog_revision,
    )


def to_unreadable_board_review_page_response(
    page: UnreadableBoardReviewPage,
) -> UnreadableBoardReviewPageResponse:
    return UnreadableBoardReviewPageResponse(
        items=tuple(
            UnreadableBoardReviewListItemResponse(
                review_item_id=item.review_item_id,
                recognized_board_id=item.recognized_board_id,
                import_job_id=item.import_job_id,
                sequence_number=item.sequence_number,
                board_status=item.board_status,
                grid_rows=item.grid_rows,
                grid_columns=item.grid_columns,
                unreadable_count=item.unreadable_count,
                pending_unreadable_count=item.pending_unreadable_count,
            )
            for item in page.items
        ),
        next_cursor=page.next_cursor,
    )


def to_unreadable_board_review_detail_response(
    detail: UnreadableBoardReviewDetail,
) -> UnreadableBoardReviewDetailResponse:
    return UnreadableBoardReviewDetailResponse(
        review_item_id=detail.review_item_id,
        recognized_board_id=detail.recognized_board_id,
        import_job_id=detail.import_job_id,
        sequence_number=detail.sequence_number,
        board_status=detail.board_status,
        grid_rows=detail.grid_rows,
        grid_columns=detail.grid_columns,
        cells=tuple(
            UnreadableBoardReviewCellResponse(
                cell_review_id=cell.cell_review_id,
                cell_index=cell.cell_index,
                row_index=cell.row_index,
                column_index=cell.column_index,
                assigned_symbol_id=cell.assigned_symbol_id,
                assigned_symbol_code=cell.assigned_symbol_code,
                assigned_symbol_name=cell.assigned_symbol_name,
                prediction_symbol_code=cell.prediction_symbol_code,
                review_state=cell.review_state,
                quality_issue=cell.quality_issue,
                revision=cell.revision,
                geometry_revision=cell.geometry_revision,
                crop_sample_id=cell.crop_sample_id,
                crop_checksum_sha256=cell.crop_checksum_sha256,
            )
            for cell in detail.cells
        ),
    )


def to_symbol_cell_review_projection_status_response(
    status: SymbolCellReviewProjectionStatus,
) -> SymbolCellReviewProjectionStatusResponse:
    return SymbolCellReviewProjectionStatusResponse(
        game_id=status.game_id,
        status=status.status,
        expected_board_count=status.expected_board_count,
        expected_cell_count=status.expected_cell_count,
        processed_board_count=status.processed_board_count,
        persisted_cell_count=status.persisted_cell_count,
        missing_sequence_count=status.missing_sequence_count,
        invalid_crop_count=status.invalid_crop_count,
        invalid_geometry_count=status.invalid_geometry_count,
        failure_message=status.failure_message,
        sample_problem_review_item_ids=status.sample_problem_review_item_ids,
        active_job_id=status.active_job_id,
        table_bytes_before=status.table_bytes_before,
        index_bytes_before=status.index_bytes_before,
        table_bytes_current=status.table_bytes_current,
        index_bytes_current=status.index_bytes_current,
        database_free_bytes_current=status.database_free_bytes_current,
    )


def to_symbol_cell_review_projection_start_response(
    result: SymbolCellReviewProjectionStart,
) -> SymbolCellReviewProjectionStartResponse:
    return SymbolCellReviewProjectionStartResponse(
        projection=to_symbol_cell_review_projection_status_response(result.status),
        job_id=None if result.job is None else result.job.id,
        created=result.created,
    )


def to_symbol_cell_review_bulk_request(
    request: SymbolCellReviewBulkOperationRequest,
    *,
    actor: str,
) -> SymbolCellReviewBulkRequest:
    """Convert the local Admin contract without accepting an actor from HTTP."""

    selection = request.selection
    if isinstance(selection, SymbolCellReviewBulkExplicitSelectionRequest):
        return SymbolCellReviewBulkRequest(
            action=request.action,
            target_symbol_id=request.target_symbol_id,
            explicit_targets=tuple(
                SymbolCellReviewBulkExplicitTarget(
                    cell_review_id=target.cell_review_id,
                    expected_revision=target.expected_revision,
                    expected_geometry_revision=target.expected_geometry_revision,
                    expected_crop_sample_id=target.expected_crop_sample_id,
                    expected_crop_checksum_sha256=target.expected_crop_checksum_sha256,
                )
                for target in selection.targets
            ),
            filter_selection=None,
            actor=actor,
        )

    symbol_id = selection.symbol_id if isinstance(selection.symbol_id, UUID) else None
    return SymbolCellReviewBulkRequest(
        action=request.action,
        target_symbol_id=request.target_symbol_id,
        explicit_targets=None,
        filter_selection=SymbolCellReviewBulkFilterSelection(
            symbol_id=symbol_id,
            state=selection.state,
            min_confidence=selection.min_confidence,
            max_confidence=selection.max_confidence,
            catalog_revision=selection.catalog_revision,
            excluded_cell_review_ids=selection.excluded_cell_review_ids,
        ),
        actor=actor,
    )


def to_symbol_cell_review_bulk_preview_response(
    preview: SymbolCellReviewBulkPreview,
) -> SymbolCellReviewBulkPreviewResponse:
    return SymbolCellReviewBulkPreviewResponse(
        action=preview.action,
        selection_kind=preview.selection_kind.value,
        catalog_revision=preview.catalog_revision,
        target_count=preview.target_count,
        board_count=preview.board_count,
        target_symbol_id=preview.target_symbol_id,
    )


def to_symbol_cell_review_bulk_operation_response(
    operation: SymbolCellReviewBulkOperation,
) -> SymbolCellReviewBulkOperationResponse:
    return SymbolCellReviewBulkOperationResponse(
        id=operation.id,
        job_id=operation.job_id,
        game_id=operation.game_id,
        action=operation.action,
        target_symbol_id=operation.target_symbol_id,
        selection_kind=operation.selection_kind.value,
        status=operation.status.value,
        catalog_revision=operation.catalog_revision,
        target_count=operation.target_count,
        applied_count=operation.applied_count,
        conflict_count=operation.conflict_count,
        failed_count=operation.failed_count,
        pending_count=operation.pending_count,
        error_code=operation.error_code,
        error_message=operation.error_message,
        command_sha256=operation.command_sha256,
    )


def _to_counts_response(counts: SymbolCellReviewCounts) -> SymbolCellReviewCountsResponse:
    return SymbolCellReviewCountsResponse(
        all_count=counts.all_count,
        approved_count=counts.approved_count,
        pending_count=counts.pending_count,
    )


def _to_item_response(item: SymbolCellReviewListItem) -> SymbolCellReviewListItemResponse:
    return SymbolCellReviewListItemResponse(
        id=item.cell_review_id,
        review_item_id=item.review_item_id,
        recognized_board_id=item.recognized_board_id,
        import_job_id=item.import_job_id,
        sequence_number=item.sequence_number,
        cell_index=item.cell_index,
        row_index=item.row_index,
        column_index=item.column_index,
        assigned_symbol_id=item.assigned_symbol_id,
        assigned_symbol_code=item.assigned_symbol_code,
        assigned_symbol_name=item.assigned_symbol_name,
        prediction_symbol_code=item.prediction_symbol_code,
        review_state=item.review_state.value,
        has_grid_issue=item.has_grid_issue,
        quality_issue=(None if item.quality_issue is None else item.quality_issue.value),
        is_unknown=item.is_unknown,
        crop_approval_state=item.crop_approval_state.value,
        revision=item.revision,
        geometry_revision=item.geometry_revision,
        crop_sample_id=item.crop_sample_id,
        crop_checksum_sha256=item.crop_checksum_sha256,
        board_status=item.board_status,
        prediction_confidence=item.prediction_confidence,
        asset_mode=cast(Literal["legacy_file", "virtual_source"], item.asset_mode),
        render_spec_checksum_sha256=item.render_spec_checksum_sha256,
    )


__all__ = [
    "SymbolCellReviewBulkExplicitSelectionRequest",
    "SymbolCellReviewBulkExplicitTargetRequest",
    "SymbolCellReviewBulkFilterSelectionRequest",
    "SymbolCellReviewBulkOperationRequest",
    "SymbolCellReviewBulkOperationResponse",
    "SymbolCellReviewBulkOperationStartRequest",
    "SymbolCellReviewBulkOperationStartResponse",
    "SymbolCellReviewBulkPreviewResponse",
    "SymbolCellReviewBulkSelectionRequest",
    "SymbolCellReviewCountsResponse",
    "SymbolCellReviewCountSnapshotResponse",
    "SymbolCellReviewListItemResponse",
    "SymbolCellReviewMutationRequest",
    "SymbolCellReviewMutationResponse",
    "SymbolCellReviewPageResponse",
    "SymbolCellReviewProjectionStartResponse",
    "SymbolCellReviewProjectionStatusResponse",
    "ResolveUnreadableCellRequest",
    "UnreadableBoardReviewDetailResponse",
    "UnreadableBoardReviewPageResponse",
    "UnreadableSymbolAssignmentRequest",
    "UnreadableUnknownAssignmentRequest",
    "to_symbol_cell_review_bulk_operation_response",
    "to_symbol_cell_review_bulk_preview_response",
    "to_symbol_cell_review_bulk_request",
    "to_symbol_cell_review_count_snapshot_response",
    "to_symbol_cell_review_mutation_response",
    "to_symbol_cell_review_page_response",
    "to_symbol_cell_review_projection_start_response",
    "to_symbol_cell_review_projection_status_response",
    "to_unreadable_board_review_detail_response",
    "to_unreadable_board_review_page_response",
]
