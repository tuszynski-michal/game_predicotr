"""Per-game input version of the super game series derivation (TASK-0933, D-535).

The input of the derivation is the set of cut boards' cells with an assigned
symbol (human decision or model prediction), the symbol roles, the game's
super game kind and the active rules.  Every write that changes this set
increments ``super_game_derivation_state.input_version`` **in the same
transaction** as the write, by calling :func:`record_super_game_input_change`.
A maximum of row revisions or ``updated_at`` cannot replace the counter: it
misses deletions and a change of a low-revision row next to a higher one.

:data:`SUPER_GAME_INPUT_WRITE_POINTS` enumerates every such write point; a
parametric test checks that each listed function calls the helper.  A new
write path that changes the input must be added to the list.

After the bump the helper enqueues one derive job per game (lane
``general``); a queued job that already exists is reused, so there is never
more than one queued derive job of a game.  Games without a super game kind
only get the bump (their state is always fresh), except when the kind itself
changes, so that series of a former kind are cleared.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, cast
from uuid import UUID, uuid4

from sqlalchemy import Table, select, text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import Executable

from game_predictor_api.domain.jobs import JobStatus, JobType, create_job
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
)
from game_predictor_api.storage.models import GameModel, JobModel
from game_predictor_api.storage.super_game_series_models import SuperGameDerivationStateModel

NO_SUPER_GAME_KIND_CODE: Final = "none"
_TRANSACTION_MARKER: Final = "super_game_input_version_marker_v1"


@dataclass(frozen=True, slots=True)
class SuperGameInputWritePoint:
    """One write path that changes the derivation input."""

    source: str
    module: str
    qualname: str
    covers: str


# Order: cell writes (one shared choke point), then the paths that bypass it,
# then catalog and rules.  ``module`` is relative to ``game_predictor_api``.
#
# Deliberately not listed: ``ImageGeometryCompletenessStateRepository
# .apply_board_repoint`` only re-points cells to a newer source geometry
# revision id of the same geometry; it changes neither assigned symbols nor
# whether a board is fully cut, so the derivation input is unchanged (lead
# decision after the TASK-0933 audit).
SUPER_GAME_INPUT_WRITE_POINTS: Final[tuple[SuperGameInputWritePoint, ...]] = (
    SuperGameInputWritePoint(
        source="symbol_cells",
        module="storage.image_symbol_review_repository",
        qualname="SymbolCellReviewWriteThroughCoordinator._touch_catalog_revision",
        covers=(
            "every cell write-through: prediction write and refresh (import recognition, "
            "pending re-inference, reference library apply and revert), human symbol "
            "correction (single cell, bulk, unreadable board, share and management "
            "correction, grid-correction symbols, board decision and reopen), grid "
            "correction (virtual board/source geometry revisions, legacy conversion, "
            "geometry admission and pending resolution), import board materialisation "
            "and backfill reconciliation"
        ),
    ),
    SuperGameInputWritePoint(
        source="symbol_cell_backfill",
        module="storage.image_symbol_review_repository",
        qualname="SqlAlchemyImageSymbolReviewRepository.finalize_backfill",
        covers="backfill finalisation after raw batch inserts of cells",
    ),
    SuperGameInputWritePoint(
        source="board_source_cleanup",
        module="storage.cleanup_repository",
        qualname="SqlAlchemyCleanupRepository._delete_board_source_graph",
        covers="deletion of boards, cells and prediction revisions (prediction delete)",
    ),
    SuperGameInputWritePoint(
        source="geometry_correction_revert",
        module="storage.geometry_correction_revert_repository",
        qualname="SqlAlchemyGeometryCorrectionRevertRepository._revert_pending_slot",
        covers=(
            "revert of a deferred-slot correction (TASK-0945): deletion of the board, "
            "its cells and their events"
        ),
    ),
    SuperGameInputWritePoint(
        source="game_layout_reset",
        module="storage.cleanup_repository",
        qualname="SqlAlchemyCleanupRepository.reset_game",
        covers="reset of a game's boards and symbols",
    ),
    SuperGameInputWritePoint(
        source="symbol_role",
        module="storage.catalog_repository",
        qualname="SqlAlchemyCatalogRepository.save_symbol",
        covers="change of is_wildcard or super_game_trigger_count",
    ),
    SuperGameInputWritePoint(
        source="symbol_role",
        module="storage.catalog_repository",
        qualname="SqlAlchemyCatalogRepository.add_symbol",
        covers="new symbol created with a trigger role",
    ),
    SuperGameInputWritePoint(
        source="symbol_role",
        module="storage.catalog_repository",
        qualname="SqlAlchemyCatalogRepository.add_manual_symbol",
        covers="new manual symbol created with a trigger role",
    ),
    SuperGameInputWritePoint(
        source="super_game_kind",
        module="storage.catalog_repository",
        qualname="SqlAlchemyCatalogRepository.save_game",
        covers="change of games.super_game_kind",
    ),
    SuperGameInputWritePoint(
        source="expected_layout_count",
        module="storage.catalog_repository",
        qualname="SqlAlchemyCatalogRepository.save_game",
        covers="change of games.expected_layout_count (the derivation walks 1..N)",
    ),
    SuperGameInputWritePoint(
        source="rules_publication",
        module="storage.rules_repository",
        qualname="SqlAlchemyRulesRepository.save_rules_version",
        covers="publication (or archival) of a rules version",
    ),
)

SUPER_GAME_INPUT_SOURCES: Final = frozenset(point.source for point in SUPER_GAME_INPUT_WRITE_POINTS)


@dataclass(slots=True)
class _Marker:
    transaction: object
    game_ids: set[UUID]


def _first_bump_in_transaction(session: Session, game_id: UUID) -> bool:
    transaction = session.get_transaction()
    if transaction is None:
        raise RuntimeError("A super game input change must be recorded inside a transaction.")
    marker = session.info.get(_TRANSACTION_MARKER)
    if not isinstance(marker, _Marker) or marker.transaction is not transaction:
        marker = _Marker(transaction=transaction, game_ids=set())
        session.info[_TRANSACTION_MARKER] = marker
    if game_id in marker.game_ids:
        return False
    marker.game_ids.add(game_id)
    return True


def _storage_writable(session: Session, game_id: UUID) -> bool:
    return GameStorageRouter().describe(session, game_id).write_available


def _upsert_state_row(session: Session, game_id: UUID, *, increment: int) -> None:
    table = cast(Table, SuperGameDerivationStateModel.__table__)
    values = {"game_id": game_id, "input_version": increment}
    conflict = [table.c.game_id]
    update_set = {
        "input_version": table.c.input_version + increment,
        "updated_at": text("CURRENT_TIMESTAMP"),
    }
    statement: Executable
    if session.connection().dialect.name == "postgresql":
        postgresql = postgresql_insert(table).values(**values)
        statement = (
            postgresql.on_conflict_do_update(index_elements=conflict, set_=update_set)
            if increment
            else postgresql.on_conflict_do_nothing(index_elements=conflict)
        )
    else:  # SQLite unit-test schemas built from metadata
        sqlite = sqlite_insert(table).values(**values)
        statement = (
            sqlite.on_conflict_do_update(index_elements=conflict, set_=update_set)
            if increment
            else sqlite.on_conflict_do_nothing(index_elements=conflict)
        )
    session.execute(statement)


def lock_super_game_state(session: Session, game_id: UUID) -> SuperGameDerivationStateModel:
    """Create the state row if missing and lock it ``FOR UPDATE`` until commit."""

    GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)
    _upsert_state_row(session, game_id, increment=0)
    state = session.scalar(
        select(SuperGameDerivationStateModel)
        .where(SuperGameDerivationStateModel.game_id == game_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if state is None:  # pragma: no cover - the upsert above guarantees the row
        raise RuntimeError("Super game derivation state row disappeared.")
    return state


def enqueue_super_game_series_derive(
    session: Session, game_id: UUID, *, reason: str
) -> tuple[UUID, bool]:
    """Return ``(job_id, created)``; reuse the game's queued derive job if one exists.

    The caller holds (or this call takes) the state row lock, which serialises
    concurrent enqueues of the same game, so at most one job is queued.
    """

    from game_predictor_api.storage.job_repository import job_record_from_domain

    lock_super_game_state(session, game_id)
    existing = session.scalar(
        select(JobModel.id)
        .where(
            JobModel.game_id == game_id,
            JobModel.job_type == JobType.SUPER_GAME_SERIES_DERIVE,
            JobModel.status == JobStatus.CREATED,
        )
        .order_by(JobModel.created_at, JobModel.id)
        .limit(1)
    )
    if existing is not None:
        return existing, False
    job = create_job(
        JobType.SUPER_GAME_SERIES_DERIVE,
        game_id=game_id,
        # request_id keeps the global input_key unique for every new run.
        input_payload={"schema_version": 1, "reason": reason, "request_id": str(uuid4())},
    )
    session.add(job_record_from_domain(job))
    session.flush()
    return job.id, True


def record_super_game_input_change(session: Session, game_id: UUID, *, source: str) -> bool:
    """Increment the game's input version in the caller's transaction.

    Returns ``False`` when the change was already recorded in this
    transaction or the game's store is not writable (a game still being
    provisioned has no derivation input yet).
    """

    if source not in SUPER_GAME_INPUT_SOURCES:
        raise ValueError(f"SUPER_GAME_INPUT_SOURCE_UNKNOWN: {source}")
    if not _first_bump_in_transaction(session, game_id):
        return False
    if not _storage_writable(session, game_id):
        return False
    GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)
    _upsert_state_row(session, game_id, increment=1)
    kind = session.scalar(select(GameModel.super_game_kind).where(GameModel.id == game_id))
    if kind is not None and (kind != NO_SUPER_GAME_KIND_CODE or source == "super_game_kind"):
        enqueue_super_game_series_derive(session, game_id, reason=source)
    return True


__all__ = [
    "SUPER_GAME_INPUT_SOURCES",
    "SUPER_GAME_INPUT_WRITE_POINTS",
    "SuperGameInputWritePoint",
    "enqueue_super_game_series_derive",
    "lock_super_game_state",
    "record_super_game_input_change",
]
