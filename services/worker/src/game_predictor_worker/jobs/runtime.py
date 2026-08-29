"""Handler registry and execution loop for durable jobs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from threading import Event, Thread
from time import sleep
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.jobs import (
    Job,
    JobConflictError,
    JobError,
    JobExecutionSlot,
    JobStatus,
    JobType,
)

DEFAULT_LEASE_DURATION = timedelta(seconds=60)
DEFAULT_POLL_INTERVAL_SECONDS = 2.0
MAX_LEASE_KEEPALIVE_INTERVAL_SECONDS = 15.0
GENERAL_JOB_TYPES = frozenset(JobType) - {JobType.IMAGE_SELECTION}


class JobExecutionResult(StrEnum):
    NO_JOB = "no_job"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING_FOR_REVIEW = "waiting_for_review"
    LEASE_LOST = "lease_lost"
    WAITING_FOR_STORAGE = "waiting_for_storage"


class JobHandlerError(RuntimeError):
    """Stable, operator-safe workflow failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        normalized_code = code.strip()
        normalized_message = message.strip()
        if not normalized_code or not normalized_message:
            raise ValueError("A job handler error requires code and message.")
        self.code = normalized_code
        self.message = normalized_message


class WorkerJobStore(Protocol):
    def claim_next(
        self,
        *,
        worker_id: str,
        worker_version: str,
        lease_duration: timedelta,
        claimed_at: datetime,
        allowed_job_types: frozenset[JobType] = GENERAL_JOB_TYPES,
        execution_slot: JobExecutionSlot = JobExecutionSlot.GENERAL,
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

    def defer_for_storage(
        self,
        job_id: UUID,
        *,
        lease_token: UUID,
        checkpoint_payload: dict[str, object],
        deferred_at: datetime,
    ) -> Job: ...


class JobHandler(Protocol):
    def __call__(self, context: JobExecutionContext, job: Job) -> None: ...


class _ExecutionStopped(RuntimeError):
    def __init__(self, status: JobStatus, *, waiting_for_storage: bool = False) -> None:
        super().__init__(status.value)
        self.status = status
        self.waiting_for_storage = waiting_for_storage


class _LeaseKeepalive:
    """Renew one claimed job independently from handler checkpoint cadence."""

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
        lease_seconds = lease_duration.total_seconds()
        if lease_seconds <= 0:
            raise ValueError("lease_duration must be positive.")
        self._store = store
        self._job_id = job.id
        self._lease_token = job.lease_token
        self._lease_duration = lease_duration
        self._clock = clock
        self._interval_seconds = min(
            MAX_LEASE_KEEPALIVE_INTERVAL_SECONDS,
            max(0.05, lease_seconds / 3.0),
        )
        self._stop = Event()
        self._error: BaseException | None = None
        self._thread = Thread(
            target=self._run,
            name=f"job-lease-keepalive-{job.id}",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> BaseException | None:
        self._stop.set()
        self._thread.join(timeout=min(16.0, self._interval_seconds + 1.0))
        if self._thread.is_alive():
            return RuntimeError("The job lease keepalive did not stop in time.")
        return self._error

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                self._store.heartbeat(
                    self._job_id,
                    lease_token=self._lease_token,
                    lease_duration=self._lease_duration,
                    heartbeat_at=self._clock(),
                )
            except BaseException as error:
                self._error = error
                self._stop.set()
                return


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

    @property
    def lease_token(self) -> UUID:
        """Return the fencing token for same-transaction handler writes."""

        return self._lease_token

    def now(self) -> datetime:
        """Return the injected worker clock for deterministic handler writes."""

        return self._clock()

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

    def wait_for_storage(self, *, checkpoint_payload: dict[str, object]) -> None:
        self._job = self._store.defer_for_storage(
            self._job.id,
            lease_token=self._lease_token,
            checkpoint_payload=checkpoint_payload,
            deferred_at=self._clock(),
        )
        raise _ExecutionStopped(self._job.status, waiting_for_storage=True)


class LocalJobWorker:
    def __init__(
        self,
        store: WorkerJobStore,
        handlers: Mapping[JobType, JobHandler],
        *,
        worker_id: str,
        worker_version: str,
        execution_slot: JobExecutionSlot = JobExecutionSlot.GENERAL,
        lease_duration: timedelta = DEFAULT_LEASE_DURATION,
        clock: Callable[[], datetime] | None = None,
        auxiliary_work: Callable[[], object] | None = None,
    ) -> None:
        self._store = store
        self._handlers = dict(handlers)
        self._worker_id = worker_id
        self._worker_version = worker_version
        self._execution_slot = execution_slot
        self._lease_duration = lease_duration
        self._clock = clock or (lambda: datetime.now(UTC))
        self._auxiliary_work = auxiliary_work

    def run_once(self) -> JobExecutionResult:
        if self._auxiliary_work is not None:
            self._auxiliary_work()
        claimed = self._store.claim_next(
            worker_id=self._worker_id,
            worker_version=self._worker_version,
            lease_duration=self._lease_duration,
            claimed_at=self._clock(),
            allowed_job_types=frozenset(self._handlers),
            execution_slot=self._execution_slot,
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
                error_message=(f"No local handler is registered for {claimed.job_type.value}."),
                failed_at=self._clock(),
            )
            return _result_for_status(failed.status)

        context = JobExecutionContext(
            self._store,
            claimed,
            lease_duration=self._lease_duration,
            clock=self._clock,
        )
        keepalive = _LeaseKeepalive(
            self._store,
            claimed,
            lease_duration=self._lease_duration,
            clock=self._clock,
        )
        keepalive.start()
        try:
            try:
                handler(context, claimed)
            finally:
                keepalive_error = keepalive.stop()
            if keepalive_error is not None:
                raise keepalive_error
            completed = self._store.complete(
                claimed.id,
                lease_token=claimed.lease_token,
                completed_at=self._clock(),
            )
            return _result_for_status(completed.status)
        except _ExecutionStopped as stopped:
            if stopped.waiting_for_storage:
                return JobExecutionResult.WAITING_FOR_STORAGE
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
            code, message = (
                (error.code, error.message)
                if isinstance(error, JobHandlerError | JobError)
                else (
                    "JOB_EXECUTION_FAILED",
                    f"Handler failed with {type(error).__name__}.",
                )
            )
            failed = self._store.fail(
                claimed.id,
                lease_token=claimed.lease_token,
                error_code=code,
                error_message=message,
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
