"""Durable range-only semi-automatic image-selection job."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast
from uuid import UUID

import numpy as np
from game_predictor_api.domain.jobs import Job, JobConflictError, JobError, JobStatus
from game_predictor_api.domain.semi_automatic_image_selections import (
    SemiAutomaticSelectionRangeStatus,
    SemiAutomaticSelectionRun,
    SemiAutomaticSelectionRunStatus,
    SemiAutomaticSelectionWorkflowMode,
    begin_filename_verification_cleanup,
    block_filename_verification_cleanup,
    classify_filename_range_verification,
    complete_filename_verification_cleanup,
    resume_filename_verification_cleanup,
)
from game_predictor_api.schemas.jobs import SemiAutomaticImageSelectionJobPayload
from game_predictor_api.storage.models import (
    BrowserSelectionRetentionModel,
    FilenameRangeVerificationReviewModel,
    JobModel,
    SemiAutomaticImageSelectionRangeModel,
    SemiAutomaticImageSelectionRunModel,
)
from game_predictor_api.storage.semi_automatic_image_selection_repository import (
    SqlAlchemySemiAutomaticSelectionRepository,
)
from numpy.typing import NDArray
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError

from .audit import SemiAutomaticSelectionAudit
from .contracts import (
    RangeEvidenceGate,
    RangeEvidenceObservation,
    RangeEvidenceResult,
    RangeEvidenceStatus,
    SemiAutomaticSelectionDirection,
    SemiAutomaticSelectionError,
    SemiAutomaticSelectionSource,
    SemiAutomaticSequenceBounds,
)
from .engine import RangeGroupingAccumulator, RangeGroupSelection, grouping_policy_fingerprint
from .five_anchor_range_label_locator import FiveAnchorRangeLabelLocator
from .five_anchor_range_proof import FiveAnchorExpectedRangeTable
from .five_anchor_range_runtime import (
    DEFAULT_FIVE_ANCHOR_RUNTIME_POLICY,
    FIVE_ANCHOR_RECOGNIZER_CONTRACT_FINGERPRINT_V6,
    FiveAnchorBatchRuntime,
    FiveAnchorSourcePayload,
)
from .middle_row_grouping import (
    FIVE_ANCHOR_EVIDENCE_SELECTOR_VERSION,
    FIVE_ANCHOR_GROUPING_VERSION,
    MIDDLE_ROW_EVIDENCE_SELECTOR_VERSION,
    ROW_FIRST_EVIDENCE_SELECTOR_VERSION,
    ROW_FIRST_GROUPING_VERSION,
    FinalizedMiddleRowGroup,
    MiddleRowGroupingAccumulator,
    five_anchor_grouping_policy_fingerprint,
    middle_row_grouping_policy_fingerprint,
    row_first_grouping_policy_fingerprint,
)
from .middle_row_locator import MiddleRowTripleLocator
from .middle_row_range import ExpectedRangeTable
from .middle_row_runtime import (
    DEFAULT_MIDDLE_ROW_RUNTIME_POLICY,
    MIDDLE_ROW_RECOGNIZER_CONTRACT_FINGERPRINT_V4,
    MiddleRowBatchRuntime,
    MiddleRowLatticePriorTracker,
    MiddleRowOrientationCalibration,
    MiddleRowPaddleRecognitionAdapter,
    MiddleRowRunOrientation,
    MiddleRowRuntimePolicy,
    MiddleRowSourcePayload,
    build_middle_row_paddle_adapter,
    calibrate_middle_row_orientation,
    deterministic_orientation_sample_indexes,
)
from .range_only_ocr import (
    RANGE_ONLY_OCR_SCHEDULING_POLICY_V3,
    RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V3,
    SUPPORTED_RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINTS,
    RangeOnlyOcrAdapter,
    RangeOnlyRecognizer,
    build_paddle_range_only_recognizer_for_contract,
)
from .range_only_scheduler import (
    RANGE_ONLY_OCR_SKIPPED_REASON,
    AdaptiveRangeOcrProbeScheduler,
)
from .range_proof_v5 import RowExpectedRangeTable
from .row_first_locator_v5 import RowFirstTripleLocator
from .row_first_runtime_v5 import (
    DEFAULT_ROW_FIRST_RUNTIME_POLICY,
    ROW_FIRST_RECOGNIZER_CONTRACT_FINGERPRINT_V5,
    RowFirstBatchRuntime,
    RowFirstSourcePayload,
)

BROWSER_SELECTION_DIRECTORY = "browser-selections"
BROWSER_SELECTION_MANIFEST = "_browser_manifest.json"
SEMI_AUTOMATIC_CHECKPOINT_SCHEMA_VERSION = 1
SEMI_AUTOMATIC_SELECTION_STAGE = "semi_automatic_image_selection"
_NATURAL_PATH_PART = re.compile(r"(\d+)")
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _StagedSource:
    identity: SemiAutomaticSelectionSource
    stored_file_name: str


@dataclass(frozen=True, slots=True)
class SelectionApplyOutcome:
    run: SemiAutomaticSelectionRun
    applied: bool


@dataclass(frozen=True, slots=True)
class FilenameVerificationCleanupPlan:
    """Direct, run-owned paths which may be removed after database fencing."""

    artifact_directory: Path
    artifact_trash_directory: Path
    staging_directory: Path
    staging_trash_directory: Path


RecognizerFactory = Callable[[Path, str], RangeOnlyRecognizer]
MiddleRowRecognizerFactory = Callable[[Path], MiddleRowPaddleRecognitionAdapter]
MiddleRowLocatorFactory = Callable[[], MiddleRowTripleLocator]
RowFirstLocatorFactory = Callable[[], RowFirstTripleLocator]
FiveAnchorLocatorFactory = Callable[[], FiveAnchorRangeLabelLocator]


class SemiAutomaticSelectionJobStore:
    """Fenced persistence for one streaming scanner and its range projection."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_run_for_job(self, job_id: UUID) -> SemiAutomaticSelectionRun:
        with self._session_factory() as session:
            run_id = session.scalar(
                select(SemiAutomaticImageSelectionRunModel.id).where(
                    SemiAutomaticImageSelectionRunModel.job_id == job_id
                )
            )
            if run_id is None:
                raise JobHandlerError(
                    "SEMI_AUTOMATIC_SELECTION_NOT_FOUND",
                    "The semi-automatic selection job has no durable run.",
                )
            run = SqlAlchemySemiAutomaticSelectionRepository(session).get(run_id)
            if run is None:
                raise JobHandlerError(
                    "SEMI_AUTOMATIC_SELECTION_NOT_FOUND",
                    "The semi-automatic selection run no longer exists.",
                )
            return run

    def persist_checkpoint(
        self,
        *,
        job_id: UUID,
        run_id: UUID,
        lease_token: UUID,
        checkpoint: Mapping[str, object],
        counters: Mapping[str, int],
        persisted_at: datetime,
    ) -> SemiAutomaticSelectionRun:
        with self._session_factory() as session, session.begin():
            _assert_fence(session, job_id, lease_token, persisted_at)
            record = _locked_run(session, run_id)
            if record.status == SemiAutomaticSelectionRunStatus.PAUSED.value:
                _apply_run_progress(record, checkpoint, counters, persisted_at)
            elif record.status in {
                SemiAutomaticSelectionRunStatus.CANCELLED.value,
                SemiAutomaticSelectionRunStatus.FAILED.value,
                SemiAutomaticSelectionRunStatus.COMPLETED.value,
            }:
                raise JobHandlerError(
                    "SEMI_AUTOMATIC_SELECTION_STATE_INVALID",
                    "The semi-automatic selection run is no longer writable.",
                )
            else:
                record.status = SemiAutomaticSelectionRunStatus.RUNNING.value
                _apply_run_progress(record, checkpoint, counters, persisted_at)
        return self._get_run(run_id)

    def apply_selection(
        self,
        *,
        job_id: UUID,
        run_id: UUID,
        lease_token: UUID,
        selection: RangeGroupSelection,
        checkpoint: Mapping[str, object],
        increment_out_of_order: bool,
        persisted_at: datetime,
    ) -> SelectionApplyOutcome:
        with self._session_factory() as session, session.begin():
            _assert_fence(session, job_id, lease_token, persisted_at)
            run = _locked_run(session, run_id)
            item = session.scalar(
                select(SemiAutomaticImageSelectionRangeModel)
                .where(
                    SemiAutomaticImageSelectionRangeModel.run_id == run_id,
                    SemiAutomaticImageSelectionRangeModel.range_start
                    == selection.group.sequence_range.start,
                    SemiAutomaticImageSelectionRangeModel.range_end
                    == selection.group.sequence_range.end,
                )
                .with_for_update()
            )
            if item is None:
                raise JobHandlerError(
                    "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                    "A selected exact range is absent from the durable expected list.",
                )
            counters = {key: int(value) for key, value in run.counters.items()}
            if increment_out_of_order:
                counters["outOfOrderGroups"] = counters.get("outOfOrderGroups", 0) + 1
            applied = item.status == SemiAutomaticSelectionRangeStatus.MISSING.value
            if applied:
                source = selection.evidence.source
                item.status = SemiAutomaticSelectionRangeStatus.AUTO_SELECTED.value
                item.source_index = source.source_index
                item.source_relative_path = source.relative_path
                item.source_size_bytes = source.size_bytes
                item.source_checksum_sha256 = source.checksum_sha256
                item.group_first_source_index = selection.group.first_source_index
                item.group_last_source_index = selection.group.last_source_index
                item.range_confidence = selection.evidence.confidence
                item.selection_method = selection.selection_method
                item.output_checksum_sha256 = None
                item.revision += 1
                item.updated_at = persisted_at
                counters["autoSelected"] = counters.get("autoSelected", 0) + 1
                counters["missing"] = max(0, counters.get("missing", 0) - 1)
                if selection.selection_method in {
                    MIDDLE_ROW_EVIDENCE_SELECTOR_VERSION,
                    ROW_FIRST_EVIDENCE_SELECTOR_VERSION,
                    FIVE_ANCHOR_EVIDENCE_SELECTOR_VERSION,
                }:
                    counters["selectedRanges"] = counters.get("selectedRanges", 0) + 1
            else:
                counters["duplicateGroups"] = counters.get("duplicateGroups", 0) + 1
                if selection.selection_method in {
                    MIDDLE_ROW_EVIDENCE_SELECTOR_VERSION,
                    ROW_FIRST_EVIDENCE_SELECTOR_VERSION,
                    FIVE_ANCHOR_EVIDENCE_SELECTOR_VERSION,
                }:
                    counters["duplicateRanges"] = counters.get("duplicateRanges", 0) + 1
            if run.status != SemiAutomaticSelectionRunStatus.PAUSED.value:
                run.status = SemiAutomaticSelectionRunStatus.RUNNING.value
            _apply_run_progress(run, checkpoint, counters, persisted_at)
        return SelectionApplyOutcome(run=self._get_run(run_id), applied=applied)

    def finalize_analysis(
        self,
        *,
        job_id: UUID,
        run_id: UUID,
        lease_token: UUID,
        checkpoint: Mapping[str, object],
        counters: Mapping[str, int],
        diagnostics_relative_path: str,
        diagnostics_checksum_sha256: str,
        persisted_at: datetime,
    ) -> SemiAutomaticSelectionRun:
        with self._session_factory() as session, session.begin():
            _assert_fence(session, job_id, lease_token, persisted_at)
            run = _locked_run(session, run_id)
            if run.status == SemiAutomaticSelectionRunStatus.PAUSED.value:
                return _domain_run(session, run_id)
            run.status = SemiAutomaticSelectionRunStatus.ANALYSIS_COMPLETE.value
            run.diagnostics_relative_path = diagnostics_relative_path
            run.diagnostics_checksum_sha256 = diagnostics_checksum_sha256
            _apply_run_progress(run, checkpoint, counters, persisted_at)
        return self._get_run(run_id)

    def begin_filename_verification_cleanup(
        self,
        *,
        job_id: UUID,
        run_id: UUID,
        lease_token: UUID,
        persisted_at: datetime,
    ) -> SemiAutomaticSelectionRun:
        """Reserve a terminal, output-free filename run for managed cleanup."""

        with self._session_factory() as session, session.begin():
            _assert_fence(session, job_id, lease_token, persisted_at)
            record = _locked_run(session, run_id)
            _locked_job(session, job_id)
            run = _domain_run(session, run_id)
            if record.status == SemiAutomaticSelectionRunStatus.CLEANUP_BLOCKED.value:
                updated = resume_filename_verification_cleanup(run, changed_at=persisted_at)
            else:
                updated = begin_filename_verification_cleanup(run, changed_at=persisted_at)
            _assert_filename_verification_cleanup_references(
                session,
                run_record=record,
                job_id=job_id,
            )
            retention = session.get(
                BrowserSelectionRetentionModel,
                record.source_upload_id,
                with_for_update=True,
            )
            if retention is not None:
                if (
                    retention.game_id is not None
                    or retention.import_job_id != job_id
                    or retention.state not in {"in_use", "blocked"}
                ):
                    raise JobHandlerError(
                        "SEMI_AUTOMATIC_SELECTION_CLEANUP_BLOCKED",
                        "The filename verification staging has a foreign database reference.",
                    )
                retention.state = "blocked"
                retention.blocked_reason = "filename_verification_cleanup"
                retention.updated_at = persisted_at
            record.status = updated.status.value
            record.checkpoint = {
                **dict(record.checkpoint),
                "cleanup": "pending",
                "phase": "cleanup_pending",
            }
            record.revision = updated.revision
            record.updated_at = updated.updated_at
            # The local worker will complete the processing job after physical
            # cleanup.  Locking it above proves that the run cannot be
            # simultaneously requeued by the Admin request path.
        return self._get_run(run_id)

    def complete_filename_verification_cleanup(
        self,
        *,
        job_id: UUID,
        run_id: UUID,
        lease_token: UUID,
        persisted_at: datetime,
    ) -> SemiAutomaticSelectionRun:
        """Delete only run-owned rows and persist the compact terminal summary."""

        with self._session_factory() as session, session.begin():
            _assert_fence(session, job_id, lease_token, persisted_at)
            record = _locked_run(session, run_id)
            _locked_job(session, job_id)
            run = _domain_run(session, run_id)
            if record.status != SemiAutomaticSelectionRunStatus.CLEANUP_PENDING.value:
                raise JobHandlerError(
                    "SEMI_AUTOMATIC_SELECTION_CLEANUP_BLOCKED",
                    "The filename verification run is not reserved for cleanup.",
                )
            _assert_filename_verification_cleanup_references(
                session,
                run_record=record,
                job_id=job_id,
            )
            retention = session.get(
                BrowserSelectionRetentionModel,
                record.source_upload_id,
                with_for_update=True,
            )
            if retention is not None and (
                retention.game_id is not None
                or retention.import_job_id != job_id
                or retention.state != "blocked"
            ):
                raise JobHandlerError(
                    "SEMI_AUTOMATIC_SELECTION_CLEANUP_BLOCKED",
                    "The filename verification staging changed before cleanup completed.",
                )
            manual_counts = dict(
                session.execute(
                    select(
                        FilenameRangeVerificationReviewModel.decision,
                        func.count(),
                    )
                    .where(FilenameRangeVerificationReviewModel.run_id == run_id)
                    .group_by(FilenameRangeVerificationReviewModel.decision)
                )
            )
            counters = {
                **dict(run.counters),
                "filenameManualKept": int(manual_counts.get("keep", 0)),
                "filenameManualRejected": int(manual_counts.get("reject", 0)),
            }
            checkpoint = {
                "cleanup": "completed",
                "completedAt": persisted_at.isoformat(),
                "observationCount": run.source.source_count,
                "phase": "cleanup_complete",
                "schemaVersion": SEMI_AUTOMATIC_CHECKPOINT_SCHEMA_VERSION,
                "sourceCount": run.source.source_count,
            }
            completed = complete_filename_verification_cleanup(
                run,
                checkpoint=checkpoint,
                counters=counters,
                changed_at=persisted_at,
            )
            session.execute(
                delete(FilenameRangeVerificationReviewModel).where(
                    FilenameRangeVerificationReviewModel.run_id == run_id
                )
            )
            session.execute(
                delete(SemiAutomaticImageSelectionRangeModel).where(
                    SemiAutomaticImageSelectionRangeModel.run_id == run_id
                )
            )
            if retention is not None:
                session.delete(retention)
            record.status = completed.status.value
            record.checkpoint = dict(completed.checkpoint)
            record.counters = dict(completed.counters)
            record.diagnostics_relative_path = None
            record.diagnostics_checksum_sha256 = None
            record.revision = completed.revision
            record.updated_at = completed.updated_at
        return self._get_run(run_id)

    def mark_filename_verification_cleanup_blocked(
        self,
        *,
        job_id: UUID,
        run_id: UUID,
        lease_token: UUID,
        error_code: str,
        persisted_at: datetime,
    ) -> SemiAutomaticSelectionRun:
        """Keep a diagnostic, retryable cleanup state after a safe refusal."""

        with self._session_factory() as session, session.begin():
            _assert_fence(session, job_id, lease_token, persisted_at)
            record = _locked_run(session, run_id)
            run = _domain_run(session, run_id)
            blocked = block_filename_verification_cleanup(run, changed_at=persisted_at)
            record.status = blocked.status.value
            record.checkpoint = {
                **dict(record.checkpoint),
                "cleanup": "blocked",
                "cleanupErrorCode": error_code,
                "phase": "cleanup_blocked",
            }
            record.revision = blocked.revision
            record.updated_at = blocked.updated_at
        return self._get_run(run_id)

    def missing_ranges(self, run_id: UUID) -> tuple[tuple[int, int, int], ...]:
        with self._session_factory() as session:
            values = session.execute(
                select(
                    SemiAutomaticImageSelectionRangeModel.expected_index,
                    SemiAutomaticImageSelectionRangeModel.range_start,
                    SemiAutomaticImageSelectionRangeModel.range_end,
                )
                .where(
                    SemiAutomaticImageSelectionRangeModel.run_id == run_id,
                    SemiAutomaticImageSelectionRangeModel.status
                    == SemiAutomaticSelectionRangeStatus.MISSING.value,
                )
                .order_by(SemiAutomaticImageSelectionRangeModel.expected_index)
            )
            return tuple((int(index), int(start), int(end)) for index, start, end in values)

    def reset_unacknowledged_filename_selections(
        self,
        *,
        job_id: UUID,
        run_id: UUID,
        lease_token: UUID,
        persisted_at: datetime,
    ) -> SemiAutomaticSelectionRun:
        """Undo only output-free selections accidentally made by filename review."""

        with self._session_factory() as session, session.begin():
            _assert_fence(session, job_id, lease_token, persisted_at)
            run = _locked_run(session, run_id)
            rows = tuple(
                session.scalars(
                    select(SemiAutomaticImageSelectionRangeModel)
                    .where(SemiAutomaticImageSelectionRangeModel.run_id == run_id)
                    .with_for_update()
                )
            )
            protected = [
                item
                for item in rows
                if item.status == SemiAutomaticSelectionRangeStatus.OUTPUT_SYNCED.value
                or item.output_checksum_sha256 is not None
            ]
            if protected:
                raise JobHandlerError(
                    "SEMI_AUTOMATIC_SELECTION_FILENAME_VERIFICATION_CONFLICT",
                    "A filename-verification run has an acknowledged local output.",
                )
            accidental = tuple(
                item
                for item in rows
                if item.status == SemiAutomaticSelectionRangeStatus.AUTO_SELECTED.value
            )
            if len(accidental) > 1:
                raise JobHandlerError(
                    "SEMI_AUTOMATIC_SELECTION_FILENAME_VERIFICATION_CONFLICT",
                    "A filename-verification run has multiple historical selections.",
                )
            restored = len(accidental)
            for item in accidental:
                item.status = SemiAutomaticSelectionRangeStatus.MISSING.value
                item.source_index = None
                item.source_relative_path = None
                item.source_size_bytes = None
                item.source_checksum_sha256 = None
                item.group_first_source_index = None
                item.group_last_source_index = None
                item.range_confidence = None
                item.selection_method = None
                item.output_checksum_sha256 = None
                item.revision += 1
                item.updated_at = persisted_at
            if restored:
                counters = {key: int(value) for key, value in run.counters.items()}
                counters["autoSelected"] = max(0, counters.get("autoSelected", 0) - restored)
                counters["missing"] = counters.get("missing", 0) + restored
                _apply_run_progress(run, run.checkpoint, counters, persisted_at)
        return self._get_run(run_id)

    def _get_run(self, run_id: UUID) -> SemiAutomaticSelectionRun:
        with self._session_factory() as session:
            return _domain_run(session, run_id)


