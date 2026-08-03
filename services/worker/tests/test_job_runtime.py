from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from game_predictor_api.domain.jobs import (
    Job,
    JobError,
    JobStatus,
    JobType,
    acknowledge_job_cancellation,
    checkpoint_job,
    complete_job,
    create_job,
    fail_job,
    recover_expired_job,
    renew_job_lease,
    request_job_cancellation,
    start_job,
    wait_for_review,
)
from game_predictor_worker.jobs.runtime import (
    JobExecutionContext,
    JobExecutionResult,
    JobHandler,
    JobHandlerError,
    LocalJobWorker,
)


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 27, 16, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


class MemoryWorkerJobStore:
    def __init__(self, jobs: list[Job]) -> None:
        self.jobs = {job.id: job for job in jobs}

    def claim_next(
        self,
        *,
        worker_id: str,
        worker_version: str,
        lease_duration: timedelta,
        claimed_at: datetime,
    ) -> Job | None:
        for job in tuple(self.jobs.values()):
            if (
                job.status is JobStatus.PROCESSING
                and job.lease_expires_at is not None
                and job.lease_expires_at <= claimed_at
            ):
                self.jobs[job.id] = recover_expired_job(
                    job,
                    recovered_at=claimed_at,
                )
        if any(
            job.status is JobStatus.PROCESSING for job in self.jobs.values()
        ):
            return None
        candidates = sorted(
            (
                job
                for job in self.jobs.values()
                if job.status is JobStatus.CREATED
            ),
            key=lambda job: (job.created_at, job.id),
        )
        if not candidates:
            return None
        claimed = start_job(
            candidates[0],
            worker_id=worker_id,
            worker_version=worker_version,
            lease_token=uuid4(),
            lease_expires_at=claimed_at + lease_duration,
            started_at=claimed_at,
        )
        self.jobs[claimed.id] = claimed
        return claimed

    def heartbeat(
        self,
        job_id: UUID,
        *,
        lease_token: UUID,
        lease_duration: timedelta,
        heartbeat_at: datetime,
    ) -> Job:
        updated = renew_job_lease(
            self.jobs[job_id],
            lease_token=lease_token,
            lease_expires_at=heartbeat_at + lease_duration,
            heartbeat_at=heartbeat_at,
        )
        self.jobs[job_id] = updated
        return updated

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
    ) -> Job:
        renewed = renew_job_lease(
            self.jobs[job_id],
            lease_token=lease_token,
            lease_expires_at=checkpointed_at + lease_duration,
            heartbeat_at=checkpointed_at,
        )
        updated = checkpoint_job(
            renewed,
            lease_token=lease_token,
            checkpoint_payload=checkpoint_payload,
            stage=stage,
            current=current,
            total=total,
            success_count=success_count,
            failure_count=failure_count,
            review_count=review_count,
            updated_at=checkpointed_at,
        )
        if updated.cancel_requested_at is not None:
            updated = acknowledge_job_cancellation(
                updated,
                lease_token=lease_token,
                finished_at=checkpointed_at,
            )
        self.jobs[job_id] = updated
        return updated

    def complete(
        self,
        job_id: UUID,
        *,
        lease_token: UUID,
        completed_at: datetime,
    ) -> Job:
        job = self.jobs[job_id]
        updated = (
            acknowledge_job_cancellation(
                job,
                lease_token=lease_token,
                finished_at=completed_at,
            )
            if job.cancel_requested_at is not None
            else complete_job(
                job,
                lease_token=lease_token,
                finished_at=completed_at,
            )
        )
        self.jobs[job_id] = updated
        return updated

    def fail(
        self,
        job_id: UUID,
        *,
        lease_token: UUID,
        error_code: str,
        error_message: str,
        failed_at: datetime,
    ) -> Job:
        job = self.jobs[job_id]
        updated = (
            acknowledge_job_cancellation(
                job,
                lease_token=lease_token,
                finished_at=failed_at,
            )
            if job.cancel_requested_at is not None
            else fail_job(
                job,
                lease_token=lease_token,
                error_code=error_code,
                error_message=error_message,
                finished_at=failed_at,
            )
        )
        self.jobs[job_id] = updated
        return updated

    def pause_for_review(
        self,
        job_id: UUID,
        *,
        lease_token: UUID,
        paused_at: datetime,
    ) -> Job:
        updated = wait_for_review(
            self.jobs[job_id],
            lease_token=lease_token,
            updated_at=paused_at,
        )
        self.jobs[job_id] = updated
        return updated


def _job(clock: MutableClock, *, offset_seconds: int = 0) -> Job:
    return create_job(
        JobType.VALIDATE,
        game_id=uuid4(),
        input_payload={
            "schema_version": 1,
            "dataset_version_id": str(uuid4()),
        },
        created_at=clock.now + timedelta(seconds=offset_seconds),
    )


def _worker(
    store: MemoryWorkerJobStore,
    clock: MutableClock,
    handler: JobHandler,
) -> LocalJobWorker:
    return LocalJobWorker(
        store,
        {JobType.VALIDATE: handler},
        worker_id="worker-test",
        worker_version="worker-v1",
        lease_duration=timedelta(seconds=60),
        clock=clock,
    )


def test_worker_claims_oldest_checkpoints_and_completes() -> None:
    clock = MutableClock()
    first = _job(clock)
    second = _job(clock, offset_seconds=1)
    store = MemoryWorkerJobStore([second, first])

    def handler(context: JobExecutionContext, _job: Job) -> None:
        clock.advance(10)
        context.checkpoint(
            checkpoint_payload={"schema_version": 1, "cursor": 100},
            stage="validating",
            current=100,
            total=1000,
            success_count=99,
            failure_count=1,
            review_count=0,
        )

    result = _worker(store, clock, handler).run_once()

    assert result is JobExecutionResult.COMPLETED
    assert store.jobs[first.id].status is JobStatus.COMPLETED
    assert store.jobs[first.id].checkpoint_payload == {
        "schema_version": 1,
        "cursor": 100,
    }
    assert store.jobs[first.id].execution_slot is None
    assert store.jobs[second.id].status is JobStatus.CREATED


