"""Find the game that owns a game-table row identified only by a global id.

TASK-0797: some routes (Reviewer unlock, revoke, work-assignment heartbeats,
dataset versions, selection runs, …) carry only a row id, while every game
table lives in ``game_data_v2`` behind forced row-level security. The
application role can read a game's rows only after binding that game, so the
owner is found by asking each registered game in its own short READ-bound
transaction (the game count is small). No privileged function and no copy of
the mapping outside the game store is needed; RLS stays the only gate.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from game_predictor_api.storage.database import assign_session_game, session_game
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageLocation,
    GameStorageRouter,
    GameStorageRoutingError,
    current_game_storage_scope,
    game_storage_scope,
)

_COLUMN: Final = re.compile(r"^[a-z_][a-z0-9_]*$")


class GameEntityLocator:
    """Locate a row's game through per-game RLS-bound reads."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def registered_games(self) -> tuple[UUID, ...]:
        with self._session_factory() as session:
            rows = session.execute(
                text("SELECT game_id FROM public.game_storage_locations ORDER BY game_id")
            ).all()
            session.rollback()
        return tuple(row[0] if isinstance(row[0], UUID) else UUID(str(row[0])) for row in rows)

    def locate(self, table: str, column: str, value: object) -> UUID | None:
        """Return the only game whose ``table.column`` equals ``value``, else ``None``."""

        if _COLUMN.fullmatch(column) is None:
            raise ValueError("Invalid locator column.")
        router = GameStorageRouter()
        found: list[UUID] = []
        for game_id in self.registered_games():
            with self._bound(game_id) as bound:
                if bound is None:
                    continue
                session, location = bound
                qualified = router.qualified_game_table(location, table)
                row = session.execute(
                    text(
                        f"SELECT 1 FROM {qualified} "
                        f'WHERE game_id = :game_id AND "{column}" = :value LIMIT 1'
                    ),
                    {"game_id": game_id, "value": value},
                ).first()
                if row is not None:
                    found.append(game_id)
        # A global id (UUID, token hash) never repeats across games; two
        # owners would be corrupt data and must not pick one silently.
        if len(found) > 1:
            raise GameStorageRoutingError(
                "GAME_SCOPED_RESOURCE_AMBIGUOUS",
                "The requested resource is owned by more than one game.",
                details={"table": table},
            )
        return found[0] if found else None

    @contextmanager
    def _bound(self, game_id: UUID) -> Iterator[tuple[Session, GameStorageLocation] | None]:
        # Its own scope: an outer request scope must not rebind this read.
        with game_storage_scope(game_id), self._session_factory() as session:
            try:
                location = GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)
            except GameStorageRoutingError:
                # A game without a usable location has no readable rows.
                session.rollback()
                yield None
                return
            try:
                yield session, location
            finally:
                session.rollback()


def session_is_scoped(session: Session) -> bool:
    """True when ``session`` already reads one game (bound, assigned or scoped)."""

    return (
        current_game_storage_scope() is not None
        or session_game(session) is not None
        or GameStorageRouter.bound_game_id(session) is not None
    )


def assign_game_if_unscoped(session: Session, game_id: UUID) -> None:
    """Route an unscoped session to the game a repository method was given."""

    if not session_is_scoped(session):
        assign_session_game(session, game_id)


def bind_located_game(
    session: Session,
    locator: GameEntityLocator | None,
    table: str,
    column: str,
    value: object,
) -> bool:
    """Bind ``session`` to the game owning the row; ``False`` when no game owns it.

    A session that is already scoped keeps its game: a row of another game is
    then simply invisible (RLS), which callers report as "not found".
    """

    if locator is None or session_is_scoped(session):
        return True
    game_id = locator.locate(table, column, value)
    if game_id is None:
        return False
    assign_session_game(session, game_id)
    return True


__all__ = [
    "GameEntityLocator",
    "assign_game_if_unscoped",
    "bind_located_game",
    "session_is_scoped",
]
