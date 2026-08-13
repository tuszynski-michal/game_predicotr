"""Durable job integration for the bounded representative-image selector."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import UUID, uuid5

from game_predictor_api.domain.image_selections import (
    ImageSelectionCandidateDecision,
    ImageSelectionExecutionMode,
    ImageSelectionGroupStatus,
    ImageSelectionSequenceDirection,
)
from game_predictor_api.domain.jobs import Job, JobConflictError, JobStatus
from game_predictor_api.storage.image_selection_repository import (
    SqlAlchemyImageSelectionRepository,
)
from game_predictor_api.storage.models import (
    ImageSelectionCandidateModel,
    ImageSelectionGroupModel,
    ImageSelectionRunModel,
    JobModel,
)
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.images.sequence_ocr import PaddleSequenceNumberRecognizer
from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError

from .adapters import (
    AccuracyFirstVisibleSequenceLabelRangeRecognizer,
    AdaptiveVisibleSequenceLabelRangeRecognizer,
    AnchoredSequenceRangeRecognizer,
    BestEffortVisibleSequenceLabelRangeRecognizer,
    ContiguousWindowVisibleSequenceLabelRangeRecognizer,
    DeterministicParallelCandidateVerifier,
    FusedRangeEvidenceVisibleSequenceLabelRangeRecognizer,
    GridFirstVisibleSequenceLabelRangeRecognizer,
    IndependentEndpointVisibleSequenceLabelRangeRecognizer,
    LabelLatticeSafeVisibleSequenceLabelRangeRecognizer,
    LayoutAnchoredVisibleSequenceLabelRangeRecognizer,
    PartialLayoutAnchoredVisibleSequenceLabelRangeRecognizer,
    ProgressiveVisibleSequenceLabelRangeRecognizer,
    TwoLabelConsensusVisibleSequenceLabelRangeRecognizer,
    VisibleSequenceLabelRangeRecognizer,
    build_default_adapters,
)
from .cache import (
    CachedCandidateVerifier,
    CachedCheapImageAnalyzer,
    FileImageScanObservationCache,
    FileImageVerificationCache,
)
from .contracts import (
    CandidateDecision,
    CandidateResult,
    CandidateVerifier,
    CheapImageAnalyzer,
    CheapImageObservation,
    ImageQualityMetrics,
    ImageSelectionResult,
    ImageSelectionSource,
    SelectionAuditSink,
    SelectionContractError,
    SelectionGroupResult,
    SelectionGroupStatus,
    SelectorCheckpoint,
    SelectorResumeState,
    SequenceRange,
)
from .engine import FastImageSelector
from .io import load_browser_selection_manifest
from .manifest import (
    ACCURACY_FIRST_SELECTOR_VERSIONS,
    APPEARANCE_ONLY_SELECTOR_VERSIONS,
    BEST_EFFORT_SELECTOR_VERSIONS,
    CONTIGUOUS_WINDOW_RANGE_ADAPTER_VERSION,
    DEFAULT_SELECTOR_MANIFEST,
    FUSED_RANGE_EVIDENCE_ADAPTER_VERSION,
    GRID_FIRST_RANGE_ADAPTER_VERSION,
    INDEPENDENT_ENDPOINT_RANGE_ADAPTER_VERSION,
    LABEL_LATTICE_SAFE_RANGE_ADAPTER_VERSION,
    LAYOUT_ANCHORED_RANGE_ADAPTER_VERSION,
    ORDERED_SELECTOR_VERSIONS,
    OWNER_ANCHORED_SELECTOR_VERSIONS,
    PARTIAL_LAYOUT_ANCHORED_RANGE_ADAPTER_VERSION,
    TWO_LABEL_CONSENSUS_RANGE_ADAPTER_VERSION,
    SelectorManifest,
    selector_manifest_for_fingerprint,
)
from .output import (
    CuratedImageOutputPublisher,
    PublishedImageSelection,
    verify_curated_image_manifest,
)
from .ports import SequenceRangeRecognizer
from .recovery import (
    RecoveryEvaluationProgress,
    RecoveryProjection,
    RecoverySourceGroup,
    evaluate_recovery,
)
from .telemetry import StageTimingCollector

BROWSER_SELECTION_DIRECTORY = "browser-selections"
BROWSER_SELECTION_MANIFEST = "_browser_manifest.json"
BROWSER_UPLOAD_METRICS = "_upload_metrics.json"
CHECKPOINT_SCHEMA_VERSION = 1
DIAGNOSTIC_CONTRACT = "image-selection-job-diagnostics-v1"
MAX_ERROR_SAMPLES = 100


@dataclass(frozen=True, slots=True)
class ImageSelectionJobRun:
    id: UUID
    job_id: UUID
    source_selection_id: UUID
    input_manifest_sha256: str
    selector_fingerprint: str
    output_manifest_sha256: str | None
    output_manifest_relative_path: str | None
    sequence_direction: ImageSelectionSequenceDirection = ImageSelectionSequenceDirection.ASCENDING
    first_sequence_number: int | None = None
    execution_mode: ImageSelectionExecutionMode = ImageSelectionExecutionMode.FULL
    source_run_id: UUID | None = None
    source_snapshot_sha256: str | None = None


class ImageSelectionJobStore(Protocol):
    def get_run_for_job(self, job_id: UUID) -> ImageSelectionJobRun: ...

    def load_groups(self, run_id: UUID) -> tuple[SelectionGroupResult, ...]: ...

    def load_recovery_source(
        self,
        run_id: UUID,
    ) -> tuple[str, tuple[RecoverySourceGroup, ...]]: ...

    def persist_groups(
        self,
        *,
        job_id: UUID,
        run_id: UUID,
        lease_token: UUID,
        groups: Sequence[SelectionGroupResult],
        group_sources: Mapping[int, Sequence[CheapImageObservation]],
        persisted_at: datetime,
    ) -> None: ...

    def record_output(
        self,
        *,
        job_id: UUID,
        run_id: UUID,
        lease_token: UUID,
        published: PublishedImageSelection,
        persisted_at: datetime,
    ) -> None: ...

    def persist_recovery_projection(
        self,
        *,
        job_id: UUID,
        run_id: UUID,
        source_run_id: UUID,
        expected_source_snapshot_sha256: str,
        lease_token: UUID,
        projection: RecoveryProjection,
        persisted_at: datetime,
    ) -> None: ...


AdapterFactory = Callable[
    [Path, SelectorManifest],
    tuple[CheapImageAnalyzer, CandidateVerifier],
]


class ImageSelectionJobHandler:
    """Run, resume, pause and publish one durable image-selection job."""

    def __init__(
        self,
        store: ImageSelectionJobStore,
        *,
        browser_upload_root: Path,
        artifact_root: Path,
        repository_root: Path,
        adapter_factory: AdapterFactory | None = None,
        selector_manifest: SelectorManifest = DEFAULT_SELECTOR_MANIFEST,
        scan_workers: int = 1,
        scan_prefetch: int | None = None,
        verification_workers: int = 1,
    ) -> None:
        if not 1 <= verification_workers <= 2:
            raise ValueError("verification_workers must be one or two.")
        self._store = store
        self._browser_upload_root = browser_upload_root.resolve() / BROWSER_SELECTION_DIRECTORY
        self._artifact_root = artifact_root.resolve()
        self._repository_root = repository_root.resolve()
        self._selector_manifest = selector_manifest
        self._scan_workers = scan_workers
        self._scan_prefetch = scan_prefetch
        self._verification_workers = verification_workers
        self._adapter_factory = adapter_factory
        self._publisher = CuratedImageOutputPublisher(self._artifact_root)
        self._scan_cache = FileImageScanObservationCache(self._artifact_root)
        self._verification_cache = FileImageVerificationCache(self._artifact_root)

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        run = self._store.get_run_for_job(job.id)
        selector_manifest: SelectorManifest | None
        if run.selector_fingerprint != self._selector_manifest.fingerprint:
            selector_manifest = selector_manifest_for_fingerprint(run.selector_fingerprint)
        else:
            selector_manifest = self._selector_manifest
        if selector_manifest is None:
            raise JobHandlerError(
                "IMAGE_SELECTION_SELECTOR_MISMATCH",
                "The durable run references another selector fingerprint.",
            )
        if (
            selector_manifest.algorithm_version in OWNER_ANCHORED_SELECTOR_VERSIONS
            and run.first_sequence_number is None
        ):
            raise JobHandlerError(
                "IMAGE_SELECTION_FIRST_SEQUENCE_REQUIRED",
                "The current selector requires the first layout sequence number.",
            )
        source_root = self._managed_source_root(run.source_selection_id)
        manifest_path = source_root / BROWSER_SELECTION_MANIFEST
        try:
            sources, manifest_sha256 = load_browser_selection_manifest(manifest_path)
        except SelectionContractError as error:
            raise JobHandlerError(error.code, str(error)) from error
        if manifest_sha256 != run.input_manifest_sha256:
            raise JobHandlerError(
                "IMAGE_SELECTION_INPUT_MANIFEST_CHANGED",
                "The staged browser manifest differs from the durable run.",
            )
        if run.output_manifest_sha256 is not None:
            try:
                self._verify_existing_output(run)
            except SelectionContractError as error:
                raise JobHandlerError(error.code, str(error)) from error
            return

        if run.execution_mode is ImageSelectionExecutionMode.RANGE_RECOVERY:
            self._run_range_recovery(
                context,
                job,
                run=run,
                selector_manifest=selector_manifest,
                source_root=source_root,
            )
            return

        try:
            telemetry = StageTimingCollector()
            persisted_groups = self._store.load_groups(run.id)
            resume_state = _resume_state(job.checkpoint_payload)
            existing_groups = _committed_groups(persisted_groups, resume_state)
            if self._adapter_factory is None:
                analyzer, verifier = self._default_adapter_factory(
                    source_root,
                    selector_manifest,
                    telemetry,
                )
            else:
                analyzer, verifier = self._adapter_factory(
                    source_root,
                    selector_manifest,
                )
            cached_analyzer = CachedCheapImageAnalyzer(
                analyzer,
                self._scan_cache,
                scan_adapter_fingerprint=selector_manifest.scan_adapter_fingerprint,
            )
            cached_verifier = CachedCandidateVerifier(
                verifier,
                self._verification_cache,
                selector_fingerprint=selector_manifest.fingerprint,
            )
            sink = _DurableSelectionSink(
                context,
                self._store,
                run=run,
                total=len(sources),
                upload_duration_seconds=_upload_duration(source_root),
                prior_checkpoint=job.checkpoint_payload,
                artifact_root=self._artifact_root,
                existing_groups=existing_groups,
                telemetry=telemetry,
                scan_cache_metrics=cached_analyzer.snapshot,
                verification_cache_metrics=cached_verifier.snapshot,
            )
            result = FastImageSelector(
                selector_manifest,
                scan_workers=self._scan_workers,
                scan_prefetch=self._scan_prefetch,
            ).select(
                sources,
                analyzer=cached_analyzer,
                verifier=cached_verifier,
                audit_sink=sink,
                resume_state=resume_state,
                existing_groups=existing_groups,
                sequence_direction=run.sequence_direction.value,
                first_sequence_number=run.first_sequence_number,
            )
        except SelectionContractError as error:
            raise JobHandlerError(error.code, str(error)) from error

        try:
            if any(
                group.status
                in {
                    SelectionGroupStatus.MANUAL_REQUIRED,
                    SelectionGroupStatus.RANGE_REQUIRED,
                }
                for group in result.groups
            ):
                sink.write_diagnostics(result)
                sink.checkpoint_stage(
                    result.checkpoint,
                    stage="image_selection:manual_review",
                )
                context.wait_for_review()

            sink.write_diagnostics(result)
            with telemetry.measure("output"):
                published = self._publisher.publish(
                    run_id=run.id,
                    source_root=source_root,
                    input_manifest_sha256=run.input_manifest_sha256,
                    result=result,
                    source_resolver=lambda candidate: self._resolve_selected_source(
                        source_root,
                        candidate,
                    ),
                    progress_callback=lambda completed, total: sink.publication_checkpoint(
                        result.checkpoint,
                        completed=completed,
                        total=total,
                    ),
                )
            telemetry.increment("outputFiles", len(published.manifest.entries))
            with telemetry.measure("persistence"):
                self._store.record_output(
                    job_id=job.id,
                    run_id=run.id,
                    lease_token=context.lease_token,
                    published=published,
                    persisted_at=context.now(),
                )
            telemetry.increment("persistenceWrites")
            sink.checkpoint_stage(
                result.checkpoint,
                stage="image_selection:ready_for_import",
            )
        except SelectionContractError as error:
            raise JobHandlerError(error.code, str(error)) from error

    def _run_range_recovery(
        self,
        context: JobExecutionContext,
        job: Job,
        *,
        run: ImageSelectionJobRun,
        selector_manifest: SelectorManifest,
        source_root: Path,
    ) -> None:
        if run.source_run_id is None or run.source_snapshot_sha256 is None:
            raise JobHandlerError(
                "IMAGE_SELECTION_RECOVERY_SOURCE_INVALID",
                "A range-recovery run has no immutable source snapshot.",
            )
        try:
            current_snapshot, source_groups = self._store.load_recovery_source(run.source_run_id)
            if current_snapshot != run.source_snapshot_sha256:
                raise SelectionContractError(
                    "IMAGE_SELECTION_RECOVERY_SOURCE_CHANGED",
                    "The source run changed after the recovery run was created.",
                )
            checkpoint = job.checkpoint_payload or {}
            projection_complete = checkpoint.get("recovery_projection_complete") is True
            if projection_complete:
                persisted_groups = self._store.load_groups(run.id)
                if not persisted_groups:
                    raise SelectionContractError(
                        "IMAGE_SELECTION_RECOVERY_PROJECTION_MISSING",
                        "The recovery checkpoint has no durable group projection.",
                    )
                result = _recovery_result(
                    run,
                    selector_manifest,
                    persisted_groups,
                    checkpoint,
                )
            else:
                result = self._build_recovery_projection(
                    context,
                    run=run,
                    selector_manifest=selector_manifest,
                    source_root=source_root,
                    source_groups=source_groups,
                )
            self._finish_recovery_run(
                context,
                run=run,
                source_root=source_root,
                result=result,
            )
        except SelectionContractError as error:
            raise JobHandlerError(error.code, str(error)) from error

    def _build_recovery_projection(
        self,
        context: JobExecutionContext,
        *,
        run: ImageSelectionJobRun,
        selector_manifest: SelectorManifest,
        source_root: Path,
        source_groups: tuple[RecoverySourceGroup, ...],
    ) -> ImageSelectionResult:
        source_run_id = run.source_run_id
        source_snapshot_sha256 = run.source_snapshot_sha256
        if source_run_id is None or source_snapshot_sha256 is None:
            raise SelectionContractError(
                "IMAGE_SELECTION_RECOVERY_SOURCE_INVALID",
                "A range-recovery run has no immutable source snapshot.",
            )
        telemetry = StageTimingCollector()
        if self._adapter_factory is None:
            analyzer, verifier = self._default_adapter_factory(
                source_root,
                selector_manifest,
                telemetry,
            )
        else:
            analyzer, verifier = self._adapter_factory(source_root, selector_manifest)
        cached_analyzer = CachedCheapImageAnalyzer(
            analyzer,
            self._scan_cache,
            scan_adapter_fingerprint=selector_manifest.scan_adapter_fingerprint,
        )
        cached_verifier = CachedCandidateVerifier(
            verifier,
            self._verification_cache,
            selector_fingerprint=selector_manifest.fingerprint,
        )
        if run.first_sequence_number is None:
            raise SelectionContractError(
                "IMAGE_SELECTION_FIRST_SEQUENCE_REQUIRED",
                "Range recovery requires the source sequence origin.",
            )

        def checkpoint_recovery(progress: RecoveryEvaluationProgress) -> None:
            context.checkpoint(
                checkpoint_payload={
                    "schema_version": CHECKPOINT_SCHEMA_VERSION,
                    "workflow": "image_selection_range_recovery",
                    "run_id": str(run.id),
                    "source_run_id": str(run.source_run_id),
                    "source_snapshot_sha256": run.source_snapshot_sha256,
                    "recovery_projection_complete": False,
                    "block_count": progress.block_count,
                    "completed_blocks": progress.completed_blocks,
                    "candidate_count": progress.candidate_count,
                    "scan_failure_count": progress.scan_failure_count,
                    "verification_count": progress.verification_count,
                },
                stage="image_selection:recovering_ranges",
                current=progress.completed_candidates,
                total=progress.candidate_count,
                success_count=0,
                failure_count=progress.scan_failure_count,
                review_count=0,
            )

        evaluation = evaluate_recovery(
            source_groups,
            manifest=selector_manifest,
            analyzer=cached_analyzer,
            verifier=cached_verifier,
            sequence_direction=run.sequence_direction.value,
            first_sequence_number=run.first_sequence_number,
            scan_workers=self._scan_workers,
            scan_prefetch=self._scan_prefetch,
            progress_callback=checkpoint_recovery,
        )
        projection = evaluation.projection
        self._store.persist_recovery_projection(
            job_id=run.job_id,
            run_id=run.id,
            source_run_id=source_run_id,
            expected_source_snapshot_sha256=source_snapshot_sha256,
            lease_token=context.lease_token,
            projection=projection,
            persisted_at=context.now(),
        )
        result = ImageSelectionResult(
            selector_version=selector_manifest.algorithm_version,
            selector_fingerprint=selector_manifest.fingerprint,
            input_count=evaluation.candidate_count,
            groups=projection.groups,
            checkpoint=SelectorCheckpoint(
                schema_version=CHECKPOINT_SCHEMA_VERSION,
                selector_fingerprint=selector_manifest.fingerprint,
                next_order_index=evaluation.candidate_count,
                processed_count=evaluation.candidate_count,
                finalized_group_count=len(projection.groups),
            ),
            scan_failure_count=evaluation.scan_failure_count,
            verification_count=evaluation.verification_count,
        )
        payload = _recovery_checkpoint_payload(
            run,
            result,
            block_count=evaluation.block_count,
        )
        selected, review = _recovery_counts(result.groups)
        context.checkpoint(
            checkpoint_payload=payload,
            stage="image_selection:recovery_projection_ready",
            current=evaluation.candidate_count,
            total=evaluation.candidate_count,
            success_count=selected,
            failure_count=evaluation.scan_failure_count,
            review_count=review,
        )
        return result

    def _finish_recovery_run(
        self,
        context: JobExecutionContext,
        *,
        run: ImageSelectionJobRun,
        source_root: Path,
        result: ImageSelectionResult,
    ) -> None:
        selected, review = _recovery_counts(result.groups)
        if review:
            context.wait_for_review()
        payload = _recovery_checkpoint_payload(
            run,
            result,
            block_count=_checkpoint_int(context.job.checkpoint_payload, "block_count"),
        )

        def publication_checkpoint(completed: int, total: int) -> None:
            if completed != total and completed % 16 != 0:
                return
            context.checkpoint(
                checkpoint_payload={
                    **payload,
                    "publication": {"completed": completed, "total": total},
                },
                stage="image_selection:writing_manifest",
                current=completed,
                total=total,
                success_count=selected,
                failure_count=result.scan_failure_count,
                review_count=0,
            )

        published = self._publisher.publish(
            run_id=run.id,
            source_root=source_root,
            input_manifest_sha256=run.input_manifest_sha256,
            result=result,
            source_resolver=lambda candidate: self._resolve_selected_source(
                source_root,
                candidate,
            ),
            progress_callback=publication_checkpoint,
        )
        self._store.record_output(
            job_id=run.job_id,
            run_id=run.id,
            lease_token=context.lease_token,
            published=published,
            persisted_at=context.now(),
        )
        context.checkpoint(
            checkpoint_payload=payload,
            stage="image_selection:ready_for_import",
            current=result.input_count,
            total=result.input_count,
            success_count=selected,
            failure_count=result.scan_failure_count,
            review_count=0,
        )

    def _managed_source_root(self, selection_id: UUID) -> Path:
        try:
            candidate = (self._browser_upload_root / str(selection_id)).resolve(strict=True)
        except OSError as error:
            raise JobHandlerError(
                "IMAGE_SELECTION_SOURCE_MISSING",
                "The managed browser staging for this run is unavailable.",
            ) from error
        if not candidate.is_relative_to(self._browser_upload_root) or not candidate.is_dir():
            raise JobHandlerError(
                "IMAGE_SELECTION_SOURCE_MISSING",
                "The managed browser staging for this run is unavailable.",
            )
        return candidate

    def build_runtime_adapters(
        self,
        source_root: Path,
        manifest: SelectorManifest,
        telemetry: StageTimingCollector,
    ) -> tuple[CheapImageAnalyzer, CandidateVerifier]:
        """Build the exact adapter graph used by a durable selection job."""

        return self._default_adapter_factory(source_root, manifest, telemetry)

    def _verify_existing_output(self, run: ImageSelectionJobRun) -> None:
        if run.output_manifest_relative_path is None or run.output_manifest_sha256 is None:
            raise JobHandlerError(
                "IMAGE_SELECTION_MANIFEST_MISMATCH",
                "The durable output reference is incomplete.",
            )
        manifest = _safe_artifact_file(
            self._artifact_root,
            run.output_manifest_relative_path,
        )
        verify_curated_image_manifest(
            manifest.parent,
            expected_manifest_sha256=run.output_manifest_sha256,
            expected_run_id=run.id,
        )

    def _resolve_selected_source(
        self,
        source_root: Path,
        candidate: CandidateResult,
    ) -> Path:
        relative = candidate.source.stored_relative_path
        if relative.startswith("data/working/is-manual/"):
            return _safe_artifact_file(self._artifact_root, relative)
        return _safe_child(source_root, relative)

    def _default_adapter_factory(
        self,
        source_root: Path,
        manifest: SelectorManifest,
        telemetry: StageTimingCollector,
    ) -> tuple[CheapImageAnalyzer, CandidateVerifier]:
        if manifest.algorithm_version in APPEARANCE_ONLY_SELECTOR_VERSIONS:
            return build_default_adapters(
                source_root,
                manifest=manifest,
                telemetry=telemetry,
            )

        def build_isolated_adapters() -> tuple[CheapImageAnalyzer, CandidateVerifier]:
            model_root = (
                self._repository_root / "artifacts" / "m5-models" / "sequence-number-ocr-v1"
            )
            ocr = PaddleSequenceNumberRecognizer(model_root)
            recognizer = AnchoredSequenceRangeRecognizer(ocr, telemetry=telemetry)
            fallback_recognizer: SequenceRangeRecognizer
            if manifest.range_adapter_version == GRID_FIRST_RANGE_ADAPTER_VERSION:
                fallback_recognizer = GridFirstVisibleSequenceLabelRangeRecognizer(
                    ocr,
                    telemetry=telemetry,
                )
            elif (
                manifest.range_adapter_version == TWO_LABEL_CONSENSUS_RANGE_ADAPTER_VERSION
                and manifest.progressive_visible_label_fallback_policy is not None
                and manifest.layout_anchor_policy is not None
                and manifest.contiguous_sequence_window_policy is not None
            ):
                fallback_recognizer = TwoLabelConsensusVisibleSequenceLabelRangeRecognizer(
                    ocr,
                    manifest.progressive_visible_label_fallback_policy,
                    manifest.layout_anchor_policy,
                    manifest.contiguous_sequence_window_policy,
                    telemetry=telemetry,
                )
            elif (
                manifest.range_adapter_version == FUSED_RANGE_EVIDENCE_ADAPTER_VERSION
                and manifest.progressive_visible_label_fallback_policy is not None
                and manifest.layout_anchor_policy is not None
                and manifest.contiguous_sequence_window_policy is not None
            ):
                fallback_recognizer = FusedRangeEvidenceVisibleSequenceLabelRangeRecognizer(
                    ocr,
                    manifest.progressive_visible_label_fallback_policy,
                    manifest.layout_anchor_policy,
                    manifest.contiguous_sequence_window_policy,
                    telemetry=telemetry,
                )
            elif (
                manifest.range_adapter_version == LABEL_LATTICE_SAFE_RANGE_ADAPTER_VERSION
                and manifest.progressive_visible_label_fallback_policy is not None
                and manifest.layout_anchor_policy is not None
                and manifest.contiguous_sequence_window_policy is not None
            ):
                fallback_recognizer = LabelLatticeSafeVisibleSequenceLabelRangeRecognizer(
                    ocr,
                    manifest.progressive_visible_label_fallback_policy,
                    manifest.layout_anchor_policy,
                    manifest.contiguous_sequence_window_policy,
                    telemetry=telemetry,
                )
            elif (
                manifest.range_adapter_version == PARTIAL_LAYOUT_ANCHORED_RANGE_ADAPTER_VERSION
                and manifest.progressive_visible_label_fallback_policy is not None
                and manifest.layout_anchor_policy is not None
            ):
                fallback_recognizer = PartialLayoutAnchoredVisibleSequenceLabelRangeRecognizer(
                    ocr,
                    manifest.progressive_visible_label_fallback_policy,
                    manifest.layout_anchor_policy,
                    telemetry=telemetry,
                )
            elif (
                manifest.range_adapter_version == LAYOUT_ANCHORED_RANGE_ADAPTER_VERSION
                and manifest.progressive_visible_label_fallback_policy is not None
                and manifest.layout_anchor_policy is not None
            ):
                fallback_recognizer = LayoutAnchoredVisibleSequenceLabelRangeRecognizer(
                    ocr,
                    manifest.progressive_visible_label_fallback_policy,
                    manifest.layout_anchor_policy,
                    telemetry=telemetry,
                )
            elif (
                manifest.range_adapter_version == CONTIGUOUS_WINDOW_RANGE_ADAPTER_VERSION
                and manifest.progressive_visible_label_fallback_policy is not None
                and manifest.contiguous_sequence_window_policy is not None
            ):
                fallback_recognizer = ContiguousWindowVisibleSequenceLabelRangeRecognizer(
                    ocr,
                    manifest.progressive_visible_label_fallback_policy,
                    manifest.contiguous_sequence_window_policy,
                    telemetry=telemetry,
                )
            elif (
                manifest.range_adapter_version == INDEPENDENT_ENDPOINT_RANGE_ADAPTER_VERSION
                and manifest.progressive_visible_label_fallback_policy is not None
            ):
                fallback_recognizer = IndependentEndpointVisibleSequenceLabelRangeRecognizer(
                    ocr,
                    manifest.progressive_visible_label_fallback_policy,
                    telemetry=telemetry,
                )
            elif manifest.progressive_visible_label_fallback_policy is not None:
                fallback_recognizer = ProgressiveVisibleSequenceLabelRangeRecognizer(
                    ocr,
                    manifest.progressive_visible_label_fallback_policy,
                    telemetry=telemetry,
                )
            elif manifest.algorithm_version in ACCURACY_FIRST_SELECTOR_VERSIONS:
                fallback_recognizer = AccuracyFirstVisibleSequenceLabelRangeRecognizer(
                    ocr,
                    telemetry=telemetry,
                )
            elif manifest.algorithm_version in BEST_EFFORT_SELECTOR_VERSIONS:
                fallback_recognizer = BestEffortVisibleSequenceLabelRangeRecognizer(
                    ocr,
                    telemetry=telemetry,
                )
            elif manifest.algorithm_version in ORDERED_SELECTOR_VERSIONS:
                fallback_recognizer = AdaptiveVisibleSequenceLabelRangeRecognizer(
                    ocr,
                    telemetry=telemetry,
                )
            else:
                fallback_recognizer = VisibleSequenceLabelRangeRecognizer(
                    ocr,
                    telemetry=telemetry,
                )
            return build_default_adapters(
                source_root,
                range_recognizer=recognizer,
                fallback_range_recognizer=fallback_recognizer,
                manifest=manifest,
                telemetry=telemetry,
            )

        analyzer, primary_verifier = build_isolated_adapters()
        if self._verification_workers == 1 or manifest.adaptive_range_consensus_policy is None:
            return analyzer, primary_verifier
        _, secondary_verifier = build_isolated_adapters()
        return analyzer, DeterministicParallelCandidateVerifier(
            (primary_verifier, secondary_verifier),
            telemetry=telemetry,
        )


class _DurableSelectionSink(SelectionAuditSink):
    def __init__(
        self,
        context: JobExecutionContext,
        store: ImageSelectionJobStore,
        *,
        run: ImageSelectionJobRun,
        total: int,
        upload_duration_seconds: float | None,
        prior_checkpoint: Mapping[str, object] | None,
        artifact_root: Path,
        existing_groups: Sequence[SelectionGroupResult],
        telemetry: StageTimingCollector,
        scan_cache_metrics: Callable[[], dict[str, object]],
        verification_cache_metrics: Callable[[], dict[str, object]],
    ) -> None:
        self._context = context
        self._store = store
        self._run = run
        self._total = total
        self._upload_duration_seconds = upload_duration_seconds
        self._artifact_root = artifact_root.resolve()
        self._pending_groups: dict[int, SelectionGroupResult] = {}
        self._pending_group_sources: dict[int, list[CheapImageObservation]] = {}
        self._latest_groups: dict[int, SelectionGroupResult] = {
            group.group_order: group for group in existing_groups
        }
        self._last_state: SelectorResumeState | None = None
        self._diagnostic: dict[str, object] | None = None
        self._error_samples = _prior_error_samples(prior_checkpoint)
        self._processing_started_at = context.now()
        self._prior_processing_seconds = _prior_processing_duration(prior_checkpoint)
        self._telemetry = telemetry
        self._scan_cache_metrics = scan_cache_metrics
        self._verification_cache_metrics = verification_cache_metrics
        self._window_started_at = self._processing_started_at
        self._window_processed_count = _prior_processed_count(prior_checkpoint)
        self._window_group_count = _checkpoint_int(prior_checkpoint, "group_count")
        self._window_verification_count = _checkpoint_int(
            prior_checkpoint,
            "verification_count",
        )
        self._window_manual_count = _checkpoint_int(prior_checkpoint, "manual_count")
        self._last_recent_window = _prior_recent_window(prior_checkpoint)

    def candidate_scanned(
        self,
        observation: CheapImageObservation,
        *,
        group_order: int,
    ) -> None:
        self._pending_group_sources.setdefault(group_order, []).append(observation)
        reasons = tuple(
            reason
            for reason in observation.reason_codes
            if reason.startswith("IMAGE_SELECTION_SCAN_")
        )
        if reasons and len(self._error_samples) < MAX_ERROR_SAMPLES:
            self._error_samples.append(
                {
                    "orderIndex": observation.source.order_index,
                    "reasonCodes": list(reasons),
                }
            )

    def checkpoint_saved(self, checkpoint: SelectorCheckpoint) -> None:
        del checkpoint

    def group_finalized(self, group: SelectionGroupResult) -> None:
        self._pending_groups[group.group_order] = group
        self._latest_groups[group.group_order] = group

    def selector_state_saved(self, state: SelectorResumeState) -> None:
        self._last_state = state
        if self._pending_groups:
            with self._telemetry.measure("persistence"):
                self._store.persist_groups(
                    job_id=self._run.job_id,
                    run_id=self._run.id,
                    lease_token=self._context.lease_token,
                    groups=tuple(self._pending_groups[key] for key in sorted(self._pending_groups)),
                    group_sources={
                        key: tuple(self._pending_group_sources.pop(key, ()))
                        for key in sorted(self._pending_groups)
                    },
                    persisted_at=self._context.now(),
                )
            self._telemetry.increment("persistenceWrites")
            self._pending_groups.clear()
        self._checkpoint(state, stage="image_selection:scanning")

    def checkpoint_stage(self, checkpoint: SelectorCheckpoint, *, stage: str) -> None:
        state = self._last_state
        if state is None or state.checkpoint != checkpoint:
            raise SelectionContractError(
                "IMAGE_SELECTION_CHECKPOINT_INVALID",
                "The selector did not expose its final durable checkpoint.",
            )
        self._checkpoint(state, stage=stage)

    def publication_checkpoint(
        self,
        checkpoint: SelectorCheckpoint,
        *,
        completed: int,
        total: int,
    ) -> None:
        if completed != total and completed % 16 != 0:
            return
        state = self._last_state
        if state is None or state.checkpoint != checkpoint:
            raise SelectionContractError(
                "IMAGE_SELECTION_CHECKPOINT_INVALID",
                "Publication lost the final selector checkpoint.",
            )
        self._checkpoint(
            state,
            stage="image_selection:writing_manifest",
            publication={"completed": completed, "total": total},
        )

    def write_diagnostics(self, result: ImageSelectionResult) -> None:
        payload = {
            "contract": DIAGNOSTIC_CONTRACT,
            "errorSampleLimit": MAX_ERROR_SAMPLES,
            "errorSamples": self._error_samples,
            "errorSamplesTruncated": result.scan_failure_count > len(self._error_samples),
            "fileCount": result.input_count,
            "groupCount": len(result.groups),
            "manualCount": sum(
                group.status
                in {
                    SelectionGroupStatus.MANUAL_REQUIRED,
                    SelectionGroupStatus.RANGE_REQUIRED,
                }
                for group in result.groups
            ),
            "missingImageRanges": [
                {"rangeEnd": group.range.end, "rangeStart": group.range.start}
                for group in result.groups
                if group.status is SelectionGroupStatus.MISSING_IMAGE and group.range is not None
            ],
            "runId": str(self._run.id),
            "scanFailureCount": result.scan_failure_count,
            "schemaVersion": 1,
            "selectedCount": sum(
                group.status
                in {
                    SelectionGroupStatus.AUTO_SELECTED,
                    SelectionGroupStatus.MANUALLY_SELECTED,
                    SelectionGroupStatus.RANGE_CONFIRMED,
                }
                for group in result.groups
            ),
            "selectorFingerprint": result.selector_fingerprint,
            "verificationCount": result.verification_count,
            "scanCache": self._scan_cache_metrics(),
            "verificationCache": self._verification_cache_metrics(),
            "stageTiming": self._telemetry.snapshot(),
        }
        content = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        checksum = hashlib.sha256(content).hexdigest()
        root = self._artifact_root / "data" / "exports" / "is-job-diagnostics"
        root.mkdir(parents=True, exist_ok=True)
        target = root / f"{checksum}.json"
        if not target.exists():
            temporary = root / f".{checksum}.part"
            with temporary.open("xb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(target)
        elif hashlib.sha256(target.read_bytes()).hexdigest() != checksum:
            raise SelectionContractError(
                "IMAGE_SELECTION_DIAGNOSTIC_CHANGED",
                "The checksum-addressed diagnostic artifact changed.",
            )
        self._diagnostic = {
            "checksumSha256": checksum,
            "relativePath": target.relative_to(self._artifact_root).as_posix(),
            "sizeBytes": len(content),
        }

    def _checkpoint(
        self,
        state: SelectorResumeState,
        *,
        stage: str,
        publication: Mapping[str, int] | None = None,
    ) -> None:
        groups = tuple(self._latest_groups[key] for key in sorted(self._latest_groups))
        selected = sum(
            group.status
            in {
                SelectionGroupStatus.AUTO_SELECTED,
                SelectionGroupStatus.MANUALLY_SELECTED,
                SelectionGroupStatus.RANGE_CONFIRMED,
            }
            for group in groups
        )
        manual = sum(
            group.status
            in {
                SelectionGroupStatus.MANUAL_REQUIRED,
                SelectionGroupStatus.RANGE_REQUIRED,
            }
            for group in groups
        )
        missing = sum(group.status is SelectionGroupStatus.MISSING_IMAGE for group in groups)
        checkpoint_now = self._context.now()
        window_advanced = state.checkpoint.processed_count > self._window_processed_count
        if window_advanced:
            self._last_recent_window = {
                "fromProcessed": self._window_processed_count,
                "toProcessed": state.checkpoint.processed_count,
                "elapsedSeconds": round(
                    max(0.0, (checkpoint_now - self._window_started_at).total_seconds()),
                    6,
                ),
                "groupsFinalized": max(0, len(groups) - self._window_group_count),
                "verifications": max(
                    0,
                    state.verification_count - self._window_verification_count,
                ),
                "manual": max(0, manual - self._window_manual_count),
            }
        payload: dict[str, object] = {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "workflow": "image_selection",
            "run_id": str(self._run.id),
            "input_manifest_sha256": self._run.input_manifest_sha256,
            "selector_state": state.to_dict(),
            "group_count": len(groups),
            "selected_count": selected,
            "manual_count": manual,
            "missing_image_count": missing,
            "skipped_count": sum(
                group.status
                in {
                    SelectionGroupStatus.SKIPPED_EXISTING_RANGE,
                    SelectionGroupStatus.SKIPPED_UNREADABLE,
                    SelectionGroupStatus.REJECTED_BY_USER,
                }
                for group in groups
            ),
            "error_count": state.scan_failure_count,
            "verification_count": state.verification_count,
            "error_samples": self._error_samples,
            "upload_duration_seconds": self._upload_duration_seconds,
            "scan_cache": self._scan_cache_metrics(),
            "verification_cache": self._verification_cache_metrics(),
            "stage_timing": self._telemetry.snapshot(),
        }
        if self._last_recent_window is not None:
            payload["recent_window"] = dict(self._last_recent_window)
        if self._diagnostic is not None:
            payload["diagnostic"] = self._diagnostic
        if publication is not None:
            payload["publication"] = dict(publication)
        processing_seconds = self._prior_processing_seconds + max(
            0.0,
            (self._context.now() - self._processing_started_at).total_seconds(),
        )
        payload["processing_duration_seconds"] = processing_seconds
        with self._telemetry.measure("persistence"):
            self._context.checkpoint(
                checkpoint_payload=payload,
                stage=stage,
                current=state.checkpoint.processed_count,
                total=self._total,
                success_count=selected,
                failure_count=state.scan_failure_count,
                review_count=max(self._context.job.review_count, manual),
            )
        self._telemetry.increment("persistenceWrites")
        if window_advanced:
            self._window_started_at = checkpoint_now
            self._window_processed_count = state.checkpoint.processed_count
            self._window_group_count = len(groups)
            self._window_verification_count = state.verification_count
            self._window_manual_count = manual


class SqlAlchemyImageSelectionJobStore(ImageSelectionJobStore):
    """Fenced PostgreSQL projection store used by the image-selection handler."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_run_for_job(self, job_id: UUID) -> ImageSelectionJobRun:
        with self._session_factory() as session:
            record = session.scalar(
                select(ImageSelectionRunModel).where(ImageSelectionRunModel.job_id == job_id)
            )
            if record is None:
                raise JobHandlerError(
                    "IMAGE_SELECTION_RUN_NOT_FOUND",
                    "The image-selection job has no durable run.",
                )
            return _job_run(record)

    def load_groups(self, run_id: UUID) -> tuple[SelectionGroupResult, ...]:
        with self._session_factory() as session:
            groups = tuple(
                session.scalars(
                    select(ImageSelectionGroupModel)
                    .where(ImageSelectionGroupModel.run_id == run_id)
                    .order_by(ImageSelectionGroupModel.group_order)
                )
            )
            candidates = tuple(
                session.scalars(
                    select(ImageSelectionCandidateModel)
                    .where(ImageSelectionCandidateModel.run_id == run_id)
                    .order_by(ImageSelectionCandidateModel.order_index)
                )
            )
        by_group: dict[UUID, list[ImageSelectionCandidateModel]] = {}
        for candidate in candidates:
            if candidate.group_id is not None:
                by_group.setdefault(candidate.group_id, []).append(candidate)
        return tuple(
            _selection_group_from_records(group, by_group.get(group.id, [])) for group in groups
        )

    def load_recovery_source(
        self,
        run_id: UUID,
    ) -> tuple[str, tuple[RecoverySourceGroup, ...]]:
        with self._session_factory() as session:
            source_run = session.get(ImageSelectionRunModel, run_id)
            if (
                source_run is None
                or ImageSelectionExecutionMode(source_run.execution_mode)
                is not ImageSelectionExecutionMode.FULL
            ):
                raise JobHandlerError(
                    "IMAGE_SELECTION_RECOVERY_SOURCE_INVALID",
                    "The recovery source must be an existing full selection run.",
                )
            snapshot, _, _, _ = SqlAlchemyImageSelectionRepository(session).recovery_snapshot(
                run_id
            )
            groups = tuple(
                session.scalars(
                    select(ImageSelectionGroupModel)
                    .where(ImageSelectionGroupModel.run_id == run_id)
                    .order_by(ImageSelectionGroupModel.group_order)
                )
            )
            candidates = tuple(
                session.scalars(
                    select(ImageSelectionCandidateModel)
                    .where(ImageSelectionCandidateModel.run_id == run_id)
                    .order_by(ImageSelectionCandidateModel.order_index)
                )
            )
        by_group: dict[UUID, list[ImageSelectionCandidateModel]] = {}
        for candidate in candidates:
            if candidate.group_id is not None:
                by_group.setdefault(candidate.group_id, []).append(candidate)
        return snapshot, tuple(
            RecoverySourceGroup(
                origin_group_id=group.id,
                result=_selection_group_from_records(group, by_group.get(group.id, [])),
                sources=tuple(
                    _source_from_candidate_record(candidate)
                    for candidate in by_group.get(group.id, [])
                ),
            )
            for group in groups
        )

    def persist_groups(
        self,
        *,
        job_id: UUID,
        run_id: UUID,
        lease_token: UUID,
        groups: Sequence[SelectionGroupResult],
        group_sources: Mapping[int, Sequence[CheapImageObservation]],
        persisted_at: datetime,
    ) -> None:
        with self._session_factory() as session, session.begin():
            _assert_fence(session, job_id, lease_token, persisted_at)
            for group in sorted(groups, key=lambda value: value.group_order):
                group_id = self._persist_group(session, run_id, group, persisted_at)
                self._persist_gallery_sources(
                    session,
                    run_id=run_id,
                    group_id=group_id,
                    group=group,
                    observations=group_sources.get(group.group_order, ()),
                    persisted_at=persisted_at,
                )

    def persist_recovery_projection(
        self,
        *,
        job_id: UUID,
        run_id: UUID,
        source_run_id: UUID,
        expected_source_snapshot_sha256: str,
        lease_token: UUID,
        projection: RecoveryProjection,
        persisted_at: datetime,
    ) -> None:
        with self._session_factory() as session, session.begin():
            _assert_fence(session, job_id, lease_token, persisted_at)
            derived = session.scalar(
                select(ImageSelectionRunModel)
                .where(ImageSelectionRunModel.id == run_id)
                .with_for_update()
            )
            if (
                derived is None
                or derived.source_run_id != source_run_id
                or derived.source_snapshot_sha256 != expected_source_snapshot_sha256
                or ImageSelectionExecutionMode(derived.execution_mode)
                is not ImageSelectionExecutionMode.RANGE_RECOVERY
            ):
                raise JobHandlerError(
                    "IMAGE_SELECTION_RECOVERY_SOURCE_INVALID",
                    "The durable recovery run does not match its source snapshot.",
                )
            source_groups = tuple(
                session.scalars(
                    select(ImageSelectionGroupModel)
                    .where(ImageSelectionGroupModel.run_id == source_run_id)
                    .order_by(ImageSelectionGroupModel.group_order)
                    .with_for_update()
                )
            )
            snapshot, _, _, _ = SqlAlchemyImageSelectionRepository(session).recovery_snapshot(
                source_run_id
            )
            if snapshot != expected_source_snapshot_sha256:
                raise JobHandlerError(
                    "IMAGE_SELECTION_RECOVERY_SOURCE_CHANGED",
                    "The source run changed before the recovery projection was committed.",
                )
            source_group_ids = {group.id for group in source_groups}
            for group in sorted(projection.groups, key=lambda value: value.group_order):
                origin_group_id = projection.origin_group_ids[group.group_order]
                if origin_group_id not in source_group_ids:
                    raise JobHandlerError(
                        "IMAGE_SELECTION_RECOVERY_PROVENANCE_MISSING",
                        "A recovered group does not reference its source projection.",
                    )
                group_id = self._persist_group(
                    session,
                    run_id,
                    group,
                    persisted_at,
                    origin_group_id=origin_group_id,
                )
                gallery = projection.group_sources.get(group.group_order)
                if gallery is None:
                    self._clone_source_candidates(
                        session,
                        run_id=run_id,
                        group_id=group_id,
                        origin_group_id=origin_group_id,
                        persisted_at=persisted_at,
                    )
                else:
                    self._persist_gallery_sources(
                        session,
                        run_id=run_id,
                        group_id=group_id,
                        group=group,
                        observations=gallery,
                        persisted_at=persisted_at,
                    )

    def record_output(
        self,
        *,
        job_id: UUID,
        run_id: UUID,
        lease_token: UUID,
        published: PublishedImageSelection,
        persisted_at: datetime,
    ) -> None:
        with self._session_factory() as session, session.begin():
            _assert_fence(session, job_id, lease_token, persisted_at)
            record = session.scalar(
                select(ImageSelectionRunModel)
                .where(ImageSelectionRunModel.id == run_id)
                .with_for_update()
            )
            if record is None:
                raise JobHandlerError(
                    "IMAGE_SELECTION_RUN_NOT_FOUND",
                    "The image-selection run no longer exists.",
                )
            if record.output_manifest_sha256 is not None and (
                record.output_manifest_sha256 != published.manifest_sha256
                or record.output_manifest_relative_path != published.manifest_relative_path
            ):
                raise JobHandlerError(
                    "IMAGE_SELECTION_MANIFEST_MISMATCH",
                    "The run already references another immutable output.",
                )
            record.output_manifest_sha256 = published.manifest_sha256
            record.output_manifest_relative_path = published.manifest_relative_path
            record.updated_at = persisted_at

    @staticmethod
    def _persist_group(
        session: Session,
        run_id: UUID,
        group: SelectionGroupResult,
        persisted_at: datetime,
        *,
        origin_group_id: UUID | None = None,
    ) -> UUID:
        record = session.scalar(
            select(ImageSelectionGroupModel)
            .where(
                ImageSelectionGroupModel.run_id == run_id,
                ImageSelectionGroupModel.group_order == group.group_order,
            )
            .with_for_update()
        )
        group_id = uuid5(run_id, f"image-selection-group:{group.group_order}")
        if record is None:
            record = ImageSelectionGroupModel(
                id=group_id,
                run_id=run_id,
                group_order=group.group_order,
                created_at=persisted_at,
                updated_at=persisted_at,
            )
            session.add(record)
            session.flush()
        elif record.id != group_id:
            group_id = record.id
        if ImageSelectionGroupStatus(record.status) in {
            ImageSelectionGroupStatus.MANUALLY_SELECTED,
            ImageSelectionGroupStatus.MISSING_IMAGE,
            ImageSelectionGroupStatus.RANGE_CONFIRMED,
            ImageSelectionGroupStatus.REJECTED_BY_USER,
        } and group.status not in {
            SelectionGroupStatus.MANUALLY_SELECTED,
            SelectionGroupStatus.MISSING_IMAGE,
            SelectionGroupStatus.RANGE_CONFIRMED,
            SelectionGroupStatus.REJECTED_BY_USER,
        }:
            return group_id
        record.range_start = None if group.range is None else group.range.start
        record.range_end = None if group.range is None else group.range.end
        record.fingerprint_sha256 = group.fingerprint_sha256
        record.board_count_consensus = group.board_count_consensus
        record.status = ImageSelectionGroupStatus(group.status.value)
        record.origin_group_id = origin_group_id
        if group.status is not SelectionGroupStatus.REJECTED_BY_USER:
            record.rejection_origin_status = None
        record.updated_at = persisted_at
        session.execute(
            update(ImageSelectionCandidateModel)
            .where(
                ImageSelectionCandidateModel.run_id == run_id,
                ImageSelectionCandidateModel.group_id == group_id,
                ImageSelectionCandidateModel.decision
                == ImageSelectionCandidateDecision.SELECTED_AUTOMATIC,
            )
            .values(decision=ImageSelectionCandidateDecision.ELIGIBLE)
        )
        selected_source = (
            None
            if group.selected_candidate is None
            else (
                group.selected_candidate.source.order_index,
                group.selected_candidate.source.checksum_sha256,
            )
        )
        for candidate in group.top_candidates:
            identity = (candidate.source.order_index, candidate.source.checksum_sha256)
            decision = candidate.decision
            if selected_source == identity:
                decision = (
                    CandidateDecision.SELECTED_MANUAL
                    if group.status is SelectionGroupStatus.MANUALLY_SELECTED
                    else CandidateDecision.SELECTED_AUTOMATIC
                )
            _upsert_candidate(
                session,
                run_id=run_id,
                group_id=group_id,
                group=group,
                candidate=candidate,
                decision=decision,
                persisted_at=persisted_at,
            )
        return group_id

    @staticmethod
    def _clone_source_candidates(
        session: Session,
        *,
        run_id: UUID,
        group_id: UUID,
        origin_group_id: UUID,
        persisted_at: datetime,
    ) -> None:
        source_candidates = tuple(
            session.scalars(
                select(ImageSelectionCandidateModel)
                .where(ImageSelectionCandidateModel.group_id == origin_group_id)
                .order_by(ImageSelectionCandidateModel.order_index)
            )
        )
        for source in source_candidates:
            existing = session.scalar(
                select(ImageSelectionCandidateModel).where(
                    ImageSelectionCandidateModel.run_id == run_id,
                    ImageSelectionCandidateModel.order_index == source.order_index,
                )
            )
            if existing is not None:
                if (
                    existing.group_id != group_id
                    or existing.checksum_sha256 != source.checksum_sha256
                ):
                    raise JobHandlerError(
                        "IMAGE_SELECTION_PERSISTENCE_CONFLICT",
                        "A copied recovery candidate already belongs to another group.",
                    )
                continue
            session.add(
                ImageSelectionCandidateModel(
                    id=uuid5(
                        run_id,
                        f"image-selection-candidate:{source.order_index}:{source.checksum_sha256}",
                    ),
                    run_id=run_id,
                    group_id=group_id,
                    order_index=source.order_index,
                    source_relative_path=source.source_relative_path,
                    checksum_sha256=source.checksum_sha256,
                    width=source.width,
                    height=source.height,
                    quality_metrics=dict(source.quality_metrics),
                    range_confidence=source.range_confidence,
                    reason_codes=list(source.reason_codes),
                    decision=ImageSelectionCandidateDecision(source.decision),
                    created_at=persisted_at,
                )
            )

    @staticmethod
    def _persist_gallery_sources(
        session: Session,
        *,
        run_id: UUID,
        group_id: UUID,
        group: SelectionGroupResult,
        observations: Sequence[CheapImageObservation],
        persisted_at: datetime,
    ) -> None:
        if not observations:
            return
        indexes = tuple(observation.source.order_index for observation in observations)
        existing = {
            record.order_index: record
            for record in session.scalars(
                select(ImageSelectionCandidateModel).where(
                    ImageSelectionCandidateModel.run_id == run_id,
                    ImageSelectionCandidateModel.order_index.in_(indexes),
                )
            )
        }
        for observation in observations:
            source = observation.source
            record = existing.get(source.order_index)
            if record is not None and not record.quality_metrics.get("manualGalleryOnly", False):
                continue
            metrics: dict[str, object] = {
                **observation.quality.to_dict(),
                "displayName": PurePosixPath(source.relative_path).name,
                "groupSourceCount": group.source_count,
                "manualGalleryOnly": True,
                "sourceOriginalRelativePath": source.relative_path,
                "sourceSizeBytes": source.size_bytes,
            }
            if record is None:
                record = ImageSelectionCandidateModel(
                    id=uuid5(
                        run_id,
                        f"image-selection-candidate:{source.order_index}:{source.checksum_sha256}",
                    ),
                    run_id=run_id,
                    group_id=group_id,
                    order_index=source.order_index,
                    source_relative_path=source.stored_relative_path,
                    checksum_sha256=source.checksum_sha256,
                    created_at=persisted_at,
                )
                session.add(record)
            elif record.group_id != group_id or record.checksum_sha256 != source.checksum_sha256:
                raise JobHandlerError(
                    "IMAGE_SELECTION_PERSISTENCE_CONFLICT",
                    "A gallery source already belongs to another selector group.",
                )
            record.width = observation.width
            record.height = observation.height
            record.quality_metrics = metrics
            record.range_confidence = None
            record.reason_codes = list(
                dict.fromkeys((*observation.reason_codes, "MANUAL_GALLERY_SOURCE"))
            )
            record.decision = ImageSelectionCandidateDecision.ELIGIBLE


