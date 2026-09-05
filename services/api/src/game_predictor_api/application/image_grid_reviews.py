"""Bounded game-wide geometry validation use cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.image_grid_reviews import (
    ImageGridApprovalResult,
    ImageGridReviewCounts,
    ImageGridReviewCursorDirection,
    ImageGridReviewError,
    ImageGridReviewListFilter,
    ImageGridReviewListItem,
    ImageGridReviewPage,
    ImageGridReviewSourceApprovalTarget,
    ImageGridReviewSourceAsset,
    ImageGridReviewView,
    ImageGridSourceApprovalResult,
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

    def get_grid_review_source_asset(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
    ) -> ImageGridReviewSourceAsset | None: ...

    def approve_grid_geometry(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
        expected_resolution_revision: int,
        expected_geometry_revision: int,
        expected_source_checksum_sha256: str,
        expected_source_width: int,
        expected_source_height: int,
        expected_grid_rows: int,
        expected_grid_columns: int,
        actor: str,
    ) -> ImageGridApprovalResult: ...

    def approve_source_grid_geometry(
        self,
        *,
        game_id: UUID,
        source_image_id: UUID,
        targets: tuple[ImageGridReviewSourceApprovalTarget, ...],
        actor: str,
    ) -> ImageGridSourceApprovalResult: ...


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
            counts=self._repository.grid_review_counts(review_filter=review_filter),
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

    def approve(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
        expected_resolution_revision: int,
        expected_geometry_revision: int,
        expected_source_checksum_sha256: str,
        expected_source_width: int,
        expected_source_height: int,
        expected_grid_rows: int,
        expected_grid_columns: int,
        actor: str,
    ) -> ImageGridApprovalResult:
        _validate_sha256(expected_source_checksum_sha256)
        self._repository.require_game(game_id)
        return self._repository.approve_grid_geometry(
            game_id=game_id,
            review_item_id=review_item_id,
            expected_resolution_revision=expected_resolution_revision,
            expected_geometry_revision=expected_geometry_revision,
            expected_source_checksum_sha256=expected_source_checksum_sha256,
            expected_source_width=expected_source_width,
            expected_source_height=expected_source_height,
            expected_grid_rows=expected_grid_rows,
            expected_grid_columns=expected_grid_columns,
            actor=actor,
        )

    def approve_source(
        self,
        *,
        game_id: UUID,
        source_image_id: UUID,
        targets: tuple[ImageGridReviewSourceApprovalTarget, ...],
        actor: str,
    ) -> ImageGridSourceApprovalResult:
        if not targets:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_SOURCE_TARGETS_EMPTY",
                "Source approval requires at least one current board target.",
            )
        if len({target.review_item_id for target in targets}) != len(targets):
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_SOURCE_TARGETS_DUPLICATE",
                "A source approval command cannot repeat a board target.",
            )
        for target in targets:
            _validate_sha256(target.expected_source_checksum_sha256)
        self._repository.require_game(game_id)
        return self._repository.approve_source_grid_geometry(
            game_id=game_id,
            source_image_id=source_image_id,
            targets=targets,
            actor=actor,
        )


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
