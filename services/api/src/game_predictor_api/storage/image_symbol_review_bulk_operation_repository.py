"""PostgreSQL persistence and recovery for durable bulk crop decisions."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Select, and_, func, insert, literal, select
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_api.application.image_symbol_review_bulk_operations import (
    SymbolCellReviewBulkFilterSelection,
    SymbolCellReviewBulkOperation,
    SymbolCellReviewBulkOperationRepository,
    SymbolCellReviewBulkOperationStatus,
    SymbolCellReviewBulkPreview,
    SymbolCellReviewBulkRequest,
    SymbolCellReviewBulkSelectionKind,
    SymbolCellReviewBulkTargetStatus,
)
from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationCommand,
)
from game_predictor_api.domain.catalog import SymbolStatus
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewAction,
    SymbolCellReviewError,
    SymbolCellReviewFilterState,
)
from game_predictor_api.domain.jobs import Job, JobType, create_job
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemySymbolCellReviewMutationRepository,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import (
    GameModel,
    ImageBoardSearchFastDocumentModel,
    ImageSymbolReviewBulkOperationModel,
    ImageSymbolReviewBulkTargetModel,
    ImageSymbolReviewCellModel,
    ImageSymbolReviewStateModel,
    RecognizedBoardModel,
    SymbolModel,
)

MAX_BULK_OPERATION_BOARDS_PER_BATCH = 100
_BULK_WORKFLOW = "image_symbol_review_bulk"
_CONFLICT_CODES = frozenset(
    {
        "SYMBOL_CELL_REVIEW_CELL_NOT_FOUND",
        "SYMBOL_CELL_REVIEW_BULK_TARGET_STATE_CONFLICT",
        "SYMBOL_CELL_REVIEW_CURRENT_OWNER_CONFLICT",
        "SYMBOL_CELL_REVIEW_CROP_DRIFT",
        "SYMBOL_CELL_REVIEW_REVISION_CONFLICT",
        "SYMBOL_CELL_REVIEW_TARGET_SYMBOL_INVALID",
        "SYMBOL_CELL_REVIEW_SYMBOL_INVALID",
    }
)


@dataclass(frozen=True, slots=True)
class SymbolCellReviewBulkWorkerProgress:
    operation: SymbolCellReviewBulkOperation
    has_pending_targets: bool


@dataclass(frozen=True, slots=True)
class _FrozenTarget:
    cell_review_id: UUID
    review_item_id: UUID
    recognized_board_id: UUID
    sequence_number: int
    cell_index: int
    expected_revision: int
    expected_geometry_revision: int
    expected_crop_sample_id: str
    expected_crop_checksum_sha256: str


class SqlAlchemySymbolCellReviewBulkOperationRepository(
    SymbolCellReviewBulkOperationRepository
):
    """Start/query operations inside the same request transaction as the snapshot."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def preview(
        self,
        *,
        game_id: UUID,
        request: SymbolCellReviewBulkRequest,
    ) -> SymbolCellReviewBulkPreview:
        state = _require_ready_state(self._session, game_id=game_id, for_update=False)
        _require_active_symbols(self._session, game_id=game_id, request=request)
        target_count, board_count = self._preview_counts(
            game_id=game_id,
            request=request,
            state=state,
        )
        return SymbolCellReviewBulkPreview(
            action=request.action,
            selection_kind=request.selection_kind,
            catalog_revision=int(state.catalog_revision),
            target_count=target_count,
            board_count=board_count,
            target_symbol_id=request.target_symbol_id,
        )

    def start(
        self,
        *,
        game_id: UUID,
        request: SymbolCellReviewBulkRequest,
        idempotency_key: UUID,
    ) -> tuple[SymbolCellReviewBulkOperation, bool]:
        state = _require_ready_state(self._session, game_id=game_id, for_update=True)
        existing = self._session.scalar(
            select(ImageSymbolReviewBulkOperationModel)
            .where(
                ImageSymbolReviewBulkOperationModel.game_id == game_id,
                ImageSymbolReviewBulkOperationModel.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )
        if existing is not None:
            if existing.command_sha256 != request.command_sha256:
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_BULK_IDEMPOTENCY_CONFLICT",
                    "The idempotency key already represents another bulk review command.",
                )
            return _operation_from_model(existing), False

        _require_active_symbols(self._session, game_id=game_id, request=request)
        target_count, _board_count = self._preview_counts(
            game_id=game_id,
            request=request,
            state=state,
        )
        operation_id = uuid4()
        job = SqlAlchemyJobRepository(self._session).add_job(
            create_job(
                JobType.IMAGE_SYMBOL_REVIEW_BULK,
                game_id=game_id,
                input_payload={
                    "schema_version": 1,
                    "workflow": _BULK_WORKFLOW,
                    "operation_id": str(operation_id),
                },
            )
        )
        filter_selection = request.filter_selection
        operation = ImageSymbolReviewBulkOperationModel(
            id=operation_id,
            game_id=game_id,
            job_id=job.id,
            action=request.action.value,
            target_symbol_id=request.target_symbol_id,
            selection_kind=request.selection_kind.value,
            filter_symbol_id=(
                None if filter_selection is None else filter_selection.symbol_id
            ),
            filter_state=(None if filter_selection is None else filter_selection.state.value),
            catalog_revision=(
                None if filter_selection is None else filter_selection.catalog_revision
            ),
            idempotency_key=idempotency_key,
            command_sha256=request.command_sha256,
            actor=request.actor.strip(),
            status=SymbolCellReviewBulkOperationStatus.CREATED.value,
            target_count=target_count,
            applied_count=0,
            conflict_count=0,
            failed_count=0,
        )
        self._session.add(operation)
        if request.filter_selection is not None:
            self._insert_filter_targets(
                game_id=game_id,
                operation_id=operation_id,
                selection=request.filter_selection,
            )
        else:
            self._session.add_all(
                ImageSymbolReviewBulkTargetModel(
                    operation_id=operation.id,
                    cell_review_id=target.cell_review_id,
                    review_item_id=target.review_item_id,
                    recognized_board_id=target.recognized_board_id,
                    sequence_number=target.sequence_number,
                    cell_index=target.cell_index,
                    expected_revision=target.expected_revision,
                    expected_geometry_revision=target.expected_geometry_revision,
                    expected_crop_sample_id=target.expected_crop_sample_id,
                    expected_crop_checksum_sha256=target.expected_crop_checksum_sha256,
                    status=SymbolCellReviewBulkTargetStatus.PENDING.value,
                )
                for target in self._snapshot_explicit_targets(game_id=game_id, request=request)
            )
        self._session.flush()
        return _operation_from_model(operation), True

    def get(self, *, game_id: UUID, operation_id: UUID) -> SymbolCellReviewBulkOperation | None:
        record = self._session.get(ImageSymbolReviewBulkOperationModel, operation_id)
        if record is None or record.game_id != game_id:
            return None
        return _operation_from_model(record)

    def _preview_counts(
        self,
        *,
        game_id: UUID,
        request: SymbolCellReviewBulkRequest,
        state: ImageSymbolReviewStateModel,
    ) -> tuple[int, int]:
        if request.filter_selection is not None:
            _require_fresh_filter_revision(
                selection=request.filter_selection,
                current_catalog_revision=int(state.catalog_revision),
            )
            visible_cells = _visible_cells_statement(
                game_id=game_id,
                selection=request.filter_selection,
            ).with_only_columns(
                ImageSymbolReviewCellModel.id,
                ImageSymbolReviewCellModel.review_item_id,
            )
            snapshot = visible_cells.subquery()
            target_count, board_count = self._session.execute(
                select(
                    func.count(snapshot.c.id),
                    func.count(func.distinct(snapshot.c.review_item_id)),
                )
            ).one()
            return int(target_count), int(board_count)

        targets = self._snapshot_explicit_targets(game_id=game_id, request=request)
        return len(targets), len({target.review_item_id for target in targets})

    def _snapshot_explicit_targets(
        self,
        *,
        game_id: UUID,
        request: SymbolCellReviewBulkRequest,
    ) -> tuple[_FrozenTarget, ...]:
        assert request.explicit_targets is not None
        requested = {target.cell_review_id: target for target in request.explicit_targets}
        rows = tuple(
            self._session.scalars(
                _visible_cells_statement(game_id=game_id).where(
                    ImageSymbolReviewCellModel.id.in_(tuple(requested))
                )
            )
        )
        actual = {row.id: row for row in rows}
        if len(actual) != len(requested):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_BULK_TARGET_NOT_CURRENT",
                "At least one explicit crop is no longer in the current game scope.",
            )
        frozen: list[_FrozenTarget] = []
        for target in request.explicit_targets:
            row = actual[target.cell_review_id]
            if (
                row.revision != target.expected_revision
                or row.geometry_revision != target.expected_geometry_revision
                or row.crop_sample_id != target.expected_crop_sample_id
                or row.crop_checksum_sha256 != target.expected_crop_checksum_sha256
            ):
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_BULK_TARGET_STALE",
                    "An explicit crop changed after it was selected. Reload and preview again.",
                    details={"cellReviewId": str(row.id)},
                )
            frozen.append(_frozen_target(row))
        return tuple(
            sorted(
                frozen,
                key=lambda target: (
                    target.sequence_number,
                    target.cell_index,
                    str(target.review_item_id),
                ),
            )
        )

    def _insert_filter_targets(
        self,
        *,
        game_id: UUID,
        operation_id: UUID,
        selection: SymbolCellReviewBulkFilterSelection,
    ) -> None:
        cell = ImageSymbolReviewCellModel
        visible_cells = _visible_cells_statement(
            game_id=game_id,
            selection=selection,
        )
        target_columns = (
            "operation_id",
            "cell_review_id",
            "review_item_id",
            "recognized_board_id",
            "sequence_number",
            "cell_index",
            "expected_revision",
            "expected_geometry_revision",
            "expected_crop_sample_id",
            "expected_crop_checksum_sha256",
            "status",
        )
        target_rows = visible_cells.with_only_columns(
            literal(operation_id),
            cell.id,
            cell.review_item_id,
            cell.recognized_board_id,
            cell.sequence_number,
            cell.cell_index,
            cell.revision,
            cell.geometry_revision,
            cell.crop_sample_id,
            cell.crop_checksum_sha256,
            literal(SymbolCellReviewBulkTargetStatus.PENDING.value),
        )
        self._session.execute(
            insert(ImageSymbolReviewBulkTargetModel).from_select(target_columns, target_rows)
        )