class SemiAutomaticImageSelectionJobHandler:
    """Scan each staged JPEG once, group exact ranges, then select midpoints."""

    def __init__(
        self,
        store: SemiAutomaticSelectionJobStore,
        *,
        browser_upload_root: Path,
        artifact_root: Path,
        repository_root: Path,
        recognizer_factory: RecognizerFactory = build_paddle_range_only_recognizer_for_contract,
        middle_row_recognizer_factory: MiddleRowRecognizerFactory = (
            build_middle_row_paddle_adapter
        ),
        middle_row_locator_factory: MiddleRowLocatorFactory = MiddleRowTripleLocator,
        row_first_locator_factory: RowFirstLocatorFactory = RowFirstTripleLocator,
        five_anchor_locator_factory: FiveAnchorLocatorFactory = FiveAnchorRangeLabelLocator,
        v4_orientation_override: MiddleRowRunOrientation = MiddleRowRunOrientation.AUTO,
    ) -> None:
        self._store = store
        self._browser_root = browser_upload_root.resolve() / BROWSER_SELECTION_DIRECTORY
        self._artifact_root = artifact_root.resolve()
        self._repository_root = repository_root.resolve()
        self._recognizer_factory = recognizer_factory
        self._middle_row_recognizer_factory = middle_row_recognizer_factory
        self._middle_row_locator_factory = middle_row_locator_factory
        self._row_first_locator_factory = row_first_locator_factory
        self._five_anchor_locator_factory = five_anchor_locator_factory
        self._v4_orientation_override = v4_orientation_override

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        try:
            payload = SemiAutomaticImageSelectionJobPayload.model_validate(job.input_payload)
            run = self._store.get_run_for_job(job.id)
            self._validate_contract(run, payload)
            if run.status in {
                SemiAutomaticSelectionRunStatus.CLEANUP_PENDING,
                SemiAutomaticSelectionRunStatus.CLEANUP_BLOCKED,
            }:
                self._cleanup_filename_verification(context, job, run=run)
                return
            if run.status is SemiAutomaticSelectionRunStatus.PAUSED:
                context.wait_for_review()
            source_root = _safe_child(self._browser_root, str(run.source.upload_id))
            sources = _load_staged_sources(source_root, run)
            audit = SemiAutomaticSelectionAudit(self._artifact_root, run.id)
            checkpoint = _normalize_checkpoint(run.checkpoint)
            audit.reconcile(
                observation_count=_checkpoint_int(checkpoint, "observationCount"),
                group_count=_checkpoint_int(checkpoint, "finalizedGroupCount"),
            )
            if checkpoint["phase"] == "analysis_complete":
                _verify_report(audit, run)
                if run.workflow_mode is SemiAutomaticSelectionWorkflowMode.FILENAME_VERIFICATION:
                    _job_checkpoint(
                        context,
                        run,
                        checkpoint,
                        total=run.source.source_count,
                    )
                context.wait_for_review()
            if checkpoint["phase"] == "scanning":
                run, checkpoint = self._scan(
                    context,
                    job,
                    run=run,
                    sources=sources,
                    source_root=source_root,
                    audit=audit,
                    checkpoint=checkpoint,
                )
            if checkpoint["phase"] == "selecting":
                if run.workflow_mode is SemiAutomaticSelectionWorkflowMode.FILENAME_VERIFICATION:
                    self._finish_filename_verification(
                        context,
                        job,
                        run=run,
                        audit=audit,
                        checkpoint=checkpoint,
                    )
                    return
                run, checkpoint = self._select(
                    context,
                    job,
                    run=run,
                    audit=audit,
                    checkpoint=checkpoint,
                )
            self._finish(context, job, run=run, audit=audit, checkpoint=checkpoint)
        except SemiAutomaticSelectionError as error:
            raise JobHandlerError(error.code, error.message) from error
        except JobError:
            raise
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            LOGGER.exception(
                "Semi-automatic selection failed while validating durable input for job %s.",
                job.id,
            )
            raise JobHandlerError(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "The semi-automatic selection could not validate its durable input.",
            ) from error

    def _scan(
        self,
        context: JobExecutionContext,
        job: Job,
        *,
        run: SemiAutomaticSelectionRun,
        sources: tuple[_StagedSource, ...],
        source_root: Path,
        audit: SemiAutomaticSelectionAudit,
        checkpoint: dict[str, object],
    ) -> tuple[SemiAutomaticSelectionRun, dict[str, object]]:
        if run.recognizer_fingerprint == ROW_FIRST_RECOGNIZER_CONTRACT_FINGERPRINT_V5:
            return self._scan_row_first_v5(
                context,
                job,
                run=run,
                sources=sources,
                source_root=source_root,
                audit=audit,
                checkpoint=checkpoint,
            )
        if run.recognizer_fingerprint == MIDDLE_ROW_RECOGNIZER_CONTRACT_FINGERPRINT_V4:
            return self._scan_middle_row_v4(
                context,
                job,
                run=run,
                sources=sources,
                source_root=source_root,
                audit=audit,
                checkpoint=checkpoint,
            )
        if run.recognizer_fingerprint == FIVE_ANCHOR_RECOGNIZER_CONTRACT_FINGERPRINT_V6:
            return self._scan_five_anchor_v6(
                context,
                job,
                run=run,
                sources=sources,
                source_root=source_root,
                audit=audit,
                checkpoint=checkpoint,
            )
        bounds = _worker_bounds(run)
        recognizer = self._recognizer_factory(
            self._repository_root / "artifacts" / "m5-models" / "sequence-number-ocr-v1",
            run.recognizer_fingerprint,
        )
        checkpoint_recognizer = checkpoint.get("runtimeRecognizerFingerprint")
        if checkpoint_recognizer is not None and checkpoint_recognizer != recognizer.fingerprint:
            raise JobHandlerError(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "The range recognizer changed after the scan was checkpointed.",
            )
        adapter = RangeOnlyOcrAdapter(bounds=bounds, recognizer=recognizer)
        grouping_checkpoint = cast(
            dict[str, object] | None,
            checkpoint.get("groupingState"),
        )
        accumulator = RangeGroupingAccumulator(checkpoint=grouping_checkpoint)
        scheduler = _restore_ocr_probe_scheduler(
            run=run,
            checkpoint=checkpoint,
            next_source_index=accumulator.next_source_index,
        )
        counters = dict(run.counters)
        for staged in sources[accumulator.next_source_index :]:
            evidence, ocr_probed = _recognize_staged_source(
                adapter,
                staged,
                source_root=source_root,
                bounds=bounds,
                scheduler=scheduler,
            )
            audit.append_observation(evidence)
            groups = accumulator.consume(evidence)
            audit.append_groups(groups)
            _increment_observation_counters(counters, evidence)
            if scheduler is not None:
                if ocr_probed:
                    counters["ocrProbedSources"] = counters.get("ocrProbedSources", 0) + 1
                elif RANGE_ONLY_OCR_SKIPPED_REASON in evidence.reason_codes:
                    counters["ocrSkippedSources"] = counters.get("ocrSkippedSources", 0) + 1
            counters["processedSources"] = accumulator.next_source_index
            counters["groups"] = _object_as_int(accumulator.checkpoint()["nextGroupOrder"])
            if scheduler is not None and (
                accumulator.next_source_index
                % RANGE_ONLY_OCR_SCHEDULING_POLICY_V3.checkpoint_interval_sources
                and accumulator.next_source_index != len(sources)
            ):
                continue
            checkpoint = _scanning_checkpoint(
                accumulator,
                runtime_recognizer_fingerprint=recognizer.fingerprint,
                ocr_scheduling_state=(None if scheduler is None else scheduler.checkpoint()),
            )
            audit.write_checkpoint(checkpoint)
            run = self._store.persist_checkpoint(
                job_id=job.id,
                run_id=run.id,
                lease_token=context.lease_token,
                checkpoint=checkpoint,
                counters=counters,
                persisted_at=context.now(),
            )
            _job_checkpoint(context, run, checkpoint, total=len(sources))
            if run.status is SemiAutomaticSelectionRunStatus.PAUSED:
                context.wait_for_review()

        final_groups = accumulator.finish()
        audit.append_groups(final_groups)
        counters["groups"] = _object_as_int(accumulator.checkpoint()["nextGroupOrder"])
        checkpoint = {
            "finalizedGroupCount": counters["groups"],
            "nextGroupOrderForSelection": 0,
            "observationCount": len(sources),
            "phase": "selecting",
            "runtimeRecognizerFingerprint": recognizer.fingerprint,
            "schemaVersion": SEMI_AUTOMATIC_CHECKPOINT_SCHEMA_VERSION,
        }
        audit.write_checkpoint(checkpoint)
        run = self._store.persist_checkpoint(
            job_id=job.id,
            run_id=run.id,
            lease_token=context.lease_token,
            checkpoint=checkpoint,
            counters=counters,
            persisted_at=context.now(),
        )
        _job_checkpoint(context, run, checkpoint, total=len(sources))
        return run, checkpoint

    def _scan_middle_row_v4(
        self,
        context: JobExecutionContext,
        job: Job,
        *,
        run: SemiAutomaticSelectionRun,
        sources: tuple[_StagedSource, ...],
        source_root: Path,
        audit: SemiAutomaticSelectionAudit,
        checkpoint: dict[str, object],
    ) -> tuple[SemiAutomaticSelectionRun, dict[str, object]]:
        bounds = _worker_bounds(run)
        expected_ranges = ExpectedRangeTable.from_bounds(bounds)
        locator = self._middle_row_locator_factory()
        recognizer = self._middle_row_recognizer_factory(
            self._repository_root / "artifacts" / "m5-models" / "sequence-number-ocr-v1"
        )
        runtime_policy = MiddleRowRuntimePolicy(
            batch=DEFAULT_MIDDLE_ROW_RUNTIME_POLICY.batch,
            orientation=DEFAULT_MIDDLE_ROW_RUNTIME_POLICY.orientation,
            prior=DEFAULT_MIDDLE_ROW_RUNTIME_POLICY.prior,
            orientation_override=self._v4_orientation_override,
        )
        calibration_raw = checkpoint.get("orientationCalibration")
        calibration: MiddleRowOrientationCalibration
        if isinstance(calibration_raw, Mapping):
            calibration = MiddleRowOrientationCalibration.from_dict(calibration_raw)
            if (
                calibration.unresolved
                and self._v4_orientation_override is not MiddleRowRunOrientation.AUTO
            ):
                calibration = calibrate_middle_row_orientation(
                    payloads=(),
                    expected_ranges=expected_ranges,
                    locator=locator,
                    recognizer=recognizer,
                    override=self._v4_orientation_override,
                    policy=runtime_policy.orientation,
                )
        else:
            sample_indexes = deterministic_orientation_sample_indexes(
                len(sources),
                sample_count=runtime_policy.orientation.calibration_source_count,
            )
            sample_payloads = _load_middle_row_payloads(
                tuple(sources[index] for index in sample_indexes),
                source_root=source_root,
            )
            calibration = calibrate_middle_row_orientation(
                payloads=sample_payloads,
                expected_ranges=expected_ranges,
                locator=locator,
                recognizer=recognizer,
                override=self._v4_orientation_override,
                policy=runtime_policy.orientation,
            )

        if calibration.unresolved or calibration.orientation is None:
            counters = dict(run.counters)
            counters["unknownOrientation"] = counters.get("unknownOrientation", 0) + 1
            checkpoint = {
                **checkpoint,
                "diagnosticCounters": dict(counters),
                "orientationCalibration": calibration.as_dict(),
                "orientationUnresolved": True,
                "phase": "scanning",
                "runtimeVariant": MIDDLE_ROW_RECOGNIZER_CONTRACT_FINGERPRINT_V4,
                "schemaVersion": SEMI_AUTOMATIC_CHECKPOINT_SCHEMA_VERSION,
                "sourceBatchSize": runtime_policy.batch.source_batch_size,
            }
            audit.write_checkpoint(checkpoint)
            run = self._store.persist_checkpoint(
                job_id=job.id,
                run_id=run.id,
                lease_token=context.lease_token,
                checkpoint=checkpoint,
                counters=counters,
                persisted_at=context.now(),
            )
            _job_checkpoint(context, run, checkpoint, total=len(sources))
            context.wait_for_review()

        grouping_checkpoint = cast(
            Mapping[str, object] | None,
            checkpoint.get("groupingState"),
        )
        accumulator = MiddleRowGroupingAccumulator(checkpoint=grouping_checkpoint)
        prior_checkpoint = cast(
            Mapping[str, object] | None,
            checkpoint.get("latticePriorState"),
        )
        prior_tracker = MiddleRowLatticePriorTracker(
            runtime_policy.prior,
            checkpoint=prior_checkpoint,
        )
        runtime = MiddleRowBatchRuntime(
            run_id=run.id,
            expected_ranges=expected_ranges,
            rotation=cast(MiddleRowRunOrientation, calibration.orientation),
            locator=locator,
            recognizer=recognizer,
            policy=runtime_policy,
            prior_tracker=prior_tracker,
        )
        checkpoint_runtime = checkpoint.get("runtimeRecognizerFingerprint")
        if checkpoint_runtime is not None and checkpoint_runtime != runtime.runtime_fingerprint:
            raise JobHandlerError(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "The v4.1 runtime fingerprint changed after checkpointing.",
            )
        checkpoint_batch_size = checkpoint.get("sourceBatchSize")
        if checkpoint_batch_size is not None and _object_as_int(checkpoint_batch_size) != (
            runtime_policy.batch.source_batch_size
        ):
            raise JobHandlerError(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "The v4.1 source batch size changed after checkpointing.",
            )

        counters = dict(run.counters)
        counter_base = dict(counters)
        next_source = accumulator.next_source_index
        batch_number = _object_as_int(checkpoint.get("lastCommittedBatch", -1)) + 1
        while next_source < len(sources):
            staged_batch = sources[
                next_source : next_source + runtime_policy.batch.source_batch_size
            ]
            payloads = _load_middle_row_payloads(staged_batch, source_root=source_root)
            observations = runtime.process_batch(payloads)
            finalized_groups: list[FinalizedMiddleRowGroup] = []
            for evidence in observations:
                audit.append_observation(evidence)
                finalized_groups.extend(accumulator.consume(evidence))
                _increment_observation_counters(counters, evidence)
            audit.append_groups(item.group for item in finalized_groups)
            counters["processedSources"] = accumulator.next_source_index
            counters["groups"] = accumulator.next_group_order
            for key, value in runtime.counters.values.items():
                counters[key] = counter_base.get(key, 0) + value
            checkpoint = _middle_row_scanning_checkpoint(
                accumulator=accumulator,
                calibration=calibration,
                runtime=runtime,
                counters=counters,
                last_committed_batch=batch_number,
            )
            audit.write_checkpoint(checkpoint)
            run = self._store.persist_checkpoint(
                job_id=job.id,
                run_id=run.id,
                lease_token=context.lease_token,
                checkpoint=checkpoint,
                counters=counters,
                persisted_at=context.now(),
            )
            _job_checkpoint(context, run, checkpoint, total=len(sources))
            if run.status is SemiAutomaticSelectionRunStatus.PAUSED:
                context.wait_for_review()
            next_source = accumulator.next_source_index
            batch_number += 1

        final_groups = accumulator.finish()
        audit.append_groups(item.group for item in final_groups)
        counters["groups"] = accumulator.next_group_order
        checkpoint = {
            "diagnosticCounters": dict(counters),
            "finalizedGroupCount": accumulator.next_group_order,
            "lastCommittedBatch": max(-1, batch_number - 1),
            "nextGroupOrderForSelection": 0,
            "observationCount": len(sources),
            "ocrBatchFillRatio": _middle_row_batch_fill_ratio(counters),
            "orientationCalibration": calibration.as_dict(),
            "phase": "selecting",
            "runtimeRecognizerFingerprint": runtime.runtime_fingerprint,
            "runtimeVariant": MIDDLE_ROW_RECOGNIZER_CONTRACT_FINGERPRINT_V4,
            "savedRanges": list(cast(Sequence[object], checkpoint.get("savedRanges", []))),
            "schemaVersion": SEMI_AUTOMATIC_CHECKPOINT_SCHEMA_VERSION,
            "sourceBatchSize": runtime_policy.batch.source_batch_size,
        }
        audit.write_checkpoint(checkpoint)
        run = self._store.persist_checkpoint(
            job_id=job.id,
            run_id=run.id,
            lease_token=context.lease_token,
            checkpoint=checkpoint,
            counters=counters,
            persisted_at=context.now(),
        )
        _job_checkpoint(context, run, checkpoint, total=len(sources))
        return run, checkpoint

    def _scan_row_first_v5(
        self,
        context: JobExecutionContext,
        job: Job,
        *,
        run: SemiAutomaticSelectionRun,
        sources: tuple[_StagedSource, ...],
        source_root: Path,
        audit: SemiAutomaticSelectionAudit,
        checkpoint: dict[str, object],
    ) -> tuple[SemiAutomaticSelectionRun, dict[str, object]]:
        """Scan v5 only by its stored contract and whole-source checkpoints."""

        expected_ranges = RowExpectedRangeTable.from_bounds(_worker_bounds(run))
        locator = self._row_first_locator_factory()
        recognizer = self._middle_row_recognizer_factory(
            self._repository_root / "artifacts" / "m5-models" / "sequence-number-ocr-v1"
        )
        runtime = RowFirstBatchRuntime(
            run_id=run.id,
            expected_ranges=expected_ranges,
            locator=locator,
            recognizer=recognizer,
            policy=DEFAULT_ROW_FIRST_RUNTIME_POLICY,
        )
        checkpoint_runtime = checkpoint.get("runtimeRecognizerFingerprint")
        if checkpoint_runtime is not None and checkpoint_runtime != runtime.runtime_fingerprint:
            raise JobHandlerError(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "The v5 row-first runtime fingerprint changed after checkpointing.",
            )
        checkpoint_batch_size = checkpoint.get("sourceBatchSize")
        if checkpoint_batch_size is not None and _object_as_int(checkpoint_batch_size) != (
            runtime.policy.batch.source_batch_size
        ):
            raise JobHandlerError(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "The v5 source batch size changed after checkpointing.",
            )

        grouping_checkpoint = cast(
            Mapping[str, object] | None,
            checkpoint.get("groupingState"),
        )
        accumulator = MiddleRowGroupingAccumulator(
            algorithm_version=ROW_FIRST_GROUPING_VERSION,
            selector_version=ROW_FIRST_EVIDENCE_SELECTOR_VERSION,
            checkpoint=grouping_checkpoint,
        )
        counters = dict(run.counters)
        counter_base = dict(counters)
        next_source = accumulator.next_source_index
        batch_number = _object_as_int(checkpoint.get("lastCommittedBatch", -1)) + 1
        while next_source < len(sources):
            staged_batch = sources[
                next_source : next_source + runtime.policy.batch.source_batch_size
            ]
            payloads = _load_row_first_payloads(staged_batch, source_root=source_root)
            observations = runtime.process_batch(payloads)
            finalized_groups: list[FinalizedMiddleRowGroup] = []
            for evidence in observations:
                audit.append_observation(evidence)
                finalized_groups.extend(accumulator.consume(evidence))
                _increment_observation_counters(counters, evidence)
            audit.append_groups(item.group for item in finalized_groups)
            counters["processedSources"] = accumulator.next_source_index
            counters["groups"] = accumulator.next_group_order
            for key, value in runtime.counters.values.items():
                counters[key] = counter_base.get(key, 0) + value
            checkpoint = _row_first_scanning_checkpoint(
                accumulator=accumulator,
                runtime=runtime,
                counters=counters,
                last_committed_batch=batch_number,
            )
            audit.write_checkpoint(checkpoint)
            run = self._store.persist_checkpoint(
                job_id=job.id,
                run_id=run.id,
                lease_token=context.lease_token,
                checkpoint=checkpoint,
                counters=counters,
                persisted_at=context.now(),
            )
            _job_checkpoint(context, run, checkpoint, total=len(sources))
            if run.status is SemiAutomaticSelectionRunStatus.PAUSED:
                context.wait_for_review()
            next_source = accumulator.next_source_index
            batch_number += 1

        final_groups = accumulator.finish()
        audit.append_groups(item.group for item in final_groups)
        counters["groups"] = accumulator.next_group_order
        checkpoint = {
            "diagnosticCounters": dict(counters),
            "finalizedGroupCount": accumulator.next_group_order,
            "lastCommittedBatch": max(-1, batch_number - 1),
            "nextGroupOrderForSelection": 0,
            "observationCount": len(sources),
            "ocrBatchFillRatio": _middle_row_batch_fill_ratio(counters),
            "phase": "selecting",
            "runtimeRecognizerFingerprint": runtime.runtime_fingerprint,
            "runtimeVariant": ROW_FIRST_RECOGNIZER_CONTRACT_FINGERPRINT_V5,
            "savedRanges": list(cast(Sequence[object], checkpoint.get("savedRanges", []))),
            "schemaVersion": SEMI_AUTOMATIC_CHECKPOINT_SCHEMA_VERSION,
            "sourceBatchSize": runtime.policy.batch.source_batch_size,
        }
        audit.write_checkpoint(checkpoint)
        run = self._store.persist_checkpoint(
            job_id=job.id,
            run_id=run.id,
            lease_token=context.lease_token,
            checkpoint=checkpoint,
            counters=counters,
            persisted_at=context.now(),
        )
        _job_checkpoint(context, run, checkpoint, total=len(sources))
        return run, checkpoint

    def _scan_five_anchor_v6(
        self,
        context: JobExecutionContext,
        job: Job,
        *,
        run: SemiAutomaticSelectionRun,
        sources: tuple[_StagedSource, ...],
        source_root: Path,
        audit: SemiAutomaticSelectionAudit,
        checkpoint: dict[str, object],
    ) -> tuple[SemiAutomaticSelectionRun, dict[str, object]]:
        """Scan v6 only through its persisted five-anchor fingerprint.

        The durable run still owns ordinary grouping and midpoint selection, but
        only source-local v6 exact proofs may become candidates.  It never
        reconstructs a range from filename, source ordinal or neighbours.
        """

        expected_ranges = FiveAnchorExpectedRangeTable.from_bounds(_worker_bounds(run))
        locator = self._five_anchor_locator_factory()
        recognizer = self._middle_row_recognizer_factory(
            self._repository_root / "artifacts" / "m5-models" / "sequence-number-ocr-v1"
        )
        runtime = FiveAnchorBatchRuntime(
            run_id=run.id,
            expected_ranges=expected_ranges,
            locator=locator,
            recognizer=recognizer,
            policy=DEFAULT_FIVE_ANCHOR_RUNTIME_POLICY,
        )
        checkpoint_runtime = checkpoint.get("runtimeRecognizerFingerprint")
        if checkpoint_runtime is not None and checkpoint_runtime != runtime.runtime_fingerprint:
            raise JobHandlerError(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "The v6 five-anchor runtime fingerprint changed after checkpointing.",
            )
        checkpoint_batch_size = checkpoint.get("sourceBatchSize")
        if checkpoint_batch_size is not None and _object_as_int(checkpoint_batch_size) != (
            runtime.policy.batch.source_batch_size
        ):
            raise JobHandlerError(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "The v6 five-anchor source batch size changed after checkpointing.",
            )

        grouping_checkpoint = cast(Mapping[str, object] | None, checkpoint.get("groupingState"))
        accumulator = MiddleRowGroupingAccumulator(
            algorithm_version=FIVE_ANCHOR_GROUPING_VERSION,
            selector_version=FIVE_ANCHOR_EVIDENCE_SELECTOR_VERSION,
            checkpoint=grouping_checkpoint,
        )
        counters = dict(run.counters)
        counter_base = dict(counters)
        next_source = accumulator.next_source_index
        batch_number = _object_as_int(checkpoint.get("lastCommittedBatch", -1)) + 1
        while next_source < len(sources):
            staged_batch = sources[
                next_source : next_source + runtime.policy.batch.source_batch_size
            ]
            observations = runtime.process_batch(
                _load_five_anchor_payloads(staged_batch, source_root=source_root)
            )
            finalized_groups: list[FinalizedMiddleRowGroup] = []
            for evidence in observations:
                audit.append_observation(evidence)
                finalized_groups.extend(accumulator.consume(evidence))
                _increment_observation_counters(counters, evidence)
            audit.append_groups(item.group for item in finalized_groups)
            counters["processedSources"] = accumulator.next_source_index
            counters["groups"] = accumulator.next_group_order
            for key, value in runtime.counters.values.items():
                counters[key] = counter_base.get(key, 0) + value
            checkpoint = _five_anchor_scanning_checkpoint(
                accumulator=accumulator,
                runtime=runtime,
                counters=counters,
                last_committed_batch=batch_number,
            )
            audit.write_checkpoint(checkpoint)
            run = self._store.persist_checkpoint(
                job_id=job.id,
                run_id=run.id,
                lease_token=context.lease_token,
                checkpoint=checkpoint,
                counters=counters,
                persisted_at=context.now(),
            )
            _job_checkpoint(context, run, checkpoint, total=len(sources))
            if run.status is SemiAutomaticSelectionRunStatus.PAUSED:
                context.wait_for_review()
            next_source = accumulator.next_source_index
            batch_number += 1

        final_groups = accumulator.finish()
        audit.append_groups(item.group for item in final_groups)
        counters["groups"] = accumulator.next_group_order
        checkpoint = {
            "diagnosticCounters": dict(counters),
            "finalizedGroupCount": accumulator.next_group_order,
            "lastCommittedBatch": max(-1, batch_number - 1),
            "nextGroupOrderForSelection": 0,
            "observationCount": len(sources),
            "ocrBatchFillRatio": _middle_row_batch_fill_ratio(counters),
            "phase": "selecting",
            "runtimeRecognizerFingerprint": runtime.runtime_fingerprint,
            "runtimeVariant": FIVE_ANCHOR_RECOGNIZER_CONTRACT_FINGERPRINT_V6,
            "savedRanges": list(cast(Sequence[object], checkpoint.get("savedRanges", []))),
            "schemaVersion": SEMI_AUTOMATIC_CHECKPOINT_SCHEMA_VERSION,
            "sourceBatchSize": runtime.policy.batch.source_batch_size,
        }
        audit.write_checkpoint(checkpoint)
        run = self._store.persist_checkpoint(
            job_id=job.id,
            run_id=run.id,
            lease_token=context.lease_token,
            checkpoint=checkpoint,
            counters=counters,
            persisted_at=context.now(),
        )
        _job_checkpoint(context, run, checkpoint, total=len(sources))
        return run, checkpoint

    def _select(
        self,
        context: JobExecutionContext,
        job: Job,
        *,
        run: SemiAutomaticSelectionRun,
        audit: SemiAutomaticSelectionAudit,
        checkpoint: dict[str, object],
    ) -> tuple[SemiAutomaticSelectionRun, dict[str, object]]:
        start = _checkpoint_int(checkpoint, "nextGroupOrderForSelection")
        maximum_seen = _object_as_int(checkpoint.get("maximumTraversalExpectedIndexSeen", -1))
        is_middle_row_v4 = (
            run.recognizer_fingerprint == MIDDLE_ROW_RECOGNIZER_CONTRACT_FINGERPRINT_V4
        )
        is_row_first_v5 = run.recognizer_fingerprint == ROW_FIRST_RECOGNIZER_CONTRACT_FINGERPRINT_V5
        is_five_anchor_v6 = (
            run.recognizer_fingerprint == FIVE_ANCHOR_RECOGNIZER_CONTRACT_FINGERPRINT_V6
        )
        selection_method = (
            MIDDLE_ROW_EVIDENCE_SELECTOR_VERSION
            if is_middle_row_v4
            else (
                ROW_FIRST_EVIDENCE_SELECTOR_VERSION
                if is_row_first_v5
                else (
                    FIVE_ANCHOR_EVIDENCE_SELECTOR_VERSION if is_five_anchor_v6 else None
                )
            )
        )
        for selection in audit.iter_group_selections(
            start_group_order=start,
            selection_method=selection_method,
        ):
            is_out_of_order = selection.group.expected_index < maximum_seen
            maximum_seen = max(maximum_seen, selection.group.expected_index)
            next_group = selection.group.group_order + 1
            next_checkpoint: dict[str, object] = {
                "finalizedGroupCount": _checkpoint_int(checkpoint, "finalizedGroupCount"),
                "maximumTraversalExpectedIndexSeen": maximum_seen,
                "nextGroupOrderForSelection": next_group,
                "observationCount": _checkpoint_int(checkpoint, "observationCount"),
                "phase": "selecting",
                "runtimeRecognizerFingerprint": checkpoint["runtimeRecognizerFingerprint"],
                "schemaVersion": SEMI_AUTOMATIC_CHECKPOINT_SCHEMA_VERSION,
            }
            if is_middle_row_v4 or is_row_first_v5 or is_five_anchor_v6:
                saved_ranges = [
                    _object_as_int(item)
                    for item in cast(Sequence[object], checkpoint.get("savedRanges", []))
                ]
                if selection.group.expected_index not in saved_ranges:
                    saved_ranges.append(selection.group.expected_index)
                next_checkpoint.update(
                    {
                        "diagnosticCounters": checkpoint.get("diagnosticCounters", {}),
                        "lastCommittedBatch": checkpoint.get("lastCommittedBatch", -1),
                        "ocrBatchFillRatio": checkpoint.get("ocrBatchFillRatio", 0.0),
                        "runtimeVariant": (
                            MIDDLE_ROW_RECOGNIZER_CONTRACT_FINGERPRINT_V4
                            if is_middle_row_v4
                            else (
                                ROW_FIRST_RECOGNIZER_CONTRACT_FINGERPRINT_V5
                                if is_row_first_v5
                                else FIVE_ANCHOR_RECOGNIZER_CONTRACT_FINGERPRINT_V6
                            )
                        ),
                        "savedRanges": saved_ranges,
                        "sourceBatchSize": checkpoint["sourceBatchSize"],
                    }
                )
                if is_middle_row_v4:
                    next_checkpoint["orientationCalibration"] = checkpoint["orientationCalibration"]
            checkpoint = next_checkpoint
            outcome = self._store.apply_selection(
                job_id=job.id,
                run_id=run.id,
                lease_token=context.lease_token,
                selection=selection,
                checkpoint=checkpoint,
                increment_out_of_order=is_out_of_order,
                persisted_at=context.now(),
            )
            run = outcome.run
            audit.write_checkpoint(checkpoint)
            _job_checkpoint(
                context,
                run,
                checkpoint,
                total=run.source.source_count,
            )
            if run.status is SemiAutomaticSelectionRunStatus.PAUSED:
                context.wait_for_review()
        return run, checkpoint

    def _finish(
        self,
        context: JobExecutionContext,
        job: Job,
        *,
        run: SemiAutomaticSelectionRun,
        audit: SemiAutomaticSelectionAudit,
        checkpoint: dict[str, object],
    ) -> None:
        missing = self._store.missing_ranges(run.id)
        counters = dict(run.counters)
        counters["missing"] = len(missing)
        checkpoint = {
            **checkpoint,
            "phase": "analysis_complete",
            "schemaVersion": SEMI_AUTOMATIC_CHECKPOINT_SCHEMA_VERSION,
        }
        relative_path, checksum = audit.write_report(
            {
                "counters": counters,
                "expectedRangesFingerprint": run.expected_ranges_fingerprint,
                "groupingPolicyFingerprint": run.grouping_policy_fingerprint,
                "missingRanges": [
                    {"expectedIndex": index, "rangeEnd": end, "rangeStart": start}
                    for index, start, end in missing
                ],
                "recognizerFingerprint": run.recognizer_fingerprint,
                "runtimeRecognizerFingerprint": checkpoint.get("runtimeRecognizerFingerprint"),
                "runId": str(run.id),
                "sourceFingerprint": run.source.source_fingerprint,
            }
        )
        audit.write_checkpoint(checkpoint)
        run = self._store.finalize_analysis(
            job_id=job.id,
            run_id=run.id,
            lease_token=context.lease_token,
            checkpoint=checkpoint,
            counters=counters,
            diagnostics_relative_path=relative_path,
            diagnostics_checksum_sha256=checksum,
            persisted_at=context.now(),
        )
        if run.status is SemiAutomaticSelectionRunStatus.PAUSED:
            _job_checkpoint(context, run, run.checkpoint, total=run.source.source_count)
            context.wait_for_review()
        _job_checkpoint(context, run, checkpoint, total=run.source.source_count)
        context.wait_for_review()

    def _finish_filename_verification(
        self,
        context: JobExecutionContext,
        job: Job,
        *,
        run: SemiAutomaticSelectionRun,
        audit: SemiAutomaticSelectionAudit,
        checkpoint: dict[str, object],
    ) -> None:
        """Finalize OCR evidence without selecting or materializing any JPEG."""

        run = self._store.reset_unacknowledged_filename_selections(
            job_id=job.id,
            run_id=run.id,
            lease_token=context.lease_token,
            persisted_at=context.now(),
        )
        totals = {
            "invalid_filename": 0,
            "mismatch": 0,
            "unreadable": 0,
            "verified": 0,
        }
        for observation in audit.iter_observation_payloads():
            status = str(classify_filename_range_verification(observation)["verificationStatus"])
            if status not in totals:
                raise JobHandlerError(
                    "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                    "The filename verification classifier returned an unsupported status.",
                )
            totals[status] += 1
        observation_count = _checkpoint_int(checkpoint, "observationCount")
        if sum(totals.values()) != observation_count:
            raise JobHandlerError(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "The committed filename verification observations are incomplete.",
            )
        counters = dict(run.counters)
        counters.update(
            {
                "filenameInvalidFilename": totals["invalid_filename"],
                "filenameMismatch": totals["mismatch"],
                "filenameReviewRequired": (
                    totals["invalid_filename"] + totals["mismatch"] + totals["unreadable"]
                ),
                "filenameUnreadable": totals["unreadable"],
                "filenameVerified": totals["verified"],
            }
        )
        checkpoint = {
            **checkpoint,
            "phase": "analysis_complete",
            "schemaVersion": SEMI_AUTOMATIC_CHECKPOINT_SCHEMA_VERSION,
        }
        relative_path, checksum = audit.write_report(
            {
                "counters": counters,
                "filenameVerification": totals,
                "recognizerFingerprint": run.recognizer_fingerprint,
                "runtimeRecognizerFingerprint": checkpoint.get("runtimeRecognizerFingerprint"),
                "runId": str(run.id),
                "sourceFingerprint": run.source.source_fingerprint,
                "workflowMode": run.workflow_mode.value,
            }
        )
        audit.write_checkpoint(checkpoint)
        run = self._store.finalize_analysis(
            job_id=job.id,
            run_id=run.id,
            lease_token=context.lease_token,
            checkpoint=checkpoint,
            counters=counters,
            diagnostics_relative_path=relative_path,
            diagnostics_checksum_sha256=checksum,
            persisted_at=context.now(),
        )
        _job_checkpoint(context, run, checkpoint, total=run.source.source_count)
        if counters["filenameReviewRequired"] == 0:
            self._cleanup_filename_verification(context, job, run=run)
            return
        context.wait_for_review()

    def _cleanup_filename_verification(
        self,
        context: JobExecutionContext,
        job: Job,
        *,
        run: SemiAutomaticSelectionRun,
    ) -> None:
        """Remove a completed filename run without touching operator-owned data."""

        if run.workflow_mode is not SemiAutomaticSelectionWorkflowMode.FILENAME_VERIFICATION:
            raise JobHandlerError(
                "SEMI_AUTOMATIC_SELECTION_CLEANUP_BLOCKED",
                "Only filename verification runs may remove their working data.",
            )
        try:
            reserved = self._store.begin_filename_verification_cleanup(
                job_id=job.id,
                run_id=run.id,
                lease_token=context.lease_token,
                persisted_at=context.now(),
            )
            plan = self._filename_verification_cleanup_plan(reserved)
            self._quarantine_and_remove_cleanup_directories(plan)
            completed = self._store.complete_filename_verification_cleanup(
                job_id=job.id,
                run_id=reserved.id,
                lease_token=context.lease_token,
                persisted_at=context.now(),
            )
        except JobHandlerError as error:
            if error.code != "JOB_LEASE_LOST":
                self._store.mark_filename_verification_cleanup_blocked(
                    job_id=job.id,
                    run_id=run.id,
                    lease_token=context.lease_token,
                    error_code=error.code,
                    persisted_at=context.now(),
                )
            raise
        _job_checkpoint(
            context,
            completed,
            completed.checkpoint,
            total=completed.source.source_count,
        )

    def _filename_verification_cleanup_plan(
        self,
        run: SemiAutomaticSelectionRun,
    ) -> FilenameVerificationCleanupPlan:
        artifacts_root = self._artifact_root / "exports" / "semi-automatic-selection"
        staging_root = self._browser_root
        return FilenameVerificationCleanupPlan(
            artifact_directory=_managed_direct_child(artifacts_root, str(run.id)),
            artifact_trash_directory=_managed_direct_child(
                artifacts_root / ".filename-verification-trash",
                str(run.id),
            ),
            staging_directory=_managed_direct_child(staging_root, str(run.source.upload_id)),
            staging_trash_directory=_managed_direct_child(
                staging_root / ".filename-verification-trash",
                str(run.id),
            ),
        )

    @staticmethod
    def _quarantine_and_remove_cleanup_directories(
        plan: FilenameVerificationCleanupPlan,
    ) -> None:
        pairs = (
            (plan.artifact_directory, plan.artifact_trash_directory),
            (plan.staging_directory, plan.staging_trash_directory),
        )
        for original, quarantined in pairs:
            _quarantine_directory_for_cleanup(original, quarantined)
        for _original, quarantined in pairs:
            _delete_quarantined_directory(quarantined)

    @staticmethod
    def _validate_contract(
        run: SemiAutomaticSelectionRun,
        payload: SemiAutomaticImageSelectionJobPayload,
    ) -> None:
        if (
            payload.run_id != run.id
            or payload.source_upload_id != run.source.upload_id
            or payload.source_manifest_checksum_sha256 != run.source.manifest_checksum_sha256
            or payload.source_fingerprint != run.source.source_fingerprint
            or payload.source_count != run.source.source_count
        ):
            raise JobHandlerError(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED",
                "The durable job payload differs from its staged source run.",
            )
        if run.recognizer_fingerprint not in SUPPORTED_RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINTS:
            raise JobHandlerError(
                "SEMI_AUTOMATIC_SELECTION_RECOGNIZER_UNSUPPORTED",
                "The durable run references an unsupported range recognizer.",
            )
        expected_grouping_fingerprint = (
            middle_row_grouping_policy_fingerprint()
            if run.recognizer_fingerprint == MIDDLE_ROW_RECOGNIZER_CONTRACT_FINGERPRINT_V4
            else (
                row_first_grouping_policy_fingerprint()
                if run.recognizer_fingerprint == ROW_FIRST_RECOGNIZER_CONTRACT_FINGERPRINT_V5
                else (
                    five_anchor_grouping_policy_fingerprint()
                    if run.recognizer_fingerprint
                    == FIVE_ANCHOR_RECOGNIZER_CONTRACT_FINGERPRINT_V6
                    else grouping_policy_fingerprint()
                )
            )
        )
        if run.grouping_policy_fingerprint != expected_grouping_fingerprint:
            raise JobHandlerError(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "The durable run references another grouping policy.",
            )


