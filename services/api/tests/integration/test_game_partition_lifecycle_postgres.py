from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameStatus
from game_predictor_api.storage.catalog_repository import SqlAlchemyCatalogRepository
from game_predictor_api.storage.database import GameStorageSession
from game_predictor_api.storage.game_data_v2_manifest_v1 import CREATE_TABLES
from game_predictor_api.storage.game_partition_lifecycle import (
    GamePartitionLifecycleKind,
    GamePartitionLifecycleRepository,
)
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
    GameStorageRoutingError,
)
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)


@pytest.fixture
def lifecycle_database() -> Iterator[Engine]:
    name = "game_predictor_task0523_" + uuid4().hex[:12]
    assert re.fullmatch(r"game_predictor_task0523_[0-9a-f]{12}", name)
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
        command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            active = connection.execute(
                text("SELECT count(*) FROM pg_stat_activity WHERE datname=:name"),
                {"name": name},
            ).scalar_one()
            assert active == 0
            connection.exec_driver_sql(f'DROP DATABASE "{name}"')
        maintenance.dispose()


def _insert_game(engine: Engine, game_id: UUID, code: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """INSERT INTO public.games
                (id, code, name, status, expected_layout_count)
                VALUES (:id, :code, :name, 'draft', 500000)"""
            ),
            {"id": game_id, "code": code, "name": code},
        )


def _run_to_done(engine: Engine, game_id: UUID, kind: GamePartitionLifecycleKind) -> None:
    with Session(engine) as session, session.begin():
        receipt = GamePartitionLifecycleRepository(session).start_or_resume(
            game_id=game_id, kind=kind
        )
        operation_id = receipt.operation_id
    for _ in range(len(CREATE_TABLES) + 2):
        with Session(engine) as session, session.begin():
            receipt = GamePartitionLifecycleRepository(session).run_next(operation_id)
        if receipt.status == "done":
            return
    raise AssertionError("lifecycle did not reach done")


def test_staging_retention_routes_v2_by_owner_after_session_restart(
    lifecycle_database: Engine,
) -> None:
    from datetime import UTC, datetime

    from game_predictor_api.domain.jobs import JobStatus, JobType, create_job
    from game_predictor_api.storage.browser_staging_retention_repository import (
        SqlAlchemyBrowserStagingRetentionRepository,
    )
    from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
    from game_predictor_api.storage.models import JobModel

    game_id, upload_id, unused_id = uuid4(), uuid4(), uuid4()
    _insert_game(lifecycle_database, game_id, "retention-routing")
    _run_to_done(lifecycle_database, game_id, GamePartitionLifecycleKind.PROVISION)
    factory = sessionmaker(bind=lifecycle_database, class_=GameStorageSession)
    now = datetime.now(UTC)
    for staging_id in (upload_id, unused_id):
        SqlAlchemyBrowserStagingRetentionRepository(factory).record_ready(
            upload_id=staging_id,
            game_id=game_id,
            display_name="staging",
            manifest_checksum_sha256="a" * 64,
            finalized_at=now,
        )
    with factory.begin() as session:
        job = SqlAlchemyJobRepository(session).add_source_bound_job(
            create_job(
                JobType.VALIDATE,
                game_id=game_id,
                input_payload={
                    "schema_version": 1,
                    "validation_kind": "page_geometry_preflight",
                    "source_selection_id": str(upload_id),
                },
                created_at=now,
            ),
            source_selection_id=upload_id,
        )
        record = session.get(JobModel, job.id)
        assert record is not None
        record.status = JobStatus.FAILED
        record.finished_at = now
    # New repository and sessions, without ambient game_storage_scope.
    repository = SqlAlchemyBrowserStagingRetentionRepository(factory)
    repository.discard_unused(upload_id=upload_id)
    repository.discard_unused(upload_id=unused_id, game_id=game_id)
    with lifecycle_database.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM game_data_v2.browser_selection_retention_states")
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM public.jobs WHERE id=:id"), {"id": job.id}
            ).scalar_one()
            == 0
        )


def test_staging_board_status_reaches_completed_before_symbol_review(
    lifecycle_database: Engine,
) -> None:
    from datetime import UTC, datetime, timedelta

    from game_predictor_api.domain.jobs import JobStatus, JobType, create_job
    from game_predictor_api.storage.browser_staging_retention_repository import (
        SqlAlchemyBrowserStagingRetentionRepository,
    )
    from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
    from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore

    game_id, upload_id = uuid4(), uuid4()
    _insert_game(lifecycle_database, game_id, "board-status")
    _run_to_done(lifecycle_database, game_id, GamePartitionLifecycleKind.PROVISION)
    factory = sessionmaker(bind=lifecycle_database, class_=GameStorageSession)
    now = datetime.now(UTC)
    retention = SqlAlchemyBrowserStagingRetentionRepository(factory)
    retention.record_ready(
        upload_id=upload_id,
        game_id=game_id,
        display_name="staging",
        manifest_checksum_sha256="a" * 64,
        finalized_at=now,
    )
    with factory.begin() as session:
        job = SqlAlchemyJobRepository(session).add_source_bound_job(
            create_job(
                JobType.IMPORT,
                game_id=game_id,
                input_payload={
                    "schema_version": 2,
                    "import_kind": "image_directory",
                    "source_selection_id": str(upload_id),
                    "pipeline_fingerprint": "b" * 64,
                },
                created_at=now,
            ),
            source_selection_id=upload_id,
        )
    retention.record_in_use(
        upload_id=upload_id,
        game_id=game_id,
        job_id=job.id,
        used_at=now,
    )
    assert retention.board_import_status(upload_id=upload_id, game_id=game_id) == "importing"

    claimed = SqlAlchemyWorkerJobStore(factory).claim_next(
        worker_id="test-worker",
        worker_version="test",
        lease_duration=timedelta(minutes=5),
        claimed_at=now,
    )
    assert claimed is not None
    paused = SqlAlchemyWorkerJobStore(factory).pause_for_review(
        claimed.id,
        lease_token=claimed.lease_token,
        paused_at=now + timedelta(seconds=1),
    )

    assert paused.status is JobStatus.WAITING_FOR_REVIEW
    assert retention.board_import_status(upload_id=upload_id, game_id=game_id) == "boards_imported"


