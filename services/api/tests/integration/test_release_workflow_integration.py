import hashlib
import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.application.jobs import JobService
from game_predictor_api.application.mobile_releases import MobileReleaseService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameStatus, SymbolStatus
from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.jobs import JobType
from game_predictor_api.domain.mobile_releases import (
    MobileReleaseGameInput,
    MobileReleaseStatus,
)
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.mobile_release_repository import (
    SqlAlchemyMobileReleaseRepository,
)
from game_predictor_api.storage.models import (
    DatasetVersionModel,
    GameModel,
    LayoutModel,
    LayoutPayoutModel,
    RulesVersionModel,
    RulesVersionSymbolModel,
    SymbolModel,
)
from game_predictor_worker.jobs.runtime import JobExecutionResult, LocalJobWorker
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore
from game_predictor_worker.payouts.readiness import PayoutReadinessService
from game_predictor_worker.payouts.store import SqlAlchemyPayoutStore
from game_predictor_worker.releases.contracts import (
    AndroidReleaseArtifact,
    AndroidReleaseBuildSpec,
)
from game_predictor_worker.releases.handler import ReleaseWorkflowHandler
from game_predictor_worker.releases.store import SqlAlchemyReleaseWorkflowStore
from game_predictor_worker.snapshots import (
    ProductionSnapshotArtifactPublisher,
    ProductionSnapshotGenerator,
    SqlAlchemyProductionSnapshotStore,
    validate_snapshot_artifact,
)
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
TEST_DATABASE_NAME = "game_predictor_release_workflow_test"

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)


def _database_url(database_name: str) -> URL:
    return make_url(ApiSettings.from_environment().database_url).set(database=database_name)


def _migration_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config


@pytest.fixture
def isolated_release_workflow_database() -> Iterator[URL]:
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


class _PayoutMustNotRun:
    def __call__(self, *_args: object) -> None:
        raise AssertionError("Complete payouts must be reused by the release workflow.")


class _DeterministicAndroidBuilder:
    def __init__(self, artifact_root: Path) -> None:
        self._artifact_root = artifact_root
        self.calls: list[AndroidReleaseBuildSpec] = []
        self.before_return: Callable[[], None] | None = None

    def build(self, spec: AndroidReleaseBuildSpec) -> AndroidReleaseArtifact:
        self.calls.append(spec)
        snapshot_checksum = spec.snapshot.manifest.snapshot_file_sha256
        apk_path = (
            self._artifact_root
            / "android-releases"
            / spec.release_version
            / "controlled"
            / "app-release.apk"
        )
        apk_path.parent.mkdir(parents=True, exist_ok=True)
        payload = (f"{spec.release_version}\n{spec.version_code}\n{snapshot_checksum}\n").encode()
        apk_path.write_bytes(payload)
        if self.before_return is not None:
            self.before_return()
        return AndroidReleaseArtifact(
            apk_path=apk_path,
            apk_sha256=hashlib.sha256(payload).hexdigest(),
            snapshot_sha256=snapshot_checksum,
        )


def _seed_complete_release_source(session: Session) -> MobileReleaseGameInput:
    game_id = uuid4()
    rules_id = uuid4()
    dataset_id = uuid4()
    symbol_id = uuid4()
    created_at = datetime(2026, 7, 27, 12, tzinfo=UTC)
    session.add(
        GameModel(
            id=game_id,
            code="release-game",
            name="Release game",
            status=GameStatus.ACTIVE,
        )
    )
    session.flush()
    session.add(
        SymbolModel(
            id=symbol_id,
            game_id=game_id,
            mobile_code=1,
            code="one",
            name="One",
            image_path="symbols/one.png",
            is_wildcard=False,
            display_order=0,
            status=SymbolStatus.ACTIVE,
        )
    )
    session.flush()
    session.add(
        RulesVersionModel(
            id=rules_id,
            game_id=game_id,
            version=1,
            rows=1,
            columns=2,
            spin_cost=10,
            status=RulesVersionStatus.PUBLISHED,
            published_at=created_at,
        )
    )
    session.flush()
    session.add(
        RulesVersionSymbolModel(
            rules_version_id=rules_id,
            symbol_id=symbol_id,
            minimum_match_length=2,
            is_active=True,
        )
    )
    session.add(
        DatasetVersionModel(
            id=dataset_id,
            game_id=game_id,
            version=1,
            rows=1,
            columns=2,
            signature_cell_width=2,
            layout_count=2,
            status=DatasetVersionStatus.PUBLISHED,
            generation_seed=39,
            generator_version="release-integration-v1",
            published_at=created_at,
        )
    )
    session.flush()
    session.add_all(
        [
            LayoutModel(
                dataset_version_id=dataset_id,
                sequence_number=1,
                signature="0101",
                cells=[1, 1],
            ),
            LayoutModel(
                dataset_version_id=dataset_id,
                sequence_number=2,
                signature="0101",
                cells=[1, 1],
            ),
        ]
    )
    session.flush()
    session.add_all(
        [
            LayoutPayoutModel(
                dataset_version_id=dataset_id,
                rules_version_id=rules_id,
                sequence_number=sequence_number,
                algorithm_version="payout-v2",
                total_payout=20 + sequence_number,
                audit_path=f"payout-audits/release-{sequence_number}.jsonl",
                calculated_at=created_at,
            )
            for sequence_number in (1, 2)
        ]
    )
    return MobileReleaseGameInput(
        game_id=game_id,
        dataset_version_id=dataset_id,
        rules_version_id=rules_id,
    )