def _load_staged_sources(
    source_root: Path,
    run: SemiAutomaticSelectionRun,
) -> tuple[_StagedSource, ...]:
    manifest_path = _safe_child(source_root, BROWSER_SELECTION_MANIFEST)
    content = manifest_path.read_bytes()
    if hashlib.sha256(content).hexdigest() != run.source.manifest_checksum_sha256:
        _fail_source_changed("The staged source manifest changed after run creation.")
    decoded = json.loads(content)
    if not isinstance(decoded, dict):
        _fail_source_changed("The staged source manifest has an incompatible contract.")
    payload = cast(dict[str, Any], decoded)
    if (
        payload.get("schemaVersion") != 1
        or payload.get("purpose") != "semi_automatic_selection"
        or payload.get("gameId") is not None
        or payload.get("orderingPolicy") != "natural_relative_path_v1"
        or not isinstance(payload.get("files"), list)
    ):
        _fail_source_changed("The staged source manifest has an incompatible contract.")
    raw_files = cast(list[object], payload["files"])
    if len(raw_files) != run.source.source_count:
        _fail_source_changed("The staged source count changed after run creation.")
    staged: list[_StagedSource] = []
    source_payload: list[dict[str, object]] = []
    relative_paths: set[str] = set()
    previous_natural_key: tuple[tuple[int, int | str], ...] | None = None
    for expected_index, raw in enumerate(raw_files):
        if not isinstance(raw, dict):
            _fail_source_changed("A staged source manifest entry is invalid.")
        item = cast(dict[str, object], raw)
        try:
            source = SemiAutomaticSelectionSource(
                source_index=_object_as_int(item["orderIndex"]),
                relative_path=str(item["relativePath"]).replace("\\", "/"),
                size_bytes=_object_as_int(item["sizeBytes"]),
                checksum_sha256=str(item["checksumSha256"]),
            )
            stored_file_name = str(item["storedFileName"])
        except (KeyError, TypeError, ValueError, SemiAutomaticSelectionError) as error:
            raise JobHandlerError(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED",
                "A staged source manifest entry is invalid.",
            ) from error
        suffix = PurePosixPath(source.relative_path).suffix.casefold()
        if (
            source.source_index != expected_index
            or suffix not in {".jpg", ".jpeg"}
            or stored_file_name != f"{expected_index + 1:08d}{suffix}"
            or source.relative_path in relative_paths
        ):
            _fail_source_changed("The staged source ordering or storage name changed.")
        natural_key = _natural_path_key(source.relative_path)
        if previous_natural_key is not None and natural_key < previous_natural_key:
            _fail_source_changed("The staged source list is not in natural path order.")
        relative_paths.add(source.relative_path)
        previous_natural_key = natural_key
        staged.append(_StagedSource(identity=source, stored_file_name=stored_file_name))
        source_payload.append(source.as_dict())
    fingerprint = hashlib.sha256(
        json.dumps(source_payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    if fingerprint != run.source.source_fingerprint:
        _fail_source_changed("The staged source fingerprint changed after run creation.")
    return tuple(staged)


def _load_middle_row_payloads(
    staged_sources: Sequence[_StagedSource],
    *,
    source_root: Path,
) -> tuple[MiddleRowSourcePayload, ...]:
    payloads: list[MiddleRowSourcePayload] = []
    for staged in staged_sources:
        path = _safe_child(source_root, staged.stored_file_name)
        try:
            content = path.read_bytes()
        except OSError as error:
            raise JobHandlerError(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED",
                "A staged JPEG disappeared before middle-row OCR.",
            ) from error
        if (
            len(content) != staged.identity.size_bytes
            or hashlib.sha256(content).hexdigest() != staged.identity.checksum_sha256
        ):
            _fail_source_changed("A staged JPEG changed after run creation.")
        payloads.append(MiddleRowSourcePayload(source=staged.identity, content=content))
    return tuple(payloads)


def _load_row_first_payloads(
    staged_sources: Sequence[_StagedSource],
    *,
    source_root: Path,
) -> tuple[RowFirstSourcePayload, ...]:
    """Load only checksum-bound JPEG bytes for the v5 recognition-only path."""

    payloads: list[RowFirstSourcePayload] = []
    for staged in staged_sources:
        path = _safe_child(source_root, staged.stored_file_name)
        try:
            content = path.read_bytes()
        except OSError as error:
            raise JobHandlerError(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED",
                "A staged JPEG disappeared before row-first OCR.",
            ) from error
        if (
            len(content) != staged.identity.size_bytes
            or hashlib.sha256(content).hexdigest() != staged.identity.checksum_sha256
        ):
            _fail_source_changed("A staged JPEG changed after run creation.")
        payloads.append(RowFirstSourcePayload(source=staged.identity, content=content))
    return tuple(payloads)


def _load_five_anchor_payloads(
    staged_sources: Sequence[_StagedSource],
    *,
    source_root: Path,
) -> tuple[FiveAnchorSourcePayload, ...]:
    """Load checksum-bound source bytes for the v6 five-anchor runtime only."""

    payloads: list[FiveAnchorSourcePayload] = []
    for staged in staged_sources:
        path = _safe_child(source_root, staged.stored_file_name)
        try:
            content = path.read_bytes()
        except OSError as error:
            raise JobHandlerError(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED",
                "A staged JPEG disappeared before five-anchor OCR.",
            ) from error
        if (
            len(content) != staged.identity.size_bytes
            or hashlib.sha256(content).hexdigest() != staged.identity.checksum_sha256
        ):
            _fail_source_changed("A staged JPEG changed after run creation.")
        payloads.append(FiveAnchorSourcePayload(source=staged.identity, content=content))
    return tuple(payloads)


def _recognize_staged_source(
    adapter: RangeOnlyOcrAdapter,
    staged: _StagedSource,
    *,
    source_root: Path,
    bounds: SemiAutomaticSequenceBounds,
    scheduler: AdaptiveRangeOcrProbeScheduler | None,
) -> tuple[RangeEvidenceResult, bool]:
    source = staged.identity
    path = _safe_child(source_root, staged.stored_file_name)
    try:
        if path.stat().st_size != source.size_bytes or _sha256_file(path) != source.checksum_sha256:
            _fail_source_changed("A staged JPEG changed after run creation.")
        if scheduler is not None:
            thumbnail_rgb = _load_scheduler_thumbnail(
                path,
                maximum_edge=RANGE_ONLY_OCR_SCHEDULING_POLICY_V3.thumbnail_max_edge,
            )
            decision = scheduler.decide(
                source_index=source.source_index,
                thumbnail_rgb=thumbnail_rgb,
            )
            if not decision.should_probe:
                return (
                    adapter.unproven(
                        source=source,
                        reason_codes=(RANGE_ONLY_OCR_SKIPPED_REASON,),
                    ),
                    False,
                )
        rgb = _load_full_rgb(path)
    except JobHandlerError:
        raise
    except (OSError, UnidentifiedImageError, ValueError):
        if scheduler is not None:
            if scheduler.next_source_index == source.source_index:
                scheduler.record_unavailable(source_index=source.source_index)
            else:
                scheduler.force_probe_after_failure()
        return (
            RangeEvidenceGate(bounds).evaluate(
                RangeEvidenceObservation(
                    source=source,
                    observed_range=None,
                    confidence=None,
                    has_strong_local_proof=False,
                    source_decodable=False,
                    diagnostic_reason_codes=("SOURCE_DECODE_FAILED",),
                )
            ),
            False,
        )
    return adapter.recognize(source=source, rgb_image=rgb), True


def _load_scheduler_thumbnail(path: Path, *, maximum_edge: int) -> NDArray[np.uint8]:
    with Image.open(path) as image:
        image.draft("RGB", (maximum_edge, maximum_edge))
        thumbnail = ImageOps.exif_transpose(image).convert("RGB")
        thumbnail.thumbnail((maximum_edge, maximum_edge), Image.Resampling.BILINEAR)
        return np.asarray(thumbnail, dtype=np.uint8)


def _load_full_rgb(path: Path) -> NDArray[np.uint8]:
    with Image.open(path) as image:
        return np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)


def _restore_ocr_probe_scheduler(
    *,
    run: SemiAutomaticSelectionRun,
    checkpoint: Mapping[str, object],
    next_source_index: int,
) -> AdaptiveRangeOcrProbeScheduler | None:
    raw_state = checkpoint.get("ocrSchedulingState")
    if run.recognizer_fingerprint != RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V3:
        if raw_state is not None:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "A historical OCR run cannot contain adaptive scheduling state.",
            )
        return None
    state = cast(Mapping[str, object] | None, raw_state)
    if next_source_index > 0 and state is None:
        raise SemiAutomaticSelectionError(
            "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
            "The adaptive OCR run is missing its durable scheduling state.",
        )
    scheduler = AdaptiveRangeOcrProbeScheduler(
        RANGE_ONLY_OCR_SCHEDULING_POLICY_V3,
        checkpoint=state,
    )
    if scheduler.next_source_index != next_source_index:
        raise SemiAutomaticSelectionError(
            "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
            "OCR scheduling and range grouping checkpoints differ.",
        )
    return scheduler


