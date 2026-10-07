from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.jobs import JobType, create_job, defer_job_for_storage, start_job
from game_predictor_api.domain.storage_retention import StorageRetentionPolicy
from game_predictor_worker import cli
from game_predictor_worker.images.orchestration import ImageBatchHandler
from game_predictor_worker.images.pipeline_contract import PIPELINE_STAGES
from game_predictor_worker.images.production_workflow import ProductionImageImportWorkflow
from game_predictor_worker.jobs.runtime import (
    JobExecutionContext,
    JobExecutionResult,
    LocalJobWorker,
    WorkerJobStore,
)
from sqlalchemy.orm import Session, sessionmaker
from test_image_batch_orchestration import (
    NOW,
    PIPELINE_FINGERPRINT,
    ExecutionStopped,
    MemoryImageBatchStore,
    RecordingContext,
    ReviewAwareExecutor,
    _leased_image_job,
)
from test_worker_cli import FakeEngine, FakeWorker, _replace_dependencies

GIB = 1024**3


def _workflow(tmp_path: Path, reserve: int | None = None) -> ProductionImageImportWorkflow:
    if reserve is None:
        return ProductionImageImportWorkflow(
            sessionmaker[Session](), tmp_path, repository_root=tmp_path
        )
    return ProductionImageImportWorkflow(
        sessionmaker[Session](), tmp_path, repository_root=tmp_path, hard_reserve_bytes=reserve
    )


def _disk_free(monkeypatch: pytest.MonkeyPatch, free_bytes: int) -> None:
    monkeypatch.setattr(
        "game_predictor_worker.images.production_workflow.shutil.disk_usage",
        lambda _path: SimpleNamespace(
            total=100 * GIB, used=100 * GIB - free_bytes, free=free_bytes
        ),
    )


@pytest.mark.parametrize("stage", ["image_pipeline", "waiting_for_storage"])
@pytest.mark.parametrize(
    ("free_bytes", "allowed"),
    [
        (5 * GIB - 1, False),
        (5 * GIB, True),
        (5 * GIB + 1, True),
        (50 * GIB, True),
        (80 * GIB, True),
    ],
)
def test_default_import_capacity_has_the_same_five_gib_boundary_in_every_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    free_bytes: int,
    allowed: bool,
) -> None:
    workflow = _workflow(tmp_path)
    job = replace(
        create_job(JobType.IMPORT, game_id=None, input_payload={"schema_version": 1}), stage=stage
    )
    _disk_free(monkeypatch, free_bytes)

    assert workflow._hard_reserve_bytes == StorageRetentionPolicy().hard_reserve_bytes == 5 * GIB
    assert workflow._has_pipeline_capacity(job) is allowed
    # Managed-original copying and pipeline execution share the same guard.
    before_original = workflow._source_handler._before_original
    assert before_original is not None
    assert before_original(job) is allowed


@pytest.mark.parametrize("stage", ["image_pipeline", "waiting_for_storage"])
@pytest.mark.parametrize(("free_bytes", "allowed"), [(7 * GIB - 1, False), (7 * GIB, True)])
def test_configured_reserve_protects_normal_and_paused_imports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str, free_bytes: int, allowed: bool
) -> None:
    workflow = _workflow(tmp_path, 7 * GIB)
    job = replace(
        create_job(JobType.IMPORT, game_id=None, input_payload={"schema_version": 1}), stage=stage
    )
    _disk_free(monkeypatch, free_bytes)

    assert workflow._has_pipeline_capacity(job) is allowed


@pytest.mark.parametrize("reserve", [-1, 0])
def test_invalid_worker_reserve_is_rejected_before_creating_storage(
    tmp_path: Path, reserve: int
) -> None:
    with pytest.raises(ValueError, match="hard_reserve_bytes must be positive"):
        _workflow(tmp_path / "not-created", reserve)
    assert not (tmp_path / "not-created").exists()