def _upsert_candidate(
    session: Session,
    *,
    run_id: UUID,
    group_id: UUID,
    group: SelectionGroupResult,
    candidate: CandidateResult,
    decision: CandidateDecision,
    persisted_at: datetime,
) -> None:
    record = session.scalar(
        select(ImageSelectionCandidateModel)
        .where(
            ImageSelectionCandidateModel.run_id == run_id,
            ImageSelectionCandidateModel.order_index == candidate.source.order_index,
        )
        .with_for_update()
    )
    metrics: dict[str, object] = {
        **candidate.quality.to_dict(),
        "groupSourceCount": group.source_count,
        "referenceFingerprintHex": group.reference_fingerprint_hex,
        "sourceOriginalRelativePath": candidate.source.relative_path,
        "sourceSizeBytes": candidate.source.size_bytes,
    }
    if candidate.recognized_range is not None:
        metrics["recognizedRangeStart"] = candidate.recognized_range.start
        metrics["recognizedRangeEnd"] = candidate.recognized_range.end
    if record is None:
        record = ImageSelectionCandidateModel(
            id=uuid5(
                run_id,
                "image-selection-candidate:"
                f"{candidate.source.order_index}:{candidate.source.checksum_sha256}",
            ),
            run_id=run_id,
            group_id=group_id,
            order_index=candidate.source.order_index,
            source_relative_path=candidate.source.stored_relative_path,
            checksum_sha256=candidate.source.checksum_sha256,
            created_at=persisted_at,
        )
        session.add(record)
    elif record.checksum_sha256 != candidate.source.checksum_sha256:
        raise JobHandlerError(
            "IMAGE_SELECTION_PERSISTENCE_CONFLICT",
            "A candidate order already belongs to another selector result.",
        )
    elif record.group_id != group_id:
        if not record.quality_metrics.get("manualGalleryOnly", False):
            raise JobHandlerError(
                "IMAGE_SELECTION_PERSISTENCE_CONFLICT",
                "A candidate order already belongs to another selector result.",
            )
        # A lightweight gallery observation is provisional. A later, fully
        # verified candidate result is authoritative and may safely promote
        # that exact source into its final selector group. Different bytes are
        # still rejected above.
        record.group_id = group_id
    record.width = candidate.width
    record.height = candidate.height
    record.quality_metrics = metrics
    record.range_confidence = (
        None if candidate.recognized_range is None else candidate.recognized_range.confidence
    )
    record.reason_codes = list(candidate.reason_codes)
    record.decision = ImageSelectionCandidateDecision(decision.value)


