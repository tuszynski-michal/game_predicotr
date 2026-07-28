import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.application.jobs import JobService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameStatus, SymbolStatus
from game_predictor_api.domain.jobs import (
    Job,
    JobConflictError,
    JobStatus,
    JobType,
    create_job,
)
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.storage.catalog_repository import (
    SqlAlchemyCatalogRepository,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import (
    LayoutImportNormalizedRowModel,
    LayoutImportRowModel,
    RulesVersionModel,
    RulesVersionSymbolModel,
)
from game_predictor_worker.imports.contracts import StagedLayoutImportRow
from game_predictor_worker.imports.normalization import normalize_layout_import_row
from game_predictor_worker.imports.store import SqlAlchemyLayoutImportStagingStore
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore
from sqlalchemy import create_engine, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
TEST_DATABASE_NAME = "game_predictor_worker_jobs_test"

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)


def _database_url(database_name: str) -> URL:
    return make_url(ApiSettings.from_environment().database_url).set(database=database_name)


def _migration_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    rendered_url = database_url.render_as_string(hide_password=False).replace(
        "%",
        "%%",
    )
    config.set_main_option("sqlalchemy.url", rendered_url)
    return config


@pytest.fixture
def isolated_worker_database() -> Iterator[URL]:
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


def test_worker_store_fences_cancellation_resume_and_concurrent_claims(
    isolated_worker_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_worker_database), "head")
    engine = create_engine(isolated_worker_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    store = SqlAlchemyWorkerJobStore(session_factory)
    now = datetime(2026, 7, 27, 17, tzinfo=UTC)
    lease_duration = timedelta(seconds=60)

    try:
        with Session(engine, expire_on_commit=False) as session:
            catalog = CatalogService(SqlAlchemyCatalogRepository(session))
            game = catalog.create_game(
                code="worker-game",
                name="Worker game",
                status=GameStatus.ACTIVE,
            )
            jobs = JobService(SqlAlchemyJobRepository(session))
            cancellable = jobs.create_job(
                JobType.VALIDATE,
                game_id=game.id,
                input_payload={
                    "schema_version": 1,
                    "dataset_version_id": "11111111-1111-4111-8111-111111111111",
                },
            )
            session.commit()

        claimed = store.claim_next(
            worker_id="worker-a",
            worker_version="worker-v1",
            lease_duration=lease_duration,
            claimed_at=now,
        )
        assert claimed is not None
        assert claimed.id == cancellable.id
        assert claimed.attempt_count == 1
        assert claimed.lease_token is not None
        assert (
            store.claim_next(
                worker_id="worker-b",
                worker_version="worker-v1",
                lease_duration=lease_duration,
                claimed_at=now,
            )
            is None
        )

        first_checkpoint = store.checkpoint(
            claimed.id,
            lease_token=claimed.lease_token,
            lease_duration=lease_duration,
            checkpoint_payload={"schema_version": 1, "cursor": 10},
            stage="validating",
            current=10,
            total=100,
            success_count=10,
            failure_count=0,
            review_count=0,
            checkpointed_at=now + timedelta(seconds=10),
        )
        assert first_checkpoint.progress_current == 10

        with Session(engine, expire_on_commit=False) as session:
            jobs = JobService(SqlAlchemyJobRepository(session))
            jobs.cancel_job(claimed.id)
            session.commit()

        cancelled = store.checkpoint(
            claimed.id,
            lease_token=claimed.lease_token,
            lease_duration=lease_duration,
            checkpoint_payload={"schema_version": 1, "cursor": 20},
            stage="validating",
            current=20,
            total=100,
            success_count=20,
            failure_count=0,
            review_count=0,
            checkpointed_at=now + timedelta(seconds=20),
        )
        assert cancelled.status is JobStatus.CANCELLED
        assert cancelled.progress_current == 20

        with Session(engine, expire_on_commit=False) as session:
            jobs = JobService(SqlAlchemyJobRepository(session))
            resumable = jobs.create_job(
                JobType.VALIDATE,
                game_id=game.id,
                input_payload={
                    "schema_version": 1,
                    "dataset_version_id": "22222222-2222-4222-8222-222222222222",
                },
            )
            session.commit()

        first_attempt = store.claim_next(
            worker_id="worker-a",
            worker_version="worker-v1",
            lease_duration=lease_duration,
            claimed_at=now + timedelta(minutes=2),
        )
        assert first_attempt is not None
        assert first_attempt.id == resumable.id
        assert first_attempt.lease_token is not None
        first_token = first_attempt.lease_token
        store.checkpoint(
            resumable.id,
            lease_token=first_token,
            lease_duration=lease_duration,
            checkpoint_payload={"schema_version": 1, "cursor": 25},
            stage="validating",
            current=25,
            total=100,
            success_count=25,
            failure_count=0,
            review_count=0,
            checkpointed_at=now + timedelta(minutes=2, seconds=10),
        )
        recovered = store.recover_expired(recovered_at=now + timedelta(minutes=3, seconds=11))
        assert recovered is not None
        assert recovered.id == resumable.id
        assert recovered.status is JobStatus.CREATED
        assert recovered.checkpoint_payload == {
            "schema_version": 1,
            "cursor": 25,
        }

        with pytest.raises(JobConflictError) as stale_worker:
            store.heartbeat(
                resumable.id,
                lease_token=first_token,
                lease_duration=lease_duration,
                heartbeat_at=now + timedelta(minutes=3, seconds=12),
            )
        assert stale_worker.value.code == "JOB_LEASE_LOST"

        second_attempt = store.claim_next(
            worker_id="worker-b",
            worker_version="worker-v1",
            lease_duration=lease_duration,
            claimed_at=now + timedelta(minutes=3, seconds=12),
        )
        assert second_attempt is not None
        assert second_attempt.id == resumable.id
        assert second_attempt.attempt_count == 2
        assert second_attempt.progress_current == 25
        assert second_attempt.lease_token is not None
        store.complete(
            resumable.id,
            lease_token=second_attempt.lease_token,
            completed_at=now + timedelta(minutes=3, seconds=20),
        )

        with Session(engine, expire_on_commit=False) as session:
            jobs = JobService(SqlAlchemyJobRepository(session))
            for dataset_id in (
                "33333333-3333-4333-8333-333333333333",
                "44444444-4444-4444-8444-444444444444",
            ):
                jobs.create_job(
                    JobType.VALIDATE,
                    game_id=game.id,
                    input_payload={
                        "schema_version": 1,
                        "dataset_version_id": dataset_id,
                    },
                )
            session.commit()

        def concurrent_claim(worker_id: str) -> Job | None:
            return store.claim_next(
                worker_id=worker_id,
                worker_version="worker-v1",
                lease_duration=lease_duration,
                claimed_at=now + timedelta(minutes=4),
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            concurrent_results = list(executor.map(concurrent_claim, ("worker-c", "worker-d")))
        winners = [result for result in concurrent_results if result is not None]
        assert len(winners) == 1
        winner = winners[0]
        assert winner.lease_token is not None
        store.complete(
            winner.id,
            lease_token=winner.lease_token,
            completed_at=now + timedelta(minutes=4, seconds=10),
        )
    finally:
        engine.dispose()


def test_layout_import_staging_upsert_is_idempotent_on_postgres(
    isolated_worker_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_worker_database), "head")
    engine = create_engine(isolated_worker_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)

    try:
        with Session(engine, expire_on_commit=False) as session:
            game = CatalogService(SqlAlchemyCatalogRepository(session)).create_game(
                code="import-game",
                name="Import game",
                status=GameStatus.ACTIVE,
            )
            job = create_job(
                JobType.IMPORT,
                game_id=game.id,
                input_payload={
                    "schema_version": 1,
                    "import_kind": "layout_file",
                    "source_path": "layouts.jsonl",
                    "source_checksum": "a" * 64,
                    "source_size_bytes": 100,
                    "file_format": "jsonl",
                    "contract_version": 1,
                },
            )
            SqlAlchemyJobRepository(session).add_job(job)
            session.commit()

        store = SqlAlchemyLayoutImportStagingStore(session_factory)
        first = StagedLayoutImportRow(
            line_number=1,
            byte_offset_end=50,
            sequence_number=1,
            cells=(1, 2, 3),
            error_code=None,
            error_message=None,
        )
        corrected = StagedLayoutImportRow(
            line_number=1,
            byte_offset_end=50,
            sequence_number=2,
            cells=(3, 2, 1),
            error_code=None,
            error_message=None,
        )
        invalid = StagedLayoutImportRow(
            line_number=2,
            byte_offset_end=100,
            sequence_number=None,
            cells=None,
            error_code="import_record_invalid",
            error_message="Line 2 is invalid.",
        )

        store.upsert_rows(job.id, (first, invalid))
        store.upsert_rows(job.id, (corrected, invalid))

        with Session(engine) as session:
            rows = session.scalars(
                select(LayoutImportRowModel)
                .where(LayoutImportRowModel.job_id == job.id)
                .order_by(LayoutImportRowModel.line_number)
            ).all()
        assert len(rows) == 2
        assert rows[0].sequence_number == 2
        assert rows[0].cells == [3, 2, 1]
        assert rows[1].error_code == "import_record_invalid"
    finally:
        engine.dispose()


def test_layout_import_normalization_uses_published_rules_and_is_idempotent(
    isolated_worker_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_worker_database), "head")
    engine = create_engine(isolated_worker_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)

    try:
        with Session(engine, expire_on_commit=False) as session:
            catalog = CatalogService(SqlAlchemyCatalogRepository(session))
            game = catalog.create_game(
                code="normalized-import-game",
                name="Normalized import game",
                status=GameStatus.ACTIVE,
            )
            first_symbol = catalog.create_symbol(
                game.id,
                mobile_code=1,
                code="S1",
                name="S1",
                image_path=None,
                is_wildcard=False,
                display_order=1,
                status=SymbolStatus.ACTIVE,
            )
            second_symbol = catalog.create_symbol(
                game.id,
                mobile_code=12,
                code="S12",
                name="S12",
                image_path=None,
                is_wildcard=False,
                display_order=2,
                status=SymbolStatus.ACTIVE,
            )
            rules = RulesVersionModel(
                game_id=game.id,
                version=1,
                rows=2,
                columns=2,
                spin_cost=10,
                status=RulesVersionStatus.PUBLISHED,
                published_at=datetime.now(UTC),
            )
            session.add(rules)
            session.flush()
            session.add_all(
                [
                    RulesVersionSymbolModel(
                        rules_version_id=rules.id,
                        symbol_id=first_symbol.id,
                        minimum_match_length=2,
                        is_active=True,
                    ),
                    RulesVersionSymbolModel(
                        rules_version_id=rules.id,
                        symbol_id=second_symbol.id,
                        minimum_match_length=2,
                        is_active=True,
                    ),
                ]
            )
            import_job = replace(
                create_job(
                    JobType.IMPORT,
                    game_id=game.id,
                    input_payload={
                        "schema_version": 1,
                        "import_kind": "layout_file",
                        "source_path": "normalized.jsonl",
                        "source_checksum": "b" * 64,
                        "source_size_bytes": 100,
                        "file_format": "jsonl",
                        "contract_version": 1,
                    },
                ),
                status=JobStatus.COMPLETED,
                finished_at=datetime.now(UTC),
            )
            validation_job = create_job(
                JobType.VALIDATE,
                game_id=game.id,
                input_payload={
                    "schema_version": 1,
                    "validation_kind": "layout_import",
                    "import_job_id": str(import_job.id),
                    "rules_version_id": str(rules.id),
                },
            )
            repository = SqlAlchemyJobRepository(session)
            repository.add_job(import_job)
            repository.add_job(validation_job)
            session.commit()

        store = SqlAlchemyLayoutImportStagingStore(session_factory)
        store.upsert_rows(
            import_job.id,
            (
                StagedLayoutImportRow(1, 50, 1, (1, 12, 1, 12), None, None),
                StagedLayoutImportRow(2, 100, 2, (1, 99, 1, 12), None, None),
            ),
        )
        source = store.load_normalization_source(
            validation_job_id=validation_job.id,
            game_id=game.id,
            import_job_id=import_job.id,
            rules_version_id=rules.id,
        )
        assert source.signature_cell_width == 2
        assert source.allowed_mobile_codes == frozenset({1, 12})
        raw_rows = store.fetch_raw_rows(
            import_job.id,
            after_line_number=0,
            limit=100,
        )
        normalized = tuple(normalize_layout_import_row(row, source) for row in raw_rows)
        store.upsert_normalized_rows(validation_job.id, source, normalized)
        store.upsert_normalized_rows(validation_job.id, source, normalized)

        with Session(engine) as session:
            records = session.scalars(
                select(LayoutImportNormalizedRowModel)
                .where(LayoutImportNormalizedRowModel.validation_job_id == validation_job.id)
                .order_by(LayoutImportNormalizedRowModel.line_number)
            ).all()
        assert len(records) == 2
        assert records[0].signature == "01120112"
        assert records[1].error_code == "import_symbol_not_in_rules"
        assert records[1].cells == [1, 99, 1, 12]
    finally:
        engine.dispose()
