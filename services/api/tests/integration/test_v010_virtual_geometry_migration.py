from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, make_url

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
    return make_url(ApiSettings.from_environment().owner_database_url).set(database=database_name)


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


def test_v010_virtual_geometry_upgrade_defaults_and_downgrade(
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

        # The 0082 rollout table starts a game on the 0082-era defaults. The
        # repository's bounded backfill (SqlAlchemyImageGeometryRolloutRepository
        # .backfill_legacy_states) is no longer run on this schema: since D-467
        # (TASK-0790, 102a6c8f) it writes ``structured_lattice_v3`` /
        # ``virtual_default``, which the 0082 CHECK does not admit (0095 adds
        # the mode), and since D-448 (migration 0125) the table exists only per
        # game in ``game_data_v2``. A new game's rollout state is created by the
        # partition lifecycle; see test_game_partition_lifecycle_postgres.py::
        # test_greenfield_catalog_create_provisions_v2_before_return.
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
            connection.execute(
                text(
                    "INSERT INTO image_geometry_rollout_states (game_id, updated_by) "
                    "VALUES (:game_id, 'test')"
                ),
                [{"game_id": game_id} for game_id in game_ids],
            )
            states = connection.execute(
                text(
                    "SELECT geometry_mode, cell_asset_mode, revision, backfill_status "
                    "FROM image_geometry_rollout_states ORDER BY game_id"
                )
            ).all()
            assert [tuple(state) for state in states] == [
                ("legacy", "legacy_files", 0, "not_started")
            ] * len(game_ids)

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
