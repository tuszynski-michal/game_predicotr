import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
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
from game_predictor_api.domain.jobs import JobExecutionSlot, JobType
from game_predictor_api.storage.catalog_repository import SqlAlchemyCatalogRepository
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.image_selection_repository import (
    SqlAlchemyImageSelectionRepository,
)
from game_predictor_worker.images.selection.contracts import (
    CandidateDecision,
    CandidateResult,
    ImageQualityMetrics,
    ImageSelectionSource,
    SelectionGroupResult,
    SelectionGroupStatus,
    SequenceRange,
)
from game_predictor_worker.images.selection.job import SqlAlchemyImageSelectionJobStore
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore
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


def test_final_projection_reassigns_selected_ranges_atomically(
    isolated_image_selection_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_image_selection_database), "head")
    engine = create_engine(isolated_image_selection_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    now = datetime(2026, 8, 14, 10, tzinfo=UTC)

    def group(order: int, start: int) -> SelectionGroupResult:
        recognized_range = SequenceRange(start, start + 8, 0.99)
        source = ImageSelectionSource(
            order_index=order,
            relative_path=f"source/{order}.jpg",
            stored_relative_path=f"{order:08d}.jpg",
            checksum_sha256=format(order + 1, "x") * 64,
            size_bytes=1024,
        )
        candidate = CandidateResult(
            source=source,
            decision=CandidateDecision.ELIGIBLE,
            quality=ImageQualityMetrics(*(0.9 for _ in range(8))),
            recognized_range=recognized_range,
            reason_codes=(),
            width=1080,
            height=1920,
        )
        return SelectionGroupResult(
            group_order=order,
            source_count=1,
            range=recognized_range,
            fingerprint_sha256=format(order, "x") * 64,
            board_count_consensus=9,
            status=SelectionGroupStatus.AUTO_SELECTED,
            selected_candidate=candidate,
            top_candidates=(candidate,),
        )

    try:
        with session_factory() as session:
            game = CatalogService(SqlAlchemyCatalogRepository(session)).create_game(
                code="atomic-projection-test",
                name="Atomic projection test",
                status=GameStatus.DRAFT,
            )
            run, created = ImageSelectionService(
                SqlAlchemyImageSelectionRepository(session)
            ).create_run(
                game_id=game.id,
                source_selection_id=uuid4(),
                input_manifest_sha256="1" * 64,
                selector_fingerprint="2" * 64,
                first_sequence_number=1,
                last_sequence_number=18,
            )
            session.commit()
        assert created is True

        claimed = SqlAlchemyWorkerJobStore(session_factory).claim_next(
            worker_id="projection-test-worker",
            worker_version="v0.6.13-test",
            lease_duration=timedelta(minutes=1),
            claimed_at=now,
            allowed_job_types=frozenset({JobType.IMAGE_SELECTION}),
            execution_slot=JobExecutionSlot.IMAGE_SELECTION,
        )
        assert claimed is not None and claimed.lease_token is not None
        store = SqlAlchemyImageSelectionJobStore(session_factory)
        store.persist_groups(
            job_id=run.job.id,
            run_id=run.id,
            lease_token=claimed.lease_token,
            groups=(group(0, 10), group(1, 1)),
            group_sources={},
            persisted_at=now,
        )

        store.persist_reconciled_groups(
            job_id=run.job.id,
            run_id=run.id,
            lease_token=claimed.lease_token,
            groups=(group(0, 1), group(1, 10)),
            persisted_at=now + timedelta(seconds=1),
        )

        persisted = store.load_groups(run.id)
        assert [(item.range.start, item.range.end) for item in persisted if item.range] == [
            (1, 9),
            (10, 18),
        ]
        assert all(item.status is SelectionGroupStatus.AUTO_SELECTED for item in persisted)
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
