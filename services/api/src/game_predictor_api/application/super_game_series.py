"""Use cases of super game series (TASK-0933, D-535).

Derivation (:class:`SuperGameSeriesDerivation`) is a durable job: it reads
the input version at the start, walks the sequence in batches of positions
(separate read transactions), writes the candidate generation to the working
table in batches (separate write transactions) and finally publishes it in
**one** transaction that locks the derivation state row ``FOR UPDATE`` and
compares the input version atomically with the swap.  A changed input version
rejects the candidate (the published series stay untouched) and leaves
exactly one queued re-run of the game.  A restarted job discards the working
rows of earlier, unpublished generations, so no intermediate state is ever
served.

Reads and the operator's super symbol definition
(:class:`SuperGameSeriesService`) run in the request transaction.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final, Protocol
from uuid import UUID

from game_predictor_api.domain.super_game_series import (
    BoardTrigger,
    DerivedSuperGameSeries,
    RunVerification,
    SeriesCompleteness,
    SuperGameSeriesConflictError,
    SuperGameSeriesDeriver,
    SuperGameSeriesError,
    SuperGameSeriesNotFoundError,
    SuperGameState,
    series_positions,
    validate_super_symbol_candidate,
)

DEFAULT_POSITION_BATCH_SIZE: Final = 5_000
DEFAULT_GENERATION_WRITE_BATCH_SIZE: Final = 500
DEFAULT_LIST_LIMIT: Final = 50
MAX_LIST_LIMIT: Final = 200
DERIVATION_ACTOR: Final = "super-game-series-derivation"


@dataclass(frozen=True, slots=True)
class SuperGameKindParameters:
    code: str
    series_length: int
    retrigger_extension: int

    @property
    def has_super_game(self) -> bool:
        return self.series_length > 0


@dataclass(frozen=True, slots=True)
class DerivationStart:
    """What a derivation reads in its first transaction."""

    game_id: UUID
    generation_id: UUID
    input_version: int
    expected_layout_count: int
    kind: SuperGameKindParameters
    trigger_thresholds: dict[UUID, int]
    discarded_generation_rows: int


class PublicationStatus(StrEnum):
    PUBLISHED = "published"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class PublicationOutcome:
    status: PublicationStatus
    input_version: int
    inserted: int = 0
    updated: int = 0
    removed: int = 0
    rerun_job_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class DerivationReport:
    game_id: UUID
    generation_id: UUID
    status: PublicationStatus
    expected_input_version: int
    current_input_version: int
    series_count: int
    trigger_board_count: int
    position_batch_count: int
    inserted: int
    updated: int
    removed: int
    rerun_job_id: UUID | None


class SuperGameSeriesDerivationStore(Protocol):
    def begin_generation(self, game_id: UUID) -> DerivationStart: ...

    def next_trigger_candidate(
        self, start: DerivationStart, *, after_sequence_number: int
    ) -> int | None: ...

    def read_trigger_boards(
        self,
        start: DerivationStart,
        *,
        after_sequence_number: int,
        until_sequence_number: int,
    ) -> list[BoardTrigger]: ...

    def last_known_sequence_number(self, start: DerivationStart, *, window: int) -> int | None: ...

    def write_generation_rows(
        self, start: DerivationStart, rows: Sequence[DerivedSuperGameSeries]
    ) -> None: ...

    def publish_generation(self, start: DerivationStart, *, actor: str) -> PublicationOutcome: ...


ProgressCallback = Callable[[int, int, int], None]


class SuperGameSeriesDerivation:
    """Build one complete generation and publish it atomically, or reject it."""

    def __init__(
        self,
        store: SuperGameSeriesDerivationStore,
        *,
        position_batch_size: int = DEFAULT_POSITION_BATCH_SIZE,
        write_batch_size: int = DEFAULT_GENERATION_WRITE_BATCH_SIZE,
    ) -> None:
        if position_batch_size < 1 or write_batch_size < 1:
            raise ValueError("Batch sizes must be positive.")
        self._store = store
        self._position_batch_size = position_batch_size
        self._write_batch_size = write_batch_size

    def derive(
        self, game_id: UUID, *, progress: ProgressCallback | None = None
    ) -> DerivationReport:
        start = self._store.begin_generation(game_id)
        series_count = 0
        trigger_board_count = 0
        batch_count = 0
        if start.kind.has_super_game and start.trigger_thresholds:
            deriver = SuperGameSeriesDeriver(
                series_length=start.kind.series_length,
                retrigger_extension=start.kind.retrigger_extension,
                expected_layout_count=start.expected_layout_count,
            )
            pending: list[DerivedSuperGameSeries] = []
            after = 0
            total = start.expected_layout_count
            while after < total:
                # Positions without any trigger-symbol cell never change the
                # state, so the window jumps to the next candidate position.
                candidate = self._store.next_trigger_candidate(start, after_sequence_number=after)
                if candidate is None or candidate > total:
                    after = total
                    break
                window_start = max(after, candidate - 1)
                until = min(window_start + self._position_batch_size, total)
                boards = self._store.read_trigger_boards(
                    start, after_sequence_number=window_start, until_sequence_number=until
                )
                batch_count += 1
                trigger_board_count += len(boards)
                for board in boards:
                    pending.extend(deriver.feed(board))
                if len(pending) >= self._write_batch_size:
                    self._store.write_generation_rows(start, pending)
                    series_count += len(pending)
                    pending = []
                after = until
                if progress is not None:
                    progress(after, total, series_count + len(pending))
            if progress is not None:
                progress(total, total, series_count + len(pending))
            last_known = self._store.last_known_sequence_number(
                start, window=self._position_batch_size
            )
            pending.extend(deriver.finish(last_known_sequence_number=last_known))
            if pending:
                self._store.write_generation_rows(start, pending)
                series_count += len(pending)
        outcome = self._store.publish_generation(start, actor=DERIVATION_ACTOR)
        return DerivationReport(
            game_id=game_id,
            generation_id=start.generation_id,
            status=outcome.status,
            expected_input_version=start.input_version,
            current_input_version=outcome.input_version,
            series_count=series_count,
            trigger_board_count=trigger_board_count,
            position_batch_count=batch_count,
            inserted=outcome.inserted,
            updated=outcome.updated,
            removed=outcome.removed,
            rerun_job_id=outcome.rerun_job_id,
        )


@dataclass(frozen=True, slots=True)
class SuperGameSeriesRecord:
    id: UUID
    game_id: UUID
    trigger_sequence_number: int
    start_sequence_number: int
    length: int
    retrigger_sequence_numbers: tuple[int, ...]
    completeness: SeriesCompleteness
    run_verification: RunVerification
    super_symbol_id: UUID | None
    defined_by: str | None
    defined_at: datetime | None
    revision: int
    generation_id: UUID
    updated_at: datetime

    @property
    def end_sequence_number(self) -> int:
        return self.start_sequence_number + self.length - 1


@dataclass(frozen=True, slots=True)
class SuperGameSeriesFilter:
    completeness: SeriesCompleteness | None = None
    run_verification: RunVerification | None = None
    defined: bool | None = None


@dataclass(frozen=True, slots=True)
class SuperGameSeriesCounts:
    """Exact counts of the published series of one game, whatever the filters."""

    total: int
    undefined: int


@dataclass(frozen=True, slots=True)
class SuperGameSeriesPage:
    items: tuple[SuperGameSeriesRecord, ...]
    next_cursor: str | None
    state: SuperGameState
    super_game_kind: str
    counts: SuperGameSeriesCounts


@dataclass(frozen=True, slots=True)
class SeriesBoardDocument:
    """One board of the board-search projection (same fields as a search result)."""

    sequence_number: int
    asset_mode: str
    review_item_id: UUID
    recognized_board_id: UUID
    import_job_id: UUID
    status: str
    board_checksum_sha256: str


class SeriesBoardRole(StrEnum):
    TRIGGER = "trigger"
    RETRIGGER = "retrigger"
    SPIN = "spin"


@dataclass(frozen=True, slots=True)
class SeriesBoard:
    sequence_number: int
    role: SeriesBoardRole
    spin_index: int | None
    missing: bool
    document: SeriesBoardDocument | None


@dataclass(frozen=True, slots=True)
class SeriesBoards:
    series: SuperGameSeriesRecord
    boards: tuple[SeriesBoard, ...]
    state: SuperGameState


@dataclass(frozen=True, slots=True)
class GameSuperGameContext:
    game_id: UUID
    super_game_kind: str
    has_super_game: bool
    expected_layout_count: int


@dataclass(frozen=True, slots=True)
class SuperSymbolCandidate:
    id: UUID
    is_wildcard: bool
    super_game_trigger_count: int | None
    status: str


@dataclass(frozen=True, slots=True)
class DeriveRequestResult:
    job_id: UUID
    deduplicated: bool
    state: SuperGameState


class SuperGameSeriesRepository(Protocol):
    def game_context(self, game_id: UUID) -> GameSuperGameContext | None: ...

    def state(self, context: GameSuperGameContext) -> SuperGameState: ...

    def list_series(
        self,
        game_id: UUID,
        *,
        filters: SuperGameSeriesFilter,
        after_trigger: int | None,
        limit: int,
    ) -> list[SuperGameSeriesRecord]: ...

    def series_counts(self, game_id: UUID) -> SuperGameSeriesCounts: ...

    def get_series(
        self, game_id: UUID, series_id: UUID, *, for_update: bool = False
    ) -> SuperGameSeriesRecord | None: ...

    def symbol(self, game_id: UUID, symbol_id: UUID) -> SuperSymbolCandidate | None: ...

    def define_super_symbol(
        self,
        series: SuperGameSeriesRecord,
        *,
        symbol_id: UUID | None,
        actor: str,
    ) -> SuperGameSeriesRecord: ...

    def board_documents(
        self, game_id: UUID, sequence_numbers: Sequence[int]
    ) -> dict[int, SeriesBoardDocument]: ...

    def enqueue_derive(self, game_id: UUID) -> tuple[UUID, bool]: ...

    def begin_read_snapshot(self) -> None:
        """Make the rest of the request one read-only consistent snapshot."""
        ...


def _parse_cursor(cursor: str | None) -> int | None:
    if cursor is None:
        return None
    if not cursor.isdigit() or len(cursor) > 9:
        raise SuperGameSeriesError(
            "SUPER_GAME_SERIES_CURSOR_INVALID", "The cursor is not a valid series cursor."
        )
    return int(cursor)


class SuperGameSeriesService:
    """Request-scoped reads, derive requests and the super symbol definition."""

    def __init__(self, repository: SuperGameSeriesRepository) -> None:
        self._repository = repository

    def _context(self, game_id: UUID) -> GameSuperGameContext:
        context = self._repository.game_context(game_id)
        if context is None:
            raise SuperGameSeriesNotFoundError(
                "GAME_NOT_FOUND", "Game does not exist.", details={"gameId": str(game_id)}
            )
        return context

    def state(self, game_id: UUID) -> SuperGameState:
        self._repository.begin_read_snapshot()
        return self._repository.state(self._context(game_id))

    def list(
        self,
        game_id: UUID,
        *,
        filters: SuperGameSeriesFilter | None = None,
        cursor: str | None = None,
        limit: int = DEFAULT_LIST_LIMIT,
    ) -> SuperGameSeriesPage:
        if not 1 <= limit <= MAX_LIST_LIMIT:
            raise SuperGameSeriesError(
                "SUPER_GAME_SERIES_LIMIT_INVALID",
                f"The limit must be between 1 and {MAX_LIST_LIMIT}.",
            )
        after = _parse_cursor(cursor)
        # Audit P0-5: state and series come from one snapshot, so `fresh`
        # always describes the generation of the returned series.
        self._repository.begin_read_snapshot()
        context = self._context(game_id)
        state = self._repository.state(context)
        if not context.has_super_game:
            return SuperGameSeriesPage(
                items=(),
                next_cursor=None,
                state=state,
                super_game_kind=context.super_game_kind,
                counts=SuperGameSeriesCounts(total=0, undefined=0),
            )
        rows = self._repository.list_series(
            game_id,
            filters=filters or SuperGameSeriesFilter(),
            after_trigger=after,
            limit=limit + 1,
        )
        items = tuple(rows[:limit])
        next_cursor = str(items[-1].trigger_sequence_number) if len(rows) > limit else None
        return SuperGameSeriesPage(
            items=items,
            next_cursor=next_cursor,
            state=state,
            super_game_kind=context.super_game_kind,
            # Same snapshot as the page: the counts describe the returned generation.
            counts=self._repository.series_counts(game_id),
        )

    def _visible_series(
        self, context: GameSuperGameContext, series_id: UUID, *, for_update: bool = False
    ) -> SuperGameSeriesRecord:
        series = (
            self._repository.get_series(context.game_id, series_id, for_update=for_update)
            if context.has_super_game
            else None
        )
        if series is None:
            raise SuperGameSeriesNotFoundError(
                "SUPER_GAME_SERIES_NOT_FOUND",
                "The super game series does not exist.",
                details={"seriesId": str(series_id)},
            )
        return series

    def boards(self, game_id: UUID, series_id: UUID) -> SeriesBoards:
        # Audit P0-5: series, board documents and state from one snapshot.
        self._repository.begin_read_snapshot()
        context = self._context(game_id)
        series = self._visible_series(context, series_id)
        positions = series_positions(
            series.trigger_sequence_number, series.length, context.expected_layout_count
        )
        documents = self._repository.board_documents(game_id, list(positions))
        retriggers = set(series.retrigger_sequence_numbers)
        boards: list[SeriesBoard] = []
        for position in positions:
            if position == series.trigger_sequence_number:
                role = SeriesBoardRole.TRIGGER
                spin_index = None
            else:
                role = SeriesBoardRole.RETRIGGER if position in retriggers else SeriesBoardRole.SPIN
                spin_index = position - series.trigger_sequence_number
            document = documents.get(position)
            boards.append(
                SeriesBoard(
                    sequence_number=position,
                    role=role,
                    spin_index=spin_index,
                    missing=document is None,
                    document=document,
                )
            )
        return SeriesBoards(
            series=series, boards=tuple(boards), state=self._repository.state(context)
        )

    def set_super_symbol(
        self,
        game_id: UUID,
        series_id: UUID,
        *,
        symbol_id: UUID | None,
        expected_revision: int,
        actor: str,
    ) -> SuperGameSeriesRecord:
        context = self._context(game_id)
        series = self._visible_series(context, series_id, for_update=True)
        if series.revision != expected_revision:
            raise SuperGameSeriesConflictError(
                "SUPER_GAME_SERIES_REVISION_CONFLICT",
                "The series changed since it was read; reload it and retry.",
                details={
                    "seriesId": str(series_id),
                    "expectedRevision": expected_revision,
                    "currentRevision": series.revision,
                },
            )
        if symbol_id is not None:
            symbol = self._repository.symbol(game_id, symbol_id)
            if symbol is None:
                raise SuperGameSeriesError(
                    "SUPER_SYMBOL_NOT_FOUND",
                    "The symbol does not belong to this game.",
                    details={"symbolId": str(symbol_id)},
                )
            validate_super_symbol_candidate(
                is_wildcard=symbol.is_wildcard,
                super_game_trigger_count=symbol.super_game_trigger_count,
                status=symbol.status,
            )
        return self._repository.define_super_symbol(series, symbol_id=symbol_id, actor=actor)

    def request_derive(self, game_id: UUID) -> DeriveRequestResult:
        context = self._context(game_id)
        job_id, created = self._repository.enqueue_derive(game_id)
        return DeriveRequestResult(
            job_id=job_id, deduplicated=not created, state=self._repository.state(context)
        )


__all__ = [
    "DEFAULT_GENERATION_WRITE_BATCH_SIZE",
    "DEFAULT_LIST_LIMIT",
    "DEFAULT_POSITION_BATCH_SIZE",
    "DERIVATION_ACTOR",
    "MAX_LIST_LIMIT",
    "DerivationReport",
    "DerivationStart",
    "DeriveRequestResult",
    "GameSuperGameContext",
    "PublicationOutcome",
    "PublicationStatus",
    "SeriesBoard",
    "SeriesBoardDocument",
    "SeriesBoardRole",
    "SeriesBoards",
    "SuperGameKindParameters",
    "SuperGameSeriesDerivation",
    "SuperGameSeriesDerivationStore",
    "SuperGameSeriesFilter",
    "SuperGameSeriesPage",
    "SuperGameSeriesRecord",
    "SuperGameSeriesRepository",
    "SuperGameSeriesService",
    "SuperSymbolCandidate",
]
