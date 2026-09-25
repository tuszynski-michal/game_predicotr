"""Transaction-scoped routing and write fencing for game-owned storage."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from enum import StrEnum
from re import compile as compile_pattern
from typing import Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from game_predictor_api.storage.game_data_v2_manifest_v1 import GAME_TABLES, VERSION

_GAME_PATH_PATTERN: Final = compile_pattern(r"(?:^|/)games/([0-9a-fA-F-]{36})(?:/|$)")
_CURRENT_SCOPE: ContextVar[GameStorageScope | None] = ContextVar("game_storage_scope", default=None)


class GameStorageSchema(StrEnum):
    V2 = "game_data_v2"


class GameStorageStatus(StrEnum):
    ACTIVE = "active"
    MIGRATING = "migrating"
    DELETING = "deleting"
    BLOCKED = "blocked"


class GameStorageIntent(StrEnum):
    READ = "read"
    WRITE = "write"


class GameStorageRoutingError(RuntimeError):
    """Stable fail-closed storage-routing failure."""

    def __init__(self, code: str, message: str, *, details: Mapping[str, object]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details)


@dataclass(frozen=True, slots=True)
class GameStorageLocation:
    game_id: UUID
    store_schema: GameStorageSchema
    generation: int
    manifest_version: str
    status: GameStorageStatus
    revision: int

    @property
    def storage_version(self) -> str:
        return self.manifest_version

    @property
    def write_available(self) -> bool:
        return self.status is GameStorageStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class GameStorageScope:
    game_id: UUID
    expected_generation: int | None = None


@contextmanager
def game_storage_scope(
    game_id: UUID, *, expected_generation: int | None = None
) -> Iterator[GameStorageScope]:
    """Bind one game identity to sessions opened by the current operation."""

    scope = GameStorageScope(game_id=game_id, expected_generation=expected_generation)
    token = _CURRENT_SCOPE.set(scope)
    try:
        yield scope
    finally:
        _CURRENT_SCOPE.reset(token)


def current_game_storage_scope() -> GameStorageScope | None:
    return _CURRENT_SCOPE.get()


def game_id_from_path(path: str) -> UUID | None:
    match = _GAME_PATH_PATTERN.search(path)
    if match is None:
        return None
    try:
        return UUID(match.group(1))
    except ValueError:
        return None


class GameStorageRouter:
    """Resolve and pin a game's physical store for one database transaction."""

    _SESSION_KEY = "game_storage_binding_v1"
    _WRITE_LOCK_KEY = "game_storage_write_lock_v1"
    _TRANSACTION_KEY = "game_storage_transaction_v1"

    def describe(self, session: Session, game_id: UUID) -> GameStorageLocation:
        connection = session.connection()
        if connection.dialect.name != "postgresql":
            return self._in_memory_v2(game_id)
        row = (
            connection.exec_driver_sql(
                """
            SELECT store_schema, generation, manifest_version, status, revision
            FROM public.game_storage_locations
            WHERE game_id = %s
            """,
                (game_id,),
            )
            .mappings()
            .one_or_none()
        )
        return self._from_row(game_id, row)

    def describe_many(
        self, session: Session, game_ids: tuple[UUID, ...]
    ) -> dict[UUID, GameStorageLocation]:
        if not game_ids:
            return {}
        connection = session.connection()
        if connection.dialect.name != "postgresql":
            return {game_id: self._in_memory_v2(game_id) for game_id in game_ids}
        rows = connection.execute(
            text(
                """
                SELECT game_id, store_schema, generation, manifest_version, status, revision
                FROM public.game_storage_locations
                WHERE game_id = ANY(CAST(:game_ids AS uuid[]))
                """
            ),
            {"game_ids": [str(game_id) for game_id in game_ids]},
        ).mappings()
        found = {UUID(str(row["game_id"])): row for row in rows}
        return {game_id: self._from_row(game_id, found.get(game_id)) for game_id in game_ids}

    def bind(
        self,
        session: Session,
        game_id: UUID,
        *,
        intent: GameStorageIntent,
        expected_generation: int | None = None,
    ) -> GameStorageLocation:
        transaction = session.get_transaction()
        if transaction is None:
            session.connection()
            transaction = session.get_transaction()
        if session.info.get(self._TRANSACTION_KEY) is not transaction:
            self.clear_session_binding(session)
            session.info[self._TRANSACTION_KEY] = transaction

        existing = session.info.get(self._SESSION_KEY)
        if existing is not None:
            if not isinstance(existing, GameStorageLocation):
                raise RuntimeError("Invalid game storage session binding.")
            self._require_same_binding(existing, game_id, expected_generation)
            if intent is GameStorageIntent.WRITE and not session.info.get(self._WRITE_LOCK_KEY):
                self._acquire_write_fence(session, game_id)
                current = self._resolve(session, game_id, lock_for_write=True)
                self._require_same_binding(current, game_id, existing.generation)
                self._require_writable(current)
                session.info[self._WRITE_LOCK_KEY] = True
            return existing

        if intent is GameStorageIntent.WRITE:
            self._acquire_write_fence(session, game_id)
        location = self._resolve(session, game_id, lock_for_write=intent is GameStorageIntent.WRITE)
        if expected_generation is not None and location.generation != expected_generation:
            raise self._stale(location, expected_generation)
        if intent is GameStorageIntent.WRITE:
            self._require_writable(location)
            session.info[self._WRITE_LOCK_KEY] = True
        self._set_transaction_scope(session, location)
        session.info[self._SESSION_KEY] = location
        return location

    @classmethod
    def clear_session_binding(cls, session: Session) -> None:
        """Forget transaction-local routing state after commit or rollback."""

        session.info.pop(cls._SESSION_KEY, None)
        session.info.pop(cls._WRITE_LOCK_KEY, None)
        session.info.pop(cls._TRANSACTION_KEY, None)

    def qualified_game_table(self, location: GameStorageLocation, table_name: str) -> str:
        """Return a safe qualified name for raw SQL over a game-owned table."""

        if table_name not in GAME_TABLES:
            raise GameStorageRoutingError(
                "GAME_STORAGE_TABLE_NOT_OWNED",
                "The requested table is not owned by one game.",
                details={"tableName": table_name},
            )
        return f'"{location.store_schema.value}"."{table_name}"'

    def _resolve(
        self, session: Session, game_id: UUID, *, lock_for_write: bool
    ) -> GameStorageLocation:
        connection = session.connection()
        if connection.dialect.name != "postgresql":
            return self._in_memory_v2(game_id)
        # A write keeps a shared row lock until commit. Cutover changes the
        # registry row and therefore requires an incompatible exclusive lock.
        lock = " FOR SHARE" if lock_for_write else ""
        row = (
            connection.exec_driver_sql(
                """
            SELECT store_schema, generation, manifest_version, status, revision
            FROM public.game_storage_locations
            WHERE game_id = %s
            """
                + lock,
                (game_id,),
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            exists = connection.exec_driver_sql(
                "SELECT id FROM public.games WHERE id = %s FOR KEY SHARE", (game_id,)
            ).one_or_none()
            if exists is None:
                raise GameStorageRoutingError(
                    "GAME_NOT_FOUND",
                    "Game does not exist.",
                    details={"gameId": str(game_id)},
                )
            raise GameStorageRoutingError(
                "GAME_STORAGE_LOCATION_MISSING",
                "The game does not have a provisioned storage location.",
                details={"gameId": str(game_id)},
            )
        return self._from_row(game_id, row)

    @staticmethod
    def _acquire_write_fence(session: Session, game_id: UUID) -> None:
        connection = session.connection()
        if connection.dialect.name != "postgresql":
            return
        # Coordinates writes with a registry location change. A cutover must
        # take pg_advisory_xact_lock with the same derived key.
        connection.exec_driver_sql(
            "SELECT pg_advisory_xact_lock_shared(hashtextextended(%s, 519))",
            (str(game_id),),
        )

    @staticmethod
    def _from_row(
        game_id: UUID, row: RowMapping | Mapping[str, object] | None
    ) -> GameStorageLocation:
        if row is None:
            return GameStorageRouter._unavailable(game_id)
        try:
            schema = GameStorageSchema(str(row["store_schema"]))
            status = GameStorageStatus(str(row["status"]))
            generation = int(str(row["generation"]))
            revision = int(str(row["revision"]))
            manifest_version = str(row["manifest_version"])
        except (KeyError, TypeError, ValueError) as error:
            raise GameStorageRoutingError(
                "GAME_STORAGE_LOCATION_INVALID",
                "The game storage registry row is invalid.",
                details={"gameId": str(game_id)},
            ) from error
        if generation < 2 or revision < 0 or manifest_version != VERSION:
            raise GameStorageRoutingError(
                "GAME_STORAGE_LOCATION_INVALID",
                "The game storage registry row is invalid.",
                details={
                    "gameId": str(game_id),
                    "generation": generation,
                    "manifestVersion": manifest_version,
                    "revision": revision,
                },
            )
        return GameStorageLocation(
            game_id=game_id,
            store_schema=schema,
            generation=generation,
            manifest_version=manifest_version,
            status=status,
            revision=revision,
        )

    @staticmethod
    def _in_memory_v2(game_id: UUID) -> GameStorageLocation:
        """V2-shaped adapter for non-PostgreSQL unit tests only.

        It deliberately does not model a physical schema switch or a legacy
        public store. PostgreSQL always resolves the durable registry row.
        """

        return GameStorageLocation(
            game_id=game_id,
            store_schema=GameStorageSchema.V2,
            generation=2,
            manifest_version=VERSION,
            status=GameStorageStatus.ACTIVE,
            revision=0,
        )

    @staticmethod
    def _unavailable(game_id: UUID) -> GameStorageLocation:
        """Catalog projection for a corrupt/missing greenfield registry row."""

        return GameStorageLocation(
            game_id=game_id,
            store_schema=GameStorageSchema.V2,
            generation=2,
            manifest_version=VERSION,
            status=GameStorageStatus.BLOCKED,
            revision=0,
        )

    @staticmethod
    def _require_same_binding(
        location: GameStorageLocation,
        game_id: UUID,
        expected_generation: int | None,
    ) -> None:
        if location.game_id != game_id:
            raise GameStorageRoutingError(
                "GAME_STORAGE_SESSION_SCOPE_CONFLICT",
                "One database transaction cannot access two game stores.",
                details={
                    "boundGameId": str(location.game_id),
                    "requestedGameId": str(game_id),
                },
            )
        if expected_generation is not None and location.generation != expected_generation:
            raise GameStorageRouter._stale(location, expected_generation)

    @staticmethod
    def _require_writable(location: GameStorageLocation) -> None:
        if not location.write_available:
            raise GameStorageRoutingError(
                "GAME_STORAGE_WRITE_UNAVAILABLE",
                "Game data is temporarily read-only during storage maintenance.",
                details={
                    "gameId": str(location.game_id),
                    "generation": location.generation,
                    "storageStatus": location.status.value,
                },
            )

    @staticmethod
    def _stale(location: GameStorageLocation, expected_generation: int) -> GameStorageRoutingError:
        return GameStorageRoutingError(
            "GAME_STORAGE_GENERATION_STALE",
            "The requested game storage generation is no longer active.",
            details={
                "gameId": str(location.game_id),
                "expectedGeneration": expected_generation,
                "currentGeneration": location.generation,
            },
        )

    @staticmethod
    def _set_transaction_scope(session: Session, location: GameStorageLocation) -> None:
        connection = session.connection()
        if connection.dialect.name != "postgresql":
            return
        search_path = "game_data_v2, public, pg_catalog"
        connection.exec_driver_sql("SELECT set_config('search_path', %s, true)", (search_path,))
        connection.exec_driver_sql(
            "SELECT set_config('game_predictor.game_id', %s, true)",
            (str(location.game_id),),
        )
        connection.exec_driver_sql(
            "SELECT set_config('game_predictor.storage_generation', %s, true)",
            (str(location.generation),),
        )


__all__ = [
    "GameStorageIntent",
    "GameStorageLocation",
    "GameStorageRouter",
    "GameStorageRoutingError",
    "GameStorageSchema",
    "GameStorageScope",
    "GameStorageStatus",
    "current_game_storage_scope",
    "game_id_from_path",
    "game_storage_scope",
]
