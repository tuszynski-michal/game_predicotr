from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.jobs import (
    Job,
    JobType,
    create_job,
    start_job,
)
from game_predictor_worker.images.orchestration import (
    IMAGE_IMPORT_KIND,
    ImageBatchCandidate,
    ImageBatchHandler,
    ImageBatchStats,
    ImageFileExecution,
    ImageStageExecutionResult,
    advance_file_checkpoint,
    initial_file_checkpoint,
)
from game_predictor_worker.images.pipeline_contract import (
    PIPELINE_STAGES,
    canonical_json_bytes,
    file_execution_key,
    validate_checkpoint_transition,
    validate_file_checkpoint,
)

PIPELINE_FINGERPRINT = "a" * 64
OTHER_PIPELINE_FINGERPRINT = "b" * 64
NOW = datetime(2026, 7, 29, 12, tzinfo=UTC)


class ExecutionStopped(RuntimeError):
    pass


class SimulatedProcessExit(BaseException):
    pass


class RecordingContext:
    def __init__(
        self,
        job: Job,
        *,
        stop_after_checkpoint: bool = False,
        crash_after_checkpoint: bool = False,
    ) -> None:
        if job.lease_token is None:
            raise ValueError("Test job must be leased.")
        self.job = job
        self.lease_token = job.lease_token
        self.checkpoints: list[dict[str, object]] = []
        self.waiting = False
        self.stop_after_checkpoint = stop_after_checkpoint
        self.crash_after_checkpoint = crash_after_checkpoint

    def now(self) -> datetime:
        return NOW

    def checkpoint(self, **values: object) -> None:
        self.checkpoints.append(dict(values))
        if self.crash_after_checkpoint:
            raise SimulatedProcessExit
        if self.stop_after_checkpoint:
            raise ExecutionStopped("cancelled")

    def wait_for_review(self) -> None:
        self.waiting = True
        raise ExecutionStopped("waiting_for_review")


class MemoryImageBatchStore:
    def __init__(self) -> None:
        self.executions: dict[str, ImageFileExecution] = {}
        self.associations: dict[UUID, list[tuple[int, str, str]]] = {}

    def register(
        self,
        job_id: UUID,
        *,
        checksum: str,
        pipeline_fingerprint: str,
        path: str,
        order_index: int,
    ) -> ImageFileExecution:
        key = file_execution_key(checksum, pipeline_fingerprint)
        execution = self.executions.get(key)
        if execution is None:
            checkpoint = initial_file_checkpoint(checksum, pipeline_fingerprint)
            execution = ImageFileExecution(
                file_execution_key=key,
                source_checksum_sha256=checksum,
                pipeline_fingerprint=pipeline_fingerprint,
                checkpoint_payload=checkpoint,
                status="processing",
                review_required=False,
            )
            self.executions[key] = execution
        association = (order_index, key, path)
        items = self.associations.setdefault(job_id, [])
        if association not in items:
            items.append(association)
            items.sort()
        return execution

    def count_job_files(self, job_id: UUID, *, pipeline_fingerprint: str) -> int:
        return len(self._items(job_id, pipeline_fingerprint))

    def next_processing_file(
        self,
        job_id: UUID,
        *,
        pipeline_fingerprint: str,
    ) -> ImageBatchCandidate | None:
        return next(
            (
                item
                for item in self._items(job_id, pipeline_fingerprint)
                if item.execution.status == "processing"
            ),
            None,
        )

    def next_waiting_file(
        self,
        job_id: UUID,
        *,
        pipeline_fingerprint: str,
        after_order_index: int,
    ) -> ImageBatchCandidate | None:
        return next(
            (
                item
                for item in self._items(job_id, pipeline_fingerprint)
                if item.order_index > after_order_index
                and item.execution.status == "waiting_for_review"
            ),
            None,
        )

    def save_file_checkpoint(
        self,
        job_id: UUID,
        *,
        lease_token: UUID,
        expected_checkpoint: Mapping[str, object],
        checkpoint_payload: Mapping[str, object],
        checkpointed_at: datetime,
    ) -> ImageFileExecution:
        del lease_token, checkpointed_at
        expected = validate_file_checkpoint(expected_checkpoint)
        current = validate_file_checkpoint(checkpoint_payload)
        validate_checkpoint_transition(expected, current)
        key = cast(str, current["fileExecutionKey"])
        assert any(item[1] == key for item in self.associations[job_id])
        persisted = self.executions[key]
        assert canonical_json_bytes(persisted.checkpoint_payload) == canonical_json_bytes(expected)
        updated = replace(
            persisted,
            checkpoint_payload=current,
            status=cast(str, current["status"]),
            review_required=(
                persisted.review_required or current["status"] == "waiting_for_review"
            ),
        )
        self.executions[key] = updated
        return updated

    def batch_stats(
        self,
        job_id: UUID,
        *,
        pipeline_fingerprint: str,
    ) -> ImageBatchStats:
        items = self._items(job_id, pipeline_fingerprint)
        executions = [item.execution for item in items]
        return ImageBatchStats(
            total=len(executions),
            current=sum(
                item.status in {"waiting_for_review", "completed", "failed"} for item in executions
            ),
            succeeded=sum(item.status == "completed" for item in executions),
            failed=sum(item.status == "failed" for item in executions),
            review=sum(item.review_required for item in executions),
            waiting=sum(item.status == "waiting_for_review" for item in executions),
        )

    def _items(
        self,
        job_id: UUID,
        pipeline_fingerprint: str,
    ) -> list[ImageBatchCandidate]:
        return [
            ImageBatchCandidate(
                execution=self.executions[key],
                order_index=order,
                source_relative_path=path,
            )
            for order, key, path in self.associations.get(job_id, [])
            if self.executions[key].pipeline_fingerprint == pipeline_fingerprint
        ]