def _worker_bounds(run: SemiAutomaticSelectionRun) -> SemiAutomaticSequenceBounds:
    direction = SemiAutomaticSelectionDirection(run.direction.value)
    if direction is SemiAutomaticSelectionDirection.ASCENDING:
        first, last = run.first_sequence_number, run.last_sequence_number
    else:
        first, last = run.last_sequence_number, run.first_sequence_number
    return SemiAutomaticSequenceBounds(
        first_sequence_number=first,
        last_sequence_number=last,
        direction=direction,
        full_range_size=run.full_range_size,
    )


def _normalize_checkpoint(value: Mapping[str, object]) -> dict[str, object]:
    if not value:
        return {
            "finalizedGroupCount": 0,
            "groupingState": None,
            "observationCount": 0,
            "phase": "scanning",
            "schemaVersion": SEMI_AUTOMATIC_CHECKPOINT_SCHEMA_VERSION,
        }
    checkpoint = dict(value)
    if checkpoint.get(
        "schemaVersion"
    ) != SEMI_AUTOMATIC_CHECKPOINT_SCHEMA_VERSION or checkpoint.get("phase") not in {
        "scanning",
        "selecting",
        "analysis_complete",
    }:
        raise SemiAutomaticSelectionError(
            "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
            "The durable selection checkpoint has an unsupported contract.",
        )
    _checkpoint_int(checkpoint, "observationCount")
    _checkpoint_int(checkpoint, "finalizedGroupCount")
    runtime_recognizer = checkpoint.get("runtimeRecognizerFingerprint")
    requires_runtime_recognizer = (
        checkpoint["phase"] in {"selecting", "analysis_complete"}
        or _checkpoint_int(checkpoint, "observationCount") > 0
    )
    if requires_runtime_recognizer and not _is_sha256(runtime_recognizer):
        raise SemiAutomaticSelectionError(
            "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
            "The durable checkpoint is missing the runtime recognizer fingerprint.",
        )
    return checkpoint


