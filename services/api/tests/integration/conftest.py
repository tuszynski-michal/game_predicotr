"""Application-role mode for the PostgreSQL integration suites (TASK-0795).

``GAME_PREDICTOR_PG_TEST_ROLE=application`` (together with
``GAME_PREDICTOR_RUN_POSTGRES_TESTS=1``) runs every application session — a
``GameStorageSession``, which is what API and worker use at runtime — as a
test-scoped role without SUPERUSER/BYPASSRLS, so the forced ``game_data_v2``
row-level security applies exactly as for the production application role.

Fixture code keeps the schema owner: Alembic, ``CREATE DATABASE``, partition
provisioning through plain ``Session``/``engine.begin()`` seeding and the
owner sessions of ``create_owner_session_factory`` (which the mode also
injects into directly built catalog repositories, as ``create_app`` does
for partition DDL). The role is
``NOLOGIN`` (reachable only by ``SET LOCAL ROLE`` from the owner connection),
is granted privileges only inside the disposable fixture databases and is
dropped at the end of the pytest session. The operator database is never touched.
"""

from __future__ import annotations

import os
import re
import warnings
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from uuid import uuid4

import pytest
from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.catalog_repository import SqlAlchemyCatalogRepository
from game_predictor_api.storage.database import (
    OWNER_SESSION_INFO_KEY,
    GameStorageSession,
    create_owner_session_factory,
)
from game_predictor_api.storage.database_roles import (
    ApplicationRoleSpec,
    provision_application_role,
)
from game_predictor_api.storage.game_storage_routing import GameStorageRouter
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL, Connection, Engine, make_url
from sqlalchemy.orm import Session, SessionTransaction
from sqlalchemy.pool import NullPool

APPLICATION_ROLE_MODE_VARIABLE = "GAME_PREDICTOR_PG_TEST_ROLE"
_TEST_ROLE_PATTERN = re.compile(r"^game_predictor_app_test_[0-9a-f]{12}$")
# Disposable databases of the integration fixtures: ``*_test`` and the older
# ``game_predictor_task<NNNN>_<hex>`` names. The operator database
# ``game_predictor`` never matches.
_TEST_DATABASE_PATTERN = re.compile(r"^(?:[a-z0-9_]+_test|game_predictor_task[0-9]+_[a-z0-9_]+)$")


def application_role_mode_enabled() -> bool:
    return (
        os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") == "1"
        and os.environ.get(APPLICATION_ROLE_MODE_VARIABLE) == "application"
    )


