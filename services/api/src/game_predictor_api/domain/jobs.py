"""Framework-independent job lifecycle and progress rules."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


class JobType(StrEnum):
    IMPORT = "import"
    VALIDATE = "validate"
    PAYOUT = "payout"
    SNAPSHOT = "snapshot"
    ANDROID_BUILD = "android_build"


class JobStatus(StrEnum):
    CREATED = "created"
    PROCESSING = "processing"
    WAITING_FOR_REVIEW = "waiting_for_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class JobNotFoundError(JobError):
    """Requested job or referenced game does not exist."""


class JobConflictError(JobError):
    """The requested job operation conflicts with its lifecycle."""


@dataclass(frozen=True, slots=True)
class Job:
    id: UUID
    job_type: JobType
    game_id: UUID | None
    status: JobStatus
    input_payload: dict[str, object]
    input_key: str
    stage: str | None
    progress_current: int
    progress_total: int | None
    success_count: int
    failure_count: int
    review_count: int
    error_code: str | None
    error_message: str | None
    worker_version: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    cancel_requested_at: datetime | None


def create_job(
    job_type: JobType,
    *,
    game_id: UUID | None,
    input_payload: dict[str, object],
    created_at: datetime | None = None,
) -> Job:
    schema_version = input_payload.get("schema_version")
    if schema_version != 1:
        raise JobError(
            "UNSUPPORTED_JOB_PAYLOAD_VERSION",
            "Job inputPayload must use schemaVersion 1.",
            details={"schemaVersion": schema_version},
        )
    now = created_at or datetime.now(UTC)
    payload = dict(input_payload)
    return Job(
        id=uuid4(),
        job_type=job_type,
        game_id=game_id,
        status=JobStatus.CREATED,
        input_payload=payload,
        input_key=job_input_key(job_type, game_id=game_id, input_payload=payload),
        stage=None,
        progress_current=0,
        progress_total=None,
        success_count=0,
        failure_count=0,
        review_count=0,
        error_code=None,
        error_message=None,
        worker_version=None,
        created_at=now,
        updated_at=now,
        started_at=None,
        finished_at=None,
        cancel_requested_at=None,
    )


def job_input_key(
    job_type: JobType,
    *,
    game_id: UUID | None,
    input_payload: dict[str, object],
) -> str:
    canonical = json.dumps(
        {
            "gameId": None if game_id is None else str(game_id),
            "inputPayload": input_payload,
            "jobType": job_type.value,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def start_job(
    job: Job,
    *,
    worker_version: str,
    started_at: datetime | None = None,
) -> Job:
    if job.status is not JobStatus.CREATED:
        _raise_invalid_transition(job, JobStatus.PROCESSING)
    normalized_version = worker_version.strip()
    if not normalized_version:
        raise JobError(
            "INVALID_WORKER_VERSION",
            "workerVersion must not be blank.",
        )
    now = started_at or datetime.now(UTC)
    return replace(
        job,
        status=JobStatus.PROCESSING,
        worker_version=normalized_version,
        started_at=job.started_at or now,
        updated_at=now,
        finished_at=None,
        error_code=None,
        error_message=None,
    )


def update_job_progress(
    job: Job,
    *,
    stage: str,
    current: int,
    total: int | None,
    success_count: int,
    failure_count: int,
    review_count: int,
    updated_at: datetime | None = None,
) -> Job:
    if job.status is not JobStatus.PROCESSING:
        raise JobConflictError(
            "JOB_NOT_PROCESSING",
            "Progress can only be updated for a processing job.",
            details={"jobId": str(job.id), "status": job.status.value},
        )
    normalized_stage = stage.strip()
    if not normalized_stage:
        raise JobError("INVALID_JOB_STAGE", "stage must not be blank.")
    values = {
        "current": current,
        "successCount": success_count,
        "failureCount": failure_count,
        "reviewCount": review_count,
    }
    if any(value < 0 for value in values.values()) or (total is not None and total < 0):
        raise JobError(
            "INVALID_JOB_PROGRESS",
            "Progress counters must be non-negative.",
        )
    if total is not None and current > total:
        raise JobError(
            "INVALID_JOB_PROGRESS",
            "progress.current cannot exceed progress.total.",
        )
    previous = (
        job.progress_current,
        job.success_count,
        job.failure_count,
        job.review_count,
    )
    candidate = (current, success_count, failure_count, review_count)
    if any(new < old for new, old in zip(candidate, previous, strict=True)):
        raise JobError(
            "JOB_PROGRESS_REGRESSION",
            "Progress counters cannot decrease.",
        )
    if (
        job.progress_total is not None
        and total is not None
        and total < job.progress_total
    ):
        raise JobError(
            "JOB_PROGRESS_REGRESSION",
            "progress.total cannot decrease.",
        )
    return replace(
        job,
        stage=normalized_stage,
        progress_current=current,
        progress_total=total,
        success_count=success_count,
        failure_count=failure_count,
        review_count=review_count,
        updated_at=updated_at or datetime.now(UTC),
    )


def wait_for_review(
    job: Job,
    *,
    updated_at: datetime | None = None,
) -> Job:
    if job.status is not JobStatus.PROCESSING:
        _raise_invalid_transition(job, JobStatus.WAITING_FOR_REVIEW)
    now = updated_at or datetime.now(UTC)
    return replace(job, status=JobStatus.WAITING_FOR_REVIEW, updated_at=now)


def requeue_job(
    job: Job,
    *,
    updated_at: datetime | None = None,
) -> Job:
    if job.status not in {JobStatus.WAITING_FOR_REVIEW, JobStatus.FAILED}:
        _raise_invalid_transition(job, JobStatus.CREATED)
    now = updated_at or datetime.now(UTC)
    return replace(
        job,
        status=JobStatus.CREATED,
        updated_at=now,
        finished_at=None,
        cancel_requested_at=None,
        error_code=None,
        error_message=None,
    )


def complete_job(
    job: Job,
    *,
    finished_at: datetime | None = None,
) -> Job:
    if job.status is not JobStatus.PROCESSING:
        _raise_invalid_transition(job, JobStatus.COMPLETED)
    now = finished_at or datetime.now(UTC)
    return replace(
        job,
        status=JobStatus.COMPLETED,
        updated_at=now,
        finished_at=now,
        error_code=None,
        error_message=None,
    )


def fail_job(
    job: Job,
    *,
    error_code: str,
    error_message: str,
    finished_at: datetime | None = None,
) -> Job:
    if job.status is not JobStatus.PROCESSING:
        _raise_invalid_transition(job, JobStatus.FAILED)
    code = error_code.strip()
    message = error_message.strip()
    if not code or not message:
        raise JobError(
            "INVALID_JOB_ERROR",
            "A failed job requires a non-empty error code and message.",
        )
    now = finished_at or datetime.now(UTC)
    return replace(
        job,
        status=JobStatus.FAILED,
        updated_at=now,
        finished_at=now,
        error_code=code,
        error_message=message,
    )


def request_job_cancellation(
    job: Job,
    *,
    requested_at: datetime | None = None,
) -> Job:
    if job.status is JobStatus.CANCELLED:
        return job
    if job.status in {JobStatus.COMPLETED, JobStatus.FAILED}:
        raise JobConflictError(
            "JOB_NOT_CANCELLABLE",
            "A terminal job cannot be cancelled.",
            details={"jobId": str(job.id), "status": job.status.value},
        )
    if job.cancel_requested_at is not None:
        return job
    now = requested_at or datetime.now(UTC)
    if job.status in {JobStatus.CREATED, JobStatus.WAITING_FOR_REVIEW}:
        return replace(
            job,
            status=JobStatus.CANCELLED,
            cancel_requested_at=now,
            finished_at=now,
            updated_at=now,
        )
    return replace(job, cancel_requested_at=now, updated_at=now)


def acknowledge_job_cancellation(
    job: Job,
    *,
    finished_at: datetime | None = None,
) -> Job:
    if job.status is not JobStatus.PROCESSING or job.cancel_requested_at is None:
        _raise_invalid_transition(job, JobStatus.CANCELLED)
    now = finished_at or datetime.now(UTC)
    return replace(
        job,
        status=JobStatus.CANCELLED,
        updated_at=now,
        finished_at=now,
    )


def _raise_invalid_transition(job: Job, target: JobStatus) -> None:
    raise JobConflictError(
        "INVALID_JOB_STATUS_TRANSITION",
        f"Job cannot transition from {job.status.value} to {target.value}.",
        details={
            "jobId": str(job.id),
            "fromStatus": job.status.value,
            "toStatus": target.value,
        },
    )
