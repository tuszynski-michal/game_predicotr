"""PostgreSQL storage of super game series (TASK-0933, D-535).

Two adapters:

- :class:`SqlAlchemySuperGameSeriesRepository` works in the caller's
  request transaction (list, boards, state, super symbol CAS, derive request);
- :class:`SqlAlchemySuperGameSeriesDerivationStore` owns its transactions:
  one per read batch, one per working-row write batch and one final
  publication transaction that locks the derivation state row.

Derivation input contract: the cells of ``image_symbol_review_cells`` with an
assigned symbol (human decision or model prediction, including ``pending``
boards) of active review items (``pending``, ``accepted``, ``corrected``),
not the canonical ``accepted/corrected`` projection.  One board counts per
position: the canonical review item when the position has one, otherwise the
active item with the smallest id (at most one ``pending`` item per position
exists).  A board counts only when it is fully cut: 15 cells, each with
geometry (``asset_mode <> 'none'``) at the board's current geometry revision.
A cell is human-decided when it is ``approved`` or its assignment source is
``human``/``board_decision``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Final
from uuid import UUID, uuid4

from game_predictor_worker.domain.super_games import (
    get_super_game_kind,
    is_known_super_game_kind,
)
from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_api.application.super_game_series import (
    DerivationStart,
    GameSuperGameContext,
    PublicationOutcome,
    PublicationStatus,
    SeriesBoardDocument,
    SuperGameKindParameters,
    SuperGameSeriesFilter,
    SuperGameSeriesRecord,
    SuperSymbolCandidate,
)
from game_predictor_api.domain.board_search import BoardSearchAssetMode
from game_predictor_api.domain.super_game_series import (
    BoardTrigger,
    DerivedSuperGameSeries,
    RunVerification,
    SeriesCompleteness,
    SuperGameSeriesConflictError,
    SuperGameSeriesNotFoundError,
    SuperGameState,
    TriggerCellCount,
    evaluate_board_trigger,
)
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
)
from game_predictor_api.storage.models import (
    GameModel,
    ImageBoardSearchFastDocumentModel,
    ImageBoardSearchProjectionStateModel,
    SymbolModel,
)
from game_predictor_api.storage.super_game_input_version import (
    enqueue_super_game_series_derive,
    lock_super_game_state,
)
from game_predictor_api.storage.super_game_series_models import (
    SuperGameDerivationStateModel,
    SuperGameSeriesAuditEventModel,
    SuperGameSeriesGenerationRowModel,
    SuperGameSeriesModel,
)

BOARD_CELL_COUNT: Final = 15

_TRIGGER_CELL_COUNTS_SQL: Final = text("""
SELECT c.sequence_number, c.review_item_id, c.assigned_symbol_id,
       count(*) AS assigned_count,
       count(*) FILTER (
           WHERE c.review_state = 'approved'
              OR c.assignment_source IN ('human', 'board_decision')
       ) AS human_count
FROM image_symbol_review_cells c
JOIN image_review_items i
  ON i.game_id = c.game_id AND i.id = c.review_item_id
 AND i.status IN ('pending', 'accepted', 'corrected')
WHERE c.game_id = :game_id
  AND c.assigned_symbol_id = ANY(:symbol_ids)
  AND c.sequence_number > :after_sequence_number
  AND c.sequence_number <= :until_sequence_number
GROUP BY c.sequence_number, c.review_item_id, c.assigned_symbol_id
""")

_NEXT_TRIGGER_CANDIDATE_SQL: Final = text("""
SELECT min(n.sequence_number)
FROM unnest(CAST(:symbol_ids AS uuid[])) AS s(id)
CROSS JOIN LATERAL (
    SELECT c.sequence_number FROM image_symbol_review_cells c
    WHERE c.game_id = :game_id AND c.assigned_symbol_id = s.id
      AND c.sequence_number > :after_sequence_number
    ORDER BY c.sequence_number
    LIMIT 1
) AS n
""")

_POSITION_BOARDS_SQL: Final = text("""
SELECT c.sequence_number, c.review_item_id,
       bool_or(k.review_item_id IS NOT NULL) AS is_canonical,
       count(*) AS cell_count,
       count(*) FILTER (
           WHERE c.asset_mode <> 'none' AND c.geometry_revision = b.geometry_revision
       ) AS cut_cell_count
