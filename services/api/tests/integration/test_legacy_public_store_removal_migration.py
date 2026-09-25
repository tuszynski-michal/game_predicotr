"""Isolated PostgreSQL proof for the irreversible legacy-public removal."""

from __future__ import annotations

import os
import re
import runpy
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameStatus
from game_predictor_api.storage.catalog_repository import SqlAlchemyCatalogRepository
from game_predictor_api.storage.database import GameStorageSession
from game_predictor_api.storage.game_data_v2_manifest_v1 import CREATE_TABLES, GAME_TABLES
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

PREVIOUS = "0124_game_data_v2_partial_visibility_constraints"
REVISION = "0125_remove_legacy_public_game_store"
MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "0125_remove_legacy_public_game_store.py"
)

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)


@pytest.fixture
def database() -> Iterator[tuple[Engine, Config]]:
    name = "game_predictor_task0684_" + uuid4().hex[:12]
    assert re.fullmatch(r"game_predictor_task0684_[0-9a-f]{12}", name)
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
        yield engine, config
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM pg_stat_activity WHERE datname=:name"),
                    {"name": name},
                )
                == 0
            )
            connection.exec_driver_sql(f'DROP DATABASE "{name}"')
        maintenance.dispose()


def _upgrade_previous(config: Config) -> None:
    command.upgrade(config, PREVIOUS)


def _legacy_tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names(schema="public")) & set(GAME_TABLES)


def _assert_guard(engine: Engine, config: Config, code: str, expected: set[str]) -> None:
    with pytest.raises(RuntimeError, match=code):
        command.upgrade(config, REVISION)
    assert _legacy_tables(engine) == expected
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM public.alembic_version")) == PREVIOUS


def test_snapshot_is_exact_frozen_manifest() -> None:
    namespace = runpy.run_path(str(MIGRATION_PATH))
    assert namespace["LEGACY_GAME_TABLES"] == tuple(sorted(GAME_TABLES))
    assert len(namespace["DROP_ORDER"]) == len(GAME_TABLES) == 65
    assert set(namespace["DROP_ORDER"]) == set(GAME_TABLES)


def test_happy_path_drops_only_legacy_game_tables(database: tuple[Engine, Config]) -> None:
    engine, config = database
    _upgrade_previous(config)
    command.upgrade(config, REVISION)
    inspector = inspect(engine)
    assert _legacy_tables(engine) == set()
    assert {"games", "symbols", "jobs", "game_storage_locations"} <= set(
        inspector.get_table_names(schema="public")
    )
    assert set(inspector.get_table_names(schema="game_data_v2")) == set(GAME_TABLES)


def test_nonempty_guard_happens_before_any_drop(database: tuple[Engine, Config]) -> None:
    engine, config = database
    _upgrade_previous(config)
    game_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO public.games (id, code, name, status, expected_layout_count) "
                "VALUES (:id, :code, 'Guard', 'draft', 1)"
            ),
            {"id": game_id, "code": game_id.hex},
        )
        connection.execute(
            text(
                "INSERT INTO public.image_geometry_rollout_states (game_id, updated_by) "
                "VALUES (:id, 'task-0684-test')"
            ),
            {"id": game_id},
        )
    _assert_guard(engine, config, "LEGACY_PUBLIC_STORE_TABLE_NOT_EMPTY", set(GAME_TABLES))


@pytest.mark.parametrize(
    ("setup_sql", "code"),
    (
        (
            "CREATE TABLE public.task0684_external_fk (game_id uuid PRIMARY KEY "
            "REFERENCES public.image_geometry_rollout_states (game_id))",
            "LEGACY_PUBLIC_STORE_EXTERNAL_FK",
        ),
        (
            "CREATE VIEW public.task0684_external_view AS "
            "SELECT game_id FROM public.image_geometry_rollout_states",
            "LEGACY_PUBLIC_STORE_EXTERNAL_RELATION_DEPENDENCY",
        ),
    ),
)
def test_external_dependency_guard_happens_before_any_drop(
    database: tuple[Engine, Config], setup_sql: str, code: str
) -> None:
    engine, config = database
    _upgrade_previous(config)
    with engine.begin() as connection:
        connection.exec_driver_sql(setup_sql)
    _assert_guard(engine, config, code, set(GAME_TABLES))


def test_relation_kind_guard_happens_before_any_drop(database: tuple[Engine, Config]) -> None:
    engine, config = database
    _upgrade_previous(config)
    with engine.begin() as connection:
        connection.exec_driver_sql('DROP TABLE public."image_sequence_alternatives"')
        connection.exec_driver_sql(
            "CREATE VIEW public.image_sequence_alternatives AS SELECT 1 AS sentinel"
        )
    _assert_guard(
        engine,
        config,
        "LEGACY_PUBLIC_STORE_RELATION_KIND_INVALID",
        set(GAME_TABLES) - {"image_sequence_alternatives"},
    )


def test_fresh_head_has_no_legacy_tables_and_bootstraps_v2(
    database: tuple[Engine, Config],
) -> None:
    engine, config = database
    command.upgrade(config, "head")
    assert _legacy_tables(engine) == set()
    factory = sessionmaker(bind=engine, class_=GameStorageSession, expire_on_commit=False)
    with factory() as session:
        game = CatalogService(SqlAlchemyCatalogRepository(session)).create_game(
            code="task0684-fresh-head",
            name="TASK-0684 fresh head",
            status=GameStatus.DRAFT,
        )
        session.commit()
    with factory() as session:
        GameStorageRouter().bind(session, game.id, intent=GameStorageIntent.READ)
        assert (
            session.scalar(
                text("SELECT count(*) FROM image_geometry_rollout_states WHERE game_id=:game_id"),
                {"game_id": game.id},
            )
            == 1
        )
        assert session.scalar(
            text(
                "SELECT count(*) FROM pg_inherits AS inheritance "
                "JOIN pg_class AS parent ON parent.oid = inheritance.inhparent "
                "JOIN pg_namespace AS namespace_row ON namespace_row.oid = parent.relnamespace "
                "WHERE namespace_row.nspname = 'game_data_v2' "
                "AND parent.relname = ANY(CAST(:tables AS text[]))"
            ),
            {"tables": list(CREATE_TABLES)},
        ) == len(CREATE_TABLES)


def test_downgrade_refuses_to_recreate_legacy_tables(database: tuple[Engine, Config]) -> None:
    engine, config = database
    _upgrade_previous(config)
    command.upgrade(config, REVISION)
    with pytest.raises(RuntimeError, match="LEGACY_PUBLIC_STORE_REMOVAL_DOWNGRADE_UNSUPPORTED"):
        command.downgrade(config, PREVIOUS)
    assert _legacy_tables(engine) == set()