def _scanning_checkpoint(
    accumulator: RangeGroupingAccumulator,
    *,
    runtime_recognizer_fingerprint: str,
    ocr_scheduling_state: Mapping[str, object] | None,
) -> dict[str, object]:
    state = accumulator.checkpoint()
    checkpoint: dict[str, object] = {
        "finalizedGroupCount": _object_as_int(state["nextGroupOrder"]),
        "groupingState": state,
        "observationCount": accumulator.next_source_index,
        "phase": "scanning",
        "runtimeRecognizerFingerprint": runtime_recognizer_fingerprint,
        "schemaVersion": SEMI_AUTOMATIC_CHECKPOINT_SCHEMA_VERSION,
    }
    if ocr_scheduling_state is not None:
        checkpoint["ocrSchedulingState"] = dict(ocr_scheduling_state)
    return checkpoint


def _middle_row_scanning_checkpoint(
    *,
    accumulator: MiddleRowGroupingAccumulator,
    calibration: MiddleRowOrientationCalibration,
    runtime: MiddleRowBatchRuntime,
    counters: Mapping[str, int],
    last_committed_batch: int,
) -> dict[str, object]:
    state = accumulator.checkpoint()
    orientation = calibration.as_dict()
    return {
        "diagnosticCounters": dict(counters),
        "finalizedGroupCount": accumulator.next_group_order,
        "groupingState": state,
        "lastCommittedBatch": last_committed_batch,
        "latticePriorState": runtime.prior_tracker.checkpoint(),
        "observationCount": accumulator.next_source_index,
        "ocrBatchFillRatio": _middle_row_batch_fill_ratio(counters),
        "orientation": orientation["orientation"],
        "orientationCalibration": orientation,
        "orientationCalibrationProofs": orientation["orientationCalibrationProofs"],
        "orientationCalibrationSamples": orientation["orientationCalibrationSamples"],
        "orientationOverride": orientation["orientationOverride"],
        "orientationSource": orientation["orientationSource"],
        "orientationUnresolved": orientation["orientationUnresolved"],
        "phase": "scanning",
        "runtimeRecognizerFingerprint": runtime.runtime_fingerprint,
        "runtimeVariant": MIDDLE_ROW_RECOGNIZER_CONTRACT_FINGERPRINT_V4,
        "savedRanges": [],
        "schemaVersion": SEMI_AUTOMATIC_CHECKPOINT_SCHEMA_VERSION,
        "sourceBatchSize": runtime.policy.batch.source_batch_size,
    }


