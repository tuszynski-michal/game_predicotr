"""Build a small production-format M3.4 APK for the in-place device update."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
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
from game_predictor_worker.releases.android import PowerShellAndroidReleaseBuilder
from game_predictor_worker.releases.handler import ReleaseWorkflowHandler
from game_predictor_worker.releases.store import SqlAlchemyReleaseWorkflowStore
from game_predictor_worker.snapshots import (
    ProductionSnapshotArtifactPublisher,
    ProductionSnapshotGenerator,
    SqlAlchemyProductionSnapshotStore,
)
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
CANDIDATE_DATABASE_NAME = "game_predictor_m34_device_candidate"
DEFAULT_RELEASE_VERSION = "m3.4-acceptance.1"


class _PayoutMustNotRun:
    def __call__(self, *_args: object) -> None:
        raise RuntimeError("The acceptance seed must contain complete payouts.")


def _database_url(database_name: str) -> URL:
    return make_url(ApiSettings.from_environment().database_url).set(database=database_name)


def _migration_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config


def _recreate_candidate_database() -> URL:
    if CANDIDATE_DATABASE_NAME == "game_predictor":
        raise RuntimeError("Refusing to replace the local application database.")
    maintenance_engine = create_engine(
        _database_url("postgres"),
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    identifier = f'"{CANDIDATE_DATABASE_NAME}"'
    try:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
            connection.exec_driver_sql(f"CREATE DATABASE {identifier}")
    finally:
        maintenance_engine.dispose()
    candidate_url = _database_url(CANDIDATE_DATABASE_NAME)
    command.upgrade(_migration_config(candidate_url), "head")
    return candidate_url


def _drop_candidate_database() -> None:
    maintenance_engine = create_engine(
        _database_url("postgres"),
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    identifier = f'"{CANDIDATE_DATABASE_NAME}"'
    try:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
    finally:
        maintenance_engine.dispose()


def _seed_source(session: Session) -> MobileReleaseGameInput:
    game_id = uuid4()
    rules_id = uuid4()
    dataset_id = uuid4()
    symbol_ids = [uuid4(), uuid4(), uuid4()]
    created_at = datetime.now(UTC)
    session.add(
        GameModel(
            id=game_id,
            code="m34-acceptance",
            name="M3.4 acceptance",
            status=GameStatus.ACTIVE,
        )
    )
    session.flush()
    session.add_all(
        [
            SymbolModel(
                id=symbol_id,
                game_id=game_id,
                mobile_code=mobile_code,
                code=f"symbol-{mobile_code}",
                name=f"Symbol {mobile_code}",
                image_path=None,
                is_wildcard=False,
                display_order=mobile_code - 1,
                status=SymbolStatus.ACTIVE,
            )
            for mobile_code, symbol_id in enumerate(symbol_ids, start=1)
        ]
    )
    session.flush()
    session.add(
        RulesVersionModel(
            id=rules_id,
            game_id=game_id,
            version=1,
            rows=3,
            columns=5,
            spin_cost=10,
            status=RulesVersionStatus.PUBLISHED,
            published_at=created_at,
        )
    )
    session.flush()
    session.add_all(
        [
            RulesVersionSymbolModel(
                rules_version_id=rules_id,
                symbol_id=symbol_id,
                minimum_match_length=3,
                is_active=True,
            )
            for symbol_id in symbol_ids
        ]
    )
    layouts = (
        [1, 2, 3, 1, 2, 2, 3, 1, 2, 3, 3, 1, 2, 3, 1],
        [2, 2, 1, 3, 1, 1, 3, 2, 1, 2, 3, 1, 3, 2, 1],
        [3, 1, 2, 2, 3, 2, 1, 3, 1, 2, 1, 3, 2, 1, 3],
        [1, 2, 3, 1, 2, 2, 3, 1, 2, 3, 3, 1, 2, 3, 1],
    )
    session.add(
        DatasetVersionModel(
            id=dataset_id,
            game_id=game_id,
            version=1,
            rows=3,
            columns=5,
            signature_cell_width=2,
            layout_count=len(layouts),
            status=DatasetVersionStatus.PUBLISHED,
            generation_seed=3401,
            generator_version="m34-device-acceptance-v1",
            published_at=created_at,
        )
    )
    session.flush()
    session.add_all(
        [
            LayoutModel(
                dataset_version_id=dataset_id,
                sequence_number=sequence_number,
                signature="".join(f"{cell:02d}" for cell in cells),
                cells=cells,
            )
            for sequence_number, cells in enumerate(layouts, start=1)
        ]
    )
    session.flush()
    payouts = (0, 80, 0, 25)
    session.add_all(
        [
            LayoutPayoutModel(
                dataset_version_id=dataset_id,
                rules_version_id=rules_id,
                sequence_number=sequence_number,
                algorithm_version="payout-v2",
                total_payout=payout,
                audit_path=f"payout-audits/m34-acceptance-{sequence_number}.jsonl",
                calculated_at=created_at,
            )
            for sequence_number, payout in enumerate(payouts, start=1)
        ]
    )
    return MobileReleaseGameInput(
        game_id=game_id,
        dataset_version_id=dataset_id,
        rules_version_id=rules_id,
    )


def _build_candidate(release_version: str, candidate_url: URL) -> dict[str, object]:
    engine = create_engine(candidate_url, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    artifact_root = (REPOSITORY_ROOT / "artifacts").resolve()
    try:
        with Session(engine) as session, session.begin():
            source = _seed_source(session)
        with Session(engine, expire_on_commit=False) as session, session.begin():
            service = MobileReleaseService(SqlAlchemyMobileReleaseRepository(session))
            release = service.create_mobile_release(
                version=release_version,
                games=(source,),
            )
            job = service.start_mobile_release_build(release.id)

        payout_store = SqlAlchemyPayoutStore(session_factory)
        release_handler = ReleaseWorkflowHandler(
            SqlAlchemyReleaseWorkflowStore(session_factory),
            _PayoutMustNotRun(),  # type: ignore[arg-type]
            PayoutReadinessService(payout_store),
            ProductionSnapshotArtifactPublisher(
                ProductionSnapshotGenerator(SqlAlchemyProductionSnapshotStore(session_factory)),
                artifact_root,
            ),
            PowerShellAndroidReleaseBuilder(REPOSITORY_ROOT, artifact_root),
            artifact_root,
        )
        handler_failures: list[str] = []

        def diagnostic_release_handler(context: object, claimed_job: object) -> None:
            try:
                release_handler(context, claimed_job)  # type: ignore[arg-type]
            except Exception as error:
                handler_failures.append(f"{type(error).__name__}: {error}")
                raise

        result = LocalJobWorker(
            SqlAlchemyWorkerJobStore(session_factory),
            {JobType.ANDROID_BUILD: diagnostic_release_handler},  # type: ignore[dict-item]
            worker_id="m34-device-candidate",
            worker_version="task-0039",
            lease_duration=timedelta(minutes=20),
        ).run_once()
        if result is not JobExecutionResult.COMPLETED:
            with Session(engine) as session:
                failed_job = SqlAlchemyJobRepository(session).get_job(job.id)
            failure = (
                "without persisted error details"
                if failed_job is None
                else f"with {failed_job.error_code}: {failed_job.error_message}"
            )
            if handler_failures:
                failure = f"{failure}; root cause {handler_failures[-1]}"
            raise RuntimeError(f"Candidate build ended with job status {result.value} {failure}.")

        with Session(engine) as session:
            ready = SqlAlchemyMobileReleaseRepository(session).get_mobile_release(release.id)
        if ready is None or ready.status is not MobileReleaseStatus.READY:
            raise RuntimeError("Candidate release did not become ready.")
        if (
            ready.snapshot_path is None
            or ready.snapshot_checksum is None
            or ready.apk_path is None
            or ready.apk_checksum is None
        ):
            raise RuntimeError("Ready candidate is missing artifact metadata.")
        return {
            "releaseId": str(ready.id),
            "buildJobId": str(job.id),
            "releaseVersion": ready.version,
            "snapshotPath": ready.snapshot_path,
            "snapshotSha256": ready.snapshot_checksum,
            "apkPath": ready.apk_path,
            "apkSha256": ready.apk_checksum,
        }
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-version", default=DEFAULT_RELEASE_VERSION)
    options = parser.parse_args()
    candidate_url = _recreate_candidate_database()
    try:
        report = _build_candidate(options.release_version, candidate_url)
    finally:
        _drop_candidate_database()

    report_path = (
        REPOSITORY_ROOT
        / "artifacts"
        / "android-releases"
        / options.release_version
        / "candidate.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Candidate report: {report_path}")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
