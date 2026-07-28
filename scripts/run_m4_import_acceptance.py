"""Run the isolated M4 import-to-release acceptance on PostgreSQL."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import sys
import zipfile
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any, cast
from uuid import UUID

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
API_SOURCE = REPOSITORY_ROOT / "services" / "api" / "src"
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(API_SOURCE))
sys.path.insert(0, str(WORKER_SOURCE))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from game_predictor_api.application.layout_imports import (  # noqa: E402
    LayoutImportSourceInspector,
)
from game_predictor_api.config import ApiSettings  # noqa: E402
from game_predictor_api.domain.jobs import Job, JobType  # noqa: E402
from game_predictor_api.main import create_app  # noqa: E402
from game_predictor_api.storage.database import (  # noqa: E402
    create_session_factory,
)
from game_predictor_api.storage.models import (  # noqa: E402
    LayoutModel,
    LayoutPayoutModel,
)
from game_predictor_worker.benchmarks import PeakMemorySampler  # noqa: E402
from game_predictor_worker.imports.fixtures import (  # noqa: E402
    DEFAULT_ACCEPTANCE_LAYOUT_COUNT,
    DEFAULT_ACCEPTANCE_SEED,
    LayoutImportFixtureResult,
    write_blocked_layout_import_fixture,
    write_layout_import_fixture,
)
from game_predictor_worker.imports.handler import (  # noqa: E402
    LayoutImportStagingHandler,
)
from game_predictor_worker.imports.store import (  # noqa: E402
    SqlAlchemyLayoutImportStagingStore,
)
from game_predictor_worker.imports.validation_handler import (  # noqa: E402
    LayoutImportValidationHandler,
)
from game_predictor_worker.jobs.runtime import (  # noqa: E402
    JobExecutionResult,
    LocalJobWorker,
)
from game_predictor_worker.jobs.store import (  # noqa: E402
    SqlAlchemyWorkerJobStore,
)
from game_predictor_worker.payouts.audit import JsonlPayoutAuditWriter  # noqa: E402
from game_predictor_worker.payouts.handler import PayoutBatchHandler  # noqa: E402
from game_predictor_worker.payouts.readiness import (  # noqa: E402
    PayoutReadinessService,
)
from game_predictor_worker.payouts.store import SqlAlchemyPayoutStore  # noqa: E402
from game_predictor_worker.releases import (  # noqa: E402
    AndroidReleaseArtifact,
    AndroidReleaseBuildSpec,
    PowerShellAndroidReleaseBuilder,
    ReleaseWorkflowHandler,
    SqlAlchemyReleaseWorkflowStore,
)
from game_predictor_worker.snapshots import (  # noqa: E402
    ProductionSnapshotArtifactPublisher,
    ProductionSnapshotGenerator,
    SqlAlchemyProductionSnapshotStore,
    validate_snapshot_artifact,
)
from sqlalchemy import create_engine, distinct, func, select  # noqa: E402
from sqlalchemy.engine import URL, make_url  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
DEFAULT_DATABASE_NAME = "game_predictor_m4_acceptance_test"
DEFAULT_IMPORT_ROOT = REPOSITORY_ROOT / "imports"
DEFAULT_ARTIFACT_ROOT = REPOSITORY_ROOT / "artifacts" / "m4-acceptance"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "ai_docs" / "quality" / "m4-import-acceptance-report.json"
_SAFE_DATABASE_NAME = re.compile(r"^game_predictor_m4_acceptance(?:_[a-z0-9]+)*$")


class SimulatedImportInterruption(RuntimeError):
    """Raised only after a real durable import checkpoint."""


class ProgressWorkerJobStore(SqlAlchemyWorkerJobStore):
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        interrupt_import_after_checkpoints: int | None = None,
    ) -> None:
        super().__init__(session_factory)
        self._interrupt_after = interrupt_import_after_checkpoints
        self._checkpoint_count = 0
        self.interrupted_checkpoint: dict[str, object] | None = None

    @property
    def checkpoint_count(self) -> int:
        return self._checkpoint_count

    def checkpoint(
        self,
        job_id: UUID,
        *,
        lease_token: UUID,
        lease_duration: timedelta,
        checkpoint_payload: dict[str, object],
        stage: str,
        current: int,
        total: int | None,
        success_count: int,
        failure_count: int,
        review_count: int,
        checkpointed_at: datetime,
    ) -> Job:
        updated = super().checkpoint(
            job_id,
            lease_token=lease_token,
            lease_duration=lease_duration,
            checkpoint_payload=checkpoint_payload,
            stage=stage,
            current=current,
            total=total,
            success_count=success_count,
            failure_count=failure_count,
            review_count=review_count,
            checkpointed_at=checkpointed_at,
        )
        self._checkpoint_count += 1
        if self._checkpoint_count == 1 or self._checkpoint_count % 25 == 0:
            rendered_total = "?" if total is None else f"{total:,}"
            print(
                f"{stage}: {current:,}/{rendered_total} "
                f"(checkpoint {self._checkpoint_count})",
                flush=True,
            )
        if (
            self._interrupt_after is not None
            and self._checkpoint_count == self._interrupt_after
            and stage == "staging_import_rows"
        ):
            self.interrupted_checkpoint = dict(checkpoint_payload)
            raise SimulatedImportInterruption(
                "Simulated process interruption after a durable import checkpoint."
            )
        return updated


class SmokeAndroidBuilder:
    """Bounded adapter for development smoke runs explicitly skipping Gradle."""

    def __init__(self, artifact_root: Path) -> None:
        self._artifact_root = artifact_root.resolve()

    def build(
        self,
        spec: AndroidReleaseBuildSpec,
        *,
        heartbeat: Callable[[], None] | None = None,
    ) -> AndroidReleaseArtifact:
        if heartbeat is not None:
            heartbeat()
        payload = (
            "M4 smoke only; not an installable APK.\n"
            f"{spec.release_version}\n"
            f"{spec.snapshot.manifest.snapshot_file_sha256}\n"
        ).encode()
        checksum = hashlib.sha256(payload).hexdigest()
        path = (
            self._artifact_root
            / "android-releases"
            / spec.release_version
            / f"smoke-only-{checksum}.apk"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() != payload:
            raise RuntimeError("Smoke artifact collision.")
        if not path.exists():
            path.write_bytes(payload)
        return AndroidReleaseArtifact(
            apk_path=path,
            apk_sha256=checksum,
            snapshot_sha256=spec.snapshot.manifest.snapshot_file_sha256,
        )


class AcceptanceRecorder:
    def __init__(self, *, layout_count: int, android_build_skipped: bool) -> None:
        self.started_at = datetime.now(UTC)
        self.report: dict[str, object] = {
            "androidBuildSkipped": android_build_skipped,
            "capturedAt": self.started_at.isoformat(),
            "dataset": {"layoutCount": layout_count},
            "environment": {
                "machine": platform.machine(),
                "operatingSystem": platform.platform(),
                "python": platform.python_version(),
            },
            "stages": {},
            "status": "running",
        }

    def measure[T](self, name: str, operation: Callable[[], T]) -> T:
        print(f"[M4] {name}...", flush=True)
        sampler = PeakMemorySampler()
        started_at = perf_counter()
        with sampler:
            result = operation()
        elapsed_seconds = perf_counter() - started_at
        stages = cast(dict[str, object], self.report["stages"])
        stages[name] = {
            "elapsedSeconds": round(elapsed_seconds, 4),
            "memory": sampler.summary().to_dict(),
        }
        print(f"[M4] {name}: {elapsed_seconds:.2f}s", flush=True)
        return result

    def finish(self, status: str) -> None:
        self.report["elapsedSeconds"] = round(
            (datetime.now(UTC) - self.started_at).total_seconds(),
            4,
        )
        self.report["status"] = status


class AcceptanceRunFailed(RuntimeError):
    def __init__(self, report: dict[str, object]) -> None:
        failure = cast(dict[str, str], report["failure"])
        super().__init__(failure["message"])
        self.report = report


def _database_url(database_name: str) -> URL:
    if not _SAFE_DATABASE_NAME.fullmatch(database_name):
        raise ValueError(
            "Acceptance database must start with game_predictor_m4_acceptance."
        )
    return make_url(ApiSettings.from_environment().database_url).set(
        database=database_name
    )


def _migration_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config


def _recreate_database(database_name: str) -> tuple[URL, Any]:
    maintenance_engine = create_engine(
        _database_url("game_predictor_m4_acceptance_test").set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    database_url = _database_url(database_name)
    identifier = f'"{database_name}"'
    with maintenance_engine.connect() as connection:
        connection.exec_driver_sql(
            f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)"
        )
        connection.exec_driver_sql(f"CREATE DATABASE {identifier}")
    command.upgrade(_migration_config(database_url), "head")
    return database_url, maintenance_engine


def _drop_database(maintenance_engine: Any, database_name: str) -> None:
    if not _SAFE_DATABASE_NAME.fullmatch(database_name):
        raise ValueError("Refusing to drop an unexpected database.")
    identifier = f'"{database_name}"'
    with maintenance_engine.connect() as connection:
        connection.exec_driver_sql(
            f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)"
        )
    maintenance_engine.dispose()


def _json(response: Any, expected_status: int) -> Any:
    if response.status_code != expected_status:
        raise RuntimeError(
            f"HTTP {response.status_code}, expected {expected_status}: {response.text}"
        )
    return response.json()


def _create_rules(client: TestClient) -> tuple[str, str]:
    game = _json(
        client.post(
            "/api/v1/admin/games",
            json={
                "code": "m4-acceptance",
                "name": "M4 Acceptance Game",
                "status": "active",
            },
        ),
        201,
    )
    game_id = str(game["id"])
    symbols: list[dict[str, object]] = []
    for mobile_code in range(1, 13):
        symbols.append(
            _json(
                client.post(
                    f"/api/v1/admin/games/{game_id}/symbols",
                    json={
                        "mobileCode": mobile_code,
                        "code": f"S{mobile_code}",
                        "name": (
                            "Joker" if mobile_code == 12 else f"Symbol {mobile_code}"
                        ),
                        "imagePath": f"symbols/m4-acceptance/s{mobile_code}.png",
                        "isWildcard": mobile_code == 12,
                        "displayOrder": mobile_code * 10,
                        "status": "active",
                    },
                ),
                201,
            )
        )
    rules = _json(
        client.post(
            f"/api/v1/admin/games/{game_id}/rules-versions",
            json={"rows": 3, "columns": 5, "spinCost": 10},
        ),
        201,
    )
    rules_id = str(rules["id"])
    for row_index, code in enumerate(("top", "middle", "bottom")):
        _json(
            client.post(
                f"/api/v1/admin/rules-versions/{rules_id}/paylines",
                json={
                    "code": code,
                    "name": code.title(),
                    "rowPath": [row_index] * 5,
                    "displayOrder": (row_index + 1) * 10,
                    "isActive": True,
                },
            ),
            201,
        )
    for symbol in symbols:
        mobile_code = int(cast(int, symbol["mobileCode"]))
        is_wildcard = bool(symbol["isWildcard"])
        minimum = None if is_wildcard else (2 if mobile_code == 1 else 3)
        _json(
            client.patch(
                f"/api/v1/admin/rules-versions/{rules_id}/symbols/{symbol['id']}",
                json={
                    "minimumMatchLength": minimum,
                    "isActive": True,
                },
            ),
            200,
        )
        if minimum is None:
            continue
        for match_length in range(minimum, 6):
            _json(
                client.post(
                    f"/api/v1/admin/rules-versions/{rules_id}/payout-rules",
                    json={
                        "symbolId": symbol["id"],
                        "matchLength": match_length,
                        "payoutCredits": mobile_code * 10 * (match_length - minimum + 1),
                        "isActive": True,
                    },
                ),
                201,
            )
    readiness = _json(
        client.get(
            f"/api/v1/admin/rules-versions/{rules_id}/publication-readiness"
        ),
        200,
    )
    if readiness != {"rulesVersionId": rules_id, "ready": True, "issues": []}:
        raise RuntimeError(f"Rules are not ready: {readiness}")
    published = _json(
        client.post(f"/api/v1/admin/rules-versions/{rules_id}/publish"),
        200,
    )
    if published["status"] != "published":
        raise RuntimeError("Rules publication did not complete.")
    return game_id, rules_id


def _create_import_job(
    client: TestClient,
    *,
    game_id: str,
    source_path: str,
) -> dict[str, object]:
    return cast(
        dict[str, object],
        _json(
            client.post(
                "/api/v1/admin/jobs",
                json={
                    "jobType": "import",
                    "gameId": game_id,
                    "inputPayload": {
                        "schemaVersion": 1,
                        "sourcePath": source_path,
                        "contractVersion": 1,
                    },
                },
            ),
            201,
        ),
    )


def _create_validation_job(
    client: TestClient,
    *,
    game_id: str,
    import_job_id: str,
    rules_id: str,
) -> dict[str, object]:
    return cast(
        dict[str, object],
        _json(
            client.post(
                "/api/v1/admin/jobs",
                json={
                    "jobType": "validate",
                    "gameId": game_id,
                    "inputPayload": {
                        "schemaVersion": 1,
                        "validationKind": "layout_import",
                        "importJobId": import_job_id,
                        "rulesVersionId": rules_id,
                    },
                },
            ),
            201,
        ),
    )


def _import_handlers(
    session_factory: sessionmaker[Session],
    settings: ApiSettings,
) -> Mapping[JobType, object]:
    store = SqlAlchemyLayoutImportStagingStore(session_factory)
    return {
        JobType.IMPORT: LayoutImportStagingHandler(
            store,
            source_attestor=LayoutImportSourceInspector(
                settings.import_root,
                max_bytes=settings.import_max_bytes,
            ),
        ),
        JobType.VALIDATE: LayoutImportValidationHandler(store),
    }


def _release_handler(
    session_factory: sessionmaker[Session],
    *,
    artifact_root: Path,
    skip_android_build: bool,
) -> ReleaseWorkflowHandler:
    payout_store = SqlAlchemyPayoutStore(session_factory)
    payout_handler = PayoutBatchHandler(
        payout_store,
        JsonlPayoutAuditWriter(artifact_root),
    )
    android_builder = (
        SmokeAndroidBuilder(artifact_root)
        if skip_android_build
        else PowerShellAndroidReleaseBuilder(REPOSITORY_ROOT, artifact_root)
    )
    return ReleaseWorkflowHandler(
        SqlAlchemyReleaseWorkflowStore(session_factory),
        payout_handler,
        PayoutReadinessService(payout_store),
        ProductionSnapshotArtifactPublisher(
            ProductionSnapshotGenerator(
                SqlAlchemyProductionSnapshotStore(session_factory)
            ),
            artifact_root,
        ),
        android_builder,
        artifact_root,
    )


def _run_one_job(
    session_factory: sessionmaker[Session],
    handlers: Mapping[JobType, object],
    *,
    worker_id: str,
    interrupt_import_after_checkpoints: int | None = None,
) -> tuple[JobExecutionResult, ProgressWorkerJobStore]:
    store = ProgressWorkerJobStore(
        session_factory,
        interrupt_import_after_checkpoints=interrupt_import_after_checkpoints,
    )
    worker = LocalJobWorker(
        store,
        cast(Mapping[JobType, Any], handlers),
        worker_id=worker_id,
        worker_version="m4-acceptance-v1",
        lease_duration=timedelta(seconds=300),
    )
    return worker.run_once(), store


def _fixture_relative_path(path: Path, import_root: Path) -> str:
    try:
        return path.resolve().relative_to(import_root.resolve()).as_posix()
    except ValueError as error:
        raise ValueError("Fixture must remain under the configured import root.") from error


def _database_invariants(
    session_factory: sessionmaker[Session],
    dataset_id: str,
) -> dict[str, int]:
    identifier = UUID(dataset_id)
    with session_factory() as session:
        row = session.execute(
            select(
                func.count(LayoutModel.sequence_number),
                func.min(LayoutModel.sequence_number),
                func.max(LayoutModel.sequence_number),
                func.count(distinct(LayoutModel.sequence_number)),
                func.count(distinct(LayoutModel.signature)),
            ).where(LayoutModel.dataset_version_id == identifier)
        ).one()
    return {
        "layoutCount": int(row[0]),
        "minimumSequenceNumber": int(row[1]),
        "maximumSequenceNumber": int(row[2]),
        "uniqueSequenceCount": int(row[3]),
        "uniqueSignatureCount": int(row[4]),
    }


def _payout_count(
    session_factory: sessionmaker[Session],
    dataset_id: str,
    rules_id: str,
) -> int:
    with session_factory() as session:
        value = session.scalar(
            select(func.count())
            .select_from(LayoutPayoutModel)
            .where(
                LayoutPayoutModel.dataset_version_id == UUID(dataset_id),
                LayoutPayoutModel.rules_version_id == UUID(rules_id),
                LayoutPayoutModel.algorithm_version == "payout-v2",
            )
        )
    return int(value or 0)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_checksum_from_apk(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        databases = sorted(name for name in archive.namelist() if name.endswith(".db"))
        if not databases:
            raise RuntimeError("Verified APK does not contain a SQLite database.")
        with archive.open(databases[0]) as database:
            digest = hashlib.sha256()
            for chunk in iter(lambda: database.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


def _generate_fixtures(
    recorder: AcceptanceRecorder,
    *,
    import_root: Path,
    layout_count: int,
    seed: int,
) -> tuple[LayoutImportFixtureResult, LayoutImportFixtureResult]:
    fixture_directory = import_root / "m4-acceptance"

    def generate() -> tuple[LayoutImportFixtureResult, LayoutImportFixtureResult]:
        def progress(current: int, total: int) -> None:
            if current == total or current % 25_000 == 0:
                print(f"fixture: {current:,}/{total:,}", flush=True)

        valid = write_layout_import_fixture(
            fixture_directory / "layouts-500k.jsonl",
            layout_count=layout_count,
            seed=seed,
            progress=progress,
        )
        blocked = write_blocked_layout_import_fixture(
            fixture_directory / "layouts-blocked.jsonl",
            seed=seed,
        )
        return valid, blocked

    return recorder.measure("fixtureGeneration", generate)


def run_acceptance(
    *,
    layout_count: int,
    seed: int,
    database_name: str,
    import_root: Path,
    artifact_root: Path,
    skip_android_build: bool,
    keep_database: bool,
    release_version: str,
) -> dict[str, object]:
    recorder = AcceptanceRecorder(
        layout_count=layout_count,
        android_build_skipped=skip_android_build,
    )
    valid_fixture, blocked_fixture = _generate_fixtures(
        recorder,
        import_root=import_root,
        layout_count=layout_count,
        seed=seed,
    )
    recorder.report["fixtures"] = {
        "blocked": blocked_fixture.to_dict(),
        "valid": valid_fixture.to_dict(),
    }

    database_url: URL | None = None
    maintenance_engine: Any | None = None
    application: Any | None = None
    worker_engine: Any | None = None
    succeeded = False
    try:
        database_url, maintenance_engine = recorder.measure(
            "databaseMigration",
            lambda: _recreate_database(database_name),
        )
        settings = ApiSettings.from_environment(
            {
                "GAME_PREDICTOR_DATABASE_URL": database_url.render_as_string(
                    hide_password=False
                ),
                "GAME_PREDICTOR_IMPORT_ROOT": str(import_root.resolve()),
                "GAME_PREDICTOR_IMPORT_MAX_BYTES": str(1024 * 1024 * 1024),
                "GAME_PREDICTOR_ARTIFACT_ROOT": str(artifact_root.resolve()),
            }
        )
        application = create_app(settings)
        worker_engine = create_engine(database_url, pool_pre_ping=True)
        session_factory = create_session_factory(worker_engine)
        import_handlers = _import_handlers(session_factory, settings)

        with TestClient(application) as client:
            game_id, rules_id = recorder.measure(
                "configuration",
                lambda: _create_rules(client),
            )

            blocked_import = recorder.measure(
                "blockedImportJobCreation",
                lambda: _create_import_job(
                    client,
                    game_id=game_id,
                    source_path=_fixture_relative_path(
                        blocked_fixture.path,
                        import_root,
                    ),
                ),
            )
            blocked_import_result, _ = recorder.measure(
                "blockedImportStaging",
                lambda: _run_one_job(
                    session_factory,
                    import_handlers,
                    worker_id="m4-blocked-import",
                ),
            )
            if blocked_import_result is not JobExecutionResult.COMPLETED:
                raise RuntimeError(
                    f"Blocked import staging ended as {blocked_import_result.value}."
                )
            blocked_validation = _create_validation_job(
                client,
                game_id=game_id,
                import_job_id=str(blocked_import["id"]),
                rules_id=rules_id,
            )
            blocked_validation_result, _ = recorder.measure(
                "blockedImportValidation",
                lambda: _run_one_job(
                    session_factory,
                    import_handlers,
                    worker_id="m4-blocked-validation",
                ),
            )
            if blocked_validation_result is not JobExecutionResult.COMPLETED:
                raise RuntimeError(
                    f"Blocked validation ended as {blocked_validation_result.value}."
                )
            blocked_report = recorder.measure(
                "blockedIntegrityReport",
                lambda: _json(
                    client.get(
                        "/api/v1/admin/layout-import-validations/"
                        f"{blocked_validation['id']}/integrity-report"
                    ),
                    200,
                ),
            )
            blocked_publication = client.post(
                "/api/v1/admin/layout-import-validations/"
                f"{blocked_validation['id']}/publish"
            )
            blocked_error = _json(blocked_publication, 409)
            if (
                blocked_report["readyForPublication"] is not False
                or blocked_error["code"] != "LAYOUT_IMPORT_NOT_READY_FOR_PUBLICATION"
            ):
                raise RuntimeError("The blocked import unexpectedly became publishable.")
            recorder.report["blockedControl"] = {
                "errorCodeCounts": blocked_report["errorCodeCounts"],
                "publicationErrorCode": blocked_error["code"],
                "reportChecks": blocked_report["checks"],
            }

            valid_import = recorder.measure(
                "validImportJobCreationAndChecksum",
                lambda: _create_import_job(
                    client,
                    game_id=game_id,
                    source_path=_fixture_relative_path(valid_fixture.path, import_root),
                ),
            )
            interrupted_result, interrupted_store = recorder.measure(
                "validImportInterruptedAttempt",
                lambda: _run_one_job(
                    session_factory,
                    import_handlers,
                    worker_id="m4-valid-import-interrupted",
                    interrupt_import_after_checkpoints=1,
                ),
            )
            if interrupted_result is not JobExecutionResult.FAILED:
                raise RuntimeError("The controlled interruption did not fail the first attempt.")
            interrupted_job = _json(
                client.get(f"/api/v1/admin/jobs/{valid_import['id']}"),
                200,
            )
            if (
                interrupted_job["error"]["code"] != "JOB_EXECUTION_FAILED"
                or interrupted_store.interrupted_checkpoint is None
            ):
                raise RuntimeError("The interrupted import did not preserve its checkpoint.")
            retry = _json(
                client.post(f"/api/v1/admin/jobs/{valid_import['id']}/retry"),
                200,
            )
            if retry["status"] != "created":
                raise RuntimeError("The interrupted import was not requeued.")
            resumed_result, resumed_store = recorder.measure(
                "validImportResume",
                lambda: _run_one_job(
                    session_factory,
                    import_handlers,
                    worker_id="m4-valid-import-resumed",
                ),
            )
            if resumed_result is not JobExecutionResult.COMPLETED:
                raise RuntimeError(f"Resumed import ended as {resumed_result.value}.")
            completed_import = _json(
                client.get(f"/api/v1/admin/jobs/{valid_import['id']}"),
                200,
            )
            if (
                completed_import["progress"]["succeeded"] != layout_count
                or completed_import["progress"]["failed"] != 0
                or completed_import["attemptCount"] != 2
            ):
                raise RuntimeError("The resumed import counters are inconsistent.")
            checkpoint = interrupted_store.interrupted_checkpoint
            assert checkpoint is not None
            recorder.report["resume"] = {
                "attemptCount": completed_import["attemptCount"],
                "checkpointByteOffset": checkpoint["byte_offset"],
                "checkpointLineNumber": checkpoint["line_number"],
                "finalCheckpointCount": resumed_store.checkpoint_count,
                "sameJobId": str(valid_import["id"]),
            }

            valid_validation = _create_validation_job(
                client,
                game_id=game_id,
                import_job_id=str(valid_import["id"]),
                rules_id=rules_id,
            )
            valid_validation_result, _ = recorder.measure(
                "validImportValidation",
                lambda: _run_one_job(
                    session_factory,
                    import_handlers,
                    worker_id="m4-valid-validation",
                ),
            )
            if valid_validation_result is not JobExecutionResult.COMPLETED:
                raise RuntimeError(
                    f"Valid import validation ended as {valid_validation_result.value}."
                )
            valid_report = recorder.measure(
                "validIntegrityReport",
                lambda: _json(
                    client.get(
                        "/api/v1/admin/layout-import-validations/"
                        f"{valid_validation['id']}/integrity-report"
                    ),
                    200,
                ),
            )
            if (
                valid_report["readyForPublication"] is not True
                or valid_report["actualRowCount"] != layout_count
                or valid_report["duplicateSignatureGroupCount"] != 6
                or valid_report["duplicateSignatureAffectedRowCount"] != 12
            ):
                raise RuntimeError("The valid import integrity report is inconsistent.")

            dataset = recorder.measure(
                "datasetPublication",
                lambda: _json(
                    client.post(
                        "/api/v1/admin/layout-import-validations/"
                        f"{valid_validation['id']}/publish"
                    ),
                    200,
                ),
            )
            publication_retry = _json(
                client.post(
                    "/api/v1/admin/layout-import-validations/"
                    f"{valid_validation['id']}/publish"
                ),
                200,
            )
            if dataset != publication_retry:
                raise RuntimeError("Publication retry returned a different dataset.")
            dataset_id = str(dataset["id"])
            invariants = recorder.measure(
                "publishedDatasetIntegrity",
                lambda: _database_invariants(session_factory, dataset_id),
            )
            expected_unique_signatures = layout_count - 6
            if invariants != {
                "layoutCount": layout_count,
                "minimumSequenceNumber": 1,
                "maximumSequenceNumber": layout_count,
                "uniqueSequenceCount": layout_count,
                "uniqueSignatureCount": expected_unique_signatures,
            }:
                raise RuntimeError(f"Published dataset invariants failed: {invariants}")
            recorder.report["dataset"] = {
                **cast(dict[str, object], recorder.report["dataset"]),
                **invariants,
                "datasetVersion": dataset["version"],
                "generatorVersion": dataset["generatorVersion"],
                "id": dataset_id,
                "publicationRetryReturnedSameId": dataset["id"]
                == publication_retry["id"],
                "rulesVersionId": rules_id,
                "sourceJobId": dataset["sourceJobId"],
            }
            recorder.report["validReport"] = {
                "actualRowCount": valid_report["actualRowCount"],
                "duplicateSignatureAffectedRowCount": (
                    valid_report["duplicateSignatureAffectedRowCount"]
                ),
                "duplicateSignatureGroupCount": (
                    valid_report["duplicateSignatureGroupCount"]
                ),
                "errorCodeCounts": valid_report["errorCodeCounts"],
                "readyForPublication": valid_report["readyForPublication"],
            }

            release = _json(
                client.post(
                    "/api/v1/admin/mobile-releases",
                    json={
                        "version": release_version,
                        "games": [
                            {
                                "gameId": game_id,
                                "datasetVersionId": dataset_id,
                                "rulesVersionId": rules_id,
                            }
                        ],
                    },
                ),
                201,
            )
            build_job = _json(
                client.post(
                    f"/api/v1/admin/mobile-releases/{release['id']}/build"
                ),
                201,
            )
            release_result, release_store = recorder.measure(
                "payoutSnapshotAndAndroidRelease",
                lambda: _run_one_job(
                    session_factory,
                    {
                        JobType.ANDROID_BUILD: _release_handler(
                            session_factory,
                            artifact_root=artifact_root,
                            skip_android_build=skip_android_build,
                        )
                    },
                    worker_id="m4-release",
                ),
            )
            if release_result is not JobExecutionResult.COMPLETED:
                persisted = _json(
                    client.get(f"/api/v1/admin/jobs/{build_job['jobId']}"),
                    200,
                )
                raise RuntimeError(
                    "Release workflow failed: "
                    f"{persisted.get('error')} ({release_result.value})"
                )
            ready = _json(
                client.get(f"/api/v1/admin/mobile-releases/{release['id']}"),
                200,
            )
            if ready["status"] != "ready" or ready["snapshot"] is None or ready["apk"] is None:
                raise RuntimeError("The release did not become ready.")

            snapshot_path = artifact_root / ready["snapshot"]["relativePath"]
            snapshot = recorder.measure(
                "independentSnapshotValidation",
                lambda: validate_snapshot_artifact(snapshot_path.parent),
            )
            if snapshot.manifest.layout_count != layout_count:
                raise RuntimeError("Snapshot layout count differs from the import.")
            apk_path = artifact_root / ready["apk"]["relativePath"]
            if _file_sha256(apk_path) != ready["apk"]["checksum"]:
                raise RuntimeError("APK checksum differs from the immutable release.")
            downloaded = client.get(
                f"/api/v1/admin/mobile-releases/{release['id']}/apk"
            )
            if downloaded.status_code != 200:
                raise RuntimeError(f"Verified APK download failed: {downloaded.text}")
            if hashlib.sha256(downloaded.content).hexdigest() != ready["apk"]["checksum"]:
                raise RuntimeError("Downloaded APK checksum differs from the release.")
            embedded_snapshot_checksum = (
                None
                if skip_android_build
                else recorder.measure(
                    "independentApkSnapshotCheck",
                    lambda: _snapshot_checksum_from_apk(apk_path),
                )
            )
            if (
                not skip_android_build
                and embedded_snapshot_checksum != ready["snapshot"]["checksum"]
            ):
                raise RuntimeError("APK embeds a different snapshot.")
            payout_count = _payout_count(session_factory, dataset_id, rules_id)
            if payout_count != layout_count:
                raise RuntimeError("Release workflow did not persist every payout.")
            recorder.report["release"] = {
                "androidBuildVerified": not skip_android_build,
                "apkChecksum": ready["apk"]["checksum"],
                "apkRelativePath": ready["apk"]["relativePath"],
                "apkSizeBytes": apk_path.stat().st_size,
                "buildJobAttemptCount": _json(
                    client.get(f"/api/v1/admin/jobs/{build_job['jobId']}"),
                    200,
                )["attemptCount"],
                "checkpointCount": release_store.checkpoint_count,
                "downloadChecksumVerified": True,
                "embeddedSnapshotChecksum": embedded_snapshot_checksum,
                "id": ready["id"],
                "offlineVerifierPassed": not skip_android_build,
                "payoutCount": payout_count,
                "snapshotChecksum": ready["snapshot"]["checksum"],
                "snapshotLogicalChecksum": (
                    snapshot.manifest.logical_content_sha256
                ),
                "snapshotRelativePath": ready["snapshot"]["relativePath"],
                "snapshotSizeBytes": snapshot.database_path.stat().st_size,
                "status": ready["status"],
                "version": ready["version"],
            }

        recorder.finish("smoke_passed" if skip_android_build else "passed")
        succeeded = True
        return recorder.report
    except BaseException as error:
        recorder.report["failure"] = {
            "message": str(error),
            "type": type(error).__name__,
        }
        recorder.report["databaseRetainedForRetry"] = maintenance_engine is not None
        recorder.finish("failed")
        raise AcceptanceRunFailed(recorder.report) from error
    finally:
        if application is not None:
            application.state.database_engine.dispose()
        if worker_engine is not None:
            worker_engine.dispose()
        if (
            maintenance_engine is not None
            and succeeded
            and not keep_database
        ):
            _drop_database(maintenance_engine, database_name)
        elif maintenance_engine is not None:
            maintenance_engine.dispose()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--layout-count",
        type=int,
        default=DEFAULT_ACCEPTANCE_LAYOUT_COUNT,
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_ACCEPTANCE_SEED)
    parser.add_argument("--database-name", default=DEFAULT_DATABASE_NAME)
    parser.add_argument("--import-root", type=Path, default=DEFAULT_IMPORT_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--release-version", default="m4-acceptance.1")
    parser.add_argument("--skip-android-build", action="store_true")
    parser.add_argument("--keep-database", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    output = cast(Path, args.output).resolve()
    report: dict[str, object]
    try:
        report = run_acceptance(
            layout_count=cast(int, args.layout_count),
            seed=cast(int, args.seed),
            database_name=cast(str, args.database_name),
            import_root=cast(Path, args.import_root).resolve(),
            artifact_root=cast(Path, args.artifact_root).resolve(),
            skip_android_build=cast(bool, args.skip_android_build),
            keep_database=cast(bool, args.keep_database),
            release_version=cast(str, args.release_version),
        )
    except AcceptanceRunFailed as error:
        report = error.report
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        raise SystemExit(1) from error
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"Saved M4 acceptance report to {output}.")


if __name__ == "__main__":
    main()
