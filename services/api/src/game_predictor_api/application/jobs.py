"""Application service and repository port for durable jobs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.jobs import (
    Job,
    JobConflictError,
    JobNotFoundError,
    JobStatus,
    JobType,
    create_job,
    request_job_cancellation,
    requeue_job,
)


class JobRepository(Protocol):
    def game_exists(self, game_id: UUID) -> bool: ...

    def add_job(self, job: Job) -> Job: ...

    def get_job(self, job_id: UUID) -> Job | None: ...

    def get_job_for_update(self, job_id: UUID) -> Job | None: ...

    def get_job_by_input_key(self, input_key: str) -> Job | None: ...

    def list_jobs(
        self,
        *,
        status: JobStatus | None,
        job_type: JobType | None,
        game_id: UUID | None,
        limit: int,
    ) -> Sequence[Job]: ...

    def save_job(self, job: Job) -> Job: ...


class JobService:
    def __init__(self, repository: JobRepository) -> None:
        self._repository = repository

    def create_job(
        self,
        job_type: JobType,
        *,
        game_id: UUID | None,
        input_payload: dict[str, object],
    ) -> Job:
        if game_id is not None and not self._repository.game_exists(game_id):
            raise JobNotFoundError(
                "GAME_NOT_FOUND",
                "Game does not exist.",
                details={"gameId": str(game_id)},
            )
        job = create_job(
            job_type,
            game_id=game_id,
            input_payload=input_payload,
        )
        existing = self._repository.get_job_by_input_key(job.input_key)
        if existing is not None:
            raise JobConflictError(
                "JOB_INPUT_ALREADY_EXISTS",
                "A job with the same type and input already exists.",
                details={"existingJobId": str(existing.id)},
            )
        return self._repository.add_job(job)

    def get_job(self, job_id: UUID) -> Job:
        job = self._repository.get_job(job_id)
        if job is None:
            raise JobNotFoundError(
                "JOB_NOT_FOUND",
                "Job does not exist.",
                details={"jobId": str(job_id)},
            )
        return job

    def list_jobs(
        self,
        *,
        status: JobStatus | None,
        job_type: JobType | None,
        game_id: UUID | None,
        limit: int,
    ) -> Sequence[Job]:
        return self._repository.list_jobs(
            status=status,
            job_type=job_type,
            game_id=game_id,
            limit=limit,
        )

    def cancel_job(self, job_id: UUID) -> Job:
        job = self._repository.get_job_for_update(job_id)
        if job is None:
            raise JobNotFoundError(
                "JOB_NOT_FOUND",
                "Job does not exist.",
                details={"jobId": str(job_id)},
            )
        updated = request_job_cancellation(job)
        if updated is job:
            return job
        return self._repository.save_job(updated)

    def retry_job(self, job_id: UUID) -> Job:
        job = self._repository.get_job_for_update(job_id)
        if job is None:
            raise JobNotFoundError(
                "JOB_NOT_FOUND",
                "Job does not exist.",
                details={"jobId": str(job_id)},
            )
        return self._repository.save_job(requeue_job(job))