def _selection_group_from_records(
    group: ImageSelectionGroupModel,
    candidates: Sequence[ImageSelectionCandidateModel],
) -> SelectionGroupResult:
    domain_candidates = tuple(
        candidate
        for candidate in candidates
        if not candidate.quality_metrics.get("manualGalleryOnly", False)
    )
    values = tuple(
        _candidate_from_record(candidate, group=group) for candidate in domain_candidates
    )
    selected = next(
        (
            candidate
            for candidate, record in zip(values, domain_candidates, strict=True)
            if ImageSelectionCandidateDecision(record.decision)
            in {
                ImageSelectionCandidateDecision.SELECTED_AUTOMATIC,
                ImageSelectionCandidateDecision.SELECTED_MANUAL,
            }
        ),
        None,
    )
    metrics = domain_candidates[0].quality_metrics if domain_candidates else {}
    source_count = _positive_int(metrics.get("groupSourceCount"), default=max(1, len(values)))
    reference = metrics.get("referenceFingerprintHex")
    recognized_range = (
        None
        if group.range_start is None or group.range_end is None
        else SequenceRange(
            start=group.range_start,
            end=group.range_end,
            confidence=max(
                (
                    value.recognized_range.confidence
                    for value in values
                    if value.recognized_range is not None
                ),
                default=0.0,
            ),
        )
    )
    return SelectionGroupResult(
        group_order=group.group_order,
        source_count=source_count,
        range=recognized_range,
        fingerprint_sha256=group.fingerprint_sha256 or "0" * 64,
        board_count_consensus=group.board_count_consensus,
        status=SelectionGroupStatus(ImageSelectionGroupStatus(group.status).value),
        selected_candidate=selected,
        top_candidates=values,
        reference_fingerprint_hex=(reference if isinstance(reference, str) else None),
    )