class ReviewAwareExecutor:
    def __init__(self, *, review_resolved: bool = False) -> None:
        self.review_resolved = review_resolved
        self.calls: list[tuple[str, str]] = []

    def execute_stage(
        self,
        candidate: ImageBatchCandidate,
        stage: str,
    ) -> ImageStageExecutionResult:
        self.calls.append((candidate.source_relative_path, stage))
        if stage == "manual_review" and not self.review_resolved:
            return ImageStageExecutionResult.WAITING_FOR_REVIEW
        return ImageStageExecutionResult.COMPLETED


def _leased_image_job(
    pipeline_fingerprint: str = PIPELINE_FINGERPRINT,
) -> Job:
    created = create_job(
        JobType.IMPORT,
        game_id=uuid4(),
        input_payload={
            "schema_version": 1,
            "import_kind": IMAGE_IMPORT_KIND,
            "pipeline_fingerprint": pipeline_fingerprint,
        },
        created_at=NOW - timedelta(minutes=1),
    )
    return start_job(
        created,
        worker_version="worker-v5",
        worker_id="test-worker",
        lease_token=uuid4(),
        lease_expires_at=NOW + timedelta(minutes=1),
        started_at=NOW - timedelta(seconds=1),
    )


def _register_two(store: MemoryImageBatchStore, job: Job) -> None:
    store.register(
        job.id,
        checksum="1" * 64,
        pipeline_fingerprint=PIPELINE_FINGERPRINT,
        path="session/page-001.jpg",
        order_index=0,
    )
    store.register(
        job.id,
        checksum="2" * 64,
        pipeline_fingerprint=PIPELINE_FINGERPRINT,
        path="session/page-002.jpg",
        order_index=1,
    )


def test_file_checkpoint_advances_one_stage_and_enforces_review() -> None:
    checkpoint = initial_file_checkpoint("1" * 64, PIPELINE_FINGERPRINT)

    for expected_stage in PIPELINE_STAGES[:6]:
        assert checkpoint["nextStage"] == expected_stage
        checkpoint = advance_file_checkpoint(
            checkpoint,
            ImageStageExecutionResult.COMPLETED,
        )

    assert checkpoint["status"] == "waiting_for_review"
    assert checkpoint["nextStage"] == "manual_review"
    assert (
        advance_file_checkpoint(
            checkpoint,
            ImageStageExecutionResult.WAITING_FOR_REVIEW,
        )
        == checkpoint
    )


