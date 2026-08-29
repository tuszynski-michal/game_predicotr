"""PostgreSQL repository for the game-wide grid validation queue."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import String, and_, case, exists, func, literal, select, tuple_
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from game_predictor_api.application.image_grid_reviews import (
    ImageGridReviewListSlice,
    ImageGridReviewRepository,
)
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_grid_reviews import (
    ImageGridApprovalResult,
    ImageGridReviewCounts,
    ImageGridReviewError,
    ImageGridReviewListFilter,
    ImageGridReviewListItem,
    ImageGridReviewSourceAsset,
    ImageGridReviewState,
    ImageGridReviewView,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SymbolCellReviewWriteThroughCoordinator,
    symbol_cell_review_projection_is_available,
)
from game_predictor_api.storage.models import (
    GameModel,
    ImageBoardSearchFastDocumentModel,
    ImageReviewItemModel,
    ImageSymbolReviewCellModel,
    ImageSymbolReviewStateModel,
    RecognizedBoardModel,
    SourceImageModel,
)


class SqlAlchemyImageGridReviewRepository(ImageGridReviewRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def require_game(self, game_id: UUID) -> None:
        if self._session.get(GameModel, game_id) is None:
            raise ImageGridReviewError("GAME_NOT_FOUND", "The selected game does not exist.")
        state = self._session.get(ImageSymbolReviewStateModel, game_id)
        if not symbol_cell_review_projection_is_available(
            self._session,
            game_id=game_id,
            state=state,
        ):
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_PROJECTION_INCOMPLETE",
                "The current symbol-cell projection is not ready for grid validation.",
            )

    def list_grid_reviews(
        self,
        *,
        review_filter: ImageGridReviewListFilter,
        after_key: tuple[int, str] | None,
        before_key: tuple[int, str] | None,
        limit: int,
    ) -> ImageGridReviewListSlice:
        if after_key is not None and before_key is not None:
            raise ValueError("only one grid review keyset direction is allowed")
        statement = self._visible_statement(review_filter=review_filter)
        sequence_number, review_item_key = _order_columns()
        if before_key is not None:
            rows = self._session.execute(
                statement.where(_before_key(before_key))
                .order_by(sequence_number.desc(), review_item_key.desc())
                .limit(limit + 1)
            ).all()
            has_previous = len(rows) > limit
            visible = tuple(reversed(rows[:limit]))
            has_next = bool(visible) and self._has_after(
                review_filter=review_filter,
                key=_row_to_item(visible[-1]).cursor_key,
            )
        else:
            if after_key is not None:
                statement = statement.where(_after_key(after_key))
            rows = self._session.execute(
                statement.order_by(sequence_number, review_item_key).limit(limit + 1)
            ).all()
            has_next = len(rows) > limit
            visible = tuple(rows[:limit])
            has_previous = bool(visible) and self._has_before(
                review_filter=review_filter,
                key=_row_to_item(visible[0]).cursor_key,
            )
        return ImageGridReviewListSlice(
            items=tuple(_row_to_item(row) for row in visible),
            has_previous=has_previous,
            has_next=has_next,
        )

    def grid_review_counts(
        self,
        *,
        review_filter: ImageGridReviewListFilter,
    ) -> ImageGridReviewCounts:
        unrestricted = ImageGridReviewListFilter(
            game_id=review_filter.game_id,
            view=ImageGridReviewView.ALL,
            import_job_id=review_filter.import_job_id,
            source_image_id=review_filter.source_image_id,
        )
        state_expression = _state_expression()
        rows = self._session.execute(
            self._visible_statement(review_filter=unrestricted)
            .with_only_columns(state_expression, func.count(ImageReviewItemModel.id))
            .group_by(state_expression)
        ).all()
        counts = {str(state): int(count) for state, count in rows}
        return ImageGridReviewCounts(
            needs_validation=counts.get(ImageGridReviewState.NEEDS_VALIDATION.value, 0),
            needs_correction=counts.get(ImageGridReviewState.NEEDS_CORRECTION.value, 0),
            approved=counts.get(ImageGridReviewState.APPROVED.value, 0),
        )

    def get_grid_review_source_asset(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
    ) -> ImageGridReviewSourceAsset | None:
        row = self._session.execute(
            self._visible_statement(
                review_filter=ImageGridReviewListFilter(
                    game_id=game_id,
                    view=ImageGridReviewView.ALL,
                    import_job_id=None,
                )
            ).where(ImageReviewItemModel.id == review_item_id)
        ).one_or_none()
        if row is None:
            return None
        item, board, source, _sequence_number, _state = row
        return ImageGridReviewSourceAsset(
            review_item_id=item.id,
            source_relative_path=source.relative_path,
            source_checksum_sha256=source.checksum_sha256,
            source_width=source.oriented_width or source.width,
            source_height=source.oriented_height or source.height,
            geometry_revision=board.geometry_revision,
            resolution_revision=item.resolution_revision,
            topology=_topology(board),
            asset_mode=board.asset_mode,
        )

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
    ) -> ImageGridApprovalResult:
        row = self._session.execute(
            self._visible_statement(
                review_filter=ImageGridReviewListFilter(
                    game_id=game_id,
                    view=ImageGridReviewView.ALL,
                    import_job_id=None,
                )
            )
            .where(ImageReviewItemModel.id == review_item_id)
            .with_for_update(of=(ImageReviewItemModel, RecognizedBoardModel, SourceImageModel))
        ).one_or_none()
        if row is None:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_ITEM_NOT_FOUND",
                "The current grid review item does not exist in this game scope.",
            )
        item, board, source, _sequence_number, _state = row
        topology = _topology(board)
        if item.resolution_revision != expected_resolution_revision:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_REVISION_CONFLICT",
                "The review item changed after it was loaded.",
            )
        if board.geometry_revision != expected_geometry_revision:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_GEOMETRY_REVISION_CONFLICT",
                "The board geometry changed after it was loaded.",
            )
        if (
            source.checksum_sha256 != expected_source_checksum_sha256
            or (source.oriented_width or source.width) != expected_source_width
            or (source.oriented_height or source.height) != expected_source_height
        ):
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_SOURCE_DRIFT",
                "The source image identity changed after the grid review was loaded.",
            )
        if topology != BoardTopology(rows=expected_grid_rows, columns=expected_grid_columns):
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_TOPOLOGY_CONFLICT",
                "The board topology changed after the grid review was loaded.",
            )
        changed = SymbolCellReviewWriteThroughCoordinator(self._session).approve_current_geometry(
            game_id=game_id,
            review_item_id=review_item_id,
            expected_geometry_revision=expected_geometry_revision,
            actor=actor,
            approved_at=datetime.now(UTC),
        )
        self._session.flush()
        refreshed = self._session.execute(
            self._visible_statement(
                review_filter=ImageGridReviewListFilter(
                    game_id=game_id,
                    view=ImageGridReviewView.ALL,
                    import_job_id=None,
                )
            ).where(ImageReviewItemModel.id == review_item_id)
        ).one_or_none()
        if refreshed is None:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_CURRENT_OWNER_CONFLICT",
                "The board stopped being the current sequence owner during approval.",
            )
        return ImageGridApprovalResult(item=_row_to_item(refreshed), changed=changed)

    def _visible_statement(self, *, review_filter: ImageGridReviewListFilter) -> Select[Any]:
        document = ImageBoardSearchFastDocumentModel
        state_expression = _state_expression()
        statement = (
            select(
                ImageReviewItemModel,
                RecognizedBoardModel,
                SourceImageModel,
                document.sequence_number,
                state_expression,
            )
            .join(document, document.review_item_id == ImageReviewItemModel.id)
            .join(
                RecognizedBoardModel,
                and_(
                    RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
                    RecognizedBoardModel.id == document.recognized_board_id,
                ),
            )
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .where(
                document.game_id == review_filter.game_id,
                ImageReviewItemModel.game_id == review_filter.game_id,
                ImageReviewItemModel.status.in_(("pending", "accepted", "corrected")),
            )
        )
        if review_filter.import_job_id is not None:
            statement = statement.where(document.import_job_id == review_filter.import_job_id)
        if review_filter.source_image_id is not None:
            statement = statement.where(
                RecognizedBoardModel.source_image_id == review_filter.source_image_id
            )
        if review_filter.view is not ImageGridReviewView.ALL:
            statement = statement.where(state_expression == review_filter.view.value)
        return statement

    def _has_after(
        self,
        *,
        review_filter: ImageGridReviewListFilter,
        key: tuple[int, str],
    ) -> bool:
        return (
            self._session.execute(
                self._visible_statement(review_filter=review_filter)
                .with_only_columns(ImageReviewItemModel.id)
                .where(_after_key(key))
                .limit(1)
            ).first()
            is not None
        )

    def _has_before(
        self,
        *,
        review_filter: ImageGridReviewListFilter,
        key: tuple[int, str],
    ) -> bool:
        return (
            self._session.execute(
                self._visible_statement(review_filter=review_filter)
                .with_only_columns(ImageReviewItemModel.id)
                .where(_before_key(key))
                .limit(1)
            ).first()
            is not None
        )


def _current_grid_issue_exists() -> Any:
    cell = ImageSymbolReviewCellModel
    return exists(
        select(cell.id).where(
            cell.review_item_id == ImageReviewItemModel.id,
            cell.recognized_board_id == RecognizedBoardModel.id,
            cell.geometry_revision == RecognizedBoardModel.geometry_revision,
            cell.quality_issue == "grid_issue",
        )
    )


def _state_expression() -> Any:
    return case(
        (_current_grid_issue_exists(), ImageGridReviewState.NEEDS_CORRECTION.value),
        (
            RecognizedBoardModel.approved_geometry_revision
            == RecognizedBoardModel.geometry_revision,
            ImageGridReviewState.APPROVED.value,
        ),
        else_=ImageGridReviewState.NEEDS_VALIDATION.value,
    )


def _order_columns() -> tuple[Any, Any]:
    return (
        ImageBoardSearchFastDocumentModel.sequence_number,
        ImageReviewItemModel.id.cast(String),
    )


def _after_key(key: tuple[int, str]) -> Any:
    return tuple_(*_order_columns()) > tuple_(literal(key[0]), literal(key[1]))


def _before_key(key: tuple[int, str]) -> Any:
    return tuple_(*_order_columns()) < tuple_(literal(key[0]), literal(key[1]))


def _topology(board: RecognizedBoardModel) -> BoardTopology:
    return BoardTopology(rows=board.grid_rows or 3, columns=board.grid_columns or 5)


def _row_to_item(row: Any) -> ImageGridReviewListItem:
    item, board, source, sequence_number, state = row
    return ImageGridReviewListItem(
        review_item_id=item.id,
        game_id=item.game_id,
        import_job_id=item.import_job_id,
        recognized_board_id=board.id,
        source_image_id=board.source_image_id,
        position_index=board.position_index,
        sequence_number=int(sequence_number),
        source_checksum_sha256=source.checksum_sha256,
        source_width=source.oriented_width or source.width,
        source_height=source.oriented_height or source.height,
        geometry_revision=board.geometry_revision,
        approved_geometry_revision=board.approved_geometry_revision,
        resolution_revision=item.resolution_revision,
        topology=_topology(board),
        geometry=dict(board.board_geometry),
        asset_mode=board.asset_mode,
        geometry_engine_name=board.geometry_engine_name,
        geometry_engine_version=board.geometry_engine_version,
        board_confidence=board.board_confidence,
        reason_codes=_reason_codes(board.board_geometry),
        state=ImageGridReviewState(str(state)),
    )


def _reason_codes(geometry: dict[str, object]) -> tuple[str, ...]:
    raw = geometry.get("reasonCodes")
    if not isinstance(raw, list):
        return ()
    return tuple(value for value in raw if isinstance(value, str) and value)


__all__ = ["SqlAlchemyImageGridReviewRepository"]