def _candidate_from_record(
    record: ImageSelectionCandidateModel,
    *,
    group: ImageSelectionGroupModel,
) -> CandidateResult:
    metrics = dict(record.quality_metrics)
    quality = _quality_from_metrics(metrics)
    range_start = metrics.get("recognizedRangeStart")
    range_end = metrics.get("recognizedRangeEnd")
    recognized_range = None
    if isinstance(range_start, int) and isinstance(range_end, int):
        recognized_range = SequenceRange(
            start=range_start,
            end=range_end,
            confidence=record.range_confidence or 0.0,
        )
    elif group.range_start is not None and group.range_end is not None:
        recognized_range = SequenceRange(
            start=group.range_start,
            end=group.range_end,
            confidence=record.range_confidence or 0.0,
        )
    return CandidateResult(
        source=_source_from_candidate_record(record),
        decision=CandidateDecision(ImageSelectionCandidateDecision(record.decision).value),
        quality=quality,
        recognized_range=recognized_range,
        reason_codes=tuple(str(item) for item in record.reason_codes),
        width=record.width,
        height=record.height,
    )


def _quality_from_metrics(metrics: Mapping[str, object]) -> ImageQualityMetrics:
    try:
        return ImageQualityMetrics.from_dict(dict(metrics))
    except SelectionContractError:
        return ImageQualityMetrics(*(0.0 for _ in range(8)))