def test_fresh_workflow_resumes_storage_checkpoint_without_repeating_settled_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _leased_image_job()
    store = MemoryImageBatchStore()
    first = store.register(
        job.id,
        checksum="1" * 64,
        pipeline_fingerprint=PIPELINE_FINGERPRINT,
        path="session/page-001.jpg",
        order_index=0,
    )
    executor = ReviewAwareExecutor()
    with pytest.raises(ExecutionStopped, match="waiting_for_review"):
        ImageBatchHandler(store, executor)(cast(JobExecutionContext, RecordingContext(job)), job)
    settled = dict(store.executions[first.file_execution_key].checkpoint_payload)
    store.register(
        job.id,
        checksum="2" * 64,
        pipeline_fingerprint=PIPELINE_FINGERPRINT,
        path="session/page-002.jpg",
        order_index=1,
    )
    calls_before_wait = list(executor.calls)
    saves_before_wait = store.save_file_checkpoint_calls

    class StorageContext(RecordingContext):
        def wait_for_storage(self, *, checkpoint_payload: dict[str, object]) -> None:
            self.job = defer_job_for_storage(
                self.job,
                lease_token=self.lease_token,
                checkpoint_payload=checkpoint_payload,
                deferred_at=NOW,
            )
            raise ExecutionStopped("waiting_for_storage")

    paused_context = StorageContext(job)
    old_workflow = _workflow(tmp_path)
    _disk_free(monkeypatch, 5 * GIB - 1)
    with pytest.raises(ExecutionStopped, match="waiting_for_storage"):
        ImageBatchHandler(
            store, executor, before_candidate=lambda: old_workflow._has_pipeline_capacity(job)
        )(cast(JobExecutionContext, paused_context), job)
    assert executor.calls == calls_before_wait
    assert store.save_file_checkpoint_calls == saves_before_wait
    saved_job = paused_context.job
    assert saved_job.stage == "waiting_for_storage"
    assert saved_job.checkpoint_payload is not None
    assert saved_job.checkpoint_payload["progress_current"] == 1

    resumed_job = start_job(
        saved_job,
        worker_id="new-worker",
        worker_version="worker-v10-general",
        lease_token=uuid4(),
        lease_expires_at=NOW + timedelta(seconds=60),
        started_at=NOW,
    )
    fresh_workflow = _workflow(tmp_path)
    _disk_free(monkeypatch, 5 * GIB)
    with pytest.raises(ExecutionStopped, match="waiting_for_review"):
        ImageBatchHandler(
            store,
            executor,
            before_candidate=lambda: fresh_workflow._has_pipeline_capacity(resumed_job),
        )(cast(JobExecutionContext, RecordingContext(resumed_job)), resumed_job)

    assert resumed_job.id == job.id
    assert resumed_job.checkpoint_payload == saved_job.checkpoint_payload
    assert len(store.executions) == 2
    assert store.executions[first.file_execution_key].checkpoint_payload == settled
    assert executor.calls[len(calls_before_wait) : len(calls_before_wait) + 7] == [
        ("session/page-002.jpg", stage) for stage in PIPELINE_STAGES[:7]
    ]
    assert all(
        path != "session/page-001.jpg" or stage == "manual_review"
        for path, stage in executor.calls[len(calls_before_wait) :]
    )
    assert executor.rehydrated == []
    assert store.batch_stats(job.id, pipeline_fingerprint=PIPELINE_FINGERPRINT).current == 2


@pytest.mark.parametrize("reserve_gib", [None, 5, 7])
def test_cli_composes_only_the_hard_reserve_not_the_gc_target(
    monkeypatch: pytest.MonkeyPatch, reserve_gib: int | None
) -> None:
    FakeWorker.instances.clear()
    _replace_dependencies(monkeypatch, FakeEngine())
    settings = cast(SimpleNamespace, ApiSettings.from_environment())
    settings.grid_shadow_enabled = False
    if reserve_gib is not None:
        settings.storage_hard_reserve_gib = reserve_gib
    settings.storage_target_gib = 80
    options: dict[str, object] = {}

    def capture_workflow(
        _session_factory: object, _artifact_root: Path, **kwargs: object
    ) -> object:
        options.update(kwargs)
        return object()

    monkeypatch.setattr(ApiSettings, "from_environment", lambda: settings)
    monkeypatch.setattr(cli, "ProductionImageImportWorkflow", capture_workflow)

    assert cli.main(["--worker-id", "storage-composition-test"]) == 0
    assert options["hard_reserve_bytes"] == (reserve_gib if reserve_gib is not None else 5) * GIB
    assert "resume_target_bytes" not in options


@pytest.mark.parametrize(
    ("result", "expected_delays"),
    [
        (JobExecutionResult.WAITING_FOR_STORAGE, [0.25, 0.25]),
        (JobExecutionResult.NO_JOB, [0.25, 0.25]),
        (JobExecutionResult.COMPLETED, []),
        (JobExecutionResult.WAITING_FOR_REVIEW, []),
    ],
)
def test_storage_wait_uses_bounded_polling_instead_of_a_tight_reclaim_loop(
    monkeypatch: pytest.MonkeyPatch, result: JobExecutionResult, expected_delays: list[float]
) -> None:
    worker = LocalJobWorker(
        cast(WorkerJobStore, object()), {}, worker_id="test", worker_version="test"
    )
    calls = 0
    delays: list[float] = []

    def run_once() -> JobExecutionResult:
        nonlocal calls
        calls += 1
        return result

    monkeypatch.setattr(worker, "run_once", run_once)
    monkeypatch.setattr("game_predictor_worker.jobs.runtime.sleep", delays.append)
    worker.run_forever(should_stop=lambda: calls >= 2, poll_interval_seconds=0.25)

    assert calls == 2
    assert delays == expected_delays
