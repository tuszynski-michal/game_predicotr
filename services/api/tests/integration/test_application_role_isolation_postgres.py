"""TASK-0795: the application role really isolates games through RLS.

Runs only on a dedicated ``*_test`` database. The schema owner migrates the
database and provisions two games; a test-scoped LOGIN role
(``game_predictor_app_test_<hex>``) is provisioned by the production
``provision_application_role`` with a random password, valid for one hour,
and dropped at teardown. It gets privileges only inside the test database.
"""

from __future__ import annotations

import os
import re
import secrets
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from game_predictor_api.config import ApiSettings
from game_predictor_api.main import create_app
from game_predictor_api.storage.database import (
    create_database_engine,
    create_session_factory,
)
from game_predictor_api.storage.database_roles import (
    ApplicationRoleSpec,
    describe_application_role,
    provision_application_role,
)
from game_predictor_api.storage.game_data_v2_manifest_v4 import CREATE_TABLES
from game_predictor_api.storage.game_partition_lifecycle import (
    GamePartitionLifecycleKind,
    GamePartitionLifecycleRepository,
    partition_name,
)
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.models import ImageGeometryRolloutStateModel
from game_predictor_api.storage.schema_readiness import require_alembic_head
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)

_ALEMBIC_INI = Path(__file__).resolve().parents[4] / "alembic.ini"
_INSUFFICIENT_PRIVILEGE = "42501"


@dataclass(frozen=True)
class _Isolated:
    owner_engine: Engine
    app_engine: Engine
    owner_url: URL
    app_url: URL
    role: str
    owner_role: str
    game_a: UUID
    game_b: UUID


def _provision_game(engine: Engine, code: str) -> UUID:
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


@pytest.fixture(scope="module")
def isolated() -> Iterator[_Isolated]:
    # One database per module: every test leaves games A and B unchanged.
    suffix = uuid4().hex[:12]
    name = f"game_predictor_t0795_{suffix}_test"
    role = f"game_predictor_app_test_{suffix}"
    assert re.fullmatch(r"game_predictor_t0795_[0-9a-f]{12}_test", name)
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
        config = Config(str(_ALEMBIC_INI))
        config.set_main_option(
            "sqlalchemy.url", owner_url.render_as_string(hide_password=False).replace("%", "%%")
        )
        command.upgrade(config, "head")
        game_a = _provision_game(owner_engine, "t0795-a")
        game_b = _provision_game(owner_engine, "t0795-b")
        with owner_engine.begin() as connection:
            owner_role = str(connection.execute(text("SELECT current_user")).scalar_one())
            provision_application_role(
                connection, ApplicationRoleSpec(role_name=role, password=password)
            )
            # A leaked test credential expires on its own even if teardown fails.
            connection.exec_driver_sql(
                f"ALTER ROLE \"{role}\" VALID UNTIL '{_one_hour_from_now(connection)}'"
            )
        yield _Isolated(
            owner_engine=owner_engine,
            app_engine=app_engine,
            owner_url=owner_url,
            app_url=app_url,
            role=role,
            owner_role=owner_role,
            game_a=game_a,
            game_b=game_b,
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


def _one_hour_from_now(connection: object) -> str:
    from sqlalchemy.engine import Connection

    return str(
        cast(Connection, connection)
        .execute(text("SELECT to_char(now() + interval '1 hour', 'YYYY-MM-DD HH24:MI:SSOF')"))
        .scalar_one()
    )


def _sqlstate(error: DBAPIError) -> str | None:
    return cast("str | None", getattr(error.orig, "sqlstate", None))


def _rollout_owners(isolated: _Isolated) -> dict[UUID, str]:
    with isolated.owner_engine.connect() as connection:
        rows = connection.execute(
            text("SELECT game_id, updated_by FROM game_data_v2.image_geometry_rollout_states")
        ).all()
    return {UUID(str(row[0])): str(row[1]) for row in rows}


def _ab_rollout_owners(isolated: _Isolated) -> dict[UUID, str]:
    owners = _rollout_owners(isolated)
    return {game: owners[game] for game in (isolated.game_a, isolated.game_b)}


_UNTOUCHED = "system:catalog-game-create"


def test_role_is_least_privileged_and_cannot_escalate(isolated: _Isolated) -> None:
    with isolated.owner_engine.connect() as connection:
        report = describe_application_role(connection, isolated.role)
    assert report.compliant, report.as_dict()
    assert report.can_login and not report.superuser and not report.bypass_rls

    with isolated.app_engine.connect() as connection:
        row = connection.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).one()
        assert tuple(row) == (False, False)
        # The import storage guard and the storage inventory read the size of
        # the current database; CONNECT is enough for that.
        assert (
            int(
                connection.execute(text("SELECT pg_database_size(current_database())")).scalar_one()
            )
            > 0
        )
    with isolated.app_engine.connect() as connection, pytest.raises(DBAPIError) as error:
        connection.exec_driver_sql(f'SET ROLE "{isolated.owner_role}"')
    assert _sqlstate(error.value) == _INSUFFICIENT_PRIVILEGE
    # Turning row security off does not bypass it; the query fails instead.
    with isolated.app_engine.connect() as connection, pytest.raises(DBAPIError) as error:
        connection.exec_driver_sql("SET row_security = off")
        connection.exec_driver_sql(
            "SELECT count(*) FROM game_data_v2.image_geometry_rollout_states"
        )
    assert _sqlstate(error.value) == _INSUFFICIENT_PRIVILEGE


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT count(*) FROM game_data_v2.image_geometry_rollout_states",
        "SELECT game_id FROM game_data_v2.image_geometry_rollout_states",
        "UPDATE game_data_v2.image_geometry_rollout_states SET updated_by = 'unbound'",
        "DELETE FROM game_data_v2.image_geometry_rollout_states",
        # An empty game table is refused the same way: the policy function is
        # evaluated for partition pruning before any row is read.
        "SELECT count(*) FROM game_data_v2.review_batches",
    ],
)
def test_unbound_statement_on_a_game_table_fails_explicitly(
    isolated: _Isolated, statement: str
) -> None:
    with isolated.app_engine.connect() as connection, pytest.raises(DBAPIError) as error:
        connection.exec_driver_sql(statement)
    assert _sqlstate(error.value) == _INSUFFICIENT_PRIVILEGE
    assert "GAME_STORAGE_SCOPE_REQUIRED" in str(error.value.orig)
    assert set(_ab_rollout_owners(isolated).values()) == {_UNTOUCHED}


