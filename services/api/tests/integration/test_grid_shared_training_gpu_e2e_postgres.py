"""TASK-1006 E2E: one shared candidate trained on the GPU from cohorts of two games.

Real PostgreSQL jobs and lane, the real supervisor and the real CUDA trainer; the frozen
cohorts are generated TASK-0995 fixtures of two disposable games of unequal size, read
through a file-backed stand-in for the per-game cohort reads. Runs only with
``GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`` and ``GAME_PREDICTOR_GRID_TRAINING_PYTHON``.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from _application_role_database import application_role_database
from _grid_training_e2e_support import FileStore, base_descriptor
from game_predictor_api.domain.jobs import JobExecutionSlot, JobStatus, JobType, create_job
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.job_repository import job_from_record, job_record_from_domain
from game_predictor_api.storage.models import JobModel
from game_predictor_worker.images.grid_shared_candidate import plan_for
from game_predictor_worker.images.grid_training_handler import (
    GridTrainingJobHandler,
    run_directory,
)
from game_predictor_worker.jobs.runtime import JobExecutionResult, LocalJobWorker
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore
from game_predictor_worker.training_core.grid_training_admission import GRID_ONLY_V1
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

PYTHON = os.environ.get("GAME_PREDICTOR_GRID_TRAINING_PYTHON", "")
REPOSITORY = Path(__file__).resolve().parents[4]
pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1" or not PYTHON,
    reason="Needs isolated PostgreSQL and GAME_PREDICTOR_GRID_TRAINING_PYTHON (CUDA).",
)
sys.path.insert(0, str(REPOSITORY / "services/worker/tests"))


class SharedFileStore(FileStore):
    def cohort(self, game_id: UUID, cohort_id: UUID) -> dict[str, Any]:
        header = self._load()["cohorts"][str(game_id)]
        assert header["id"] == str(cohort_id)
        return header

    def recordings(self, game_id: UUID, cohort_id: UUID) -> dict[str, str]:
        return self._load()["recordings"][str(game_id)]


def _cohort(
    root: Path, game: UUID, base: dict[str, Any], train: int, shade: int
) -> tuple[Any, Any, Any]:
    from unittest.mock import patch

    from PIL import Image
    from test_grid_cohort_dataset import SnapshotFixture

    fixture = SnapshotFixture(root)
    fixture.game = str(game)  # the snapshot belongs to the disposable game
    fixture.directory = f"data/grid-training-cohorts/{fixture.game}/{fixture.cohort}"
    real = Image.new
    # Distinct photos per game: equal bytes across games would be a refused control alias.
    with patch.object(
        Image, "new", lambda mode, size, colour: real(mode, size, (colour[0], shade, 90))
    ):
        for _ in range(train):
            fixture.source("TRAIN", full=True)
        for _ in range(2):
            fixture.source("VALIDATION", full=True)
        fixture.source("REGRESSION", full=True)
    fixture.publish()
    header = {
        "gameId": fixture.game,
        "id": fixture.cohort,
        "status": "frozen",
        "manifestSha256": fixture.manifest_pin["sha256"],
        "manifestPath": fixture.manifest_pin["path"],
        "mode": "grid-only",
        "familyId": base["familyId"],
        "baseVersionId": base["versionId"],
        "summary": {
            "roles": [
                {
                    "role": "TRAIN",
                    "eligibleBoards": 9 * train,
                    "eligiblePhotos": train,
                    "eligibleFullPhotos": train,
                },
                {
                    "role": "VALIDATION",
                    "eligibleBoards": 18,
                    "eligiblePhotos": 2,
                    "eligibleFullPhotos": 2,
                },
            ]
        },
    }
    groups = {
        source["sourceId"]: f"{fixture.game}:{source['role']}:{index % 3}"
        for index, source in enumerate(fixture.sources)
    }
    return fixture, header, groups


def test_shared_candidate_trains_on_two_games_on_the_gpu(tmp_path: Path) -> None:
    with application_role_database("t1006gpu", ("small", "large")) as db:
        root = tmp_path / "artifacts"
        root.mkdir()
        base = base_descriptor(root)
        small, large = db.games["small"], db.games["large"]
        _, small_header, small_groups = _cohort(root, small, base, train=3, shade=40)
        _, large_header, large_groups = _cohort(root, large, base, train=9, shade=160)
        (root / "e2e-store.json").write_text(
            json.dumps(
                {
                    "cohorts": {str(small): small_header, str(large): large_header},
                    "recordings": {str(small): small_groups, str(large): large_groups},
                    "base": base,
                }
            ),
            encoding="utf-8",
        )
        plan = plan_for(
            root, str(small), [(small_header, small_groups), (large_header, large_groups)]
        )
        app_url = db.app_url.render_as_string(hide_password=False)
        engine = create_engine(app_url, poolclass=NullPool)
        factory = create_session_factory(engine)
        job = create_job(
            JobType.GRID_TRAINING,
            game_id=small,
            input_payload={
                "schema_version": 1,
                "training_kind": "grid-shared-training-run-v1",
                "idempotency_key": str(uuid4()),
                "cohort_id": small_header["id"],
                "cohort_manifest_sha256": small_header["manifestSha256"],
                "mode": "grid-only",
                "family_id": base["familyId"],
                "base_version_id": base["versionId"],
                "preset_id": GRID_ONLY_V1.preset_id,
                "preset_fingerprint": GRID_ONLY_V1.fingerprint,
                "seed": 13,
                "planned_steps": 40,
                "shared_cohorts": [
                    {
                        "game_id": str(large),
                        "cohort_id": large_header["id"],
                        "manifest_sha256": large_header["manifestSha256"],
                    }
                ],
                "joint_sha256": plan["sha256"],
            },
        )
        with game_storage_scope(small), factory.begin() as session:
            session.add(job_record_from_domain(job))
        sources = [REPOSITORY / "services/worker/src", REPOSITORY / "services/api/src"]
        handler = GridTrainingJobHandler(
            SharedFileStore(root),
            artifact_root=root,
            python=Path(PYTHON),
            pythonpath=os.pathsep.join(str(path) for path in sources),
            repository_root=REPOSITORY,
            poll_seconds=2.0,
        )
        worker = LocalJobWorker(
            SqlAlchemyWorkerJobStore(factory),
            {JobType.GRID_TRAINING: handler},
            worker_id=f"e2e-{os.getpid()}",
            worker_version="e2e",
            execution_slot=JobExecutionSlot.GRID_TRAINING,
            lease_duration=timedelta(seconds=20),
        )
        started = time.monotonic()
        result = worker.run_once()
        seconds = round(time.monotonic() - started, 1)
        with game_storage_scope(small), factory() as session:
            done = job_from_record(session.get(JobModel, job.id))
        assert result is JobExecutionResult.COMPLETED, (done.error_code, done.error_message)
        assert done.status is JobStatus.COMPLETED
        spec = json.loads((run_directory(root, job.id) / "spec.json").read_text("utf-8"))
        joint = spec["payload"]["joint"]
        assert joint["sha256"] == plan["sha256"]
        assert [pin["gameId"] for pin in joint["cohorts"]] == [str(small), str(large)]
        registered = json.loads((root / "e2e-store.json").read_text("utf-8"))["registered"]
        (descriptor,) = registered.values()
        assert descriptor["admission"] == "not_evaluated"
        assert descriptor["cohortId"] == small_header["id"]
        assert descriptor["provenance"]["snapshotId"] == plan["sha256"]
        assert str(large) in descriptor["inferenceManifest"]["selectionReason"]
        evidence = REPOSITORY / "artifacts/audits/TASK-1006_GPU_E2E.json"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(
            json.dumps(
                {
                    "seconds": seconds,
                    "jointSha256": plan["sha256"],
                    "cohorts": plan["cohorts"],
                    "history": done.checkpoint_payload.get("history"),
                    "versionId": descriptor["versionId"],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        engine.dispose()