def test_restartable_provision_and_delete_keep_other_game_isolated(
    lifecycle_database: Engine,
) -> None:
    first, second = uuid4(), uuid4()
    _insert_game(lifecycle_database, first, "first")
    _insert_game(lifecycle_database, second, "second")
    _run_to_done(lifecycle_database, first, GamePartitionLifecycleKind.PROVISION)
    _run_to_done(lifecycle_database, second, GamePartitionLifecycleKind.PROVISION)

    with Session(lifecycle_database) as session, session.begin():
        resumed = GamePartitionLifecycleRepository(session).start_or_resume(
            game_id=first, kind=GamePartitionLifecycleKind.PROVISION
        )
        assert resumed.status == "done"

    _run_to_done(lifecycle_database, first, GamePartitionLifecycleKind.DELETE)

    with lifecycle_database.connect() as connection:
        games = set(connection.execute(text("SELECT id FROM public.games")).scalars())
        locations = set(
            connection.execute(text("SELECT game_id FROM public.game_storage_locations")).scalars()
        )
        second_partition_count = connection.execute(
            text(
                """SELECT count(DISTINCT child.oid) FROM pg_inherits i
                JOIN pg_class child ON child.oid=i.inhrelid
                JOIN pg_namespace n ON n.oid=child.relnamespace
                WHERE n.nspname='game_data_v2' AND child.relkind = 'r'
                  AND child.relname LIKE :prefix"""
            ),
            {"prefix": f"gpv2_{second.hex[:12]}_%"},
        ).scalar_one()
    assert games == {second}
    assert locations == {second}
    assert second_partition_count == len(CREATE_TABLES)


def test_greenfield_catalog_create_provisions_v2_before_return(
    lifecycle_database: Engine,
) -> None:
    factory = sessionmaker(
        bind=lifecycle_database,
        class_=GameStorageSession,
        expire_on_commit=False,
    )

    with factory() as session:
        game = CatalogService(
            SqlAlchemyCatalogRepository(session, GameStorageRouter())
        ).create_game(
            code="greenfield-game",
            name="Greenfield game",
            status=GameStatus.DRAFT,
            expected_layout_count=500_000,
        )

    assert game.storage_schema == "game_data_v2"
    assert game.storage_generation == 2
    assert game.storage_status == "active"
    assert game.storage_write_available is True
    with lifecycle_database.connect() as connection:
        location = connection.execute(
            text(
                """SELECT store_schema, generation, status
                FROM public.game_storage_locations WHERE game_id=:game_id"""
            ),
            {"game_id": game.id},
        ).one()
        partition_count = connection.scalar(
            text(
                """SELECT count(*) FROM pg_inherits i
                JOIN pg_class child ON child.oid=i.inhrelid
                JOIN pg_namespace n ON n.oid=child.relnamespace
                WHERE n.nspname='game_data_v2' AND child.relkind='r'
                  AND child.relname LIKE :prefix"""
            ),
            {"prefix": f"gpv2_{game.id.hex[:12]}_%"},
        )
        geometry_state = connection.scalar(
            text(
                """SELECT count(*) FROM game_data_v2.image_geometry_rollout_states
                WHERE game_id=:game_id"""
            ),
            {"game_id": game.id},
        )
        legacy_state = connection.scalar(
            text(
                """SELECT count(*) FROM public.image_geometry_rollout_states
                WHERE game_id=:game_id"""
            ),
            {"game_id": game.id},
        )
    assert tuple(map(str, location)) == ("game_data_v2", "2", "active")
    assert partition_count == len(CREATE_TABLES)
    assert geometry_state == 1
    assert legacy_state == 0


def test_missing_registry_fails_closed_without_public_fallback(
    lifecycle_database: Engine,
) -> None:
    game_id = uuid4()
    _insert_game(lifecycle_database, game_id, "missing-registry")
    factory = sessionmaker(
        bind=lifecycle_database,
        class_=GameStorageSession,
        expire_on_commit=False,
    )

    with factory() as session:
        described = GameStorageRouter().describe(session, game_id)
        assert described.status.value == "blocked"
        with pytest.raises(GameStorageRoutingError) as raised:
            GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)

    assert raised.value.code == "GAME_STORAGE_LOCATION_MISSING"