def _row_first_scanning_checkpoint(
    *,
    accumulator: MiddleRowGroupingAccumulator,
    runtime: RowFirstBatchRuntime,
    counters: Mapping[str, int],
    last_committed_batch: int,
) -> dict[str, object]:
    state = accumulator.checkpoint()
    return {
        "diagnosticCounters": dict(counters),
        "finalizedGroupCount": accumulator.next_group_order,
        "groupingState": state,
        "lastCommittedBatch": last_committed_batch,
        "observationCount": accumulator.next_source_index,
        "ocrBatchFillRatio": _middle_row_batch_fill_ratio(counters),
        "phase": "scanning",
        "runtimeRecognizerFingerprint": runtime.runtime_fingerprint,
        "runtimeVariant": ROW_FIRST_RECOGNIZER_CONTRACT_FINGERPRINT_V5,
        "savedRanges": [],
        "schemaVersion": SEMI_AUTOMATIC_CHECKPOINT_SCHEMA_VERSION,
        "sourceBatchSize": runtime.policy.batch.source_batch_size,
    }


def _five_anchor_scanning_checkpoint(
    *,
    accumulator: MiddleRowGroupingAccumulator,
    runtime: FiveAnchorBatchRuntime,
    counters: Mapping[str, int],
    last_committed_batch: int,
) -> dict[str, object]:
    state = accumulator.checkpoint()
    return {
        "diagnosticCounters": dict(counters),
        "finalizedGroupCount": accumulator.next_group_order,
        "groupingState": state,
        "lastCommittedBatch": last_committed_batch,
        "observationCount": accumulator.next_source_index,
        "ocrBatchFillRatio": _middle_row_batch_fill_ratio(counters),
        "phase": "scanning",
        "runtimeRecognizerFingerprint": runtime.runtime_fingerprint,
        "runtimeVariant": FIVE_ANCHOR_RECOGNIZER_CONTRACT_FINGERPRINT_V6,
        "savedRanges": [],
        "schemaVersion": SEMI_AUTOMATIC_CHECKPOINT_SCHEMA_VERSION,
        "sourceBatchSize": runtime.policy.batch.source_batch_size,
    }


