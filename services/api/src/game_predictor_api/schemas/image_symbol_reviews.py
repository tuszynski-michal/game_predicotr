"""OpenAPI responses for bounded, local-only symbol-cell review reads."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewCounts,
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
    revision: int = Field(ge=0)
    geometry_revision: int = Field(ge=0)
    crop_checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    board_status: str


class SymbolCellReviewPageResponse(ApiModel):
    items: tuple[SymbolCellReviewListItemResponse, ...] = Field(max_length=100)
    counts: SymbolCellReviewCountsResponse
    catalog_revision: int = Field(ge=0)
    next_cursor: str | None
    previous_cursor: str | None


def to_symbol_cell_review_page_response(
    page: SymbolCellReviewPage,
) -> SymbolCellReviewPageResponse:
    return SymbolCellReviewPageResponse(
        items=tuple(_to_item_response(item) for item in page.items),
        counts=_to_counts_response(page.counts),
        catalog_revision=page.catalog_revision,
        next_cursor=page.next_cursor,
        previous_cursor=page.previous_cursor,
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
        revision=item.revision,
        geometry_revision=item.geometry_revision,
        crop_checksum_sha256=item.crop_checksum_sha256,
        board_status=item.board_status,
    )


__all__ = [
    "SymbolCellReviewCountsResponse",
    "SymbolCellReviewListItemResponse",
    "SymbolCellReviewPageResponse",
    "to_symbol_cell_review_page_response",
]