def test_postgres_release_workflow_keeps_previous_release_immutable(
    isolated_release_workflow_database: URL,
    tmp_path: Path,
) -> None:
    command.upgrade(_migration_config(isolated_release_workflow_database), "head")
    engine = create_engine(isolated_release_workflow_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    artifact_root = tmp_path / "artifacts"
    payout_store = SqlAlchemyPayoutStore(session_factory)
    android_builder = _DeterministicAndroidBuilder(artifact_root)
    handler = ReleaseWorkflowHandler(
        SqlAlchemyReleaseWorkflowStore(session_factory),
        _PayoutMustNotRun(),  # type: ignore[arg-type]
        PayoutReadinessService(payout_store),
        ProductionSnapshotArtifactPublisher(
            ProductionSnapshotGenerator(
                SqlAlchemyProductionSnapshotStore(session_factory),
                batch_size=1,
            ),
            artifact_root,
        ),
        android_builder,
        artifact_root,
    )
    worker = LocalJobWorker(
        SqlAlchemyWorkerJobStore(session_factory),
        {JobType.ANDROID_BUILD: handler},
        worker_id="release-integration-worker",
        worker_version="test-v1",
        lease_duration=timedelta(seconds=60),
    )

    try:
        with Session(engine) as session, session.begin():
            source = _seed_complete_release_source(session)

        release_ids = []
        for version in ("m3.4-integration.1", "m3.4-integration.2"):
            with Session(engine, expire_on_commit=False) as session, session.begin():
                service = MobileReleaseService(SqlAlchemyMobileReleaseRepository(session))
                release = service.create_mobile_release(
                    version=version,
                    games=(source,),
                )
                service.start_mobile_release_build(release.id)
                release_ids.append(release.id)

            assert worker.run_once() is JobExecutionResult.COMPLETED

            with Session(engine) as session:
                completed = SqlAlchemyMobileReleaseRepository(session).get_mobile_release(
                    release.id
                )
            assert completed is not None
            assert completed.status is MobileReleaseStatus.READY
            assert completed.snapshot_path is not None
            assert completed.snapshot_checksum is not None
            assert completed.apk_path is not None
            assert completed.apk_checksum is not None

        with Session(engine) as session:
            repository = SqlAlchemyMobileReleaseRepository(session)
            first = repository.get_mobile_release(release_ids[0])
            second = repository.get_mobile_release(release_ids[1])
        assert first is not None
        assert second is not None
        first_snapshot = artifact_root / first.snapshot_path  # type: ignore[arg-type]
        first_apk = artifact_root / first.apk_path  # type: ignore[arg-type]
        first_snapshot_bytes = first_snapshot.read_bytes()
        first_apk_bytes = first_apk.read_bytes()
        assert hashlib.sha256(first_snapshot_bytes).hexdigest() == first.snapshot_checksum
        assert hashlib.sha256(first_apk_bytes).hexdigest() == first.apk_checksum

        assert first.snapshot_path != second.snapshot_path
        assert first.apk_path != second.apk_path
        assert first_snapshot.read_bytes() == first_snapshot_bytes
        assert first_apk.read_bytes() == first_apk_bytes
        assert validate_snapshot_artifact(first_snapshot.parent).manifest.release_version == (
            first.version
        )
        second_snapshot = artifact_root / second.snapshot_path  # type: ignore[arg-type]
        assert validate_snapshot_artifact(second_snapshot.parent).manifest.release_version == (
            second.version
        )

        with Session(engine, expire_on_commit=False) as session, session.begin():
            service = MobileReleaseService(SqlAlchemyMobileReleaseRepository(session))
            cancelled_release = service.create_mobile_release(
                version="m3.4-integration.cancelled",
                games=(source,),
            )
            cancelled_job = service.start_mobile_release_build(cancelled_release.id)

        def request_cancellation() -> None:
            with Session(engine) as session, session.begin():
                JobService(SqlAlchemyJobRepository(session)).cancel_job(cancelled_job.id)

        android_builder.before_return = request_cancellation
        assert worker.run_once() is JobExecutionResult.CANCELLED
        with Session(engine) as session:
            cancelled = SqlAlchemyMobileReleaseRepository(session).get_mobile_release(
                cancelled_release.id
            )
        assert cancelled is not None
        assert cancelled.status is MobileReleaseStatus.FAILED
        assert cancelled.snapshot_path is not None
        assert cancelled.apk_path is None
        assert first_snapshot.read_bytes() == first_snapshot_bytes
        assert first_apk.read_bytes() == first_apk_bytes
        assert len(android_builder.calls) == 3
    finally:
        engine.dispose()