def _assert_fence(
    session: Session,
    job_id: UUID,
    lease_token: UUID,
    persisted_at: datetime,
) -> None:
    record = session.scalar(select(JobModel).where(JobModel.id == job_id).with_for_update())
    if (
        record is None
        or record.status != JobStatus.PROCESSING
        or record.lease_token != lease_token
        or record.lease_expires_at is None
        or record.lease_expires_at <= persisted_at
    ):
        raise JobConflictError(
            "JOB_LEASE_LOST",
            "The worker lease no longer permits image-selection writes.",
        )


def _job_run(record: ImageSelectionRunModel) -> ImageSelectionJobRun:
    return ImageSelectionJobRun(
        id=record.id,
        job_id=record.job_id,
        source_selection_id=record.source_selection_id,
        input_manifest_sha256=record.input_manifest_sha256,
        selector_fingerprint=record.selector_fingerprint,
        output_manifest_sha256=record.output_manifest_sha256,
        output_manifest_relative_path=record.output_manifest_relative_path,
        sequence_direction=ImageSelectionSequenceDirection(record.sequence_direction),
        first_sequence_number=record.first_sequence_number or None,
        execution_mode=ImageSelectionExecutionMode(record.execution_mode),
        source_run_id=record.source_run_id,
        source_snapshot_sha256=record.source_snapshot_sha256,
    )


