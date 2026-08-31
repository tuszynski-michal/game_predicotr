"""Persistence and resumable backfill for checksum-bound symbol-cell review."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Float, String, and_, delete, func, or_, select
from sqlalchemy import cast as sql_cast
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
from game_predictor_api.application.unreadable_board_reviews import (
    ResolveUnreadableCellCommand,
    UnreadableBoardReviewCell,
    UnreadableBoardReviewDetail,
    UnreadableBoardReviewListItem,
    UnreadableBoardReviewRepository,
    UnreadableBoardReviewSlice,
    UnreadableBoardReviewView,
)
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.catalog import SymbolStatus
from game_predictor_api.domain.image_grid_reviews import (
    approve_image_grid_review,
    derive_image_grid_review,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewAction,
    ImageReviewCell,
    ImageReviewResolutionCell,
    canonical_image_review_bytes,
)
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellApprovedCropIdentity,
    SymbolCellAssignmentSource,
    SymbolCellCropIdentity,
    SymbolCellQualityIssue,
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
    invalidate_symbol_cell_reviews_for_geometry,
    map_current_symbol_cell_reviews,
    mark_symbol_cell_grid_issue,
    mark_symbol_cell_unreadable,
    reassign_symbol_cell_review,
    resolve_unreadable_symbol_cell_review,
)
from game_predictor_api.domain.jobs import JobStatus, JobType
from game_predictor_api.storage.additive_virtual_geometry_contracts import (
    PersistedVerificationV2,
    optional_verification_outcome_value,
    verification_outcome_value,
)
from game_predictor_api.storage.models import (
    CellObservationModel,
    GameModel,
    ImageBoardGeometryReviewEventModel,
    ImageBoardGeometryRevisionModel,
    ImageBoardSearchFastDocumentModel,
    ImageReviewItemModel,
    ImageReviewQueueItemModel,
    ImageSourceGeometryRevisionModel,
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
_MAX_CELL_ROWS_PER_INSERT = 1_000
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


def _iter_cell_insert_chunks(
    values: Sequence[dict[str, object]],
) -> Iterator[Sequence[dict[str, object]]]:
    """Keep each PostgreSQL INSERT safely below psycopg's parameter limit."""

    for offset in range(0, len(values), _MAX_CELL_ROWS_PER_INSERT):
        yield values[offset : offset + _MAX_CELL_ROWS_PER_INSERT]


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


def symbol_cell_review_projection_is_available(
    session: Session,
    *,
    game_id: UUID,
    state: ImageSymbolReviewStateModel | None,
) -> bool:
    if state is None:
        return False
    if state.status == "ready":
        return True
    if state.status != "rebuilding":
        return False
    jobs = session.scalars(
        select(JobModel).where(
            JobModel.game_id == game_id,
            JobModel.job_type == JobType.IMAGE_SYMBOL_REVIEW_BACKFILL,
            JobModel.status.in_((JobStatus.CREATED, JobStatus.PROCESSING)),
        )
    ).all()
    return any(job.input_payload.get("preserve_ready_projection") is True for job in jobs)


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


