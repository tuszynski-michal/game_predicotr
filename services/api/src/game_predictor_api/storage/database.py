"""Synchronous SQLAlchemy infrastructure for the local Admin API."""

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import ORMExecuteState, Session, sessionmaker

from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
    current_game_storage_scope,
)

_DATABASE_CONNECT_TIMEOUT_SECONDS = 5


class GameStorageSession(Session):
    """Session that applies the operation's game route before ORM access."""


def _parameter_game_id(parameters: object) -> UUID | None:
    parameter_sets = parameters if isinstance(parameters, list) else [parameters]
    game_ids: set[UUID] = set()
    for parameter_set in parameter_sets:
        if not isinstance(parameter_set, Mapping):
            continue
        for key, value in parameter_set.items():
            if "gameid" not in str(key).replace("_", "").lower():
                continue
            try:
                game_ids.add(value if isinstance(value, UUID) else UUID(str(value)))
            except (TypeError, ValueError):
                continue
    if len(game_ids) > 1:
        raise RuntimeError("One database operation cannot target multiple game stores.")
    return next(iter(game_ids), None)


def _pending_game_id(session: Session) -> UUID | None:
    game_ids = {
        game_id
        for record in (*session.new, *session.dirty, *session.deleted)
        if isinstance((game_id := getattr(record, "game_id", None)), UUID)
    }
    if len(game_ids) > 1:
        raise RuntimeError("One database transaction cannot mutate multiple game stores.")
    return next(iter(game_ids), None)


@event.listens_for(GameStorageSession, "do_orm_execute")
def _route_orm_statement(execute_state: ORMExecuteState) -> None:
    scope = current_game_storage_scope()
    game_id = (
        scope.game_id
        if scope is not None
        else _parameter_game_id(getattr(execute_state, "parameters", None))
    )
    if game_id is None:
        return
    session = execute_state.session
    # SQLAlchemy marks ORM/Core SELECT statements explicitly. Unknown textual
    # statements are treated as writes so raw SQL cannot bypass maintenance.
    intent = (
        GameStorageIntent.READ
        if bool(getattr(execute_state, "is_select", False))
        else GameStorageIntent.WRITE
    )
    GameStorageRouter().bind(
        session,
        game_id,
        intent=intent,
        expected_generation=None if scope is None else scope.expected_generation,
    )


@event.listens_for(GameStorageSession, "before_flush")
def _route_orm_flush(session: Session, *_args: object) -> None:
    scope = current_game_storage_scope()
    if not (session.new or session.dirty or session.deleted):
        return
    game_id = scope.game_id if scope is not None else _pending_game_id(session)
    if game_id is None:
        return
    GameStorageRouter().bind(
        session,
        game_id,
        intent=GameStorageIntent.WRITE,
        expected_generation=None if scope is None else scope.expected_generation,
    )


@event.listens_for(GameStorageSession, "after_transaction_end")
def _clear_finished_game_route(session: Session, transaction: object) -> None:
    if getattr(transaction, "parent", None) is None:
        GameStorageRouter.clear_session_binding(session)


def create_database_engine(settings: ApiSettings, *, echo: bool = False) -> Engine:
    """Create an engine without opening a database connection."""

    return create_engine(
        settings.database_url,
        connect_args={"connect_timeout": _DATABASE_CONNECT_TIMEOUT_SECONDS},
        echo=echo,
        pool_pre_ping=True,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create the transaction boundary used by future repositories."""

    return sessionmaker(bind=engine, class_=GameStorageSession, expire_on_commit=False)
