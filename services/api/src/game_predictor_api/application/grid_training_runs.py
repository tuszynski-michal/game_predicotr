"""Application grid-training runs as pinned ``grid_training`` jobs (TASK-0996, D-558).

A run is one job of its own lane. Creation repeats the read-only ``run-preview`` checks,
pins the frozen cohort, its base version and the approved preset, and is idempotent per
key. The durable run state (budget, checkpoint pointer, export, registered candidate) is
the job's ``checkpoint_payload`` written by the supervisor; this service only reads it.
Cancel and resume reuse the job lifecycle; resume never renews the budget.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from uuid import UUID

from game_predictor_api.application.grid_training_cohorts import GridTrainingCohortService
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.jobs import (
    Job,
    JobStatus,
    JobType,
    create_job,
    request_job_cancellation,
    requeue_job,
)

TRAINING_KIND = "grid-training-run-v1"
LIST_LIMIT = 200
# Lease state only says whether the GPU is free now; a queued job waits for its lane.
_QUEUE_BLOCKERS_IGNORED = {"GRID_RUN_LEASE_BUSY", "GRID_RUN_LEASE_UNKNOWN"}


class GridTrainingJobRepository(Protocol):
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

    def add_job(self, job: Job) -> Job: ...

    def save_job(self, job: Job) -> Job: ...

    def lock_idempotency(self, key: UUID) -> None: ...

    def find_by_idempotency(self, key: UUID) -> Job | None: ...


def _error(code: str, message: str, status: int = 409) -> GridCohortError:
    return GridCohortError(code, message, status)


class GridTrainingRunService:
    def __init__(self, cohorts: GridTrainingCohortService, jobs: GridTrainingJobRepository) -> None:
        self.cohorts, self.jobs = cohorts, jobs

    def create(self, game: UUID, command: Mapping[str, Any]) -> dict[str, Any]:
        key = UUID(str(command["idempotencyKey"]))
        cohort = UUID(str(command["cohortId"]))
        self.jobs.lock_idempotency(key)
        existing = self.jobs.find_by_idempotency(key)
        if existing is not None:
            if (
                existing.game_id != game
                or existing.input_payload.get("cohort_id") != str(cohort)
                or existing.input_payload.get("preset_id") != command["presetId"]
                or existing.input_payload.get("preset_fingerprint") != command["presetFingerprint"]
            ):
                raise _error("GRID_RUN_IDEMPOTENCY_CONFLICT", "The key was used for another run.")
            return self.view(existing)
        preview = self.cohorts.run_preview(game, cohort)
        blockers = [code for code in preview["apiBlockers"] if code not in _QUEUE_BLOCKERS_IGNORED]
        if blockers:
            raise _error(blockers[0], "The cohort cannot start a training run.")
        if (
            preview["selectedPresetId"] != command["presetId"]
            or next(
                (
                    p["fingerprint"]
                    for p in preview["presets"]
                    if p["presetId"] == command["presetId"]
                ),
                None,
            )
            != command["presetFingerprint"]
        ):
            raise _error("GRID_RUN_PRESET_NOT_APPROVED", "Choose the approved preset of the mode.")
        header = self.cohorts.get(game, cohort)
        payload: dict[str, object] = {
            "schema_version": 1,
            "training_kind": TRAINING_KIND,
            "idempotency_key": str(key),
            "cohort_id": str(cohort),
            "cohort_manifest_sha256": header["manifestSha256"],
            "mode": header["mode"],
            "family_id": str(header["familyId"]),
            "base_version_id": str(header["baseVersionId"]),
            "preset_id": command["presetId"],
            "preset_fingerprint": command["presetFingerprint"],
            "seed": key.int % (2**31 - 1),
            "planned_steps": int(preview["cost"]["plannedSteps"]),
        }
        job = create_job(JobType.GRID_TRAINING, game_id=game, input_payload=payload)
        existing = self.jobs.get_job_by_input_key(job.input_key)
        return self.view(existing if existing is not None else self.jobs.add_job(job))

    def _jobs(self, game: UUID) -> list[Job]:
        return [
            job
            for job in self.jobs.list_jobs(
                status=None, job_type=JobType.GRID_TRAINING, game_id=game, limit=LIST_LIMIT
            )
            if job.game_id == game
        ]

    def _job(self, game: UUID, run: UUID, *, lock: bool = False) -> Job:
        job = self.jobs.get_job_for_update(run) if lock else self.jobs.get_job(run)
        if job is None or job.job_type is not JobType.GRID_TRAINING or job.game_id != game:
            raise _error("GRID_RUN_NOT_FOUND", "Training run does not exist.", 404)
        return job

    def list(self, game: UUID) -> dict[str, Any]:
        return {"items": [self.view(job) for job in self._jobs(game)]}

    def get(self, game: UUID, run: UUID) -> dict[str, Any]:
        return self.view(self._job(game, run))

    def cancel(self, game: UUID, run: UUID) -> dict[str, Any]:
        job = self._job(game, run, lock=True)
        updated = request_job_cancellation(job)
        return self.view(job if updated is job else self.jobs.save_job(updated))

    def resume(self, game: UUID, run: UUID) -> dict[str, Any]:
        job = self._job(game, run, lock=True)
        if job.status not in {JobStatus.FAILED, JobStatus.CANCELLED}:
            raise _error("GRID_RUN_NOT_RESUMABLE", "Only failed or cancelled runs can resume.")
        return self.view(self.jobs.save_job(requeue_job(job)))

    @staticmethod
    def view(job: Job) -> dict[str, Any]:
        payload = job.input_payload
        state = job.checkpoint_payload or {}
        budget = state.get("budget") if isinstance(state, dict) else None
        budget_body = budget.get("payload") if isinstance(budget, dict) else None
        registered = state.get("registered") if isinstance(state, dict) else None
        checkpoint = state.get("checkpoint") if isinstance(state, dict) else None
        return {
            "runId": str(job.id),
            "gameId": str(job.game_id),
            "status": job.status.value,
            "stage": job.stage,
            "cohortId": payload["cohort_id"],
            "mode": payload["mode"],
            "presetId": payload["preset_id"],
            "presetFingerprint": payload["preset_fingerprint"],
            "baseVersionId": payload["base_version_id"],
            "plannedSteps": payload["planned_steps"],
            "progressCurrent": job.progress_current,
            "progressTotal": job.progress_total,
            "attempt": int(str(state.get("attempt", 0))) if isinstance(state, dict) else 0,
            "budget": None
            if not isinstance(budget_body, dict)
            else {
                "maxSteps": budget_body["max_steps"],
                "maxSeconds": budget_body["max_seconds"],
                "reservedSteps": budget_body["reserved_steps"],
                "usedSeconds": budget_body["used_seconds"],
            },
            "checkpointStep": None if not isinstance(checkpoint, dict) else checkpoint.get("step"),
            "candidateVersionId": None
            if not isinstance(registered, dict)
            else registered.get("versionId"),
            "cancelRequested": job.cancel_requested_at is not None,
            "errorCode": job.error_code,
            "createdAt": job.created_at.isoformat(),
            "updatedAt": job.updated_at.isoformat(),
        }
