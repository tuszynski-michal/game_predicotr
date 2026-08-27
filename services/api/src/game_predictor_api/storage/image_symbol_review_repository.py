"""Persistence and resumable backfill for checksum-bound symbol-cell review."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import String, and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql import ColumnElement, Select

from game_predictor_api.application.image_reviews import OperationalImageReviewService
from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationCommand,
    SymbolCellReviewMutationRepository,
    SymbolCellReviewMutationResult,
)
from game_predictor_api.application.image_symbol_reviews import (
    SymbolCellReviewListSlice,
    SymbolCellReviewQueryRepository,
)
from game_predictor_api.domain.catalog import SymbolStatus
from game_predictor_api.domain.image_reviews import (
    ImageReviewAction,
    ImageReviewCell,
    ImageReviewResolutionCell,
    canonical_image_review_bytes,
)
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellAssignmentSource,
    SymbolCellCropIdentity,
    SymbolCellReview,
    SymbolCellReviewAction,
    SymbolCellReviewAsset,
    SymbolCellReviewCounts,
    SymbolCellReviewError,
    SymbolCellReviewFilterState,
    SymbolCellReviewListFilter,
    SymbolCellReviewListItem,
    SymbolCellReviewState,
    SymbolCellReviewTransition,
    approve_symbol_cell_review,
    derive_symbol_cell_board_resolution,
    map_current_symbol_cell_reviews,
    mark_symbol_cell_grid_issue,
    reassign_symbol_cell_review,
)
from game_predictor_api.storage.models import (
    CellObservationModel,
    GameModel,
    ImageBoardGeometryRevisionModel,
    ImageBoardSearchFastDocumentModel,
    ImageReviewItemModel,
    ImageReviewQueueItemModel,
    ImageSymbolPredictionRevisionModel,
    ImageSymbolReviewCellModel,
    ImageSymbolReviewEventModel,
    ImageSymbolReviewStateModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
    SymbolModel,
)

_ACTIVE_REVIEW_STATUSES = frozenset({"pending", "accepted", "corrected"})
_DEFAULT_BATCH_SIZE = 200
_BACKFILL_ACTOR = "system:symbol-cell-backfill"
_WRITE_THROUGH_ACTOR = "system:symbol-cell-write-through"
_CELL_REVIEW_TRANSACTION_MARKER = "symbol_cell_review_catalog_revision_transaction"

BackfillRow = tuple[
    ImageBoardSearchFastDocumentModel,
    ImageReviewItemModel,
    RecognizedBoardModel,
    SourceImageModel,
    ImageReviewQueueItemModel,
    JobModel,
]


class SymbolCellReviewBackfillError(RuntimeError):
    """Controlled integrity failure preventing a game from becoming ready."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        review_item_ids: Sequence[UUID] = (),
        invalid_crop_count: int = 0,
        invalid_geometry_count: int = 0,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.review_item_ids = tuple(review_item_ids)
        self.invalid_crop_count = invalid_crop_count
        self.invalid_geometry_count = invalid_geometry_count


@dataclass(frozen=True, slots=True)
class SymbolCellReviewBackfillReport:
    game_id: UUID
    status: str
    catalog_revision: int
    processed_review_item_count: int
    cell_count: int
    missing_sequence_count: int
    invalid_crop_count: int
    invalid_geometry_count: int
    failure_message: str | None
    sample_problem_review_item_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class SymbolCellReviewBackfillStep:
    report: SymbolCellReviewBackfillReport
    processed_review_item_count: int
    has_more: bool


