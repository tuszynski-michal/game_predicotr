"""Persistence and resumable backfill for checksum-bound symbol-cell review."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from threading import Event, Lock
from typing import Any, Literal, Protocol, TypedDict, cast
from uuid import UUID, uuid4

from sqlalchemy import (
    Integer,
    String,
    and_,
    case,
    column,
    delete,
    exists,
    false,
    func,
    or_,
    select,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, aliased, load_only
from sqlalchemy.sql import ColumnElement, Select

from game_predictor_api.application.image_reviews import OperationalImageReviewService
from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationCommand,
    SymbolCellReviewMutationRepository,
    SymbolCellReviewMutationResult,
)
from game_predictor_api.application.image_symbol_reviews import (
    SymbolCellReviewCatalogState,
    SymbolCellReviewListSlice,
    SymbolCellReviewQueryRepository,
)
from game_predictor_api.application.unreadable_board_reviews import (
    ResolveUnreadableCellCommand,
    SaveUnreadableBoardCommand,
    SaveUnreadableBoardResult,
    UnreadableBoardReviewCell,
    UnreadableBoardReviewDetail,
    UnreadableBoardReviewListItem,
    UnreadableBoardReviewRepository,
    UnreadableBoardReviewSlice,
    UnreadableBoardReviewView,
)
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.catalog import SymbolStatus
from game_predictor_api.domain.geometry_qualification import (
    GEOMETRY_QUALIFICATION_VERSION_V3,
    available_cell_indices,
    partially_visible_cell_indices,
)
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError
from game_predictor_api.domain.image_reviews import (
    ImageReviewAction,
    ImageReviewCell,
    ImageReviewResolutionCell,
    canonical_image_review_bytes,
)
from game_predictor_api.domain.image_symbol_reviews import (
    REFERENCE_LIBRARY_PREDICTION_MODEL_VERSION,
    RGB_V2_PREDICTION_MODEL_VERSION,
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
    SymbolCellReviewPredictionSource,
    SymbolCellReviewState,
    SymbolCellReviewTransition,
    SymbolCellWithoutImageIdentity,
    approve_symbol_cell_review,
    derive_symbol_cell_board_resolution,
    invalidate_symbol_cell_reviews_for_geometry,
    map_current_symbol_cell_reviews,
    mark_symbol_cell_blurry,
    mark_symbol_cell_grid_issue,
    mark_symbol_cell_unreadable,
    reassign_symbol_cell_review,
    resolve_unreadable_symbol_cell_review,
    symbol_cell_approval_pixels_changed,
)
from game_predictor_api.domain.jobs import JobStatus, JobType
from game_predictor_api.storage.additive_virtual_geometry_contracts import (
    PersistedVerificationV2,
    optional_verification_outcome_value,
    verification_outcome_value,
)
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.cell_render_specs import (
    CellRenderSpecKey,
    load_cell_render_specs,
)
from game_predictor_api.storage.current_board_cell_sources import (
    NO_CELL_SOURCES,
    CurrentBoardCellSources,
    load_current_board_cell_source,
    load_current_board_cell_sources,
)
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
)
from game_predictor_api.storage.image_geometry_completeness_state_repository import (
    _manual_neural_lattice_approved,
    withheld_review_item_ids,
)
from game_predictor_api.storage.models import (
    BoardRenderManifestModel,
    GameModel,
    GameSymbolModelActivationModel,
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
    SymbolModelIterationModel,
    VerifiedTrainingCohortCellModel,
)
from game_predictor_api.storage.super_game_input_version import record_super_game_input_change
from game_predictor_api.storage.symbol_cell_source_visibility import (
    current_source_visibilities,
    pinned_visibility_geometry,
    qualification_visibilities,
)

_ACTIVE_REVIEW_STATUSES = frozenset({"pending", "accepted", "corrected"})
_DEFAULT_BATCH_SIZE = 200
_MAX_CELL_ROWS_PER_INSERT = 1_000
_BACKFILL_ACTOR = "system:symbol-cell-backfill"
_WRITE_THROUGH_ACTOR = "system:symbol-cell-write-through"
_CELL_REVIEW_TRANSACTION_MARKER = "symbol_cell_review_catalog_revision_transaction"
_TEMPORARILY_UNRECOGNIZED_QUALITY_ISSUES = (
    SymbolCellQualityIssue.GRID_ISSUE.value,
    SymbolCellQualityIssue.UNREADABLE.value,
)
_COUNT_SCOPE_ALL = "all"
_COUNT_SCOPE_UNKNOWN = "unknown"
_COUNT_SCOPE_OUTSIDE = "outside"
_COUNT_SEMANTICS_KEY = "_semantics"
_COUNT_SEMANTICS = {"version": 2}
_COUNT_STATES = (
    SymbolCellReviewState.APPROVED.value,
    SymbolCellReviewState.PENDING.value,
)


@dataclass(frozen=True, slots=True)
class _CountedCellState:
    source_available: bool
    assigned_symbol_id: UUID | None
    review_state: str
    quality_issue: str | None
    source_visibility: str | None = None

    @classmethod
    def from_model(cls, cell: ImageSymbolReviewCellModel) -> _CountedCellState:
        return cls(
            source_available=cell.source_available,
            source_visibility=cell.source_visibility,
            assigned_symbol_id=cell.assigned_symbol_id,
            review_state=cell.review_state,
            quality_issue=_quality_issue_from_model(cell),
        )


def _logical_cell_visible_clause() -> ColumnElement[bool]:
    """Cells that take part in symbol verification (lists, counts, bulk scopes).

    A cell is visible when it has source pixels (or is a fully outside cell)
    and its review item is not rejected (TASK-0949, W7): a rejected board
    leaves symbol verification while its rows and decision history stay, so
    reverting the rejection brings it back unchanged.
    """

    cell = ImageSymbolReviewCellModel
    owner = aliased(ImageReviewItemModel)
    # An uncorrelated ``NOT IN`` over the (small) set of rejected items: hashed once
    # per statement, and no extra EXISTS next to the prediction-revision filters.
    # ``review_item_id`` is NOT NULL, so the NULL rule of ``NOT IN`` never applies.
    return and_(
        or_(cell.source_available.is_(True), cell.source_visibility == "outside"),
        cell.review_item_id.not_in(select(owner.id).where(owner.status == "rejected")),
    )


def _count_scope_keys(cell: _CountedCellState | None) -> tuple[str, ...]:
    if cell is None or cell.review_state not in _COUNT_STATES:
        return ()
    if not cell.source_available and cell.source_visibility != "outside":
        return ()
    if cell.source_visibility == "outside":
        scope = (
            _COUNT_SCOPE_OUTSIDE
            if cell.assigned_symbol_id is None
            else f"symbol:{cell.assigned_symbol_id}"
        )
    elif (
        cell.assigned_symbol_id is None
        or cell.quality_issue in _TEMPORARILY_UNRECOGNIZED_QUALITY_ISSUES
    ):
        scope = _COUNT_SCOPE_UNKNOWN
    else:
        scope = f"symbol:{cell.assigned_symbol_id}"
    return (_COUNT_SCOPE_ALL, scope)


def _symbol_scope_filter_clause(review_filter: SymbolCellReviewListFilter) -> ColumnElement[bool]:
    """One mutually exclusive grouping shared by pages, counts and bulk snapshots."""
    cell = ImageSymbolReviewCellModel
    outside = cell.source_visibility == "outside"
    inside = cell.source_visibility.is_distinct_from("outside")
    if review_filter.include_all_symbols:
        return _logical_cell_visible_clause()
    if review_filter.outside_only:
        return and_(outside, cell.assigned_symbol_id.is_(None))
    if review_filter.symbol_id is None:
        return and_(
            inside,
            or_(
                cell.assigned_symbol_id.is_(None),
                cell.quality_issue.in_(_TEMPORARILY_UNRECOGNIZED_QUALITY_ISSUES),
            ),
        )
    return and_(
        cell.assigned_symbol_id == review_filter.symbol_id,
        or_(
            outside,
            cell.quality_issue.is_(None),
            cell.quality_issue.not_in(_TEMPORARILY_UNRECOGNIZED_QUALITY_ISSUES),
        ),
    )


def _count_semantics_current(state: ImageSymbolReviewStateModel) -> bool:
    return state.count_projection.get(_COUNT_SEMANTICS_KEY) == _COUNT_SEMANTICS


def _count_deltas(
    before: Sequence[_CountedCellState],
    after: Sequence[_CountedCellState],
) -> Counter[tuple[str, str]]:
    delta: Counter[tuple[str, str]] = Counter()
    for sign, cells in ((-1, before), (1, after)):
        for cell in cells:
            for scope in _count_scope_keys(cell):
                delta[(scope, cell.review_state)] += sign
    return delta


def _apply_count_delta_payload(
    payload: Mapping[str, object],
    deltas: Mapping[tuple[str, str], int],
) -> dict[str, object]:
    updated: dict[str, object] = {
        str(scope): dict(cast(Mapping[str, object], counts))
        for scope, counts in payload.items()
        if isinstance(scope, str) and isinstance(counts, Mapping)
    }
    for (scope, review_state), delta in sorted(deltas.items()):
        if delta == 0:
            continue
        counts = cast(dict[str, object], updated.setdefault(scope, {}))
        current = counts.get(review_state, 0)
        if not isinstance(current, int) or isinstance(current, bool):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_COUNT_PROJECTION_INVALID",
                "The stored symbol review count projection is invalid.",
            )
        next_count = current + delta
        if next_count < 0:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_COUNT_PROJECTION_NEGATIVE",
                "A symbol review mutation would make an exact count negative.",
                details={"scope": scope, "state": review_state},
            )
        counts[review_state] = next_count
    return updated


def _apply_count_deltas(
    state: ImageSymbolReviewStateModel,
    *,
    before: Sequence[_CountedCellState] = (),
    after: Sequence[_CountedCellState] = (),
) -> bool:
    if state.count_projection_status not in {"ready", "rebuilding"}:
        return False
    if state.count_projection_status == "ready" and not _count_semantics_current(state):
        state.count_projection_status = "unavailable"
        state.count_projection_failure_message = (
            "Count semantics changed; run bounded count rebuild."
        )
        return False
    deltas = _count_deltas(before, after)
    if not any(deltas.values()):
        return False
    if (
        state.count_projection_status == "rebuilding"
        and state.count_rebuild_accumulator.get("_building") == _COUNT_SEMANTICS
    ):
        # The writer holds the same state lock as each rebuild batch. A write
        # may precede the UUID cursor, so restart instead of publishing a mixed snapshot.
        state.count_rebuild_cursor = None
        state.count_rebuild_accumulator = {"_building": dict(_COUNT_SEMANTICS)}
        return False
    if (
        state.count_projection_status == "rebuilding"
        and state.count_projection.get("_building_semantics") != _COUNT_SEMANTICS
    ):
        state.count_projection_status = "unavailable"
        state.count_projection_failure_message = (
            "Historical count rebuild requires restart with current semantics."
        )
        return False
    state.count_projection = _apply_count_delta_payload(state.count_projection, deltas)
    state.count_projection_revision += 1
    return True


class _SafeCancelableDriverConnection(Protocol):
    def cancel_safe(self, *, timeout: float = 30.0) -> None: ...


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


def _database_error_sqlstate(error: DBAPIError) -> str | None:
    original = error.orig
    sqlstate = getattr(original, "sqlstate", None)
    if isinstance(sqlstate, str):
        return sqlstate
    pgcode = getattr(original, "pgcode", None)
    return pgcode if isinstance(pgcode, str) else None


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


def _bind_game_store(session: Session, game_id: UUID) -> None:
    """Bind the session to the game's store before the first cell statement.

    The bind sets the search path, the game id and the storage generation used
    by row-level security, independently of an ambient ``game_storage_scope``.
    Every repository path that queries cells without such a scope calls it once
    before its first statement (see ``test_cell_paths_bind_the_game_store``).
    """

    GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)


def _backfill_cell_conflict_columns(
    session: Session,
    game_id: UUID,
) -> tuple[str, ...]:
    """Match the physical uniqueness rule of the V2 game store."""

    _bind_game_store(session, game_id)
    return ("game_id", "review_item_id", "cell_index")


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
    # D-484 (TASK-0807): boards of incomplete images skipped with the reason
    # ``SOURCE_IMAGE_GEOMETRY_INCOMPLETE``; they are cut once admitted.
    geometry_withheld_review_item_count: int = 0


@dataclass(frozen=True, slots=True)
class SymbolCellReviewReconciliationStep:
    report: SymbolCellReviewBackfillReport
    processed_review_item_count: int
    has_more: bool


class SqlAlchemySymbolCellReviewQueryRepository(SymbolCellReviewQueryRepository):
    """Bounded current-owner reads for the local Admin workspace.

    A V2 store keeps exactly one current row per logical ``game + sequence``
    cell position, so reads filter the cell projection directly without an
    ownership join.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._active_read_lock = Lock()
        self._active_read_connection: _SafeCancelableDriverConnection | None = None
        self._active_read_operation: str | None = None
        self._read_cancel_requested = Event()

    @contextmanager
    def bounded_read(self, *, timeout_ms: int, operation: str) -> Iterator[None]:
        if timeout_ms <= 0:
            raise ValueError("Symbol-cell review statement timeout must be positive.")
        self._raise_if_read_cancelled(operation=operation)
        sqlalchemy_connection = self._session.connection()
        driver_connection = cast(
            _SafeCancelableDriverConnection,
            sqlalchemy_connection.connection.driver_connection,
        )
        with self._active_read_lock:
            if self._active_read_connection is not None:
                raise RuntimeError("A symbol-cell review read is already active in this session.")
            self._active_read_connection = driver_connection
            self._active_read_operation = operation
        try:
            self._raise_if_read_cancelled(operation=operation)
            self._session.execute(
                text("SELECT set_config('statement_timeout', :timeout, true)"),
                {"timeout": f"{timeout_ms}ms"},
            )
            self._raise_if_read_cancelled(operation=operation)
            yield
        except DBAPIError as error:
            if _database_error_sqlstate(error) != "57014":
                raise
            if self._read_cancel_requested.is_set():
                raise self._cancelled_error(operation=operation) from error
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_QUERY_TIMEOUT",
                "The symbol-cell review query exceeded its server-side time limit.",
                details={"operation": operation, "timeoutMs": timeout_ms},
            ) from error
        finally:
            with self._active_read_lock:
                if self._active_read_connection is driver_connection:
                    self._active_read_connection = None
                    self._active_read_operation = None

    def mark_active_read_cancelled(self) -> None:
        """Persist transport cancellation for every remaining SQL stage."""

        self._read_cancel_requested.set()

    def cancel_active_read(self) -> bool:
        """Thread-safely interrupt only the PostgreSQL read owned by this request."""

        with self._active_read_lock:
            connection = self._active_read_connection
            if connection is None:
                return False
            connection.cancel_safe(timeout=1.0)
            return True

    def _raise_if_read_cancelled(self, *, operation: str | None = None) -> None:
        if self._read_cancel_requested.is_set():
            raise self._cancelled_error(operation=operation)

    def _cancelled_error(self, *, operation: str | None = None) -> SymbolCellReviewError:
        return SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_QUERY_CANCELLED",
            "The symbol-cell review query was cancelled after the client disconnected.",
            details={"operation": operation or self._active_read_operation or "unknown"},
        )

    def require_ready_game(self, game_id: UUID) -> SymbolCellReviewCatalogState:
        self._raise_if_read_cancelled()
        if self._session.get(GameModel, game_id) is None:
            raise SymbolCellReviewError(
                "GAME_NOT_FOUND",
                "The selected game does not exist.",
                details={"gameId": str(game_id)},
            )
        self._raise_if_read_cancelled()
        state = self._session.get(ImageSymbolReviewStateModel, game_id)
        self._raise_if_read_cancelled()
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
        location = GameStorageRouter().bind(self._session, game_id, intent=GameStorageIntent.READ)
        return SymbolCellReviewCatalogState(
            catalog_revision=int(state.catalog_revision),
            storage_generation=location.generation,
        )

    def active_model_cohort_id(self, game_id: UUID) -> UUID | None:
        self._raise_if_read_cancelled()
        current = self._session.scalar(
            select(GameSymbolModelActivationModel)
            .where(GameSymbolModelActivationModel.game_id == game_id)
            .order_by(GameSymbolModelActivationModel.activation_number.desc())
            .limit(1)
        )
        if current is None or current.model_iteration_id is None:
            return None
        return cast(
            UUID | None,
            self._session.scalar(
                select(SymbolModelIterationModel.cohort_id)
                .where(SymbolModelIterationModel.id == current.model_iteration_id)
                .where(SymbolModelIterationModel.game_id == game_id)
                .limit(1)
            ),
        )

    def _seek_visible_keys(
        self,
        *,
        review_filter: SymbolCellReviewListFilter,
        seek_key: tuple[int, int, UUID] | None,
        descending: bool,
        needed_count: int,
    ) -> list[tuple[int, int, UUID]]:
        """Walk the indexed candidate seek, returning up to ``needed_count``
        currently-visible keys in seek order.

        Shared by full-page hydration and cursor-only skipping so both agree
        exactly on what counts as a visible item and on batch/cancellation
        behaviour; only the caller decides whether to hydrate the result.
        """
        statement = self._candidate_seek_statement(review_filter=review_filter)
        sequence, cell_index, cell_key = _symbol_cell_review_order_columns()
        visible_keys: list[tuple[int, int, UUID]] = []
        seek_batch_size = max(needed_count, 1_000)
        while len(visible_keys) < needed_count:
            self._raise_if_read_cancelled()
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
                cell_key.desc() if descending else cell_key,
            ).limit(seek_batch_size)
            candidate_rows = self._session.execute(batch_statement).all()
            if not candidate_rows:
                break
            self._raise_if_read_cancelled()
            visible_keys.extend(
                (int(row[1]), int(row[2]), cast(UUID, row[3])) for row in candidate_rows
            )
            last = candidate_rows[-1]
            seek_key = (int(last[1]), int(last[2]), cast(UUID, last[3]))
            if len(candidate_rows) < seek_batch_size:
                break
        return visible_keys

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
        seek_key = before_key if before_key is not None else after_key
        descending = before_key is not None
        visible_keys = self._seek_visible_keys(
            review_filter=review_filter,
            seek_key=seek_key,
            descending=descending,
            needed_count=limit + 1,
        )
        visible_ids = [key[2] for key in visible_keys]

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
        self._raise_if_read_cancelled()
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

    def skip_keys(
        self,
        *,
        review_filter: SymbolCellReviewListFilter,
        after_key: tuple[int, int, UUID] | None,
        before_key: tuple[int, int, UUID] | None,
        count: int,
    ) -> tuple[int, int, UUID] | None:
        if after_key is not None and before_key is not None:
            raise ValueError("only one symbol-cell review keyset direction is allowed")
        if count < 1:
            raise ValueError("symbol-cell review skip count must be positive")
        seek_key = before_key if before_key is not None else after_key
        descending = before_key is not None
        visible_keys = self._seek_visible_keys(
            review_filter=review_filter,
            seek_key=seek_key,
            descending=descending,
            needed_count=count,
        )
        if len(visible_keys) < count:
            return None
        return visible_keys[count - 1]

    def counts(self, *, review_filter: SymbolCellReviewListFilter) -> SymbolCellReviewCounts:
        self._raise_if_read_cancelled()
        scope = self._basic_count_scope(review_filter)
        if scope is not None:
            state = self._session.get(ImageSymbolReviewStateModel, review_filter.game_id)
            if (
                state is None
                or state.count_projection_status != "ready"
                or not _count_semantics_current(state)
            ):
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_COUNTS_UNAVAILABLE",
                    "Exact symbol review counts are being prepared for this game.",
                    details={
                        "status": (
                            "unavailable" if state is None else state.count_projection_status
                        )
                    },
                )
            raw_counts = state.count_projection.get(scope, {})
            if not isinstance(raw_counts, Mapping):
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_COUNT_PROJECTION_INVALID",
                    "The stored symbol review count projection is invalid.",
                )
            approved_count = raw_counts.get(SymbolCellReviewState.APPROVED.value, 0)
            pending_count = raw_counts.get(SymbolCellReviewState.PENDING.value, 0)
            if any(
                not isinstance(value, int) or isinstance(value, bool) or value < 0
                for value in (approved_count, pending_count)
            ):
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_COUNT_PROJECTION_INVALID",
                    "The stored symbol review count projection is invalid.",
                )
            if review_filter.state is SymbolCellReviewFilterState.APPROVED:
                pending_count = 0
            elif review_filter.state is SymbolCellReviewFilterState.PENDING:
                approved_count = 0
            return SymbolCellReviewCounts(
                all_count=approved_count + pending_count,
                approved_count=approved_count,
                pending_count=pending_count,
            )
        approved_count, pending_count = self._session.execute(
            self._count_statement(review_filter=review_filter)
        ).one()
        return SymbolCellReviewCounts(
            all_count=int(approved_count) + int(pending_count),
            approved_count=int(approved_count),
            pending_count=int(pending_count),
        )

    @staticmethod
    def _basic_count_scope(review_filter: SymbolCellReviewListFilter) -> str | None:
        if (
            review_filter.state is SymbolCellReviewFilterState.ACTIVE_MODEL_COHORT
            or review_filter.min_confidence is not None
            or review_filter.max_confidence is not None
            or review_filter.has_extended_filters
        ):
            return None
        if review_filter.include_all_symbols:
            return _COUNT_SCOPE_ALL
        if review_filter.outside_only:
            return _COUNT_SCOPE_OUTSIDE
        if review_filter.symbol_id is None:
            return _COUNT_SCOPE_UNKNOWN
        return f"symbol:{review_filter.symbol_id}"

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
        source_geometry = ImageSourceGeometryRevisionModel
        statement = select(
            cell,
            RecognizedBoardModel.geometry_revision,
            RecognizedBoardModel.source_geometry_revision_id,
            SourceImageModel.checksum_sha256,
            source_geometry.normalized_pixel_checksum_sha256,
            source_geometry.geometry_checksum_sha256,
        )
        _bind_game_store(self._session, game_id)
        rows = self._session.execute(
            statement.join(
                RecognizedBoardModel, RecognizedBoardModel.id == cell.recognized_board_id
            )
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .outerjoin(
                source_geometry,
                source_geometry.id == cell.source_geometry_revision_id,
            )
            .where(cell.game_id == game_id, cell.id.in_(cell_review_ids), cell.asset_mode != "none")
        ).all()
        # D-467 S7 (TASK-0792): the render specification comes from the board
        # render manifest of the cell's revision, verified against the cell's
        # checksum; the cell column is no longer read.  A drifted virtual cell
        # is rejected here, as the application layer would reject it anyway.
        virtual_keys: dict[UUID, CellRenderSpecKey] = {}
        for review_cell, current_geometry_revision, current_source_id, *_ in rows:
            # D-467 S6 (TASK-0796): an image cell is always a virtual render.
            if review_cell.asset_mode != "virtual_source":
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_ASSET_MODE_UNSUPPORTED",
                    "Only virtual_source symbol-cell assets can be served.",
                )
            if (
                review_cell.geometry_revision != int(current_geometry_revision)
                or review_cell.source_geometry_revision_id != current_source_id
            ):
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_CROP_DRIFT",
                    "The symbol-cell crop no longer belongs to the current geometry revision.",
                )
            if review_cell.render_spec_checksum_sha256 is None:
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_VIRTUAL_PROVENANCE_INVALID",
                    "A virtual symbol review cell has no render checksum.",
                )
            virtual_keys[review_cell.id] = CellRenderSpecKey(
                recognized_board_id=review_cell.recognized_board_id,
                geometry_revision=review_cell.geometry_revision,
                cell_index=review_cell.cell_index,
                render_spec_checksum_sha256=review_cell.render_spec_checksum_sha256,
            )
        render_specs = load_cell_render_specs(
            self._session, game_id=game_id, keys=virtual_keys.values()
        )
        return tuple(
            SymbolCellReviewAsset(
                cell_review_id=review_cell.id,
                crop_relative_path=review_cell.crop_relative_path,
                crop_checksum_sha256=review_cell.crop_checksum_sha256,
                geometry_revision=review_cell.geometry_revision,
                current_geometry_revision=int(current_geometry_revision),
                revision=review_cell.revision,
                asset_mode=review_cell.asset_mode,
                source_checksum_sha256=source_checksum,
                normalized_pixel_checksum_sha256=normalized_pixel_checksum,
                source_geometry_revision_id=review_cell.source_geometry_revision_id,
                current_source_geometry_revision_id=current_source_geometry_revision_id,
                geometry_checksum_sha256=geometry_checksum,
                logical_cell_key=review_cell.logical_cell_key,
                render_spec=render_specs[virtual_keys[review_cell.id]],
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
        statement = (
            self._visible_statement(review_filter=review_filter)
            .add_columns(
                ImageReviewItemModel.status.label("board_status"),
                assigned_symbol.id.label("assigned_symbol_id"),
                assigned_symbol.code.label("assigned_symbol_code"),
                assigned_symbol.name.label("assigned_symbol_name"),
                cell.prediction_confidence.label("prediction_confidence"),
            )
            .outerjoin(assigned_symbol, assigned_symbol.id == cell.assigned_symbol_id)
            .join(ImageReviewItemModel, ImageReviewItemModel.id == cell.review_item_id)
        )
        return statement.options(
            load_only(
                cell.id,
                cell.review_item_id,
                cell.recognized_board_id,
                cell.import_job_id,
                cell.sequence_number,
                cell.cell_index,
                cell.row_index,
                cell.column_index,
                cell.assigned_symbol_id,
                cell.prediction_symbol_code,
                cell.review_state,
                cell.quality_issue,
                cell.revision,
                cell.geometry_revision,
                cell.crop_sample_id,
                cell.crop_relative_path,
                cell.crop_checksum_sha256,
                cell.cropper_version,
                cell.asset_mode,
                cell.source_visibility,
                cell.render_spec_checksum_sha256,
                cell.assignment_source,
                cell.approved_crop_sample_id,
                cell.approved_crop_checksum_sha256,
                cell.approved_geometry_revision,
            )
        )

    def _candidate_seek_statement(
        self,
        *,
        review_filter: SymbolCellReviewListFilter,
    ) -> Select[Any]:
        """Seek indexed candidates without joins that could force a global sort."""

        cell = ImageSymbolReviewCellModel
        return _visible_cell_scope(
            select(cell.id, cell.sequence_number, cell.cell_index, cell.id),
            review_filter=review_filter,
        )

    def _visible_statement(self, *, review_filter: SymbolCellReviewListFilter) -> Select[Any]:
        return _visible_cell_scope(
            select(ImageSymbolReviewCellModel),
            review_filter=review_filter,
        )

    def _count_statement(self, *, review_filter: SymbolCellReviewListFilter) -> Select[Any]:
        """Aggregate a ready current-owner projection with the narrowest safe joins."""

        cell = ImageSymbolReviewCellModel
        return self._visible_statement(review_filter=review_filter).with_only_columns(
            func.count().filter(cell.review_state == SymbolCellReviewState.APPROVED.value),
            func.count().filter(cell.review_state == SymbolCellReviewState.PENDING.value),
            maintain_column_froms=True,
        )


def _visible_cell_scope(
    statement: Select[Any],
    *,
    review_filter: SymbolCellReviewListFilter,
) -> Select[Any]:
    """Restrict a cell statement to the current V2 cells of one list scope.

    A V2 store keeps one mutable current row per logical board position, so
    every visible row is already its position's current owner and needs no
    ownership join. Listing, counting and seeking do not join geometry
    (unchanged V2 behaviour); bulk operations and ``_locked_current_rows``
    keep the ``geometry_revision`` guard.
    """

    cell = ImageSymbolReviewCellModel
    statement = statement.where(
        cell.game_id == review_filter.game_id, _logical_cell_visible_clause()
    )
    if not review_filter.include_all_symbols:
        statement = statement.where(_symbol_scope_filter_clause(review_filter))
    statement = _apply_symbol_cell_review_state_filter(
        statement,
        review_filter=review_filter,
    )
    if review_filter.min_confidence is not None:
        statement = statement.where(cell.prediction_confidence >= review_filter.min_confidence)
    if review_filter.max_confidence is not None:
        statement = statement.where(cell.prediction_confidence <= review_filter.max_confidence)
    if review_filter.min_confidence is not None or review_filter.max_confidence is not None:
        # Outside cells require NULL confidence by the source-asset CHECK, so
        # every confidence match is already source-available. Expose the bare
        # boolean predicate used by the partial confidence index to PostgreSQL.
        statement = statement.where(cell.source_available)
    return statement.where(*extended_symbol_cell_review_filter_clauses(review_filter))


def _current_prediction_entry_exists(
    *,
    revision_alias: str,
    model_version: str,
    marker_key: str,
    marker_fields: Mapping[str, str],
) -> ColumnElement[bool]:
    """Whether the cell's own entry in its current prediction revision carries a writer marker.

    Aliased and correlated to the cell only: some enclosing statements already join the cell's
    prediction revision, which auto-correlation would otherwise swallow.  A rewriting revision
    copies the whole board, so only the entries the writer rewrote carry its marker and the
    source is decided per cell, not per revision.  The entry's ``marker_key`` value must be a JSON
    object containing ``marker_fields`` (no fields matches any object).
    """

    cell = ImageSymbolReviewCellModel
    revision = aliased(ImageSymbolPredictionRevisionModel, name=revision_alias)
    marker_object = func.jsonb_build_object(
        *(argument for item in marker_fields.items() for argument in item)
    )
    return (
        select(revision.id)
        .where(
            revision.game_id == cell.game_id,
            revision.id == cell.prediction_revision_id,
            revision.model_version == model_version,
            revision.predictions.contains(
                func.jsonb_build_array(
                    func.jsonb_build_object(
                        "rowIndex",
                        cell.row_index,
                        "columnIndex",
                        cell.column_index,
                        marker_key,
                        marker_object,
                    )
                )
            ),
        )
        .correlate(cell)
        .exists()
    )


def extended_symbol_cell_review_filter_clauses(
    review_filter: SymbolCellReviewListFilter,
) -> tuple[ColumnElement[bool], ...]:
    """Extended conditions shared by pages, counts and bulk scopes."""

    cell = ImageSymbolReviewCellModel
    clauses: list[ColumnElement[bool]] = []
    source = review_filter.prediction_source
    if source is not None:
        # Each writer has its own correlated EXISTS (own alias) so ``model`` can exclude both.
        if source is SymbolCellReviewPredictionSource.REFERENCE_LIBRARY:
            clauses.append(_reference_library_entry_exists())
        elif source is SymbolCellReviewPredictionSource.RGB_V2:
            clauses.append(_rgb_v2_entry_exists())
        elif source is SymbolCellReviewPredictionSource.RGB_V2_TENTATIVE:
            clauses.append(_rgb_v2_entry_exists(status="tentative"))
        else:
            # ``model`` is whatever neither the library nor RGB v2 wrote.
            clauses.append(~_reference_library_entry_exists())
            clauses.append(~_rgb_v2_entry_exists())
    if review_filter.changed_from is not None:
        clauses.append(cell.updated_at >= review_filter.changed_from)
    if review_filter.changed_to is not None:
        clauses.append(cell.updated_at <= review_filter.changed_to)
    if review_filter.import_job_id is not None:
        clauses.append(cell.import_job_id == review_filter.import_job_id)
    return tuple(clauses)


def _reference_library_entry_exists() -> ColumnElement[bool]:
    return _current_prediction_entry_exists(
        revision_alias="library_revision",
        model_version=REFERENCE_LIBRARY_PREDICTION_MODEL_VERSION,
        marker_key="referenceLibrary",
        marker_fields={},
    )


def _rgb_v2_entry_exists(*, status: str | None = None) -> ColumnElement[bool]:
    return _current_prediction_entry_exists(
        revision_alias="rgb_revision",
        model_version=RGB_V2_PREDICTION_MODEL_VERSION,
        marker_key="rgbV2",
        marker_fields={} if status is None else {"status": status},
    )


def _apply_symbol_cell_review_state_filter(
    statement: Select[Any],
    *,
    review_filter: SymbolCellReviewListFilter,
) -> Select[Any]:
    cell = ImageSymbolReviewCellModel
    if review_filter.state is SymbolCellReviewFilterState.ALL:
        return statement
    if review_filter.state is not SymbolCellReviewFilterState.ACTIVE_MODEL_COHORT:
        return statement.where(cell.review_state == review_filter.state.value)
    if review_filter.model_cohort_id is None:
        return statement.where(false())
    cohort_cell = VerifiedTrainingCohortCellModel
    return statement.join(
        cohort_cell,
        and_(
            cohort_cell.cohort_id == review_filter.model_cohort_id,
            cohort_cell.cell_review_id == cell.id,
            cohort_cell.crop_checksum_sha256 == cell.crop_checksum_sha256,
            cohort_cell.asset_mode == cell.asset_mode,
            cohort_cell.source_geometry_revision_id.is_not_distinct_from(
                cell.source_geometry_revision_id
            ),
            cohort_cell.render_spec_checksum_sha256.is_not_distinct_from(
                cell.render_spec_checksum_sha256
            ),
            cohort_cell.rendered_pixel_checksum_sha256.is_not_distinct_from(
                cell.rendered_pixel_checksum_sha256
            ),
        ),
    ).where(cell.review_state == SymbolCellReviewState.APPROVED.value)


def enter_cell_decision(session: Session, *, game_id: UUID, review_item_id: UUID) -> None:
    """Ownership lock of a symbol-cell decision (TASK-0950, P0-5).

    Keeps a lock an enclosing operation already holds; otherwise takes the mode
    the board needs (``SHARED`` unless resolving it may supersede another
    photo's pending item), before any sequence or row lock.
    """

    from game_predictor_api.storage.sequence_ownership_lock import (
        acquire_sequence_ownership_lock,
        cell_decision_lock_mode,
        held_sequence_ownership_lock,
    )

    if held_sequence_ownership_lock(session, game_id=game_id) is not None:
        return
    acquire_sequence_ownership_lock(
        session,
        game_id=game_id,
        mode=cell_decision_lock_mode(session, game_id=game_id, review_item_id=review_item_id),
    )


class SqlAlchemySymbolCellReviewMutationRepository(SymbolCellReviewMutationRepository):
    """Apply checksum-bound crop decisions and reconcile one parent board once."""

    def __init__(
        self, session: Session, *, allow_current_manual_neural_board: bool = False
    ) -> None:
        self._session = session
        self._allow_current_manual_neural_board = allow_current_manual_neural_board

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
        # TASK-0950 (P0-5): the decision may reopen or resolve the board, which
        # reaches the game's ownership lock; take it before the sequence lock.
        # An enclosing entry point may already hold it (kept as is).
        enter_cell_decision(self._session, game_id=game_id, review_item_id=review_item_id)
        self._acquire_board_locks(
            game_id=game_id,
            review_item_id=review_item_id,
            sequence_number=sequence_number,
        )
        # Lock rows again after advisory locks; their current owner may have
        # changed while the deterministic sequence lock was being acquired.
        rows = self._locked_current_rows(commands)
        # The worker and geometry editor lock sequences/source rows before the
        # shared catalog state. Taking state first deadlocks against a worker
        # that is finishing another board while this mutation waits on its source.
        state = self._require_ready_state(game_id, current_board=None if not rows else rows[0][2])
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
        count_before = tuple(
            _CountedCellState.from_model(row_by_cell_id[command.cell_review_id][0])
            for command in commands
        )
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
        _apply_count_deltas(
            state,
            before=count_before,
            after=tuple(
                _CountedCellState.from_model(row_by_cell_id[command.cell_review_id][0])
                for command in commands
            ),
        )
        self._session.flush()

        current_board_reviews, stale_approvals = self._locked_current_board_reviews(
            game_id=game_id,
            review_item_id=item.id,
            recognized_board_id=board.id,
            sequence_number=sequence_number,
            geometry_revision=board.geometry_revision,
            symbol_code_by_id=symbol_codes,
        )
        # D-462: the cells alone close the board; geometry approval is no gate.
        # A partial source still never publishes a complete layout (D-451).
        board_resolution = (
            None
            if board.completeness_status == "pending_partial"
            else derive_symbol_cell_board_resolution(
                reviews=current_board_reviews,
                active_symbol_codes=tuple(symbol_codes.values()),
                topology=_board_topology(board),
                stale_approval_cell_indices=stale_approvals,
            )
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
                    crop_sample_id=_required_crop_sample_id(review),
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
        if any_changed:
            # D-462: a verified cell feeds board search and approximate win
            # immediately, even while its board stays pending.
            SqlAlchemyBoardSearchProjectionRepository(self._session).sync_review_item(item.id)
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

    def _require_ready_state(
        self, game_id: UUID, *, current_board: RecognizedBoardModel | None = None
    ) -> ImageSymbolReviewStateModel:
        if self._session.get(GameModel, game_id) is None:
            raise SymbolCellReviewError(
                "GAME_NOT_FOUND",
                "The selected game does not exist.",
                details={"gameId": str(game_id)},
            )
        state = self._session.get(ImageSymbolReviewStateModel, game_id, with_for_update=True)
        current_manual_board_available = (
            self._allow_current_manual_neural_board
            and state is not None
            and state.status == "rebuilding"
            and not state.failure_message
            and current_board is not None
            and _manual_neural_lattice_approved(current_board)
        )
        if state is None or not (
            current_manual_board_available
            or symbol_cell_review_projection_is_available(
                self._session,
                game_id=game_id,
                state=state,
            )
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
                    _logical_cell_visible_clause(),
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
        statement = select(cell, ImageReviewItemModel, RecognizedBoardModel, SourceImageModel)
        _bind_game_store(self._session, command.game_id)
        rows = self._session.execute(
            statement.join(ImageReviewItemModel, ImageReviewItemModel.id == cell.review_item_id)
            .join(RecognizedBoardModel, RecognizedBoardModel.id == cell.recognized_board_id)
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .where(
                cell.id.in_(cell_ids),
                _logical_cell_visible_clause(),
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
    ) -> tuple[tuple[SymbolCellReview, ...], frozenset[int]]:
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


def _current_review_documents(session: Session, game_id: UUID) -> Any:
    """Current V2 owner projection of one game's active boards."""
    _bind_game_store(session, game_id)
    cell = ImageSymbolReviewCellModel
    return (
        select(
            cell.review_item_id,
            cell.recognized_board_id,
            cell.import_job_id,
            cell.sequence_number,
            cell.game_id,
            ImageReviewItemModel.status,
        )
        .join(ImageReviewItemModel, ImageReviewItemModel.id == cell.review_item_id)
        .where(
            cell.game_id == game_id,
            _logical_cell_visible_clause(),
            ImageReviewItemModel.status.in_(_ACTIVE_REVIEW_STATUSES),
        )
        .distinct()
        .subquery()
        .c
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
        document = _current_review_documents(self._session, game_id)
        unreadable_count = (
            select(func.count(cell.id))
            .where(
                cell.game_id == game_id,
                cell.review_item_id == document.review_item_id,
                cell.geometry_revision == RecognizedBoardModel.geometry_revision,
                cell.quality_issue == SymbolCellQualityIssue.UNREADABLE.value,
                _logical_cell_visible_clause(),
            )
            .correlate(document.review_item_id.table, RecognizedBoardModel)
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
                _logical_cell_visible_clause(),
            )
            .correlate(document.review_item_id.table, RecognizedBoardModel)
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
        document = _current_review_documents(self._session, game_id)
        board_row = self._session.execute(
            select(
                document.review_item_id,
                document.recognized_board_id,
                document.import_job_id,
                document.sequence_number,
                document.status,
                RecognizedBoardModel,
            )
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
                    _logical_cell_visible_clause(),
                )
                .exists(),
            )
        ).one_or_none()
        if board_row is None:
            return None
        current, board = board_row, board_row[-1]
        assigned = aliased(SymbolModel)
        rows = self._session.execute(
            select(ImageSymbolReviewCellModel, assigned)
            .outerjoin(assigned, assigned.id == ImageSymbolReviewCellModel.assigned_symbol_id)
            .where(
                ImageSymbolReviewCellModel.game_id == game_id,
                ImageSymbolReviewCellModel.review_item_id == review_item_id,
                ImageSymbolReviewCellModel.recognized_board_id == board.id,
                ImageSymbolReviewCellModel.geometry_revision == board.geometry_revision,
                _logical_cell_visible_clause(),
            )
            .order_by(ImageSymbolReviewCellModel.cell_index)
        ).all()
        topology = _board_topology(board)
        expected_indices = set(range(topology.cell_count))
        if (
            len(rows) != len(expected_indices)
            or {cell.cell_index for cell, _ in rows} != expected_indices
        ):
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
                    source_visibility=_source_visibility(cell_row),
                    asset_mode=cell_row.asset_mode,
                    crop_sample_id=cell_row.crop_sample_id,
                    crop_checksum_sha256=cell_row.crop_checksum_sha256,
                    render_spec_checksum_sha256=cell_row.render_spec_checksum_sha256,
                )
                for cell_row, symbol in rows
            ),
        )

    def resolve_cell(
        self,
        command: ResolveUnreadableCellCommand,
    ) -> SymbolCellReviewMutationResult:
        statement = select(ImageSymbolReviewCellModel.id)
        _bind_game_store(self._session, command.game_id)
        cell_id = self._session.scalar(
            statement.where(
                ImageSymbolReviewCellModel.game_id == command.game_id,
                ImageSymbolReviewCellModel.review_item_id == command.review_item_id,
                ImageSymbolReviewCellModel.cell_index == command.cell_index,
                _logical_cell_visible_clause(),
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

    def save_board(
        self,
        command: SaveUnreadableBoardCommand,
    ) -> SaveUnreadableBoardResult:
        """Persist one complete board edit in the caller's single transaction.

        A board shown in the pending unreadable queue is already reopened.  The
        operation first marks every newly unknown normal crop as unreadable,
        then applies real-symbol changes, and only then resolves unreadable
        crops.  This ordering prevents a transient accepted parent board while
        a later cell in the same HTTP request still needs to change.
        """

        # One ownership lock for every crop decision of this save (TASK-0950).
        enter_cell_decision(
            self._session, game_id=command.game_id, review_item_id=command.review_item_id
        )
        detail = self.get_board(
            game_id=command.game_id,
            review_item_id=command.review_item_id,
        )
        if detail is None:
            raise SymbolCellReviewError(
                "UNREADABLE_BOARD_REVIEW_NOT_FOUND",
                "The unreadable board is not a current logical owner in this game.",
            )
        if not any(
            cell.quality_issue == SymbolCellQualityIssue.UNREADABLE.value
            and cell.review_state == SymbolCellReviewState.PENDING.value
            for cell in detail.cells
        ):
            raise SymbolCellReviewError(
                "UNREADABLE_BOARD_REVIEW_NOT_PENDING",
                "Only a board with an unresolved unreadable crop can be edited here.",
            )

        requested_by_index = {cell.cell_index: cell for cell in command.cells}
        current_by_index = {cell.cell_index: cell for cell in detail.cells}
        if set(requested_by_index) != set(current_by_index):
            raise SymbolCellReviewError(
                "UNREADABLE_BOARD_REVIEW_SAVE_TOPOLOGY_MISMATCH",
                "Saving an unreadable board requires exactly every current board cell.",
            )

        mutation_repository = SqlAlchemySymbolCellReviewMutationRepository(self._session)
        current_revision_by_index = {
            cell.cell_index: requested_by_index[cell.cell_index].expected_revision
            for cell in detail.cells
        }
        changed_indexes: set[int] = set()
        last_result: SymbolCellReviewMutationResult | None = None

        def apply(
            *,
            cell: UnreadableBoardReviewCell,
            action: SymbolCellReviewAction,
            target_symbol_id: UUID | None,
            resolve_unreadable: bool,
        ) -> None:
            nonlocal last_result
            requested = requested_by_index[cell.cell_index]
            expected_revision = current_revision_by_index[cell.cell_index]
            result = mutation_repository.apply_mutation(
                SymbolCellReviewMutationCommand(
                    game_id=command.game_id,
                    cell_review_id=cell.cell_review_id,
                    action=action,
                    expected_revision=expected_revision,
                    expected_geometry_revision=requested.expected_geometry_revision,
                    expected_crop_sample_id=requested.expected_crop_sample_id,
                    expected_crop_checksum_sha256=requested.expected_crop_checksum_sha256,
                    target_symbol_id=target_symbol_id,
                    actor=command.actor,
                    resolve_unreadable=resolve_unreadable,
                )
            )
            if result.cell_revision != expected_revision:
                changed_indexes.add(cell.cell_index)
            current_revision_by_index[cell.cell_index] = result.cell_revision
            last_result = result

        # A `?` picked for a normal cell means: mark it unreadable and then
        # resolve that unreadable crop as the intentional logical unknown.
        for cell in detail.cells:
            requested = requested_by_index[cell.cell_index]
            if (
                requested.target_symbol_id is None
                and cell.quality_issue != SymbolCellQualityIssue.UNREADABLE.value
            ):
                apply(
                    cell=cell,
                    action=SymbolCellReviewAction.MARK_UNREADABLE,
                    target_symbol_id=None,
                    resolve_unreadable=False,
                )

        for cell in detail.cells:
            requested = requested_by_index[cell.cell_index]
            if (
                requested.target_symbol_id is not None
                and cell.quality_issue != SymbolCellQualityIssue.UNREADABLE.value
                and requested.target_symbol_id != cell.assigned_symbol_id
            ):
                apply(
                    cell=cell,
                    action=SymbolCellReviewAction.REASSIGN,
                    target_symbol_id=requested.target_symbol_id,
                    resolve_unreadable=False,
                )

        for cell in detail.cells:
            requested = requested_by_index[cell.cell_index]
            if (
                cell.quality_issue == SymbolCellQualityIssue.UNREADABLE.value
                or requested.target_symbol_id is None
            ):
                apply(
                    cell=cell,
                    action=(
                        SymbolCellReviewAction.APPROVE
                        if requested.target_symbol_id is None
                        else SymbolCellReviewAction.REASSIGN
                    ),
                    target_symbol_id=requested.target_symbol_id,
                    resolve_unreadable=True,
                )

        if last_result is None:
            raise AssertionError("An unreadable board save must resolve at least one pending crop.")
        return SaveUnreadableBoardResult(
            review_item_id=last_result.review_item_id,
            sequence_number=last_result.sequence_number,
            board_status=last_result.board_status,
            changed_cell_count=len(changed_indexes),
        )


class SqlAlchemyGridCorrectionSymbolRepository:
    """Operator symbols of one board's current cells in a grid correction (D-488)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def assign(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
        symbol_id_by_cell_index: Mapping[int, UUID | None],
        actor: str,
    ) -> int:
        """Approve the operator's symbols on the board's exact current crops.

        A ``None`` symbol is the operator's "cannot tell": that crop is marked
        unreadable (pending, no label) instead of being approved.

        Runs in the caller's transaction, after the geometry write.  A cell
        without a current reviewable crop is an error: nothing may be skipped
        silently, the caller rolls the whole save back.
        """

        self._session.flush()
        cells = {
            int(cell.cell_index): cell
            for cell in self._current_cells(
                game_id=game_id,
                review_item_id=review_item_id,
                cell_indices=tuple(symbol_id_by_cell_index),
            )
            if cell.source_available
        }
        missing = sorted(set(symbol_id_by_cell_index) - set(cells))
        if missing:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_SYMBOL_CELL_UNAVAILABLE",
                "The board has no current reviewable crop for cells "
                f"{', '.join(str(index + 1) for index in missing)}; "
                "save the grid without symbols for these cells.",
            )
        commands = tuple(
            SymbolCellReviewMutationCommand(
                game_id=game_id,
                cell_review_id=cell.id,
                action=(
                    SymbolCellReviewAction.MARK_UNREADABLE
                    if symbol_id_by_cell_index[index] is None
                    else SymbolCellReviewAction.REASSIGN
                ),
                expected_revision=int(cell.revision),
                expected_geometry_revision=int(cell.geometry_revision),
                expected_crop_sample_id=cell.crop_sample_id,
                expected_crop_checksum_sha256=cell.crop_checksum_sha256,
                target_symbol_id=symbol_id_by_cell_index[index],
                actor=actor,
            )
            for index, cell in sorted(cells.items())
        )
        mutations = SqlAlchemySymbolCellReviewMutationRepository(
            self._session, allow_current_manual_neural_board=True
        )
        changed = 0
        for command in commands:
            result = mutations.apply_mutation(command)
            changed += int(result.cell_revision != command.expected_revision)
        return changed

    def current_symbols(
        self, *, game_id: UUID, review_item_id: UUID
    ) -> tuple[tuple[int, UUID | None, Literal["assigned", "predicted"]], ...]:
        """``(cell index, symbol id, origin)`` of every current crop with pixels."""

        cells = self._current_cells(
            game_id=game_id, review_item_id=review_item_id, cell_indices=None
        )
        symbol_id_by_code = _active_symbol_maps(self._session, game_id)[1]
        return tuple(
            (int(cell.cell_index), cell.assigned_symbol_id, "assigned")
            if cell.assigned_symbol_id is not None
            else (
                int(cell.cell_index),
                symbol_id_by_code.get(cell.prediction_symbol_code or ""),
                "predicted",
            )
            for cell in cells
            if cell.source_available
        )

    def active_symbol_ids_by_code(self, *, game_id: UUID) -> dict[str, UUID]:
        _bind_game_store(self._session, game_id)
        return _active_symbol_maps(self._session, game_id)[1]

    def _current_cells(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
        cell_indices: Sequence[int] | None,
    ) -> tuple[ImageSymbolReviewCellModel, ...]:
        _bind_game_store(self._session, game_id)
        cell = ImageSymbolReviewCellModel
        statement = (
            select(cell)
            .join(RecognizedBoardModel, RecognizedBoardModel.id == cell.recognized_board_id)
            .where(
                cell.game_id == game_id,
                cell.review_item_id == review_item_id,
                cell.geometry_revision == RecognizedBoardModel.geometry_revision,
                _logical_cell_visible_clause(),
            )
            .order_by(cell.cell_index)
        )
        if cell_indices is not None:
            statement = statement.where(cell.cell_index.in_(tuple(cell_indices)))
        return tuple(self._session.scalars(statement))


class SymbolCellReviewWriteThroughCoordinator:
    """Keep current crop review state in the same transaction as board writes.

    The legacy Reviewer still owns the parent-board decision.  This adapter is
    deliberately storage-bound: every existing writer already has a locked
    SQLAlchemy session, so running the projection here makes a board mutation,
    its 15 cells and its search/canonical changes commit or roll back together.
    No cell state is materialised before a game's explicit backfill starts.

    D-484 (TASK-0807): a board whose source image is not admitted by the
    geometry gate and has no cells yet is not cut; its id is recorded in
    ``geometry_withheld_review_item_ids`` (reason
    ``SOURCE_IMAGE_GEOMETRY_INCOMPLETE``). Existing cells keep being maintained.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self.geometry_withheld_review_item_ids: set[UUID] = set()

    def synchronize_after_geometry_admission(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
        actor: str = _WRITE_THROUGH_ACTOR,
    ) -> bool:
        """Cut a board whose image the geometry gate just admitted (TASK-0807)."""

        return self._synchronize(
            game_id=game_id,
            review_item_id=review_item_id,
            reason="geometry_admission",
            actor=actor,
        )

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

    def release_cells_of_rejected_board(self, *, game_id: UUID, review_item_id: UUID) -> int:
        """Take a just-rejected board's cells out of the exact counters (TASK-0949).

        The rows and events stay as decision history; the visible scope
        already excludes rejected items. Call it once, on the transition of
        the item into ``rejected``.
        """

        cells = self._cells_of_item(game_id, review_item_id)
        state = self._state_if_initialized(game_id)
        if state is None:
            return len(cells)
        _apply_count_deltas(state, before=tuple(_CountedCellState.from_model(c) for c in cells))
        self._touch_catalog_revision(state)
        return len(cells)

    def restore_cells_of_reopened_board(self, *, game_id: UUID, review_item_id: UUID) -> int:
        """Put the cells of a board whose rejection was undone back into the counters.

        Call it once, on the transition out of ``rejected`` and before the
        regular write-through synchronization of the reactivated item.
        """

        cells = self._cells_of_item(game_id, review_item_id)
        state = self._state_if_initialized(game_id)
        if state is None:
            return len(cells)
        _apply_count_deltas(state, after=tuple(_CountedCellState.from_model(c) for c in cells))
        self._touch_catalog_revision(state)
        return len(cells)

    def _cells_of_item(
        self, game_id: UUID, review_item_id: UUID
    ) -> tuple[ImageSymbolReviewCellModel, ...]:
        # Both callers run inside the resolution/revert transaction, which has
        # already bound the game store.
        return tuple(
            self._session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(
                    ImageSymbolReviewCellModel.game_id == game_id,
                    ImageSymbolReviewCellModel.review_item_id == review_item_id,
                )
                .order_by(ImageSymbolReviewCellModel.cell_index)
                .with_for_update()
            )
        )

    def _rejected_item_ids(self, review_item_ids: set[UUID]) -> set[UUID]:
        if not review_item_ids:
            return set()
        return set(
            self._session.scalars(
                select(ImageReviewItemModel.id).where(
                    ImageReviewItemModel.id.in_(review_item_ids),
                    ImageReviewItemModel.status == "rejected",
                )
            )
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

    def synchronize_board_from_cells(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
        actor: str,
    ) -> bool:
        """Materialize a complete parent decision from current cell state.

        All current cell labels and their approved pixels are checked again
        under the same transaction; geometry approval is no condition
        (D-462).  Crop provenance is deliberately not promoted:
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
        if board.completeness_status == "pending_partial":
            return False
        if item.status != "pending":
            return False
        if self._geometry_withheld(game_id=game_id, item=item, board=board, source=source):
            # No cells to derive a decision from until the image is admitted.
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
        reviews, stale_approvals = _locked_board_reviews(
            self._session,
            game_id=game_id,
            review_item_id=item.id,
            recognized_board_id=board.id,
            sequence_number=sequence_number,
            geometry_revision=board.geometry_revision,
            symbol_code_by_id=symbol_codes,
            topology=topology,
        )
        # `pending_partial` returned above; geometry approval is no gate (D-462).
        resolution = derive_symbol_cell_board_resolution(
            reviews=reviews,
            active_symbol_codes=tuple(symbol_codes.values()),
            topology=topology,
            stale_approval_cell_indices=stale_approvals,
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
                    crop_sample_id=_required_crop_sample_id(review),
                    symbol_code=review.assigned_symbol_code,
                )
                for review in reviews
            ),
            rejection_reason=None,
            resolved_by=actor,
            allow_unknown_cells=any(review.assigned_symbol_code is None for review in reviews),
        )
        return True

    def recheck_changed_pixel_approvals(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
        cell_indices: Sequence[int],
        actor: str,
    ) -> int:
        """Return approvals of other pixels to verification (D-462 R10, TASK-0728).

        Like the recrop suggestion (R6): the human label and its source stay
        as the suggestion and the `approved_*` columns stay as history. An
        approved cell can only carry `blurry`, which described the approved
        pixels, so it is cleared. A cell that is no longer such an approval
        is a drift and aborts.
        """

        state = self._state_if_initialized(game_id)
        if state is None:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_PROJECTION_INCOMPLETE",
                "The symbol-cell review projection is not ready for this game.",
            )
        indices = sorted(set(cell_indices))
        cells = tuple(
            self._session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(
                    ImageSymbolReviewCellModel.game_id == game_id,
                    ImageSymbolReviewCellModel.review_item_id == review_item_id,
                    ImageSymbolReviewCellModel.cell_index.in_(indices),
                )
                .order_by(ImageSymbolReviewCellModel.cell_index)
                .with_for_update()
            )
        )
        if [cell.cell_index for cell in cells] != indices or not all(
            cell.review_state == SymbolCellReviewState.APPROVED.value
            and _approval_pixels_changed(cell)
            for cell in cells
        ):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_MIGRATION_DRIFT",
                "A cell is no longer an approval of other pixels.",
            )
        count_before = tuple(_CountedCellState.from_model(cell) for cell in cells)
        for cell in cells:
            previous = _CellPreviousState.from_model(cell)
            cell.review_state = SymbolCellReviewState.PENDING.value
            if cell.quality_issue == SymbolCellQualityIssue.BLURRY.value:
                cell.quality_issue = None
            verification = _verification_v2(
                review_state=cell.review_state,
                quality_issue=cell.quality_issue,
                assigned_symbol_id=cell.assigned_symbol_id,
                prediction_symbol_code=cell.prediction_symbol_code,
                assignment_source=cell.assignment_source,
            )
            cell.verification_outcome = verification.outcome
            cell.verified_symbol_id_v2 = verification.verified_symbol_id
            cell.revision += 1
            cell.last_reviewed_by = actor
            self._append_event(
                cell=cell, previous=previous, action="geometry_invalidated", actor=actor
            )
        self._session.flush()
        _apply_count_deltas(
            state,
            before=count_before,
            after=tuple(_CountedCellState.from_model(cell) for cell in cells),
        )
        self._touch_catalog_revision(state)
        return len(cells)

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
            # Persist new imports immediately even before the first historical
            # rebuild. Readiness remains fenced until that rebuild completes.
            state = ImageSymbolReviewStateModel(game_id=game_id, status="rebuilding")
            self._session.add(state)
            self._session.flush()
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
        if self._geometry_withheld(game_id=game_id, item=item, board=board, source=source):
            # D-484: the image is not admitted and this board was never cut.
            return False

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
            (
                current_cells,
                cropper_version,
                prediction_revision_id,
                prediction_model_iteration_id,
            ) = self._current_cells(
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

        existing_statement = select(ImageSymbolReviewCellModel).order_by(
            ImageSymbolReviewCellModel.cell_index
        )
        _bind_game_store(self._session, game_id)
        existing_statement = existing_statement.where(
            ImageSymbolReviewCellModel.game_id == game_id,
            ImageSymbolReviewCellModel.sequence_number == sequence_number,
        )
        existing = {
            cell.cell_index: cell
            for cell in self._session.scalars(existing_statement.with_for_update())
        }
        # Cells of a rejected previous owner were taken out of the exact counters
        # when it was rejected, so they are not subtracted again (TASK-0949).
        rejected_owner_ids = self._rejected_item_ids(
            {cell.review_item_id for cell in existing.values()} - {item.id}
        )
        count_before = tuple(
            _CountedCellState.from_model(cell)
            for cell in existing.values()
            if cell.review_item_id not in rejected_owner_ids
        )
        # Logical V2 cells can move from a previous owner of this sequence;
        # that owner's search evidence must be refreshed as well (D-462 R8).
        previous_owner_ids = {cell.review_item_id for cell in existing.values()} - {item.id}
        topology = _board_topology(board)
        expected_cell_indices = set(
            available_cell_indices(
                unavailable_cell_indices=board.unavailable_cell_indices,
                geometry_qualification=board.geometry_qualification,
                asset_mode=board.asset_mode,
                cell_count=topology.cell_count,
            )
        )
        qualified = board.geometry_qualification is not None
        partially_visible = partially_visible_cell_indices(
            unavailable_cell_indices=board.unavailable_cell_indices,
            geometry_qualification=board.geometry_qualification,
            asset_mode=board.asset_mode,
        )
        visibilities = qualification_visibilities(board.geometry_qualification, topology.cell_count)
        source_geometry = None
        manual_geometry = None
        if board.asset_mode == "virtual_source":
            source_geometry = self._session.get(
                ImageSourceGeometryRevisionModel, board.source_geometry_revision_id
            )
        elif board.geometry_revision > 0:
            manual_geometry = self._session.scalar(
                select(ImageBoardGeometryRevisionModel).where(
                    ImageBoardGeometryRevisionModel.recognized_board_id == board.id,
                    ImageBoardGeometryRevisionModel.revision == board.geometry_revision,
                )
            )
        geometry_payload = pinned_visibility_geometry(
            board=vars(board) | {"sequence_number": sequence_number},
            source=vars(source),
            source_geometry=None if source_geometry is None else vars(source_geometry),
            manual_geometry=None if manual_geometry is None else vars(manual_geometry),
        )
        if isinstance(geometry_payload, Mapping):
            visibilities = current_source_visibilities(
                geometry=geometry_payload,
                width=source.oriented_width or source.width,
                height=source.oriented_height or source.height,
                topology=topology,
            )
        outside = {
            index for index, visibility in enumerate(visibilities) if visibility == "outside"
        }
        partially_visible = partially_visible | frozenset(
            index for index, visibility in enumerate(visibilities) if visibility == "partial"
        )
        if all(visibility is not None for visibility in visibilities):
            expected_cell_indices = set(range(topology.cell_count)) - outside
            # Historical file writers emitted all fifteen images even when a
            # cell had no source pixels. Such files are never current assets.
            current_cells = tuple(cell for cell in current_cells if cell.cell_index not in outside)
        if qualified and {cell.cell_index for cell in current_cells} != expected_cell_indices:
            self._mark_integrity_failure(
                state,
                "SYMBOL_CELL_REVIEW_CELLS_INCOMPLETE",
                "Qualified current renders do not match the authoritative availability mask.",
            )
            return False
        if not qualified and existing and set(existing) != expected_cell_indices:
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
        incompatible_prediction_codes = _incompatible_prediction_codes(
            cells=current_cells,
            active_symbol_ids=active_symbol_ids,
            model_iteration_id=prediction_model_iteration_id,
        )
        if incompatible_prediction_codes:
            self._mark_integrity_failure(
                state,
                "SYMBOL_MODEL_CLASS_CATALOG_MISMATCH",
                "An active model prediction contains classes outside the game's active "
                f"symbol catalog: {', '.join(incompatible_prediction_codes)}.",
            )
            return False
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

        current_cells_by_index = {cell.cell_index: cell for cell in current_cells}
        geometry_changed = any(
            cell.geometry_revision != board.geometry_revision
            or cell.cell_index not in current_cells_by_index
            or cell.crop_checksum_sha256
            != current_cells_by_index[cell.cell_index].crop_checksum_sha256
            or (qualified and cell.source_available is False)
            for index, cell in existing.items()
            if not qualified or index in expected_cell_indices
        )
        if geometry_changed and board.completeness_status == "pending_partial" and not qualified:
            self._mark_integrity_failure(
                state,
                "SYMBOL_CELL_REVIEW_PARTIAL_GEOMETRY_IMMUTABLE",
                "A partial board cannot be recropped as a complete board.",
            )
            return False
        recropped_targets: dict[int, _CellProjection] = {}
        if geometry_changed and existing:
            symbol_code_by_id = {symbol_id: code for code, symbol_id in active_symbol_ids.items()}
            recropped = invalidate_symbol_cell_reviews_for_geometry(
                existing_reviews=tuple(
                    _symbol_cell_review_from_model(
                        existing[index],
                        symbol_code_by_id=symbol_code_by_id,
                    )
                    for index in sorted(expected_cell_indices)
                    if index in existing and existing[index].crop_sample_id is not None
                ),
                current_cells=current_cells,
                geometry_revision=board.geometry_revision,
                cropper_version=cropper_version,
                topology=topology,
                # Partially visible cells are declared unavailable but still
                # rendered; only the fully outside ones have no current crop.
                unavailable_cell_indices=_fully_unavailable_cell_indices(board)
                if qualified
                else None,
                unchanged_available_indices=frozenset(
                    index
                    for index, cell in existing.items()
                    if qualified
                    and cell.source_available is not False
                    and index in current_cells_by_index
                    and cell.crop_checksum_sha256
                    == current_cells_by_index[index].crop_checksum_sha256
                ),
                # D-539 (TASK-0950): a replacement board takes the logical cells
                # over from the rejected board of another image.
                handoff_from_rejected_board=all(
                    cell.review_item_id in rejected_owner_ids
                    and cell.recognized_board_id != board.id
                    for cell in existing.values()
                ),
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
                    **_projection_approved_asset_kwargs(
                        # An approval rebound to unchanged pixels (D-462 R6)
                        # takes the current asset provenance as well. The rebind
                        # is recognized by crop identity, never by the revision
                        # number: boards of different photos share revision
                        # numbers (a D-539 handoff 0 -> 0, TASK-0950).
                        _approved_asset_projection_from_review_cell(
                            current_cells_by_index[review.cell_index]
                        )
                        if review.approved_crop is not None
                        and _approval_matches_current_crop(
                            review.approved_crop, current_cells_by_index[review.cell_index]
                        )
                        else _approved_asset_projection_from_model(existing[review.cell_index])
                        if review.approved_crop is not None
                        else _empty_approved_asset_projection()
                    ),
                )
                for review in recropped
            }
        changed = False
        for index in sorted(outside):
            cell = existing.get(index)
            if cell is None:
                cell = ImageSymbolReviewCellModel(
                    game_id=game_id,
                    import_job_id=source.import_job_id,
                    review_item_id=item.id,
                    recognized_board_id=board.id,
                    sequence_number=sequence_number,
                    cell_index=index,
                    row_index=index // topology.columns,
                    column_index=index % topology.columns,
                    asset_mode="none",
                    source_geometry_revision_id=getattr(board, "source_geometry_revision_id", None),
                    source_available=False,
                    source_visibility="outside",
                    geometry_revision=board.geometry_revision,
                    cropper_version=cropper_version,
                    assignment_source="geometry_partial",
                    review_state="pending",
                    revision=0,
                    verification_outcome="unknown",
                    last_reviewed_by=actor,
                )
                self._session.add(cell)
                changed = True
            else:
                values = dict(
                    import_job_id=source.import_job_id,
                    review_item_id=item.id,
                    recognized_board_id=board.id,
                    sequence_number=sequence_number,
                    geometry_revision=board.geometry_revision,
                    cropper_version=cropper_version,
                    asset_mode="none",
                    source_available=False,
                    source_visibility="outside",
                    crop_sample_id=None,
                    crop_checksum_sha256=None,
                    crop_relative_path=None,
                    render_spec_checksum_sha256=None,
                    rendered_pixel_checksum_sha256=None,
                    render_identity_v2_sha256=None,
                    logical_cell_key_v2=None,
                    logical_cell_key=None,
                    extractor_version=None,
                    source_geometry_revision_id=getattr(board, "source_geometry_revision_id", None),
                    prediction_symbol_code=None,
                    prediction_confidence=None,
                    prediction_revision_id=None,
                )
                if not _is_human_cell_decision(cell):
                    values.update(
                        assigned_symbol_id=None,
                        review_state="pending",
                        assignment_source="geometry_partial",
                        verification_outcome="unknown",
                        verified_symbol_id_v2=None,
                    )
                else:
                    values.update(
                        _outside_human_decision_values(
                            cell,
                            new_geometry=cell.geometry_revision != board.geometry_revision,
                        )
                    )
                if any(getattr(cell, key) != value for key, value in values.items()):
                    previous = _CellPreviousState.from_model(cell)
                    for key, value in values.items():
                        setattr(cell, key, value)
                    cell.revision += 1
                    cell.last_reviewed_by = actor
                    self._append_event(
                        cell=cell, previous=previous, action="geometry_invalidated", actor=actor
                    )
                    changed = True
        if qualified:
            for index, cell in existing.items():
                available = index in expected_cell_indices
                if cell.source_available is not available:
                    cell.source_available = available
                    changed = True
                if (
                    geometry_changed
                    and not available
                    and cell.quality_issue == SymbolCellQualityIssue.GRID_ISSUE.value
                ):
                    # R5: a saved geometry resolves the report of a position
                    # that no longer has source pixels as well.
                    previous_state = _CellPreviousState.from_model(cell)
                    cell.quality_issue = None
                    verification = _verification_v2(
                        review_state=cell.review_state,
                        quality_issue=None,
                        assigned_symbol_id=cell.assigned_symbol_id,
                        prediction_symbol_code=cell.prediction_symbol_code,
                        assignment_source=cell.assignment_source,
                    )
                    cell.verification_outcome = verification.outcome
                    cell.verified_symbol_id_v2 = verification.verified_symbol_id
                    cell.revision += 1
                    cell.last_reviewed_by = actor
                    self._append_event(
                        cell=cell,
                        previous=previous_state,
                        action="geometry_invalidated",
                        actor=actor,
                    )
                    changed = True
                if not available and (
                    cell.import_job_id != source.import_job_id
                    or cell.review_item_id != item.id
                    or cell.recognized_board_id != board.id
                ):
                    cell.import_job_id = source.import_job_id
                    cell.review_item_id = item.id
                    cell.recognized_board_id = board.id
                    cell.sequence_number = sequence_number
                    cell.revision += 1
                    cell.last_reviewed_by = actor
                    changed = True
        for review_cell in current_cells:
            existing_cell = existing.get(review_cell.cell_index)
            owner_changed = existing_cell is not None and (
                existing_cell.import_job_id != source.import_job_id
                or existing_cell.review_item_id != item.id
                or existing_cell.recognized_board_id != board.id
            )
            prediction_symbol_id = active_symbol_ids.get(review_cell.predicted_symbol_code)
            if geometry_changed and existing_cell is not None:
                target = recropped_targets[review_cell.cell_index]
                if existing_cell.crop_sample_id is None and _is_human_cell_decision(existing_cell):
                    # A logical position without pixels (D-451) gained pixels:
                    # its human label becomes a pending suggestion (D-462 R6);
                    # the domain rule only sees positions that had pixels.
                    target = replace(
                        target,
                        assigned_symbol_id=existing_cell.assigned_symbol_id,
                        assignment_source=existing_cell.assignment_source,
                        approved_crop_sample_id=existing_cell.approved_crop_sample_id,
                        approved_crop_checksum_sha256=existing_cell.approved_crop_checksum_sha256,
                        approved_geometry_revision=existing_cell.approved_geometry_revision,
                        **_projection_approved_asset_kwargs(
                            _approved_asset_projection_from_model(existing_cell)
                        ),
                    )
                if (
                    review_cell.cell_index in partially_visible
                    and target.review_state != SymbolCellReviewState.APPROVED.value
                ):
                    # D-434: unverified partial pixels are forced unknown; a
                    # human label stays as a pending suggestion (D-462 R6).
                    target = (
                        replace(
                            target,
                            quality_issue=SymbolCellQualityIssue.PARTIAL_VISIBILITY.value,
                        )
                        if target.assignment_source
                        in {
                            SymbolCellAssignmentSource.HUMAN.value,
                            SymbolCellAssignmentSource.BOARD_DECISION.value,
                        }
                        else _forced_partial_visibility_projection()
                    )
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
                    **_projection_approved_asset_kwargs(
                        _approved_asset_projection_from_model(existing_cell)
                        if preserve_approved_crop and existing_cell is not None
                        else _approved_asset_projection_from_review_cell(review_cell)
                    ),
                )
                event_action = "board_synchronized"
            elif geometry_changed or reason == "board_reopened":
                target = (
                    _forced_partial_visibility_projection()
                    if review_cell.cell_index in partially_visible
                    else _CellProjection(
                        assigned_symbol_id=prediction_symbol_id,
                        review_state=SymbolCellReviewState.PENDING.value,
                        assignment_source=SymbolCellAssignmentSource.MODEL.value,
                        quality_issue=None,
                        approved_crop_sample_id=None,
                        approved_crop_checksum_sha256=None,
                        approved_geometry_revision=None,
                        **_projection_approved_asset_kwargs(_empty_approved_asset_projection()),
                    )
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
                    **_projection_approved_asset_kwargs(
                        _approved_asset_projection_from_model(existing_cell)
                    ),
                )
                event_action = None
            else:
                target = (
                    _forced_partial_visibility_projection()
                    if review_cell.cell_index in partially_visible
                    else _CellProjection(
                        assigned_symbol_id=prediction_symbol_id,
                        review_state=SymbolCellReviewState.PENDING.value,
                        assignment_source=SymbolCellAssignmentSource.MODEL.value,
                        quality_issue=None,
                        approved_crop_sample_id=None,
                        approved_crop_checksum_sha256=None,
                        approved_geometry_revision=None,
                        **_projection_approved_asset_kwargs(_empty_approved_asset_projection()),
                    )
                )
                event_action = None
            if owner_changed and event_action is None:
                event_action = "board_synchronized"
            if (
                qualified
                and existing_cell is not None
                and not geometry_changed
                and target.approved_crop_sample_id is None
            ):
                # A no-op reconciliation must not erase the retained approval
                # provenance; pending still prevents training on the new pixels.
                target = replace(
                    target,
                    approved_crop_sample_id=existing_cell.approved_crop_sample_id,
                    approved_crop_checksum_sha256=existing_cell.approved_crop_checksum_sha256,
                    approved_geometry_revision=existing_cell.approved_geometry_revision,
                    **_projection_approved_asset_kwargs(
                        _approved_asset_projection_from_model(existing_cell)
                    ),
                )
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
                        source_visibility=visibilities[review_cell.cell_index],
                        source_available=True,
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
                        **_asset_provenance_values(review_cell),
                        crop_checksum_sha256=review_cell.crop_checksum_sha256,
                        geometry_revision=board.geometry_revision,
                        cropper_version=cropper_version,
                        prediction_symbol_code=_known_symbol_code(
                            review_cell.predicted_symbol_code
                        ),
                        prediction_confidence=review_cell.confidence,
                        prediction_revision_id=prediction_revision_id,
                        assigned_symbol_id=target.assigned_symbol_id,
                        review_state=target.review_state,
                        quality_issue=target.quality_issue,
                        verification_outcome=verification.outcome,
                        verified_symbol_id_v2=verification.verified_symbol_id,
                        approved_crop_sample_id=target.approved_crop_sample_id,
                        approved_crop_checksum_sha256=target.approved_crop_checksum_sha256,
                        approved_geometry_revision=target.approved_geometry_revision,
                        approved_asset_mode=target.approved_asset_mode,
                        approved_source_geometry_revision_id=(
                            target.approved_source_geometry_revision_id
                        ),
                        approved_render_spec_checksum_sha256=(
                            target.approved_render_spec_checksum_sha256
                        ),
                        approved_rendered_pixel_checksum_sha256=(
                            target.approved_rendered_pixel_checksum_sha256
                        ),
                        assignment_source=target.assignment_source,
                        revision=0,
                        last_reviewed_by=actor,
                    )
                )
                changed = True
                continue
            visibility = visibilities[review_cell.cell_index]
            if existing_cell.source_visibility != visibility:
                existing_cell.source_visibility = visibility
                changed = True
            if not qualified and existing_cell.source_available is False:
                # A complete board renders every cell: a logical position that
                # had no image (e.g. taken over from a rejected partial board,
                # D-539, TASK-0950) is available again. Qualified boards set
                # availability from their mask above.
                existing_cell.source_available = True
                changed = True
            if not _cell_matches_projection(
                existing_cell,
                review_cell=review_cell,
                cropper_version=cropper_version,
                prediction_revision_id=prediction_revision_id,
                target=target,
                import_job_id=source.import_job_id,
                review_item_id=item.id,
                recognized_board_id=board.id,
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
                    import_job_id=source.import_job_id,
                    review_item_id=item.id,
                    recognized_board_id=board.id,
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
            _bind_game_store(self._session, game_id)
            current_count_statement = select(ImageSymbolReviewCellModel).where(
                ImageSymbolReviewCellModel.game_id == game_id,
                ImageSymbolReviewCellModel.sequence_number == sequence_number,
            )
            count_after = tuple(
                _CountedCellState.from_model(cell)
                for cell in self._session.scalars(
                    current_count_statement.order_by(ImageSymbolReviewCellModel.cell_index)
                )
            )
            _apply_count_deltas(state, before=count_before, after=count_after)
            self._touch_catalog_revision(state)
            # D-462 R8: search evidence of a pending board is read from these
            # rows; callers refreshed the projection before the cells changed.
            for review_item_id in sorted({item.id, *previous_owner_ids}, key=str):
                self._refresh_search_projection(review_item_id)
        return changed

    def _refresh_search_projection(self, review_item_id: UUID) -> None:
        SqlAlchemyBoardSearchProjectionRepository(self._session).sync_review_item(review_item_id)

    def _geometry_withheld(
        self,
        *,
        game_id: UUID,
        item: ImageReviewItemModel,
        board: RecognizedBoardModel,
        source: SourceImageModel,
    ) -> bool:
        if item.id not in withheld_review_item_ids(
            self._session, game_id, ((item.id, board, source),)
        ):
            return False
        self.geometry_withheld_review_item_ids.add(item.id)
        return True

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
    ) -> tuple[tuple[ImageReviewCell, ...], str, UUID | None, UUID | None]:
        # See the local import in ``_cell_values``.  The Reviewer remains the
        # owner of the base-vs-corrected geometry mapper.
        from game_predictor_api.storage.image_review_repository import (
            materialize_current_image_review_cells,
        )

        cell_sources = load_current_board_cell_source(
            self._session, game_id=cast(UUID, job.game_id), board=board
        )
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
            cell_sources=cell_sources,
            prediction_override=prediction_override,
        )
        return (
            tuple(cells),
            _current_cropper_version(
                board=board,
                cell_sources=cell_sources,
                geometry=geometry,
            ),
            None if prediction is None else prediction.id,
            None if prediction is None else prediction.model_iteration_id,
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
            # The super game derivation input changes with every cell write
            # (TASK-0933); recorded in this same transaction.
            record_super_game_input_change(self._session, state.game_id, source="symbol_cells")

    @staticmethod
    def _mark_integrity_failure(
        state: ImageSymbolReviewStateModel,
        code: str,
        message: str,
    ) -> None:
        state.status = "failed"
        state.failure_message = f"{code}: {message}"[:500]
        # Let the transaction owner roll back board, observations and counters.
        # Returning False also means a harmless retry and cannot signal failure.
        raise SymbolCellReviewError(code, message)


@dataclass(frozen=True, slots=True)
class _CellProjection:
    assigned_symbol_id: UUID | None
    review_state: str
    assignment_source: str
    quality_issue: str | None
    approved_crop_sample_id: str | None
    approved_crop_checksum_sha256: str | None
    approved_geometry_revision: int | None
    approved_asset_mode: str | None = None
    approved_source_geometry_revision_id: UUID | None = None
    approved_render_spec_checksum_sha256: str | None = None
    approved_rendered_pixel_checksum_sha256: str | None = None


class _ApprovedAssetProjectionKwargs(TypedDict):
    approved_asset_mode: str | None
    approved_source_geometry_revision_id: UUID | None
    approved_render_spec_checksum_sha256: str | None
    approved_rendered_pixel_checksum_sha256: str | None


@dataclass(frozen=True, slots=True)
class _CellPreviousState:
    assigned_symbol_id: UUID | None
    review_state: str
    quality_issue: str | None
    approved_crop_sample_id: str | None
    approved_crop_checksum_sha256: str | None
    approved_geometry_revision: int | None
    approved_asset_mode: str | None
    approved_source_geometry_revision_id: UUID | None
    approved_render_spec_checksum_sha256: str | None
    approved_rendered_pixel_checksum_sha256: str | None
    logical_cell_key_v2: str | None
    render_identity_v2_sha256: str | None
    asset_mode: str
    source_geometry_revision_id: UUID | None
    render_spec_checksum_sha256: str | None
    rendered_pixel_checksum_sha256: str | None
    verification_outcome: str | None
    verified_symbol_id_v2: UUID | None
    # TASK-0945: recorded on every event so a revert can restore it.
    assignment_source: str | None = None

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
            approved_asset_mode=cell.approved_asset_mode,
            approved_source_geometry_revision_id=(cell.approved_source_geometry_revision_id),
            approved_render_spec_checksum_sha256=(cell.approved_render_spec_checksum_sha256),
            approved_rendered_pixel_checksum_sha256=(cell.approved_rendered_pixel_checksum_sha256),
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
            assignment_source=cell.assignment_source,
        )


def _geometry_review_event_board_checksum(board: RecognizedBoardModel) -> str | None:
    """Audit identity of the approved board geometry.

    A virtual_source board has no board crop; like its geometry_saved event,
    it is identified by the source geometry checksum.
    """

    return board.board_checksum_sha256 or board.geometry_checksum_sha256


def _asset_provenance_values(review_cell: ImageReviewCell) -> dict[str, object]:
    """Translate the shared current-cell asset identity into persisted columns.

    ``virtual_source`` deliberately has no crop path.  Its render provenance is
    mandatory instead, so fail closed rather than creating a row that would be
    unreadable by the checksum-bound asset endpoint.
    """

    if review_cell.asset_mode != "virtual_source" or (
        review_cell.crop_relative_path is not None
        or review_cell.source_geometry_revision_id is None
        or review_cell.logical_cell_key is None
        or review_cell.render_spec is None
        or review_cell.render_spec_checksum_sha256 is None
        or review_cell.rendered_pixel_checksum_sha256 is None
        or not review_cell.extractor_version
    ):
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_VIRTUAL_PROVENANCE_INVALID",
            "A virtual symbol review cell is missing current render provenance.",
        )
    return {
        "asset_mode": "virtual_source",
        "source_geometry_revision_id": review_cell.source_geometry_revision_id,
        "logical_cell_key": review_cell.logical_cell_key,
        "logical_cell_key_v2": review_cell.logical_cell_key_v2,
        "render_identity_v2_sha256": review_cell.render_identity_v2_sha256,
        "render_spec_checksum_sha256": review_cell.render_spec_checksum_sha256,
        "rendered_pixel_checksum_sha256": review_cell.rendered_pixel_checksum_sha256,
        "extractor_version": review_cell.extractor_version,
    }


def _approved_asset_provenance_from_review_cell(
    review_cell: ImageReviewCell,
) -> dict[str, object]:
    _asset_provenance_values(review_cell)
    return {
        "approved_asset_mode": "virtual_source",
        "approved_source_geometry_revision_id": review_cell.source_geometry_revision_id,
        "approved_render_spec_checksum_sha256": review_cell.render_spec_checksum_sha256,
        "approved_rendered_pixel_checksum_sha256": review_cell.rendered_pixel_checksum_sha256,
    }


def _approved_asset_provenance_from_model(
    cell: ImageSymbolReviewCellModel,
) -> dict[str, object]:
    return {
        "approved_asset_mode": cell.approved_asset_mode,
        "approved_source_geometry_revision_id": cell.approved_source_geometry_revision_id,
        "approved_render_spec_checksum_sha256": cell.approved_render_spec_checksum_sha256,
        "approved_rendered_pixel_checksum_sha256": (cell.approved_rendered_pixel_checksum_sha256),
    }


def _empty_approved_asset_provenance() -> dict[str, object]:
    return {
        "approved_asset_mode": None,
        "approved_source_geometry_revision_id": None,
        "approved_render_spec_checksum_sha256": None,
        "approved_rendered_pixel_checksum_sha256": None,
    }


def _approval_matches_current_crop(
    approved: SymbolCellApprovedCropIdentity, current: ImageReviewCell
) -> bool:
    """The approval was rebound to the current crop (same sample and pixels)."""

    return (
        approved.crop_sample_id == current.crop_sample_id
        and approved.crop_checksum_sha256 == current.crop_checksum_sha256
    )


def _approved_asset_projection_from_review_cell(
    review_cell: ImageReviewCell,
) -> _ApprovedAssetProjectionKwargs:
    return cast(
        _ApprovedAssetProjectionKwargs,
        _approved_asset_provenance_from_review_cell(review_cell),
    )


def _approved_asset_projection_from_model(
    cell: ImageSymbolReviewCellModel,
) -> _ApprovedAssetProjectionKwargs:
    return {
        "approved_asset_mode": cell.approved_asset_mode,
        "approved_source_geometry_revision_id": cell.approved_source_geometry_revision_id,
        "approved_render_spec_checksum_sha256": cell.approved_render_spec_checksum_sha256,
        "approved_rendered_pixel_checksum_sha256": (cell.approved_rendered_pixel_checksum_sha256),
    }


def _empty_approved_asset_projection() -> _ApprovedAssetProjectionKwargs:
    return {
        "approved_asset_mode": None,
        "approved_source_geometry_revision_id": None,
        "approved_render_spec_checksum_sha256": None,
        "approved_rendered_pixel_checksum_sha256": None,
    }


def _projection_approved_asset_kwargs(
    value: _ApprovedAssetProjectionKwargs,
) -> _ApprovedAssetProjectionKwargs:
    """Keep a named boundary for type-safe ``_CellProjection`` construction."""

    return value


@dataclass(slots=True)
class _CatalogRevisionTransactionMarker:
    transaction: object
    game_ids: set[UUID]


def _board_topology(board: RecognizedBoardModel) -> BoardTopology:
    return BoardTopology(
        rows=board.grid_rows or 3,
        columns=board.grid_columns or 5,
    )


def _fully_unavailable_cell_indices(board: RecognizedBoardModel) -> tuple[int, ...]:
    """Cells without a current crop; partially visible cells are still rendered."""

    available = available_cell_indices(
        unavailable_cell_indices=board.unavailable_cell_indices,
        geometry_qualification=board.geometry_qualification,
        asset_mode=board.asset_mode,
        cell_count=_board_topology(board).cell_count,
    )
    return tuple(
        index for index in range(_board_topology(board).cell_count) if index not in available
    )


def _excluded_cell_count_sql(model: type[RecognizedBoardModel]) -> ColumnElement[int]:
    """SQL mirror of ``geometry_qualification.available_cell_indices``.

    Only virtual-source boards (D-434/435) with a v3 qualification exclude
    just the genuinely, fully unavailable cells from their expected count;
    every other board still excludes the whole declared mask.
    """
    return case(
        (
            and_(
                model.asset_mode == "virtual_source",
                model.geometry_qualification["version"].astext == GEOMETRY_QUALIFICATION_VERSION_V3,
            ),
            func.jsonb_array_length(model.geometry_qualification["fullyUnavailableCellIndices"]),
        ),
        else_=func.cardinality(model.unavailable_cell_indices),
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
) -> tuple[tuple[SymbolCellReview, ...], frozenset[int]]:
    """Lock the board's current cells; also name approvals of other pixels."""

    rows = tuple(
        session.scalars(
            select(ImageSymbolReviewCellModel)
            .where(
                ImageSymbolReviewCellModel.game_id == game_id,
                ImageSymbolReviewCellModel.review_item_id == review_item_id,
                ImageSymbolReviewCellModel.recognized_board_id == recognized_board_id,
                _logical_cell_visible_clause(),
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
    reviews = tuple(
        _symbol_cell_review_from_model(cell, symbol_code_by_id=symbol_code_by_id) for cell in rows
    )
    stale_approvals = frozenset(
        cell.cell_index
        for cell in rows
        if cell.review_state == SymbolCellReviewState.APPROVED.value
        and _approval_pixels_changed(cell)
    )
    return reviews, stale_approvals


def _approval_pixels_changed(cell: ImageSymbolReviewCellModel) -> bool:
    return symbol_cell_approval_pixels_changed(
        asset_mode=cell.asset_mode,
        crop_checksum_sha256=cell.crop_checksum_sha256,
        approved_crop_checksum_sha256=cell.approved_crop_checksum_sha256,
        rendered_pixel_checksum_sha256=cell.rendered_pixel_checksum_sha256,
        approved_rendered_pixel_checksum_sha256=cell.approved_rendered_pixel_checksum_sha256,
    )


def active_symbol_codes_by_id(session: Session, game_id: UUID) -> dict[UUID, str]:
    """Active symbol codes of one game keyed by symbol id."""

    return _active_symbol_maps(session, game_id)[0]


@dataclass(frozen=True, slots=True)
class CellLevelBoardAssessment:
    """What D-462 decides for one board from its current cell rows."""

    changed_pixel_approvals: frozenset[int]
    resolution_after_recheck: str | None
    blocker: str | None


def assess_cell_level_board(
    *,
    item: ImageReviewItemModel,
    board: RecognizedBoardModel,
    cells: Sequence[ImageSymbolReviewCellModel],
    symbol_code_by_id: Mapping[UUID, str],
) -> CellLevelBoardAssessment:
    """Mirror `synchronize_board_from_cells` without locks or writes (TASK-0728).

    Approvals of other pixels count as rechecked (pending); the result is the
    board decision the cells would derive after that recheck.
    """

    changed = frozenset(
        cell.cell_index
        for cell in cells
        if cell.review_state == SymbolCellReviewState.APPROVED.value
        and _approval_pixels_changed(cell)
    )
    if item.status != "pending" or board.completeness_status == "pending_partial":
        return CellLevelBoardAssessment(changed, None, None)
    sequence_number = _current_sequence_number(item=item, board=board)
    if sequence_number is None:
        return CellLevelBoardAssessment(changed, None, "SYMBOL_CELL_REVIEW_SEQUENCE_MISSING")
    topology = _board_topology(board)
    visible = sorted(
        (
            cell
            for cell in cells
            if cell.recognized_board_id == board.id
            and (cell.source_available is True or cell.source_visibility == "outside")
        ),
        key=lambda cell: cell.cell_index,
    )
    if [cell.cell_index for cell in visible] != list(range(topology.cell_count)) or any(
        cell.sequence_number != sequence_number or cell.geometry_revision != board.geometry_revision
        for cell in visible
    ):
        return CellLevelBoardAssessment(changed, None, "SYMBOL_CELL_REVIEW_CELLS_INCOMPLETE")
    try:
        reviews = tuple(
            replace(review, review_state=SymbolCellReviewState.PENDING)
            if review.cell_index in changed
            else review
            for review in (
                _symbol_cell_review_from_model(cell, symbol_code_by_id=symbol_code_by_id)
                for cell in visible
            )
        )
    except SymbolCellReviewError as error:
        return CellLevelBoardAssessment(changed, None, error.code)
    resolution = derive_symbol_cell_board_resolution(
        reviews=reviews,
        active_symbol_codes=tuple(symbol_code_by_id.values()),
        topology=topology,
    )
    return CellLevelBoardAssessment(
        changed, None if resolution is None else resolution.action.value, None
    )


def _symbol_cell_review_order_columns() -> tuple[Any, Any, Any]:
    cell = ImageSymbolReviewCellModel
    return cell.sequence_number, cell.cell_index, cell.id


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
    temporarily_unrecognized = cell.source_visibility != "outside" and review.quality_issue in {
        SymbolCellQualityIssue.GRID_ISSUE,
        SymbolCellQualityIssue.UNREADABLE,
    }
    return SymbolCellReviewListItem(
        cell_review_id=cell.id,
        review_item_id=cell.review_item_id,
        recognized_board_id=cell.recognized_board_id,
        import_job_id=cell.import_job_id,
        sequence_number=int(cell.sequence_number),
        cell_index=int(cell.cell_index),
        row_index=int(cell.row_index),
        column_index=int(cell.column_index),
        assigned_symbol_id=None if temporarily_unrecognized else cast(UUID | None, row[2]),
        assigned_symbol_code=None if temporarily_unrecognized else cast(str | None, row[3]),
        assigned_symbol_name=None if temporarily_unrecognized else cast(str | None, row[4]),
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
        source_visibility=_source_visibility(cell),
    )


def _required_crop_sample_id(review: SymbolCellReview) -> str:
    if review.crop.crop_sample_id is None:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_ASSET_UNAVAILABLE",
            "A complete image-board resolution requires real crops.",
        )
    return review.crop.crop_sample_id


def _source_visibility(cell: ImageSymbolReviewCellModel) -> Literal["full", "partial", "outside"]:
    value = cell.source_visibility
    if value in {"full", "partial", "outside"}:
        return cast(Literal["full", "partial", "outside"], value)
    return "partial" if cell.quality_issue == "partial_visibility" else "full"


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
    visibility = _source_visibility(cell)
    identity: SymbolCellCropIdentity | SymbolCellWithoutImageIdentity
    if visibility == "outside":
        if (
            cell.asset_mode != "none"
            or cell.crop_sample_id is not None
            or cell.crop_checksum_sha256 is not None
        ):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_ASSET_INVALID",
                "Outside position contains unexpected crop identity.",
            )
        identity = SymbolCellWithoutImageIdentity(
            cell_index=int(cell.cell_index),
            geometry_revision=int(cell.geometry_revision),
            cropper_version=cell.cropper_version,
        )
    else:
        if cell.crop_sample_id is None or cell.crop_checksum_sha256 is None:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_ASSET_UNAVAILABLE",
                "The visible position has no image identity.",
            )
        identity = SymbolCellCropIdentity(
            cell_index=int(cell.cell_index),
            crop_sample_id=cell.crop_sample_id,
            crop_relative_path=cell.crop_relative_path,
            crop_checksum_sha256=cell.crop_checksum_sha256,
            geometry_revision=int(cell.geometry_revision),
            cropper_version=cell.cropper_version,
            asset_mode=cell.asset_mode,
        )
    return SymbolCellReview(
        crop=identity,
        source_visibility=visibility,
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
    if command.action is SymbolCellReviewAction.MARK_BLURRY:
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
        return mark_symbol_cell_blurry(
            review,
            active_symbol_codes=active_symbol_codes,
            target_symbol_code=target_symbol_code,
        )
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
    if review.approved_crop is None:
        cell.approved_asset_mode = None
        cell.approved_source_geometry_revision_id = None
        cell.approved_render_spec_checksum_sha256 = None
        cell.approved_rendered_pixel_checksum_sha256 = None
    elif cell.asset_mode == "virtual_source":
        if (
            cell.source_geometry_revision_id is None
            or cell.render_spec_checksum_sha256 is None
            or cell.rendered_pixel_checksum_sha256 is None
        ):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_VIRTUAL_PROVENANCE_INVALID",
                "A virtual symbol crop is missing render provenance.",
            )
        cell.approved_asset_mode = "virtual_source"
        cell.approved_source_geometry_revision_id = cell.source_geometry_revision_id
        cell.approved_render_spec_checksum_sha256 = cell.render_spec_checksum_sha256
        cell.approved_rendered_pixel_checksum_sha256 = cell.rendered_pixel_checksum_sha256
    else:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_VIRTUAL_PROVENANCE_INVALID",
            "A symbol crop has an unsupported asset mode.",
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
            previous_assignment_source=previous.assignment_source,
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
            previous_approved_asset_mode=previous.approved_asset_mode,
            approved_asset_mode=cell.approved_asset_mode,
            previous_approved_source_geometry_revision_id=(
                previous.approved_source_geometry_revision_id
            ),
            approved_source_geometry_revision_id=cell.approved_source_geometry_revision_id,
            previous_approved_render_spec_checksum_sha256=(
                previous.approved_render_spec_checksum_sha256
            ),
            approved_render_spec_checksum_sha256=cell.approved_render_spec_checksum_sha256,
            previous_approved_rendered_pixel_checksum_sha256=(
                previous.approved_rendered_pixel_checksum_sha256
            ),
            approved_rendered_pixel_checksum_sha256=(cell.approved_rendered_pixel_checksum_sha256),
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


def _incompatible_prediction_codes(
    *,
    cells: Sequence[ImageReviewCell],
    active_symbol_ids: Mapping[str, UUID],
    model_iteration_id: UUID | None,
) -> tuple[str, ...]:
    """Reject catalog drift for predictions made by a game-specific model.

    Historical bootstrap predictions intentionally have no model iteration and
    remain readable as unknown. Once a trained iteration is involved, silently
    converting a model class to ``?`` would destroy the meaning of the result.
    """

    if model_iteration_id is None:
        return ()
    return tuple(
        sorted(
            {
                code
                for cell in cells
                if (code := _known_symbol_code(cell.predicted_symbol_code)) is not None
                and code not in active_symbol_ids
            }
        )
    )


def _verification_v2(
    *,
    review_state: str,
    quality_issue: str | None,
    assigned_symbol_id: UUID | None,
    prediction_symbol_code: str | None,
    assignment_source: str,
) -> PersistedVerificationV2:
    if (
        review_state == SymbolCellReviewState.PENDING.value
        and assigned_symbol_id is not None
        and assignment_source in {"human", "board_decision"}
        and quality_issue not in {"grid_issue", "unreadable"}
    ):
        # Current runtime intentionally retains a human logical label after
        # recropping. The legacy migration adapter must remain fail-closed.
        return PersistedVerificationV2("requires_review", None)
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


def _outside_human_decision_values(
    cell: ImageSymbolReviewCellModel,
    *,
    new_geometry: bool,
) -> dict[str, object]:
    """D-462 for a human decision on a position without source pixels.

    Only a newly saved geometry resolves a grid report (R5, R7); any other
    synchronization keeps it. A logical decision made without pixels (D-451)
    stays; a verification of pixels that are gone now needs a new check, and
    pixel-bound flags do not carry over (R6).
    """

    had_pixels = cell.crop_sample_id is not None
    review_state = cell.review_state
    quality_issue = cell.quality_issue
    if new_geometry and quality_issue == SymbolCellQualityIssue.GRID_ISSUE.value:
        quality_issue = None
    if had_pixels:
        review_state = SymbolCellReviewState.PENDING.value
        if quality_issue in {
            SymbolCellQualityIssue.BLURRY.value,
            SymbolCellQualityIssue.UNREADABLE.value,
            SymbolCellQualityIssue.PARTIAL_VISIBILITY.value,
        }:
            quality_issue = None
    if review_state == cell.review_state and quality_issue == cell.quality_issue:
        return {}
    verification = _verification_v2(
        review_state=review_state,
        quality_issue=quality_issue,
        assigned_symbol_id=cell.assigned_symbol_id,
        prediction_symbol_code=None,
        assignment_source=cell.assignment_source,
    )
    return {
        "review_state": review_state,
        "quality_issue": quality_issue,
        "verification_outcome": verification.outcome,
        "verified_symbol_id_v2": verification.verified_symbol_id,
    }


def _forced_partial_visibility_projection() -> _CellProjection:
    """A partially visible cell (D-434/435) is never auto-assigned or
    auto-approved from a model prediction -- only a human, reviewing the
    real (if incomplete) pixels, may assign or approve it."""
    return _CellProjection(
        assigned_symbol_id=None,
        review_state=SymbolCellReviewState.PENDING.value,
        assignment_source=SymbolCellAssignmentSource.GEOMETRY_PARTIAL.value,
        quality_issue=SymbolCellQualityIssue.PARTIAL_VISIBILITY.value,
        approved_crop_sample_id=None,
        approved_crop_checksum_sha256=None,
        approved_geometry_revision=None,
        **_projection_approved_asset_kwargs(_empty_approved_asset_projection()),
    )


def _cell_matches_projection(
    cell: ImageSymbolReviewCellModel,
    *,
    review_cell: ImageReviewCell,
    cropper_version: str,
    prediction_revision_id: UUID | None,
    target: _CellProjection,
    import_job_id: UUID,
    review_item_id: UUID,
    recognized_board_id: UUID,
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
        cell.import_job_id == import_job_id
        and cell.review_item_id == review_item_id
        and cell.recognized_board_id == recognized_board_id
        and cell.sequence_number == sequence_number
        and cell.crop_sample_id == review_cell.crop_sample_id
        and cell.crop_relative_path == review_cell.crop_relative_path
        and cell.asset_mode == review_cell.asset_mode
        and cell.source_geometry_revision_id == review_cell.source_geometry_revision_id
        and cell.logical_cell_key == review_cell.logical_cell_key
        and cell.logical_cell_key_v2 == review_cell.logical_cell_key_v2
        and cell.render_identity_v2_sha256 == review_cell.render_identity_v2_sha256
        # D-467 S7: the checksum of the canonical render specification is the
        # comparison key; the write-only column is never read back.
        and cell.render_spec_checksum_sha256 == review_cell.render_spec_checksum_sha256
        and cell.rendered_pixel_checksum_sha256 == review_cell.rendered_pixel_checksum_sha256
        and cell.extractor_version == review_cell.extractor_version
        and cell.crop_checksum_sha256 == review_cell.crop_checksum_sha256
        and cell.geometry_revision == geometry_revision
        and cell.cropper_version == cropper_version
        and cell.prediction_symbol_code == _known_symbol_code(review_cell.predicted_symbol_code)
        and cell.prediction_confidence == review_cell.confidence
        and cell.prediction_revision_id == prediction_revision_id
        and cell.assigned_symbol_id == target.assigned_symbol_id
        and cell.review_state == target.review_state
        and cell.quality_issue == target.quality_issue
        and cell.verification_outcome == verification.outcome
        and cell.verified_symbol_id_v2 == verification.verified_symbol_id
        and cell.approved_crop_sample_id == target.approved_crop_sample_id
        and cell.approved_crop_checksum_sha256 == target.approved_crop_checksum_sha256
        and cell.approved_geometry_revision == target.approved_geometry_revision
        and cell.approved_asset_mode == target.approved_asset_mode
        and cell.approved_source_geometry_revision_id == target.approved_source_geometry_revision_id
        and cell.approved_render_spec_checksum_sha256 == target.approved_render_spec_checksum_sha256
        and cell.approved_rendered_pixel_checksum_sha256
        == target.approved_rendered_pixel_checksum_sha256
        and cell.assignment_source == target.assignment_source
    )


def _apply_cell_projection(
    cell: ImageSymbolReviewCellModel,
    *,
    review_cell: ImageReviewCell,
    cropper_version: str,
    prediction_revision_id: UUID | None,
    target: _CellProjection,
    import_job_id: UUID,
    review_item_id: UUID,
    recognized_board_id: UUID,
    sequence_number: int,
    geometry_revision: int,
    actor: str,
) -> None:
    cell.import_job_id = import_job_id
    cell.review_item_id = review_item_id
    cell.recognized_board_id = recognized_board_id
    cell.sequence_number = sequence_number
    cell.crop_sample_id = review_cell.crop_sample_id
    cell.crop_relative_path = review_cell.crop_relative_path
    cell.asset_mode = review_cell.asset_mode
    cell.source_geometry_revision_id = review_cell.source_geometry_revision_id
    cell.logical_cell_key = review_cell.logical_cell_key
    cell.logical_cell_key_v2 = review_cell.logical_cell_key_v2
    cell.render_identity_v2_sha256 = review_cell.render_identity_v2_sha256
    cell.render_spec_checksum_sha256 = review_cell.render_spec_checksum_sha256
    cell.rendered_pixel_checksum_sha256 = review_cell.rendered_pixel_checksum_sha256
    cell.extractor_version = review_cell.extractor_version
    cell.crop_checksum_sha256 = review_cell.crop_checksum_sha256
    cell.geometry_revision = geometry_revision
    cell.cropper_version = cropper_version
    cell.prediction_symbol_code = _known_symbol_code(review_cell.predicted_symbol_code)
    cell.prediction_confidence = review_cell.confidence
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
    cell.approved_asset_mode = target.approved_asset_mode
    cell.approved_source_geometry_revision_id = target.approved_source_geometry_revision_id
    cell.approved_render_spec_checksum_sha256 = target.approved_render_spec_checksum_sha256
    cell.approved_rendered_pixel_checksum_sha256 = target.approved_rendered_pixel_checksum_sha256
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
                count_projection_status="rebuilding",
                count_projection={"_building_semantics": dict(_COUNT_SEMANTICS)},
                count_projection_revision=0,
                count_rebuild_cursor=None,
                count_rebuild_accumulator={},
                count_projection_failure_message=None,
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

    def start_count_rebuild(self, game_id: UUID) -> None:
        """Fence writes and reset only the per-game count reconstruction state."""

        state = self._session.get(ImageSymbolReviewStateModel, game_id, with_for_update=True)
        if state is None or state.status != "ready":
            raise SymbolCellReviewBackfillError(
                "SYMBOL_CELL_REVIEW_COUNT_REBUILD_NOT_READY",
                "The current symbol-cell projection must be ready before counts are rebuilt.",
            )
        state.status = "rebuilding"
        state.count_projection_status = "rebuilding"
        state.count_rebuild_cursor = None
        state.count_rebuild_accumulator = {"_building": dict(_COUNT_SEMANTICS)}
        state.count_projection_failure_message = None
        self._session.flush()

    def ensure_current_count_projection_next_batch(
        self, game_id: UUID, *, batch_size: int = 5_000
    ) -> bool:
        """Finish historical count repair without rescanning a ready projection."""
        state = self._session.get(ImageSymbolReviewStateModel, game_id, with_for_update=True)
        if (
            state is not None
            and state.count_projection_status == "ready"
            and _count_semantics_current(state)
        ):
            return True
        if state is None:
            raise SymbolCellReviewBackfillError(
                "SYMBOL_CELL_REVIEW_COUNT_REBUILD_NOT_READY",
                "The symbol-cell projection must exist before counts are rebuilt.",
            )
        # Reuse the persisted accumulator on a cold handler retry. The normal
        # backfill may have republished crop readiness before reaching this step.
        if (
            state.count_projection_status != "rebuilding"
            or state.count_rebuild_accumulator.get("_building") != _COUNT_SEMANTICS
        ):
            self.start_count_rebuild(game_id)
        return self.rebuild_count_projection_next_batch(game_id, batch_size=batch_size)

    def rebuild_count_projection_next_batch(
        self,
        game_id: UUID,
        *,
        batch_size: int = 5_000,
    ) -> bool:
        """Resume a keyset count rebuild; return True after atomic publication."""

        if not 1 <= batch_size <= 10_000:
            raise ValueError("batch_size must be between 1 and 10000")
        state = self._session.get(ImageSymbolReviewStateModel, game_id, with_for_update=True)
        if state is None or state.count_projection_status != "rebuilding":
            raise SymbolCellReviewBackfillError(
                "SYMBOL_CELL_REVIEW_COUNT_REBUILD_NOT_STARTED",
                "Start the symbol review count rebuild before processing a batch.",
            )
        statement = (
            select(
                ImageSymbolReviewCellModel.id,
                ImageSymbolReviewCellModel.source_available,
                ImageSymbolReviewCellModel.assigned_symbol_id,
                ImageSymbolReviewCellModel.review_state,
                ImageSymbolReviewCellModel.quality_issue,
                ImageSymbolReviewCellModel.source_visibility,
            )
            .where(
                ImageSymbolReviewCellModel.game_id == game_id,
                # TASK-0949: cells of rejected boards are not counted.
                ~exists().where(
                    ImageReviewItemModel.id == ImageSymbolReviewCellModel.review_item_id,
                    ImageReviewItemModel.status == "rejected",
                ),
            )
            .order_by(ImageSymbolReviewCellModel.id)
            .limit(batch_size)
        )
        if state.count_rebuild_cursor is not None:
            statement = statement.where(ImageSymbolReviewCellModel.id > state.count_rebuild_cursor)
        if state.count_rebuild_accumulator.get("_building") != _COUNT_SEMANTICS:
            state.count_rebuild_cursor = None
            state.count_rebuild_accumulator = {"_building": dict(_COUNT_SEMANTICS)}
            self._session.flush()
            return False
        rows = self._session.execute(statement).all()
        if not rows:
            state.count_projection = {
                key: value
                for key, value in state.count_rebuild_accumulator.items()
                if key != "_building"
            }
            state.count_projection[_COUNT_SEMANTICS_KEY] = dict(_COUNT_SEMANTICS)
            state.count_projection_revision += 1
            state.count_projection_status = "ready"
            state.count_rebuild_cursor = None
            state.count_rebuild_accumulator = {}
            state.count_projection_failure_message = None
            state.status = "ready"
            state.catalog_revision += 1
            self._session.flush()
            return True
        states = tuple(
            _CountedCellState(
                source_available=bool(row[1]),
                assigned_symbol_id=cast(UUID | None, row[2]),
                review_state=str(row[3]),
                quality_issue=cast(str | None, row[4]),
                source_visibility=cast(str | None, row[5]),
            )
            for row in rows
        )
        deltas = _count_deltas((), states)
        state.count_rebuild_accumulator = _apply_count_delta_payload(
            state.count_rebuild_accumulator,
            deltas,
        )
        state.count_rebuild_cursor = cast(UUID, rows[-1][0])
        self._session.flush()
        return False

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
        # D-484 (TASK-0807): boards of incomplete images are not cut; the
        # cursor still moves over them (they are cut once the image is admitted).
        withheld = withheld_review_item_ids(
            self._session,
            game_id,
            ((item.id, board, source) for _document, item, board, source, _queue, _job in rows),
        )
        admitted_rows = tuple(row for row in rows if row[1].id not in withheld)
        try:
            values = self._cell_values(admitted_rows) if admitted_rows else []
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
            inserted = self._session.execute(
                statement.on_conflict_do_nothing(
                    index_elements=_backfill_cell_conflict_columns(self._session, game_id)
                ).returning(
                    ImageSymbolReviewCellModel.source_available,
                    ImageSymbolReviewCellModel.assigned_symbol_id,
                    ImageSymbolReviewCellModel.review_state,
                    ImageSymbolReviewCellModel.quality_issue,
                    ImageSymbolReviewCellModel.source_visibility,
                )
            ).all()
            _apply_count_deltas(
                state,
                after=tuple(
                    _CountedCellState(
                        source_available=bool(row[0]),
                        assigned_symbol_id=cast(UUID | None, row[1]),
                        review_state=str(row[2]),
                        quality_issue=cast(str | None, row[3]),
                        source_visibility=cast(str | None, row[4]),
                    )
                    for row in inserted
                ),
            )
        coordinator = SymbolCellReviewWriteThroughCoordinator(self._session)
        for _document, item, _board, _source, _queue, _job in admitted_rows:
            coordinator.synchronize_for_backfill_reconciliation(
                game_id=game_id, review_item_id=item.id
            )
        state.last_review_item_id = rows[-1][1].id
        state.processed_review_item_count += len(rows)
        state.cell_count = self._current_selected_cell_count(game_id)
        self._session.flush()
        return SymbolCellReviewBackfillStep(
            report=self._report_from_state(state),
            processed_review_item_count=len(rows),
            has_more=len(rows) == batch_size,
            geometry_withheld_review_item_count=len(withheld),
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
        if (
            state.count_projection_status == "rebuilding"
            and not state.count_rebuild_accumulator
            and state.count_projection.get("_building_semantics") == _COUNT_SEMANTICS
        ):
            state.count_projection = {
                key: value
                for key, value in state.count_projection.items()
                if key != "_building_semantics"
            }
            state.count_projection[_COUNT_SEMANTICS_KEY] = dict(_COUNT_SEMANTICS)
            state.count_projection_status = "ready"
            state.count_projection_failure_message = None
        state.catalog_revision += 1
        record_super_game_input_change(self._session, game_id, source="symbol_cell_backfill")
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
        cell_sources_by_board = load_current_board_cell_sources(
            self._session,
            ((board, document.game_id) for document, _item, board, _source, _queue, _job in rows),
        )
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
        for document, item, board, source, _queue_item, _job in rows:
            prediction_revision = prediction_by_item.get(item.id)
            prediction_override = (
                None if prediction_revision is None else list(prediction_revision.predictions)
            )
            current_geometry = revisions_by_board.get(board.id)
            cell_sources = cell_sources_by_board.get(board.id, NO_CELL_SOURCES)
            try:
                current_cells = materialize_current_image_review_cells(
                    item=item,
                    board=board,
                    cell_sources=cell_sources,
                    prediction_override=prediction_override,
                )
                incompatible_prediction_codes = _incompatible_prediction_codes(
                    cells=current_cells,
                    active_symbol_ids=active_symbol_ids,
                    model_iteration_id=(
                        None
                        if prediction_revision is None
                        else prediction_revision.model_iteration_id
                    ),
                )
                if incompatible_prediction_codes:
                    raise SymbolCellReviewBackfillError(
                        "SYMBOL_MODEL_CLASS_CATALOG_MISMATCH",
                        "A trained model prediction contains classes outside the game's active "
                        f"symbol catalog: {', '.join(incompatible_prediction_codes)}.",
                        review_item_ids=(item.id,),
                        invalid_crop_count=1,
                    )
                cropper_version = _current_cropper_version(
                    board=board,
                    cell_sources=cell_sources,
                    geometry=current_geometry,
                )
                mapped = map_current_symbol_cell_reviews(
                    cells=current_cells,
                    geometry_revision=board.geometry_revision,
                    cropper_version=cropper_version,
                    topology=_board_topology(board),
                    unavailable_cell_indices=(
                        _fully_unavailable_cell_indices(board)
                        if board.geometry_qualification is not None
                        else None
                    ),
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

            current_cells_by_index = {cell.cell_index: cell for cell in current_cells}
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
                        "row_index": current_cells_by_index[review.cell_index].row_index,
                        "column_index": current_cells_by_index[review.cell_index].column_index,
                        **_asset_provenance_values(current_cells_by_index[review.cell_index]),
                        "crop_sample_id": review.crop.crop_sample_id,
                        "crop_relative_path": review.crop.crop_relative_path,
                        "crop_checksum_sha256": review.crop.crop_checksum_sha256,
                        "geometry_revision": review.crop.geometry_revision,
                        "cropper_version": review.crop.cropper_version,
                        "prediction_symbol_code": review.predicted_symbol_code,
                        "prediction_confidence": current_cells_by_index[
                            review.cell_index
                        ].confidence,
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
                        **(
                            _approved_asset_provenance_from_review_cell(
                                current_cells_by_index[review.cell_index]
                            )
                            if approved
                            else _empty_approved_asset_provenance()
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
        expected_count = func.coalesce(RecognizedBoardModel.grid_rows, 3) * func.coalesce(
            RecognizedBoardModel.grid_columns, 5
        ) - _excluded_cell_count_sql(RecognizedBoardModel)
        counts = (
            select(
                ImageBoardSearchFastDocumentModel.review_item_id.label("review_item_id"),
                func.count(ImageSymbolReviewCellModel.id).label("cell_count"),
            )
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageBoardSearchFastDocumentModel.recognized_board_id,
            )
            .outerjoin(
                ImageSymbolReviewCellModel,
                and_(
                    ImageSymbolReviewCellModel.review_item_id
                    == ImageBoardSearchFastDocumentModel.review_item_id,
                    ImageSymbolReviewCellModel.source_available.is_(True),
                ),
            )
            .where(ImageBoardSearchFastDocumentModel.game_id == game_id)
            .group_by(ImageBoardSearchFastDocumentModel.review_item_id, expected_count)
            .having(func.count(ImageSymbolReviewCellModel.id) != expected_count)
            .order_by(ImageBoardSearchFastDocumentModel.review_item_id)
        )
        incomplete = tuple(cast(UUID, value) for value in self._session.scalars(counts))
        if not incomplete:
            return ()
        # D-484 (TASK-0807): a board the geometry gate withholds has no cells
        # by design; it is not an incomplete backfill.
        rows = self._session.execute(
            select(ImageReviewItemModel.id, RecognizedBoardModel, SourceImageModel)
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .where(ImageReviewItemModel.id.in_(incomplete))
        ).tuples()
        withheld = withheld_review_item_ids(self._session, game_id, rows)
        return tuple(
            review_item_id for review_item_id in incomplete if review_item_id not in withheld
        )

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
                ImageSymbolReviewCellModel.game_id == game_id,
                ImageSymbolReviewCellModel.geometry_revision
                != RecognizedBoardModel.geometry_revision,
                ImageSymbolReviewCellModel.source_available.is_(True),
            )
            .distinct()
            .order_by(ImageSymbolReviewCellModel.review_item_id)
        )
        return tuple(self._session.scalars(statement))

    def _selected_items_with_stale_base_crop(self, game_id: UUID) -> tuple[UUID, ...]:
        """Revision-0 review cells that no longer match their base render.

        Virtual boards compare against the revision-0 render manifest
        (D-467): a missing manifest or manifest cell is stale.  Legacy boards
        have no revision-0 base since S5 (TASK-0759) dropped their per-cell
        import records; the mapper refuses such a board, so only the virtual
        comparison remains.
        """

        cell = ImageSymbolReviewCellModel
        manifest = BoardRenderManifestModel
        element = func.jsonb_array_elements(manifest.cells["cells"]).table_valued(
            column("value", JSONB)
        )
        manifest_cells = (
            select(
                manifest.recognized_board_id.label("recognized_board_id"),
                manifest.source_geometry_revision_id.label("source_geometry_revision_id"),
                manifest.extractor_version.label("extractor_version"),
                element.c.value["cellIndex"].astext.cast(Integer).label("cell_index"),
                element.c.value["logicalCellKeySha256"].astext.label("logical_cell_key"),
                element.c.value["renderSpecChecksumSha256"].astext.label(
                    "render_spec_checksum_sha256"
                ),
                element.c.value["renderedPixelChecksumSha256"].astext.label(
                    "rendered_pixel_checksum_sha256"
                ),
            )
            .select_from(manifest)
            .join(element, true())
            .where(manifest.game_id == game_id, manifest.geometry_revision == 0)
            .subquery("manifest_cells")
        )
        statement = (
            select(cell.review_item_id)
            .join(
                ImageBoardSearchFastDocumentModel,
                ImageBoardSearchFastDocumentModel.review_item_id == cell.review_item_id,
            )
            .join(RecognizedBoardModel, RecognizedBoardModel.id == cell.recognized_board_id)
            .outerjoin(
                manifest_cells,
                and_(
                    manifest_cells.c.recognized_board_id == cell.recognized_board_id,
                    manifest_cells.c.cell_index == cell.cell_index,
                ),
            )
            .where(
                ImageBoardSearchFastDocumentModel.game_id == game_id,
                # Explicit partition key: it prunes the per-game cell
                # partition at plan time and keeps the query correct when it
                # runs as the schema owner (RLS bypass), not only as the
                # application role (TASK-0795).
                cell.game_id == game_id,
                RecognizedBoardModel.geometry_revision == 0,
                RecognizedBoardModel.asset_mode == "virtual_source",
                cell.source_available.is_(True),
                or_(
                    manifest_cells.c.cell_index.is_(None),
                    # A virtual base crop is identified by its rendered pixel
                    # checksum and has no crop path.
                    manifest_cells.c.rendered_pixel_checksum_sha256 != cell.crop_checksum_sha256,
                    cell.crop_relative_path.is_not(None),
                    manifest_cells.c.extractor_version != cell.cropper_version,
                    cell.asset_mode != "virtual_source",
                    manifest_cells.c.source_geometry_revision_id
                    != cell.source_geometry_revision_id,
                    manifest_cells.c.logical_cell_key != cell.logical_cell_key,
                    manifest_cells.c.render_spec_checksum_sha256
                    != cell.render_spec_checksum_sha256,
                    manifest_cells.c.rendered_pixel_checksum_sha256
                    != cell.rendered_pixel_checksum_sha256,
                ),
            )
            .distinct()
            .order_by(cell.review_item_id)
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
                .where(ImageSymbolReviewCellModel.source_available.is_(True))
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
    cell_sources: CurrentBoardCellSources,
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
    # Revision 0 (D-467): a virtual board's base cropper is its render
    # manifest's extractor (the import writer requires ``cropper_version ==
    # extractor_version``).  A board without a manifest is refused below.
    versions = (
        set()
        if cell_sources.render_manifest is None
        else {cell_sources.render_manifest.extractor_version}
    )
    if (
        not versions
        and getattr(board, "geometry_qualification", None) is not None
        and board.completeness_status == "pending_partial"
        and tuple(board.unavailable_cell_indices) == tuple(range(15))
    ):
        # No asset or extractor exists for a completely unavailable slot.
        return "manual-geometry-no-source-cells-v1"
    if len(versions) != 1:
        raise SymbolCellReviewBackfillError(
            "SYMBOL_CELL_REVIEW_BACKFILL_CROP_INVALID",
            "The base board observations do not have one current cropper version.",
            invalid_crop_count=1,
        )
    return next(iter(versions))


__all__ = [
    "CellLevelBoardAssessment",
    "active_symbol_codes_by_id",
    "assess_cell_level_board",
    "SqlAlchemySymbolCellReviewQueryRepository",
    "SqlAlchemySymbolCellReviewMutationRepository",
    "SqlAlchemyUnreadableBoardReviewRepository",
    "SqlAlchemyGridCorrectionSymbolRepository",
    "SymbolCellReviewWriteThroughCoordinator",
    "SqlAlchemyImageSymbolReviewRepository",
    "SymbolCellReviewBackfillError",
    "SymbolCellReviewBackfillReport",
    "SymbolCellReviewBackfillStep",
    "symbol_cell_review_projection_is_available",
]
