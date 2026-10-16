"""TASK-0996 E2E: real PostgreSQL jobs, the real grid-training lane worker and the GPU trainer.

Runs only with ``GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`` and a CUDA interpreter in
``GAME_PREDICTOR_GRID_TRAINING_PYTHON``. The database is a disposable ``*_test`` database;
the cohort is the generated TASK-0995 fixture; no operator data is read or written.
Scenario 2 kills the supervisor process mid-run: the orphaned trainer must stop itself,
the job must be recovered after its lease expires and resume from a checkpoint, and the
candidate must be registered exactly once.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from _application_role_database import application_role_database
from _grid_training_e2e_support import base_descriptor, worker
from game_predictor_api.domain.jobs import JobStatus, JobType, create_job
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.job_repository import job_from_record, job_record_from_domain
from game_predictor_api.storage.models import JobModel
from game_predictor_worker.images.grid_training_handler import run_directory
from game_predictor_worker.jobs.runtime import JobExecutionResult
from game_predictor_worker.training_core.gpu_lease import lease_path
from game_predictor_worker.training_core.grid_training_admission import GRID_ONLY_V1, RunBudget
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

PYTHON = os.environ.get("GAME_PREDICTOR_GRID_TRAINING_PYTHON", "")
REPOSITORY = Path(__file__).resolve().parents[4]
pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1" or not PYTHON,
    reason="Needs isolated PostgreSQL and GAME_PREDICTOR_GRID_TRAINING_PYTHON (CUDA).",
)
sys.path.insert(0, str(REPOSITORY / "services/worker/tests"))


def _cohort(root: Path) -> tuple[Any, dict[str, Any]]:
    from test_grid_cohort_dataset import SnapshotFixture

    fixture = SnapshotFixture(root)
    for _ in range(6):
        fixture.source("TRAIN", full=True)
    for _ in range(2):
        fixture.source("VALIDATION", full=True)
    fixture.source("REGRESSION", full=True)
    fixture.publish()
    return fixture, {
        "status": "frozen",
        "manifestSha256": fixture.manifest_pin["sha256"],
        "manifestPath": fixture.manifest_pin["path"],
        "mode": "grid-only",
        "baseVersionId": base_descriptor_holder["base"]["versionId"],
        "summary": {
            "roles": [
                {
                    "role": "TRAIN",
                    "eligibleBoards": 54,
                    "eligiblePhotos": 6,
                    "eligibleFullPhotos": 6,
                },
                {
                    "role": "VALIDATION",
                    "eligibleBoards": 18,
                    "eligiblePhotos": 2,
                    "eligibleFullPhotos": 2,
                },
                {
                    "role": "REGRESSION",
                    "eligibleBoards": 9,
                    "eligiblePhotos": 1,
                    "eligibleFullPhotos": 1,
                },
            ]
        },
    }


base_descriptor_holder: dict[str, Any] = {}


def _job(factory: Any, game: UUID, header: dict[str, Any], planned_steps: int) -> UUID:
    job = create_job(
        JobType.GRID_TRAINING,
        game_id=game,
        input_payload={
            "schema_version": 1,
            "training_kind": "grid-training-run-v1",
            "idempotency_key": str(uuid4()),
            "cohort_id": str(uuid4()),
            "cohort_manifest_sha256": header["manifestSha256"],
            "mode": "grid-only",
            "family_id": base_descriptor_holder["base"]["familyId"],
            "base_version_id": base_descriptor_holder["base"]["versionId"],
            "preset_id": GRID_ONLY_V1.preset_id,
            "preset_fingerprint": GRID_ONLY_V1.fingerprint,
            "seed": 11,
            "planned_steps": planned_steps,
        },
    )
    with game_storage_scope(game), factory.begin() as session:
        session.add(job_record_from_domain(job))
    return job.id


def _read(factory: Any, game: UUID, job_id: UUID) -> Any:
    with game_storage_scope(game), factory() as session:
        return job_from_record(session.get(JobModel, job_id))


def _registered(root: Path) -> dict[str, Any]:
    return json.loads((root / "e2e-store.json").read_text(encoding="utf-8")).get("registered", {})


def test_lane_worker_trains_on_gpu_and_recovers_a_killed_supervisor(tmp_path: Path) -> None:
    with application_role_database("t0996gpu", ("e2e",)) as db:
        root = tmp_path / "artifacts"
        root.mkdir()
        base_descriptor_holder["base"] = base_descriptor(root)
        _, header = _cohort(root)
        (root / "e2e-store.json").write_text(
            json.dumps({"cohort": header, "base": base_descriptor_holder["base"]}), encoding="utf-8"
        )
        app_url = db.app_url.render_as_string(hide_password=False)
        factory = create_session_factory(create_engine(app_url, poolclass=NullPool))
        game = db.games["e2e"]
        evidence: dict[str, Any] = {}

        # 1. Normal run in the lane: claim, GPU training, export, install, register.
        first = _job(factory, game, header, planned_steps=40)
        started = time.monotonic()
        result = worker(app_url, root, PYTHON, 20.0).run_once()
        evidence["normalSeconds"] = round(time.monotonic() - started, 1)
        done = _read(factory, game, first)
        assert result is JobExecutionResult.COMPLETED, (done.error_code, done.error_message)
        assert done.status is JobStatus.COMPLETED
        state = done.checkpoint_payload
        assert state["registered"]["versionId"] in {
            p["versionId"] for p in _registered(root).values()
        }
        budget = RunBudget.from_payload(state["budget"])
        assert budget.reserved_steps == 40 and budget.attempts == 1
        assert not lease_path(root).exists()
        evidence["normal"] = {"usedSeconds": budget.used_seconds, "stage": done.stage}

        # 2. Kill the supervisor mid-run; the orphan stops itself; a new worker resumes.
        second = _job(factory, game, header, planned_steps=700)
        run = run_directory(root, second)
        environment = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                str(REPOSITORY / part)
                for part in (
                    "services/worker/src",
                    "services/api/src",
                    "services/api/tests/integration",
                    "services/worker/tests",
                )
            ),
        }
        process = subprocess.Popen(
            [
                sys.executable,
                str(REPOSITORY / "services/api/tests/integration/_grid_training_e2e_support.py"),
                app_url,
                str(root),
                PYTHON,
                "10",
            ],
            env=environment,
            stdin=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 420
        step = 0
        while time.monotonic() < deadline:
            try:
                step = int(json.loads((run / "progress.json").read_text(encoding="utf-8"))["step"])
            except (OSError, ValueError, KeyError, TypeError):
                step = 0
            if step >= 100:
                break
            time.sleep(2)
        assert step >= 100, "trainer did not reach step 100"
        process.kill()
        process.wait(timeout=30)
        killed_at = time.monotonic()
        evidence["killedAtStep"] = step
        resumed_worker = worker(app_url, root, PYTHON, 10.0)
        outcome = JobExecutionResult.NO_JOB
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            outcome = resumed_worker.run_once()
            if outcome is not JobExecutionResult.NO_JOB:
                break
            time.sleep(3)
        evidence["recoverySeconds"] = round(time.monotonic() - killed_at, 1)
        resumed = _read(factory, game, second)
        assert outcome is JobExecutionResult.COMPLETED, (resumed.error_code, resumed.error_message)
        state = resumed.checkpoint_payload
        spec = json.loads((run / "spec.json").read_text(encoding="utf-8"))["payload"]
        assert spec["attempt"] == 2 and spec["resume"] is not None
        assert spec["resume"]["step"] >= 100  # the orphan's own checkpoint was adopted
        budget = RunBudget.from_payload(state["budget"])
        assert budget.attempts == 2 and budget.reserved_steps == 700  # settled from trusted counts
        versions = [
            p for p in _registered(root).values() if p["provenance"]["runId"] == str(second)
        ]
        assert len(versions) == 1
        assert not lease_path(root).exists()
        evidence["crash"] = {
            "resumeStep": spec["resume"]["step"],
            "reservedSteps": budget.reserved_steps,
            "usedSeconds": budget.used_seconds,
        }
        out = REPOSITORY / "artifacts" / "audits" / "TASK-0996_GPU_E2E.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