class SqlAlchemySymbolCellReviewQueryRepository(SymbolCellReviewQueryRepository):
    """Bounded current-owner reads for the future local Admin workspace.

    The table can contain historical rows for superseded review items.  Every
    read therefore joins the narrow fast-document projection, which is the
    deterministic current owner of one logical ``game + sequence``.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def require_ready_game(self, game_id: UUID) -> int:
        if self._session.get(GameModel, game_id) is None:
            raise SymbolCellReviewError(
                "GAME_NOT_FOUND",
                "The selected game does not exist.",
                details={"gameId": str(game_id)},
            )
        state = self._session.get(ImageSymbolReviewStateModel, game_id)
        if state is None or state.status != "ready":
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_PROJECTION_INCOMPLETE",
                "The symbol-cell review projection is not ready for this game.",
                details={
                    "status": None if state is None else state.status,
                    "gameId": str(game_id),
                },
            )
        return int(state.catalog_revision)

    def list_items(
        self,
        *,
        review_filter: SymbolCellReviewListFilter,
        after_key: tuple[int, int, str] | None,
        before_key: tuple[int, int, str] | None,
        limit: int,
    ) -> SymbolCellReviewListSlice:
        if after_key is not None and before_key is not None:
            raise ValueError("only one symbol-cell review keyset direction is allowed")
        statement = self._list_statement(review_filter=review_filter)
        sequence, cell_index, review_item_key = _symbol_cell_review_order_columns()
        if before_key is not None:
            rows = self._session.execute(
                statement.where(_symbol_cell_review_before_key(before_key))
                .order_by(sequence.desc(), cell_index.desc(), review_item_key.desc())
                .limit(limit + 1)
            ).all()
            has_previous = len(rows) > limit
            visible = tuple(reversed(rows[:limit]))
            has_next = bool(visible) and self._has_item_after(
                review_filter=review_filter,
                key=_row_to_list_item(visible[-1]).cursor_key,
            )
        else:
            if after_key is not None:
                statement = statement.where(_symbol_cell_review_after_key(after_key))
            rows = self._session.execute(
                statement.order_by(sequence, cell_index, review_item_key).limit(limit + 1)
            ).all()
            has_next = len(rows) > limit
            visible = tuple(rows[:limit])
            has_previous = bool(visible) and self._has_item_before(
                review_filter=review_filter,
                key=_row_to_list_item(visible[0]).cursor_key,
            )
        return SymbolCellReviewListSlice(
            items=tuple(_row_to_list_item(row) for row in visible),
            has_previous=has_previous,
            has_next=has_next,
        )

    def counts(self, *, review_filter: SymbolCellReviewListFilter) -> SymbolCellReviewCounts:
        cell = ImageSymbolReviewCellModel
        rows = self._session.execute(
            self._visible_statement(review_filter=review_filter)
            .with_only_columns(cell.review_state, func.count(cell.id))
            .group_by(cell.review_state)
        ).all()
        by_state = {str(state): int(count) for state, count in rows}
        approved_count = by_state.get(SymbolCellReviewState.APPROVED.value, 0)
        pending_count = by_state.get(SymbolCellReviewState.PENDING.value, 0)
        return SymbolCellReviewCounts(
            all_count=approved_count + pending_count,
            approved_count=approved_count,
            pending_count=pending_count,
        )

    def get_asset(
        self,
        *,
        game_id: UUID,
        cell_review_id: UUID,
    ) -> SymbolCellReviewAsset | None:
        cell = ImageSymbolReviewCellModel
        document = ImageBoardSearchFastDocumentModel
        row = self._session.execute(
            select(cell, RecognizedBoardModel.geometry_revision)
            .join(
                document,
                and_(
                    document.game_id == cell.game_id,
                    document.sequence_number == cell.sequence_number,
                    document.review_item_id == cell.review_item_id,
                    document.recognized_board_id == cell.recognized_board_id,
                    document.import_job_id == cell.import_job_id,
                ),
            )
            .join(RecognizedBoardModel, RecognizedBoardModel.id == cell.recognized_board_id)
            .where(cell.game_id == game_id, cell.id == cell_review_id)
        ).one_or_none()
        if row is None:
            return None
        review_cell, current_geometry_revision = row
        return SymbolCellReviewAsset(
            cell_review_id=review_cell.id,
            crop_relative_path=review_cell.crop_relative_path,
            crop_checksum_sha256=review_cell.crop_checksum_sha256,
            geometry_revision=review_cell.geometry_revision,
            current_geometry_revision=int(current_geometry_revision),
        )

    def _list_statement(
        self, *, review_filter: SymbolCellReviewListFilter
    ) -> Select[Any]:
        cell = ImageSymbolReviewCellModel
        assigned_symbol = aliased(SymbolModel)
        return self._visible_statement(review_filter=review_filter).add_columns(
            ImageBoardSearchFastDocumentModel.status.label("board_status"),
            assigned_symbol.id.label("assigned_symbol_id"),
            assigned_symbol.code.label("assigned_symbol_code"),
            assigned_symbol.name.label("assigned_symbol_name"),
        ).outerjoin(assigned_symbol, assigned_symbol.id == cell.assigned_symbol_id)

    def _visible_statement(
        self, *, review_filter: SymbolCellReviewListFilter
    ) -> Select[Any]:
        cell = ImageSymbolReviewCellModel
        document = ImageBoardSearchFastDocumentModel
        statement = (
            select(cell)
            .join(
                document,
                and_(
                    document.game_id == cell.game_id,
                    document.sequence_number == cell.sequence_number,
                    document.review_item_id == cell.review_item_id,
                    document.recognized_board_id == cell.recognized_board_id,
                    document.import_job_id == cell.import_job_id,
                ),
            )
            .join(RecognizedBoardModel, RecognizedBoardModel.id == cell.recognized_board_id)
            .where(
                cell.game_id == review_filter.game_id,
                cell.geometry_revision == RecognizedBoardModel.geometry_revision,
            )
        )
        if review_filter.symbol_id is None:
            statement = statement.where(cell.assigned_symbol_id.is_(None))
        else:
            statement = statement.where(cell.assigned_symbol_id == review_filter.symbol_id)
        if review_filter.state is not SymbolCellReviewFilterState.ALL:
            statement = statement.where(cell.review_state == review_filter.state.value)
        return statement

    def _has_item_after(
        self,
        *,
        review_filter: SymbolCellReviewListFilter,
        key: tuple[int, int, str],
    ) -> bool:
        return (
            self._session.execute(
                self._visible_statement(review_filter=review_filter)
                .with_only_columns(ImageSymbolReviewCellModel.id)
                .where(_symbol_cell_review_after_key(key))
                .limit(1)
            ).first()
            is not None
        )

    def _has_item_before(
        self,
        *,
        review_filter: SymbolCellReviewListFilter,
        key: tuple[int, int, str],
    ) -> bool:
        return (
            self._session.execute(
                self._visible_statement(review_filter=review_filter)
                .with_only_columns(ImageSymbolReviewCellModel.id)
                .where(_symbol_cell_review_before_key(key))
                .limit(1)
            ).first()
            is not None
        )


class SqlAlchemySymbolCellReviewMutationRepository(SymbolCellReviewMutationRepository):
    """Apply checksum-bound crop decisions and reconcile one parent board once."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def apply_mutation(
        self,
        command: SymbolCellReviewMutationCommand,
    ) -> SymbolCellReviewMutationResult:
        return self.apply_board_mutations((command,))[0]

    def apply_board_mutations(
        self,
        commands: tuple[SymbolCellReviewMutationCommand, ...],
    ) -> tuple[SymbolCellReviewMutationResult, ...]:
        """Apply a frozen set of crops from one board without intermediate closure.

        A grid-issue command can remove canonical ownership.  Therefore a
        durable batch may not call the single-crop command repeatedly: it must
        update all requested cells and aggregate/reopen the parent only once.
        """

        if not commands:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_BULK_BOARD_EMPTY",
                "A bulk board mutation needs at least one crop command.",
            )
        game_id = commands[0].game_id
        if any(command.game_id != game_id for command in commands):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_BULK_BOARD_SCOPE_INVALID",
                "All crop commands in one board batch must belong to the same game.",
            )
        if len({command.cell_review_id for command in commands}) != len(commands):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_BULK_BOARD_DUPLICATE",
                "A board batch cannot contain the same crop more than once.",
            )
        if len({(command.action, command.target_symbol_id) for command in commands}) != 1:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_BULK_BOARD_COMMAND_MISMATCH",
                "A durable board batch must use one action and one target symbol.",
            )

        # This remains a local import because the operational Reviewer imports
        # the write-through coordinator from this module.
        from game_predictor_api.storage.image_review_repository import (
            SqlAlchemyOperationalImageReviewRepository,
        )

        state = self._require_ready_state(game_id)
        probes = self._probe_board_cells(commands)
        review_item_ids = {probe.review_item_id for probe in probes}
        sequence_numbers = {probe.sequence_number for probe in probes}
        if len(review_item_ids) != 1 or len(sequence_numbers) != 1:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_BULK_BOARD_SCOPE_INVALID",
                "A durable board batch cannot span more than one current board.",
            )
        review_item_id = next(iter(review_item_ids))
        sequence_number = int(next(iter(sequence_numbers)))
        self._acquire_board_locks(
            game_id=game_id,
            review_item_id=review_item_id,
            sequence_number=sequence_number,
        )
        # Lock rows again after advisory locks; their current owner may have
        # changed while the deterministic sequence lock was being acquired.
        rows = self._locked_current_rows(commands)
        row_by_cell_id = {row[0].id: row for row in rows}
        if set(row_by_cell_id) != {command.cell_review_id for command in commands}:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_CURRENT_OWNER_CONFLICT",
                "A crop changed before the durable board batch acquired its lock.",
            )
        item = rows[0][1]
        board = rows[0][2]
        source = rows[0][3]
        if (
            item.id != review_item_id
            or any(row[0].sequence_number != sequence_number for row in rows)
            or any(
                row[1].id != item.id or row[2].id != board.id or row[3].id != source.id
                for row in rows
            )
        ):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_CURRENT_OWNER_CONFLICT",
                "The current board changed while the durable batch was being locked.",
            )

        symbol_codes, symbol_ids = self._active_symbols(game_id)
        changed_by_cell_id: dict[UUID, bool] = {}
        for command in commands:
            cell = row_by_cell_id[command.cell_review_id][0]
            self._require_expected_identity(cell, command)
            current = _symbol_cell_review_from_model(cell, symbol_code_by_id=symbol_codes)
            transition = _apply_symbol_cell_command(
                command=command,
                review=current,
                active_symbol_codes=tuple(symbol_codes.values()),
                symbol_code_by_id=symbol_codes,
            )
            changed_by_cell_id[cell.id] = transition.changed
            if transition.changed:
                previous = _CellPreviousState.from_model(cell)
                _apply_symbol_cell_review_transition(
                    cell,
                    review=transition.review,
                    symbol_id_by_code=symbol_ids,
                    actor=command.actor.strip(),
                )
                _append_symbol_cell_event(
                    self._session,
                    cell=cell,
                    previous=previous,
                    action=command.action.value,
                    actor=command.actor.strip(),
                    operation_id=command.operation_id,
                )
        self._session.flush()

        current_board_reviews = self._locked_current_board_reviews(
            game_id=game_id,
            review_item_id=item.id,
            recognized_board_id=board.id,
            sequence_number=sequence_number,
            geometry_revision=board.geometry_revision,
            symbol_code_by_id=symbol_codes,
        )
        board_resolution = derive_symbol_cell_board_resolution(
            reviews=current_board_reviews,
            active_symbol_codes=tuple(symbol_codes.values()),
        )
        any_changed = any(changed_by_cell_id.values())
        board_reopened = False
        board_resolution_action: str | None = None
        board_status = item.status
        reopen_command = next(
            (
                command
                for command in commands
                if command.action is SymbolCellReviewAction.MARK_GRID_ISSUE
                and changed_by_cell_id[command.cell_review_id]
            ),
            None,
        )
        if reopen_command is not None and item.status in {"accepted", "corrected"}:
            updated, board_reopened = SqlAlchemyOperationalImageReviewRepository(
                self._session
            ).reopen_for_symbol_cell_grid_issue(
                review_item_id=item.id,
                game_id=game_id,
                import_job_id=source.import_job_id,
                idempotency_key=uuid4(),
                command_sha256=_symbol_cell_mutation_checksum(reopen_command),
                reopened_by=reopen_command.actor.strip(),
                reopened_at=datetime.now(UTC),
            )
            board_status = updated.status
        elif board_resolution is not None and (any_changed or item.status == "pending"):
            review_item = SqlAlchemyOperationalImageReviewRepository(self._session).get_item(
                item.id,
                game_id=game_id,
                import_job_id=source.import_job_id,
                for_update=True,
            )
            if review_item is None:
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_CURRENT_OWNER_CONFLICT",
                    "The parent board changed before the crop decisions could be aggregated.",
                )
            aggregate_action = board_resolution.action
            if (
                aggregate_action is ImageReviewAction.ACCEPTED
                and review_item.suggested_sequence_number != sequence_number
            ):
                aggregate_action = ImageReviewAction.CORRECTED
            cells = tuple(
                ImageReviewResolutionCell(
                    cell_index=review.cell_index,
                    crop_sample_id=review.crop.crop_sample_id,
                    symbol_code=review.assigned_symbol_code or "",
                )
                for review in current_board_reviews
            )
            updated, _event, _created = OperationalImageReviewService(
                SqlAlchemyOperationalImageReviewRepository(self._session)
            ).resolve_item(
                item.id,
                game_id=game_id,
                import_job_id=source.import_job_id,
                idempotency_key=uuid4(),
                expected_revision=review_item.resolution_revision,
                action=aggregate_action,
                sequence_number=sequence_number,
                geometry_revision=review_item.geometry_revision,
                cells=cells,
                rejection_reason=None,
                resolved_by=commands[0].actor.strip(),
            )
            board_status = updated.status
            board_resolution_action = aggregate_action.value

        coordinator = SymbolCellReviewWriteThroughCoordinator(self._session)
        if not coordinator.synchronize_after_cell_mutation(game_id=game_id):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_PROJECTION_INCOMPLETE",
                "The symbol-cell review projection is not ready for this game.",
            )
        self._session.flush()
        return tuple(
            SymbolCellReviewMutationResult(
                cell_review_id=command.cell_review_id,
                review_item_id=item.id,
                sequence_number=sequence_number,
                cell_revision=int(row_by_cell_id[command.cell_review_id][0].revision),
                review_state=SymbolCellReviewState(
                    row_by_cell_id[command.cell_review_id][0].review_state
                ),
                assigned_symbol_id=row_by_cell_id[command.cell_review_id][0].assigned_symbol_id,
                has_grid_issue=bool(row_by_cell_id[command.cell_review_id][0].has_grid_issue),
                board_status=board_status,
                board_resolution_action=board_resolution_action,
                board_reopened=board_reopened,
                catalog_revision=int(state.catalog_revision),
            )
            for command in commands
        )

    def _require_ready_state(self, game_id: UUID) -> ImageSymbolReviewStateModel:
        if self._session.get(GameModel, game_id) is None:
            raise SymbolCellReviewError(
                "GAME_NOT_FOUND",
                "The selected game does not exist.",
                details={"gameId": str(game_id)},
            )
        state = self._session.get(ImageSymbolReviewStateModel, game_id, with_for_update=True)
        if state is None or state.status != "ready":
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_PROJECTION_INCOMPLETE",
                "The symbol-cell review projection is not ready for this game.",
                details={"status": None if state is None else state.status},
            )
        return state

    def _probe_board_cells(
        self,
        commands: tuple[SymbolCellReviewMutationCommand, ...],
    ) -> tuple[ImageSymbolReviewCellModel, ...]:
        cell_ids = tuple(command.cell_review_id for command in commands)
        rows = tuple(
            self._session.scalars(
                select(ImageSymbolReviewCellModel).where(
                    ImageSymbolReviewCellModel.id.in_(cell_ids),
                    ImageSymbolReviewCellModel.game_id == commands[0].game_id,
                )
            )
        )
        if len(rows) != len(cell_ids):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_CELL_NOT_FOUND",
                "The symbol-cell review crop does not exist in this game.",
            )
        return rows

    def _acquire_board_locks(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
        sequence_number: int,
    ) -> None:
        # Keep the existing order: sequence advisory locks, then the parent
        # review item and finally the individual crop rows.
        from game_predictor_api.storage.image_review_repository import (
            acquire_image_review_sequence_locks,
        )

        acquire_image_review_sequence_locks(
            self._session,
            game_id=game_id,
            review_item_id=review_item_id,
            requested_sequence_number=sequence_number,
        )

    def _locked_current_rows(
        self,
        commands: tuple[SymbolCellReviewMutationCommand, ...],
    ) -> tuple[
        tuple[
            ImageSymbolReviewCellModel,
            ImageReviewItemModel,
            RecognizedBoardModel,
            SourceImageModel,
        ],
        ...,
    ]:
        command = commands[0]
        cell_ids = tuple(command.cell_review_id for command in commands)
        cell = ImageSymbolReviewCellModel
        document = ImageBoardSearchFastDocumentModel
        rows = self._session.execute(
            select(cell, ImageReviewItemModel, RecognizedBoardModel, SourceImageModel)
            .join(
                document,
                and_(
                    document.game_id == cell.game_id,
                    document.sequence_number == cell.sequence_number,
                    document.review_item_id == cell.review_item_id,
                    document.recognized_board_id == cell.recognized_board_id,
                    document.import_job_id == cell.import_job_id,
                ),
            )
            .join(ImageReviewItemModel, ImageReviewItemModel.id == cell.review_item_id)
            .join(RecognizedBoardModel, RecognizedBoardModel.id == cell.recognized_board_id)
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .where(
                cell.id.in_(cell_ids),
                cell.game_id == command.game_id,
                cell.geometry_revision == RecognizedBoardModel.geometry_revision,
                ImageReviewItemModel.status.in_(_ACTIVE_REVIEW_STATUSES),
            )
            .with_for_update(
                of=(
                    ImageSymbolReviewCellModel,
                    ImageReviewItemModel,
                    RecognizedBoardModel,
                    SourceImageModel,
                )
            )
            .order_by(cell.sequence_number, cell.cell_index, cell.id)
        ).all()
        return cast(
            tuple[
                tuple[
                    ImageSymbolReviewCellModel,
                    ImageReviewItemModel,
                    RecognizedBoardModel,
                    SourceImageModel,
                ],
                ...,
            ],
            tuple(rows),
        )

    @staticmethod
    def _require_expected_identity(
        cell: ImageSymbolReviewCellModel,
        command: SymbolCellReviewMutationCommand,
    ) -> None:
        if cell.revision != command.expected_revision:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_REVISION_CONFLICT",
                "The symbol-cell review changed after it was loaded. Reload the page.",
                details={
                    "actualRevision": cell.revision,
                    "expectedRevision": command.expected_revision,
                },
            )
        if (
            cell.geometry_revision != command.expected_geometry_revision
            or cell.crop_sample_id != command.expected_crop_sample_id
            or cell.crop_checksum_sha256 != command.expected_crop_checksum_sha256
        ):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_CROP_DRIFT",
                "The symbol-cell crop changed after it was loaded. Reload the page.",
                details={
                    "actualCropChecksumSha256": cell.crop_checksum_sha256,
                    "actualGeometryRevision": cell.geometry_revision,
                },
            )

    def _active_symbols(self, game_id: UUID) -> tuple[dict[UUID, str], dict[str, UUID]]:
        rows = self._session.execute(
            select(SymbolModel.id, SymbolModel.code).where(
                SymbolModel.game_id == game_id,
                SymbolModel.status == SymbolStatus.ACTIVE,
            )
        ).all()
        symbol_code_by_id = {symbol_id: code for symbol_id, code in rows}
        return symbol_code_by_id, {code: symbol_id for symbol_id, code in rows}

    def _locked_current_board_reviews(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
        recognized_board_id: UUID,
        sequence_number: int,
        geometry_revision: int,
        symbol_code_by_id: Mapping[UUID, str],
    ) -> tuple[SymbolCellReview, ...]:
        rows = tuple(
            self._session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(
                    ImageSymbolReviewCellModel.game_id == game_id,
                    ImageSymbolReviewCellModel.review_item_id == review_item_id,
                    ImageSymbolReviewCellModel.recognized_board_id == recognized_board_id,
                )
                .order_by(ImageSymbolReviewCellModel.cell_index)
                .with_for_update()
            )
        )
        if (
            len(rows) != 15
            or [cell.cell_index for cell in rows] != list(range(15))
            or any(
                cell.sequence_number != sequence_number
                or cell.geometry_revision != geometry_revision
                for cell in rows
            )
        ):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_CELLS_INCOMPLETE",
                "The current board does not have exactly 15 matching symbol-cell crops.",
            )
        return tuple(
            _symbol_cell_review_from_model(cell, symbol_code_by_id=symbol_code_by_id)
            for cell in rows
        )