FROM image_symbol_review_cells c
JOIN image_review_items i
  ON i.game_id = c.game_id AND i.id = c.review_item_id
 AND i.status IN ('pending', 'accepted', 'corrected')
JOIN recognized_boards b ON b.game_id = c.game_id AND b.id = c.recognized_board_id
LEFT JOIN image_sequence_canonical k
  ON k.game_id = c.game_id AND k.sequence_number = c.sequence_number
 AND k.review_item_id = c.review_item_id
WHERE c.game_id = :game_id AND c.sequence_number = ANY(:positions)
GROUP BY c.sequence_number, c.review_item_id
""")

_MAX_CELL_SEQUENCE_SQL: Final = text("""
SELECT max(c.sequence_number) FROM image_symbol_review_cells c
WHERE c.game_id = :game_id AND c.sequence_number <= :ceiling
""")

_LAST_CUT_BOARD_IN_WINDOW_SQL: Final = text("""
SELECT c.sequence_number
FROM image_symbol_review_cells c
JOIN image_review_items i
  ON i.game_id = c.game_id AND i.id = c.review_item_id
 AND i.status IN ('pending', 'accepted', 'corrected')
JOIN recognized_boards b ON b.game_id = c.game_id AND b.id = c.recognized_board_id
WHERE c.game_id = :game_id
  AND c.sequence_number > :after_sequence_number
  AND c.sequence_number <= :until_sequence_number
GROUP BY c.sequence_number, c.review_item_id
HAVING count(*) = 15
   AND count(*) FILTER (
       WHERE c.asset_mode <> 'none' AND c.geometry_revision = b.geometry_revision) = 15
ORDER BY c.sequence_number DESC
LIMIT 1
""")

_AUDIT_REMOVED_SERIES_SQL: Final = text("""
INSERT INTO super_game_series_audit_events (
    game_id, id, series_id, trigger_sequence_number, event_kind,
    previous_super_symbol_id, super_symbol_id, previous_revision, revision,
    generation_id, actor)
SELECT s.game_id, gen_random_uuid(), s.id, s.trigger_sequence_number, 'series_removed',
       s.super_symbol_id, NULL, s.revision, NULL, :generation_id, :actor
FROM super_game_series s
WHERE s.game_id = :game_id
  AND NOT EXISTS (
      SELECT 1 FROM super_game_series_generation_rows g
      WHERE g.game_id = s.game_id AND g.generation_id = :generation_id
        AND g.trigger_sequence_number = s.trigger_sequence_number)
""")

_DELETE_REMOVED_SERIES_SQL: Final = text("""
DELETE FROM super_game_series s
WHERE s.game_id = :game_id
  AND NOT EXISTS (
      SELECT 1 FROM super_game_series_generation_rows g
      WHERE g.game_id = s.game_id AND g.generation_id = :generation_id
        AND g.trigger_sequence_number = s.trigger_sequence_number)
""")

_SERIES_CHANGED_PREDICATE: Final = """(
    s.start_sequence_number IS DISTINCT FROM g.start_sequence_number
    OR s.length IS DISTINCT FROM g.length
    OR s.retrigger_sequence_numbers IS DISTINCT FROM g.retrigger_sequence_numbers
    OR s.completeness IS DISTINCT FROM g.completeness
    OR s.run_verification IS DISTINCT FROM g.run_verification)"""

_COUNT_CHANGED_SERIES_SQL: Final = text(f"""
SELECT count(*) FROM super_game_series s
JOIN super_game_series_generation_rows g
  ON g.game_id = s.game_id AND g.generation_id = :generation_id
 AND g.trigger_sequence_number = s.trigger_sequence_number
