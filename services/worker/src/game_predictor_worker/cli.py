"""Windows-friendly command line entry point for the local job worker."""

from __future__ import annotations

import argparse
import os
import socket
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

from game_predictor_api.application.layout_imports import LayoutImportSourceInspector
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.jobs import JobType
from game_predictor_api.storage.database import (
    create_database_engine,
    create_session_factory,
)

from game_predictor_worker.imports.handler import LayoutImportStagingHandler
from game_predictor_worker.imports.store import SqlAlchemyLayoutImportStagingStore
from game_predictor_worker.imports.validation_handler import (
    LayoutImportValidationHandler,
)
from game_predictor_worker.jobs.runtime import LocalJobWorker
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore
from game_predictor_worker.payouts.audit import JsonlPayoutAuditWriter
from game_predictor_worker.payouts.handler import PayoutBatchHandler
from game_predictor_worker.payouts.readiness import PayoutReadinessService
from game_predictor_worker.payouts.store import SqlAlchemyPayoutStore
from game_predictor_worker.releases import (
    PowerShellAndroidReleaseBuilder,
    ReleaseWorkflowHandler,
    SqlAlchemyReleaseWorkflowStore,
)
from game_predictor_worker.snapshots import (
    ProductionSnapshotArtifactPublisher,
    ProductionSnapshotGenerator,
    SqlAlchemyProductionSnapshotStore,
)

WORKER_VERSION = "worker-v4"


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local durable job worker.")
    parser.add_argument(
        "--poll",
        action="store_true",
        help="Continue polling instead of performing one claim attempt.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Seconds between empty polling attempts.",
    )
    parser.add_argument(
        "--lease-seconds",
        type=int,
        default=60,
        help="Lease duration renewed by heartbeat/checkpoint.",
    )
    parser.add_argument(
        "--worker-id",
        default=f"{socket.gethostname()}-{os.getpid()}",
        help="Diagnostic owner stored with the lease.",
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path("artifacts"),
        help="Local root for deterministic worker artifacts.",
    )
    options = parser.parse_args(arguments)
    if not 5 <= options.lease_seconds <= 3600:
        parser.error("--lease-seconds must be between 5 and 3600.")
    if options.poll_interval <= 0:
        parser.error("--poll-interval must be positive.")

    settings = ApiSettings.from_environment()
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    store = SqlAlchemyWorkerJobStore(session_factory)
    artifact_root = options.artifact_root.resolve()
    payout_store = SqlAlchemyPayoutStore(session_factory)
    payout_handler = PayoutBatchHandler(
        payout_store,
        JsonlPayoutAuditWriter(artifact_root),
    )
    import_store = SqlAlchemyLayoutImportStagingStore(session_factory)
    import_handler = LayoutImportStagingHandler(
        import_store,
        LayoutImportSourceInspector(
            settings.import_root,
            max_bytes=settings.import_max_bytes,
        ),
    )
    import_validation_handler = LayoutImportValidationHandler(import_store)
    snapshot_store = SqlAlchemyProductionSnapshotStore(session_factory)
    release_handler = ReleaseWorkflowHandler(
        SqlAlchemyReleaseWorkflowStore(session_factory),
        payout_handler,
        PayoutReadinessService(payout_store),
        ProductionSnapshotArtifactPublisher(
            ProductionSnapshotGenerator(snapshot_store),
            artifact_root,
        ),
        PowerShellAndroidReleaseBuilder(
            Path.cwd(),
            artifact_root,
        ),
        artifact_root,
    )
    worker = LocalJobWorker(
        store,
        {
            JobType.IMPORT: import_handler,
            JobType.VALIDATE: import_validation_handler,
            JobType.PAYOUT: payout_handler,
            JobType.ANDROID_BUILD: release_handler,
        },
        worker_id=options.worker_id,
        worker_version=WORKER_VERSION,
        lease_duration=timedelta(seconds=options.lease_seconds),
    )
    try:
        if options.poll:
            worker.run_forever(
                should_stop=lambda: False,
                poll_interval_seconds=options.poll_interval,
            )
            return 0
        result = worker.run_once()
        print(result.value)
        return 0
    except KeyboardInterrupt:
        return 130
    finally:
        engine.dispose()
