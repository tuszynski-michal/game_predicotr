"""Windows-friendly command line entry point for the local job worker."""

from __future__ import annotations

import argparse
import os
import socket
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from game_predictor_api.application.layout_imports import LayoutImportSourceInspector
from game_predictor_api.application.remote_manual_selection_host import (
    RemoteManualSelectionHostService,
)
from game_predictor_api.application.remote_manual_selection_materialization import (
    RemoteManualSelectionHostActionRunner,
    RemoteManualSelectionHostMaterializer,
    RemoteManualSelectionMaterializationLimits,
)
from game_predictor_api.application.remote_manual_selection_recovery import (
    RemoteManualSelectionRecoveryRunner,
)
from game_predictor_api.application.remote_manual_selection_removal import (
    RemoteManualSelectionHostRemover,
    RemoteManualSelectionRemovalLimits,
    RemoteManualSelectionRemovalRunner,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.jobs import JobExecutionSlot, JobType
from game_predictor_api.domain.worker_lanes import WorkerLaneName
from game_predictor_api.storage.database import (
    create_database_engine,
    create_session_factory,
)
from game_predictor_api.storage.worker_lane_repository import SqlAlchemyWorkerLaneRepository

from game_predictor_worker.images.page_geometry_preflight import PageGeometryPreflightHandler
from game_predictor_worker.images.pending_grid_reinference import (
    PendingGridReinferenceHandler,
)
from game_predictor_worker.images.pending_symbol_reinference import (
    PendingSymbolReinferenceHandler,
)
from game_predictor_worker.images.production_workflow import ProductionImageImportWorkflow
from game_predictor_worker.images.selection.adapters import (
    AnchoredSequenceRangeRecognizer,
    GridFirstVisibleSequenceLabelRangeRecognizer,
    IndependentEndpointVisibleSequenceLabelRangeRecognizer,
    LabelLatticeSafeVisibleSequenceLabelRangeRecognizer,
    LayoutAnchoredVisibleSequenceLabelRangeRecognizer,
    NoRangeRecognizer,
    PartialLayoutAnchoredVisibleSequenceLabelRangeRecognizer,
    SequenceValidatedVisibleSequenceLabelRangeRecognizer,
    TwoLabelConsensusVisibleSequenceLabelRangeRecognizer,
    build_default_adapters,
    configure_opencv_thread_budget,
)
from game_predictor_worker.images.selection.contracts import SelectionContractError
from game_predictor_worker.images.selection.engine import (
    DEFAULT_PARALLEL_SCAN_PREFETCH,
    DEFAULT_PARALLEL_SCAN_WORKERS,
    FastImageSelector,
)
from game_predictor_worker.images.selection.io import (
    JsonSelectionAuditSink,
    load_browser_selection_manifest,
)
from game_predictor_worker.images.selection.job import (
    ImageSelectionJobHandler,
    SqlAlchemyImageSelectionJobStore,
)
from game_predictor_worker.images.selection.manifest import (
    DEFAULT_SELECTOR_MANIFEST,
    LABEL_LATTICE_SAFE_RANGE_ADAPTER_VERSION,
    SEQUENCE_VALIDATED_RANGE_ADAPTER_VERSION,
    STAGED_OCR_RANGE_ADAPTER_VERSION,
    TWO_LABEL_CONSENSUS_RANGE_ADAPTER_VERSION,
    ProgressiveVisibleLabelFallbackPolicy,
)
from game_predictor_worker.images.selection.ports import SequenceRangeRecognizer
from game_predictor_worker.images.sequence_ocr import PaddleSequenceNumberRecognizer
from game_predictor_worker.imports.dispatch import ImportJobDispatchHandler
from game_predictor_worker.imports.handler import LayoutImportStagingHandler
from game_predictor_worker.imports.store import SqlAlchemyLayoutImportStagingStore
from game_predictor_worker.imports.validation_dispatch import ValidationJobDispatchHandler
from game_predictor_worker.imports.validation_handler import (
    LayoutImportValidationHandler,
)
from game_predictor_worker.jobs.lane_runtime import WorkerLaneHeartbeat
from game_predictor_worker.jobs.runtime import JobHandler, LocalJobWorker
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
from game_predictor_worker.storage_gc import StorageGcHandler
from game_predictor_worker.symbols.review_backfill import SymbolCellReviewBackfillHandler
from game_predictor_worker.symbols.review_bulk import SymbolCellReviewBulkHandler
from game_predictor_worker.symbols.training_job import (
    SymbolTrainingJobHandler,
    SymbolTrainingJobStore,
)

WORKER_VERSION = "worker-v10"
GENERAL_LANE = "general"
IMAGE_SELECTION_LANE = "image-selection"
DEFAULT_GENERAL_THREAD_BUDGET = 7
DEFAULT_IMAGE_SELECTION_THREAD_BUDGET = 5


def _remote_host_action_cycle(
    recovery_runner: RemoteManualSelectionRecoveryRunner | None,
    removal_runner: RemoteManualSelectionRemovalRunner | None,
    materialization_runner: RemoteManualSelectionHostActionRunner,
) -> Callable[[], None]:
    def run() -> None:
        if recovery_runner is not None:
            recovery_runner.run_bounded_cycle()
        if removal_runner is not None:
            removal_runner.run_bounded_cycle()
        materialization_runner.run_bounded_cycle()

    return run


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
        "--lane",
        choices=(GENERAL_LANE, IMAGE_SELECTION_LANE),
        default=GENERAL_LANE,
        help=(
            "Claim only general jobs or only image-selection jobs. "
            "Run one polling process for each lane when both workflows are needed."
        ),
    )
    parser.add_argument(
        "--cpu-thread-budget",
        type=int,
        default=None,
        help="Cooperative per-process budget for scan and native library threads.",
    )
    parser.add_argument(
        "--lane-instance-token",
        type=UUID,
        default=None,
        help="Supervisor-provided fencing token for this worker process.",
    )
    parser.add_argument(
        "--mark-lane-stopped",
        action="store_true",
        help="Persist a fenced controlled-stop marker and exit without polling.",
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
    parser.add_argument(
        "--first-sequence-number",
        type=int,
        help="First layout number visible in the standalone selection input.",
    )
    options = parser.parse_args(arguments)
    if not 5 <= options.lease_seconds <= 3600:
        parser.error("--lease-seconds must be between 5 and 3600.")
    if options.poll_interval <= 0:
        parser.error("--poll-interval must be positive.")
    default_thread_budget = (
        DEFAULT_IMAGE_SELECTION_THREAD_BUDGET
        if options.lane == IMAGE_SELECTION_LANE
        else DEFAULT_GENERAL_THREAD_BUDGET
    )
    thread_budget = options.cpu_thread_budget or default_thread_budget
    if not 1 <= thread_budget <= 64:
        parser.error("--cpu-thread-budget must be between 1 and 64.")
    if options.mark_lane_stopped and options.lane_instance_token is None:
        parser.error("--mark-lane-stopped requires --lane-instance-token.")
    if options.mark_lane_stopped and options.poll:
        parser.error("--mark-lane-stopped cannot be combined with --poll.")
    if (options.image_selection_manifest is None) != (options.image_selection_output is None):
        parser.error(
            "--image-selection-manifest and --image-selection-output must be used together."
        )
    if options.first_sequence_number is not None and options.first_sequence_number < 1:
        parser.error("--first-sequence-number must be positive.")
    # Parallel handlers own the cooperative process budget.  Native libraries
    # stay single-threaded so seven registered pages cannot fan out into 49
    # OpenCV/BLAS threads on the eight-logical-CPU owner workstation.
    native_thread_budget = 1
    _configure_native_thread_budget(native_thread_budget)
    configure_opencv_thread_budget()
    if options.image_selection_manifest is not None:
        if options.poll:
            parser.error("--poll cannot be combined with standalone image selection.")
        if options.first_sequence_number is None:
            parser.error(
                "--first-sequence-number is required for standalone anchored image selection."
            )
        return _run_standalone_image_selection(
            options.image_selection_manifest,
            options.image_selection_output,
            ocr_model_root=options.image_selection_ocr_model_root,
            first_sequence_number=options.first_sequence_number,
        )

    settings = ApiSettings.from_environment()
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    runtime_lane = (
        WorkerLaneName.IMAGE_SELECTION
        if options.lane == IMAGE_SELECTION_LANE
        else WorkerLaneName.GENERAL
    )
    if options.mark_lane_stopped:
        try:
            stopped = SqlAlchemyWorkerLaneRepository(session_factory).stop(
                lane=runtime_lane,
                instance_token=options.lane_instance_token,
                stopped_at=datetime.now(UTC),
            )
            print("stopped" if stopped else "fenced")
            return 0
        finally:
            engine.dispose()
    store = SqlAlchemyWorkerJobStore(session_factory)
    artifact_root = options.artifact_root.resolve()
    handlers: dict[JobType, JobHandler]
    materialization_runner: RemoteManualSelectionHostActionRunner | None = None
    removal_runner: RemoteManualSelectionRemovalRunner | None = None
    recovery_runner: RemoteManualSelectionRecoveryRunner | None = None
    if options.lane == IMAGE_SELECTION_LANE:
        # TASK-0194 showed that two Paddle/OpenCV verifier instances contend on
        # the owner's CPU and make the real first-200 profile slower. Keep the
        # deterministic parallel adapter available, but do not activate it in
        # the production lane without a new hardware-specific gate.
        verification_workers = 1
        scan_workers = min(
            DEFAULT_PARALLEL_SCAN_WORKERS,
            max(1, thread_budget - verification_workers),
        )
        handlers = {
            JobType.IMAGE_SELECTION: ImageSelectionJobHandler(
                SqlAlchemyImageSelectionJobStore(session_factory),
                browser_upload_root=settings.import_root,
                artifact_root=artifact_root,
                repository_root=Path.cwd(),
                scan_workers=scan_workers,
                scan_prefetch=DEFAULT_PARALLEL_SCAN_PREFETCH,
                verification_workers=verification_workers,
            )
        }
        execution_slot = JobExecutionSlot.IMAGE_SELECTION
    else:
        remote_selection_host = RemoteManualSelectionHostService(lambda: None)
        recovery_runner = RemoteManualSelectionRecoveryRunner(
            session_factory,
            remote_selection_host,
            enabled=settings.remote_selection_recovery_enabled,
            upload_timeout=timedelta(seconds=settings.remote_selection_upload_timeout_seconds),
            limit=settings.remote_selection_recovery_limit,
        )
        materialization_runner = RemoteManualSelectionHostActionRunner(
            session_factory,
            RemoteManualSelectionHostMaterializer(remote_selection_host),
            worker_id=f"{options.worker_id}-remote-materialization",
            limits=RemoteManualSelectionMaterializationLimits(
                lease_duration=timedelta(
                    seconds=settings.remote_selection_materialization_lease_seconds
                ),
                max_attempts=settings.remote_selection_materialization_max_attempts,
                max_actions_per_cycle=(
                    settings.remote_selection_materialization_max_actions_per_cycle
                ),
            ),
        )
        if settings.remote_selection_deselect_enabled:
            removal_runner = RemoteManualSelectionRemovalRunner(
                session_factory,
                RemoteManualSelectionHostRemover(remote_selection_host),
                worker_id=f"{options.worker_id}-remote-removal",
                limits=RemoteManualSelectionRemovalLimits(
                    lease_duration=timedelta(
                        seconds=settings.remote_selection_materialization_lease_seconds
                    ),
                    max_attempts=settings.remote_selection_materialization_max_attempts,
                    max_actions_per_cycle=(
                        settings.remote_selection_materialization_max_actions_per_cycle
                    ),
                ),
            )
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
        validation_dispatch_handler = ValidationJobDispatchHandler(
            import_validation_handler,
            PageGeometryPreflightHandler(
                artifact_root=artifact_root,
                registration_workers=thread_budget,
            ),
        )
        image_import_handler = ProductionImageImportWorkflow(
            session_factory,
            artifact_root,
            repository_root=Path.cwd(),
            hard_reserve_bytes=settings.storage_hard_reserve_gib * 1024**3,
            resume_target_bytes=settings.storage_target_gib * 1024**3,
        )
        import_dispatch_handler = ImportJobDispatchHandler(
            import_handler,
            image_import_handler,
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
        handlers = {
            JobType.IMPORT: import_dispatch_handler,
            JobType.VALIDATE: validation_dispatch_handler,
            JobType.PAYOUT: payout_handler,
            JobType.ANDROID_BUILD: release_handler,
            JobType.SYMBOL_TRAINING: SymbolTrainingJobHandler(
                SymbolTrainingJobStore(session_factory, artifact_root)
            ),
            JobType.IMAGE_SYMBOL_REINFERENCE: PendingSymbolReinferenceHandler(
                session_factory,
                artifact_root,
                repository_root=Path.cwd(),
            ),
            JobType.IMAGE_GRID_REINFERENCE: PendingGridReinferenceHandler(
                session_factory,
                artifact_root,
            ),
            JobType.IMAGE_SYMBOL_REVIEW_BULK: SymbolCellReviewBulkHandler(session_factory),
            JobType.IMAGE_SYMBOL_REVIEW_BACKFILL: SymbolCellReviewBackfillHandler(session_factory),
            JobType.STORAGE_GC: StorageGcHandler(
                session_factory,
                artifact_root,
                settings.import_root,
            ),
        }
        execution_slot = JobExecutionSlot.GENERAL
    worker = LocalJobWorker(
        store,
        handlers,
        worker_id=options.worker_id,
        worker_version=f"{WORKER_VERSION}-{options.lane}",
        execution_slot=execution_slot,
        lease_duration=timedelta(seconds=options.lease_seconds),
        auxiliary_work=(
            _remote_host_action_cycle(
                recovery_runner,
                removal_runner,
                materialization_runner,
            )
            if materialization_runner is not None
            else None
        ),
    )
    lane_heartbeat = WorkerLaneHeartbeat(
        SqlAlchemyWorkerLaneRepository(session_factory),
        lane=runtime_lane,
        worker_id=options.worker_id,
        worker_version=f"{WORKER_VERSION}-{options.lane}",
        process_id=os.getpid(),
        thread_budget=thread_budget,
        instance_token=options.lane_instance_token,
    )
    try:
        with lane_heartbeat:
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


def _configure_native_thread_budget(thread_budget: int) -> None:
    value = str(thread_budget)
    for variable in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        os.environ[variable] = value


def _run_standalone_image_selection(
    manifest_path: Path,
    output_root: Path,
    *,
    ocr_model_root: Path | None,
    first_sequence_number: int | None,
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
    range_recognizer: SequenceRangeRecognizer
    fallback_range_recognizer: SequenceRangeRecognizer | None = None
    fast_range_recognizer: SequenceRangeRecognizer | None = None
    if ocr_model_root is None:
        range_recognizer = NoRangeRecognizer()
        selector_manifest = replace(
            DEFAULT_SELECTOR_MANIFEST,
            range_adapter_version=range_recognizer.version,
        )
    else:
        ocr = PaddleSequenceNumberRecognizer(ocr_model_root.resolve(strict=True))
        if DEFAULT_SELECTOR_MANIFEST.algorithm_version == "fast-image-selector-v10.4":
            range_recognizer = GridFirstVisibleSequenceLabelRangeRecognizer(ocr)
        else:
            range_recognizer = AnchoredSequenceRangeRecognizer(ocr)
            fallback_policy = DEFAULT_SELECTOR_MANIFEST.progressive_visible_label_fallback_policy
            assert fallback_policy is not None
            if DEFAULT_SELECTOR_MANIFEST.layout_anchor_policy is not None:
                anchor_policy = DEFAULT_SELECTOR_MANIFEST.layout_anchor_policy
                if (
                    DEFAULT_SELECTOR_MANIFEST.range_adapter_version
                    == SEQUENCE_VALIDATED_RANGE_ADAPTER_VERSION
                ):
                    window_policy = DEFAULT_SELECTOR_MANIFEST.contiguous_sequence_window_policy
                    assert window_policy is not None
                    fallback_range_recognizer = (
                        SequenceValidatedVisibleSequenceLabelRangeRecognizer(
                            ocr,
                            fallback_policy,
                            anchor_policy,
                            window_policy,
                        )
                    )
                elif DEFAULT_SELECTOR_MANIFEST.range_adapter_version in {
                    STAGED_OCR_RANGE_ADAPTER_VERSION,
                    TWO_LABEL_CONSENSUS_RANGE_ADAPTER_VERSION,
                }:
                    window_policy = DEFAULT_SELECTOR_MANIFEST.contiguous_sequence_window_policy
                    assert window_policy is not None
                    fallback_range_recognizer = (
                        TwoLabelConsensusVisibleSequenceLabelRangeRecognizer(
                            ocr,
                            fallback_policy,
                            anchor_policy,
                            window_policy,
                        )
                    )
                    if (
                        DEFAULT_SELECTOR_MANIFEST.range_adapter_version
                        == STAGED_OCR_RANGE_ADAPTER_VERSION
                    ):
                        staged_policy = DEFAULT_SELECTOR_MANIFEST.staged_ocr_policy
                        assert staged_policy is not None
                        fast_range_recognizer = (
                            TwoLabelConsensusVisibleSequenceLabelRangeRecognizer(
                                ocr,
                                ProgressiveVisibleLabelFallbackPolicy(
                                    candidate_levels=staged_policy.broad_candidate_levels,
                                ),
                                anchor_policy,
                                window_policy,
                            )
                        )
                elif (
                    DEFAULT_SELECTOR_MANIFEST.range_adapter_version
                    == LABEL_LATTICE_SAFE_RANGE_ADAPTER_VERSION
                ):
                    window_policy = DEFAULT_SELECTOR_MANIFEST.contiguous_sequence_window_policy
                    assert window_policy is not None
                    fallback_range_recognizer = LabelLatticeSafeVisibleSequenceLabelRangeRecognizer(
                        ocr,
                        fallback_policy,
                        anchor_policy,
                        window_policy,
                    )
                else:
                    recognizer_type = (
                        PartialLayoutAnchoredVisibleSequenceLabelRangeRecognizer
                        if anchor_policy.enable_partial_grid_recovery
                        else LayoutAnchoredVisibleSequenceLabelRangeRecognizer
                    )
                    fallback_range_recognizer = recognizer_type(
                        ocr,
                        fallback_policy,
                        anchor_policy,
                    )
            else:
                fallback_range_recognizer = IndependentEndpointVisibleSequenceLabelRangeRecognizer(
                    ocr,
                    fallback_policy,
                )
        selector_manifest = DEFAULT_SELECTOR_MANIFEST
    analyzer, verifier = build_default_adapters(
        source_root,
        range_recognizer=range_recognizer,
        fallback_range_recognizer=fallback_range_recognizer,
        fast_range_recognizer=fast_range_recognizer,
        manifest=selector_manifest,
    )
    sink = JsonSelectionAuditSink(output)
    result = FastImageSelector(
        selector_manifest,
        scan_workers=DEFAULT_PARALLEL_SCAN_WORKERS,
        scan_prefetch=DEFAULT_PARALLEL_SCAN_PREFETCH,
    ).select(
        sources,
        analyzer=analyzer,
        verifier=verifier,
        audit_sink=sink,
        first_sequence_number=first_sequence_number,
    )
    report_path = sink.write_result(
        result,
        input_manifest_sha256=input_manifest_sha256,
    )
    print(report_path)
    return 0
