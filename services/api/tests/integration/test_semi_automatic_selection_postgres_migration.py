from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL, make_url

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
PREVIOUS_REVISION = "0086_partial_page_geometry_overrides"
MIGRATION_REVISION = "0087_semi_automatic_image_selection"
TEST_DATABASE_NAME = "game_predictor_semi_automatic_selection_schema_test"

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)


def _database_url(database_name: str) -> URL:
    return make_url(ApiSettings.from_environment().database_url).set(database=database_name)


def _migration_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    rendered_url = database_url.render_as_string(hide_password=False).replace("%", "%%")
    config.set_main_option("sqlalchemy.url", rendered_url)
    return config


@pytest.fixture
def isolated_database() -> Iterator[URL]:
    maintenance_engine = create_engine(
        _database_url("postgres"), isolation_level="AUTOCOMMIT", pool_pre_ping=True
    )
    database_url = _database_url(TEST_DATABASE_NAME)
    identifier = f'"{TEST_DATABASE_NAME}"'
    try:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
            connection.exec_driver_sql(f"CREATE DATABASE {identifier}")
        yield database_url
    finally:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
        maintenance_engine.dispose()


def test_upgrade_and_downgrade_global_selection_tables(isolated_database: URL) -> None:
    config = _migration_config(isolated_database)
    engine = create_engine(isolated_database, pool_pre_ping=True)
    try:
        command.upgrade(config, PREVIOUS_REVISION)
        assert "semi_automatic_image_selection_runs" not in inspect(engine).get_table_names()

        engine.dispose()
        command.upgrade(config, MIGRATION_REVISION)
        schema = inspect(engine)
        assert "semi_automatic_image_selection_runs" in schema.get_table_names()
        assert "semi_automatic_image_selection_ranges" in schema.get_table_names()
        assert {column["name"] for column in schema.get_columns("jobs")} >= {
            "job_type",
            "execution_slot",
        }

        engine.dispose()
        command.downgrade(config, PREVIOUS_REVISION)
        downgraded = inspect(engine)
        assert "semi_automatic_image_selection_runs" not in downgraded.get_table_names()
        assert "semi_automatic_image_selection_ranges" not in downgraded.get_table_names()
    finally:
        engine.dispose()
