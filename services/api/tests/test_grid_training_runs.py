"""TASK-0996: pinned grid-training run jobs, their lane and the HTTP vertical."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.grid_training_runs import create_grid_training_runs_router
from game_predictor_api.application.grid_training_runs import GridTrainingRunService
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.jobs import (
    JobError,
    JobExecutionSlot,
    JobStatus,
    JobType,
    create_job,
    execution_slot_for,
    start_job,
)
from game_predictor_api.schemas.jobs import GridTrainingJobPayload
from game_predictor_worker.training_core.grid_training_admission import GRID_ONLY_V1, PRESETS

GAME = UUID("11111111-1111-4111-8111-111111111111")
COHORT = UUID("22222222-2222-4222-8222-222222222222")
BASE = "33333333-3333-4333-8333-333333333333"


class Cohorts:
    def __init__(self, blockers: list[str] | None = None) -> None:
        self.blockers = blockers or []

    def run_preview(self, game: UUID, cohort: UUID) -> dict[str, Any]:
        return {
            "apiBlockers": list(self.blockers),
            "selectedPresetId": GRID_ONLY_V1.preset_id,
            "presets": [
                {"presetId": p.preset_id, "fingerprint": p.fingerprint} for p in PRESETS.values()
            ],
            "cost": {"plannedSteps": 1200},
        }

    def get(self, game: UUID, cohort: UUID) -> dict[str, Any]:
        return {
            "manifestSha256": "c" * 64,
            "mode": "grid-only",
            "familyId": str(uuid4()),
            "baseVersionId": BASE,
        }


class Jobs:
    def __init__(self) -> None:
        self.rows: dict[UUID, Any] = {}
        self.locked: list[UUID] = []

    def get_job(self, job_id: UUID) -> Any:
        return self.rows.get(job_id)

    get_job_for_update = get_job

    def get_job_by_input_key(self, key: str) -> Any:
        return next((job for job in self.rows.values() if job.input_key == key), None)

    def list_jobs(self, *, status: Any, job_type: Any, game_id: Any, limit: int) -> list[Any]:
        return [
            job for job in self.rows.values() if job.job_type is job_type and job.game_id == game_id
        ][:limit]

    def lock_idempotency(self, key: UUID) -> None:
        self.locked.append(key)

    def find_by_idempotency(self, key: UUID) -> Any:
        return next(
            (
                job
                for job in self.rows.values()
                if job.input_payload.get("idempotency_key") == str(key)
            ),
            None,
        )

    def add_job(self, job: Any) -> Any:
        self.rows[job.id] = job
        return job

    save_job = add_job


def command(key: UUID | None = None, **changes: Any) -> dict[str, Any]:
    return {
        "idempotencyKey": str(key or uuid4()),
        "cohortId": str(COHORT),
        "presetId": GRID_ONLY_V1.preset_id,
        "presetFingerprint": GRID_ONLY_V1.fingerprint,
        **changes,
    }


def test_create_pins_the_cohort_preset_and_plan_and_is_idempotent_per_key() -> None:
    jobs = Jobs()
    service = GridTrainingRunService(Cohorts(), jobs)  # type: ignore[arg-type]
    key = uuid4()
    first = service.create(GAME, command(key))
    again = service.create(GAME, command(key))
    assert first == again and len(jobs.rows) == 1
    assert jobs.locked == [key, key]  # every create serializes on its exact key
    job = next(iter(jobs.rows.values()))
    assert job.job_type is JobType.GRID_TRAINING and job.status is JobStatus.CREATED
    payload = GridTrainingJobPayload.model_validate(job.input_payload)
    assert payload.planned_steps == 1200 and str(payload.base_version_id) == BASE
    assert payload.seed == key.int % (2**31 - 1)
    assert first["presetFingerprint"] == GRID_ONLY_V1.fingerprint and first["budget"] is None
    with pytest.raises(GridCohortError) as error:
        service.create(GAME, command(key, presetId="screen-grid-v1"))
    assert error.value.code == "GRID_RUN_IDEMPOTENCY_CONFLICT"
    for _ in range(250):  # an old key stays found beyond any listing limit
        service.create(GAME, command())
    with pytest.raises(GridCohortError) as error:
        service.create(GAME, command(key, presetId="screen-grid-v1"))
    assert error.value.code == "GRID_RUN_IDEMPOTENCY_CONFLICT"


def test_create_repeats_preview_blockers_but_queues_while_the_gpu_is_busy() -> None:
    jobs = Jobs()
    blocked = GridTrainingRunService(Cohorts(["GRID_RUN_COHORT_NOT_QUALIFIED"]), jobs)  # type: ignore[arg-type]
    with pytest.raises(GridCohortError) as error:
        blocked.create(GAME, command())
    assert error.value.code == "GRID_RUN_COHORT_NOT_QUALIFIED" and not jobs.rows
    busy = GridTrainingRunService(Cohorts(["GRID_RUN_LEASE_BUSY"]), jobs)  # type: ignore[arg-type]
    assert busy.create(GAME, command())["status"] == "created"
    with pytest.raises(GridCohortError) as error:
        busy.create(GAME, command(presetFingerprint="0" * 64))
    assert error.value.code == "GRID_RUN_PRESET_NOT_APPROVED"


def test_cancel_and_resume_keep_the_durable_budget_state() -> None:
    jobs = Jobs()
    service = GridTrainingRunService(Cohorts(), jobs)  # type: ignore[arg-type]
    run = UUID(service.create(GAME, command())["runId"])
    with pytest.raises(GridCohortError) as error:
        service.resume(GAME, run)
    assert error.value.code == "GRID_RUN_NOT_RESUMABLE"
    cancelled = service.cancel(GAME, run)
    assert cancelled["status"] == "cancelled"
    state = {
        "budget": {
            "payload": {
                "max_steps": 4000,
                "max_seconds": 3600.0,
                "reserved_steps": 30,
                "used_seconds": 170.0,
            }
        },
        "attempt": 2,
    }
    jobs.rows[run] = replace(jobs.rows[run], checkpoint_payload=state)
    resumed = service.resume(GAME, run)
    assert resumed["status"] == "created" and resumed["attempt"] == 2
    assert resumed["budget"] == {
        "maxSteps": 4000,
        "maxSeconds": 3600.0,
        "reservedSteps": 30,
        "usedSeconds": 170.0,
    }
    with pytest.raises(GridCohortError) as error:
        service.get(uuid4(), run)  # another game never sees the run
    assert error.value.code == "GRID_RUN_NOT_FOUND"


def test_grid_training_has_its_own_slot_and_payload_version() -> None:
    assert execution_slot_for(JobType.GRID_TRAINING) is JobExecutionSlot.GRID_TRAINING
    assert execution_slot_for(JobType.IMPORT) is JobExecutionSlot.GENERAL
    job = create_job(
        JobType.GRID_TRAINING,
        game_id=GAME,
        input_payload={"schema_version": 1, "training_kind": "grid-training-run-v1"},
    )
    started = start_job(
        job,
        worker_version="w",
        worker_id="w",
        lease_token=uuid4(),
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=1),
        execution_slot=JobExecutionSlot.GRID_TRAINING,
    )
    assert started.status is JobStatus.PROCESSING
    with pytest.raises(JobError) as error:
        start_job(
            job,
            worker_version="w",
            worker_id="w",
            lease_token=uuid4(),
            lease_expires_at=datetime.now(UTC) + timedelta(minutes=1),
        )
    assert error.value.code == "INVALID_JOB_EXECUTION_SLOT"
    with pytest.raises(JobError) as error:
        create_job(JobType.GRID_TRAINING, game_id=GAME, input_payload={"schema_version": 2})
    assert error.value.code == "UNSUPPORTED_JOB_PAYLOAD_VERSION"


def test_http_routes_require_the_local_actor_for_mutations() -> None:
    jobs = Jobs()
    service = GridTrainingRunService(Cohorts(), jobs)  # type: ignore[arg-type]
    application = FastAPI()

    @application.middleware("http")
    async def actor(request: Any, call_next: Any) -> Any:
        if request.headers.get("x-test-actor") == "owner":
            request.state.local_admin_actor = "local-owner"
        return await call_next(request)

    @application.exception_handler(GridCohortError)
    async def handle(request: Any, error: GridCohortError) -> Any:
        from fastapi.responses import JSONResponse

        return JSONResponse({"code": error.code}, status_code=error.status)

    application.include_router(create_grid_training_runs_router(lambda: service), prefix="/api/v1")
    client = TestClient(application)
    base = f"/api/v1/admin/games/{GAME}/grid-training-runs"
    assert client.post(base, json=command()).status_code == 403
    created = client.post(base, json=command(), headers={"x-test-actor": "owner"})
    assert created.status_code == 200
    run = created.json()["runId"]
    assert client.get(base).json()["items"][0]["runId"] == run
    assert client.get(f"{base}/{run}").json()["status"] == "created"
    assert client.get(f"{base}/{uuid4()}").status_code == 404
    assert client.post(f"{base}/{run}/cancel").status_code == 403
    assert (
        client.post(f"{base}/{run}/cancel", headers={"x-test-actor": "owner"}).json()["status"]
        == "cancelled"
    )
    resumed = client.post(f"{base}/{run}/resume", headers={"x-test-actor": "owner"})
    assert resumed.json()["status"] == "created"
    operations = {
        operation["operationId"]
        for path in application.openapi()["paths"].values()
        for operation in path.values()
    }
    assert operations == {
        "createGridTrainingRun",
        "listGridTrainingRuns",
        "getGridTrainingRun",
        "cancelGridTrainingRun",
        "resumeGridTrainingRun",
    }
