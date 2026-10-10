"""Bounded game-wide grid correction queue use cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.image_grid_reviews import (
    ImageGridReviewCounts,
    ImageGridReviewCountsMode,
    ImageGridReviewCursorDirection,
    ImageGridReviewError,
    ImageGridReviewListFilter,
    ImageGridReviewListItem,
    ImageGridReviewPage,
    ImageGridReviewSourceAsset,
    ImageGridReviewView,
    decode_image_grid_review_cursor,
    encode_image_grid_review_cursor,
)

DEFAULT_IMAGE_GRID_REVIEW_PAGE_SIZE = 25
MAX_IMAGE_GRID_REVIEW_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class ImageGridReviewListSlice:
    items: tuple[ImageGridReviewListItem, ...]
    has_previous: bool
    has_next: bool


class ImageGridReviewRepository(Protocol):
    def require_game(self, game_id: UUID) -> None: ...

    def list_grid_reviews(
        self,
        *,
        review_filter: ImageGridReviewListFilter,
        after_key: tuple[int, str] | None,
        before_key: tuple[int, str] | None,
        limit: int,
    ) -> ImageGridReviewListSlice: ...

    def grid_review_counts(
        self,
        *,
        review_filter: ImageGridReviewListFilter,
    ) -> ImageGridReviewCounts: ...

    def grid_review_correction_count(
        self,
        *,
        review_filter: ImageGridReviewListFilter,
    ) -> int:
        """Only the D-462 R4 correction queue size (TASK-0961); cheap by design."""
        ...

    def get_grid_review_source_asset(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
    ) -> ImageGridReviewSourceAsset | None: ...


class ImageGridReviewService:
    def __init__(self, repository: ImageGridReviewRepository) -> None:
        self._repository = repository

    def list(
        self,
        *,
        game_id: UUID,
        view: ImageGridReviewView,
        import_job_id: UUID | None,
        source_image_id: UUID | None,
        after_cursor: str | None,
        before_cursor: str | None,
        limit: int = DEFAULT_IMAGE_GRID_REVIEW_PAGE_SIZE,
        counts: ImageGridReviewCountsMode = ImageGridReviewCountsMode.ALL,
    ) -> ImageGridReviewPage:
        if not 1 <= limit <= MAX_IMAGE_GRID_REVIEW_PAGE_SIZE:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_PAGE_INVALID",
                "The grid review page limit must be between 1 and 100.",
            )
        if after_cursor and before_cursor:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_CURSOR_DIRECTION_CONFLICT",
                "Use either afterCursor or beforeCursor, not both.",
            )
        review_filter = ImageGridReviewListFilter(
            game_id=game_id,
            view=view,
            import_job_id=import_job_id,
            source_image_id=source_image_id,
        )
        after_key = (
            decode_image_grid_review_cursor(
                after_cursor,
                review_filter=review_filter,
                direction=ImageGridReviewCursorDirection.AFTER,
            )
            if after_cursor
            else None
        )
        before_key = (
            decode_image_grid_review_cursor(
                before_cursor,
                review_filter=review_filter,
                direction=ImageGridReviewCursorDirection.BEFORE,
            )
            if before_cursor
            else None
        )
        self._repository.require_game(game_id)
        page_slice = self._repository.list_grid_reviews(
            review_filter=review_filter,
            after_key=after_key,
            before_key=before_key,
            limit=limit,
        )
        items = page_slice.items
        return ImageGridReviewPage(
            items=items,
            counts=self._counts(review_filter=review_filter, mode=counts),
            previous_cursor=(
                encode_image_grid_review_cursor(
                    review_filter=review_filter,
                    direction=ImageGridReviewCursorDirection.BEFORE,
                    key=items[0].cursor_key,
                )
                if items and page_slice.has_previous
                else None
            ),
            next_cursor=(
                encode_image_grid_review_cursor(
                    review_filter=review_filter,
                    direction=ImageGridReviewCursorDirection.AFTER,
                    key=items[-1].cursor_key,
                )
                if items and page_slice.has_next
                else None
            ),
        )

    def _counts(
        self,
        *,
        review_filter: ImageGridReviewListFilter,
        mode: ImageGridReviewCountsMode,
    ) -> ImageGridReviewCounts:
        if mode is ImageGridReviewCountsMode.CORRECTION:
            # TASK-0961: only the correction queue is counted; every other
            # counter is reported as 0, as the OpenAPI description says.
            return ImageGridReviewCounts(
                needs_validation=0,
                needs_correction=0,
                approved=0,
                full_grids=0,
                correction=self._repository.grid_review_correction_count(
                    review_filter=review_filter
                ),
            )
        return self._repository.grid_review_counts(review_filter=review_filter)

    def source_asset(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
        expected_source_checksum_sha256: str,
    ) -> ImageGridReviewSourceAsset:
        _validate_sha256(expected_source_checksum_sha256)
        self._repository.require_game(game_id)
        asset = self._repository.get_grid_review_source_asset(
            game_id=game_id,
            review_item_id=review_item_id,
        )
        if asset is None:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_ITEM_NOT_FOUND",
                "The current grid review item does not exist in this game scope.",
            )
        if asset.source_checksum_sha256 != expected_source_checksum_sha256:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_SOURCE_DRIFT",
                "The source image changed after the grid review was loaded.",
            )
        return asset


def _validate_sha256(value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_CHECKSUM_INVALID",
            "The expected source checksum must be a lowercase SHA-256 checksum.",
        )


__all__ = [
    "DEFAULT_IMAGE_GRID_REVIEW_PAGE_SIZE",
    "MAX_IMAGE_GRID_REVIEW_PAGE_SIZE",
    "ImageGridReviewListSlice",
    "ImageGridReviewRepository",
    "ImageGridReviewService",
]
