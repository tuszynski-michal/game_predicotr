"""Handler registry and execution loop for durable jobs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from time import sleep
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.jobs import (
    Job,
    JobConflictError,
    JobStatus,
    JobType,
)

DEFAULT_LEASE_DURATION = timedelta(seconds=60)
DEFAULT_POLL_INTERVAL_SECONDS = 2.0


class JobExecutionResult(StrEnum):
    NO_JOB = "no_job"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING_FOR_REVIEW = "waiting_for_review"
    LEASE_LOST = "lease_lost"


class WorkerJobStore(Protocol):
    def claim_next(
        self,
        *,
        worker_id: str,
        worker_version: str,
        lease_duration: timedelta,
        claimed_at: datetime,
    ) -> Job | None: ...

    def heartbeat(
        self,
        job_id: UUID,
        *,
        lease_token: UUID,
        lease_duration: timedelta,
        heartbeat_at: datetime,
    ) -> Job: ...

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
    ) -> Job: ...

    def complete(
        self,
        job_id: UUID,
        *,
        lease_token: UUID,
        completed_at: datetime,
    ) -> Job: ...

    def fail(
        self,
        job_id: UUID,
        *,
        lease_token: UUID,
        error_code: str,
        error_message: str,
        failed_at: datetime,
    ) -> Job: ...

    def pause_for_review(
        self,
        job_id: UUID,
        *,
        lease_token: UUID,
        paused_at: datetime,
    ) -> Job: ...


class JobHandler(Protocol):
    def __call__(self, context: JobExecutionContext, job: Job) -> None: ...


class _ExecutionStopped(RuntimeError):
    def __init__(self, status: JobStatus) -> None:
        super().__init__(status.value)
        self.status = status


class JobExecutionContext:
    def __init__(
        self,
        store: WorkerJobStore,
        job: Job,
        *,
        lease_duration: timedelta,
        clock: Callable[[], datetime],
    ) -> None:
        if job.lease_token is None:
            raise ValueError("A claimed job must have a lease token.")
        self._store = store
        self._job = job
        self._lease_token = job.lease_token
        self._lease_duration = lease_duration
        self._clock = clock

    @property
    def job(self) -> Job:
        return self._job

    def heartbeat(self) -> None:
        self._job = self._store.heartbeat(
            self._job.id,
            lease_token=self._lease_token,
            lease_duration=self._lease_duration,
            heartbeat_at=self._clock(),
        )

    def checkpoint(
        self,
        *,
        checkpoint_payload: dict[str, object],
        stage: str,
        current: int,
        total: int | None,
        success_count: int,
        failure_count: int,
        review_count: int,
    ) -> None:
        self._job = self._store.checkpoint(
            self._job.id,
            lease_token=self._lease_token,
            lease_duration=self._lease_duration,
            checkpoint_payload=checkpoint_payload,
            stage=stage,
            current=current,
            total=total,
            success_count=success_count,
            failure_count=failure_count,
            review_count=review_count,
            checkpointed_at=self._clock(),
        )
        if self._job.status is JobStatus.CANCELLED:
            raise _ExecutionStopped(JobStatus.CANCELLED)

    def wait_for_review(self) -> None:
        self._job = self._store.pause_for_review(
            self._job.id,
            lease_token=self._lease_token,
            paused_at=self._clock(),
        )
        raise _ExecutionStopped(self._job.status)


class LocalJobWorker:
    def __init__(
        self,
        store: WorkerJobStore,
        handlers: Mapping[JobType, JobHandler],
        *,
        worker_id: str,
        worker_version: str,
        lease_duration: timedelta = DEFAULT_LEASE_DURATION,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._handlers = dict(handlers)
        self._worker_id = worker_id
        self._worker_version = worker_version
        self._lease_duration = lease_duration
        self._clock = clock or (lambda: datetime.now(UTC))

    def run_once(self) -> JobExecutionResult:
        claimed = self._store.claim_next(
            worker_id=self._worker_id,
            worker_version=self._worker_version,
            lease_duration=self._lease_duration,
            claimed_at=self._clock(),
        )
        if claimed is None:
            return JobExecutionResult.NO_JOB
        if claimed.lease_token is None:
            raise RuntimeError("Claimed job is missing its lease token.")

        handler = self._handlers.get(claimed.job_type)
        if handler is None:
            failed = self._store.fail(
                claimed.id,
                lease_token=claimed.lease_token,
                error_code="JOB_HANDLER_NOT_REGISTERED",
                error_message=(
                    f"No local handler is registered for {claimed.job_type.value}."
                ),
                failed_at=self._clock(),
            )
            return _result_for_status(failed.status)

        context = JobExecutionContext(
            self._store,
            claimed,
            lease_duration=self._lease_duration,
            clock=self._clock,
        )
        try:
            handler(context, claimed)
            completed = self._store.complete(
                claimed.id,
                lease_token=claimed.lease_token,
                completed_at=self._clock(),
            )
            return _result_for_status(completed.status)
        except _ExecutionStopped as stopped:
            return _result_for_status(stopped.status)
        except JobConflictError as error:
            if error.code == "JOB_LEASE_LOST":
                return JobExecutionResult.LEASE_LOST
            return self._fail_handler(claimed, error)
        except Exception as error:
            return self._fail_handler(claimed, error)

    def run_forever(
        self,
        *,
        should_stop: Callable[[], bool],
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive.")
        while not should_stop():
            result = self.run_once()
            if result is JobExecutionResult.NO_JOB:
                sleep(poll_interval_seconds)

    def _fail_handler(
        self,
        claimed: Job,
        error: Exception,
    ) -> JobExecutionResult:
        if claimed.lease_token is None:
            return JobExecutionResult.LEASE_LOST
        try:
            failed = self._store.fail(
                claimed.id,
                lease_token=claimed.lease_token,
                error_code="JOB_EXECUTION_FAILED",
                error_message=f"Handler failed with {type(error).__name__}.",
                failed_at=self._clock(),
            )
        except JobConflictError as lease_error:
            if lease_error.code == "JOB_LEASE_LOST":
                return JobExecutionResult.LEASE_LOST
            raise
        return _result_for_status(failed.status)


def _result_for_status(status: JobStatus) -> JobExecutionResult:
    mapping = {
        JobStatus.COMPLETED: JobExecutionResult.COMPLETED,
        JobStatus.FAILED: JobExecutionResult.FAILED,
        JobStatus.CANCELLED: JobExecutionResult.CANCELLED,
        JobStatus.WAITING_FOR_REVIEW: JobExecutionResult.WAITING_FOR_REVIEW,
    }
    result = mapping.get(status)
    if result is None:
        raise RuntimeError(f"Worker stopped in unexpected status {status.value}.")
    return result