@dataclass
class _ApplicationRoleMode:
    role: str
    owner_url: URL
    # (database name, engine identity): fixtures recreate databases under the
    # same name with a new engine, and a recreated database needs its grants
    # again. A wrong cache hit fails loudly with "permission denied".
    provisioned: set[tuple[str, int]] = field(default_factory=set)
    sessions: int = 0

    def after_begin(
        self, session: Session, _transaction: SessionTransaction, connection: Connection
    ) -> None:
        if session.info.get(OWNER_SESSION_INFO_KEY):
            return
        database = connection.engine.url.database
        if (
            # Engines that already log in as another role (the isolation
            # test's LOGIN application role) keep their own identity.
            connection.engine.url.username != self.owner_url.username
            or database is None
            or database == self.owner_url.database
            or _TEST_DATABASE_PATTERN.fullmatch(database) is None
        ):
            return
        key = (database, id(connection.engine))
        if key not in self.provisioned:
            self._provision(connection.engine.url)
            self.provisioned.add(key)
        # SET takes no snapshot, so a following SET TRANSACTION ISOLATION
        # LEVEL in the application code remains valid.
        connection.exec_driver_sql(f'SET LOCAL ROLE "{self.role}"')
        self.sessions += 1

    def _provision(self, url: URL) -> None:
        engine = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 5})
        try:
            with engine.begin() as connection:
                provision_application_role(
                    connection,
                    ApplicationRoleSpec(role_name=self.role, password=None, login=False),
                )
        finally:
            engine.dispose()

    def drop(self) -> None:
        maintenance = create_engine(
            self.owner_url.set(database="postgres"),
            isolation_level="AUTOCOMMIT",
            poolclass=NullPool,
            connect_args={"connect_timeout": 5},
        )
        try:
            with maintenance.connect() as connection:
                remaining = [
                    str(name)
                    for (name,) in connection.execute(
                        text("SELECT datname FROM pg_database WHERE datname = ANY(:names)"),
                        {"names": sorted({name for name, _oid in self.provisioned})},
                    )
                ]
            for database in remaining:
                # A leftover test database (failed fixture cleanup) still holds
                # grants; revoke them there so the cluster role can be dropped.
                if _TEST_DATABASE_PATTERN.fullmatch(database) is None:
                    continue
                leftover = create_engine(
                    self.owner_url.set(database=database),
                    isolation_level="AUTOCOMMIT",
                    poolclass=NullPool,
                    connect_args={"connect_timeout": 5},
                )
                try:
                    with leftover.connect() as connection:
                        connection.exec_driver_sql(f'DROP OWNED BY "{self.role}"')
                finally:
                    leftover.dispose()
                warnings.warn(
                    f"Test database {database} was left behind by its fixture.",
                    stacklevel=1,
                )
            with maintenance.connect() as connection:
                connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{self.role}"')
        finally:
            maintenance.dispose()


def _inject_owner_partition_ddl(patches: pytest.MonkeyPatch) -> None:
    """Give catalog repositories the owner DDL sessions that ``create_app`` wires.

    Fixtures construct ``SqlAlchemyCatalogRepository(session)`` directly; in
    production the API always passes ``partition_ddl_session_factory`` built
    from the owner URL. Test engines connect as the owner, so an owner
    session factory over the same engine reproduces that wiring.
    """

    original = SqlAlchemyCatalogRepository.__init__

    def init(
        self: SqlAlchemyCatalogRepository,
        session: Session,
        storage_router: GameStorageRouter | None = None,
        *,
        partition_ddl_session_factory: Callable[[], Session] | None = None,
    ) -> None:
        if partition_ddl_session_factory is None and isinstance(session, GameStorageSession):
            bind = session.get_bind()
            if isinstance(bind, Engine):
                partition_ddl_session_factory = create_owner_session_factory(bind)
        original(
            self,
            session,
            storage_router,
            partition_ddl_session_factory=partition_ddl_session_factory,
        )

    patches.setattr(SqlAlchemyCatalogRepository, "__init__", init)


@pytest.fixture(scope="session", autouse=True)
def application_role_mode() -> Iterator[_ApplicationRoleMode | None]:
    if not application_role_mode_enabled():
        yield None
        return
    owner_url = make_url(ApiSettings.from_environment().owner_database_url)
    role = f"game_predictor_app_test_{uuid4().hex[:12]}"
    assert _TEST_ROLE_PATTERN.fullmatch(role)
    maintenance = create_engine(
        owner_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        connect_args={"connect_timeout": 5},
    )
    try:
        with maintenance.connect() as connection:
            connection.exec_driver_sql(
                f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB '
                "NOCREATEROLE NOREPLICATION NOINHERIT"
            )
    finally:
        maintenance.dispose()
    mode = _ApplicationRoleMode(role=role, owner_url=owner_url)
    event.listen(GameStorageSession, "after_begin", mode.after_begin)
    patches = pytest.MonkeyPatch()
    _inject_owner_partition_ddl(patches)
    try:
        yield mode
    finally:
        patches.undo()
        event.remove(GameStorageSession, "after_begin", mode.after_begin)
        mode.drop()
        print(
            f"\n[application-role mode] role {role}: {mode.sessions} application "
            f"transactions in {len(mode.provisioned)} test database(s); role dropped."
        )