def _source_from_candidate_record(
    record: ImageSelectionCandidateModel,
) -> ImageSelectionSource:
    metrics = record.quality_metrics
    original = metrics.get("sourceOriginalRelativePath")
    size = _positive_int(metrics.get("sourceSizeBytes"), default=1)
    return ImageSelectionSource(
        order_index=record.order_index,
        relative_path=(original if isinstance(original, str) else record.source_relative_path),
        stored_relative_path=record.source_relative_path,
        checksum_sha256=record.checksum_sha256,
        size_bytes=size,
    )


def _recovery_counts(
    groups: Sequence[SelectionGroupResult],
) -> tuple[int, int]:
    selected = sum(
        group.status
        in {
            SelectionGroupStatus.AUTO_SELECTED,
            SelectionGroupStatus.MANUALLY_SELECTED,
            SelectionGroupStatus.RANGE_CONFIRMED,
        }
        for group in groups
    )
    review = sum(
        group.status
        in {
            SelectionGroupStatus.MANUAL_REQUIRED,
            SelectionGroupStatus.RANGE_REQUIRED,
        }
        for group in groups
    )
    return selected, review


def _recovery_checkpoint_payload(
    run: ImageSelectionJobRun,
    result: ImageSelectionResult,
    *,
    block_count: int,
) -> dict[str, object]:
    selected, review = _recovery_counts(result.groups)
    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "workflow": "image_selection_range_recovery",
        "run_id": str(run.id),
        "source_run_id": str(run.source_run_id),
        "source_snapshot_sha256": run.source_snapshot_sha256,
        "recovery_projection_complete": True,
        "block_count": block_count,
        "candidate_count": result.input_count,
        "group_count": len(result.groups),
        "selected_count": selected,
        "manual_count": review,
        "scan_failure_count": result.scan_failure_count,
        "verification_count": result.verification_count,
        "selector_state": {"checkpoint": result.checkpoint.to_dict()},
    }