@dataclass(frozen=True, slots=True)
class SymbolCellReviewReconciliationStep:
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
        projection_available = symbol_cell_review_projection_is_available(
            self._session,
            game_id=game_id,
            state=state,
        )
        if state is None or not projection_available:
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
        after_key: tuple[int, int, UUID] | None,
        before_key: tuple[int, int, UUID] | None,
        limit: int,
    ) -> SymbolCellReviewListSlice:
        if after_key is not None and before_key is not None:
            raise ValueError("only one symbol-cell review keyset direction is allowed")
        statement = self._candidate_seek_statement(review_filter=review_filter)
        sequence, cell_index, review_item_key = _symbol_cell_review_order_columns()
        seek_key = before_key if before_key is not None else after_key
        descending = before_key is not None
        visible_ids: list[UUID] = []
        seek_batch_size = max(limit + 1, 1_000)
        while len(visible_ids) < limit + 1:
            batch_statement = statement
            if seek_key is not None:
                batch_statement = batch_statement.where(
                    _symbol_cell_review_before_key(seek_key)
                    if descending
                    else _symbol_cell_review_after_key(seek_key)
                )
            batch_statement = batch_statement.order_by(
                sequence.desc() if descending else sequence,
                cell_index.desc() if descending else cell_index,
                review_item_key.desc() if descending else review_item_key,
            ).limit(seek_batch_size)
            candidate_rows = self._session.execute(batch_statement).all()
            if not candidate_rows:
                break
            candidate_ids = tuple(cast(UUID, row[0]) for row in candidate_rows)
            current_ids = {
                cast(UUID, row[0])
                for row in self._session.execute(
                    self._base_visible_statement(
                        review_filter=review_filter,
                        include_prediction_confidence=False,
                    )
                    .with_only_columns(ImageSymbolReviewCellModel.id)
                    .where(ImageSymbolReviewCellModel.id.in_(candidate_ids))
                ).all()
            }
            visible_ids.extend(cell_id for cell_id in candidate_ids if cell_id in current_ids)
            last = candidate_rows[-1]
            seek_key = (int(last[1]), int(last[2]), cast(UUID, last[3]))
            if len(candidate_rows) < seek_batch_size:
                break

        if before_key is not None:
            has_previous = len(visible_ids) > limit
            page_ids = tuple(reversed(visible_ids[:limit]))
            has_next = bool(page_ids)
        else:
            has_next = len(visible_ids) > limit
            page_ids = tuple(visible_ids[:limit])
            has_previous = after_key is not None and bool(page_ids)
        if not page_ids:
            return SymbolCellReviewListSlice(items=(), has_previous=False, has_next=False)
        hydrated_rows = self._session.execute(
            self._list_statement(review_filter=review_filter).where(
                ImageSymbolReviewCellModel.id.in_(page_ids)
            )
        ).all()
        hydrated_items = tuple(_row_to_list_item(row) for row in hydrated_rows)
        item_by_id = {item.cell_review_id: item for item in hydrated_items}
        # A concurrent mutation may move one seeked item outside the filter
        # before hydration under READ COMMITTED. Returning the remaining
        # checksum-bound rows is safer than serving stale metadata or failing
        # the whole page.
        visible = tuple(item_by_id[cell_id] for cell_id in page_ids if cell_id in item_by_id)
        return SymbolCellReviewListSlice(
            items=visible,
            has_previous=has_previous,
            has_next=has_next,
        )

    def counts(self, *, review_filter: SymbolCellReviewListFilter) -> SymbolCellReviewCounts:
        cell = ImageSymbolReviewCellModel
        rows = self._session.execute(
            self._base_visible_statement(
                review_filter=review_filter,
                include_prediction_confidence=False,
            )
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
        assets = self.get_assets(game_id=game_id, cell_review_ids=(cell_review_id,))
        return assets[0] if assets else None

    def get_assets(
        self,
        *,
        game_id: UUID,
        cell_review_ids: tuple[UUID, ...],
    ) -> tuple[SymbolCellReviewAsset, ...]:
        if not cell_review_ids:
            return ()
        cell = ImageSymbolReviewCellModel
        document = ImageBoardSearchFastDocumentModel
        source_geometry = ImageSourceGeometryRevisionModel
        rows = self._session.execute(
            select(
                cell,
                RecognizedBoardModel.geometry_revision,
                RecognizedBoardModel.source_geometry_revision_id,
                SourceImageModel.checksum_sha256,
                source_geometry.normalized_pixel_checksum_sha256,
                source_geometry.geometry_checksum_sha256,
            )
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
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .outerjoin(
                source_geometry,
                source_geometry.id == cell.source_geometry_revision_id,
            )
            .where(cell.game_id == game_id, cell.id.in_(cell_review_ids))
        ).all()
        return tuple(
            SymbolCellReviewAsset(
                cell_review_id=review_cell.id,
                crop_relative_path=review_cell.crop_relative_path,
                crop_checksum_sha256=review_cell.crop_checksum_sha256,
                geometry_revision=review_cell.geometry_revision,
                current_geometry_revision=int(current_geometry_revision),
                revision=review_cell.revision,
                asset_mode=review_cell.asset_mode,
                source_checksum_sha256=(
                    None if review_cell.asset_mode != "virtual_source" else source_checksum
                ),
                normalized_pixel_checksum_sha256=(
                    None
                    if review_cell.asset_mode != "virtual_source"
                    else normalized_pixel_checksum
                ),
                source_geometry_revision_id=review_cell.source_geometry_revision_id,
                current_source_geometry_revision_id=current_source_geometry_revision_id,
                geometry_checksum_sha256=(
                    None if review_cell.asset_mode != "virtual_source" else geometry_checksum
                ),
                logical_cell_key=review_cell.logical_cell_key,
                render_spec=review_cell.render_spec,
                render_spec_checksum_sha256=review_cell.render_spec_checksum_sha256,
                rendered_pixel_checksum_sha256=review_cell.rendered_pixel_checksum_sha256,
                extractor_version=review_cell.extractor_version,
            )
            for (
                review_cell,
                current_geometry_revision,
                current_source_geometry_revision_id,
                source_checksum,
                normalized_pixel_checksum,
                geometry_checksum,
            ) in rows
        )

    def _list_statement(self, *, review_filter: SymbolCellReviewListFilter) -> Select[Any]:
        cell = ImageSymbolReviewCellModel
        assigned_symbol = aliased(SymbolModel)
        return (
            self._visible_statement(review_filter=review_filter)
            .add_columns(
                ImageBoardSearchFastDocumentModel.status.label("board_status"),
                assigned_symbol.id.label("assigned_symbol_id"),
                assigned_symbol.code.label("assigned_symbol_code"),
                assigned_symbol.name.label("assigned_symbol_name"),
                _prediction_confidence_expression().label("prediction_confidence"),
            )
            .outerjoin(assigned_symbol, assigned_symbol.id == cell.assigned_symbol_id)
        )

    def _candidate_seek_statement(
        self,
        *,
        review_filter: SymbolCellReviewListFilter,
    ) -> Select[Any]:
        """Seek indexed candidates without allowing ownership joins to force a global sort."""

        cell = ImageSymbolReviewCellModel
        statement = select(
            cell.id,
            cell.sequence_number,
            cell.cell_index,
            cell.review_item_id,
        ).where(
            cell.game_id == review_filter.game_id,
        )
        if review_filter.symbol_id is None:
            statement = statement.where(cell.assigned_symbol_id.is_(None))
        else:
            statement = statement.where(cell.assigned_symbol_id == review_filter.symbol_id)
        if review_filter.state is not SymbolCellReviewFilterState.ALL:
            statement = statement.where(cell.review_state == review_filter.state.value)
        return statement

    def _visible_statement(self, *, review_filter: SymbolCellReviewListFilter) -> Select[Any]:
        return self._base_visible_statement(
            review_filter=review_filter,
            include_prediction_confidence=True,
        )

    def _base_visible_statement(
        self,
        *,
        review_filter: SymbolCellReviewListFilter,
        include_prediction_confidence: bool,
    ) -> Select[Any]:
        cell = ImageSymbolReviewCellModel
        document = ImageBoardSearchFastDocumentModel
        prediction_revision = ImageSymbolPredictionRevisionModel
        observation = CellObservationModel
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
        confidence_is_required = (
            include_prediction_confidence
            or review_filter.min_confidence is not None
            or review_filter.max_confidence is not None
        )
        if confidence_is_required:
            statement = statement.outerjoin(
                prediction_revision,
                prediction_revision.id == cell.prediction_revision_id,
            ).outerjoin(
                observation,
                and_(
                    observation.recognized_board_id == cell.recognized_board_id,
                    observation.row_index == cell.row_index,
                    observation.column_index == cell.column_index,
                ),
            )
        confidence = _prediction_confidence_expression()
        if review_filter.min_confidence is not None:
            statement = statement.where(confidence >= review_filter.min_confidence)
        if review_filter.max_confidence is not None:
            statement = statement.where(confidence <= review_filter.max_confidence)
        return statement


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
            topology=_board_topology(board),
            geometry_approved=board.approved_geometry_revision == board.geometry_revision,
        )
        any_changed = any(changed_by_cell_id.values())
        board_reopened = False
        board_resolution_action: str | None = None
        board_status = item.status
        reopen_command = next(
            (
                command
                for command in commands
                if command.action
                in {
                    SymbolCellReviewAction.MARK_GRID_ISSUE,
                    SymbolCellReviewAction.MARK_UNREADABLE,
                }
                and changed_by_cell_id[command.cell_review_id]
            ),
            None,
        )
        if reopen_command is not None and item.status in {"accepted", "corrected"}:
            updated, board_reopened = SqlAlchemyOperationalImageReviewRepository(
                self._session
            ).reopen_for_symbol_cell_issue(
                review_item_id=item.id,
                game_id=game_id,
                import_job_id=source.import_job_id,
                idempotency_key=uuid4(),
                command_sha256=_symbol_cell_mutation_checksum(reopen_command),
                reopened_by=reopen_command.actor.strip(),
                reopened_at=datetime.now(UTC),
                reason=reopen_command.action.value,
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
                    symbol_code=review.assigned_symbol_code,
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
                allow_unknown_cells=any(cell.symbol_code is None for cell in cells),
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
                has_grid_issue=(
                    _quality_issue_from_model(row_by_cell_id[command.cell_review_id][0])
                    == SymbolCellQualityIssue.GRID_ISSUE.value
                ),
                quality_issue=(
                    None
                    if (
                        issue := _quality_issue_from_model(
                            row_by_cell_id[command.cell_review_id][0]
                        )
                    )
                    is None
                    else SymbolCellQualityIssue(issue)
                ),
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
        if state is None or not symbol_cell_review_projection_is_available(
            self._session,
            game_id=game_id,
            state=state,
        ):
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
        return _active_symbol_maps(self._session, game_id)

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
        board = self._session.get(RecognizedBoardModel, recognized_board_id)
        if board is None:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_CURRENT_OWNER_CONFLICT",
                "The current board disappeared before its crop decisions were aggregated.",
            )
        return _locked_board_reviews(
            self._session,
            game_id=game_id,
            review_item_id=review_item_id,
            recognized_board_id=recognized_board_id,
            sequence_number=sequence_number,
            geometry_revision=geometry_revision,
            symbol_code_by_id=symbol_code_by_id,
            topology=_board_topology(board),
        )


