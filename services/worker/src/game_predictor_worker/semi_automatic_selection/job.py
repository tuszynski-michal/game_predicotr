"""Durable range-only semi-automatic image-selection job."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast
from uuid import UUID

import numpy as np
from game_predictor_api.domain.jobs import Job, JobConflictError, JobStatus
from game_predictor_api.domain.semi_automatic_image_selections import (
    SemiAutomaticSelectionRangeStatus,
    SemiAutomaticSelectionRun,
    SemiAutomaticSelectionRunStatus,
)
from game_predictor_api.schemas.jobs import SemiAutomaticImageSelectionJobPayload
from game_predictor_api.storage.models import (
    JobModel,
    SemiAutomaticImageSelectionRangeModel,
    SemiAutomaticImageSelectionRunModel,
)
from game_predictor_api.storage.semi_automatic_image_selection_repository import (
    SqlAlchemySemiAutomaticSelectionRepository,
)
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
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
from .range_only_ocr import (
    SUPPORTED_RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINTS,
    RangeOnlyOcrAdapter,
    RangeOnlyRecognizer,
    build_paddle_range_only_recognizer_for_contract,
)

BROWSER_SELECTION_DIRECTORY = "browser-selections"
BROWSER_SELECTION_MANIFEST = "_browser_manifest.json"
SEMI_AUTOMATIC_CHECKPOINT_SCHEMA_VERSION = 1
SEMI_AUTOMATIC_SELECTION_STAGE = "semi_automatic_image_selection"
_NATURAL_PATH_PART = re.compile(r"(\d+)")


@dataclass(frozen=True, slots=True)
class _StagedSource:
    identity: SemiAutomaticSelectionSource
    stored_file_name: str


@dataclass(frozen=True, slots=True)
class SelectionApplyOutcome:
    run: SemiAutomaticSelectionRun
    applied: bool


RecognizerFactory = Callable[[Path, str], RangeOnlyRecognizer]


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
            else:
                counters["duplicateGroups"] = counters.get("duplicateGroups", 0) + 1
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
    ) -> None:
        self._store = store
        self._browser_root = browser_upload_root.resolve() / BROWSER_SELECTION_DIRECTORY
        self._artifact_root = artifact_root.resolve()
        self._repository_root = repository_root.resolve()
        self._recognizer_factory = recognizer_factory

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        try:
            payload = SemiAutomaticImageSelectionJobPayload.model_validate(job.input_payload)
            run = self._store.get_run_for_job(job.id)
            self._validate_contract(run, payload)
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
        except JobConflictError:
            raise
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
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
        counters = dict(run.counters)
        for staged in sources[accumulator.next_source_index :]:
            evidence = _recognize_staged_source(
                adapter,
                staged,
                source_root=source_root,
                bounds=bounds,
            )
            audit.append_observation(evidence)
            groups = accumulator.consume(evidence)
            audit.append_groups(groups)
            _increment_observation_counters(counters, evidence)
            counters["processedSources"] = accumulator.next_source_index
            counters["groups"] = _object_as_int(accumulator.checkpoint()["nextGroupOrder"])
            checkpoint = _scanning_checkpoint(
                accumulator,
                runtime_recognizer_fingerprint=recognizer.fingerprint,
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
        for selection in audit.iter_group_selections(start_group_order=start):
            is_out_of_order = selection.group.expected_index < maximum_seen
            maximum_seen = max(maximum_seen, selection.group.expected_index)
            next_group = selection.group.group_order + 1
            checkpoint = {
                "finalizedGroupCount": _checkpoint_int(checkpoint, "finalizedGroupCount"),
                "maximumTraversalExpectedIndexSeen": maximum_seen,
                "nextGroupOrderForSelection": next_group,
                "observationCount": _checkpoint_int(checkpoint, "observationCount"),
                "phase": "selecting",
                "runtimeRecognizerFingerprint": checkpoint["runtimeRecognizerFingerprint"],
                "schemaVersion": SEMI_AUTOMATIC_CHECKPOINT_SCHEMA_VERSION,
            }
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
        if run.grouping_policy_fingerprint != grouping_policy_fingerprint():
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


def _recognize_staged_source(
    adapter: RangeOnlyOcrAdapter,
    staged: _StagedSource,
    *,
    source_root: Path,
    bounds: SemiAutomaticSequenceBounds,
) -> RangeEvidenceResult:
    source = staged.identity
    path = _safe_child(source_root, staged.stored_file_name)
    try:
        if path.stat().st_size != source.size_bytes or _sha256_file(path) != source.checksum_sha256:
            _fail_source_changed("A staged JPEG changed after run creation.")
        with Image.open(path) as image:
            rgb = np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
    except JobHandlerError:
        raise
    except (OSError, UnidentifiedImageError, ValueError):
        return RangeEvidenceGate(bounds).evaluate(
            RangeEvidenceObservation(
                source=source,
                observed_range=None,
                confidence=None,
                has_strong_local_proof=False,
                source_decodable=False,
                diagnostic_reason_codes=("SOURCE_DECODE_FAILED",),
            )
        )
    return adapter.recognize(source=source, rgb_image=rgb)


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
) -> dict[str, object]:
    state = accumulator.checkpoint()
    return {
        "finalizedGroupCount": _object_as_int(state["nextGroupOrder"]),
        "groupingState": state,
        "observationCount": accumulator.next_source_index,
        "phase": "scanning",
        "runtimeRecognizerFingerprint": runtime_recognizer_fingerprint,
        "schemaVersion": SEMI_AUTOMATIC_CHECKPOINT_SCHEMA_VERSION,
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


def _job_checkpoint(
    context: JobExecutionContext,
    run: SemiAutomaticSelectionRun,
    checkpoint: Mapping[str, object],
    *,
    total: int,
) -> None:
    counters = run.counters
    context.checkpoint(
        checkpoint_payload={"semi_automatic_image_selection": dict(checkpoint)},
        stage=f"{SEMI_AUTOMATIC_SELECTION_STAGE}:{checkpoint['phase']}",
        current=_checkpoint_int(checkpoint, "observationCount"),
        total=total,
        success_count=counters.get("autoSelected", 0),
        failure_count=counters.get("sourceErrors", 0),
        review_count=counters.get("missing", 0),
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
