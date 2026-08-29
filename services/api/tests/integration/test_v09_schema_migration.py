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
PREVIOUS_REVISION = "0072_verified_training_cohort_cells"
V09_REVISION = "0073_topology_geometry_crop_provenance"
TEST_DATABASE_NAME = "game_predictor_v09_schema_test"

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
def isolated_v09_database() -> Iterator[URL]:
    maintenance_engine = create_engine(
        _database_url("postgres"),
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
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


def test_v09_schema_upgrade_downgrade_upgrade_cycle(isolated_v09_database: URL) -> None:
    config = _migration_config(isolated_v09_database)
    engine = create_engine(isolated_v09_database, pool_pre_ping=True)
    try:
        command.upgrade(config, PREVIOUS_REVISION)
        before = inspect(engine)
        assert "board_topology_rules_version_id" not in {
            column["name"] for column in before.get_columns("games")
        }

        engine.dispose()
        command.upgrade(config, V09_REVISION)
        after = inspect(engine)
        assert "image_board_geometry_review_events" in after.get_table_names()
        assert "board_topology_rules_version_id" in {
            column["name"] for column in after.get_columns("games")
        }
        assert "approved_geometry_revision" in {
            column["name"] for column in after.get_columns("recognized_boards")
        }
        assert "quality_issue" in {
            column["name"] for column in after.get_columns("image_symbol_review_cells")
        }
        cell_checks = {
            constraint["name"]: str(constraint["sqltext"]).lower()
            for constraint in after.get_check_constraints("image_symbol_review_cells")
        }
        assert (
            "approved_crop_sample_id is not null"
            in cell_checks["ck_image_symbol_review_cells_approved_crop_identity"]
        )
        assert (
            "quality_issue is not null"
            in cell_checks["ck_image_symbol_review_cells_approved_symbol"]
        )
        board_checks = {
            constraint["name"]: str(constraint["sqltext"]).lower()
            for constraint in after.get_check_constraints("recognized_boards")
        }
        assert "grid_rows is not null" in board_checks["ck_recognized_boards_grid_topology"]

        engine.dispose()
        command.downgrade(config, PREVIOUS_REVISION)
        downgraded = inspect(engine)
        assert "image_board_geometry_review_events" not in downgraded.get_table_names()
        assert "quality_issue" not in {
            column["name"] for column in downgraded.get_columns("image_symbol_review_cells")
        }

        engine.dispose()
        command.upgrade(config, V09_REVISION)
        assert "image_board_geometry_review_events" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