def test_unbound_orm_session_fails_instead_of_returning_rows(isolated: _Isolated) -> None:
    # ORM game tables are unqualified; only a game binding puts game_data_v2
    # on the transaction's search_path, so an unbound ORM read cannot even
    # resolve the table (and a qualified one hits the RLS scope check above).
    factory = create_session_factory(isolated.app_engine)
    with factory() as session, pytest.raises(DBAPIError) as error:
        session.execute(select(ImageGeometryRolloutStateModel.game_id)).all()
    assert _sqlstate(error.value) == "42P01"


def test_bound_game_sees_only_its_own_rows(isolated: _Isolated) -> None:
    factory = create_session_factory(isolated.app_engine)
    for game_id in (isolated.game_a, isolated.game_b):
        with game_storage_scope(game_id), factory() as session:
            orm_rows = session.scalars(select(ImageGeometryRolloutStateModel.game_id)).all()
            raw_rows = session.execute(
                text("SELECT game_id FROM game_data_v2.image_geometry_rollout_states")
            ).all()
        assert orm_rows == [game_id]
        assert [UUID(str(row[0])) for row in raw_rows] == [game_id]


def test_write_without_game_predicate_cannot_touch_another_game(isolated: _Isolated) -> None:
    factory = create_session_factory(isolated.app_engine)
    try:
        _assert_writes_stay_in_the_bound_game(isolated, factory)
    finally:
        with isolated.owner_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE game_data_v2.image_geometry_rollout_states SET updated_by = :value "
                    "WHERE game_id = :game"
                ),
                {"value": _UNTOUCHED, "game": isolated.game_a},
            )


