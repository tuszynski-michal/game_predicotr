"""Read-only use cases for the bounded symbol-cell review workspace."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewAsset,
    SymbolCellReviewCounts,
    SymbolCellReviewCursorDirection,
    SymbolCellReviewError,
    SymbolCellReviewFilterState,
    SymbolCellReviewListFilter,
    SymbolCellReviewListItem,
    SymbolCellReviewPage,
    decode_symbol_cell_review_cursor,
    encode_symbol_cell_review_cursor,
)

DEFAULT_SYMBOL_CELL_REVIEW_PAGE_SIZE = 60
MAX_SYMBOL_CELL_REVIEW_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class SymbolCellReviewListSlice:
    """One already ordered, bounded keyset query result."""

    items: tuple[SymbolCellReviewListItem, ...]
    has_previous: bool
    has_next: bool


class SymbolCellReviewQueryRepository(Protocol):
    def require_ready_game(self, game_id: UUID) -> int: ...

    def list_items(
        self,
        *,
        review_filter: SymbolCellReviewListFilter,
        after_key: tuple[int, int, str] | None,
        before_key: tuple[int, int, str] | None,
        limit: int,
    ) -> SymbolCellReviewListSlice: ...

    def counts(self, *, review_filter: SymbolCellReviewListFilter) -> SymbolCellReviewCounts: ...

    def get_asset(
        self,
        *,
        game_id: UUID,
        cell_review_id: UUID,
    ) -> SymbolCellReviewAsset | None: ...


class SymbolCellReviewQueryService:
    """Keep HTTP parsing and database pagination outside the domain layer."""

    def __init__(self, repository: SymbolCellReviewQueryRepository) -> None:
        self._repository = repository

    def list(
        self,
        *,
        game_id: UUID,
        symbol_id: UUID | None,
        state: SymbolCellReviewFilterState,
        after_cursor: str | None,
        before_cursor: str | None,
        limit: int = DEFAULT_SYMBOL_CELL_REVIEW_PAGE_SIZE,
    ) -> SymbolCellReviewPage:
        if not 1 <= limit <= MAX_SYMBOL_CELL_REVIEW_PAGE_SIZE:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_PAGE_INVALID",
                "The symbol-cell review page limit must be between 1 and 100.",
            )
        if after_cursor and before_cursor:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_CURSOR_DIRECTION_CONFLICT",
                "Use either afterCursor or beforeCursor, not both.",
            )
        review_filter = SymbolCellReviewListFilter(
            game_id=game_id,
            symbol_id=symbol_id,
            state=state,
        )
        after_key = (
            decode_symbol_cell_review_cursor(
                after_cursor,
                review_filter=review_filter,
                direction=SymbolCellReviewCursorDirection.AFTER,
            )
            if after_cursor
            else None
        )
        before_key = (
            decode_symbol_cell_review_cursor(
                before_cursor,
                review_filter=review_filter,
                direction=SymbolCellReviewCursorDirection.BEFORE,
            )
            if before_cursor
            else None
        )
        catalog_revision = self._repository.require_ready_game(game_id)
        page_slice = self._repository.list_items(
            review_filter=review_filter,
            after_key=after_key,
            before_key=before_key,
            limit=limit,
        )
        items = page_slice.items
        return SymbolCellReviewPage(
            items=items,
            counts=self._repository.counts(review_filter=review_filter),
            catalog_revision=catalog_revision,
            next_cursor=(
                encode_symbol_cell_review_cursor(
                    review_filter=review_filter,
                    direction=SymbolCellReviewCursorDirection.AFTER,
                    key=items[-1].cursor_key,
                )
                if items and page_slice.has_next
                else None
            ),
            previous_cursor=(
                encode_symbol_cell_review_cursor(
                    review_filter=review_filter,
                    direction=SymbolCellReviewCursorDirection.BEFORE,
                    key=items[0].cursor_key,
                )
                if items and page_slice.has_previous
                else None
            ),
        )

    def asset(
        self,
        *,
        game_id: UUID,
        cell_review_id: UUID,
        expected_crop_checksum_sha256: str,
    ) -> SymbolCellReviewAsset:
        if len(expected_crop_checksum_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in expected_crop_checksum_sha256
        ):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_CHECKSUM_INVALID",
                "expectedCropChecksumSha256 must be a lowercase SHA-256 checksum.",
            )
        self._repository.require_ready_game(game_id)
        asset = self._repository.get_asset(game_id=game_id, cell_review_id=cell_review_id)
        if asset is None:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_CELL_NOT_FOUND",
                "The symbol-cell review crop does not exist in this current game scope.",
            )
        if asset.geometry_revision != asset.current_geometry_revision:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_CROP_DRIFT",
                "The symbol-cell crop no longer belongs to the current geometry revision.",
            )
        if asset.crop_checksum_sha256 != expected_crop_checksum_sha256:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_CROP_DRIFT",
                "The symbol-cell crop changed after it was loaded. Reload the page.",
            )
        return asset


__all__ = [
    "DEFAULT_SYMBOL_CELL_REVIEW_PAGE_SIZE",
    "MAX_SYMBOL_CELL_REVIEW_PAGE_SIZE",
    "SymbolCellReviewListSlice",
    "SymbolCellReviewQueryRepository",
    "SymbolCellReviewQueryService",
]