WHERE s.game_id = :game_id AND {_SERIES_CHANGED_PREDICATE}
""")

# Identity is kept: id, super_symbol_id, revision and defined_* never change here.
_UPDATE_EXISTING_SERIES_SQL: Final = text(f"""
UPDATE super_game_series s
SET start_sequence_number = g.start_sequence_number,
    length = g.length,
    retrigger_sequence_numbers = g.retrigger_sequence_numbers,
    completeness = g.completeness,
    run_verification = g.run_verification,
    generation_id = g.generation_id,
    updated_at = CASE WHEN {_SERIES_CHANGED_PREDICATE} THEN now() ELSE s.updated_at END
FROM super_game_series_generation_rows g
WHERE s.game_id = :game_id
  AND g.game_id = s.game_id AND g.generation_id = :generation_id
  AND g.trigger_sequence_number = s.trigger_sequence_number
""")

_INSERT_NEW_SERIES_SQL: Final = text("""
INSERT INTO super_game_series (
    game_id, id, trigger_sequence_number, start_sequence_number, length,
    retrigger_sequence_numbers, completeness, run_verification, revision, generation_id)
SELECT g.game_id, gen_random_uuid(), g.trigger_sequence_number, g.start_sequence_number,
       g.length, g.retrigger_sequence_numbers, g.completeness, g.run_verification, 0,
       g.generation_id
FROM super_game_series_generation_rows g
WHERE g.game_id = :game_id AND g.generation_id = :generation_id
  AND NOT EXISTS (
      SELECT 1 FROM super_game_series s
      WHERE s.game_id = g.game_id AND s.trigger_sequence_number = g.trigger_sequence_number)
