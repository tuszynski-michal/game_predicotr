"""Synchronous SQLAlchemy infrastructure for the local Admin API."""

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.orm import ORMExecuteState, Session, sessionmaker
from sqlalchemy.pool import NullPool

from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
    current_game_storage_scope,
)

_DATABASE_CONNECT_TIMEOUT_SECONDS = 5
# Marks sessions opened by ``create_owner_session_factory``.
OWNER_SESSION_INFO_KEY = "game_predictor_owner_session_v1"
# TASK-0797: game of a session whose request named only a game-owned row id.
SESSION_GAME_INFO_KEY = "game_storage_session_game_v1"
# Marks sessions of ``create_cross_game_owner_session_factory``.
CROSS_GAME_SESSION_INFO_KEY = "game_storage_cross_game_owner_v1"


def assign_session_game(session: Session, game_id: UUID) -> None:
    """Route every later transaction of ``session`` to ``game_id``.

    Used when a request names only a row id and the owning game was located
    (``GameEntityLocator``). A request-wide ``game_storage_scope`` still wins.
    """

    session.info[SESSION_GAME_INFO_KEY] = game_id


def session_game(session: Session) -> UUID | None:
    value = session.info.get(SESSION_GAME_INFO_KEY)
    return value if isinstance(value, UUID) else None


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


def _is_cross_game(session: Session) -> bool:
    return bool(session.info.get(CROSS_GAME_SESSION_INFO_KEY))


def _bind(
    session: Session,
    game_id: UUID,
    *,
    intent: GameStorageIntent,
    expected_generation: int | None,
) -> None:
    if _is_cross_game(session):
        # A cross-game owner transaction (CrossGameOwnerSession) moves its
        # route to the game it touches next: the write fence of each touched
        # game is taken and the column default ``game_id`` follows the game.
        bound = GameStorageRouter.bound_game_id(session)
        if bound is not None and bound != game_id:
            GameStorageRouter.clear_session_binding(session)
    GameStorageRouter().bind(
        session,
        game_id,
        intent=intent,
        expected_generation=expected_generation,
    )


@event.listens_for(GameStorageSession, "do_orm_execute")
def _route_orm_statement(execute_state: ORMExecuteState) -> None:
    scope = current_game_storage_scope()
    session = execute_state.session
    if scope is not None:
        game_id: UUID | None = scope.game_id
    else:
        try:
            game_id = session_game(session) or _parameter_game_id(
                getattr(execute_state, "parameters", None)
            )
        except RuntimeError:
            # Several games in one statement: only a cross-game owner session
            # (RLS bypass, explicit predicates) may run it unrouted.
            if not _is_cross_game(session):
                raise
            return
    if game_id is None:
        return
    # SQLAlchemy marks ORM/Core SELECT statements explicitly. Unknown textual
    # statements are treated as writes so raw SQL cannot bypass maintenance.
    intent = (
        GameStorageIntent.READ
        if bool(getattr(execute_state, "is_select", False))
        else GameStorageIntent.WRITE
    )
    _bind(
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
    if scope is not None:
        game_id: UUID | None = scope.game_id
    else:
        try:
            game_id = session_game(session) or _pending_game_id(session)
        except RuntimeError:
            # A mobile release writes rows of several games in one flush; the
            # cross-game owner session stores their explicit game_id values.
            if not _is_cross_game(session):
                raise
            return
    if game_id is None:
        return
    _bind(
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
    """Create the runtime (application role) engine without connecting.

    TASK-0795: this role has no SUPERUSER/BYPASSRLS, so every game table read
    or write must bind its game first (``GameStorageRouter``). An unbound
    statement fails: unqualified game tables are not on the search_path and
    qualified ``game_data_v2`` tables raise ``GAME_STORAGE_SCOPE_REQUIRED``.
    """

    return create_engine(
        settings.database_url,
        connect_args={"connect_timeout": _DATABASE_CONNECT_TIMEOUT_SECONDS},
        echo=echo,
        pool_pre_ping=True,
    )


def create_owner_database_engine(settings: ApiSettings, *, echo: bool = False) -> Engine:
    """Create the schema-owner engine for the explicit DDL/maintenance paths.

    Only partition lifecycle steps and planner/space maintenance (``ANALYZE``,
    ``VACUUM``) use it at runtime; data-plane reads and writes never do.
    Without a pool no owner connection outlives its short maintenance step.
    """

    return create_engine(
        settings.owner_database_url,
        connect_args={"connect_timeout": _DATABASE_CONNECT_TIMEOUT_SECONDS},
        echo=echo,
        poolclass=NullPool,
    )


def create_maintenance_database_engine(settings: ApiSettings, *, echo: bool = False) -> Engine:
    """Create a pooled schema-owner engine for operator maintenance scripts.

    TASK-0795: scripts (rebuilds, conversions, slimming, exports, audits) keep
    running as the schema owner, exactly as before the application role. They
    are operator tools on the loopback machine, not request-serving runtime.
    """

    return create_engine(
        settings.owner_database_url,
        connect_args={"connect_timeout": _DATABASE_CONNECT_TIMEOUT_SECONDS},
        echo=echo,
        pool_pre_ping=True,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create the transaction boundary used by future repositories."""

    return sessionmaker(bind=engine, class_=GameStorageSession, expire_on_commit=False)


class CrossGameOwnerSession(GameStorageSession):
    """Schema-owner session for the few aggregates that span games (TASK-0797).

    A mobile release (and its snapshot, payout readiness, build workflow and
    cleanup) references dataset and rules versions of several games in one
    transaction, which a game-bound application-role transaction cannot do by
    design (one game per transaction, RLS). These operator-initiated release
    paths therefore run on the owner URL with ``game_data_v2`` on the
    search_path. The local owner is a superuser, so RLS does not filter it;
    every query keeps its explicit game or release predicate. Routing still
    applies per statement (write fence, ``game_id`` column defaults) and moves
    from game to game instead of refusing a second game.
    """


@event.listens_for(CrossGameOwnerSession, "after_begin")
def _cross_game_search_path(
    _session: Session, _transaction: object, connection: Connection
) -> None:
    if connection.dialect.name == "postgresql":
        connection.exec_driver_sql(
            "SELECT set_config('search_path', 'game_data_v2, public, pg_catalog', true)"
        )


def create_cross_game_owner_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Sessions for release aggregates over the schema-owner ``engine``."""

    return sessionmaker(
        bind=engine,
        class_=CrossGameOwnerSession,
        expire_on_commit=False,
        info={OWNER_SESSION_INFO_KEY: True, CROSS_GAME_SESSION_INFO_KEY: True},
    )


def create_owner_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Plain sessions for owner-only control-plane steps (no data-plane routing)."""

    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
        info={OWNER_SESSION_INFO_KEY: True},
    )
