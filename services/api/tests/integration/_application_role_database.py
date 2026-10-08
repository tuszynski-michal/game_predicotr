"""Disposable database with a real LOGIN application role (TASK-0795, TASK-0797).

The schema owner creates and migrates a ``*_test`` database and provisions
the requested games; a test-scoped role ``game_predictor_app_test_<hex>`` is
provisioned by the production ``provision_application_role`` with a random
password valid for one hour. Privileges exist only inside the test database;
the database and the role are dropped on exit.
"""

from __future__ import annotations

import re
import secrets
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.database_roles import (
    ApplicationRoleSpec,
    provision_application_role,
)
from game_predictor_api.storage.game_data_v2_manifest_v5 import CREATE_TABLES
from game_predictor_api.storage.game_partition_lifecycle import (
    GamePartitionLifecycleKind,
    GamePartitionLifecycleRepository,
)
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

ALEMBIC_INI = Path(__file__).resolve().parents[4] / "alembic.ini"
_NAME = re.compile(r"^game_predictor_t[0-9a-z]+_[0-9a-f]{12}_test$")


@dataclass(frozen=True)
class ApplicationRoleDatabase:
    owner_engine: Engine
    app_engine: Engine
    owner_url: URL
    app_url: URL
    role: str
    owner_role: str
    games: dict[str, UUID]

    def subprocess_environment(self, **changes: str) -> dict[str, str]:
        """Pin fresh processes to this checkout, even with a shared editable venv."""
        import os

        root = Path(__file__).resolve().parents[4]
        sources = [str(root / name) for name in ("services/api/src", "services/worker/src")]
        existing = os.environ.get("PYTHONPATH")
        if existing:
            sources.append(existing)
        return {**os.environ, "PYTHONPATH": os.pathsep.join(sources), **changes}

    def settings(self, root: Path) -> ApiSettings:
        """API settings whose runtime sessions log in as the application role."""

        return ApiSettings(
            host="127.0.0.1",
            port=8000,
            admin_origin="http://127.0.0.1:3000",
            database_url=self.app_url.render_as_string(hide_password=False),
            configured_owner_database_url=self.owner_url.render_as_string(hide_password=False),
            artifact_root=(root / "artifacts").resolve(),
            import_root=(root / "imports").resolve(),
        )


def provision_game(engine: Engine, code: str) -> UUID:
    """Create a catalog game and its V2 partitions as the schema owner."""

    game_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                """INSERT INTO public.games (id, code, name, status, expected_layout_count)
                VALUES (:id, :code, :name, 'draft', 500000)"""
            ),
            {"id": game_id, "code": code, "name": code},
        )
    with Session(engine) as session, session.begin():
        operation_id = (
            GamePartitionLifecycleRepository(session)
            .start_or_resume(game_id=game_id, kind=GamePartitionLifecycleKind.PROVISION)
            .operation_id
        )
    for _ in range(len(CREATE_TABLES) + 2):
        with Session(engine) as session, session.begin():
            receipt = GamePartitionLifecycleRepository(session).run_next(operation_id)
        if receipt.status == "done":
            return game_id
    raise AssertionError("provisioning did not reach done")


@contextmanager
def application_role_database(
    prefix: str, game_codes: tuple[str, ...], *, migration_revision: str = "head"
) -> Iterator[ApplicationRoleDatabase]:
    suffix = uuid4().hex[:12]
    name = f"game_predictor_{prefix}_{suffix}_test"
    role = f"game_predictor_app_test_{suffix}"
    assert _NAME.fullmatch(name), name
    assert re.fullmatch(r"game_predictor_app_test_[0-9a-f]{12}", role)
    base = make_url(ApiSettings.from_environment().owner_database_url)
    assert base.database != name
    owner_url = base.set(database=name)
    password = secrets.token_urlsafe(24)
    app_url = owner_url.set(username=role, password=password)
    maintenance = create_engine(
        base.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
    )
    owner_engine = create_engine(owner_url, poolclass=NullPool, connect_args={"connect_timeout": 5})
    app_engine = create_engine(app_url, poolclass=NullPool, connect_args={"connect_timeout": 5})
    with maintenance.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    try:
        config = Config(str(ALEMBIC_INI))
        config.set_main_option(
            "sqlalchemy.url", owner_url.render_as_string(hide_password=False).replace("%", "%%")
        )
        command.upgrade(config, migration_revision)
        games = {code: provision_game(owner_engine, code) for code in game_codes}
        with owner_engine.begin() as connection:
            owner_role = str(connection.execute(text("SELECT current_user")).scalar_one())
            provision_application_role(
                connection, ApplicationRoleSpec(role_name=role, password=password)
            )
            # A leaked test credential expires on its own even if teardown fails.
            expires = connection.execute(
                text("SELECT to_char(now() + interval '1 hour', 'YYYY-MM-DD HH24:MI:SSOF')")
            ).scalar_one()
            connection.exec_driver_sql(f"ALTER ROLE \"{role}\" VALID UNTIL '{expires}'")
        yield ApplicationRoleDatabase(
            owner_engine=owner_engine,
            app_engine=app_engine,
            owner_url=owner_url,
            app_url=app_url,
            role=role,
            owner_role=owner_role,
            games=games,
        )
    finally:
        app_engine.dispose()
        owner_engine.dispose()
        try:
            with maintenance.connect() as connection:
                active = -1
                for _attempt in range(50):
                    active = connection.execute(
                        text("SELECT count(*) FROM pg_stat_activity WHERE datname=:name"),
                        {"name": name},
                    ).scalar_one()
                    if active == 0:
                        break
                    time.sleep(0.1)
                assert active == 0, "Refusing DROP while a test connection remains"
                connection.exec_driver_sql(f'DROP DATABASE "{name}"')
        finally:
            with maintenance.connect() as connection:
                connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{role}"')
            maintenance.dispose()


__all__ = [
    "ALEMBIC_INI",
    "ApplicationRoleDatabase",
    "application_role_database",
    "provision_game",
]