def _increment_observation_counters(
    counters: dict[str, int],
    evidence: RangeEvidenceResult,
) -> None:
    key = {
        RangeEvidenceStatus.EXACT_RANGE: "exactObservations",
        RangeEvidenceStatus.RANGE_UNREADABLE: "unreadableObservations",
        RangeEvidenceStatus.RANGE_AMBIGUOUS: "ambiguousObservations",
        RangeEvidenceStatus.INVALID_RANGE: "invalidRangeObservations",
        RangeEvidenceStatus.OUTSIDE_REQUESTED_RANGE: "outsideRangeObservations",
        RangeEvidenceStatus.NOT_EXPECTED_RANGE: "notExpectedRangeObservations",
        RangeEvidenceStatus.SOURCE_ERROR: "sourceErrors",
    }[evidence.status]
    counters[key] = counters.get(key, 0) + 1


def _middle_row_batch_fill_ratio(counters: Mapping[str, int]) -> float:
    internal_batches = counters.get("ocrInternalBatches", 0)
    if internal_batches < 1:
        return 0.0
    return counters.get("ocrCrops", 0) / (internal_batches * 9)


def _job_checkpoint(
    context: JobExecutionContext,
    run: SemiAutomaticSelectionRun,
    checkpoint: Mapping[str, object],
    *,
    total: int,
) -> None:
    counters = run.counters
    is_terminal_analysis = checkpoint["phase"] in {
        "analysis_complete",
        "cleanup_complete",
    }
    if run.workflow_mode is SemiAutomaticSelectionWorkflowMode.FILENAME_VERIFICATION:
        success_count = counters.get("filenameVerified", 0) if is_terminal_analysis else 0
        review_count = counters.get("filenameReviewRequired", 0) if is_terminal_analysis else 0
    else:
        success_count = counters.get("autoSelected", 0)
        review_count = counters.get("missing", 0) if is_terminal_analysis else 0
    context.checkpoint(
        checkpoint_payload={
            "schema_version": 1,
            "semi_automatic_image_selection": dict(checkpoint),
        },
        stage=f"{SEMI_AUTOMATIC_SELECTION_STAGE}:{checkpoint['phase']}",
        current=_checkpoint_int(checkpoint, "observationCount"),
        total=total,
        success_count=success_count,
        failure_count=counters.get("sourceErrors", 0),
        review_count=review_count,
    )


