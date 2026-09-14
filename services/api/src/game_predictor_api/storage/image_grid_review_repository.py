"""PostgreSQL repository for the game-wide grid validation queue."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import String, and_, case, exists, func, literal, or_, select, tuple_
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import ColumnElement

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
    ImageGridReviewSlotKind,
    ImageGridReviewSourceApprovalTarget,
    ImageGridReviewSourceAsset,
    ImageGridReviewState,
    ImageGridReviewView,
    ImageGridSourceApprovalResult,
)
from game_predictor_api.storage.image_review_repository import acquire_image_sequence_locks
from game_predictor_api.storage.image_symbol_review_repository import (
    SymbolCellReviewWriteThroughCoordinator,
    symbol_cell_review_projection_is_available,
)
from game_predictor_api.storage.models import (
    GameModel,
    ImageBoardGeometryPendingModel,
    ImageBoardSearchFastDocumentModel,
    ImageReviewItemModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    ImageSymbolReviewStateModel,
    RecognizedBoardModel,
    SourceImageModel,
)


def _confirmed_partial_expression() -> ColumnElement[bool]:
    """Classify persisted partials even after the proposal was accepted."""

    return or_(
        RecognizedBoardModel.completeness_status == "pending_partial",
        func.cardinality(RecognizedBoardModel.unavailable_cell_indices) > 0,
        RecognizedBoardModel.geometry_qualification.op("->>")("completenessStatus")
        == "pending_partial",
    )


def _pending_automatic_proposal_expression() -> ColumnElement[bool]:
    """A proposal is reviewable only when it also carries a four-corner grid."""

    geometry = ImageSourceGeometryRevisionModel.board_geometries.op("->")(
        ImageBoardGeometryPendingModel.position_index
    )
    proposal = geometry.op("->")("automaticPartialProposal")
    symbol_grid = geometry.op("->")("symbolGridQuad")
    symbol_grid_length = case(
        (
            func.jsonb_typeof(symbol_grid) == "array",
            func.jsonb_array_length(symbol_grid),
        ),
        else_=0,
    )
    return and_(
        func.jsonb_typeof(proposal) == "object",
        symbol_grid_length == 4,
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
        current_statement = self._visible_statement(review_filter=review_filter)
        pending_statement = self._pending_statement(review_filter=review_filter)
        sequence_number, review_item_key = _order_columns()
        pending_sequence, pending_key = _pending_order_columns()
        if before_key is not None:
            current_rows = self._session.execute(
                current_statement.where(_before_key(before_key))
                .order_by(sequence_number.desc(), review_item_key.desc())
                .limit(limit + 1)
            ).all()
            pending_rows = self._session.execute(
                pending_statement.where(_pending_before_key(before_key))
                .order_by(pending_sequence.desc(), pending_key.desc())
                .limit(limit + 1)
            ).all()
            candidates = sorted(
                (
                    *(_row_to_item(row) for row in current_rows),
                    *(_pending_row_to_item(row) for row in pending_rows),
                ),
                key=lambda item: item.cursor_key,
                reverse=True,
            )
            has_previous = len(candidates) > limit
            visible = tuple(reversed(candidates[:limit]))
            has_next = bool(visible)
        else:
            if after_key is not None:
                current_statement = current_statement.where(_after_key(after_key))
                pending_statement = pending_statement.where(_pending_after_key(after_key))
            current_rows = self._session.execute(
                current_statement.order_by(sequence_number, review_item_key).limit(limit + 1)
            ).all()
            pending_rows = self._session.execute(
                pending_statement.order_by(pending_sequence, pending_key).limit(limit + 1)
            ).all()
            candidates = sorted(
                (
                    *(_row_to_item(row) for row in current_rows),
                    *(_pending_row_to_item(row) for row in pending_rows),
                ),
                key=lambda item: item.cursor_key,
            )
            has_next = len(candidates) > limit
            visible = tuple(candidates[:limit])
            has_previous = after_key is not None and bool(visible)
        return ImageGridReviewListSlice(
            items=visible,
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
        pending_count = int(
            self._session.scalar(
                self._pending_statement(review_filter=unrestricted).with_only_columns(
                    func.count(ImageBoardGeometryPendingModel.id)
                )
            )
            or 0
        )
        automatic_proposal = _pending_automatic_proposal_expression()
        lateral_partial_proposals = int(
            self._session.scalar(
                self._pending_statement(review_filter=unrestricted)
                .with_only_columns(func.count(ImageBoardGeometryPendingModel.id))
                .where(automatic_proposal)
            )
            or 0
        )
        needs_validation = (
            counts.get(ImageGridReviewState.NEEDS_VALIDATION.value, 0)
            + lateral_partial_proposals
        )
        approved = counts.get(ImageGridReviewState.APPROVED.value, 0)
        needs_correction = (
            counts.get(ImageGridReviewState.NEEDS_CORRECTION.value, 0)
            + pending_count
            - lateral_partial_proposals
        )
        current_statement = self._visible_statement(review_filter=unrestricted)
        current_count = int(
            self._session.scalar(
                current_statement.with_only_columns(func.count(ImageReviewItemModel.id))
            )
            or 0
        )
        partial_expression = _confirmed_partial_expression()
        confirmed_partial_grids = int(
            self._session.scalar(
                current_statement.with_only_columns(func.count(ImageReviewItemModel.id)).where(
                    partial_expression
                )
            )
            or 0
        )
        return ImageGridReviewCounts(
            needs_validation=needs_validation,
            needs_correction=needs_correction,
            approved=approved,
            full_grids=max(0, current_count - confirmed_partial_grids),
            lateral_partial_proposals=lateral_partial_proposals,
            confirmed_partial_grids=confirmed_partial_grids,
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
            pending_row = self._session.execute(
                self._pending_statement(
                    review_filter=ImageGridReviewListFilter(
                        game_id=game_id,
                        view=ImageGridReviewView.ALL,
                        import_job_id=None,
                    )
                ).where(ImageBoardGeometryPendingModel.id == review_item_id)
            ).one_or_none()
            if pending_row is None:
                return None
            pending, source, _source_geometry = pending_row
            return ImageGridReviewSourceAsset(
                review_item_id=pending.id,
                source_image_id=source.id,
                source_relative_path=source.relative_path,
                source_checksum_sha256=source.checksum_sha256,
                source_width=source.oriented_width or source.width,
                source_height=source.oriented_height or source.height,
                geometry_revision=pending.expected_geometry_revision,
                resolution_revision=pending.expected_review_resolution_revision,
                topology=BoardTopology(rows=3, columns=5),
                asset_mode="virtual_source",
            )
        item, board, source, _sequence_number, _state = row
        return ImageGridReviewSourceAsset(
            review_item_id=item.id,
            source_image_id=source.id,
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

    def approve_source_grid_geometry(
        self,
        *,
        game_id: UUID,
        source_image_id: UUID,
        targets: tuple[ImageGridReviewSourceApprovalTarget, ...],
        actor: str,
    ) -> ImageGridSourceApprovalResult:
        """Approve every current slot of one source as one all-or-nothing command.

        The local reviewer deliberately hydrates all boards from one source image.
        Their revision identities are a single snapshot, so validating and
        mutating them one HTTP request at a time is inherently racy: the first
        decision can invalidate identities held by the remaining requests.
        Validate the complete source before invoking the coordinator for any
        board, then let the surrounding request transaction commit them together.
        """

        review_filter = ImageGridReviewListFilter(
            game_id=game_id,
            view=ImageGridReviewView.ALL,
            import_job_id=None,
            source_image_id=source_image_id,
        )
        rows = tuple(
            self._session.execute(
                self._visible_statement(review_filter=review_filter)
                .order_by(
                    RecognizedBoardModel.position_index,
                    ImageBoardSearchFastDocumentModel.sequence_number,
                    ImageReviewItemModel.id,
                )
                .with_for_update(
                    of=(
                        ImageReviewItemModel,
                        RecognizedBoardModel,
                        SourceImageModel,
                    )
                )
            ).all()
        )
        if not rows:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_SOURCE_NOT_FOUND",
                "The current grid-review source has no active board slots in this game.",
            )
        current_items = tuple(_row_to_item(row) for row in rows)
        expected_by_id = {target.review_item_id: target for target in targets}
        current_ids = {_require_current_review_item_id(item) for item in current_items}
        if set(expected_by_id) != current_ids:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_SOURCE_SLOT_CONFLICT",
                "The active board slots changed after this source image was loaded.",
            )
        for item in current_items:
            review_item_id = _require_current_review_item_id(item)
            target = expected_by_id[review_item_id]
            _require_source_target_identity(item, target)
            if item.state is ImageGridReviewState.NEEDS_CORRECTION:
                raise ImageGridReviewError(
                    "IMAGE_GRID_REVIEW_CORRECTION_REQUIRED",
                    "A source containing a current grid issue must be corrected before approval.",
                )

        acquire_image_sequence_locks(
            self._session,
            game_id=game_id,
            sequence_numbers=[item.sequence_number for item in current_items],
        )
        coordinator = SymbolCellReviewWriteThroughCoordinator(self._session)
        changed: list[UUID] = []
        for item in current_items:
            review_item_id = _require_current_review_item_id(item)
            if coordinator.approve_current_geometry(
                game_id=game_id,
                review_item_id=review_item_id,
                expected_geometry_revision=item.geometry_revision,
                actor=actor,
                approved_at=datetime.now(UTC),
            ):
                changed.append(review_item_id)
        self._session.flush()
        return ImageGridSourceApprovalResult(
            source_image_id=source_image_id,
            approved_review_item_ids=tuple(changed),
        )

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

    def _pending_statement(self, *, review_filter: ImageGridReviewListFilter) -> Select[Any]:
        latest_geometry_id = (
            select(ImageSourceGeometryRevisionModel.id)
            .where(
                ImageSourceGeometryRevisionModel.game_id == review_filter.game_id,
                ImageSourceGeometryRevisionModel.source_image_id
                == ImageBoardGeometryPendingModel.source_image_id,
            )
            .order_by(ImageSourceGeometryRevisionModel.revision.desc())
            .limit(1)
            .correlate(ImageBoardGeometryPendingModel)
            .scalar_subquery()
        )
        statement = (
            select(
                ImageBoardGeometryPendingModel,
                SourceImageModel,
                ImageSourceGeometryRevisionModel,
            )
            .join(
                SourceImageModel,
                SourceImageModel.id == ImageBoardGeometryPendingModel.source_image_id,
            )
            .join(
                ImageSourceGeometryRevisionModel,
                ImageSourceGeometryRevisionModel.id == latest_geometry_id,
            )
            .where(
                ImageBoardGeometryPendingModel.game_id == review_filter.game_id,
                ImageBoardGeometryPendingModel.status == "pending",
            )
        )
        if review_filter.import_job_id is not None:
            statement = statement.where(
                ImageBoardGeometryPendingModel.import_job_id == review_filter.import_job_id
            )
        if review_filter.source_image_id is not None:
            statement = statement.where(
                ImageBoardGeometryPendingModel.source_image_id == review_filter.source_image_id
            )
        automatic_proposal = _pending_automatic_proposal_expression()
        if review_filter.view is ImageGridReviewView.NEEDS_VALIDATION:
            statement = statement.where(automatic_proposal)
        elif review_filter.view is ImageGridReviewView.NEEDS_CORRECTION:
            statement = statement.where(~automatic_proposal)
        elif review_filter.view is not ImageGridReviewView.ALL:
            statement = statement.where(literal(False))
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
            cell.source_available.is_(True),
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


def _require_source_target_identity(
    item: ImageGridReviewListItem,
    target: ImageGridReviewSourceApprovalTarget,
) -> None:
    if item.resolution_revision != target.expected_resolution_revision:
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_REVISION_CONFLICT",
            "A board review item changed after the source was loaded.",
        )
    if item.geometry_revision != target.expected_geometry_revision:
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_GEOMETRY_REVISION_CONFLICT",
            "A board geometry changed after the source was loaded.",
        )
    if (
        item.source_checksum_sha256 != target.expected_source_checksum_sha256
        or item.source_width != target.expected_source_width
        or item.source_height != target.expected_source_height
    ):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_SOURCE_DRIFT",
            "The source image identity changed after the grid review was loaded.",
        )
    if (
        item.topology.rows != target.expected_grid_rows
        or item.topology.columns != target.expected_grid_columns
    ):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_TOPOLOGY_CONFLICT",
            "The board topology changed after the grid review was loaded.",
        )


def _row_to_item(row: Any) -> ImageGridReviewListItem:
    item, board, source, sequence_number, state = row
    return ImageGridReviewListItem(
        slot_id=item.id,
        slot_kind=ImageGridReviewSlotKind.CURRENT_REVIEW,
        review_item_id=item.id,
        game_id=item.game_id,
        import_job_id=item.import_job_id,
        recognized_board_id=board.id,
        pending_geometry_id=None,
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


def _require_current_review_item_id(item: ImageGridReviewListItem) -> UUID:
    if item.review_item_id is None:
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_SLOT_IDENTITY_INVALID",
            "A current grid-review item is missing its review identity.",
        )
    return item.review_item_id


def _pending_row_to_item(row: Any) -> ImageGridReviewListItem:
    pending, source, source_geometry = row
    position = int(pending.position_index)
    geometries = tuple(source_geometry.board_geometries or ())
    raw_geometry = geometries[position] if position < len(geometries) else {}
    geometry = dict(raw_geometry) if isinstance(raw_geometry, dict) else {}
    automatic_quad = _pending_automatic_quad(geometry)
    suggested = automatic_quad or _pending_suggested_quad(
        geometry,
        position_index=position,
        source_width=int(source.oriented_width or source.width),
        source_height=int(source.oriented_height or source.height),
    )
    geometry["manualGeometryRequired"] = automatic_quad is None
    geometry["sourceQuad"] = suggested
    if automatic_quad is None:
        geometry["manualTemplateQuad"] = suggested
    else:
        geometry.pop("manualTemplateQuad", None)
    reason_codes = (
        "IMAGE_GRID_REVIEW_DEFERRED_SLOT",
        str(pending.reason_code),
    )
    return ImageGridReviewListItem(
        slot_id=pending.id,
        slot_kind=ImageGridReviewSlotKind.DEFERRED_GEOMETRY,
        review_item_id=None,
        game_id=pending.game_id,
        import_job_id=pending.import_job_id,
        recognized_board_id=None,
        pending_geometry_id=pending.id,
        source_image_id=pending.source_image_id,
        position_index=position,
        sequence_number=int(pending.sequence_number),
        source_checksum_sha256=source.checksum_sha256,
        source_width=int(source.oriented_width or source.width),
        source_height=int(source.oriented_height or source.height),
        geometry_revision=int(pending.expected_geometry_revision),
        approved_geometry_revision=None,
        resolution_revision=int(pending.expected_review_resolution_revision),
        topology=BoardTopology(rows=3, columns=5),
        geometry=geometry,
        asset_mode="virtual_source",
        geometry_engine_name=str(source_geometry.engine_kind),
        geometry_engine_version=str(source_geometry.engine_version),
        board_confidence=0.0,
        reason_codes=reason_codes,
        state=(
            ImageGridReviewState.NEEDS_VALIDATION
            if automatic_quad is not None
            else ImageGridReviewState.NEEDS_CORRECTION
        ),
    )


def _pending_automatic_quad(geometry: dict[str, object]) -> list[dict[str, int]] | None:
    if not isinstance(geometry.get("automaticPartialProposal"), dict):
        return None
    value = geometry.get("symbolGridQuad")
    if (
        not isinstance(value, list | tuple)
        or len(value) != 4
        or not all(
            isinstance(point, dict)
            and type(point.get("x")) in {int, float}
            and type(point.get("y")) in {int, float}
            and math.isfinite(float(point["x"]))
            and math.isfinite(float(point["y"]))
            for point in value
        )
    ):
        return None
    return [
        {"x": round(float(point["x"])), "y": round(float(point["y"]))}
        for point in value
    ]


def _pending_suggested_quad(
    geometry: dict[str, object],
    *,
    position_index: int,
    source_width: int,
    source_height: int,
) -> list[dict[str, int]]:
    for key in ("symbolGridQuad", "finalQuad", "analysisQuad", "initialQuad", "quad"):
        value = geometry.get(key)
        if (
            isinstance(value, list | tuple)
            and len(value) == 4
            and all(
                isinstance(point, dict)
                and isinstance(point.get("x"), int | float)
                and isinstance(point.get("y"), int | float)
                for point in value
            )
        ):
            return [
                {"x": round(float(point["x"])), "y": round(float(point["y"]))} for point in value
            ]
    row, column = divmod(position_index, 3)
    left = round(source_width * (0.08 + column * 0.29))
    right = round(source_width * (0.34 + column * 0.29))
    top = round(source_height * (0.20 + row * 0.23))
    bottom = round(source_height * (0.39 + row * 0.23))
    return [
        {"x": left, "y": top},
        {"x": min(source_width - 1, right), "y": top},
        {"x": min(source_width - 1, right), "y": min(source_height - 1, bottom)},
        {"x": left, "y": min(source_height - 1, bottom)},
    ]


def _pending_order_columns() -> tuple[Any, Any]:
    return (
        ImageBoardGeometryPendingModel.sequence_number,
        ImageBoardGeometryPendingModel.id.cast(String),
    )


def _pending_after_key(key: tuple[int, str]) -> Any:
    return tuple_(*_pending_order_columns()) > tuple_(literal(key[0]), literal(key[1]))


def _pending_before_key(key: tuple[int, str]) -> Any:
    return tuple_(*_pending_order_columns()) < tuple_(literal(key[0]), literal(key[1]))


def _reason_codes(geometry: dict[str, object]) -> tuple[str, ...]:
    raw = geometry.get("reasonCodes")
    if not isinstance(raw, list):
        return ()
    return tuple(value for value in raw if isinstance(value, str) and value)


__all__ = ["SqlAlchemyImageGridReviewRepository"]
