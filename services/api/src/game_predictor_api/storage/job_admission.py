"""One transaction-scoped gate for mutually conflicting game image workflows."""

import hashlib
from uuid import UUID

from sqlalchemy import and_, func, or_, select, text, true
from sqlalchemy.orm import Session

from game_predictor_api.domain.jobs import Job, JobConflictError, JobStatus, JobType
from game_predictor_api.storage.models import JobModel

_TYPES = frozenset(
    {
        JobType.IMAGE_GRID_REINFERENCE,
        JobType.IMAGE_GEOMETRY_ROLLOUT_BACKFILL,
        JobType.SYMBOL_TRAINING,
        JobType.IMAGE_SYMBOL_REINFERENCE,
        JobType.IMAGE_SYMBOL_REVIEW_BULK,
        JobType.IMAGE_SYMBOL_REVIEW_BACKFILL,
    }
)


def participates(job: Job) -> bool:
    return bool(
        job.game_id is not None
        and (
            job.job_type in _TYPES
            or (
                job.job_type is JobType.IMPORT
                and job.input_payload.get("import_kind") == "image_directory"
            )
            or (
                job.job_type is JobType.VALIDATE
                and job.input_payload.get("validation_kind") == "page_geometry_preflight"
            )
        )
    )


def acquire_job_admission(
    session: Session,
    game_id: UUID,
    *,
    exclude_job_id: UUID | None = None,
    require_idle: bool = True,
    processing_only: bool = False,
    wait: bool = True,
) -> None:
    """Call before the first job row lock and before publishing CREATED."""
    lock_key = int.from_bytes(
        hashlib.sha256(f"grid-admission:{game_id}".encode()).digest()[:8], "big", signed=True
    )
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SET LOCAL lock_timeout='5s'"))
        if wait:
            session.execute(select(func.pg_advisory_xact_lock(lock_key)))
        elif not session.scalar(select(func.pg_try_advisory_xact_lock(lock_key))):
            raise JobConflictError(
                "GAME_JOB_ADMISSION_CONFLICT", "The game execution gate is busy."
            )
    if not require_idle:
        return
    candidate = session.scalar(
        select(JobModel.id)
        .where(
            JobModel.game_id == game_id,
            JobModel.status.in_(
                (JobStatus.PROCESSING,)
                if processing_only
                else (JobStatus.CREATED, JobStatus.PROCESSING)
            ),
            JobModel.id != exclude_job_id if exclude_job_id is not None else true(),
            or_(
                JobModel.job_type.in_(_TYPES),
                and_(
                    JobModel.job_type == JobType.IMPORT,
                    JobModel.input_payload["import_kind"].as_string() == "image_directory",
                ),
                and_(
                    JobModel.job_type == JobType.VALIDATE,
                    JobModel.input_payload["validation_kind"].as_string()
                    == "page_geometry_preflight",
                ),
            ),
        )
        .limit(1)
    )
    if candidate is not None:
        raise JobConflictError(
            "GAME_JOB_ADMISSION_CONFLICT",
            "A conflicting image or symbol job is active.",
            details={"existingJobId": str(candidate)},
        )


def admit_job(session: Session, job: Job, *, worker_execution: bool = False) -> None:
    if participates(job):
        assert job.game_id is not None
        acquire_job_admission(
            session,
            job.game_id,
            exclude_job_id=job.id,
            processing_only=worker_execution,
            wait=not worker_execution,
        )
