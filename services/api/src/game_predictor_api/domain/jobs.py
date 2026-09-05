"""Framework-independent job lifecycle and progress rules."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from uuid import UUID, uuid4


class JobType(StrEnum):
    IMPORT = "import"
    IMAGE_SELECTION = "image_selection"
    SEMI_AUTOMATIC_IMAGE_SELECTION = "semi_automatic_image_selection"
    VALIDATE = "validate"
    PAYOUT = "payout"
    SNAPSHOT = "snapshot"
    ANDROID_BUILD = "android_build"
    SYMBOL_TRAINING = "symbol_training"
    IMAGE_SYMBOL_REINFERENCE = "image_symbol_reinference"
    IMAGE_GRID_REINFERENCE = "image_grid_reinference"
    IMAGE_SYMBOL_REVIEW_BULK = "image_symbol_review_bulk"
    IMAGE_SYMBOL_REVIEW_BACKFILL = "image_symbol_review_backfill"
    IMAGE_GEOMETRY_ROLLOUT_BACKFILL = "image_geometry_rollout_backfill"
    STORAGE_GC = "storage_gc"
    STORAGE_INVENTORY = "storage_inventory"
    STORAGE_PIPELINE_COMPACTION = "storage_pipeline_compaction"


class JobStatus(StrEnum):
    CREATED = "created"
    PROCESSING = "processing"
    WAITING_FOR_REVIEW = "waiting_for_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobExecutionSlot(IntEnum):
    GENERAL = 1
    IMAGE_SELECTION = 2


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
    checkpoint_payload: dict[str, object] | None
    attempt_count: int
    execution_slot: int | None
    lease_owner: str | None
    lease_token: UUID | None
    lease_expires_at: datetime | None
    heartbeat_at: datetime | None
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
    supports_pinned_image_model = (
        schema_version in {2, 3, 4, 5, 6, 7}
        and job_type is JobType.IMPORT
        and input_payload.get("import_kind") == "image_directory"
    )
    supports_symbol_training_v2 = schema_version == 2 and job_type is JobType.SYMBOL_TRAINING
    supports_page_geometry_preflight_v2 = (
        schema_version == 2
        and job_type is JobType.VALIDATE
        and input_payload.get("validation_kind") == "page_geometry_preflight"
    )
    supports_pending_grid_reinference_v2 = (
        schema_version == 2
        and job_type is JobType.IMAGE_GRID_REINFERENCE
        and input_payload.get("inference_kind") == "pending_grid_only"
    )
    supports_semi_automatic_selection_v2 = (
        schema_version == 2 and job_type is JobType.SEMI_AUTOMATIC_IMAGE_SELECTION
    )
    if (
        schema_version != 1
        and not supports_pinned_image_model
        and not supports_symbol_training_v2
        and not supports_page_geometry_preflight_v2
        and not supports_pending_grid_reinference_v2
        and not supports_semi_automatic_selection_v2
    ):
        raise JobError(
            "UNSUPPORTED_JOB_PAYLOAD_VERSION",
            "Job inputPayload must use a supported schema version.",
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
        checkpoint_payload=None,
        attempt_count=0,
        execution_slot=None,
        lease_owner=None,
        lease_token=None,
        lease_expires_at=None,
        heartbeat_at=None,
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
    identity_payload = input_payload
    if job_type is JobType.IMPORT and input_payload.get("import_kind") == "layout_file":
        identity_payload = {
            "schema_version": input_payload.get("schema_version"),
            "import_kind": input_payload.get("import_kind"),
            "source_checksum": input_payload.get("source_checksum"),
            "file_format": input_payload.get("file_format"),
            "contract_version": input_payload.get("contract_version"),
        }
    elif (
        job_type is JobType.VALIDATE
        and input_payload.get("validation_kind") == "page_geometry_preflight"
    ):
        identity_payload = {
            key: value for key, value in input_payload.items() if key != "source_display_name"
        }
    canonical = json.dumps(
        {
            "gameId": None if game_id is None else str(game_id),
            "inputPayload": identity_payload,
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
    worker_id: str,
    lease_token: UUID,
    lease_expires_at: datetime,
    execution_slot: JobExecutionSlot = JobExecutionSlot.GENERAL,
    started_at: datetime | None = None,
) -> Job:
    if job.status is not JobStatus.CREATED:
        _raise_invalid_transition(job, JobStatus.PROCESSING)
    expected_slot = (
        JobExecutionSlot.IMAGE_SELECTION
        if job.job_type in {JobType.IMAGE_SELECTION, JobType.SEMI_AUTOMATIC_IMAGE_SELECTION}
        else JobExecutionSlot.GENERAL
    )
    if execution_slot is not expected_slot:
        raise JobError(
            "INVALID_JOB_EXECUTION_SLOT",
            "The execution slot does not match the job type.",
            details={
                "jobType": job.job_type.value,
                "executionSlot": int(execution_slot),
                "expectedExecutionSlot": int(expected_slot),
            },
        )
    normalized_version = worker_version.strip()
    if not normalized_version:
        raise JobError(
            "INVALID_WORKER_VERSION",
            "workerVersion must not be blank.",
        )
    normalized_worker_id = worker_id.strip()
    if not normalized_worker_id:
        raise JobError(
            "INVALID_WORKER_ID",
            "workerId must not be blank.",
        )
    now = started_at or datetime.now(UTC)
    if lease_expires_at <= now:
        raise JobError(
            "INVALID_JOB_LEASE_EXPIRY",
            "leaseExpiresAt must be later than the claim time.",
        )
    return replace(
        job,
        status=JobStatus.PROCESSING,
        worker_version=normalized_version,
        attempt_count=job.attempt_count + 1,
        execution_slot=int(execution_slot),
        lease_owner=normalized_worker_id,
        lease_token=lease_token,
        lease_expires_at=lease_expires_at,
        heartbeat_at=now,
        started_at=job.started_at or now,
        updated_at=now,
        finished_at=None,
        error_code=None,
        error_message=None,
    )


def update_job_progress(
    job: Job,
    *,
    lease_token: UUID,
    stage: str,
    current: int,
    total: int | None,
    success_count: int,
    failure_count: int,
    review_count: int,
    updated_at: datetime | None = None,
) -> Job:
    now = updated_at or datetime.now(UTC)
    if job.status is not JobStatus.PROCESSING:
        raise JobConflictError(
            "JOB_NOT_PROCESSING",
            "Progress can only be updated for a processing job.",
            details={"jobId": str(job.id), "status": job.status.value},
        )
    require_active_job_lease(job, lease_token=lease_token, checked_at=now)
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
    if job.progress_total is not None and total is not None and total < job.progress_total:
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
        updated_at=now,
    )


def checkpoint_job(
    job: Job,
    *,
    lease_token: UUID,
    checkpoint_payload: dict[str, object],
    stage: str,
    current: int,
    total: int | None,
    success_count: int,
    failure_count: int,
    review_count: int,
    updated_at: datetime | None = None,
) -> Job:
    if checkpoint_payload.get("schema_version") != 1:
        raise JobError(
            "UNSUPPORTED_JOB_CHECKPOINT_VERSION",
            "checkpointPayload must use schemaVersion 1.",
        )
    progressed = update_job_progress(
        job,
        lease_token=lease_token,
        stage=stage,
        current=current,
        total=total,
        success_count=success_count,
        failure_count=failure_count,
        review_count=review_count,
        updated_at=updated_at,
    )
    return replace(progressed, checkpoint_payload=dict(checkpoint_payload))


def renew_job_lease(
    job: Job,
    *,
    lease_token: UUID,
    lease_expires_at: datetime,
    heartbeat_at: datetime | None = None,
) -> Job:
    now = heartbeat_at or datetime.now(UTC)
    require_active_job_lease(job, lease_token=lease_token, checked_at=now)
    if lease_expires_at <= now:
        raise JobError(
            "INVALID_JOB_LEASE_EXPIRY",
            "leaseExpiresAt must be later than heartbeatAt.",
        )
    return replace(
        job,
        lease_expires_at=lease_expires_at,
        heartbeat_at=now,
        updated_at=now,
    )


def wait_for_review(
    job: Job,
    *,
    lease_token: UUID,
    updated_at: datetime | None = None,
) -> Job:
    if job.status is not JobStatus.PROCESSING:
        _raise_invalid_transition(job, JobStatus.WAITING_FOR_REVIEW)
    now = updated_at or datetime.now(UTC)
    require_active_job_lease(job, lease_token=lease_token, checked_at=now)
    return _without_lease(
        replace(
            job,
            status=JobStatus.WAITING_FOR_REVIEW,
            updated_at=now,
        )
    )


def defer_job_for_storage(
    job: Job,
    *,
    lease_token: UUID,
    checkpoint_payload: dict[str, object],
    deferred_at: datetime | None = None,
) -> Job:
    """Release a processing lease while preserving a resumable storage checkpoint."""

    now = deferred_at or datetime.now(UTC)
    if job.status is not JobStatus.PROCESSING:
        _raise_invalid_transition(job, JobStatus.CREATED)
    require_active_job_lease(job, lease_token=lease_token, checked_at=now)
    if checkpoint_payload.get("schema_version") != 1:
        raise JobError(
            "UNSUPPORTED_JOB_CHECKPOINT_VERSION",
            "checkpointPayload must use schemaVersion 1.",
        )
    return _without_lease(
        replace(
            job,
            status=JobStatus.CREATED,
            stage="waiting_for_storage",
            checkpoint_payload=dict(checkpoint_payload),
            updated_at=now,
            finished_at=None,
            error_code=None,
            error_message=None,
        )
    )


def requeue_job(
    job: Job,
    *,
    updated_at: datetime | None = None,
) -> Job:
    if job.status not in {
        JobStatus.WAITING_FOR_REVIEW,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    }:
        _raise_invalid_transition(job, JobStatus.CREATED)
    now = updated_at or datetime.now(UTC)
    return _without_lease(
        replace(
            job,
            status=JobStatus.CREATED,
            updated_at=now,
            finished_at=None,
            cancel_requested_at=None,
            error_code=None,
            error_message=None,
        )
    )


def requeue_job_with_fresh_progress(
    job: Job,
    *,
    updated_at: datetime | None = None,
) -> Job:
    """Requeue a job whose handler deterministically recomputes all progress.

    This is intentionally distinct from :func:`requeue_job`: resumable jobs
    retain their durable cursor, whereas a whole-staging preflight starts a
    fresh calculation. Carrying prior partial counters would make its first
    correct checkpoint look like a progress regression.
    """

    requeued = requeue_job(job, updated_at=updated_at)
    return replace(
        requeued,
        stage=None,
        progress_current=0,
        progress_total=None,
        success_count=0,
        failure_count=0,
        review_count=0,
        checkpoint_payload=None,
    )


def reopen_completed_job_for_revision(
    job: Job,
    *,
    updated_at: datetime | None = None,
) -> Job:
    """Requeue a completed image-selection job after an audited manual revision."""

    if job.status is not JobStatus.COMPLETED or job.job_type is not JobType.IMAGE_SELECTION:
        _raise_invalid_transition(job, JobStatus.CREATED)
    now = updated_at or datetime.now(UTC)
    return _without_lease(
        replace(
            job,
            status=JobStatus.CREATED,
            stage="image_selection:manual_revision",
            updated_at=now,
            finished_at=None,
            cancel_requested_at=None,
            error_code=None,
            error_message=None,
        )
    )


def complete_job(
    job: Job,
    *,
    lease_token: UUID,
    finished_at: datetime | None = None,
) -> Job:
    if job.status is not JobStatus.PROCESSING:
        _raise_invalid_transition(job, JobStatus.COMPLETED)
    now = finished_at or datetime.now(UTC)
    require_active_job_lease(job, lease_token=lease_token, checked_at=now)
    return _without_lease(
        replace(
            job,
            status=JobStatus.COMPLETED,
            updated_at=now,
            finished_at=now,
            error_code=None,
            error_message=None,
        )
    )


def fail_job(
    job: Job,
    *,
    lease_token: UUID,
    error_code: str,
    error_message: str,
    finished_at: datetime | None = None,
) -> Job:
    if job.status is not JobStatus.PROCESSING:
        _raise_invalid_transition(job, JobStatus.FAILED)
    now = finished_at or datetime.now(UTC)
    require_active_job_lease(job, lease_token=lease_token, checked_at=now)
    code = error_code.strip()
    message = error_message.strip()
    if not code or not message:
        raise JobError(
            "INVALID_JOB_ERROR",
            "A failed job requires a non-empty error code and message.",
        )
    return _without_lease(
        replace(
            job,
            status=JobStatus.FAILED,
            updated_at=now,
            finished_at=now,
            error_code=code,
            error_message=message,
        )
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
    lease_token: UUID,
    finished_at: datetime | None = None,
) -> Job:
    if job.status is not JobStatus.PROCESSING:
        _raise_invalid_transition(job, JobStatus.CANCELLED)
    now = finished_at or datetime.now(UTC)
    require_active_job_lease(job, lease_token=lease_token, checked_at=now)
    if job.cancel_requested_at is None:
        _raise_invalid_transition(job, JobStatus.CANCELLED)
    return _without_lease(
        replace(
            job,
            status=JobStatus.CANCELLED,
            updated_at=now,
            finished_at=now,
        )
    )


def recover_expired_job(
    job: Job,
    *,
    recovered_at: datetime | None = None,
) -> Job:
    now = recovered_at or datetime.now(UTC)
    if (
        job.status is not JobStatus.PROCESSING
        or job.lease_expires_at is None
        or job.lease_expires_at > now
    ):
        raise JobConflictError(
            "JOB_LEASE_NOT_EXPIRED",
            "Only a processing job with an expired lease can be recovered.",
            details={"jobId": str(job.id)},
        )
    if job.cancel_requested_at is not None:
        return _without_lease(
            replace(
                job,
                status=JobStatus.CANCELLED,
                updated_at=now,
                finished_at=now,
            )
        )
    return _without_lease(
        replace(
            job,
            status=JobStatus.CREATED,
            updated_at=now,
        )
    )


def require_active_job_lease(
    job: Job,
    *,
    lease_token: UUID,
    checked_at: datetime | None = None,
) -> None:
    now = checked_at or datetime.now(UTC)
    if (
        job.status is not JobStatus.PROCESSING
        or job.lease_token != lease_token
        or job.lease_expires_at is None
        or job.lease_expires_at <= now
    ):
        raise JobConflictError(
            "JOB_LEASE_LOST",
            "The worker no longer owns an active lease for this job.",
            details={"jobId": str(job.id)},
        )


def _without_lease(job: Job) -> Job:
    return replace(
        job,
        execution_slot=None,
        lease_owner=None,
        lease_token=None,
        lease_expires_at=None,
        heartbeat_at=None,
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
