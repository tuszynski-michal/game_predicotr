from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.jobs import JobRepository, JobService
from game_predictor_api.domain.jobs import (
    Job,
    JobConflictError,
    JobError,
    JobStatus,
    JobType,
    acknowledge_job_cancellation,
    complete_job,
    create_job,
    fail_job,
    job_input_key,
    request_job_cancellation,
    start_job,
    update_job_progress,
    wait_for_review,
)


class MemoryJobRepository(JobRepository):
    def __init__(self, game_id: UUID) -> None:
        self.game_id = game_id
        self.items: dict[UUID, Job] = {}

    def game_exists(self, game_id: UUID) -> bool:
        return game_id == self.game_id

    def add_job(self, job: Job) -> Job:
        self.items[job.id] = job
        return job

    def get_job(self, job_id: UUID) -> Job | None:
        return self.items.get(job_id)

    def get_job_for_update(self, job_id: UUID) -> Job | None:
        return self.get_job(job_id)

    def get_job_by_input_key(self, input_key: str) -> Job | None:
        return next(
            (item for item in self.items.values() if item.input_key == input_key),
            None,
        )

    def list_jobs(
        self,
        *,
        status: JobStatus | None,
        job_type: JobType | None,
        game_id: UUID | None,
        limit: int,
    ) -> list[Job]:
        return [
            item
            for item in reversed(tuple(self.items.values()))
            if (status is None or item.status is status)
            and (job_type is None or item.job_type is job_type)
            and (game_id is None or item.game_id == game_id)
        ][:limit]

    def save_job(self, job: Job) -> Job:
        self.items[job.id] = job
        return job


def _job() -> Job:
    return create_job(
        JobType.VALIDATE,
        game_id=uuid4(),
        input_payload={"schema_version": 1, "dataset_version_id": str(uuid4())},
        created_at=datetime(2026, 7, 27, 12, tzinfo=UTC),
    )


def test_input_key_is_canonical_and_includes_type_and_game() -> None:
    game_id = uuid4()
    first = {"schema_version": 1, "alpha": "a", "nested": {"b": 2, "a": 1}}
    second = {"nested": {"a": 1, "b": 2}, "alpha": "a", "schema_version": 1}

    assert job_input_key(JobType.IMPORT, game_id=game_id, input_payload=first) == (
        job_input_key(JobType.IMPORT, game_id=game_id, input_payload=second)
    )
    assert job_input_key(JobType.IMPORT, game_id=game_id, input_payload=first) != (
        job_input_key(JobType.VALIDATE, game_id=game_id, input_payload=first)
    )


def test_processing_progress_review_resume_and_completion_lifecycle() -> None:
    original = _job()
    started = start_job(original, worker_version="worker-v1")
    progressed = update_job_progress(
        started,
        stage="validating",
        current=20,
        total=100,
        success_count=18,
        failure_count=1,
        review_count=1,
    )
    waiting = wait_for_review(progressed)

    assert waiting.status is JobStatus.WAITING_FOR_REVIEW
    assert waiting.stage == "validating"
    with pytest.raises(JobConflictError) as error:
        complete_job(waiting)
    assert error.value.code == "INVALID_JOB_STATUS_TRANSITION"


def test_invalid_transition_and_progress_regression_are_rejected() -> None:
    original = _job()
    with pytest.raises(JobConflictError) as error:
        complete_job(original)
    assert error.value.code == "INVALID_JOB_STATUS_TRANSITION"

    started = start_job(original, worker_version="worker-v1")
    progressed = update_job_progress(
        started,
        stage="scanning",
        current=5,
        total=10,
        success_count=5,
        failure_count=0,
        review_count=0,
    )
    with pytest.raises(JobError) as progress_error:
        update_job_progress(
            progressed,
            stage="scanning",
            current=4,
            total=10,
            success_count=4,
            failure_count=0,
            review_count=0,
        )
    assert progress_error.value.code == "JOB_PROGRESS_REGRESSION"


def test_cancellation_is_immediate_before_start_and_deferred_during_processing() -> None:
    now = datetime(2026, 7, 27, 13, tzinfo=UTC)
    unstarted = request_job_cancellation(_job(), requested_at=now)
    assert unstarted.status is JobStatus.CANCELLED
    assert unstarted.finished_at == now

    processing = start_job(_job(), worker_version="worker-v1")
    requested = request_job_cancellation(processing, requested_at=now)
    assert requested.status is JobStatus.PROCESSING
    assert requested.cancel_requested_at == now

    acknowledged = acknowledge_job_cancellation(
        requested,
        finished_at=now + timedelta(seconds=1),
    )
    assert acknowledged.status is JobStatus.CANCELLED


def test_completed_and_failed_jobs_are_terminal_for_cancel() -> None:
    processing = start_job(_job(), worker_version="worker-v1")
    completed = complete_job(processing)
    failed = fail_job(
        start_job(_job(), worker_version="worker-v1"),
        error_code="VALIDATION_FAILED",
        error_message="Dataset is invalid.",
    )

    for terminal in (completed, failed):
        with pytest.raises(JobConflictError) as error:
            request_job_cancellation(terminal)
        assert error.value.code == "JOB_NOT_CANCELLABLE"


def test_service_rejects_duplicate_input_and_cancels_persisted_job() -> None:
    game_id = uuid4()
    service = JobService(MemoryJobRepository(game_id))
    payload: dict[str, object] = {
        "schema_version": 1,
        "dataset_version_id": str(uuid4()),
    }
    created = service.create_job(
        JobType.VALIDATE,
        game_id=game_id,
        input_payload=payload,
    )

    with pytest.raises(JobConflictError) as error:
        service.create_job(
            JobType.VALIDATE,
            game_id=game_id,
            input_payload=payload,
        )
    assert error.value.code == "JOB_INPUT_ALREADY_EXISTS"
    assert service.cancel_job(created.id).status is JobStatus.CANCELLED