class SqlAlchemyUnreadableBoardReviewRepository(UnreadableBoardReviewRepository):
    """Current-owner board queue built directly from unreadable cell state."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def require_ready_game(self, game_id: UUID) -> None:
        SqlAlchemySymbolCellReviewQueryRepository(self._session).require_ready_game(game_id)

    def list_boards(
        self,
        *,
        game_id: UUID,
        view: UnreadableBoardReviewView,
        after_key: tuple[int, str] | None,
        limit: int,
    ) -> UnreadableBoardReviewSlice:
        cell = ImageSymbolReviewCellModel
        document = ImageBoardSearchFastDocumentModel
        unreadable_count = (
            select(func.count(cell.id))
            .where(
                cell.game_id == game_id,
                cell.review_item_id == document.review_item_id,
                cell.geometry_revision == RecognizedBoardModel.geometry_revision,
                cell.quality_issue == SymbolCellQualityIssue.UNREADABLE.value,
            )
            .correlate(document, RecognizedBoardModel)
            .scalar_subquery()
        )
        pending_count = (
            select(func.count(cell.id))
            .where(
                cell.game_id == game_id,
                cell.review_item_id == document.review_item_id,
                cell.geometry_revision == RecognizedBoardModel.geometry_revision,
                cell.quality_issue == SymbolCellQualityIssue.UNREADABLE.value,
                cell.review_state == SymbolCellReviewState.PENDING.value,
            )
            .correlate(document, RecognizedBoardModel)
            .scalar_subquery()
        )
        statement = (
            select(
                document.review_item_id,
                document.recognized_board_id,
                document.import_job_id,
                document.sequence_number,
                document.status,
                RecognizedBoardModel.grid_rows,
                RecognizedBoardModel.grid_columns,
                unreadable_count.label("unreadable_count"),
                pending_count.label("pending_count"),
            )
            .join(RecognizedBoardModel, RecognizedBoardModel.id == document.recognized_board_id)
            .where(document.game_id == game_id, unreadable_count > 0)
        )
        if view is UnreadableBoardReviewView.PENDING:
            statement = statement.where(pending_count > 0)
        if after_key is not None:
            statement = statement.where(
                or_(
                    document.sequence_number > after_key[0],
                    and_(
                        document.sequence_number == after_key[0],
                        document.review_item_id.cast(String) > after_key[1],
                    ),
                )
            )
        rows = self._session.execute(
            statement.order_by(document.sequence_number, document.review_item_id).limit(limit + 1)
        ).all()
        visible = rows[:limit]
        return UnreadableBoardReviewSlice(
            items=tuple(
                UnreadableBoardReviewListItem(
                    review_item_id=row.review_item_id,
                    recognized_board_id=row.recognized_board_id,
                    import_job_id=row.import_job_id,
                    sequence_number=int(row.sequence_number),
                    board_status=str(row.status),
                    grid_rows=int(row.grid_rows or 3),
                    grid_columns=int(row.grid_columns or 5),
                    unreadable_count=int(row.unreadable_count),
                    pending_unreadable_count=int(row.pending_count),
                )
                for row in visible
            ),
            has_next=len(rows) > limit,
        )

    def get_board(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
    ) -> UnreadableBoardReviewDetail | None:
        document = ImageBoardSearchFastDocumentModel
        board_row = self._session.execute(
            select(document, RecognizedBoardModel)
            .join(RecognizedBoardModel, RecognizedBoardModel.id == document.recognized_board_id)
            .where(
                document.game_id == game_id,
                document.review_item_id == review_item_id,
                select(ImageSymbolReviewCellModel.id)
                .where(
                    ImageSymbolReviewCellModel.game_id == game_id,
                    ImageSymbolReviewCellModel.review_item_id == review_item_id,
                    ImageSymbolReviewCellModel.geometry_revision
                    == RecognizedBoardModel.geometry_revision,
                    ImageSymbolReviewCellModel.quality_issue
                    == SymbolCellQualityIssue.UNREADABLE.value,
                )
                .exists(),
            )
        ).one_or_none()
        if board_row is None:
            return None
        current, board = board_row
        assigned = aliased(SymbolModel)
        rows = self._session.execute(
            select(ImageSymbolReviewCellModel, assigned)
            .outerjoin(assigned, assigned.id == ImageSymbolReviewCellModel.assigned_symbol_id)
            .where(
                ImageSymbolReviewCellModel.game_id == game_id,
                ImageSymbolReviewCellModel.review_item_id == review_item_id,
                ImageSymbolReviewCellModel.recognized_board_id == board.id,
                ImageSymbolReviewCellModel.geometry_revision == board.geometry_revision,
            )
            .order_by(ImageSymbolReviewCellModel.cell_index)
        ).all()
        topology = _board_topology(board)
        if len(rows) != topology.cell_count:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_PROJECTION_INCOMPLETE",
                "The unreadable board does not contain every current topology cell.",
            )
        return UnreadableBoardReviewDetail(
            review_item_id=current.review_item_id,
            recognized_board_id=current.recognized_board_id,
            import_job_id=current.import_job_id,
            sequence_number=int(current.sequence_number),
            board_status=str(current.status),
            grid_rows=topology.rows,
            grid_columns=topology.columns,
            cells=tuple(
                UnreadableBoardReviewCell(
                    cell_review_id=cell_row.id,
                    cell_index=int(cell_row.cell_index),
                    row_index=int(cell_row.row_index),
                    column_index=int(cell_row.column_index),
                    assigned_symbol_id=cell_row.assigned_symbol_id,
                    assigned_symbol_code=None if symbol is None else symbol.code,
                    assigned_symbol_name=None if symbol is None else symbol.name,
                    prediction_symbol_code=_known_symbol_code(cell_row.prediction_symbol_code),
                    review_state=cell_row.review_state,
                    quality_issue=_quality_issue_from_model(cell_row),
                    revision=int(cell_row.revision),
                    geometry_revision=int(cell_row.geometry_revision),
                    crop_sample_id=cell_row.crop_sample_id,
                    crop_checksum_sha256=cell_row.crop_checksum_sha256,
                )
                for cell_row, symbol in rows
            ),
        )

    def resolve_cell(
        self,
        command: ResolveUnreadableCellCommand,
    ) -> SymbolCellReviewMutationResult:
        cell_id = self._session.scalar(
            select(ImageSymbolReviewCellModel.id)
            .join(
                ImageBoardSearchFastDocumentModel,
                and_(
                    ImageBoardSearchFastDocumentModel.game_id == ImageSymbolReviewCellModel.game_id,
                    ImageBoardSearchFastDocumentModel.review_item_id
                    == ImageSymbolReviewCellModel.review_item_id,
                    ImageBoardSearchFastDocumentModel.recognized_board_id
                    == ImageSymbolReviewCellModel.recognized_board_id,
                ),
            )
            .where(
                ImageSymbolReviewCellModel.game_id == command.game_id,
                ImageSymbolReviewCellModel.review_item_id == command.review_item_id,
                ImageSymbolReviewCellModel.cell_index == command.cell_index,
            )
        )
        if cell_id is None:
            raise SymbolCellReviewError(
                "UNREADABLE_BOARD_REVIEW_CELL_NOT_FOUND",
                "The selected unreadable cell is not part of the current logical board.",
            )
        action = (
            SymbolCellReviewAction.APPROVE
            if command.target_symbol_id is None
            else SymbolCellReviewAction.REASSIGN
        )
        return SqlAlchemySymbolCellReviewMutationRepository(self._session).apply_mutation(
            SymbolCellReviewMutationCommand(
                game_id=command.game_id,
                cell_review_id=cell_id,
                action=action,
                expected_revision=command.expected_revision,
                expected_geometry_revision=command.expected_geometry_revision,
                expected_crop_sample_id=command.expected_crop_sample_id,
                expected_crop_checksum_sha256=command.expected_crop_checksum_sha256,
                target_symbol_id=command.target_symbol_id,
                actor=command.actor,
                resolve_unreadable=True,
            )
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

    def approve_current_geometry(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
        expected_geometry_revision: int,
        actor: str,
        approved_at: datetime,
    ) -> bool:
        """Approve one exact geometry revision and aggregate its logical board."""

        from game_predictor_api.storage.image_review_repository import (
            acquire_image_review_sequence_locks,
        )

        acquire_image_review_sequence_locks(
            self._session,
            game_id=game_id,
            review_item_id=review_item_id,
            requested_sequence_number=None,
        )
        state = self._state_if_initialized(game_id)
        if state is None:
            return False
        row = self._review_row(game_id=game_id, review_item_id=review_item_id)
        if row is None:
            return False
        item, board, _source, _queue_item, _job = row
        locked_board = self._session.get(RecognizedBoardModel, board.id, with_for_update=True)
        if locked_board is None or locked_board.geometry_revision != expected_geometry_revision:
            raise SymbolCellReviewError(
                "IMAGE_GRID_REVIEW_GEOMETRY_REVISION_CONFLICT",
                "The board geometry changed before it could be approved.",
            )
        board = locked_board
        topology = _board_topology(board)
        cells = tuple(
            self._session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(ImageSymbolReviewCellModel.review_item_id == review_item_id)
                .order_by(ImageSymbolReviewCellModel.cell_index)
                .with_for_update()
            )
        )
        if len(cells) != topology.cell_count or [cell.cell_index for cell in cells] != list(
            range(topology.cell_count)
        ):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_CELLS_INCOMPLETE",
                "Geometry approval requires every configured symbol-cell crop.",
            )
        quality_issues = tuple(_quality_issue_from_model(cell) for cell in cells)
        grid_review = derive_image_grid_review(
            topology=topology,
            geometry_revision=board.geometry_revision,
            approved_geometry_revision=board.approved_geometry_revision,
            cell_quality_issues=tuple(
                None if issue is None else SymbolCellQualityIssue(issue) for issue in quality_issues
            ),
        )
        transition = approve_image_grid_review(grid_review)
        if not transition.changed:
            return False
        previous = board.approved_geometry_revision
        board.approved_geometry_revision = transition.review.approved_geometry_revision
        board.geometry_approved_at = approved_at
        board.geometry_approved_by = actor
        self._session.add(
            ImageBoardGeometryReviewEventModel(
                review_item_id=item.id,
                recognized_board_id=board.id,
                geometry_revision=board.geometry_revision,
                grid_rows=topology.rows,
                grid_columns=topology.columns,
                board_checksum_sha256=board.board_checksum_sha256,
                action="approved",
                previous_approved_geometry_revision=previous,
                approved_geometry_revision=board.geometry_revision,
                actor=actor,
                created_at=approved_at,
            )
        )
        self._session.flush()
        self._touch_catalog_revision(state)
        self.synchronize_board_from_cells(
            game_id=game_id,
            review_item_id=review_item_id,
            actor=actor,
        )
        return True

    def synchronize_board_from_cells(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
        actor: str,
    ) -> bool:
        """Materialize a complete parent decision from current cell state.

        Geometry approval and all current cell labels are checked again under
        the same transaction.  Crop provenance is deliberately not promoted:
        resolving the logical board after a recrop must not make the new
        pixels training-eligible.
        """

        state = self._state_if_initialized(game_id)
        if state is None:
            return False
        row = self._review_row(game_id=game_id, review_item_id=review_item_id)
        if row is None:
            return False
        item, board, source, _queue_item, _job = row
        if item.status != "pending":
            return False
        sequence_number = _current_sequence_number(item=item, board=board)
        if sequence_number is None:
            self._mark_integrity_failure(
                state,
                "SYMBOL_CELL_REVIEW_SEQUENCE_MISSING",
                "An active board has no resolved sequence number.",
            )
            return False
        topology = _board_topology(board)
        symbol_codes, _symbol_ids = _active_symbol_maps(self._session, game_id)
        reviews = _locked_board_reviews(
            self._session,
            game_id=game_id,
            review_item_id=item.id,
            recognized_board_id=board.id,
            sequence_number=sequence_number,
            geometry_revision=board.geometry_revision,
            symbol_code_by_id=symbol_codes,
            topology=topology,
        )
        resolution = derive_symbol_cell_board_resolution(
            reviews=reviews,
            active_symbol_codes=tuple(symbol_codes.values()),
            topology=topology,
            geometry_approved=board.approved_geometry_revision == board.geometry_revision,
        )
        if resolution is None:
            return False

        from game_predictor_api.application.image_reviews import OperationalImageReviewService
        from game_predictor_api.storage.image_review_repository import (
            SqlAlchemyOperationalImageReviewRepository,
        )

        repository = SqlAlchemyOperationalImageReviewRepository(self._session)
        current = repository.get_item(
            item.id,
            game_id=game_id,
            import_job_id=source.import_job_id,
            for_update=True,
        )
        if current is None or current.status != "pending":
            return False
        action = resolution.action
        if (
            action is ImageReviewAction.ACCEPTED
            and current.suggested_sequence_number != sequence_number
        ):
            action = ImageReviewAction.CORRECTED
        OperationalImageReviewService(repository).resolve_item(
            item.id,
            game_id=game_id,
            import_job_id=source.import_job_id,
            idempotency_key=uuid4(),
            expected_revision=current.resolution_revision,
            action=action,
            sequence_number=sequence_number,
            geometry_revision=current.geometry_revision,
            cells=tuple(
                ImageReviewResolutionCell(
                    cell_index=review.cell_index,
                    crop_sample_id=review.crop.crop_sample_id,
                    symbol_code=review.assigned_symbol_code,
                )
                for review in reviews
            ),
            rejection_reason=None,
            resolved_by=actor,
            allow_unknown_cells=any(review.assigned_symbol_code is None for review in reviews),
        )
        return True

    def synchronize_for_backfill_reconciliation(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
    ) -> bool:
        """Repair one current owner without overwriting human crop decisions."""

        return self._synchronize(
            game_id=game_id,
            review_item_id=review_item_id,
            reason="backfill_reconciliation",
            actor=_BACKFILL_ACTOR,
            repair_incomplete_backfill=True,
        )

    def _synchronize(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
        reason: str,
        actor: str,
        repair_incomplete_backfill: bool = False,
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
        topology = _board_topology(board)
        if existing and set(existing) != set(range(topology.cell_count)):
            if repair_incomplete_backfill and not any(
                _is_human_cell_decision(cell) for cell in existing.values()
            ):
                self._session.execute(
                    delete(ImageSymbolReviewCellModel).where(
                        ImageSymbolReviewCellModel.review_item_id == review_item_id
                    )
                )
                existing = {}
            else:
                self._mark_integrity_failure(
                    state,
                    "SYMBOL_CELL_REVIEW_CELLS_INCOMPLETE",
                    "Existing symbol-cell review state does not contain every configured "
                    "row-major cell.",
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
            cell_count=topology.cell_count,
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
        recropped_targets: dict[int, _CellProjection] = {}
        if geometry_changed and existing:
            symbol_code_by_id = {symbol_id: code for code, symbol_id in active_symbol_ids.items()}
            recropped = invalidate_symbol_cell_reviews_for_geometry(
                existing_reviews=tuple(
                    _symbol_cell_review_from_model(
                        existing[index],
                        symbol_code_by_id=symbol_code_by_id,
                    )
                    for index in range(topology.cell_count)
                ),
                current_cells=current_cells,
                geometry_revision=board.geometry_revision,
                cropper_version=cropper_version,
                topology=topology,
            )
            recropped_targets = {
                review.cell_index: _CellProjection(
                    assigned_symbol_id=(
                        None
                        if review.assigned_symbol_code is None
                        else active_symbol_ids.get(review.assigned_symbol_code)
                    ),
                    review_state=review.review_state.value,
                    assignment_source=review.assignment_source.value,
                    quality_issue=(
                        None if review.quality_issue is None else review.quality_issue.value
                    ),
                    approved_crop_sample_id=(
                        None
                        if review.approved_crop is None
                        else review.approved_crop.crop_sample_id
                    ),
                    approved_crop_checksum_sha256=(
                        None
                        if review.approved_crop is None
                        else review.approved_crop.crop_checksum_sha256
                    ),
                    approved_geometry_revision=(
                        None
                        if review.approved_crop is None
                        else review.approved_crop.geometry_revision
                    ),
                )
                for review in recropped
            }
        changed = False
        for review_cell in current_cells:
            existing_cell = existing.get(review_cell.cell_index)
            prediction_symbol_id = active_symbol_ids.get(review_cell.predicted_symbol_code)
            if geometry_changed and existing_cell is not None:
                target = recropped_targets[review_cell.cell_index]
                event_action = "geometry_invalidated"
            elif resolved_symbol_ids is not None:
                resolved_symbol_id = resolved_symbol_ids[review_cell.cell_index]
                preserve_approved_crop = (
                    existing_cell is not None
                    and existing_cell.review_state == SymbolCellReviewState.APPROVED.value
                    and existing_cell.assigned_symbol_id == resolved_symbol_id
                )
                target = _CellProjection(
                    assigned_symbol_id=resolved_symbol_id,
                    review_state=SymbolCellReviewState.APPROVED.value,
                    assignment_source=(
                        existing_cell.assignment_source
                        if preserve_approved_crop and existing_cell is not None
                        else SymbolCellAssignmentSource.BOARD_DECISION.value
                    ),
                    quality_issue=(
                        _quality_issue_from_model(existing_cell)
                        if preserve_approved_crop and existing_cell is not None
                        else None
                    ),
                    approved_crop_sample_id=(
                        existing_cell.approved_crop_sample_id
                        if preserve_approved_crop and existing_cell is not None
                        else review_cell.crop_sample_id
                    ),
                    approved_crop_checksum_sha256=(
                        existing_cell.approved_crop_checksum_sha256
                        if preserve_approved_crop and existing_cell is not None
                        else review_cell.crop_checksum_sha256
                    ),
                    approved_geometry_revision=(
                        existing_cell.approved_geometry_revision
                        if preserve_approved_crop and existing_cell is not None
                        else board.geometry_revision
                    ),
                )
                event_action = "board_synchronized"
            elif geometry_changed or reason == "board_reopened":
                target = _CellProjection(
                    assigned_symbol_id=prediction_symbol_id,
                    review_state=SymbolCellReviewState.PENDING.value,
                    assignment_source=SymbolCellAssignmentSource.MODEL.value,
                    quality_issue=None,
                    approved_crop_sample_id=None,
                    approved_crop_checksum_sha256=None,
                    approved_geometry_revision=None,
                )
                event_action = "geometry_invalidated" if geometry_changed else "board_synchronized"
            elif existing_cell is not None and _is_human_cell_decision(existing_cell):
                target = _CellProjection(
                    assigned_symbol_id=existing_cell.assigned_symbol_id,
                    review_state=existing_cell.review_state,
                    assignment_source=existing_cell.assignment_source,
                    quality_issue=_quality_issue_from_model(existing_cell),
                    approved_crop_sample_id=existing_cell.approved_crop_sample_id,
                    approved_crop_checksum_sha256=existing_cell.approved_crop_checksum_sha256,
                    approved_geometry_revision=existing_cell.approved_geometry_revision,
                )
                event_action = None
            else:
                target = _CellProjection(
                    assigned_symbol_id=prediction_symbol_id,
                    review_state=SymbolCellReviewState.PENDING.value,
                    assignment_source=SymbolCellAssignmentSource.MODEL.value,
                    quality_issue=None,
                    approved_crop_sample_id=None,
                    approved_crop_checksum_sha256=None,
                    approved_geometry_revision=None,
                )
                event_action = None
            if existing_cell is None:
                verification = _verification_v2(
                    review_state=target.review_state,
                    quality_issue=target.quality_issue,
                    assigned_symbol_id=target.assigned_symbol_id,
                    prediction_symbol_code=review_cell.predicted_symbol_code,
                    assignment_source=target.assignment_source,
                )
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
                        quality_issue=target.quality_issue,
                        verification_outcome=verification.outcome,
                        verified_symbol_id_v2=verification.verified_symbol_id,
                        approved_crop_sample_id=target.approved_crop_sample_id,
                        approved_crop_checksum_sha256=target.approved_crop_checksum_sha256,
                        approved_geometry_revision=target.approved_geometry_revision,
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
        cell_count: int,
    ) -> tuple[UUID | None, ...] | None:
        if item.status not in {"accepted", "corrected"}:
            return None
        resolved = cast(Mapping[str, object] | None, item.resolved_value)
        raw_codes = None if resolved is None else resolved.get("symbolCodes")
        if not isinstance(raw_codes, list | tuple) or len(raw_codes) != cell_count:
            return None
        if any(code is not None and not isinstance(code, str) for code in raw_codes):
            return None
        if any(isinstance(code, str) and code not in active_symbol_ids for code in raw_codes):
            return None
        return tuple(
            None if code is None else active_symbol_ids[cast(str, code)] for code in raw_codes
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
    assignment_source: str
    quality_issue: str | None
    approved_crop_sample_id: str | None
    approved_crop_checksum_sha256: str | None
    approved_geometry_revision: int | None


@dataclass(frozen=True, slots=True)
class _CellPreviousState:
    assigned_symbol_id: UUID | None
    review_state: str
    quality_issue: str | None
    approved_crop_sample_id: str | None
    approved_crop_checksum_sha256: str | None
    approved_geometry_revision: int | None
    logical_cell_key_v2: str | None
    render_identity_v2_sha256: str | None
    asset_mode: str
    source_geometry_revision_id: UUID | None
    render_spec_checksum_sha256: str | None
    rendered_pixel_checksum_sha256: str | None
    verification_outcome: str | None
    verified_symbol_id_v2: UUID | None

    @classmethod
    def from_model(cls, cell: ImageSymbolReviewCellModel) -> _CellPreviousState:
        previous_v2 = optional_verification_outcome_value(
            review_state=cell.review_state,
            quality_issue=_quality_issue_from_model(cell),
            assigned_symbol_id=cell.assigned_symbol_id,
            prediction_present=_known_symbol_code(cell.prediction_symbol_code) is not None,
            assignment_source=cell.assignment_source,
        )
        return cls(
            assigned_symbol_id=cell.assigned_symbol_id,
            review_state=cell.review_state,
            quality_issue=_quality_issue_from_model(cell),
            approved_crop_sample_id=cell.approved_crop_sample_id,
            approved_crop_checksum_sha256=cell.approved_crop_checksum_sha256,
            approved_geometry_revision=cell.approved_geometry_revision,
            logical_cell_key_v2=cell.logical_cell_key_v2,
            render_identity_v2_sha256=cell.render_identity_v2_sha256,
            asset_mode=cell.asset_mode,
            source_geometry_revision_id=cell.source_geometry_revision_id,
            render_spec_checksum_sha256=cell.render_spec_checksum_sha256,
            rendered_pixel_checksum_sha256=cell.rendered_pixel_checksum_sha256,
            verification_outcome=(
                cell.verification_outcome
                if cell.verification_outcome is not None
                else None
                if previous_v2 is None
                else previous_v2.outcome
            ),
            verified_symbol_id_v2=(
                cell.verified_symbol_id_v2
                if cell.verification_outcome is not None
                else None
                if previous_v2 is None
                else previous_v2.verified_symbol_id
            ),
        )


@dataclass(slots=True)
class _CatalogRevisionTransactionMarker:
    transaction: object
    game_ids: set[UUID]


def _board_topology(board: RecognizedBoardModel) -> BoardTopology:
    return BoardTopology(
        rows=board.grid_rows or 3,
        columns=board.grid_columns or 5,
    )


def _active_symbol_maps(
    session: Session,
    game_id: UUID,
) -> tuple[dict[UUID, str], dict[str, UUID]]:
    rows = session.execute(
        select(SymbolModel.id, SymbolModel.code).where(
            SymbolModel.game_id == game_id,
            SymbolModel.status == SymbolStatus.ACTIVE,
        )
    ).all()
    symbol_code_by_id = {symbol_id: code for symbol_id, code in rows}
    return symbol_code_by_id, {code: symbol_id for symbol_id, code in rows}


def _locked_board_reviews(
    session: Session,
    *,
    game_id: UUID,
    review_item_id: UUID,
    recognized_board_id: UUID,
    sequence_number: int,
    geometry_revision: int,
    symbol_code_by_id: Mapping[UUID, str],
    topology: BoardTopology,
) -> tuple[SymbolCellReview, ...]:
    rows = tuple(
        session.scalars(
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
        len(rows) != topology.cell_count
        or [cell.cell_index for cell in rows] != list(range(topology.cell_count))
        or any(
            cell.sequence_number != sequence_number or cell.geometry_revision != geometry_revision
            for cell in rows
        )
    ):
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_CELLS_INCOMPLETE",
            "The current board does not have every configured matching symbol-cell crop.",
        )
    return tuple(
        _symbol_cell_review_from_model(cell, symbol_code_by_id=symbol_code_by_id) for cell in rows
    )


def _symbol_cell_review_order_columns() -> tuple[Any, Any, Any]:
    cell = ImageSymbolReviewCellModel
    return cell.sequence_number, cell.cell_index, cell.review_item_id


def _symbol_cell_review_after_key(key: tuple[int, int, UUID]) -> ColumnElement[bool]:
    sequence, cell_index, review_item_key = _symbol_cell_review_order_columns()
    return or_(
        sequence > key[0],
        and_(sequence == key[0], cell_index > key[1]),
        and_(sequence == key[0], cell_index == key[1], review_item_key > key[2]),
    )


def _symbol_cell_review_before_key(key: tuple[int, int, UUID]) -> ColumnElement[bool]:
    sequence, cell_index, review_item_key = _symbol_cell_review_order_columns()
    return or_(
        sequence < key[0],
        and_(sequence == key[0], cell_index < key[1]),
        and_(sequence == key[0], cell_index == key[1], review_item_key < key[2]),
    )


def _row_to_list_item(row: Any) -> SymbolCellReviewListItem:
    cell = cast(ImageSymbolReviewCellModel, row[0])
    review = _symbol_cell_review_from_model(
        cell,
        symbol_code_by_id=(
            {} if row[2] is None or row[3] is None else {cast(UUID, row[2]): cast(str, row[3])}
        ),
    )
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
        has_grid_issue=(review.quality_issue is SymbolCellQualityIssue.GRID_ISSUE),
        quality_issue=review.quality_issue,
        crop_approval_state=review.crop_approval_state,
        revision=int(cell.revision),
        geometry_revision=int(cell.geometry_revision),
        crop_sample_id=cell.crop_sample_id,
        crop_checksum_sha256=cell.crop_checksum_sha256,
        board_status=cast(str, row[1]),
        prediction_confidence=(None if row[5] is None else float(row[5])),
        asset_mode=cell.asset_mode,
        render_spec_checksum_sha256=cell.render_spec_checksum_sha256,
    )


def _prediction_confidence_expression() -> ColumnElement[float | None]:
    """Read the latest review confidence without materialising a new projection.

    Pending reinference stores the current per-cell confidence in the linked
    prediction revision. Legacy rows retain it in ``cell_observations``.  The
    list and frozen bulk filter use the same expression so a filter snapshot
    cannot silently broaden between preview and execution.
    """

    cell = ImageSymbolReviewCellModel
    revision = ImageSymbolPredictionRevisionModel
    observation = CellObservationModel
    revision_confidence = sql_cast(
        revision.predictions.op("->")(cell.cell_index).op("->>")("confidence"),
        Float(),
    )
    legacy_confidence = sql_cast(
        observation.prediction.op("->>")("confidence"),
        Float(),
    )
    return cast(
        ColumnElement[float | None],
        func.coalesce(revision_confidence, legacy_confidence),
    )


def _symbol_cell_review_from_model(
    cell: ImageSymbolReviewCellModel,
    *,
    symbol_code_by_id: Mapping[UUID, str],
) -> SymbolCellReview:
    quality_issue = _quality_issue_from_model(cell)
    assigned_symbol_code = (
        None if cell.assigned_symbol_id is None else symbol_code_by_id.get(cell.assigned_symbol_id)
    )
    if cell.assigned_symbol_id is not None and assigned_symbol_code is None:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_SYMBOL_INVALID",
            "The crop references an inactive or foreign symbol.",
        )
    if cell.crop_relative_path is None:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_VIRTUAL_ASSET_UNAVAILABLE",
            "Virtual symbol assets are not active in the legacy review mapper.",
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
        has_grid_issue=(quality_issue == SymbolCellQualityIssue.GRID_ISSUE.value),
        assignment_source=SymbolCellAssignmentSource(cell.assignment_source),
        revision=int(cell.revision),
        quality_issue=(None if quality_issue is None else SymbolCellQualityIssue(quality_issue)),
        approved_crop=(
            None
            if cell.approved_crop_sample_id is None
            or cell.approved_crop_checksum_sha256 is None
            or cell.approved_geometry_revision is None
            else SymbolCellApprovedCropIdentity(
                crop_sample_id=cell.approved_crop_sample_id,
                crop_checksum_sha256=cell.approved_crop_checksum_sha256,
                geometry_revision=int(cell.approved_geometry_revision),
            )
        ),
    )


def _apply_symbol_cell_command(
    *,
    command: SymbolCellReviewMutationCommand,
    review: SymbolCellReview,
    active_symbol_codes: Sequence[str],
    symbol_code_by_id: Mapping[UUID, str],
) -> SymbolCellReviewTransition:
    if command.resolve_unreadable:
        target_symbol_code = (
            None
            if command.target_symbol_id is None
            else symbol_code_by_id.get(command.target_symbol_id)
        )
        if command.target_symbol_id is not None and target_symbol_code is None:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_TARGET_SYMBOL_INVALID",
                "The target symbol is not active for this game.",
            )
        return resolve_unreadable_symbol_cell_review(
            review,
            target_symbol_code=target_symbol_code,
            active_symbol_codes=active_symbol_codes,
        )
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
    if command.action is SymbolCellReviewAction.MARK_UNREADABLE:
        return mark_symbol_cell_unreadable(review)
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
    cell.quality_issue = None if review.quality_issue is None else review.quality_issue.value
    cell.approved_crop_sample_id = (
        None if review.approved_crop is None else review.approved_crop.crop_sample_id
    )
    cell.approved_crop_checksum_sha256 = (
        None if review.approved_crop is None else review.approved_crop.crop_checksum_sha256
    )
    cell.approved_geometry_revision = (
        None if review.approved_crop is None else review.approved_crop.geometry_revision
    )
    cell.assignment_source = review.assignment_source.value
    verification = _verification_v2(
        review_state=cell.review_state,
        quality_issue=cell.quality_issue,
        assigned_symbol_id=cell.assigned_symbol_id,
        prediction_symbol_code=cell.prediction_symbol_code,
        assignment_source=cell.assignment_source,
    )
    cell.verification_outcome = verification.outcome
    cell.verified_symbol_id_v2 = verification.verified_symbol_id
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
            logical_cell_key=cell.logical_cell_key,
            previous_logical_cell_key_v2=previous.logical_cell_key_v2,
            logical_cell_key_v2=cell.logical_cell_key_v2,
            previous_render_identity_v2_sha256=previous.render_identity_v2_sha256,
            render_identity_v2_sha256=cell.render_identity_v2_sha256,
            previous_asset_mode=previous.asset_mode,
            asset_mode=cell.asset_mode,
            previous_source_geometry_revision_id=previous.source_geometry_revision_id,
            source_geometry_revision_id=cell.source_geometry_revision_id,
            previous_render_spec_checksum_sha256=previous.render_spec_checksum_sha256,
            render_spec_checksum_sha256=cell.render_spec_checksum_sha256,
            previous_rendered_pixel_checksum_sha256=previous.rendered_pixel_checksum_sha256,
            rendered_pixel_checksum_sha256=cell.rendered_pixel_checksum_sha256,
            extractor_version=cell.extractor_version,
            crop_sample_id=cell.crop_sample_id,
            crop_checksum_sha256=cell.crop_checksum_sha256,
            geometry_revision=cell.geometry_revision,
            cell_revision=cell.revision,
            action=action,
            previous_assigned_symbol_id=previous.assigned_symbol_id,
            assigned_symbol_id=cell.assigned_symbol_id,
            previous_review_state=previous.review_state,
            review_state=cell.review_state,
            previous_quality_issue=previous.quality_issue,
            quality_issue=cell.quality_issue,
            previous_verification_outcome=previous.verification_outcome,
            verification_outcome=cell.verification_outcome,
            previous_verified_symbol_id_v2=previous.verified_symbol_id_v2,
            verified_symbol_id_v2=cell.verified_symbol_id_v2,
            previous_approved_crop_sample_id=previous.approved_crop_sample_id,
            approved_crop_sample_id=cell.approved_crop_sample_id,
            previous_approved_crop_checksum_sha256=(previous.approved_crop_checksum_sha256),
            approved_crop_checksum_sha256=cell.approved_crop_checksum_sha256,
            previous_approved_geometry_revision=previous.approved_geometry_revision,
            approved_geometry_revision=cell.approved_geometry_revision,
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


def _verification_v2(
    *,
    review_state: str,
    quality_issue: str | None,
    assigned_symbol_id: UUID | None,
    prediction_symbol_code: str | None,
    assignment_source: str,
) -> PersistedVerificationV2:
    return verification_outcome_value(
        review_state=review_state,
        quality_issue=quality_issue,
        assigned_symbol_id=assigned_symbol_id,
        prediction_present=_known_symbol_code(prediction_symbol_code) is not None,
        assignment_source=assignment_source,
    )


def _quality_issue_from_model(cell: ImageSymbolReviewCellModel) -> str | None:
    return cell.quality_issue


def _is_human_cell_decision(cell: ImageSymbolReviewCellModel) -> bool:
    return (
        cell.review_state == SymbolCellReviewState.APPROVED.value
        or cell.quality_issue == SymbolCellQualityIssue.GRID_ISSUE.value
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
    verification = _verification_v2(
        review_state=target.review_state,
        quality_issue=target.quality_issue,
        assigned_symbol_id=target.assigned_symbol_id,
        prediction_symbol_code=review_cell.predicted_symbol_code,
        assignment_source=target.assignment_source,
    )
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
        and cell.quality_issue == target.quality_issue
        and cell.verification_outcome == verification.outcome
        and cell.verified_symbol_id_v2 == verification.verified_symbol_id
        and cell.approved_crop_sample_id == target.approved_crop_sample_id
        and cell.approved_crop_checksum_sha256 == target.approved_crop_checksum_sha256
        and cell.approved_geometry_revision == target.approved_geometry_revision
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
    cell.quality_issue = target.quality_issue
    verification = _verification_v2(
        review_state=target.review_state,
        quality_issue=target.quality_issue,
        assigned_symbol_id=target.assigned_symbol_id,
        prediction_symbol_code=review_cell.predicted_symbol_code,
        assignment_source=target.assignment_source,
    )
    cell.verification_outcome = verification.outcome
    cell.verified_symbol_id_v2 = verification.verified_symbol_id
    cell.approved_crop_sample_id = target.approved_crop_sample_id
    cell.approved_crop_checksum_sha256 = target.approved_crop_checksum_sha256
    cell.approved_geometry_revision = target.approved_geometry_revision
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
        else:
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
        finalize_when_exhausted: bool = True,
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
            report = (
                self.finalize_backfill(game_id)
                if finalize_when_exhausted
                else self._report_from_state(state)
            )
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

        for chunk in _iter_cell_insert_chunks(values):
            statement = postgresql_insert(ImageSymbolReviewCellModel).values(chunk)
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

    def begin_reconciliation_pass(self, game_id: UUID) -> SymbolCellReviewBackfillReport:
        state = self._session.get(ImageSymbolReviewStateModel, game_id, with_for_update=True)
        if state is None:
            raise SymbolCellReviewBackfillError(
                "SYMBOL_CELL_REVIEW_BACKFILL_NOT_STARTED",
                "Start the symbol-cell review backfill before reconciliation.",
            )
        state.status = "rebuilding"
        state.missing_sequence_count = 0
        state.invalid_crop_count = 0
        state.invalid_geometry_count = 0
        state.failure_message = None
        self._session.flush()
        return self._report_from_state(state)

    def reconcile_next_batch(
        self,
        game_id: UUID,
        *,
        batch_size: int = _DEFAULT_BATCH_SIZE,
    ) -> SymbolCellReviewReconciliationStep:
        if not 1 <= batch_size <= 500:
            raise ValueError("batch_size must be between 1 and 500")
        state = self._require_rebuilding_state(game_id)
        problem_ids = self._selected_problem_items(game_id)[:batch_size]
        if not problem_ids:
            return SymbolCellReviewReconciliationStep(
                report=self._report_from_state(state),
                processed_review_item_count=0,
                has_more=False,
            )

        coordinator = SymbolCellReviewWriteThroughCoordinator(self._session)
        processed = 0
        for review_item_id in problem_ids:
            coordinator.synchronize_for_backfill_reconciliation(
                game_id=game_id,
                review_item_id=review_item_id,
            )
            processed += 1
            if state.status == "failed":
                break
        state.cell_count = self._current_selected_cell_count(game_id)
        self._session.flush()
        return SymbolCellReviewReconciliationStep(
            report=self._report_from_state(
                state,
                sample_problem_review_item_ids=(problem_ids if state.status == "failed" else ()),
            ),
            processed_review_item_count=processed,
            has_more=state.status == "rebuilding" and len(problem_ids) == batch_size,
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
            revisions_by_board[geometry_revision_record.recognized_board_id] = (
                geometry_revision_record
            )
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
                        "quality_issue": None,
                        "approved_crop_sample_id": (
                            review.crop.crop_sample_id if approved else None
                        ),
                        "approved_crop_checksum_sha256": (
                            review.crop.crop_checksum_sha256 if approved else None
                        ),
                        "approved_geometry_revision": (
                            review.crop.geometry_revision if approved else None
                        ),
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

    def _selected_problem_items(self, game_id: UUID) -> tuple[UUID, ...]:
        return tuple(
            sorted(
                set(self._selected_items_without_exactly_fifteen_cells(game_id))
                | set(self._selected_items_with_stale_geometry(game_id))
                | set(self._selected_items_with_stale_base_crop(game_id)),
                key=str,
            )
        )

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
    "SqlAlchemyUnreadableBoardReviewRepository",
    "SymbolCellReviewWriteThroughCoordinator",
    "SqlAlchemyImageSymbolReviewRepository",
    "SymbolCellReviewBackfillError",
    "SymbolCellReviewBackfillReport",
    "SymbolCellReviewBackfillStep",
    "symbol_cell_review_projection_is_available",
]