class SymbolCellReviewWriteThroughCoordinator:
    """Keep current crop review state in the same transaction as board writes.

    The legacy Reviewer still owns the parent-board decision.  This adapter is
    deliberately storage-bound: every existing writer already has a locked
    SQLAlchemy session, so running the projection here makes a board mutation,
    its 15 cells and its search/canonical changes commit or roll back together.
    No cell state is materialised before a game's explicit backfill starts.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def synchronize_after_board_resolution(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
        actor: str = _WRITE_THROUGH_ACTOR,
    ) -> bool:
        return self._synchronize(
            game_id=game_id,
            review_item_id=review_item_id,
            reason="board_resolution",
            actor=actor,
        )

    def synchronize_after_geometry_change(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
        actor: str = _WRITE_THROUGH_ACTOR,
    ) -> bool:
        return self._synchronize(
            game_id=game_id,
            review_item_id=review_item_id,
            reason="geometry_change",
            actor=actor,
        )

    def synchronize_after_prediction_refresh(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
        actor: str = _WRITE_THROUGH_ACTOR,
    ) -> bool:
        return self._synchronize(
            game_id=game_id,
            review_item_id=review_item_id,
            reason="prediction_refresh",
            actor=actor,
        )

    def synchronize_after_board_reopened(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
        actor: str = _WRITE_THROUGH_ACTOR,
    ) -> bool:
        """Reopen all cells when a full-board decision is invalidated."""

        return self._synchronize(
            game_id=game_id,
            review_item_id=review_item_id,
            reason="board_reopened",
            actor=actor,
        )

    def synchronize_after_projection_change(self, *, game_id: UUID) -> bool:
        """Advance the filter snapshot after a canonical owner changes."""

        state = self._state_if_initialized(game_id)
        if state is None:
            return False
        self._touch_catalog_revision(state)
        return True

    def synchronize_after_cell_mutation(self, *, game_id: UUID) -> bool:
        """Advance the frozen catalog snapshot after one human crop decision."""

        state = self._state_if_initialized(game_id)
        if state is None:
            return False
        self._touch_catalog_revision(state)
        return True

    def _synchronize(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
        reason: str,
        actor: str,
    ) -> bool:
        state = self._state_if_initialized(game_id)
        if state is None:
            return False
        row = self._review_row(game_id=game_id, review_item_id=review_item_id)
        if row is None:
            self._touch_catalog_revision(state)
            return True
        item, board, source, queue_item, job = row
        if item.status not in _ACTIVE_REVIEW_STATUSES:
            # The fast-document projection has already removed this item from
            # read paths.  Preserve its existing rows for audit; its changed
            # visibility is still a catalog change for a frozen bulk filter.
            self._touch_catalog_revision(state)
            return True

        sequence_number = _current_sequence_number(item=item, board=board)
        if sequence_number is None:
            self._mark_integrity_failure(
                state,
                "SYMBOL_CELL_REVIEW_SEQUENCE_MISSING",
                "An active board has no resolved sequence number; "
                "symbol-cell review cannot hide it.",
            )
            return False

        try:
            current_cells, cropper_version, prediction_revision_id = self._current_cells(
                item=item,
                board=board,
                source=source,
                queue_item=queue_item,
                job=job,
            )
        except Exception as error:
            self._mark_integrity_failure(
                state,
                "SYMBOL_CELL_REVIEW_CROP_INVALID",
                "The current board crop projection is incomplete or invalid: "
                f"{getattr(error, 'code', str(error))}",
            )
            return False

        existing = {
            cell.cell_index: cell
            for cell in self._session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(ImageSymbolReviewCellModel.review_item_id == review_item_id)
                .order_by(ImageSymbolReviewCellModel.cell_index)
                .with_for_update()
            )
        }
        if existing and set(existing) != set(range(15)):
            self._mark_integrity_failure(
                state,
                "SYMBOL_CELL_REVIEW_CELLS_INCOMPLETE",
                "Existing symbol-cell review state does not contain exactly 15 row-major cells.",
            )
            return False

        active_symbol_ids = {
            code: symbol_id
            for symbol_id, code in self._session.execute(
                select(SymbolModel.id, SymbolModel.code).where(
                    SymbolModel.game_id == game_id,
                    SymbolModel.status == SymbolStatus.ACTIVE,
                )
            )
        }
        resolved_symbol_ids = self._resolved_symbol_ids(
            item=item,
            active_symbol_ids=active_symbol_ids,
        )
        if item.status in {"accepted", "corrected"} and resolved_symbol_ids is None:
            self._mark_integrity_failure(
                state,
                "SYMBOL_CELL_REVIEW_RESOLUTION_INVALID",
                "A resolved board does not contain 15 active symbol assignments.",
            )
            return False

        geometry_changed = reason == "geometry_change" or any(
            cell.geometry_revision != board.geometry_revision
            or cell.crop_checksum_sha256 != current_cells[cell.cell_index].crop_checksum_sha256
            for cell in existing.values()
        )
        changed = False
        for review_cell in current_cells:
            existing_cell = existing.get(review_cell.cell_index)
            prediction_symbol_id = active_symbol_ids.get(review_cell.predicted_symbol_code)
            if resolved_symbol_ids is not None:
                target = _CellProjection(
                    assigned_symbol_id=resolved_symbol_ids[review_cell.cell_index],
                    review_state=SymbolCellReviewState.APPROVED.value,
                    has_grid_issue=False,
                    assignment_source=SymbolCellAssignmentSource.BOARD_DECISION.value,
                )
                event_action = "board_synchronized"
            elif geometry_changed or reason == "board_reopened":
                target = _CellProjection(
                    assigned_symbol_id=prediction_symbol_id,
                    review_state=SymbolCellReviewState.PENDING.value,
                    has_grid_issue=False,
                    assignment_source=SymbolCellAssignmentSource.MODEL.value,
                )
                event_action = "geometry_invalidated" if geometry_changed else "board_synchronized"
            elif existing_cell is not None and _is_human_cell_decision(existing_cell):
                target = _CellProjection(
                    assigned_symbol_id=existing_cell.assigned_symbol_id,
                    review_state=existing_cell.review_state,
                    has_grid_issue=existing_cell.has_grid_issue,
                    assignment_source=existing_cell.assignment_source,
                )
                event_action = None
            else:
                target = _CellProjection(
                    assigned_symbol_id=prediction_symbol_id,
                    review_state=SymbolCellReviewState.PENDING.value,
                    has_grid_issue=False,
                    assignment_source=SymbolCellAssignmentSource.MODEL.value,
                )
                event_action = None
            if existing_cell is None:
                self._session.add(
                    ImageSymbolReviewCellModel(
                        game_id=game_id,
                        import_job_id=source.import_job_id,
                        review_item_id=item.id,
                        recognized_board_id=board.id,
                        sequence_number=sequence_number,
                        cell_index=review_cell.cell_index,
                        row_index=review_cell.row_index,
                        column_index=review_cell.column_index,
                        crop_sample_id=review_cell.crop_sample_id,
                        crop_relative_path=review_cell.crop_relative_path,
                        crop_checksum_sha256=review_cell.crop_checksum_sha256,
                        geometry_revision=board.geometry_revision,
                        cropper_version=cropper_version,
                        prediction_symbol_code=_known_symbol_code(
                            review_cell.predicted_symbol_code
                        ),
                        prediction_revision_id=prediction_revision_id,
                        assigned_symbol_id=target.assigned_symbol_id,
                        review_state=target.review_state,
                        has_grid_issue=target.has_grid_issue,
                        assignment_source=target.assignment_source,
                        revision=0,
                        last_reviewed_by=actor,
                    )
                )
                changed = True
                continue
            if not _cell_matches_projection(
                existing_cell,
                review_cell=review_cell,
                cropper_version=cropper_version,
                prediction_revision_id=prediction_revision_id,
                target=target,
                sequence_number=sequence_number,
                geometry_revision=board.geometry_revision,
            ):
                previous = _CellPreviousState.from_model(existing_cell)
                _apply_cell_projection(
                    existing_cell,
                    review_cell=review_cell,
                    cropper_version=cropper_version,
                    prediction_revision_id=prediction_revision_id,
                    target=target,
                    sequence_number=sequence_number,
                    geometry_revision=board.geometry_revision,
                    actor=actor,
                )
                if event_action is not None:
                    self._append_event(
                        cell=existing_cell,
                        previous=previous,
                        action=event_action,
                        actor=actor,
                    )
                changed = True

        if changed:
            self._session.flush()
            self._touch_catalog_revision(state)
        return changed

    def _state_if_initialized(self, game_id: UUID) -> ImageSymbolReviewStateModel | None:
        return self._session.get(
            ImageSymbolReviewStateModel,
            game_id,
            with_for_update=True,
        )

    def _review_row(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
    ) -> (
        tuple[
            ImageReviewItemModel,
            RecognizedBoardModel,
            SourceImageModel,
            ImageReviewQueueItemModel,
            JobModel,
        ]
        | None
    ):
        row = self._session.execute(
            select(
                ImageReviewItemModel,
                RecognizedBoardModel,
                SourceImageModel,
                ImageReviewQueueItemModel,
                JobModel,
            )
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .join(
                ImageReviewQueueItemModel,
                and_(
                    ImageReviewQueueItemModel.review_item_id == ImageReviewItemModel.id,
                    ImageReviewQueueItemModel.import_job_id == SourceImageModel.import_job_id,
                ),
            )
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .where(
                ImageReviewItemModel.id == review_item_id,
                JobModel.game_id == game_id,
            )
            .with_for_update(of=ImageReviewItemModel)
        ).one_or_none()
        if row is None:
            return None
        return cast(
            tuple[
                ImageReviewItemModel,
                RecognizedBoardModel,
                SourceImageModel,
                ImageReviewQueueItemModel,
                JobModel,
            ],
            row,
        )

    def _current_cells(
        self,
        *,
        item: ImageReviewItemModel,
        board: RecognizedBoardModel,
        source: SourceImageModel,
        queue_item: ImageReviewQueueItemModel,
        job: JobModel,
    ) -> tuple[tuple[ImageReviewCell, ...], str, UUID | None]:
        # See the local import in ``_cell_values``.  The Reviewer remains the
        # owner of the base-vs-corrected geometry mapper.
        from game_predictor_api.storage.image_review_repository import (
            materialize_current_image_review_cells,
        )

        observations = self._session.scalars(
            select(CellObservationModel)
            .where(CellObservationModel.recognized_board_id == board.id)
            .order_by(CellObservationModel.row_index, CellObservationModel.column_index)
        ).all()
        geometry = None
        if board.geometry_revision > 0:
            geometry = self._session.scalar(
                select(ImageBoardGeometryRevisionModel).where(
                    ImageBoardGeometryRevisionModel.recognized_board_id == board.id,
                    ImageBoardGeometryRevisionModel.revision == board.geometry_revision,
                )
            )
        prediction = self._session.scalar(
            select(ImageSymbolPredictionRevisionModel)
            .where(ImageSymbolPredictionRevisionModel.review_item_id == item.id)
            .order_by(
                ImageSymbolPredictionRevisionModel.created_at.desc(),
                ImageSymbolPredictionRevisionModel.id.desc(),
            )
        )
        prediction_override = None if prediction is None else list(prediction.predictions)
        cells = materialize_current_image_review_cells(
            item=item,
            board=board,
            source=source,
            queue_item=queue_item,
            job=job,
            observations=observations,
            geometry_revision=geometry,
            prediction_override=prediction_override,
        )
        return (
            tuple(cells),
            _current_cropper_version(
                board=board,
                observations=observations,
                geometry=geometry,
            ),
            None if prediction is None else prediction.id,
        )

    @staticmethod
    def _resolved_symbol_ids(
        *,
        item: ImageReviewItemModel,
        active_symbol_ids: Mapping[str, UUID],
    ) -> tuple[UUID, ...] | None:
        if item.status not in {"accepted", "corrected"}:
            return None
        resolved = cast(Mapping[str, object] | None, item.resolved_value)
        raw_codes = None if resolved is None else resolved.get("symbolCodes")
        if not isinstance(raw_codes, list | tuple) or len(raw_codes) != 15:
            return None
        symbol_ids = tuple(
            active_symbol_ids.get(code) if isinstance(code, str) else None for code in raw_codes
        )
        return (
            None
            if any(symbol_id is None for symbol_id in symbol_ids)
            else cast(tuple[UUID, ...], symbol_ids)
        )

    def _append_event(
        self,
        *,
        cell: ImageSymbolReviewCellModel,
        previous: _CellPreviousState,
        action: str,
        actor: str,
    ) -> None:
        _append_symbol_cell_event(
            self._session,
            cell=cell,
            previous=previous,
            action=action,
            actor=actor,
        )

    def _touch_catalog_revision(self, state: ImageSymbolReviewStateModel) -> None:
        transaction = self._session.get_transaction()
        if transaction is None:
            raise RuntimeError("A symbol-cell write-through must run in a transaction.")
        marker = self._session.info.get(_CELL_REVIEW_TRANSACTION_MARKER)
        if (
            not isinstance(marker, _CatalogRevisionTransactionMarker)
            or marker.transaction is not transaction
        ):
            marker = _CatalogRevisionTransactionMarker(transaction=transaction, game_ids=set())
            self._session.info[_CELL_REVIEW_TRANSACTION_MARKER] = marker
        if state.game_id not in marker.game_ids:
            state.catalog_revision += 1
            marker.game_ids.add(state.game_id)

    @staticmethod
    def _mark_integrity_failure(
        state: ImageSymbolReviewStateModel,
        code: str,
        message: str,
    ) -> None:
        state.status = "failed"
        state.failure_message = f"{code}: {message}"[:500]


@dataclass(frozen=True, slots=True)
class _CellProjection:
    assigned_symbol_id: UUID | None
    review_state: str
    has_grid_issue: bool
    assignment_source: str


@dataclass(frozen=True, slots=True)
class _CellPreviousState:
    assigned_symbol_id: UUID | None
    review_state: str
    has_grid_issue: bool

    @classmethod
    def from_model(cls, cell: ImageSymbolReviewCellModel) -> _CellPreviousState:
        return cls(
            assigned_symbol_id=cell.assigned_symbol_id,
            review_state=cell.review_state,
            has_grid_issue=cell.has_grid_issue,
        )


@dataclass(slots=True)
class _CatalogRevisionTransactionMarker:
    transaction: object
    game_ids: set[UUID]


def _symbol_cell_review_order_columns() -> tuple[Any, Any, Any]:
    cell = ImageSymbolReviewCellModel
    return cell.sequence_number, cell.cell_index, cell.review_item_id.cast(String)


def _symbol_cell_review_after_key(key: tuple[int, int, str]) -> ColumnElement[bool]:
    sequence, cell_index, review_item_key = _symbol_cell_review_order_columns()
    return or_(
        sequence > key[0],
        and_(sequence == key[0], cell_index > key[1]),
        and_(sequence == key[0], cell_index == key[1], review_item_key > key[2]),
    )


def _symbol_cell_review_before_key(key: tuple[int, int, str]) -> ColumnElement[bool]:
    sequence, cell_index, review_item_key = _symbol_cell_review_order_columns()
    return or_(
        sequence < key[0],
        and_(sequence == key[0], cell_index < key[1]),
        and_(sequence == key[0], cell_index == key[1], review_item_key < key[2]),
    )


def _row_to_list_item(row: Any) -> SymbolCellReviewListItem:
    cell = cast(ImageSymbolReviewCellModel, row[0])
    return SymbolCellReviewListItem(
        cell_review_id=cell.id,
        review_item_id=cell.review_item_id,
        recognized_board_id=cell.recognized_board_id,
        import_job_id=cell.import_job_id,
        sequence_number=int(cell.sequence_number),
        cell_index=int(cell.cell_index),
        row_index=int(cell.row_index),
        column_index=int(cell.column_index),
        assigned_symbol_id=cast(UUID | None, row[2]),
        assigned_symbol_code=cast(str | None, row[3]),
        assigned_symbol_name=cast(str | None, row[4]),
        prediction_symbol_code=cell.prediction_symbol_code,
        review_state=SymbolCellReviewState(cell.review_state),
        has_grid_issue=bool(cell.has_grid_issue),
        revision=int(cell.revision),
        geometry_revision=int(cell.geometry_revision),
        crop_sample_id=cell.crop_sample_id,
        crop_checksum_sha256=cell.crop_checksum_sha256,
        board_status=cast(str, row[1]),
    )


def _symbol_cell_review_from_model(
    cell: ImageSymbolReviewCellModel,
    *,
    symbol_code_by_id: Mapping[UUID, str],
) -> SymbolCellReview:
    assigned_symbol_code = (
        None
        if cell.assigned_symbol_id is None
        else symbol_code_by_id.get(cell.assigned_symbol_id)
    )
    if cell.assigned_symbol_id is not None and assigned_symbol_code is None:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_SYMBOL_INVALID",
            "The crop references an inactive or foreign symbol.",
        )
    return SymbolCellReview(
        crop=SymbolCellCropIdentity(
            cell_index=int(cell.cell_index),
            crop_sample_id=cell.crop_sample_id,
            crop_relative_path=cell.crop_relative_path,
            crop_checksum_sha256=cell.crop_checksum_sha256,
            geometry_revision=int(cell.geometry_revision),
            cropper_version=cell.cropper_version,
        ),
        predicted_symbol_code=_known_symbol_code(cell.prediction_symbol_code),
        assigned_symbol_code=assigned_symbol_code,
        review_state=SymbolCellReviewState(cell.review_state),
        has_grid_issue=bool(cell.has_grid_issue),
        assignment_source=SymbolCellAssignmentSource(cell.assignment_source),
        revision=int(cell.revision),
    )


def _apply_symbol_cell_command(
    *,
    command: SymbolCellReviewMutationCommand,
    review: SymbolCellReview,
    active_symbol_codes: Sequence[str],
    symbol_code_by_id: Mapping[UUID, str],
) -> SymbolCellReviewTransition:
    if command.action is SymbolCellReviewAction.APPROVE:
        return approve_symbol_cell_review(review, active_symbol_codes=active_symbol_codes)
    if command.action is SymbolCellReviewAction.REASSIGN:
        target_symbol_id = command.target_symbol_id
        target_symbol_code = (
            None if target_symbol_id is None else symbol_code_by_id.get(target_symbol_id)
        )
        if target_symbol_code is None:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_TARGET_SYMBOL_INVALID",
                "The target symbol is not active for this game.",
            )
        return reassign_symbol_cell_review(
            review,
            target_symbol_code=target_symbol_code,
            active_symbol_codes=active_symbol_codes,
        )
    if command.action is SymbolCellReviewAction.MARK_GRID_ISSUE:
        return mark_symbol_cell_grid_issue(review)
    raise SymbolCellReviewError(
        "SYMBOL_CELL_REVIEW_ACTION_INVALID",
        "The symbol-cell review action is not supported.",
    )


def _apply_symbol_cell_review_transition(
    cell: ImageSymbolReviewCellModel,
    *,
    review: SymbolCellReview,
    symbol_id_by_code: Mapping[str, UUID],
    actor: str,
) -> None:
    assigned_symbol_id = (
        None
        if review.assigned_symbol_code is None
        else symbol_id_by_code.get(review.assigned_symbol_code)
    )
    if review.assigned_symbol_code is not None and assigned_symbol_id is None:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_SYMBOL_INVALID",
            "The assigned crop symbol is no longer active for this game.",
        )
    cell.assigned_symbol_id = assigned_symbol_id
    cell.review_state = review.review_state.value
    cell.has_grid_issue = review.has_grid_issue
    cell.assignment_source = review.assignment_source.value
    cell.revision = review.revision
    cell.last_reviewed_by = actor


def _append_symbol_cell_event(
    session: Session,
    *,
    cell: ImageSymbolReviewCellModel,
    previous: _CellPreviousState,
    action: str,
    actor: str,
    operation_id: UUID | None = None,
) -> None:
    session.add(
        ImageSymbolReviewEventModel(
            cell_review_id=cell.id,
            review_item_id=cell.review_item_id,
            crop_sample_id=cell.crop_sample_id,
            crop_checksum_sha256=cell.crop_checksum_sha256,
            geometry_revision=cell.geometry_revision,
            cell_revision=cell.revision,
            action=action,
            previous_assigned_symbol_id=previous.assigned_symbol_id,
            assigned_symbol_id=cell.assigned_symbol_id,
            previous_review_state=previous.review_state,
            review_state=cell.review_state,
            previous_has_grid_issue=previous.has_grid_issue,
            has_grid_issue=cell.has_grid_issue,
            operation_id=operation_id,
            actor=actor,
        )
    )


def _symbol_cell_mutation_checksum(command: SymbolCellReviewMutationCommand) -> str:
    return hashlib.sha256(
        canonical_image_review_bytes(
            {
                "action": command.action.value,
                "cellReviewId": str(command.cell_review_id),
                "expectedCropChecksumSha256": command.expected_crop_checksum_sha256,
                "expectedCropSampleId": command.expected_crop_sample_id,
                "expectedGeometryRevision": command.expected_geometry_revision,
                "expectedRevision": command.expected_revision,
                "targetSymbolId": (
                    None if command.target_symbol_id is None else str(command.target_symbol_id)
                ),
            }
        )
    ).hexdigest()


def _current_sequence_number(
    *, item: ImageReviewItemModel, board: RecognizedBoardModel
) -> int | None:
    if item.status in {"accepted", "corrected"}:
        resolved = cast(Mapping[str, object] | None, item.resolved_value)
        value = None if resolved is None else resolved.get("sequenceNumber")
    else:
        value = board.sequence_number
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _known_symbol_code(value: str | None) -> str | None:
    return value if value is not None and value != "?" else None


def _is_human_cell_decision(cell: ImageSymbolReviewCellModel) -> bool:
    return (
        cell.review_state == SymbolCellReviewState.APPROVED.value
        or cell.has_grid_issue
        or cell.assignment_source
        in {
            SymbolCellAssignmentSource.HUMAN.value,
            SymbolCellAssignmentSource.BOARD_DECISION.value,
        }
    )


def _cell_matches_projection(
    cell: ImageSymbolReviewCellModel,
    *,
    review_cell: ImageReviewCell,
    cropper_version: str,
    prediction_revision_id: UUID | None,
    target: _CellProjection,
    sequence_number: int,
    geometry_revision: int,
) -> bool:
    return (
        cell.sequence_number == sequence_number
        and cell.crop_sample_id == review_cell.crop_sample_id
        and cell.crop_relative_path == review_cell.crop_relative_path
        and cell.crop_checksum_sha256 == review_cell.crop_checksum_sha256
        and cell.geometry_revision == geometry_revision
        and cell.cropper_version == cropper_version
        and cell.prediction_symbol_code == _known_symbol_code(review_cell.predicted_symbol_code)
        and cell.prediction_revision_id == prediction_revision_id
        and cell.assigned_symbol_id == target.assigned_symbol_id
        and cell.review_state == target.review_state
        and bool(cell.has_grid_issue) == target.has_grid_issue
        and cell.assignment_source == target.assignment_source
    )


def _apply_cell_projection(
    cell: ImageSymbolReviewCellModel,
    *,
    review_cell: ImageReviewCell,
    cropper_version: str,
    prediction_revision_id: UUID | None,
    target: _CellProjection,
    sequence_number: int,
    geometry_revision: int,
    actor: str,
) -> None:
    cell.sequence_number = sequence_number
    cell.crop_sample_id = review_cell.crop_sample_id
    cell.crop_relative_path = review_cell.crop_relative_path
    cell.crop_checksum_sha256 = review_cell.crop_checksum_sha256
    cell.geometry_revision = geometry_revision
    cell.cropper_version = cropper_version
    cell.prediction_symbol_code = _known_symbol_code(review_cell.predicted_symbol_code)
    cell.prediction_revision_id = prediction_revision_id
    cell.assigned_symbol_id = target.assigned_symbol_id
    cell.review_state = target.review_state
    cell.has_grid_issue = target.has_grid_issue
    cell.assignment_source = target.assignment_source
    cell.revision += 1
    cell.last_reviewed_by = actor


class SqlAlchemyImageSymbolReviewRepository:
    """Backfills only selected logical boards and never stores crop bytes."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def start_or_resume_backfill(self, game_id: UUID) -> SymbolCellReviewBackfillReport:
        game = self._session.scalar(
            select(GameModel).where(GameModel.id == game_id).with_for_update()
        )
        if game is None:
            raise SymbolCellReviewBackfillError(
                "SYMBOL_CELL_REVIEW_GAME_NOT_FOUND", "The selected game does not exist."
            )
        missing = self._active_review_items_without_sequence(game_id)
        state = self._session.get(ImageSymbolReviewStateModel, game_id, with_for_update=True)
        if state is None:
            state = ImageSymbolReviewStateModel(
                game_id=game_id,
                status="rebuilding",
                processed_review_item_count=0,
                cell_count=0,
                missing_sequence_count=0,
                invalid_crop_count=0,
                invalid_geometry_count=0,
                last_review_item_id=None,
                failure_message=None,
            )
            self._session.add(state)
        elif state.status != "ready":
            state.status = "rebuilding"
            state.failure_message = None

        if missing:
            self._mark_failed(
                state,
                SymbolCellReviewBackfillError(
                    "SYMBOL_CELL_REVIEW_SEQUENCE_MISSING",
                    "An active board has no resolved sequence number; "
                    "symbol-cell review cannot hide it.",
                    review_item_ids=missing,
                ),
            )
        self._session.flush()
        return self._report_from_state(state, sample_problem_review_item_ids=missing)

    def backfill_next_batch(
        self,
        game_id: UUID,
        *,
        batch_size: int = _DEFAULT_BATCH_SIZE,
    ) -> SymbolCellReviewBackfillStep:
        if not 1 <= batch_size <= 500:
            raise ValueError("batch_size must be between 1 and 500")
        state = self._require_rebuilding_state(game_id)
        rows = self._selected_rows_after(
            game_id=game_id,
            after_review_item_id=state.last_review_item_id,
            limit=batch_size,
        )
        if not rows:
            report = self.finalize_backfill(game_id)
            return SymbolCellReviewBackfillStep(
                report=report,
                processed_review_item_count=0,
                has_more=False,
            )
        try:
            values = self._cell_values(rows)
        except SymbolCellReviewBackfillError as error:
            self._mark_failed(state, error)
            self._session.flush()
            return SymbolCellReviewBackfillStep(
                report=self._report_from_state(
                    state,
                    sample_problem_review_item_ids=error.review_item_ids,
                ),
                processed_review_item_count=0,
                has_more=False,
            )

        if values:
            statement = postgresql_insert(ImageSymbolReviewCellModel).values(values)
            self._session.execute(
                statement.on_conflict_do_nothing(
                    index_elements=[
                        ImageSymbolReviewCellModel.review_item_id,
                        ImageSymbolReviewCellModel.cell_index,
                    ]
                )
            )
        state.last_review_item_id = rows[-1][1].id
        state.processed_review_item_count += len(rows)
        state.cell_count = self._current_selected_cell_count(game_id)
        self._session.flush()
        return SymbolCellReviewBackfillStep(
            report=self._report_from_state(state),
            processed_review_item_count=len(rows),
            has_more=len(rows) == batch_size,
        )

    def finalize_backfill(self, game_id: UUID) -> SymbolCellReviewBackfillReport:
        state = self._require_rebuilding_state(game_id)
        missing = self._active_review_items_without_sequence(game_id)
        incomplete = self._selected_items_without_exactly_fifteen_cells(game_id)
        stale_geometry = self._selected_items_with_stale_geometry(game_id)
        stale_base_crop = self._selected_items_with_stale_base_crop(game_id)
        if missing:
            error = SymbolCellReviewBackfillError(
                "SYMBOL_CELL_REVIEW_SEQUENCE_MISSING",
                "An active board has no resolved sequence number; "
                "symbol-cell review cannot hide it.",
                review_item_ids=missing,
            )
            self._mark_failed(state, error)
            self._session.flush()
            return self._report_from_state(state, sample_problem_review_item_ids=missing)
        if incomplete:
            error = SymbolCellReviewBackfillError(
                "SYMBOL_CELL_REVIEW_BACKFILL_INCOMPLETE",
                "The symbol-cell backfill did not create exactly 15 current crops for every board.",
                review_item_ids=incomplete,
                invalid_crop_count=len(incomplete),
            )
            self._mark_failed(state, error)
            self._session.flush()
            return self._report_from_state(state, sample_problem_review_item_ids=incomplete)
        if stale_geometry or stale_base_crop:
            problem_ids = tuple(dict.fromkeys((*stale_geometry, *stale_base_crop)))
            error = SymbolCellReviewBackfillError(
                "SYMBOL_CELL_REVIEW_CROP_STALE",
                "Persisted symbol-cell crops no longer match their current geometry or base crop.",
                review_item_ids=problem_ids,
                invalid_crop_count=len(stale_base_crop),
                invalid_geometry_count=len(stale_geometry),
            )
            self._mark_failed(state, error)
            self._session.flush()
            return self._report_from_state(state, sample_problem_review_item_ids=problem_ids)

        state.status = "ready"
        state.catalog_revision += 1
        state.cell_count = self._current_selected_cell_count(game_id)
        state.missing_sequence_count = 0
        state.invalid_crop_count = 0
        state.invalid_geometry_count = 0
        state.failure_message = None
        self._session.flush()
        return self._report_from_state(state)

    def mark_backfill_failed(
        self,
        game_id: UUID,
        error: Exception,
    ) -> SymbolCellReviewBackfillReport:
        state = self._session.get(ImageSymbolReviewStateModel, game_id, with_for_update=True)
        if state is None:
            raise SymbolCellReviewBackfillError(
                "SYMBOL_CELL_REVIEW_BACKFILL_NOT_STARTED",
                "Start the symbol-cell review backfill before marking it failed.",
            )
        controlled = (
            error
            if isinstance(error, SymbolCellReviewBackfillError)
            else SymbolCellReviewBackfillError(
                "SYMBOL_CELL_REVIEW_BACKFILL_FAILED",
                str(error) or "Symbol-cell review backfill failed.",
            )
        )
        self._mark_failed(state, controlled)
        self._session.flush()
        return self._report_from_state(
            state,
            sample_problem_review_item_ids=controlled.review_item_ids,
        )

    def state_for_game(self, game_id: UUID) -> SymbolCellReviewBackfillReport | None:
        state = self._session.get(ImageSymbolReviewStateModel, game_id)
        return None if state is None else self._report_from_state(state)

    def _require_rebuilding_state(self, game_id: UUID) -> ImageSymbolReviewStateModel:
        state = self._session.get(ImageSymbolReviewStateModel, game_id, with_for_update=True)
        if state is None:
            raise SymbolCellReviewBackfillError(
                "SYMBOL_CELL_REVIEW_BACKFILL_NOT_STARTED",
                "Start the symbol-cell review backfill before processing a batch.",
            )
        if state.status != "rebuilding":
            raise SymbolCellReviewBackfillError(
                "SYMBOL_CELL_REVIEW_BACKFILL_NOT_REBUILDING",
                "The symbol-cell review backfill is not currently rebuilding.",
            )
        return state

    def _selected_rows_after(
        self,
        *,
        game_id: UUID,
        after_review_item_id: UUID | None,
        limit: int,
    ) -> tuple[BackfillRow, ...]:
        statement = (
            select(
                ImageBoardSearchFastDocumentModel,
                ImageReviewItemModel,
                RecognizedBoardModel,
                SourceImageModel,
                ImageReviewQueueItemModel,
                JobModel,
            )
            .join(
                ImageReviewItemModel,
                ImageReviewItemModel.id == ImageBoardSearchFastDocumentModel.review_item_id,
            )
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .join(
                ImageReviewQueueItemModel,
                and_(
                    ImageReviewQueueItemModel.review_item_id == ImageReviewItemModel.id,
                    ImageReviewQueueItemModel.import_job_id == SourceImageModel.import_job_id,
                ),
            )
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .where(
                ImageBoardSearchFastDocumentModel.game_id == game_id,
                ImageReviewItemModel.status.in_(_ACTIVE_REVIEW_STATUSES),
                *(
                    ()
                    if after_review_item_id is None
                    else (ImageReviewItemModel.id > after_review_item_id,)
                ),
            )
            .order_by(ImageReviewItemModel.id)
            .with_for_update(of=ImageReviewItemModel)
            .limit(limit)
        )
        return tuple(self._session.execute(statement).tuples())

    def _cell_values(self, rows: Sequence[BackfillRow]) -> list[dict[str, object]]:
        # Kept local so the operational Reviewer can use the write-through
        # coordinator from this module without a module-import cycle.
        from game_predictor_api.storage.image_review_repository import (
            materialize_current_image_review_cells,
        )

        board_ids = [board.id for _document, _item, board, _source, _queue, _job in rows]
        item_ids = [item.id for _document, item, _board, _source, _queue, _job in rows]
        observations_by_board: dict[UUID, list[CellObservationModel]] = defaultdict(list)
        for observation in self._session.scalars(
            select(CellObservationModel)
            .where(CellObservationModel.recognized_board_id.in_(board_ids))
            .order_by(
                CellObservationModel.recognized_board_id,
                CellObservationModel.row_index,
                CellObservationModel.column_index,
            )
        ):
            observations_by_board[observation.recognized_board_id].append(observation)
        revisions_by_board: dict[UUID, ImageBoardGeometryRevisionModel] = {}
        for geometry_revision_record in self._session.scalars(
            select(ImageBoardGeometryRevisionModel)
            .where(ImageBoardGeometryRevisionModel.recognized_board_id.in_(board_ids))
            .order_by(
                ImageBoardGeometryRevisionModel.recognized_board_id,
                ImageBoardGeometryRevisionModel.revision,
            )
        ):
            revisions_by_board[
                geometry_revision_record.recognized_board_id
            ] = geometry_revision_record
        prediction_by_item: dict[UUID, ImageSymbolPredictionRevisionModel] = {}
        for prediction in self._session.scalars(
            select(ImageSymbolPredictionRevisionModel)
            .where(ImageSymbolPredictionRevisionModel.review_item_id.in_(item_ids))
            .order_by(
                ImageSymbolPredictionRevisionModel.review_item_id,
                ImageSymbolPredictionRevisionModel.created_at,
                ImageSymbolPredictionRevisionModel.id,
            )
        ):
            prediction_by_item[prediction.review_item_id] = prediction
        active_symbol_ids = {
            code: symbol_id
            for symbol_id, code in self._session.execute(
                select(SymbolModel.id, SymbolModel.code).where(
                    SymbolModel.game_id == rows[0][0].game_id,
                    SymbolModel.status == SymbolStatus.ACTIVE,
                )
            )
        }

        values: list[dict[str, object]] = []
        for document, item, board, source, queue_item, job in rows:
            prediction_revision = prediction_by_item.get(item.id)
            prediction_override = (
                None if prediction_revision is None else list(prediction_revision.predictions)
            )
            current_geometry = revisions_by_board.get(board.id)
            observations = observations_by_board[board.id]
            try:
                current_cells = materialize_current_image_review_cells(
                    item=item,
                    board=board,
                    source=source,
                    queue_item=queue_item,
                    job=job,
                    observations=observations,
                    geometry_revision=current_geometry,
                    prediction_override=prediction_override,
                )
                cropper_version = _current_cropper_version(
                    board=board,
                    observations=observations,
                    geometry=current_geometry,
                )
                mapped = map_current_symbol_cell_reviews(
                    cells=current_cells,
                    geometry_revision=board.geometry_revision,
                    cropper_version=cropper_version,
                    assignment_source=(
                        SymbolCellAssignmentSource.BOARD_DECISION
                        if item.status in {"accepted", "corrected"}
                        else SymbolCellAssignmentSource.BACKFILL
                    ),
                )
            except Exception as error:
                if isinstance(error, SymbolCellReviewBackfillError):
                    raise
                geometry_error = getattr(error, "code", "") in {
                    "IMAGE_REVIEW_GEOMETRY_PROJECTION_INVALID",
                    "SYMBOL_CELL_REVIEW_GEOMETRY_REVISION_INVALID",
                }
                raise SymbolCellReviewBackfillError(
                    "SYMBOL_CELL_REVIEW_BACKFILL_CROP_INVALID",
                    "The current crop projection is incomplete or invalid for a selected board.",
                    review_item_ids=(item.id,),
                    invalid_crop_count=0 if geometry_error else 1,
                    invalid_geometry_count=1 if geometry_error else 0,
                ) from error

            for review in mapped:
                approved = item.status in {"accepted", "corrected"}
                symbol_code = review.assigned_symbol_code
                symbol_id = active_symbol_ids.get(symbol_code) if symbol_code is not None else None
                if approved and symbol_id is None:
                    raise SymbolCellReviewBackfillError(
                        "SYMBOL_CELL_REVIEW_BACKFILL_RESOLUTION_INVALID",
                        "A resolved board contains an unknown or inactive symbol assignment.",
                        review_item_ids=(item.id,),
                        invalid_crop_count=1,
                    )
                values.append(
                    {
                        "id": uuid4(),
                        "game_id": document.game_id,
                        "import_job_id": source.import_job_id,
                        "review_item_id": item.id,
                        "recognized_board_id": board.id,
                        "sequence_number": document.sequence_number,
                        "cell_index": review.cell_index,
                        "row_index": review.cell_index // 5,
                        "column_index": review.cell_index % 5,
                        "crop_sample_id": review.crop.crop_sample_id,
                        "crop_relative_path": review.crop.crop_relative_path,
                        "crop_checksum_sha256": review.crop.crop_checksum_sha256,
                        "geometry_revision": review.crop.geometry_revision,
                        "cropper_version": review.crop.cropper_version,
                        "prediction_symbol_code": review.predicted_symbol_code,
                        "prediction_revision_id": (
                            None if prediction_revision is None else prediction_revision.id
                        ),
                        "assigned_symbol_id": symbol_id,
                        "review_state": (
                            SymbolCellReviewState.APPROVED.value
                            if approved
                            else SymbolCellReviewState.PENDING.value
                        ),
                        "has_grid_issue": False,
                        "assignment_source": (
                            SymbolCellAssignmentSource.BOARD_DECISION.value
                            if approved
                            else SymbolCellAssignmentSource.BACKFILL.value
                        ),
                        "revision": 0,
                        "last_reviewed_by": _BACKFILL_ACTOR,
                    }
                )
        return values

    def _active_review_items_without_sequence(self, game_id: UUID) -> tuple[UUID, ...]:
        rows = self._session.execute(
            select(
                ImageReviewItemModel.id,
                ImageReviewItemModel.status,
                ImageReviewItemModel.resolved_value,
                RecognizedBoardModel.sequence_number,
            )
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .where(
                JobModel.game_id == game_id,
                ImageReviewItemModel.status.in_(_ACTIVE_REVIEW_STATUSES),
            )
            .order_by(ImageReviewItemModel.id)
        ).all()
        missing: list[UUID] = []
        for review_item_id, status, resolved_value, board_sequence_number in rows:
            sequence_value: object = board_sequence_number
            if status in {"accepted", "corrected"} and isinstance(resolved_value, Mapping):
                sequence_value = resolved_value.get("sequenceNumber")
            if (
                not isinstance(sequence_value, int)
                or isinstance(sequence_value, bool)
                or sequence_value < 1
            ):
                missing.append(cast(UUID, review_item_id))
        return tuple(missing)

    def _selected_items_without_exactly_fifteen_cells(self, game_id: UUID) -> tuple[UUID, ...]:
        counts = (
            select(
                ImageBoardSearchFastDocumentModel.review_item_id.label("review_item_id"),
                func.count(ImageSymbolReviewCellModel.id).label("cell_count"),
            )
            .outerjoin(
                ImageSymbolReviewCellModel,
                ImageSymbolReviewCellModel.review_item_id
                == ImageBoardSearchFastDocumentModel.review_item_id,
            )
            .where(ImageBoardSearchFastDocumentModel.game_id == game_id)
            .group_by(ImageBoardSearchFastDocumentModel.review_item_id)
            .having(func.count(ImageSymbolReviewCellModel.id) != 15)
            .order_by(ImageBoardSearchFastDocumentModel.review_item_id)
        )
        return tuple(cast(UUID, value) for value in self._session.scalars(counts))

    def _selected_items_with_stale_geometry(self, game_id: UUID) -> tuple[UUID, ...]:
        statement = (
            select(ImageSymbolReviewCellModel.review_item_id)
            .join(
                ImageBoardSearchFastDocumentModel,
                ImageBoardSearchFastDocumentModel.review_item_id
                == ImageSymbolReviewCellModel.review_item_id,
            )
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageSymbolReviewCellModel.recognized_board_id,
            )
            .where(
                ImageBoardSearchFastDocumentModel.game_id == game_id,
                ImageSymbolReviewCellModel.geometry_revision
                != RecognizedBoardModel.geometry_revision,
            )
            .distinct()
            .order_by(ImageSymbolReviewCellModel.review_item_id)
        )
        return tuple(self._session.scalars(statement))

    def _selected_items_with_stale_base_crop(self, game_id: UUID) -> tuple[UUID, ...]:
        statement = (
            select(ImageSymbolReviewCellModel.review_item_id)
            .join(
                ImageBoardSearchFastDocumentModel,
                ImageBoardSearchFastDocumentModel.review_item_id
                == ImageSymbolReviewCellModel.review_item_id,
            )
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageSymbolReviewCellModel.recognized_board_id,
            )
            .outerjoin(
                CellObservationModel,
                and_(
                    CellObservationModel.recognized_board_id
                    == ImageSymbolReviewCellModel.recognized_board_id,
                    CellObservationModel.row_index == ImageSymbolReviewCellModel.row_index,
                    CellObservationModel.column_index == ImageSymbolReviewCellModel.column_index,
                ),
            )
            .where(
                ImageBoardSearchFastDocumentModel.game_id == game_id,
                RecognizedBoardModel.geometry_revision == 0,
                or_(
                    CellObservationModel.id.is_(None),
                    CellObservationModel.crop_checksum_sha256
                    != ImageSymbolReviewCellModel.crop_checksum_sha256,
                    CellObservationModel.crop_relative_path
                    != ImageSymbolReviewCellModel.crop_relative_path,
                    CellObservationModel.cropper_version
                    != ImageSymbolReviewCellModel.cropper_version,
                ),
            )
            .distinct()
            .order_by(ImageSymbolReviewCellModel.review_item_id)
        )
        return tuple(self._session.scalars(statement))

    def _current_selected_cell_count(self, game_id: UUID) -> int:
        return int(
            self._session.scalar(
                select(func.count(ImageSymbolReviewCellModel.id))
                .join(
                    ImageBoardSearchFastDocumentModel,
                    ImageBoardSearchFastDocumentModel.review_item_id
                    == ImageSymbolReviewCellModel.review_item_id,
                )
                .where(ImageBoardSearchFastDocumentModel.game_id == game_id)
            )
            or 0
        )

    @staticmethod
    def _mark_failed(
        state: ImageSymbolReviewStateModel,
        error: SymbolCellReviewBackfillError,
    ) -> None:
        state.status = "failed"
        state.missing_sequence_count = (
            len(error.review_item_ids) if error.code == "SYMBOL_CELL_REVIEW_SEQUENCE_MISSING" else 0
        )
        state.invalid_crop_count = error.invalid_crop_count
        state.invalid_geometry_count = error.invalid_geometry_count
        state.failure_message = f"{error.code}: {error.message}"[:500]

    @staticmethod
    def _report_from_state(
        state: ImageSymbolReviewStateModel,
        *,
        sample_problem_review_item_ids: Sequence[UUID] = (),
    ) -> SymbolCellReviewBackfillReport:
        return SymbolCellReviewBackfillReport(
            game_id=state.game_id,
            status=state.status,
            catalog_revision=int(state.catalog_revision),
            processed_review_item_count=int(state.processed_review_item_count),
            cell_count=int(state.cell_count),
            missing_sequence_count=int(state.missing_sequence_count),
            invalid_crop_count=int(state.invalid_crop_count),
            invalid_geometry_count=int(state.invalid_geometry_count),
            failure_message=state.failure_message,
            sample_problem_review_item_ids=tuple(sample_problem_review_item_ids[:100]),
        )


