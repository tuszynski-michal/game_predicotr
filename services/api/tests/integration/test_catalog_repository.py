import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import (
    CatalogConflictError,
    GameStatus,
    SymbolStatus,
)
from game_predictor_api.storage.catalog_repository import (
    SqlAlchemyCatalogRepository,
)
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
TEST_DATABASE_NAME = "game_predictor_catalog_test"

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
def isolated_catalog_database() -> Iterator[URL]:
    maintenance_engine = create_engine(
        _database_url("postgres"),
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    test_database_url = _database_url(TEST_DATABASE_NAME)
    identifier = f'"{TEST_DATABASE_NAME}"'

    try:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
            connection.exec_driver_sql(f"CREATE DATABASE {identifier}")
        yield test_database_url
    finally:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
        maintenance_engine.dispose()


def test_catalog_repository_uses_real_constraints(
    isolated_catalog_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_catalog_database), "head")
    engine = create_engine(isolated_catalog_database, pool_pre_ping=True)

    try:
        assert set(inspect(engine).get_table_names()) == {
            "alembic_version",
            "games",
            "symbols",
        }

        with Session(engine, expire_on_commit=False) as session:
            service = CatalogService(SqlAlchemyCatalogRepository(session))
            game = service.create_game(
                code="game-1",
                name="Game 1",
                status=GameStatus.ACTIVE,
            )
            first = service.create_symbol(
                game.id,
                mobile_code=1,
                code="S1",
                name="Symbol 1",
                image_path="symbols/game-1/s1.png",
                is_wildcard=False,
                display_order=20,
                status=SymbolStatus.ACTIVE,
            )
            second = service.create_symbol(
                game.id,
                mobile_code=2,
                code="WILD",
                name="Wildcard",
                image_path=None,
                is_wildcard=True,
                display_order=10,
                status=SymbolStatus.ACTIVE,
            )
            session.commit()

            assert [symbol.id for symbol in service.list_symbols(game.id)] == [
                second.id,
                first.id,
            ]
            assert (
                service.archive_symbol(game.id, first.id).status
                is SymbolStatus.ARCHIVED
            )
            session.commit()

        with Session(engine, expire_on_commit=False) as session:
            service = CatalogService(SqlAlchemyCatalogRepository(session))
            with pytest.raises(CatalogConflictError) as error:
                service.create_game(
                    code="game-1",
                    name="Duplicate",
                    status=GameStatus.DRAFT,
                )
            assert error.value.code == "GAME_CODE_ALREADY_EXISTS"
            session.rollback()

            with pytest.raises(CatalogConflictError) as error:
                service.create_symbol(
                    game.id,
                    mobile_code=3,
                    code="S1",
                    name="Duplicate code",
                    image_path=None,
                    is_wildcard=False,
                    display_order=30,
                    status=SymbolStatus.ACTIVE,
                )
            assert error.value.code == "SYMBOL_CODE_ALREADY_EXISTS"
            session.rollback()

            with pytest.raises(CatalogConflictError) as error:
                service.create_symbol(
                    game.id,
                    mobile_code=2,
                    code="S2",
                    name="Duplicate mobile code",
                    image_path=None,
                    is_wildcard=False,
                    display_order=30,
                    status=SymbolStatus.ACTIVE,
                )
            assert error.value.code == "SYMBOL_MOBILE_CODE_ALREADY_EXISTS"
    finally:
        engine.dispose()