def _recovery_result(
    run: ImageSelectionJobRun,
    manifest: SelectorManifest,
    groups: tuple[SelectionGroupResult, ...],
    checkpoint: Mapping[str, object],
) -> ImageSelectionResult:
    input_count = _checkpoint_int(checkpoint, "candidate_count")
    return ImageSelectionResult(
        selector_version=manifest.algorithm_version,
        selector_fingerprint=manifest.fingerprint,
        input_count=input_count,
        groups=groups,
        checkpoint=SelectorCheckpoint(
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            selector_fingerprint=run.selector_fingerprint,
            next_order_index=input_count,
            processed_count=input_count,
            finalized_group_count=len(groups),
        ),
        scan_failure_count=_checkpoint_int(checkpoint, "scan_failure_count"),
        verification_count=_checkpoint_int(checkpoint, "verification_count"),
    )


def _resume_state(checkpoint: Mapping[str, object] | None) -> SelectorResumeState | None:
    if checkpoint is None:
        return None
    if (
        checkpoint.get("schema_version") != CHECKPOINT_SCHEMA_VERSION
        or checkpoint.get("workflow") != "image_selection"
    ):
        raise SelectionContractError(
            "IMAGE_SELECTION_CHECKPOINT_INVALID",
            "The job checkpoint does not belong to the image selector.",
        )
    value = checkpoint.get("selector_state")
    if not isinstance(value, dict):
        raise SelectionContractError(
            "IMAGE_SELECTION_CHECKPOINT_INVALID",
            "The job checkpoint is missing selector state.",
        )
    return SelectorResumeState.from_dict(value)


