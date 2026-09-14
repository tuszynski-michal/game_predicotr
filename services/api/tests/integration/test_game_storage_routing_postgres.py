"""Isolated PostgreSQL acceptance for TASK-0519 routing and write fences."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.application.jobs import JobService
from game_predictor_api.application.page_geometry_overrides import PageGeometryOverrideService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_api.storage.database import GameStorageSession
from game_predictor_api.storage.game_data_v2_manifest_v1 import GAME_TABLES, VERSION
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
    GameStorageRoutingError,
    GameStorageSchema,
    game_storage_scope,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import ImageGeometryRolloutStateModel
from game_predictor_api.storage.page_geometry_override_repository import (
    SqlAlchemyPageGeometryOverrideRepository,
)
from game_predictor_worker.images.orchestration import ImageFileRegistration
from game_predictor_worker.images.orchestration_store import SqlAlchemyImageBatchStore
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)


@pytest.fixture
def database() -> Iterator[Engine]:
    name = "game_predictor_task0519_" + uuid4().hex[:12]
    assert re.fullmatch(r"game_predictor_task0519_[0-9a-f]{12}", name)
    url = make_url(ApiSettings.from_environment().database_url)
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
    )
    engine = create_engine(url.set(database=name), connect_args={"connect_timeout": 5})
    config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url",
        url.set(database=name).render_as_string(hide_password=False).replace("%", "%%"),
    )
    with maintenance.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    try:
        command.upgrade(config, "0106_game_storage_routing_fence")
        yield engine
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            active = connection.execute(
                text("SELECT count(*) FROM pg_stat_activity WHERE datname=:name"), {"name": name}
            ).scalar_one()
            assert active == 0
            connection.exec_driver_sql(f'DROP DATABASE "{name}"')
        maintenance.dispose()


def _game(connection: object, *, code: str) -> UUID:
    game_id = uuid4()
    connection.execute(  # type: ignore[attr-defined]
        text(
            "INSERT INTO public.games "
            "(id, code, name, status, expected_layout_count) "
            "VALUES (:id, :code, :name, 'draft', 500000)"
        ),
        {"id": game_id, "code": code, "name": code},
    )
    return game_id


def test_v2_parents_have_scope_default_rls_and_runtime_triggers(database: Engine) -> None:
    with database.connect() as connection:
        guarded = set(
            connection.execute(
                text(
                    "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='game_data_v2' AND c.relrowsecurity AND c.relforcerowsecurity"
                )
            ).scalars()
        )
        defaults = set(
            connection.execute(
                text(
                    "SELECT c.relname FROM pg_attrdef d JOIN pg_attribute a "
                    "ON a.attrelid=d.adrelid "
                    "AND a.attnum=d.adnum JOIN pg_class c ON c.oid=a.attrelid "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='game_data_v2' AND a.attname='game_id' "
                    "AND pg_get_expr(d.adbin,d.adrelid) LIKE '%current_game_id_v1%'"
                )
            ).scalars()
        )
        triggers = set(
            connection.execute(
                text(
                    "SELECT tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='game_data_v2' AND NOT t.tgisinternal"
                )
            ).scalars()
        )
    assert guarded == set(GAME_TABLES)
    assert defaults == set(GAME_TABLES)
    assert len(triggers) == 7


def test_router_selects_v2_and_default_injects_exact_game(database: Engine) -> None:
    with database.begin() as connection:
        game_id = _game(connection, code="route-v2")
        connection.execute(
            text(
                "INSERT INTO public.game_storage_locations "
                "(game_id,store_schema,generation,manifest_version,status,revision) "
                "VALUES (:game_id,'game_data_v2',2,:version,'active',1)"
            ),
            {"game_id": game_id, "version": VERSION},
        )
        suffix = game_id.hex
        connection.exec_driver_sql(
            f"CREATE TABLE game_data_v2.image_geometry_rollout_states_g_{suffix} "
            f"PARTITION OF game_data_v2.image_geometry_rollout_states FOR VALUES IN ('{game_id}')"
        )
    factory = sessionmaker(bind=database, class_=GameStorageSession, expire_on_commit=False)
    with game_storage_scope(game_id), factory.begin() as session:
        session.execute(
            text(
                "INSERT INTO image_geometry_rollout_states "
                "(geometry_mode,cell_asset_mode,revision,backfill_status,updated_by) "
                "VALUES ('legacy','legacy_files',0,'not_started','test')"
            )
        )
        location = GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)
        assert location.store_schema is GameStorageSchema.V2
        assert session.scalar(text("SELECT game_id FROM image_geometry_rollout_states")) == game_id


def test_page_geometry_snapshot_reads_v2_in_a_new_unscoped_session(database: Engine) -> None:
    """A saved correction must survive reopening the report after V2 cutover."""

    with database.begin() as connection:
        game_id = _game(connection, code="geometry-snapshot-v2")
        connection.execute(
            text(
                "INSERT INTO public.game_storage_locations "
                "(game_id,store_schema,generation,manifest_version,status,revision) "
                "VALUES (:game_id,'game_data_v2',2,:version,'active',1)"
            ),
            {"game_id": game_id, "version": VERSION},
        )
        connection.exec_driver_sql(
            "CREATE TABLE game_data_v2.image_page_geometry_overrides_g_"
            f"{game_id.hex} PARTITION OF game_data_v2.image_page_geometry_overrides "
            f"FOR VALUES IN ('{game_id}')"
        )

    quads = tuple(
        (
            {"x": column * 100 + 5, "y": row * 100 + 5},
            {"x": column * 100 + 95, "y": row * 100 + 5},
            {"x": column * 100 + 95, "y": row * 100 + 95},
            {"x": column * 100 + 5, "y": row * 100 + 95},
        )
        for row in range(3)
        for column in range(3)
    )
    source_checksum = "a" * 64
    factory = sessionmaker(bind=database, class_=GameStorageSession, expire_on_commit=False)

    with factory.begin() as session:
        writer = PageGeometryOverrideService(SqlAlchemyPageGeometryOverrideRepository(session))
        saved, created = writer.save(
            game_id=game_id,
            source_checksum_sha256=source_checksum,
            image_width=320,
            image_height=320,
            expected_board_count=9,
            final_quads=quads,
            actor="test-owner",
        )
        assert created is True

    # The report opens a separate API session and has no /games/{id} path scope.
    with factory.begin() as session:
        report = PageGeometryOverrideService(SqlAlchemyPageGeometryOverrideRepository(session))
        snapshot = report.snapshot(game_id=game_id)

    assert snapshot[source_checksum]["decisionChecksumSha256"] == saved.decision_checksum_sha256
    with database.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM public.image_page_geometry_overrides "
                    "WHERE game_id=:game_id"
                ),
                {"game_id": game_id},
            )
            == 0
        )


def test_import_policy_reads_v2_rollout_in_a_new_unscoped_session(database: Engine) -> None:
    """The report and start must pin the same per-game engine policy."""

    with database.begin() as connection:
        game_id = _game(connection, code="import-policy-v2")
        connection.execute(
            text(
                "INSERT INTO public.game_storage_locations "
                "(game_id,store_schema,generation,manifest_version,status,revision) "
                "VALUES (:game_id,'game_data_v2',2,:version,'active',1)"
            ),
            {"game_id": game_id, "version": VERSION},
        )
        connection.exec_driver_sql(
            "CREATE TABLE game_data_v2.image_geometry_rollout_states_g_"
            f"{game_id.hex} PARTITION OF game_data_v2.image_geometry_rollout_states "
            f"FOR VALUES IN ('{game_id}')"
        )

    factory = sessionmaker(bind=database, class_=GameStorageSession, expire_on_commit=False)
    with game_storage_scope(game_id), factory.begin() as session:
        session.add(
            ImageGeometryRolloutStateModel(
                game_id=game_id,
                geometry_mode="structured_lattice_v3",
                cell_asset_mode="virtual_default",
                revision=1,
                backfill_status="not_started",
                updated_by="test-owner",
            )
        )

    # Browser preflight and Start open separate, unscoped API sessions.
    with factory.begin() as session:
        policy = JobService(SqlAlchemyJobRepository(session)).current_image_import_engine_policy(
            game_id=game_id
        )

    assert policy.policy.value == "structured_lattice_v3"
    assert policy.revision == 1
    with database.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM public.image_geometry_rollout_states "
                    "WHERE game_id=:game_id"
                ),
                {"game_id": game_id},
            )
            == 0
        )


def test_image_batch_registration_uses_v2_composite_identity(database: Engine) -> None:
    pipeline_fingerprint = "f" * 64
    registered_at = datetime(2026, 9, 14, tzinfo=UTC)
    with database.begin() as connection:
        game_id = _game(connection, code="image-batch-v2")
        connection.execute(
            text(
                "INSERT INTO public.game_storage_locations "
                "(game_id,store_schema,generation,manifest_version,status,revision) "
                "VALUES (:game_id,'game_data_v2',2,:version,'active',1)"
            ),
            {"game_id": game_id, "version": VERSION},
        )
        connection.exec_driver_sql(
            "CREATE TABLE game_data_v2.image_import_job_files_g_"
            f"{game_id.hex} PARTITION OF game_data_v2.image_import_job_files "
            f"FOR VALUES IN ('{game_id}')"
        )

    factory = sessionmaker(bind=database, class_=GameStorageSession, expire_on_commit=False)
    with factory.begin() as session:
        job = SqlAlchemyJobRepository(session).add_job(
            create_job(
                JobType.IMPORT,
                game_id=game_id,
                input_payload={
                    "schema_version": 1,
                    "import_kind": "image_directory",
                    "pipeline_fingerprint": pipeline_fingerprint,
                },
                created_at=registered_at,
            )
        )

    registrations = tuple(
        ImageFileRegistration(
            source_checksum_sha256=str(index) * 64,
            source_relative_path=f"source-{index}.jpg",
            order_index=index - 1,
        )
        for index in (1, 2)
    )
    store = SqlAlchemyImageBatchStore(factory)
    with game_storage_scope(game_id):
        store.register_files(
            job.id,
            registrations=registrations,
            pipeline_fingerprint=pipeline_fingerprint,
            registered_at=registered_at,
        )
        store.register_files(
            job.id,
            registrations=registrations,
            pipeline_fingerprint=pipeline_fingerprint,
            registered_at=registered_at,
        )

    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM public.image_file_executions")) == 2
        assert connection.scalar(text("SELECT count(*) FROM public.image_import_job_files")) == 0
        rows = connection.execute(
            text(
                "SELECT game_id, job_id, file_execution_key, order_index "
                "FROM game_data_v2.image_import_job_files ORDER BY order_index"
            )
        ).all()
    assert len(rows) == 2
    assert {row.game_id for row in rows} == {game_id}
    assert {row.job_id for row in rows} == {job.id}
    assert [row.order_index for row in rows] == [0, 1]


def test_write_status_generation_and_transaction_lock_are_fail_closed(database: Engine) -> None:
    with database.begin() as connection:
        game_id = _game(connection, code="fence-v2")
        connection.execute(
            text(
                "INSERT INTO public.game_storage_locations "
                "(game_id,store_schema,generation,manifest_version,status,revision) "
                "VALUES (:game_id,'public',1,:version,'active',0)"
            ),
            {"game_id": game_id, "version": VERSION},
        )
    factory = sessionmaker(bind=database, class_=GameStorageSession, expire_on_commit=False)
    first = factory()
    try:
        GameStorageRouter().bind(first, game_id, intent=GameStorageIntent.WRITE)
        with database.connect() as concurrent:
            concurrent.execute(text("SET LOCAL lock_timeout='100ms'"))
            advisory_available = concurrent.scalar(
                text(
                    "SELECT pg_try_advisory_xact_lock("
                    "hashtextextended(CAST(:game_id AS text), 519))"
                ),
                {"game_id": game_id},
            )
            assert advisory_available is False
            with pytest.raises(DBAPIError):
                concurrent.execute(
                    text(
                        "UPDATE public.game_storage_locations SET generation=2, revision=1 "
                        "WHERE game_id=:game_id"
                    ),
                    {"game_id": game_id},
                )
        first.rollback()
    finally:
        first.close()
    with database.begin() as connection:
        connection.execute(
            text(
                "UPDATE public.game_storage_locations "
                "SET status='migrating', revision=revision+1 WHERE game_id=:game_id"
            ),
            {"game_id": game_id},
        )
    with factory() as session:
        with pytest.raises(GameStorageRoutingError) as blocked:
            GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)
        assert blocked.value.code == "GAME_STORAGE_WRITE_UNAVAILABLE"
    with game_storage_scope(game_id), factory() as session:
        with pytest.raises(GameStorageRoutingError) as raw_sql_blocked:
            session.execute(
                text("UPDATE public.games SET updated_at=updated_at WHERE id=:game_id"),
                {"game_id": game_id},
            )
        assert raw_sql_blocked.value.code == "GAME_STORAGE_WRITE_UNAVAILABLE"
    with factory() as session:
        with pytest.raises(GameStorageRoutingError) as inferred_scope_blocked:
            session.execute(
                text("UPDATE public.games SET updated_at=updated_at WHERE id=:game_id"),
                {"game_id": game_id},
            )
        assert inferred_scope_blocked.value.code == "GAME_STORAGE_WRITE_UNAVAILABLE"
    with database.begin() as connection:
        connection.execute(
            text(
                "UPDATE public.game_storage_locations "
                "SET store_schema='game_data_v2', status='active', generation=2, "
                "revision=revision+1 WHERE game_id=:game_id"
            ),
            {"game_id": game_id},
        )
    with factory() as session:
        with pytest.raises(GameStorageRoutingError) as stale:
            GameStorageRouter().bind(
                session,
                game_id,
                intent=GameStorageIntent.READ,
                expected_generation=1,
            )
        assert stale.value.code == "GAME_STORAGE_GENERATION_STALE"


def test_reused_session_resolves_storage_again_after_commit(database: Engine) -> None:
    with database.begin() as connection:
        game_id = _game(connection, code="rebind-v2")
        connection.execute(
            text(
                "INSERT INTO public.game_storage_locations "
                "(game_id,store_schema,generation,manifest_version,status,revision) "
                "VALUES (:game_id,'public',1,:version,'active',0)"
            ),
            {"game_id": game_id, "version": VERSION},
        )
    factory = sessionmaker(bind=database, class_=GameStorageSession, expire_on_commit=False)
    with factory() as session:
        first = GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)
        assert first.generation == 1
        session.commit()
        with database.begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.game_storage_locations "
                    "SET status='migrating', revision=1 WHERE game_id=:game_id"
                ),
                {"game_id": game_id},
            )
        with pytest.raises(GameStorageRoutingError) as blocked:
            GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)
        assert blocked.value.code == "GAME_STORAGE_WRITE_UNAVAILABLE"
        assert blocked.value.details["generation"] == 1
