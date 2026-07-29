from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameStatus
from game_predictor_api.domain.jobs import Job, JobType, create_job
from game_predictor_api.storage.catalog_repository import (
    SqlAlchemyCatalogRepository,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import (
    ImageFileExecutionModel,
    ImageImportJobFileModel,
)
from game_predictor_worker.images.orchestration import (
    ImageStageExecutionResult,
    advance_file_checkpoint,
)
from game_predictor_worker.images.orchestration_store import (
    ImageOrchestrationStoreError,
    SqlAlchemyImageBatchStore,
)
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
TEST_DATABASE_NAME = "game_predictor_image_batch_test"
PIPELINE = "a" * 64
OTHER_PIPELINE = "b" * 64

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)


def _database_url(database_name: str) -> URL:
    return (
        make_url(ApiSettings.from_environment().database_url)
        .set(database=database_name)
        .update_query_dict({"connect_timeout": "3"})
    )


def _migration_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    rendered_url = database_url.render_as_string(hide_password=False).replace("%", "%%")
    config.set_main_option("sqlalchemy.url", rendered_url)
    return config


@pytest.fixture
def isolated_image_batch_database() -> Iterator[URL]:
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


def _image_job(game_id: UUID, pipeline: str, created_at: datetime) -> Job:
    return create_job(
        JobType.IMPORT,
        game_id=game_id,
        input_payload={
            "schema_version": 1,
            "import_kind": "image_directory",
            "pipeline_fingerprint": pipeline,
        },
        created_at=created_at,
    )


def test_image_batch_store_reuses_execution_and_fences_checkpoint(
    isolated_image_batch_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_image_batch_database), "head")
    engine = create_engine(isolated_image_batch_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    image_store = SqlAlchemyImageBatchStore(session_factory)
    worker_store = SqlAlchemyWorkerJobStore(session_factory)
    now = datetime(2026, 7, 29, 18, tzinfo=UTC)

    try:
        with Session(engine, expire_on_commit=False) as session:
            game = CatalogService(SqlAlchemyCatalogRepository(session)).create_game(
                code="image-batch-game",
                name="Image batch game",
                status=GameStatus.ACTIVE,
            )
            repository = SqlAlchemyJobRepository(session)
            first_job = repository.add_job(_image_job(game.id, PIPELINE, now))
            second_job = repository.add_job(
                _image_job(game.id, PIPELINE, now + timedelta(seconds=1))
            )
            changed_job = repository.add_job(
                _image_job(game.id, OTHER_PIPELINE, now + timedelta(seconds=2))
            )
            session.commit()

        first = image_store.register_file(
            first_job.id,
            source_checksum_sha256="1" * 64,
            pipeline_fingerprint=PIPELINE,
            source_relative_path="first/page.jpg",
            order_index=0,
            registered_at=now,
        )
        reused = image_store.register_file(
            second_job.id,
            source_checksum_sha256="1" * 64,
            pipeline_fingerprint=PIPELINE,
            source_relative_path="renamed/page.jpg",
            order_index=0,
            registered_at=now,
        )
        changed = image_store.register_file(
            changed_job.id,
            source_checksum_sha256="1" * 64,
            pipeline_fingerprint=OTHER_PIPELINE,
            source_relative_path="renamed/page.jpg",
            order_index=0,
            registered_at=now,
        )

        assert reused.file_execution_key == first.file_execution_key
        assert changed.file_execution_key != first.file_execution_key
        assert (
            image_store.count_job_files(
                first_job.id,
                pipeline_fingerprint=PIPELINE,
            )
            == 1
        )

        claimed = worker_store.claim_next(
            worker_id="image-worker",
            worker_version="worker-v5",
            lease_duration=timedelta(seconds=60),
            claimed_at=now + timedelta(seconds=2),
        )
        assert claimed is not None
        assert claimed.id == first_job.id
        assert claimed.lease_token is not None

        advanced = advance_file_checkpoint(
            first.checkpoint_payload,
            ImageStageExecutionResult.COMPLETED,
        )
        persisted = image_store.save_file_checkpoint(
            first_job.id,
            lease_token=claimed.lease_token,
            expected_checkpoint=first.checkpoint_payload,
            checkpoint_payload=advanced,
            checkpointed_at=now + timedelta(seconds=3),
        )
        assert persisted.checkpoint_payload["completedStages"] == ["discovery"]

        with pytest.raises(ImageOrchestrationStoreError) as stale:
            image_store.save_file_checkpoint(
                first_job.id,
                lease_token=claimed.lease_token,
                expected_checkpoint=first.checkpoint_payload,
                checkpoint_payload=advanced,
                checkpointed_at=now + timedelta(seconds=4),
            )
        assert stale.value.code == "IMAGE_FILE_CHECKPOINT_STALE"

        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(ImageFileExecutionModel)) == 2
            assert session.scalar(select(func.count()).select_from(ImageImportJobFileModel)) == 3
    finally:
        engine.dispose()
