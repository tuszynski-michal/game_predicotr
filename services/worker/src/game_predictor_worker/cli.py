"""Windows-friendly command line entry point for the local job worker."""

from __future__ import annotations

import argparse
import os
import socket
from collections.abc import Sequence
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from game_predictor_api.application.layout_imports import LayoutImportSourceInspector
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.jobs import JobType
from game_predictor_api.storage.database import (
    create_database_engine,
    create_session_factory,
)

from game_predictor_worker.images.production_workflow import ProductionImageImportWorkflow
from game_predictor_worker.images.selection.adapters import (
    AnchoredSequenceRangeRecognizer,
    NoRangeRecognizer,
    build_default_adapters,
)
from game_predictor_worker.images.selection.contracts import SelectionContractError
from game_predictor_worker.images.selection.engine import FastImageSelector
from game_predictor_worker.images.selection.io import (
    JsonSelectionAuditSink,
    load_browser_selection_manifest,
)
from game_predictor_worker.images.selection.job import (
    ImageSelectionJobHandler,
    SqlAlchemyImageSelectionJobStore,
)
from game_predictor_worker.images.selection.manifest import DEFAULT_SELECTOR_MANIFEST
from game_predictor_worker.images.sequence_ocr import PaddleSequenceNumberRecognizer
from game_predictor_worker.imports.dispatch import ImportJobDispatchHandler
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

WORKER_VERSION = "worker-v6"


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
    parser.add_argument(
        "--image-selection-manifest",
        type=Path,
        help="Run the standalone fast selector for one staged browser manifest.",
    )
    parser.add_argument(
        "--image-selection-output",
        type=Path,
        help="Directory for selector checkpoint, JSONL audit and final report.",
    )
    parser.add_argument(
        "--image-selection-ocr-model-root",
        type=Path,
        help="Optional local Paddle recognition model used for bounded range anchors.",
    )
    options = parser.parse_args(arguments)
    if not 5 <= options.lease_seconds <= 3600:
        parser.error("--lease-seconds must be between 5 and 3600.")
    if options.poll_interval <= 0:
        parser.error("--poll-interval must be positive.")
    if (options.image_selection_manifest is None) != (options.image_selection_output is None):
        parser.error(
            "--image-selection-manifest and --image-selection-output must be used together."
        )
    if options.image_selection_manifest is not None:
        if options.poll:
            parser.error("--poll cannot be combined with standalone image selection.")
        return _run_standalone_image_selection(
            options.image_selection_manifest,
            options.image_selection_output,
            ocr_model_root=options.image_selection_ocr_model_root,
        )

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
    image_import_handler = ProductionImageImportWorkflow(
        session_factory,
        artifact_root,
        repository_root=Path.cwd(),
    )
    import_dispatch_handler = ImportJobDispatchHandler(
        import_handler,
        image_import_handler,
    )
    image_selection_handler = ImageSelectionJobHandler(
        SqlAlchemyImageSelectionJobStore(session_factory),
        browser_upload_root=settings.import_root,
        artifact_root=artifact_root,
        repository_root=Path.cwd(),
    )
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
            JobType.IMPORT: import_dispatch_handler,
            JobType.VALIDATE: import_validation_handler,
            JobType.PAYOUT: payout_handler,
            JobType.ANDROID_BUILD: release_handler,
            JobType.IMAGE_SELECTION: image_selection_handler,
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


def _run_standalone_image_selection(
    manifest_path: Path,
    output_root: Path,
    *,
    ocr_model_root: Path | None,
) -> int:
    manifest = manifest_path.resolve(strict=True)
    sources, input_manifest_sha256 = load_browser_selection_manifest(manifest)
    source_root = manifest.parent
    output = output_root.resolve()
    if output == source_root or output.is_relative_to(source_root):
        raise SelectionContractError(
            "IMAGE_SELECTION_OUTPUT_IN_SOURCE",
            "Image selector output must be outside the read-only source staging.",
        )
    range_recognizer: NoRangeRecognizer | AnchoredSequenceRangeRecognizer
    if ocr_model_root is None:
        range_recognizer = NoRangeRecognizer()
        selector_manifest = replace(
            DEFAULT_SELECTOR_MANIFEST,
            range_adapter_version=range_recognizer.version,
        )
    else:
        range_recognizer = AnchoredSequenceRangeRecognizer(
            PaddleSequenceNumberRecognizer(ocr_model_root.resolve(strict=True))
        )
        selector_manifest = DEFAULT_SELECTOR_MANIFEST
    analyzer, verifier = build_default_adapters(
        source_root,
        range_recognizer=range_recognizer,
        manifest=selector_manifest,
    )
    sink = JsonSelectionAuditSink(output)
    result = FastImageSelector(selector_manifest).select(
        sources,
        analyzer=analyzer,
        verifier=verifier,
        audit_sink=sink,
    )
    report_path = sink.write_result(
        result,
        input_manifest_sha256=input_manifest_sha256,
    )
    print(report_path)
    return 0
