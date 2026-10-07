"""TASK-0795: the application role really isolates games through RLS.

Runs only on a dedicated ``*_test`` database. The schema owner migrates the
database and provisions two games; a test-scoped LOGIN role
(``game_predictor_app_test_<hex>``) is provisioned by the production
``provision_application_role`` with a random password, valid for one hour,
and dropped at teardown. It gets privileges only inside the test database.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from _application_role_database import application_role_database
from fastapi.testclient import TestClient
from game_predictor_api.config import ApiSettings
from game_predictor_api.main import create_app
from game_predictor_api.storage.database import (
    create_database_engine,
    create_session_factory,
)
from game_predictor_api.storage.database_roles import describe_application_role
from game_predictor_api.storage.game_data_v2_manifest_v5 import CREATE_TABLES
from game_predictor_api.storage.game_entity_locator import GameEntityLocator
from game_predictor_api.storage.game_partition_lifecycle import partition_name
from game_predictor_api.storage.game_storage_routing import (
    GameStorageRoutingError,
    current_game_storage_scope,
    game_storage_scope,
)
from game_predictor_api.storage.models import (
    BrowserSelectionRetentionModel,
    ImageGeometryRolloutStateModel,
)
from game_predictor_api.storage.schema_readiness import require_alembic_head
from sqlalchemy import Engine, delete, select, text, update
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)

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


@pytest.fixture(scope="module")
def isolated() -> Iterator[_Isolated]:
    # One database per module: every test leaves games A and B unchanged.
    with application_role_database("t0795", ("t0795-a", "t0795-b")) as database:
        yield _Isolated(
            owner_engine=database.owner_engine,
            app_engine=database.app_engine,
            owner_url=database.owner_url,
            app_url=database.app_url,
            role=database.role,
            owner_role=database.owner_role,
            game_a=database.games["t0795-a"],
            game_b=database.games["t0795-b"],
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


@pytest.mark.parametrize("status", ["migrating", "deleting", "blocked"])
def test_owner_lookup_reads_other_games_without_requesting_write(
    isolated: _Isolated, status: str
) -> None:
    factory = create_session_factory(isolated.app_engine)
    locator = GameEntityLocator(factory)
    with isolated.owner_engine.begin() as connection:
        connection.execute(
            text("UPDATE public.game_storage_locations SET status = :status WHERE game_id = :id"),
            {"status": status, "id": isolated.game_b},
        )
    try:
        # Fresh locator sessions must temporarily override the caller's scope
        # and probe both owners without upgrading a read to a maintenance write.
        with game_storage_scope(isolated.game_a):
            assert (
                locator.locate("image_geometry_rollout_states", "game_id", isolated.game_a)
                == isolated.game_a
            )
            assert (
                locator.locate("image_geometry_rollout_states", "game_id", isolated.game_b)
                == isolated.game_b
            )
            restored_scope = current_game_storage_scope()
            assert restored_scope is not None
            assert restored_scope.game_id == isolated.game_a
        assert locator.locate("image_geometry_rollout_states", "game_id", uuid4()) is None
        # Identifying the owner never makes a non-active store writable.
        with game_storage_scope(isolated.game_b), factory() as session:
            with pytest.raises(GameStorageRoutingError) as raised:
                session.execute(
                    update(ImageGeometryRolloutStateModel)
                    .where(ImageGeometryRolloutStateModel.game_id == isolated.game_b)
                    .values(updated_by="must-not-write")
                )
            assert raised.value.code == "GAME_STORAGE_WRITE_UNAVAILABLE"
            assert raised.value.details["gameId"] == str(isolated.game_b)
            # Unknown text SQL must retain its conservative WRITE classification.
            with pytest.raises(GameStorageRoutingError) as raw_raised:
                session.execute(
                    text("UPDATE image_geometry_rollout_states SET updated_by = 'must-not-write'")
                )
            assert raw_raised.value.code == "GAME_STORAGE_WRITE_UNAVAILABLE"
        assert _ab_rollout_owners(isolated) == {
            isolated.game_a: _UNTOUCHED,
            isolated.game_b: _UNTOUCHED,
        }
    finally:
        with isolated.owner_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.game_storage_locations SET status = 'active' WHERE game_id = :id"
                ),
                {"id": isolated.game_b},
            )


def test_browser_start_owner_dependency_ignores_unrelated_maintenance(
    isolated: _Isolated, tmp_path: Path
) -> None:
    upload_id = uuid4()
    factory = create_session_factory(isolated.app_engine)
    with game_storage_scope(isolated.game_a), factory.begin() as session:
        session.add(
            BrowserSelectionRetentionModel(
                upload_id=upload_id,
                game_id=isolated.game_a,
                display_name="isolated game A staging",
                state="ready",
                board_import_status="ready",
                manifest_checksum_sha256="0" * 64,
                finalized_at=datetime.now(UTC),
            )
        )
    with isolated.owner_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE public.game_storage_locations SET status = 'migrating' WHERE game_id = :id"
            ),
            {"id": isolated.game_b},
        )
    application = create_app(
        ApiSettings(
            host="127.0.0.1",
            port=8000,
            admin_origin="http://127.0.0.1:3000",
            database_url=isolated.app_url.render_as_string(hide_password=False),
            configured_owner_database_url=isolated.owner_url.render_as_string(hide_password=False),
            artifact_root=(tmp_path / "artifacts").resolve(),
            import_root=(tmp_path / "imports").resolve(),
            remote_selection_recovery_enabled=False,
        )
    )
    try:
        with TestClient(application) as client:
            response = client.post(
                f"/api/v1/admin/image-imports/browser-selections/{upload_id}/start",
                json={
                    "gameId": str(isolated.game_a),
                    "manifestChecksumSha256": "0" * 64,
                    "preflightChecksumSha256": "0" * 64,
                },
            )
        # Deliberately no staging files: once owner lookup succeeds, normal
        # import validation must report the missing source, not game B's 409.
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "IMAGE_BROWSER_SELECTION_NOT_FOUND"
        assert (
            GameEntityLocator(factory).locate(
                "browser_selection_retention_states", "upload_id", upload_id
            )
            == isolated.game_a
        )
        assert _ab_rollout_owners(isolated) == {
            isolated.game_a: _UNTOUCHED,
            isolated.game_b: _UNTOUCHED,
        }
    finally:
        application.state.database_engine.dispose()
        with isolated.owner_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.game_storage_locations SET status = 'active' WHERE game_id = :id"
                ),
                {"id": isolated.game_b},
            )
        with game_storage_scope(isolated.game_a), factory.begin() as session:
            session.execute(
                delete(BrowserSelectionRetentionModel).where(
                    BrowserSelectionRetentionModel.upload_id == upload_id
                )
            )


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