def _assert_writes_stay_in_the_bound_game(
    isolated: _Isolated, factory: sessionmaker[Session]
) -> None:
    with game_storage_scope(isolated.game_a), factory.begin() as session:
        updated = session.execute(
            text("UPDATE game_data_v2.image_geometry_rollout_states SET updated_by = 'only-a'")
        )
        assert updated.rowcount == 1
    assert _ab_rollout_owners(isolated) == {
        isolated.game_a: "only-a",
        isolated.game_b: _UNTOUCHED,
    }

    with game_storage_scope(isolated.game_a), factory() as session:
        deleted = session.execute(text("DELETE FROM game_data_v2.image_geometry_rollout_states"))
        assert deleted.rowcount == 1
        session.rollback()

    # Moving a row to another game, or writing a row for another game, is
    # rejected by the policy's WITH CHECK.
    with (
        game_storage_scope(isolated.game_a),
        factory() as session,
        pytest.raises(DBAPIError) as error,
    ):
        session.execute(
            text("UPDATE game_data_v2.image_geometry_rollout_states SET game_id = :other"),
            {"other": isolated.game_b},
        )
    assert _sqlstate(error.value) == _INSUFFICIENT_PRIVILEGE
    with isolated.app_engine.connect() as connection, pytest.raises(DBAPIError) as error:
        connection.execute(
            text("SELECT set_config('game_predictor.game_id', :game, true)"),
            {"game": str(isolated.game_a)},
        )
        # The RLS INSERT check runs before NOT NULL constraints of the row.
        connection.execute(
            text("INSERT INTO game_data_v2.review_batches (id, game_id) VALUES (:id, :other)"),
            {"id": uuid4(), "other": isolated.game_b},
        )
    assert _sqlstate(error.value) == _INSUFFICIENT_PRIVILEGE
    assert _ab_rollout_owners(isolated) == {
        isolated.game_a: "only-a",
        isolated.game_b: _UNTOUCHED,
    }


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE public.t0795_probe (id integer)",
        "CREATE TABLE game_data_v2.t0795_probe (id integer)",
        "CREATE SCHEMA t0795_probe",
        "ALTER TABLE game_data_v2.image_geometry_rollout_states DISABLE ROW LEVEL SECURITY",
        "ALTER TABLE game_data_v2.image_geometry_rollout_states NO FORCE ROW LEVEL SECURITY",
        "DROP POLICY game_scope_v1 ON game_data_v2.image_geometry_rollout_states",
        "TRUNCATE game_data_v2.image_geometry_rollout_states",
        "DROP TABLE game_data_v2.review_batches",
        "ALTER TABLE public.games ADD COLUMN t0795_probe integer",
        "UPDATE public.alembic_version SET version_num = version_num",
        "VACUUM public.games",
    ],
)
def test_application_role_cannot_run_ddl_or_owner_maintenance(
    isolated: _Isolated, statement: str
) -> None:
    connection = isolated.app_engine.connect()
    try:
        if statement.startswith("VACUUM"):
            # VACUUM by a non-owner only warns and skips; prove nothing ran.
            connection = connection.execution_options(isolation_level="AUTOCOMMIT")
            before = _vacuum_count(isolated)
            connection.exec_driver_sql(statement)
            assert _vacuum_count(isolated) == before
            return
        with pytest.raises(DBAPIError) as error:
            connection.exec_driver_sql(statement)
        assert _sqlstate(error.value) == _INSUFFICIENT_PRIVILEGE
    finally:
        connection.close()


def _vacuum_count(isolated: _Isolated) -> int:
    with isolated.owner_engine.connect() as connection:
        return int(
            connection.execute(
                text(
                    "SELECT vacuum_count FROM pg_stat_user_tables "
                    "WHERE schemaname = 'public' AND relname = 'games'"
                )
            ).scalar_one()
        )


def test_api_starts_and_creates_a_game_on_the_application_role(
    isolated: _Isolated, tmp_path: Path
) -> None:
    settings = ApiSettings(
        host="127.0.0.1",
        port=8000,
        admin_origin="http://127.0.0.1:3000",
        database_url=isolated.app_url.render_as_string(hide_password=False),
        configured_owner_database_url=isolated.owner_url.render_as_string(hide_password=False),
        artifact_root=(tmp_path / "artifacts").resolve(),
        import_root=(tmp_path / "imports").resolve(),
    )
    assert settings.uses_separate_owner_role
    runtime_engine = create_database_engine(settings)
    try:
        require_alembic_head(runtime_engine)
    finally:
        runtime_engine.dispose()

    application = create_app(settings)
    try:
        with TestClient(application) as client:
            listed = client.get("/api/v1/admin/games")
            assert listed.status_code == 200, listed.text
            assert {"t0795-a", "t0795-b"} <= {item["code"] for item in listed.json()}
            created = client.post(
                "/api/v1/admin/games",
                json={"code": "t0795-new", "name": "T0795 new", "expectedLayoutCount": 1000},
            )
            assert created.status_code == 201, created.text
            body = created.json()
            assert body["storageStatus"] == "active"
            assert body["storageWriteAvailable"] is True
            new_game = UUID(body["id"])
    finally:
        application.state.database_engine.dispose()

    # The partitions were created by the schema owner, the application role
    # owns nothing, and the default rollout policy row exists.
    with isolated.owner_engine.connect() as connection:
        owners = {
            str(owner)
            for (owner,) in connection.execute(
                text(
                    """SELECT pg_get_userbyid(c.relowner) FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'game_data_v2' AND c.relname = ANY(:names)"""
                ),
                {"names": [partition_name(new_game, table) for table in CREATE_TABLES]},
            )
        }
        assert owners == {isolated.owner_role}
        report = describe_application_role(connection, isolated.role)
    assert report.owned_relations == 0 and report.compliant
    assert _rollout_owners(isolated)[new_game] == _UNTOUCHED