""")


def _rowcount(result: object) -> int:
    count = getattr(result, "rowcount", None)
    return int(count) if isinstance(count, int) and count >= 0 else 0


def _kind_parameters(code: str) -> SuperGameKindParameters:
    if not is_known_super_game_kind(code):
        return SuperGameKindParameters(code=code, series_length=0, retrigger_extension=0)
    kind = get_super_game_kind(code)
    return SuperGameKindParameters(
        code=kind.code,
        series_length=kind.series_length,
        retrigger_extension=kind.retrigger_extension,
    )


def _record(model: SuperGameSeriesModel) -> SuperGameSeriesRecord:
    return SuperGameSeriesRecord(
        id=model.id,
        game_id=model.game_id,
        trigger_sequence_number=model.trigger_sequence_number,
        start_sequence_number=model.start_sequence_number,
        length=model.length,
        retrigger_sequence_numbers=tuple(model.retrigger_sequence_numbers or ()),
        completeness=SeriesCompleteness(model.completeness),
        run_verification=RunVerification(model.run_verification),
        super_symbol_id=model.super_symbol_id,
        defined_by=model.defined_by,
        defined_at=model.defined_at,
        revision=model.revision,
        generation_id=model.generation_id,
        updated_at=model.updated_at,
    )


def _read_state(session: Session, game_id: UUID, *, has_super_game: bool) -> SuperGameState:
    row = session.execute(
        select(
            SuperGameDerivationStateModel.input_version,
            SuperGameDerivationStateModel.input_version_of_generation,
        ).where(SuperGameDerivationStateModel.game_id == game_id)
    ).one_or_none()
    return SuperGameState(
        input_version=0 if row is None else int(row[0]),
        generation_input_version=None if row is None or row[1] is None else int(row[1]),
        has_super_game=has_super_game,
    )


class SqlAlchemySuperGameSeriesRepository:
    """Request-transaction adapter; never commits."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._router = GameStorageRouter()

    def begin_read_snapshot(self) -> None:
        """Start the request transaction as one read-only REPEATABLE READ snapshot.

        Audit TASK-0933 P0-5: a list or boards read takes the series, the board
        documents and the derivation state from the same snapshot, so a
        generation published in between can never pair old series with the new
        `fresh` state. Like the management stake snapshot (TASK-0922) it only
        reads and takes no locks; unlike it, it reuses the request session's
        application-role connection: the isolation level is set when the
        transaction procures its connection, which must be the first use of
        the session (it is: these are the first repository calls of the
        request). The pool resets the isolation level on release.
        """

        connection = self._session.connection(
            execution_options={"isolation_level": "REPEATABLE READ"}
        )
        if connection.dialect.name != "postgresql":
            return
        # SQLAlchemy only warns when the connection was already procured; a
        # snapshot that is not REPEATABLE READ must never be served silently.
        if connection.get_isolation_level() != "REPEATABLE READ":
            raise RuntimeError(
                "A super game series read snapshot must be the first use of the transaction."
            )
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")

    def game_context(self, game_id: UUID) -> GameSuperGameContext | None:
        row = self._session.execute(
            select(GameModel.super_game_kind, GameModel.expected_layout_count).where(
                GameModel.id == game_id
            )
        ).one_or_none()
        if row is None:
            return None
        kind = _kind_parameters(str(row[0]))
        return GameSuperGameContext(
            game_id=game_id,
            super_game_kind=str(row[0]),
            has_super_game=kind.has_super_game,
            expected_layout_count=int(row[1]),
        )

    def state(self, context: GameSuperGameContext) -> SuperGameState:
        self._router.bind(self._session, context.game_id, intent=GameStorageIntent.READ)
        return _read_state(self._session, context.game_id, has_super_game=context.has_super_game)

    def list_series(
        self,
        game_id: UUID,
        *,
        filters: SuperGameSeriesFilter,
        after_trigger: int | None,
        limit: int,
    ) -> list[SuperGameSeriesRecord]:
        self._router.bind(self._session, game_id, intent=GameStorageIntent.READ)
        statement = select(SuperGameSeriesModel).where(SuperGameSeriesModel.game_id == game_id)
        if after_trigger is not None:
            statement = statement.where(
                SuperGameSeriesModel.trigger_sequence_number > after_trigger
            )
        if filters.completeness is not None:
            statement = statement.where(
                SuperGameSeriesModel.completeness == filters.completeness.value
            )
        if filters.run_verification is not None:
            statement = statement.where(
                SuperGameSeriesModel.run_verification == filters.run_verification.value
            )
        if filters.defined is True:
            statement = statement.where(SuperGameSeriesModel.super_symbol_id.is_not(None))
        elif filters.defined is False:
            statement = statement.where(SuperGameSeriesModel.super_symbol_id.is_(None))
        statement = statement.order_by(SuperGameSeriesModel.trigger_sequence_number).limit(limit)
        return [_record(model) for model in self._session.scalars(statement)]

    def get_series(
        self, game_id: UUID, series_id: UUID, *, for_update: bool = False
    ) -> SuperGameSeriesRecord | None:
        intent = GameStorageIntent.WRITE if for_update else GameStorageIntent.READ
        self._router.bind(self._session, game_id, intent=intent)
        statement = select(SuperGameSeriesModel).where(
            SuperGameSeriesModel.game_id == game_id, SuperGameSeriesModel.id == series_id
        )
        if for_update:
            statement = statement.with_for_update()
        # Core UPDATEs (super symbol CAS) bypass the identity map; always reload.
        model = self._session.scalar(statement.execution_options(populate_existing=True))
        return None if model is None else _record(model)

    def symbol(self, game_id: UUID, symbol_id: UUID) -> SuperSymbolCandidate | None:
        model = self._session.scalar(
            select(SymbolModel).where(SymbolModel.game_id == game_id, SymbolModel.id == symbol_id)
        )
        if model is None:
            return None
        return SuperSymbolCandidate(
            id=model.id,
            is_wildcard=bool(model.is_wildcard),
            super_game_trigger_count=model.super_game_trigger_count,
            status=str(getattr(model.status, "value", model.status)),
        )

    def define_super_symbol(
        self,
        series: SuperGameSeriesRecord,
        *,
        symbol_id: UUID | None,
        actor: str,
    ) -> SuperGameSeriesRecord:
        self._router.bind(self._session, series.game_id, intent=GameStorageIntent.WRITE)
        now = datetime.now(UTC)
        result = self._session.execute(
            update(SuperGameSeriesModel)
            .where(
                SuperGameSeriesModel.game_id == series.game_id,
                SuperGameSeriesModel.id == series.id,
                SuperGameSeriesModel.revision == series.revision,
            )
            .values(
                super_symbol_id=symbol_id,
                revision=series.revision + 1,
                defined_by=actor,
                defined_at=now,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if _rowcount(result) != 1:
            raise SuperGameSeriesConflictError(
                "SUPER_GAME_SERIES_REVISION_CONFLICT",
                "The series changed since it was read; reload it and retry.",
                details={"seriesId": str(series.id), "expectedRevision": series.revision},
            )
        self._session.add(
            SuperGameSeriesAuditEventModel(
                game_id=series.game_id,
                id=uuid4(),
                series_id=series.id,
                trigger_sequence_number=series.trigger_sequence_number,
                event_kind="super_symbol_defined",
                previous_super_symbol_id=series.super_symbol_id,
                super_symbol_id=symbol_id,
                previous_revision=series.revision,
                revision=series.revision + 1,
                generation_id=series.generation_id,
                actor=actor,
            )
        )
        self._session.flush()
        updated = self.get_series(series.game_id, series.id)
        if updated is None:  # pragma: no cover - the row is locked by this transaction
            raise SuperGameSeriesNotFoundError(
                "SUPER_GAME_SERIES_NOT_FOUND", "The super game series does not exist."
            )
        return updated

    def board_documents(
        self, game_id: UUID, sequence_numbers: Sequence[int]
    ) -> dict[int, SeriesBoardDocument]:
        self._router.bind(self._session, game_id, intent=GameStorageIntent.READ)
        status = self._session.scalar(
            select(ImageBoardSearchProjectionStateModel.status).where(
                ImageBoardSearchProjectionStateModel.game_id == game_id
            )
        )
        if status != "ready":
            raise SuperGameSeriesConflictError(
                "BOARD_SEARCH_PROJECTION_INCOMPLETE",
                "The board-search projection is not ready for this game.",
            )
        if not sequence_numbers:
            return {}
        document = ImageBoardSearchFastDocumentModel
        rows = self._session.execute(
            select(
                document.sequence_number,
                document.review_item_id,
                document.recognized_board_id,
                document.import_job_id,
                document.status,
                document.board_checksum_sha256,
            ).where(
                document.game_id == game_id,
                document.sequence_number >= min(sequence_numbers),
                document.sequence_number <= max(sequence_numbers),
            )
        ).all()
        wanted = set(sequence_numbers)
        return {
            int(row[0]): SeriesBoardDocument(
                sequence_number=int(row[0]),
                asset_mode=BoardSearchAssetMode.OPERATIONAL_REVIEW.value,
                review_item_id=row[1],
                recognized_board_id=row[2],
                import_job_id=row[3],
                status=str(row[4]),
                board_checksum_sha256=str(row[5]),
            )
            for row in rows
            if int(row[0]) in wanted
        }

    def enqueue_derive(self, game_id: UUID) -> tuple[UUID, bool]:
        return enqueue_super_game_series_derive(self._session, game_id, reason="manual")


class SqlAlchemySuperGameSeriesDerivationStore:
    """Transaction-owning adapter of one derivation pass."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._router = GameStorageRouter()

    def begin_generation(self, game_id: UUID) -> DerivationStart:
        with self._session_factory() as session, session.begin():
            if session.scalar(select(GameModel.id).where(GameModel.id == game_id)) is None:
                raise SuperGameSeriesNotFoundError(
                    "GAME_NOT_FOUND", "Game does not exist.", details={"gameId": str(game_id)}
                )
            # Lock order (audit TASK-0933 P0-3): the state row FOR UPDATE comes
            # first, and only then are the input version and every input
            # parameter (kind, sequence length, trigger roles) read, with plain
            # READ COMMITTED reads and no further lock. A catalog write locks
            # its own games/symbols row and then the state row (bump), so it
            # either committed before this lock (its new values and its new
            # version are both visible here) or it bumps after this commit
            # (old values with the old version, so publication rejects the
            # candidate). Publication also locks the state row first; cleanup
            # bumps it after its own deletes. No transaction holds the state
            # row while waiting for a games or symbols row lock.
            state = lock_super_game_state(session, game_id)
            input_version = int(state.input_version)
            kind_code, expected_layout_count, thresholds = self._read_input_parameters(
                session, game_id
            )
            kind = _kind_parameters(kind_code)
            # A restarted job starts over: unpublished generations are discarded.
            discarded = session.execute(
                delete(SuperGameSeriesGenerationRowModel).where(
                    SuperGameSeriesGenerationRowModel.game_id == game_id
                )
            )
            return DerivationStart(
                game_id=game_id,
                generation_id=uuid4(),
                input_version=input_version,
                expected_layout_count=expected_layout_count,
                kind=kind,
                trigger_thresholds=thresholds,
                discarded_generation_rows=_rowcount(discarded),
            )

    def _read_input_parameters(
        self, session: Session, game_id: UUID
    ) -> tuple[str, int, dict[UUID, int]]:
        """Kind, sequence length and trigger roles; called under the state lock."""

        game = session.execute(
            select(GameModel.super_game_kind, GameModel.expected_layout_count).where(
                GameModel.id == game_id
            )
        ).one()
        thresholds = {
            symbol_id: int(count)
            for symbol_id, count in session.execute(
                select(SymbolModel.id, SymbolModel.super_game_trigger_count).where(
                    SymbolModel.game_id == game_id,
                    SymbolModel.super_game_trigger_count.is_not(None),
                )
            )
        }
        return str(game[0]), int(game[1]), thresholds

    def next_trigger_candidate(
        self, start: DerivationStart, *, after_sequence_number: int
    ) -> int | None:
        if not start.trigger_thresholds:
            return None
        with self._session_factory() as session, session.begin():
            self._router.bind(session, start.game_id, intent=GameStorageIntent.READ)
            found = session.scalar(
                _NEXT_TRIGGER_CANDIDATE_SQL,
                {
                    "game_id": start.game_id,
                    "symbol_ids": list(start.trigger_thresholds),
                    "after_sequence_number": after_sequence_number,
                },
            )
        return None if found is None else int(found)

    def read_trigger_boards(
        self,
        start: DerivationStart,
        *,
        after_sequence_number: int,
        until_sequence_number: int,
    ) -> list[BoardTrigger]:
        if not start.trigger_thresholds:
            return []
        with self._session_factory() as session, session.begin():
            self._router.bind(session, start.game_id, intent=GameStorageIntent.READ)
            counts: dict[tuple[int, UUID], dict[UUID, TriggerCellCount]] = defaultdict(dict)
            for sequence_number, review_item_id, symbol_id, assigned, human in session.execute(
                _TRIGGER_CELL_COUNTS_SQL,
                {
                    "game_id": start.game_id,
                    "symbol_ids": list(start.trigger_thresholds),
                    "after_sequence_number": after_sequence_number,
                    "until_sequence_number": until_sequence_number,
                },
            ):
                counts[(int(sequence_number), review_item_id)][symbol_id] = TriggerCellCount(
                    assigned=int(assigned), human=int(human)
                )
            candidates = {
                key: trigger
                for key, symbol_counts in counts.items()
                if (
                    trigger := evaluate_board_trigger(
                        key[0], symbol_counts, start.trigger_thresholds
                    )
                )
                is not None
            }
            if not candidates:
                return []
            positions = sorted({position for position, _ in candidates})
            boards_by_position: dict[int, list[tuple[bool, UUID, bool]]] = defaultdict(list)
            for sequence_number, review_item_id, canonical, cells, cut_cells in session.execute(
                _POSITION_BOARDS_SQL, {"game_id": start.game_id, "positions": positions}
            ):
                fully_cut = int(cells) == BOARD_CELL_COUNT and int(cut_cells) == BOARD_CELL_COUNT
                boards_by_position[int(sequence_number)].append(
                    (bool(canonical), review_item_id, fully_cut)
                )
        triggers: list[BoardTrigger] = []
        for position in positions:
            boards = boards_by_position.get(position)
            if not boards:
                continue
            # Canonical item first, then the smallest review item id.
            boards.sort(key=lambda board: (not board[0], str(board[1])))
            _, review_item_id, fully_cut = boards[0]
            trigger = candidates.get((position, review_item_id))
            if fully_cut and trigger is not None:
                triggers.append(trigger)
        return triggers

    def last_known_sequence_number(self, start: DerivationStart, *, window: int) -> int | None:
        with self._session_factory() as session, session.begin():
            self._router.bind(session, start.game_id, intent=GameStorageIntent.READ)
            highest = session.scalar(
                _MAX_CELL_SEQUENCE_SQL,
                {"game_id": start.game_id, "ceiling": start.expected_layout_count},
            )
            if highest is None:
                return None
            until = int(highest)
            while until > 0:
                after = max(until - window, 0)
                found = session.scalar(
                    _LAST_CUT_BOARD_IN_WINDOW_SQL,
                    {
                        "game_id": start.game_id,
                        "after_sequence_number": after,
                        "until_sequence_number": until,
                    },
                )
                if found is not None:
                    return int(found)
                until = after
        return None

    def write_generation_rows(
        self, start: DerivationStart, rows: Sequence[DerivedSuperGameSeries]
    ) -> None:
        if not rows:
            return
        with self._session_factory() as session, session.begin():
            self._router.bind(session, start.game_id, intent=GameStorageIntent.WRITE)
            session.execute(
                insert(SuperGameSeriesGenerationRowModel),
                [
                    {
                        "game_id": start.game_id,
                        "generation_id": start.generation_id,
                        "trigger_sequence_number": row.trigger_sequence_number,
                        "start_sequence_number": row.start_sequence_number,
                        "length": row.length,
                        "retrigger_sequence_numbers": list(row.retrigger_sequence_numbers),
                        "completeness": row.completeness.value,
                        "run_verification": row.run_verification.value,
                    }
                    for row in rows
                ],
            )

    def publish_generation(self, start: DerivationStart, *, actor: str) -> PublicationOutcome:
        parameters: dict[str, Any] = {
            "game_id": start.game_id,
            "generation_id": start.generation_id,
            "actor": actor,
        }
        with self._session_factory() as session, session.begin():
            state = lock_super_game_state(session, start.game_id)
            current = int(state.input_version)
            if current != start.input_version:
                session.execute(
                    delete(SuperGameSeriesGenerationRowModel).where(
                        SuperGameSeriesGenerationRowModel.game_id == start.game_id,
                        SuperGameSeriesGenerationRowModel.generation_id == start.generation_id,
                    )
                )
                job_id, _created = enqueue_super_game_series_derive(
                    session, start.game_id, reason="stale_candidate"
                )
                return PublicationOutcome(
                    status=PublicationStatus.REJECTED,
                    input_version=current,
                    rerun_job_id=job_id,
                )
            session.execute(_AUDIT_REMOVED_SERIES_SQL, parameters)
            removed = _rowcount(session.execute(_DELETE_REMOVED_SERIES_SQL, parameters))
            updated = int(session.scalar(_COUNT_CHANGED_SERIES_SQL, parameters) or 0)
            session.execute(_UPDATE_EXISTING_SERIES_SQL, parameters)
            inserted = _rowcount(session.execute(_INSERT_NEW_SERIES_SQL, parameters))
            session.execute(
                delete(SuperGameSeriesGenerationRowModel).where(
                    SuperGameSeriesGenerationRowModel.game_id == start.game_id,
                    SuperGameSeriesGenerationRowModel.generation_id == start.generation_id,
                )
            )
            state.current_generation_id = start.generation_id
            state.input_version_of_generation = start.input_version
            state.updated_at = datetime.now(UTC)
            session.flush()
            return PublicationOutcome(
                status=PublicationStatus.PUBLISHED,
                input_version=current,
                inserted=inserted,
                updated=updated,
                removed=removed,
            )


def published_series_count(session: Session, game_id: UUID) -> int:
    """Number of published series of a game (diagnostics and tests)."""

    GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)
    count = session.scalar(
        select(func.count())
        .select_from(SuperGameSeriesModel)
        .where(SuperGameSeriesModel.game_id == game_id)
    )
    return int(count or 0)


__all__ = [
    "BOARD_CELL_COUNT",
    "SqlAlchemySuperGameSeriesDerivationStore",
    "SqlAlchemySuperGameSeriesRepository",
    "published_series_count",
]
