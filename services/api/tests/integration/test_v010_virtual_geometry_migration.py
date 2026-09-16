from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.image_geometry_v2_repository import (
    SqlAlchemyImageGeometryRolloutRepository,
)
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
PREVIOUS_REVISION = "0081_pipeline_terminal_manifest_v2"
VIRTUAL_GEOMETRY_REVISION = "0082_virtual_geometry_foundation"
TEST_DATABASE_NAME = "game_predictor_v010_geometry_schema_test"

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
def isolated_v010_database() -> Iterator[URL]:
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


def test_v010_virtual_geometry_upgrade_backfill_and_downgrade(
    isolated_v010_database: URL,
) -> None:
    config = _migration_config(isolated_v010_database)
    engine = create_engine(isolated_v010_database, pool_pre_ping=True)
    game_ids = sorted((uuid4(), uuid4(), uuid4()))
    try:
        command.upgrade(config, PREVIOUS_REVISION)
        assert "image_source_geometry_revisions" not in inspect(engine).get_table_names()

        engine.dispose()
        command.upgrade(config, VIRTUAL_GEOMETRY_REVISION)
        schema = inspect(engine)
        assert "image_source_geometry_revisions" in schema.get_table_names()
        assert "image_geometry_rollout_states" in schema.get_table_names()
        assert "coordinate_space" in {
            column["name"] for column in schema.get_columns("source_images")
        }
        assert next(
            column
            for column in schema.get_columns("cell_observations")
            if column["name"] == "crop_relative_path"
        )["nullable"]

        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO games (id, code, name, status, expected_layout_count) "
                    "VALUES (:id, :code, :name, 'draft', 1)"
                ),
                [
                    {"id": game_id, "code": f"v010-{index}", "name": f"Game {index}"}
                    for index, game_id in enumerate(game_ids)
                ],
            )

        with Session(engine) as session:
            repository = SqlAlchemyImageGeometryRolloutRepository(session)
            first = repository.backfill_legacy_states(limit=2)
            session.commit()
            assert first.processed_game_count == 2
            assert first.inserted_state_count == 2
            assert first.has_more is True

            second = repository.backfill_legacy_states(after_game_id=first.last_game_id, limit=2)
            session.commit()
            assert second.processed_game_count == 1
            assert second.inserted_state_count == 1
            assert second.has_more is False
            assert repository.get(game_ids[-1]) is not None

            retry = repository.backfill_legacy_states(limit=2)
            session.commit()
            assert retry.inserted_state_count == 0

        with engine.begin() as connection:
            connection.execute(text("DELETE FROM image_geometry_rollout_states"))
            connection.execute(text("DELETE FROM games WHERE code LIKE 'v010-%'"))

        engine.dispose()
        command.downgrade(config, PREVIOUS_REVISION)
        downgraded = inspect(engine)
        assert "image_source_geometry_revisions" not in downgraded.get_table_names()
        assert "asset_mode" not in {
            column["name"] for column in downgraded.get_columns("cell_observations")
        }
    finally:
        engine.dispose()