def _verify_report(audit: SemiAutomaticSelectionAudit, run: SemiAutomaticSelectionRun) -> None:
    if (
        run.diagnostics_relative_path is None
        or run.diagnostics_checksum_sha256 is None
        or not audit.report_path.is_file()
        or _sha256_file(audit.report_path) != run.diagnostics_checksum_sha256
    ):
        raise SemiAutomaticSelectionError(
            "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
            "The completed diagnostics report changed or disappeared.",
        )


def _checkpoint_int(value: Mapping[str, object], key: str) -> int:
    try:
        result = _object_as_int(value[key])
    except (KeyError, TypeError, ValueError) as error:
        raise SemiAutomaticSelectionError(
            "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
            f"The durable checkpoint is missing {key}.",
        ) from error
    if result < 0:
        raise SemiAutomaticSelectionError(
            "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
            f"The durable checkpoint has invalid {key}.",
        )
    return result


def _safe_child(root: Path, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path.replace("\\", "/"))
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise JobHandlerError(
            "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED",
            "A staged source path is unsafe.",
        )
    target = root.joinpath(*relative.parts).resolve()
    if root != target and root not in target.parents:
        raise JobHandlerError(
            "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED",
            "A staged source path escapes the managed staging root.",
        )
    return target


def _managed_direct_child(root: Path, name: str) -> Path:
    """Return one direct child of a managed root without following symlinks."""

    if not name or Path(name).name != name or name in {".", ".."}:
        raise JobHandlerError(
            "SEMI_AUTOMATIC_SELECTION_CLEANUP_PATH_UNSAFE",
            "A filename verification cleanup path is unsafe.",
        )
    resolved_root = root.resolve()
    if root.is_symlink():
        raise JobHandlerError(
            "SEMI_AUTOMATIC_SELECTION_CLEANUP_PATH_UNSAFE",
            "A managed filename verification root must not be a symbolic link.",
        )
    candidate = root / name
    if candidate.is_symlink():
        raise JobHandlerError(
            "SEMI_AUTOMATIC_SELECTION_CLEANUP_PATH_UNSAFE",
            "A filename verification cleanup target must not be a symbolic link.",
        )
    if candidate.exists() and candidate.resolve().parent != resolved_root:
        raise JobHandlerError(
            "SEMI_AUTOMATIC_SELECTION_CLEANUP_PATH_UNSAFE",
            "A filename verification cleanup target escapes its managed root.",
        )
    return candidate


def _quarantine_directory_for_cleanup(original: Path, quarantined: Path) -> None:
    if original.is_symlink() or quarantined.is_symlink():
        raise JobHandlerError(
            "SEMI_AUTOMATIC_SELECTION_CLEANUP_PATH_UNSAFE",
            "A filename verification cleanup path must not be a symbolic link.",
        )
    if original.exists() and not original.is_dir():
        raise JobHandlerError(
            "SEMI_AUTOMATIC_SELECTION_CLEANUP_BLOCKED",
            "A managed filename verification directory has an unexpected file type.",
        )
    if original.exists() and quarantined.exists():
        raise JobHandlerError(
            "SEMI_AUTOMATIC_SELECTION_CLEANUP_BLOCKED",
            "A previous filename verification cleanup requires recovery.",
        )
    if not original.exists():
        return
    try:
        quarantined.parent.mkdir(parents=True, exist_ok=True)
        original.replace(quarantined)
    except OSError as error:
        raise JobHandlerError(
            "SEMI_AUTOMATIC_SELECTION_CLEANUP_FAILED",
            "The filename verification working directory could not be quarantined.",
        ) from error


def _delete_quarantined_directory(quarantined: Path) -> None:
    if not quarantined.exists():
        return
    if quarantined.is_symlink() or not quarantined.is_dir():
        raise JobHandlerError(
            "SEMI_AUTOMATIC_SELECTION_CLEANUP_PATH_UNSAFE",
            "The filename verification quarantine is unsafe.",
        )
    try:
        shutil.rmtree(quarantined)
    except FileNotFoundError:
        return
    except OSError as error:
        raise JobHandlerError(
            "SEMI_AUTOMATIC_SELECTION_CLEANUP_FAILED",
            "The filename verification quarantine could not be removed.",
        ) from error
    # The trash root may contain another resumable cleanup.  It is not a
    # run-owned directory and therefore must never turn a successful cleanup
    # into a failure just because it is non-empty.
    with suppress(OSError):
        quarantined.parent.rmdir()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_fence(
    session: Session,
    job_id: UUID,
    lease_token: UUID,
    persisted_at: datetime,
) -> None:
    job = session.scalar(select(JobModel).where(JobModel.id == job_id).with_for_update())
    if (
        job is None
        or job.status != JobStatus.PROCESSING
        or job.lease_token != lease_token
        or job.lease_expires_at is None
        or job.lease_expires_at <= persisted_at
    ):
        raise JobConflictError(
            "JOB_LEASE_LOST",
            "The worker lease no longer permits semi-automatic selection writes.",
        )


def _locked_run(session: Session, run_id: UUID) -> SemiAutomaticImageSelectionRunModel:
    record = session.scalar(
        select(SemiAutomaticImageSelectionRunModel)
        .where(SemiAutomaticImageSelectionRunModel.id == run_id)
        .with_for_update()
    )
    if record is None:
        raise JobHandlerError(
            "SEMI_AUTOMATIC_SELECTION_NOT_FOUND",
            "The semi-automatic selection run no longer exists.",
        )
    return record


def _locked_job(session: Session, job_id: UUID) -> JobModel:
    record = session.scalar(select(JobModel).where(JobModel.id == job_id).with_for_update())
    if record is None:
        raise JobHandlerError(
            "SEMI_AUTOMATIC_SELECTION_NOT_FOUND",
            "The semi-automatic selection job no longer exists.",
        )
    return record


def _assert_filename_verification_cleanup_references(
    session: Session,
    *,
    run_record: SemiAutomaticImageSelectionRunModel,
    job_id: UUID,
) -> None:
    """Fail closed whenever the staging is shared outside this one run.

    Filename verification has no valid handoff: it must not own game data,
    local output, or a second run.  The checks are repeated before database
    finalization because filesystem deletion and SQL cannot share a transaction.
    """

    if run_record.workflow_mode != SemiAutomaticSelectionWorkflowMode.FILENAME_VERIFICATION.value:
        raise JobHandlerError(
            "SEMI_AUTOMATIC_SELECTION_CLEANUP_BLOCKED",
            "Only filename verification runs may remove this staging.",
        )
    shared_runs = tuple(
        session.scalars(
            select(SemiAutomaticImageSelectionRunModel.id)
            .where(
                SemiAutomaticImageSelectionRunModel.source_upload_id
                == run_record.source_upload_id,
                SemiAutomaticImageSelectionRunModel.id != run_record.id,
            )
            .with_for_update()
        )
    )
    if shared_runs:
        raise JobHandlerError(
            "SEMI_AUTOMATIC_SELECTION_CLEANUP_BLOCKED",
            "The browser staging is still referenced by another selection run.",
        )
    foreign_jobs = tuple(
        session.scalars(
            select(JobModel.id)
            .where(
                JobModel.id != job_id,
                JobModel.input_payload["source_selection_id"].as_string()
                == str(run_record.source_upload_id),
            )
            .with_for_update()
        )
    )
    if foreign_jobs:
        raise JobHandlerError(
            "SEMI_AUTOMATIC_SELECTION_CLEANUP_BLOCKED",
            "The browser staging is still referenced by another image job.",
        )
    protected_outputs = int(
        session.scalar(
            select(func.count())
            .select_from(SemiAutomaticImageSelectionRangeModel)
            .where(
                SemiAutomaticImageSelectionRangeModel.run_id == run_record.id,
                (
                    SemiAutomaticImageSelectionRangeModel.status
                    == SemiAutomaticSelectionRangeStatus.OUTPUT_SYNCED.value
                )
                | (SemiAutomaticImageSelectionRangeModel.output_checksum_sha256.is_not(None)),
            )
        )
        or 0
    )
    if protected_outputs:
        raise JobHandlerError(
            "SEMI_AUTOMATIC_SELECTION_CLEANUP_BLOCKED",
            "The filename verification run has a protected local output reference.",
        )


def _apply_run_progress(
    record: SemiAutomaticImageSelectionRunModel,
    checkpoint: Mapping[str, object],
    counters: Mapping[str, int],
    persisted_at: datetime,
) -> None:
    record.checkpoint = dict(checkpoint)
    record.counters = {key: int(value) for key, value in counters.items()}
    record.revision += 1
    record.updated_at = persisted_at


def _domain_run(session: Session, run_id: UUID) -> SemiAutomaticSelectionRun:
    run = SqlAlchemySemiAutomaticSelectionRepository(session).get(run_id)
    if run is None:
        raise JobHandlerError(
            "SEMI_AUTOMATIC_SELECTION_NOT_FOUND",
            "The semi-automatic selection run no longer exists.",
        )
    return run


def _object_as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise TypeError("value is not an integer")
    return int(value)


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _natural_path_key(value: str) -> tuple[tuple[int, int | str], ...]:
    return tuple(
        (1, int(part)) if part.isdigit() else (0, part.casefold())
        for part in _NATURAL_PATH_PART.split(value)
    )


def _fail_source_changed(message: str) -> NoReturn:
    raise JobHandlerError("SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED", message)


__all__ = [
    "SelectionApplyOutcome",
    "SemiAutomaticImageSelectionJobHandler",
    "SemiAutomaticSelectionJobStore",
]