class SqlAlchemySymbolCellReviewBulkOperationWorker:
    """Claim and apply frozen targets in small, board-atomic transactions."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def operation_for_job(self, job: Job) -> SymbolCellReviewBulkOperation:
        if job.job_type is not JobType.IMAGE_SYMBOL_REVIEW_BULK or job.game_id is None:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_BULK_JOB_INVALID",
                "The worker job is not a symbol-cell bulk operation.",
            )
        operation_id = _operation_id_from_job(job)
        with self._session_factory() as session:
            operation = session.get(ImageSymbolReviewBulkOperationModel, operation_id)
            if (
                operation is None
                or operation.game_id != job.game_id
                or operation.job_id != job.id
            ):
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_BULK_OPERATION_MISSING",
                    "The durable symbol-cell bulk operation is unavailable for this job.",
                )
            return _operation_from_model(operation)

    def process_next_batch(
        self,
        *,
        job: Job,
        max_boards: int = MAX_BULK_OPERATION_BOARDS_PER_BATCH,
    ) -> SymbolCellReviewBulkWorkerProgress:
        if not 1 <= max_boards <= MAX_BULK_OPERATION_BOARDS_PER_BATCH:
            raise ValueError("max_boards must be between 1 and 100")
        operation_id = _operation_id_from_job(job)
        board_targets = self._next_pending_board_targets(
            operation_id=operation_id,
            max_boards=max_boards,
        )
        for targets in board_targets:
            self._apply_board_targets(job=job, operation_id=operation_id, targets=targets)
        with self._session_factory() as session, session.begin():
            operation = _locked_operation_for_job(session, job=job, operation_id=operation_id)
            _refresh_operation_counts(session, operation)
            pending = _pending_target_count(operation)
            if pending == 0:
                operation.status = SymbolCellReviewBulkOperationStatus.COMPLETED.value
                operation.completed_at = datetime.now(UTC)
                operation.error_code = None
                operation.error_message = None
            elif operation.status in {
                SymbolCellReviewBulkOperationStatus.CREATED.value,
                SymbolCellReviewBulkOperationStatus.CANCELLED.value,
                SymbolCellReviewBulkOperationStatus.FAILED.value,
            }:
                operation.status = SymbolCellReviewBulkOperationStatus.PROCESSING.value
                operation.completed_at = None
            session.flush()
            return SymbolCellReviewBulkWorkerProgress(
                operation=_operation_from_model(operation),
                has_pending_targets=pending > 0,
            )

    def mark_job_failed(self, *, job: Job, code: str, message: str) -> None:
        if job.job_type is not JobType.IMAGE_SYMBOL_REVIEW_BULK:
            return
        operation_id = _operation_id_from_job(job)
        with self._session_factory() as session, session.begin():
            operation = _locked_operation_for_job(session, job=job, operation_id=operation_id)
            operation.status = SymbolCellReviewBulkOperationStatus.FAILED.value
            operation.error_code = code[:100]
            operation.error_message = message[:1000]
            operation.completed_at = None

    def mark_job_cancelled(self, *, job: Job) -> None:
        if job.job_type is not JobType.IMAGE_SYMBOL_REVIEW_BULK:
            return
        operation_id = _operation_id_from_job(job)
        with self._session_factory() as session, session.begin():
            operation = _locked_operation_for_job(session, job=job, operation_id=operation_id)
            operation.status = SymbolCellReviewBulkOperationStatus.CANCELLED.value
            operation.completed_at = None

    def _next_pending_board_targets(
        self,
        *,
        operation_id: UUID,
        max_boards: int,
    ) -> tuple[tuple[_FrozenTarget, ...], ...]:
        with self._session_factory() as session:
            target = ImageSymbolReviewBulkTargetModel
            board_ids = (
                select(
                    target.review_item_id.label("review_item_id"),
                    func.min(target.sequence_number).label("sequence_number"),
                )
                .where(
                    target.operation_id == operation_id,
                    target.status == SymbolCellReviewBulkTargetStatus.PENDING.value,
                )
                .group_by(target.review_item_id)
                .order_by(func.min(target.sequence_number), target.review_item_id)
                .limit(max_boards)
                .subquery()
            )
            rows = tuple(
                session.scalars(
                    select(target)
                    .join(board_ids, board_ids.c.review_item_id == target.review_item_id)
                    .where(
                        target.operation_id == operation_id,
                        target.status == SymbolCellReviewBulkTargetStatus.PENDING.value,
                    )
                    .order_by(target.sequence_number, target.review_item_id, target.cell_index)
                )
            )
        grouped: dict[UUID, list[_FrozenTarget]] = defaultdict(list)
        for row in rows:
            grouped[row.review_item_id].append(
                _FrozenTarget(
                    cell_review_id=row.cell_review_id,
                    review_item_id=row.review_item_id,
                    recognized_board_id=row.recognized_board_id,
                    sequence_number=int(row.sequence_number),
                    cell_index=int(row.cell_index),
                    expected_revision=int(row.expected_revision),
                    expected_geometry_revision=int(row.expected_geometry_revision),
                    expected_crop_sample_id=row.expected_crop_sample_id,
                    expected_crop_checksum_sha256=row.expected_crop_checksum_sha256,
                )
            )
        return tuple(
            tuple(grouped[review_item_id])
            for review_item_id in sorted(
                grouped,
                key=lambda identifier: (
                    grouped[identifier][0].sequence_number,
                    str(identifier),
                ),
            )
        )

    def _apply_board_targets(
        self,
        *,
        job: Job,
        operation_id: UUID,
        targets: tuple[_FrozenTarget, ...],
    ) -> None:
        if not targets:
            return
        try:
            with self._session_factory() as session, session.begin():
                operation = _locked_operation_for_job(session, job=job, operation_id=operation_id)
                _require_target_symbol_still_active(session, operation=operation)
                mutation_repository = SqlAlchemySymbolCellReviewMutationRepository(session)
                commands: list[SymbolCellReviewMutationCommand] = []
                persisted_targets: list[ImageSymbolReviewBulkTargetModel] = []
                for target in targets:
                    persisted_target = session.get(
                        ImageSymbolReviewBulkTargetModel,
                        {
                            "operation_id": operation_id,
                            "cell_review_id": target.cell_review_id,
                        },
                        with_for_update=True,
                    )
                    if (
                        persisted_target is None
                        or persisted_target.status
                        != SymbolCellReviewBulkTargetStatus.PENDING.value
                    ):
                        raise SymbolCellReviewError(
                            "SYMBOL_CELL_REVIEW_BULK_TARGET_STATE_CONFLICT",
                            "A bulk crop target changed before its board could be processed.",
                        )
                    persisted_targets.append(persisted_target)
                    commands.append(
                        SymbolCellReviewMutationCommand(
                            game_id=operation.game_id,
                            cell_review_id=target.cell_review_id,
                            action=_action_from_model(operation),
                            expected_revision=target.expected_revision,
                            expected_geometry_revision=target.expected_geometry_revision,
                            expected_crop_sample_id=target.expected_crop_sample_id,
                            expected_crop_checksum_sha256=target.expected_crop_checksum_sha256,
                            target_symbol_id=operation.target_symbol_id,
                            actor=operation.actor,
                            operation_id=operation.id,
                        )
                    )
                results = mutation_repository.apply_board_mutations(tuple(commands))
                for persisted_target, result in zip(persisted_targets, results, strict=True):
                    persisted_target.status = SymbolCellReviewBulkTargetStatus.APPLIED.value
                    persisted_target.applied_cell_revision = result.cell_revision
                    persisted_target.error_code = None
                    persisted_target.error_message = None
                _refresh_operation_counts(session, operation)
        except SymbolCellReviewError as error:
            self._record_board_error(
                job=job,
                operation_id=operation_id,
                targets=targets,
                code=error.code,
                message=error.message,
            )

    def _record_board_error(
        self,
        *,
        job: Job,
        operation_id: UUID,
        targets: Iterable[_FrozenTarget],
        code: str,
        message: str,
    ) -> None:
        status = (
            SymbolCellReviewBulkTargetStatus.CONFLICT.value
            if code in _CONFLICT_CODES
            else SymbolCellReviewBulkTargetStatus.FAILED.value
        )
        with self._session_factory() as session, session.begin():
            operation = _locked_operation_for_job(session, job=job, operation_id=operation_id)
            for target in targets:
                persisted_target = session.get(
                    ImageSymbolReviewBulkTargetModel,
                    {"operation_id": operation_id, "cell_review_id": target.cell_review_id},
                    with_for_update=True,
                )
                if (
                    persisted_target is not None
                    and persisted_target.status == SymbolCellReviewBulkTargetStatus.PENDING.value
                ):
                    persisted_target.status = status
                    persisted_target.error_code = code[:100]
                    persisted_target.error_message = message[:1000]
            _refresh_operation_counts(session, operation)


def _require_ready_state(
    session: Session,
    *,
    game_id: UUID,
    for_update: bool,
) -> ImageSymbolReviewStateModel:
    if session.get(GameModel, game_id) is None:
        raise SymbolCellReviewError("GAME_NOT_FOUND", "The selected game does not exist.")
    statement = select(ImageSymbolReviewStateModel).where(
        ImageSymbolReviewStateModel.game_id == game_id
    )
    if for_update:
        statement = statement.with_for_update()
    state = session.scalar(statement)
    if state is None or state.status != "ready":
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_PROJECTION_INCOMPLETE",
            "The symbol-cell review projection is not ready for this game.",
            details={"status": None if state is None else state.status},
        )
    return state


def _require_fresh_filter_revision(
    *,
    selection: SymbolCellReviewBulkFilterSelection,
    current_catalog_revision: int,
) -> None:
    if selection.catalog_revision != current_catalog_revision:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_BULK_FILTER_STALE",
            "The filtered crop list changed after preview. Refresh the preview before starting.",
            details={
                "actualCatalogRevision": current_catalog_revision,
                "expectedCatalogRevision": selection.catalog_revision,
            },
        )


def _require_active_symbols(
    session: Session,
    *,
    game_id: UUID,
    request: SymbolCellReviewBulkRequest,
) -> None:
    symbol_ids = tuple(
        identifier
        for identifier in (
            request.target_symbol_id,
            None if request.filter_selection is None else request.filter_selection.symbol_id,
        )
        if identifier is not None
    )
    if not symbol_ids:
        return
    records = set(
        session.scalars(
            select(SymbolModel.id).where(
                SymbolModel.game_id == game_id,
                SymbolModel.id.in_(symbol_ids),
                SymbolModel.status == SymbolStatus.ACTIVE,
            )
        )
    )
    if set(symbol_ids) != records:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_TARGET_SYMBOL_INVALID",
            "A bulk review symbol is not active for this game.",
        )


def _visible_cells_statement(
    *,
    game_id: UUID,
    selection: SymbolCellReviewBulkFilterSelection | None = None,
) -> Select[tuple[ImageSymbolReviewCellModel]]:
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
            cell.game_id == game_id,
            cell.geometry_revision == RecognizedBoardModel.geometry_revision,
        )
    )
    if selection is None:
        return statement
    if selection.symbol_id is None:
        statement = statement.where(cell.assigned_symbol_id.is_(None))
    else:
        statement = statement.where(cell.assigned_symbol_id == selection.symbol_id)
    if selection.state is not SymbolCellReviewFilterState.ALL:
        statement = statement.where(cell.review_state == selection.state.value)
    if selection.excluded_cell_review_ids:
        statement = statement.where(cell.id.not_in(selection.excluded_cell_review_ids))
    return statement


def _frozen_target(cell: ImageSymbolReviewCellModel) -> _FrozenTarget:
    return _FrozenTarget(
        cell_review_id=cell.id,
        review_item_id=cell.review_item_id,
        recognized_board_id=cell.recognized_board_id,
        sequence_number=int(cell.sequence_number),
        cell_index=int(cell.cell_index),
        expected_revision=int(cell.revision),
        expected_geometry_revision=int(cell.geometry_revision),
        expected_crop_sample_id=cell.crop_sample_id,
        expected_crop_checksum_sha256=cell.crop_checksum_sha256,
    )


def _operation_id_from_job(job: Job) -> UUID:
    raw = job.input_payload.get("operation_id")
    if not isinstance(raw, str):
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_BULK_JOB_INVALID",
            "The bulk review job does not contain an operation id.",
        )
    try:
        return UUID(raw)
    except ValueError as error:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_BULK_JOB_INVALID",
            "The bulk review job has an invalid operation id.",
        ) from error


def _locked_operation_for_job(
    session: Session,
    *,
    job: Job,
    operation_id: UUID,
) -> ImageSymbolReviewBulkOperationModel:
    operation = session.scalar(
        select(ImageSymbolReviewBulkOperationModel)
        .where(ImageSymbolReviewBulkOperationModel.id == operation_id)
        .with_for_update()
    )
    if (
        operation is None
        or operation.game_id != job.game_id
        or operation.job_id != job.id
    ):
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_BULK_OPERATION_MISSING",
            "The durable bulk operation does not match the worker job.",
        )
    return operation


def _require_target_symbol_still_active(
    session: Session,
    *,
    operation: ImageSymbolReviewBulkOperationModel,
) -> None:
    if operation.target_symbol_id is None:
        return
    symbol = session.get(SymbolModel, operation.target_symbol_id)
    if (
        symbol is None
        or symbol.game_id != operation.game_id
        or symbol.status is not SymbolStatus.ACTIVE
    ):
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_TARGET_SYMBOL_INVALID",
            "The target symbol is no longer active for this game.",
        )


def _action_from_model(
    operation: ImageSymbolReviewBulkOperationModel,
) -> SymbolCellReviewAction:
    try:
        return SymbolCellReviewAction(operation.action)
    except ValueError as error:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_BULK_ACTION_INVALID",
            "The stored bulk operation contains an unsupported action.",
        ) from error


def _refresh_operation_counts(
    session: Session,
    operation: ImageSymbolReviewBulkOperationModel,
) -> None:
    rows = session.execute(
        select(ImageSymbolReviewBulkTargetModel.status, func.count())
        .where(ImageSymbolReviewBulkTargetModel.operation_id == operation.id)
        .group_by(ImageSymbolReviewBulkTargetModel.status)
    ).all()
    counts = {str(status): int(count) for status, count in rows}
    operation.applied_count = counts.get(SymbolCellReviewBulkTargetStatus.APPLIED.value, 0)
    operation.conflict_count = counts.get(SymbolCellReviewBulkTargetStatus.CONFLICT.value, 0)
    operation.failed_count = counts.get(SymbolCellReviewBulkTargetStatus.FAILED.value, 0)


def _pending_target_count(operation: ImageSymbolReviewBulkOperationModel) -> int:
    return (
        int(operation.target_count)
        - int(operation.applied_count)
        - int(operation.conflict_count)
        - int(operation.failed_count)
    )


def _operation_from_model(
    operation: ImageSymbolReviewBulkOperationModel,
) -> SymbolCellReviewBulkOperation:
    return SymbolCellReviewBulkOperation(
        id=operation.id,
        job_id=operation.job_id,
        game_id=operation.game_id,
        action=_action_from_model(operation),
        target_symbol_id=operation.target_symbol_id,
        selection_kind=SymbolCellReviewBulkSelectionKind(operation.selection_kind),
        status=SymbolCellReviewBulkOperationStatus(operation.status),
        catalog_revision=(
            None if operation.catalog_revision is None else int(operation.catalog_revision)
        ),
        target_count=int(operation.target_count),
        applied_count=int(operation.applied_count),
        conflict_count=int(operation.conflict_count),
        failed_count=int(operation.failed_count),
        pending_count=_pending_target_count(operation),
        error_code=operation.error_code,
        error_message=operation.error_message,
        command_sha256=operation.command_sha256,
    )


__all__ = [
    "MAX_BULK_OPERATION_BOARDS_PER_BATCH",
    "SqlAlchemySymbolCellReviewBulkOperationRepository",
    "SqlAlchemySymbolCellReviewBulkOperationWorker",
    "SymbolCellReviewBulkWorkerProgress",
]
