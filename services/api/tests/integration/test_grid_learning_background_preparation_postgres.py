"""Real durable job replay, preparation-only fencing and recovery in a fresh service."""

import os
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.application.grid_correction_learning import GridCorrectionLearningService
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.jobs import JobType
from game_predictor_api.domain.worker_lanes import WorkerLaneName
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.grid_model_registry import SqlAlchemyGridModelRegistryRepository
from game_predictor_api.storage.worker_lane_repository import SqlAlchemyWorkerLaneRepository
from game_predictor_worker.images.grid_correction_learning_handler import (
    GridCorrectionLearningJobHandler,
)
from game_predictor_worker.jobs.runtime import JobExecutionResult, LocalJobWorker
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore
from game_predictor_worker.training_core.grid_training_admission import RuntimeFacts
from test_grid_correction_learning_api import preview_value

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit disposable PostgreSQL only",
)


def test_queue_is_fast_replay_safe_and_preparation_requires_explicit_training_resume(
    tmp_path, monkeypatch
):
    with application_role_database("t1230", ("preparation",)) as db:
        game = next(iter(db.games.values()))
        factory = create_session_factory(db.app_engine)
        service = GridCorrectionLearningService(db.app_engine, factory, tmp_path)
        default = SimpleNamespace(version_id=uuid4(), revision=5)
        monkeypatch.setattr(SqlAlchemyGridModelRegistryRepository, "default", lambda _: default)
        monkeypatch.setattr(service, "_preview", lambda *_: pytest.fail("No split inside HTTP"))
        command = {
            "idempotencyKey": str(uuid4()),
            "prepareInBackground": True,
            "preparationOnly": True,
            "trainingMode": "screen+grid",
            "importJobIds": [],
            "exclusions": [],
        }
        with pytest.raises(GridCohortError, match="Restart the general worker"):
            service.start(game, command, "local-owner")
        SqlAlchemyWorkerLaneRepository(factory).register(
            lane=WorkerLaneName.GENERAL,
            instance_token=uuid4(),
            worker_id="test",
            worker_version="test-grid-preparation-v1",
            process_id=1,
            thread_budget=1,
            started_at=datetime.now(UTC),
        )
        queued = service.start(game, command, "local-owner")
        identifier = UUID(queued["learningId"])
        assert queued["stage"] == "preparing_data"
        assert queued["commandKey"] == command["idempotencyKey"]
        fresh = GridCorrectionLearningService(db.app_engine, factory, tmp_path)
        assert fresh.start(game, command, "local-owner")["learningId"] == str(identifier)
        with pytest.raises(GridCohortError, match="another command"):
            fresh.start(game, {**command, "trainingMode": "grid-only"}, "local-owner")
        with pytest.raises(GridCohortError, match="already active"):
            fresh.start(game, {**command, "idempotencyKey": str(uuid4())}, "local-owner")
        preview = {
            **preview_value(),
            "gameId": str(game),
            "trainingMode": "screen+grid",
            "baseVersionId": str(default.version_id),
            "defaultRevision": 5,
        }
        monkeypatch.setattr(fresh, "_preview", lambda *_: (preview, {}))
        runtime = RuntimeFacts(
            True,
            "2.12.1+cu130",
            "0.27.1+cu130",
            "13.0",
            "NVIDIA GeForce RTX 4050 Laptop GPU",
            6439305216,
            6200000000,
        )
        probes = []

        def probe():
            probes.append(True)
            return runtime

        worker = LocalJobWorker(
            SqlAlchemyWorkerJobStore(factory),
            {JobType.GRID_CORRECTION_LEARNING: GridCorrectionLearningJobHandler(fresh, probe)},
            worker_id="preparation-test",
            worker_version="test-grid-preparation-v1",
        )
        old_worker = LocalJobWorker(
            SqlAlchemyWorkerJobStore(factory),
            {JobType.GRID_CORRECTION_LEARNING: lambda *_: pytest.fail("Old worker must not claim")},
            worker_id="old-preparation-test",
            worker_version="worker-v10-general",
        )
        assert old_worker.run_once() == JobExecutionResult.NO_JOB
        assert fresh.get(game, identifier)["status"] == "created"
        assert worker.run_once() == JobExecutionResult.WAITING_FOR_REVIEW
        assert probes == []
        restarted = GridCorrectionLearningService(db.app_engine, factory, tmp_path)
        prepared = restarted.get(game, identifier)
        assert prepared["status"] == "waiting_for_review"
        assert prepared["preparedPreview"]["trainingMode"] == "screen+grid"
        assert prepared["trainingRunId"] is None
        another = restarted.start(game, {**command, "idempotencyKey": str(uuid4())}, "local-owner")
        with pytest.raises(GridCohortError, match="already active"):
            restarted.resume(game, identifier, "local-owner")
        restarted.cancel(game, UUID(another["learningId"]), "local-owner")
        resumed = restarted.resume(game, identifier, "local-owner")
        assert resumed["status"] == "created"
        assert worker.run_once() == JobExecutionResult.WAITING_FOR_DEPENDENCY
        assert probes == [True]
        with factory() as session:
            assert restarted._job(session, game, identifier).checkpoint_payload[
                "trainingAuthorized"
            ]
