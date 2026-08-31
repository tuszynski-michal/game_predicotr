"""Read-only use cases for the symbol-cell review workspace."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from game_predictor_api.application.virtual_cell_previews import (
    SymbolCellPreviewTarget,
    VirtualCellPreviewTarget,
)
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewAsset,
    SymbolCellReviewCounts,
    SymbolCellReviewCountSnapshot,
    SymbolCellReviewCursorDirection,
    SymbolCellReviewError,
    SymbolCellReviewFilterState,
    SymbolCellReviewListFilter,
    SymbolCellReviewListItem,
    SymbolCellReviewPage,
    decode_symbol_cell_review_cursor,
    encode_symbol_cell_review_cursor,
)

DEFAULT_SYMBOL_CELL_REVIEW_PAGE_SIZE = 500
MAX_SYMBOL_CELL_REVIEW_PAGE_SIZE = 500


@dataclass(frozen=True, slots=True)
class SymbolCellReviewListSlice:
    """One already ordered keyset query result."""

    items: tuple[SymbolCellReviewListItem, ...]
    has_previous: bool
    has_next: bool


class SymbolCellReviewQueryRepository(Protocol):
    def require_ready_game(self, game_id: UUID) -> int: ...

    def list_items(
        self,
        *,
        review_filter: SymbolCellReviewListFilter,
        after_key: tuple[int, int, UUID] | None,
        before_key: tuple[int, int, UUID] | None,
        limit: int,
    ) -> SymbolCellReviewListSlice: ...

    def counts(self, *, review_filter: SymbolCellReviewListFilter) -> SymbolCellReviewCounts: ...

    def get_asset(
        self,
        *,
        game_id: UUID,
        cell_review_id: UUID,
    ) -> SymbolCellReviewAsset | None: ...

    def get_assets(
        self,
        *,
        game_id: UUID,
        cell_review_ids: tuple[UUID, ...],
    ) -> tuple[SymbolCellReviewAsset, ...]: ...


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
        min_confidence: float | None = None,
        max_confidence: float | None = None,
        limit: int = DEFAULT_SYMBOL_CELL_REVIEW_PAGE_SIZE,
    ) -> SymbolCellReviewPage:
        if not 1 <= limit <= MAX_SYMBOL_CELL_REVIEW_PAGE_SIZE:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_PAGE_INVALID",
                "The symbol-cell review page limit must be between 1 and 500.",
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
            min_confidence=min_confidence,
            max_confidence=max_confidence,
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

    def counts(
        self,
        *,
        game_id: UUID,
        symbol_id: UUID | None,
        state: SymbolCellReviewFilterState,
        expected_catalog_revision: int,
        min_confidence: float | None = None,
        max_confidence: float | None = None,
    ) -> SymbolCellReviewCountSnapshot:
        review_filter = SymbolCellReviewListFilter(
            game_id=game_id,
            symbol_id=symbol_id,
            state=state,
            min_confidence=min_confidence,
            max_confidence=max_confidence,
        )
        catalog_revision = self._repository.require_ready_game(game_id)
        if catalog_revision != expected_catalog_revision:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_CATALOG_REVISION_STALE",
                "The symbol-cell review catalog changed after the page was loaded.",
                details={
                    "actualCatalogRevision": catalog_revision,
                    "expectedCatalogRevision": expected_catalog_revision,
                },
            )
        return SymbolCellReviewCountSnapshot(
            counts=self._repository.counts(review_filter=review_filter),
            catalog_revision=catalog_revision,
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
        assets = self._assets(
            game_id=game_id,
            cell_review_ids=(cell_review_id,),
        )
        return self._validate_expected_checksum(
            asset=assets[0],
            expected_crop_checksum_sha256=expected_crop_checksum_sha256,
        )

    def virtual_preview_assets(
        self,
        *,
        game_id: UUID,
        targets: tuple[VirtualCellPreviewTarget, ...],
    ) -> tuple[SymbolCellReviewAsset, ...]:
        """Validate every current virtual cell before one bounded atlas render."""

        if not targets:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_PREVIEW_BATCH_LIMIT",
                "A virtual preview batch must contain at least one symbol cell.",
            )
        ids = tuple(target.cell_review_id for target in targets)
        if len(set(ids)) != len(ids):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_PREVIEW_DUPLICATE_CELL",
                "A virtual preview batch cannot contain the same cell more than once.",
            )
        by_id = {
            asset.cell_review_id: asset
            for asset in self._assets(game_id=game_id, cell_review_ids=ids)
        }
        ordered: list[SymbolCellReviewAsset] = []
        for target in targets:
            asset = by_id.get(target.cell_review_id)
            if asset is None:
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_CELL_NOT_FOUND",
                    "The symbol-cell review crop does not exist in this current game scope.",
                )
            if asset.asset_mode != "virtual_source":
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_PREVIEW_ASSET_MODE_INVALID",
                    "The selected symbol cell still uses a legacy crop artifact.",
                )
            if asset.revision != target.expected_revision:
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_CROP_DRIFT",
                    "The symbol-cell review changed after it was loaded. Reload the page.",
                )
            if asset.render_spec_checksum_sha256 != target.expected_render_spec_checksum_sha256:
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_CROP_DRIFT",
                    "The virtual symbol-cell render changed after it was loaded. Reload the page.",
                )
            ordered.append(asset)
        return tuple(ordered)

    def preview_assets(
        self,
        *,
        game_id: UUID,
        targets: tuple[SymbolCellPreviewTarget, ...],
    ) -> tuple[SymbolCellReviewAsset, ...]:
        """Validate current legacy and virtual cells for one shared atlas."""

        if not targets:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_PREVIEW_BATCH_LIMIT",
                "A symbol preview batch must contain at least one cell.",
            )
        ids = tuple(target.cell_review_id for target in targets)
        if len(set(ids)) != len(ids):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_PREVIEW_DUPLICATE_CELL",
                "A symbol preview batch cannot contain the same cell more than once.",
            )
        by_id = {
            asset.cell_review_id: asset
            for asset in self._assets(game_id=game_id, cell_review_ids=ids)
        }
        ordered: list[SymbolCellReviewAsset] = []
        for target in targets:
            asset = by_id.get(target.cell_review_id)
            if asset is None:
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_CELL_NOT_FOUND",
                    "The symbol-cell review crop does not exist in this current game scope.",
                )
            if (
                asset.revision != target.expected_revision
                or asset.crop_checksum_sha256 != target.expected_crop_checksum_sha256
            ):
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_CROP_DRIFT",
                    "The symbol-cell review changed after it was loaded. Reload the page.",
                )
            if asset.asset_mode == "virtual_source":
                if (
                    target.expected_render_spec_checksum_sha256 is None
                    or asset.render_spec_checksum_sha256
                    != target.expected_render_spec_checksum_sha256
                ):
                    raise SymbolCellReviewError(
                        "SYMBOL_CELL_REVIEW_CROP_DRIFT",
                        "The virtual symbol-cell render changed after it was loaded. "
                        "Reload the page.",
                    )
            elif target.expected_render_spec_checksum_sha256 is not None:
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_PREVIEW_ASSET_MODE_INVALID",
                    "A legacy symbol-cell preview must not declare virtual render provenance.",
                )
            ordered.append(asset)
        return tuple(ordered)

    def _assets(
        self,
        *,
        game_id: UUID,
        cell_review_ids: tuple[UUID, ...],
    ) -> tuple[SymbolCellReviewAsset, ...]:
        self._repository.require_ready_game(game_id)
        assets = self._repository.get_assets(
            game_id=game_id,
            cell_review_ids=cell_review_ids,
        )
        by_id = {asset.cell_review_id: asset for asset in assets}
        ordered: list[SymbolCellReviewAsset] = []
        for cell_review_id in cell_review_ids:
            asset = by_id.get(cell_review_id)
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
            if asset.asset_mode == "virtual_source" and (
                asset.source_geometry_revision_id != asset.current_source_geometry_revision_id
            ):
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_CROP_DRIFT",
                    "The virtual cell no longer belongs to the current source geometry revision.",
                )
            ordered.append(asset)
        return tuple(ordered)

    def _validate_expected_checksum(
        self,
        *,
        asset: SymbolCellReviewAsset,
        expected_crop_checksum_sha256: str,
    ) -> SymbolCellReviewAsset:
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
