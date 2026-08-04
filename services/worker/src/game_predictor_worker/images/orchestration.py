"""Durable per-file orchestration over the versioned image pipeline contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, cast
from uuid import UUID

from game_predictor_api.domain.jobs import Job, JobType

from game_predictor_worker.jobs.runtime import (
    JobExecutionContext,
    JobHandlerError,
)

from .pipeline_contract import (
    FILE_CHECKPOINT_VERSION,
    PIPELINE_STAGES,
    file_execution_key,
    validate_checkpoint_transition,
    validate_file_checkpoint,
)

IMAGE_BATCH_CHECKPOINT_VERSION = "image-batch-checkpoint-v1"
IMAGE_IMPORT_KIND = "image_directory"


class ImageStageExecutionResult(StrEnum):
    COMPLETED = "completed"
    WAITING_FOR_REVIEW = "waiting_for_review"


@dataclass(frozen=True, slots=True)
class ImageFileExecution:
    file_execution_key: str
    source_checksum_sha256: str
    pipeline_fingerprint: str
    checkpoint_payload: dict[str, object]
    status: str
    review_required: bool
    error_code: str | None = None
    error_message: str | None = None
    failed_stage: str | None = None
    retry_count: int = 0
    last_failed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ImageBatchCandidate:
    execution: ImageFileExecution
    order_index: int
    source_relative_path: str
    job_id: UUID | None = None
    lease_token: UUID | None = None
    executed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ImageFileRegistration:
    source_checksum_sha256: str
    source_relative_path: str
    order_index: int


@dataclass(frozen=True, slots=True)
class ImageBatchStats:
    total: int
    current: int
    succeeded: int
    failed: int
    review: int
    waiting: int


@dataclass(slots=True)
class _IncrementalBatchStats:
    """Track exact batch counters without rescanning every job association."""

    total: int
    current: int
    succeeded: int
    failed: int
    review: int
    waiting: int

    @classmethod
    def from_snapshot(cls, snapshot: ImageBatchStats) -> _IncrementalBatchStats:
        return cls(
            total=snapshot.total,
            current=snapshot.current,
            succeeded=snapshot.succeeded,
            failed=snapshot.failed,
            review=snapshot.review,
            waiting=snapshot.waiting,
        )

    def observe_transition(
        self,
        previous: ImageFileExecution,
        current: ImageFileExecution,
    ) -> None:
        previous_values = _stats_contribution(previous)
        current_values = _stats_contribution(current)
        self.current += current_values[0] - previous_values[0]
        self.succeeded += current_values[1] - previous_values[1]
        self.failed += current_values[2] - previous_values[2]
        self.review += current_values[3] - previous_values[3]
        self.waiting += current_values[4] - previous_values[4]

    def snapshot(self) -> ImageBatchStats:
        return ImageBatchStats(
            total=self.total,
            current=self.current,
            succeeded=self.succeeded,
            failed=self.failed,
            review=self.review,
            waiting=self.waiting,
        )


class ImageStageExecutor(Protocol):
    def execute_stage(
        self,
        candidate: ImageBatchCandidate,
        stage: str,
    ) -> ImageStageExecutionResult: ...


class ImageResultRehydrator(Protocol):
    def rehydrate(self, candidate: ImageBatchCandidate) -> None: ...


class ImageBatchStore(Protocol):
    def count_job_files(self, job_id: UUID, *, pipeline_fingerprint: str) -> int: ...

    def next_processing_file(
        self,
        job_id: UUID,
        *,
        pipeline_fingerprint: str,
    ) -> ImageBatchCandidate | None: ...

    def next_waiting_file(
        self,
        job_id: UUID,
        *,
        pipeline_fingerprint: str,
        after_order_index: int,
    ) -> ImageBatchCandidate | None: ...

    def save_file_checkpoint(
        self,
        job_id: UUID,
        *,
        lease_token: UUID,
        expected_checkpoint: Mapping[str, object],
        checkpoint_payload: Mapping[str, object],
        checkpointed_at: datetime,
    ) -> ImageFileExecution: ...

    def fail_file(
        self,
        job_id: UUID,
        *,
        lease_token: UUID,
        expected_checkpoint: Mapping[str, object],
        failed_stage: str,
        error_code: str,
        error_message: str,
        failed_at: datetime,
    ) -> ImageFileExecution: ...

    def retry_file(
        self,
        job_id: UUID,
        *,
        file_execution_key: str,
        expected_stage: str,
        retried_at: datetime,
    ) -> ImageFileExecution: ...

    def batch_stats(
        self,
        job_id: UUID,
        *,
        pipeline_fingerprint: str,
    ) -> ImageBatchStats: ...


def initial_file_checkpoint(
    source_checksum_sha256: str,
    pipeline_fingerprint: str,
) -> dict[str, object]:
    """Build the first persistence-neutral checkpoint for one source."""

    execution_key = file_execution_key(source_checksum_sha256, pipeline_fingerprint)
    checkpoint = {
        "completedStages": [],
        "contractVersion": FILE_CHECKPOINT_VERSION,
        "fileExecutionKey": execution_key,
        "nextStage": PIPELINE_STAGES[0],
        "pipelineFingerprint": pipeline_fingerprint,
        "schemaVersion": 1,
        "sourceChecksumSha256": source_checksum_sha256,
        "status": "processing",
    }
    return validate_file_checkpoint(checkpoint)


def advance_file_checkpoint(
    checkpoint_payload: Mapping[str, object],
    result: ImageStageExecutionResult,
) -> dict[str, object]:
    """Advance exactly one stage or preserve an unresolved review checkpoint."""

    previous = validate_file_checkpoint(checkpoint_payload)
    next_stage = cast(str | None, previous["nextStage"])
    if next_stage is None:
        raise JobHandlerError(
            "IMAGE_FILE_ALREADY_COMPLETED",
            "A completed image file has no next stage.",
        )
    if result is ImageStageExecutionResult.WAITING_FOR_REVIEW:
        if next_stage != "manual_review" or previous["status"] != "waiting_for_review":
            raise JobHandlerError(
                "IMAGE_REVIEW_STAGE_INVALID",
                "Only an unresolved manual_review stage may remain waiting.",
            )
        return previous

    completed = [*cast(list[str], previous["completedStages"]), next_stage]
    if len(completed) == len(PIPELINE_STAGES):
        status = "completed"
        following_stage = None
    elif next_stage == "symbol_inference":
        status = "waiting_for_review"
        following_stage = "manual_review"
    else:
        status = "processing"
        following_stage = PIPELINE_STAGES[len(completed)]
    current = {
        **previous,
        "completedStages": completed,
        "nextStage": following_stage,
        "status": status,
    }
    validate_checkpoint_transition(previous, current)
    return validate_file_checkpoint(current)


class ImageBatchHandler:
    """Run staged image work while keeping every file independently resumable."""

    def __init__(
        self,
        store: ImageBatchStore,
        stage_executor: ImageStageExecutor,
    ) -> None:
        self._store = store
        self._stage_executor = stage_executor

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        pipeline_fingerprint = _pipeline_fingerprint(job)
        initial_stats = self._store.batch_stats(
            job.id,
            pipeline_fingerprint=pipeline_fingerprint,
        )
        if initial_stats.total == 0:
            raise JobHandlerError(
                "IMAGE_BATCH_EMPTY",
                "The image import job has no attested source files.",
            )
        progress = _IncrementalBatchStats.from_snapshot(initial_stats)
        self._recheck_waiting_once(
            context,
            job,
            pipeline_fingerprint,
            progress,
        )
        self._drain_processing(
            context,
            job,
            pipeline_fingerprint,
            progress,
        )
        stats = self._store.batch_stats(
            job.id,
            pipeline_fingerprint=pipeline_fingerprint,
        )
        if stats.waiting or stats.failed:
            context.wait_for_review()
            return
        if stats.current != stats.total:
            raise JobHandlerError(
                "IMAGE_BATCH_INCOMPLETE",
                "The image batch stopped without a review boundary or complete result.",
            )

    def _drain_processing(
        self,
        context: JobExecutionContext,
        job: Job,
        pipeline_fingerprint: str,
        progress: _IncrementalBatchStats,
    ) -> None:
        while candidate := self._store.next_processing_file(
            job.id,
            pipeline_fingerprint=pipeline_fingerprint,
        ):
            self._run_candidate(
                context,
                job,
                candidate,
                pipeline_fingerprint,
                progress,
                rehydrate_review=False,
            )

    def _recheck_waiting_once(
        self,
        context: JobExecutionContext,
        job: Job,
        pipeline_fingerprint: str,
        progress: _IncrementalBatchStats,
    ) -> None:
        cursor = -1
        while candidate := self._store.next_waiting_file(
            job.id,
            pipeline_fingerprint=pipeline_fingerprint,
            after_order_index=cursor,
        ):
            cursor = candidate.order_index
            self._run_candidate(
                context,
                job,
                candidate,
                pipeline_fingerprint,
                progress,
                rehydrate_review=True,
            )

    def _run_candidate(
        self,
        context: JobExecutionContext,
        job: Job,
        candidate: ImageBatchCandidate,
        pipeline_fingerprint: str,
        progress: _IncrementalBatchStats,
        *,
        rehydrate_review: bool,
    ) -> None:
        current = candidate
        should_rehydrate_review = rehydrate_review
        while True:
            checkpoint = validate_file_checkpoint(current.execution.checkpoint_payload)
            stage = cast(str | None, checkpoint["nextStage"])
            if stage is None:
                return
            execution_candidate = ImageBatchCandidate(
                execution=current.execution,
                order_index=current.order_index,
                source_relative_path=current.source_relative_path,
                job_id=job.id,
                lease_token=context.lease_token,
                executed_at=context.now(),
            )
            try:
                rehydrate = getattr(self._stage_executor, "rehydrate", None)
                if (
                    should_rehydrate_review
                    and stage in {"manual_review", "validation"}
                    and callable(rehydrate)
                ):
                    cast(ImageResultRehydrator, self._stage_executor).rehydrate(execution_candidate)
                    should_rehydrate_review = False
                result = self._stage_executor.execute_stage(execution_candidate, stage)
            except Exception as error:
                if (
                    isinstance(error, JobHandlerError)
                    and error.code == "IMAGE_SEQUENCE_REVIEW_REOPENED"
                ):
                    return
                code, message = _safe_stage_failure(error)
                persisted = self._store.fail_file(
                    job.id,
                    lease_token=context.lease_token,
                    expected_checkpoint=checkpoint,
                    failed_stage=stage,
                    error_code=code,
                    error_message=message,
                    failed_at=context.now(),
                )
                progress.observe_transition(current.execution, persisted)
                stats = progress.snapshot()
                context.checkpoint(
                    checkpoint_payload=_job_checkpoint(
                        pipeline_fingerprint,
                        persisted,
                    ),
                    stage=stage,
                    current=stats.current,
                    total=stats.total,
                    success_count=stats.succeeded,
                    failure_count=stats.failed,
                    review_count=stats.review,
                )
                return
            advanced = advance_file_checkpoint(checkpoint, result)
            persisted = self._store.save_file_checkpoint(
                job.id,
                lease_token=context.lease_token,
                expected_checkpoint=checkpoint,
                checkpoint_payload=advanced,
                checkpointed_at=context.now(),
            )
            progress.observe_transition(current.execution, persisted)
            stats = progress.snapshot()
            context.checkpoint(
                checkpoint_payload=_job_checkpoint(
                    pipeline_fingerprint,
                    persisted,
                ),
                stage=stage,
                current=stats.current,
                total=stats.total,
                success_count=stats.succeeded,
                failure_count=stats.failed,
                review_count=stats.review,
            )
            if (
                result is ImageStageExecutionResult.WAITING_FOR_REVIEW
                or persisted.status == "completed"
            ):
                return
            current = ImageBatchCandidate(
                execution=persisted,
                order_index=current.order_index,
                source_relative_path=current.source_relative_path,
                job_id=job.id,
            )


def _stats_contribution(execution: ImageFileExecution) -> tuple[int, int, int, int, int]:
    terminal = execution.status in {"waiting_for_review", "completed", "failed"}
    return (
        int(terminal),
        int(execution.status == "completed"),
        int(execution.status == "failed"),
        int(execution.review_required),
        int(execution.status == "waiting_for_review"),
    )


def _pipeline_fingerprint(job: Job) -> str:
    if (
        job.job_type is not JobType.IMPORT
        or job.input_payload.get("import_kind") != IMAGE_IMPORT_KIND
    ):
        raise JobHandlerError(
            "IMAGE_BATCH_JOB_KIND_INVALID",
            "Image batch orchestration requires an image_directory import job.",
        )
    fingerprint = job.input_payload.get("pipeline_fingerprint")
    if not isinstance(fingerprint, str):
        raise JobHandlerError(
            "IMAGE_BATCH_PIPELINE_MISSING",
            "The image import job is missing pipelineFingerprint.",
        )
    file_execution_key("0" * 64, fingerprint)
    return fingerprint


def _job_checkpoint(
    pipeline_fingerprint: str,
    execution: ImageFileExecution,
) -> dict[str, object]:
    return {
        "checkpoint_kind": IMAGE_BATCH_CHECKPOINT_VERSION,
        "file_checkpoint": execution.checkpoint_payload,
        "last_file_execution_key": execution.file_execution_key,
        "pipeline_fingerprint": pipeline_fingerprint,
        "schema_version": 1,
    }


def _safe_stage_failure(error: Exception) -> tuple[str, str]:
    if isinstance(error, JobHandlerError):
        return error.code, error.message
    return (
        "IMAGE_STAGE_EXECUTION_FAILED",
        "The image stage failed unexpectedly.",
    )


__all__ = [
    "IMAGE_BATCH_CHECKPOINT_VERSION",
    "IMAGE_IMPORT_KIND",
    "ImageBatchCandidate",
    "ImageBatchHandler",
    "ImageBatchStats",
    "ImageBatchStore",
    "ImageFileExecution",
    "ImageFileRegistration",
    "ImageResultRehydrator",
    "ImageStageExecutionResult",
    "ImageStageExecutor",
    "advance_file_checkpoint",
    "initial_file_checkpoint",
]
