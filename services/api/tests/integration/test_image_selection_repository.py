import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.application.image_selections import ImageSelectionService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameStatus
from game_predictor_api.domain.image_selections import (
    ImageSelectionGroup,
    ImageSelectionGroupStatus,
)
from game_predictor_api.storage.catalog_repository import SqlAlchemyCatalogRepository
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.image_selection_repository import (
    SqlAlchemyImageSelectionRepository,
)
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL, make_url

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
TEST_DATABASE_NAME = "game_predictor_image_selection_test"

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)

DERIVED_RECOVERY_REVISION = "0042_image_selection_derived_recovery"
REVIEW_QUEUES_REVISION = "0041_image_selection_review_queues"


def _database_url(database_name: str) -> URL:
    return make_url(ApiSettings.from_environment().database_url).set(database=database_name)


def _migration_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    rendered_url = database_url.render_as_string(hide_password=False).replace("%", "%%")
    config.set_main_option("sqlalchemy.url", rendered_url)
    return config


@pytest.fixture
def isolated_image_selection_database() -> Iterator[URL]:
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


def test_create_run_persists_job_before_foreign_key_dependent_run(
    isolated_image_selection_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_image_selection_database), "head")
    engine = create_engine(isolated_image_selection_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)

    try:
        with session_factory() as session:
            game = CatalogService(SqlAlchemyCatalogRepository(session)).create_game(
                code="image-selection-test",
                name="Image selection test",
                status=GameStatus.DRAFT,
            )
            service = ImageSelectionService(SqlAlchemyImageSelectionRepository(session))
            source_selection_id = uuid4()

            created_run, created = service.create_run(
                game_id=game.id,
                source_selection_id=source_selection_id,
                input_manifest_sha256="1" * 64,
                selector_fingerprint="2" * 64,
            )
            versioned_run, versioned_created = service.create_run(
                game_id=game.id,
                source_selection_id=source_selection_id,
                input_manifest_sha256="1" * 64,
                selector_fingerprint="3" * 64,
            )
            session.commit()

            persisted_run = service.get_run(created_run.id)
            persisted_versioned_run = service.get_run(versioned_run.id)
            now = datetime.now(UTC)
            group = SqlAlchemyImageSelectionRepository(session).add_group(
                ImageSelectionGroup(
                    id=uuid4(),
                    run_id=created_run.id,
                    group_order=0,
                    range_start=None,
                    range_end=None,
                    fingerprint_sha256=None,
                    board_count_consensus=None,
                    status=ImageSelectionGroupStatus.MANUAL_REQUIRED,
                    selected_candidate_id=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            missing = service.continue_without_image(
                run_id=created_run.id,
                group_id=group.id,
                idempotency_key=uuid4(),
                range_start=None,
                range_end=None,
            )
            session.commit()
            persisted_missing = SqlAlchemyImageSelectionRepository(session).get_group(
                run_id=created_run.id,
                group_id=group.id,
            )

        assert created is True
        assert versioned_created is True
        assert persisted_run.id == created_run.id
        assert persisted_run.job.id == created_run.job.id
        assert persisted_versioned_run.source_selection_id == source_selection_id
        assert persisted_versioned_run.id != persisted_run.id
        assert missing.decision.candidate_id is None
        assert persisted_missing is not None
        assert persisted_missing.status is ImageSelectionGroupStatus.MISSING_IMAGE
        assert persisted_missing.range_start is None
        assert persisted_missing.range_end is None
    finally:
        engine.dispose()


def test_derived_recovery_migration_round_trip(
    isolated_image_selection_database: URL,
) -> None:
    config = _migration_config(isolated_image_selection_database)
    command.upgrade(config, REVIEW_QUEUES_REVISION)

    command.upgrade(config, DERIVED_RECOVERY_REVISION)
    upgraded_engine = create_engine(isolated_image_selection_database, pool_pre_ping=True)
    try:
        run_columns = {
            column["name"]
            for column in inspect(upgraded_engine).get_columns("image_selection_runs")
        }
        group_columns = {
            column["name"]
            for column in inspect(upgraded_engine).get_columns("image_selection_groups")
        }
    finally:
        upgraded_engine.dispose()
    assert {"execution_mode", "source_run_id", "source_snapshot_sha256"} <= run_columns
    assert "origin_group_id" in group_columns

    command.downgrade(config, REVIEW_QUEUES_REVISION)
    downgraded_engine = create_engine(isolated_image_selection_database, pool_pre_ping=True)
    try:
        run_columns = {
            column["name"]
            for column in inspect(downgraded_engine).get_columns("image_selection_runs")
        }
        group_columns = {
            column["name"]
            for column in inspect(downgraded_engine).get_columns("image_selection_groups")
        }
    finally:
        downgraded_engine.dispose()
    assert not {"execution_mode", "source_run_id", "source_snapshot_sha256"} & run_columns
    assert "origin_group_id" not in group_columns
