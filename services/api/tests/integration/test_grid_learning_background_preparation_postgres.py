"""Real durable job replay, preparation-only fencing and recovery in a fresh service."""

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.application.grid_correction_learning import GridCorrectionLearningService
from game_predictor_api.application.storage_gc import StorageGcArtifactStore
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.jobs import JobType
from game_predictor_api.domain.storage_retention import StorageRetentionPolicy
from game_predictor_api.domain.worker_lanes import WorkerLaneName
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.grid_cohort_asset_retention import cohort_asset_guard_key
from game_predictor_api.storage.grid_model_registry import SqlAlchemyGridModelRegistryRepository
from game_predictor_api.storage.storage_gc_repository import SqlAlchemyStorageGcRepository
from game_predictor_api.storage.worker_lane_repository import SqlAlchemyWorkerLaneRepository
from game_predictor_worker.images.grid_correction_learning_handler import (
    GridCorrectionLearningJobHandler,
)
from game_predictor_worker.jobs.runtime import JobExecutionResult, LocalJobWorker
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore
from game_predictor_worker.training_core.grid_training_admission import RuntimeFacts
from sqlalchemy import text
from test_grid_correction_learning_api import preview_value

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit disposable PostgreSQL only",
)


def test_queue_is_fast_replay_safe_and_preparation_requires_explicit_training_resume(
    tmp_path_factory, monkeypatch
):
    # Keep the managed tree enumerable by Windows GC, so retention is exercised
    # rather than accidentally passing because a long fixture path is invisible.
    tmp_path = tmp_path_factory.mktemp("prep")
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
        legacy = {"idempotencyKey": str(uuid4()), "previewSha256": "unused"}
        with pytest.raises(GridCohortError, match="already active"):
            fresh.start(game, legacy, "local-owner")
        with pytest.raises(GridCohortError, match="another command"):
            fresh.start(
                game, {**legacy, "idempotencyKey": command["idempotencyKey"]}, "local-owner"
            )
        with factory() as blocker, blocker.begin():
            blocker.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": f"grid-learning-background:{game}"},
            )
            with pytest.raises(GridCohortError) as busy:
                fresh.start(game, {**command, "idempotencyKey": str(uuid4())}, "local-owner")
            assert busy.value.code == "GRID_LEARNING_BUSY" and busy.value.status == 409
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
        imports = tmp_path / "imports"
        imports.mkdir()

        def assert_retained(expected_status):
            with factory() as session:
                persisted = fresh._job(session, game, identifier)
                assert persisted.status.value == expected_status
                artifact = persisted.checkpoint_payload["preparedArtifact"]
            scan = StorageGcArtifactStore(tmp_path, imports).scan(
                SqlAlchemyStorageGcRepository(factory),
                policy=StorageRetentionPolicy(),
                now=datetime.now(UTC),
            )
            assert artifact["path"] not in {item.relative_path for item in scan.entries}
            retained = next(
                item
                for item in scan.protected
                if item.observation.relative_path == artifact["path"]
            )
            assert "retained_cohort_reference" in {
                reason.value for reason in retained.protection_reasons
            }
            assert (tmp_path / artifact["path"]).is_file()

        def probe():
            assert_retained("processing")
            probes.append(True)
            return runtime

        store = SqlAlchemyWorkerJobStore(factory)
        checkpoint = store.checkpoint
        guarded_publications = []

        def guarded_checkpoint(job_id, **values):
            if values["stage"] == "data_prepared":
                namespace, guard_key = cohort_asset_guard_key(game, job_id)
                with factory() as session:
                    acquired = session.scalar(
                        text(
                            "SELECT pg_try_advisory_xact_lock("
                            "CAST(:namespace AS integer),CAST(:key AS integer))"
                        ),
                        {"namespace": namespace, "key": guard_key},
                    )
                    assert acquired is False, "Publication guard must cover the durable checkpoint"
                guarded_publications.append(job_id)
            return checkpoint(job_id, **values)

        monkeypatch.setattr(store, "checkpoint", guarded_checkpoint)
        projection_changes = []
        monkeypatch.setattr(
            SqlAlchemyBoardSearchProjectionRepository,
            "mark_live_projection_ready",
            lambda *args: projection_changes.append(args),
        )
        worker = LocalJobWorker(
            store,
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
        assert guarded_publications == [identifier]
        assert projection_changes == [], "Learning review must not repair an unrelated projection"
        restarted = GridCorrectionLearningService(db.app_engine, factory, tmp_path)
        prepared = restarted.get(game, identifier)
        assert prepared["status"] == "waiting_for_review"
        assert prepared["preparedPreview"]["trainingMode"] == "screen+grid"
        assert prepared["trainingRunId"] is None
        with factory() as session:
            artifact = fresh._job(session, game, identifier).checkpoint_payload["preparedArtifact"]
        old = (datetime.now(UTC) - timedelta(hours=25)).timestamp()
        os.utime(tmp_path / artifact["path"], (old, old))
        assert_retained("waiting_for_review")
        another = restarted.start(game, {**command, "idempotencyKey": str(uuid4())}, "local-owner")
        with pytest.raises(GridCohortError, match="already active"):
            restarted.resume(game, identifier, "local-owner")
        restarted.cancel(game, UUID(another["learningId"]), "local-owner")
        with factory() as blocker, blocker.begin():
            blocker.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": f"grid-learning-background:{game}"},
            )
            with pytest.raises(GridCohortError) as busy:
                restarted.resume(game, identifier, "local-owner")
            assert busy.value.code == "GRID_LEARNING_BUSY" and busy.value.status == 409
        resumed = restarted.resume(game, identifier, "local-owner")
        assert resumed["status"] == "created"
        assert_retained("created")
        assert worker.run_once() == JobExecutionResult.WAITING_FOR_DEPENDENCY
        assert probes == [True]
        with factory() as session:
            assert restarted._job(session, game, identifier).checkpoint_payload[
                "trainingAuthorized"
            ]