def test_cancel_request_stops_handler_at_safe_checkpoint() -> None:
    clock = MutableClock()
    job = _job(clock)
    store = MemoryWorkerJobStore([job])
    reached_after_checkpoint = False

    def handler(context: JobExecutionContext, _job: Job) -> None:
        nonlocal reached_after_checkpoint
        store.jobs[job.id] = request_job_cancellation(
            store.jobs[job.id],
            requested_at=clock.now,
        )
        context.checkpoint(
            checkpoint_payload={"schema_version": 1, "cursor": 10},
            stage="validating",
            current=10,
            total=100,
            success_count=10,
            failure_count=0,
            review_count=0,
        )
        reached_after_checkpoint = True

    result = _worker(store, clock, handler).run_once()

    assert result is JobExecutionResult.CANCELLED
    assert reached_after_checkpoint is False
    assert store.jobs[job.id].status is JobStatus.CANCELLED
    assert store.jobs[job.id].progress_current == 10


def test_waiting_for_review_releases_the_single_execution_slot() -> None:
    clock = MutableClock()
    waiting_job = _job(clock)
    next_job = _job(clock, offset_seconds=1)
    store = MemoryWorkerJobStore([waiting_job, next_job])

    def pause_handler(context: JobExecutionContext, _job: Job) -> None:
        context.wait_for_review()

    assert (
        _worker(store, clock, pause_handler).run_once()
        is JobExecutionResult.WAITING_FOR_REVIEW
    )
    paused = store.jobs[waiting_job.id]
    assert paused.status is JobStatus.WAITING_FOR_REVIEW
    assert paused.execution_slot is None
    assert paused.lease_token is None

    processed: list[UUID] = []

    def next_handler(_context: JobExecutionContext, job: Job) -> None:
        processed.append(job.id)

    assert _worker(store, clock, next_handler).run_once() is JobExecutionResult.COMPLETED
    assert processed == [next_job.id]


def test_handler_failure_and_missing_registration_release_slot() -> None:
    clock = MutableClock()
    failed_job = _job(clock)
    store = MemoryWorkerJobStore([failed_job])

    def failing_handler(_context: JobExecutionContext, _job: Job) -> None:
        raise RuntimeError("sensitive details")

    result = _worker(store, clock, failing_handler).run_once()

    assert result is JobExecutionResult.FAILED
    assert store.jobs[failed_job.id].error_code == "JOB_EXECUTION_FAILED"
    assert store.jobs[failed_job.id].error_message == (
        "Handler failed with RuntimeError."
    )
    assert store.jobs[failed_job.id].execution_slot is None

    missing_job = _job(clock, offset_seconds=1)
    missing_store = MemoryWorkerJobStore([missing_job])
    missing_worker = LocalJobWorker(
        missing_store,
        {},
        worker_id="worker-test",
        worker_version="worker-v1",
        clock=clock,
    )
    assert missing_worker.run_once() is JobExecutionResult.FAILED
    assert (
        missing_store.jobs[missing_job.id].error_code
        == "JOB_HANDLER_NOT_REGISTERED"
    )


def test_worker_preserves_operator_safe_handler_error() -> None:
    clock = MutableClock()
    job = _job(clock)
    store = MemoryWorkerJobStore([job])

    def fail_safely(_context: JobExecutionContext, _job: Job) -> None:
        raise JobHandlerError(
            "PAYOUT_SOURCE_NOT_FOUND",
            "The payout source does not exist.",
        )

    assert (
        _worker(store, clock, fail_safely).run_once()
        is JobExecutionResult.FAILED
    )
    failed = store.jobs[job.id]
    assert failed.error_code == "PAYOUT_SOURCE_NOT_FOUND"
    assert failed.error_message == "The payout source does not exist."


def test_worker_preserves_operator_safe_domain_job_error() -> None:
    clock = MutableClock()
    job = _job(clock)
    store = MemoryWorkerJobStore([job])

    def fail_domain_validation(_context: JobExecutionContext, _job: Job) -> None:
        raise JobError(
            "UNSUPPORTED_JOB_CHECKPOINT_VERSION",
            "checkpointPayload must use schemaVersion 1.",
        )

    assert (
        _worker(store, clock, fail_domain_validation).run_once()
        is JobExecutionResult.FAILED
    )
    failed = store.jobs[job.id]
    assert failed.error_code == "UNSUPPORTED_JOB_CHECKPOINT_VERSION"
    assert failed.error_message == "checkpointPayload must use schemaVersion 1."


def test_expired_worker_is_fenced_and_same_job_is_resumed() -> None:
    clock = MutableClock()
    job = _job(clock)
    store = MemoryWorkerJobStore([job])

    def lease_losing_handler(
        context: JobExecutionContext,
        _job: Job,
    ) -> None:
        clock.advance(61)
        context.heartbeat()

    first_result = _worker(store, clock, lease_losing_handler).run_once()
    assert first_result is JobExecutionResult.LEASE_LOST

    resumed_attempts: list[int] = []

    def resumed_handler(
        _context: JobExecutionContext,
        resumed_job: Job,
    ) -> None:
        resumed_attempts.append(resumed_job.attempt_count)

    second_result = _worker(store, clock, resumed_handler).run_once()

    assert second_result is JobExecutionResult.COMPLETED
    assert resumed_attempts == [2]
    assert store.jobs[job.id].status is JobStatus.COMPLETED
