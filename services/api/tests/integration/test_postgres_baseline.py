import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from game_predictor_api.config import ApiSettings
from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.engine import URL, make_url

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
HEAD_REVISION = "0005_symbol_payouts"
TEST_DATABASE_NAME = "game_predictor_baseline_test"

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)


def _quoted_identifier(identifier: str) -> str:
    if identifier != TEST_DATABASE_NAME:
        raise ValueError("Only the dedicated baseline test database may be managed.")
    return f'"{identifier}"'


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
        _database_url("postgres"),
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    test_database_url = _database_url(TEST_DATABASE_NAME)
    identifier = _quoted_identifier(TEST_DATABASE_NAME)

    try:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
            connection.exec_driver_sql(f"CREATE DATABASE {identifier}")
        yield test_database_url
    finally:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
        maintenance_engine.dispose()


def _current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def test_upgrade_downgrade_upgrade_cycle_on_postgres(isolated_database: URL) -> None:
    config = _migration_config(isolated_database)
    engine = create_engine(isolated_database, pool_pre_ping=True)

    try:
        command.upgrade(config, "head")
        assert _current_revision(engine) == HEAD_REVISION
        assert set(inspect(engine).get_table_names()) == {
            "alembic_version",
            "games",
            "paylines",
            "payout_rules",
            "rules_versions",
            "rules_version_symbols",
            "symbols",
        }

        engine.dispose()
        command.downgrade(config, "base")
        assert _current_revision(engine) is None
        assert set(inspect(engine).get_table_names()) <= {"alembic_version"}

        engine.dispose()
        command.upgrade(config, "head")
        assert _current_revision(engine) == HEAD_REVISION
        assert set(inspect(engine).get_table_names()) == {
            "alembic_version",
            "games",
            "paylines",
            "payout_rules",
            "rules_versions",
            "rules_version_symbols",
            "symbols",
        }
    finally:
        engine.dispose()