def _committed_groups(
    persisted_groups: Sequence[SelectionGroupResult],
    resume_state: SelectorResumeState | None,
) -> tuple[SelectionGroupResult, ...]:
    committed_count = 0 if resume_state is None else resume_state.checkpoint.finalized_group_count
    if len(persisted_groups) < committed_count:
        raise SelectionContractError(
            "IMAGE_SELECTION_CHECKPOINT_INVALID",
            "The selector checkpoint is ahead of its durable group projection.",
        )
    return tuple(persisted_groups[:committed_count])


def _prior_error_samples(
    checkpoint: Mapping[str, object] | None,
) -> list[dict[str, object]]:
    if checkpoint is None:
        return []
    value = checkpoint.get("error_samples")
    if not isinstance(value, list):
        return []
    samples: list[dict[str, object]] = []
    for item in value[:MAX_ERROR_SAMPLES]:
        if not isinstance(item, dict):
            continue
        order_index = item.get("orderIndex")
        reasons = item.get("reasonCodes")
        if isinstance(order_index, int) and isinstance(reasons, list):
            samples.append(
                {
                    "orderIndex": order_index,
                    "reasonCodes": [str(reason) for reason in reasons[:10]],
                }
            )
    return samples


def _upload_duration(source_root: Path) -> float | None:
    path = source_root / BROWSER_UPLOAD_METRICS
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        duration = float(value["durationSeconds"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return duration if duration >= 0 else None


def _prior_processing_duration(
    checkpoint: Mapping[str, object] | None,
) -> float:
    if checkpoint is None:
        return 0.0
    value = checkpoint.get("processing_duration_seconds")
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0.0
    return max(0.0, float(value))


def _checkpoint_int(checkpoint: Mapping[str, object] | None, key: str) -> int:
    if checkpoint is None:
        return 0
    value = checkpoint.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return 0
    try:
        return max(0, int(value))
    except ValueError:
        return 0


def _prior_processed_count(checkpoint: Mapping[str, object] | None) -> int:
    if checkpoint is None:
        return 0
    selector_state = checkpoint.get("selector_state")
    if not isinstance(selector_state, Mapping):
        return 0
    selector_checkpoint = selector_state.get("checkpoint")
    if not isinstance(selector_checkpoint, Mapping):
        return 0
    value = selector_checkpoint.get("processedCount", 0)
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return 0
    try:
        return max(0, int(value))
    except ValueError:
        return 0


def _prior_recent_window(
    checkpoint: Mapping[str, object] | None,
) -> dict[str, object] | None:
    if checkpoint is None:
        return None
    value = checkpoint.get("recent_window")
    return dict(value) if isinstance(value, Mapping) else None


def _safe_child(root: Path, relative_path: str) -> Path:
    try:
        pure = PurePosixPath(relative_path)
        if pure.is_absolute() or ".." in pure.parts or "\\" in relative_path:
            raise ValueError
        child = (root / Path(*pure.parts)).resolve(strict=True)
    except (OSError, ValueError) as error:
        raise SelectionContractError(
            "IMAGE_SELECTION_SOURCE_MISSING",
            "A selected source is missing or unsafe.",
        ) from error
    if not child.is_relative_to(root) or not child.is_file():
        raise SelectionContractError(
            "IMAGE_SELECTION_SOURCE_MISSING",
            "A selected source escaped its managed root.",
        )
    return child


def _safe_artifact_file(root: Path, relative_path: str) -> Path:
    return _safe_child(root, relative_path)


def _positive_int(value: object, *, default: int) -> int:
    return value if isinstance(value, int) and value > 0 else default


__all__ = [
    "ImageSelectionJobHandler",
    "ImageSelectionJobRun",
    "ImageSelectionJobStore",
    "SqlAlchemyImageSelectionJobStore",
]