def _current_cropper_version(
    *,
    board: RecognizedBoardModel,
    observations: Sequence[CellObservationModel],
    geometry: ImageBoardGeometryRevisionModel | None,
) -> str:
    if board.geometry_revision > 0:
        if geometry is None or geometry.revision != board.geometry_revision:
            raise SymbolCellReviewBackfillError(
                "SYMBOL_CELL_REVIEW_BACKFILL_GEOMETRY_INVALID",
                "The current board geometry revision is missing.",
                invalid_geometry_count=1,
            )
        return geometry.cropper_version
    versions = {observation.cropper_version for observation in observations}
    if len(versions) != 1:
        raise SymbolCellReviewBackfillError(
            "SYMBOL_CELL_REVIEW_BACKFILL_CROP_INVALID",
            "The base board observations do not have one current cropper version.",
            invalid_crop_count=1,
        )
    return next(iter(versions))


__all__ = [
    "SqlAlchemySymbolCellReviewQueryRepository",
    "SqlAlchemySymbolCellReviewMutationRepository",
    "SymbolCellReviewWriteThroughCoordinator",
    "SqlAlchemyImageSymbolReviewRepository",
    "SymbolCellReviewBackfillError",
    "SymbolCellReviewBackfillReport",
    "SymbolCellReviewBackfillStep",
]