def test_same_file_pipeline_is_reused_but_model_drift_creates_new_execution() -> None:
    store = MemoryImageBatchStore()
    first_job = _leased_image_job()
    second_job = _leased_image_job()
    checksum = "3" * 64

    first = store.register(
        first_job.id,
        checksum=checksum,
        pipeline_fingerprint=PIPELINE_FINGERPRINT,
        path="first/page.jpg",
        order_index=0,
    )
    reused = store.register(
        second_job.id,
        checksum=checksum,
        pipeline_fingerprint=PIPELINE_FINGERPRINT,
        path="renamed/page.jpg",
        order_index=0,
    )
    changed = store.register(
        second_job.id,
        checksum=checksum,
        pipeline_fingerprint=OTHER_PIPELINE_FINGERPRINT,
        path="renamed/page.jpg",
        order_index=1,
    )

    assert reused.file_execution_key == first.file_execution_key
    assert changed.file_execution_key != first.file_execution_key
    assert len(store.executions) == 2


def test_review_files_do_not_block_diagnostics_and_resume_to_completion() -> None:
    job = _leased_image_job()
    store = MemoryImageBatchStore()
    _register_two(store, job)
    executor = ReviewAwareExecutor()
    context = RecordingContext(job)

    with pytest.raises(ExecutionStopped, match="waiting_for_review"):
        ImageBatchHandler(store, executor)(cast(object, context), job)

    assert context.waiting is True
    assert executor.calls[:12] == [
        (path, stage)
        for path in ("session/page-001.jpg", "session/page-002.jpg")
        for stage in PIPELINE_STAGES[:6]
    ]
    assert executor.calls[12:] == [
        ("session/page-001.jpg", "manual_review"),
        ("session/page-002.jpg", "manual_review"),
    ]
    assert store.batch_stats(
        job.id,
        pipeline_fingerprint=PIPELINE_FINGERPRINT,
    ) == ImageBatchStats(total=2, current=2, succeeded=0, failed=0, review=2, waiting=2)

    executor.review_resolved = True
    resumed_context = RecordingContext(job)
    ImageBatchHandler(store, executor)(cast(object, resumed_context), job)

    assert store.batch_stats(
        job.id,
        pipeline_fingerprint=PIPELINE_FINGERPRINT,
    ) == ImageBatchStats(total=2, current=2, succeeded=2, failed=0, review=2, waiting=0)
    assert executor.calls[-4:] == [
        ("session/page-001.jpg", "manual_review"),
        ("session/page-001.jpg", "validation"),
        ("session/page-002.jpg", "manual_review"),
        ("session/page-002.jpg", "validation"),
    ]


def test_restart_resumes_after_persisted_file_checkpoint() -> None:
    job = _leased_image_job()
    store = MemoryImageBatchStore()
    store.register(
        job.id,
        checksum="4" * 64,
        pipeline_fingerprint=PIPELINE_FINGERPRINT,
        path="session/page.jpg",
        order_index=0,
    )
    executor = ReviewAwareExecutor()
    crashing_context = RecordingContext(job, crash_after_checkpoint=True)

    with pytest.raises(SimulatedProcessExit):
        ImageBatchHandler(store, executor)(cast(object, crashing_context), job)

    persisted = next(iter(store.executions.values()))
    assert persisted.checkpoint_payload["completedStages"] == ["discovery"]

    executor.review_resolved = True
    ImageBatchHandler(store, executor)(cast(object, RecordingContext(job)), job)

    assert executor.calls[:2] == [
        ("session/page.jpg", "discovery"),
        ("session/page.jpg", "normalization"),
    ]
    assert next(iter(store.executions.values())).status == "completed"


def test_cancellation_stops_after_file_checkpoint_before_next_stage() -> None:
    job = _leased_image_job()
    store = MemoryImageBatchStore()
    _register_two(store, job)
    executor = ReviewAwareExecutor(review_resolved=True)
    context = RecordingContext(job, stop_after_checkpoint=True)

    with pytest.raises(ExecutionStopped, match="cancelled"):
        ImageBatchHandler(store, executor)(cast(object, context), job)

    first = store.executions[file_execution_key("1" * 64, PIPELINE_FINGERPRINT)]
    second = store.executions[file_execution_key("2" * 64, PIPELINE_FINGERPRINT)]
    assert first.checkpoint_payload["completedStages"] == ["discovery"]
    assert second.checkpoint_payload["completedStages"] == []
    assert executor.calls == [("session/page-001.jpg", "discovery")]
