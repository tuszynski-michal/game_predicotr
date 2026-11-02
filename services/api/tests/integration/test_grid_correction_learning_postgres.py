"""Disposable PostgreSQL: parent replay/CAS, no general-lane deadlock and same-child resume."""

import copy
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.application.grid_correction_learning import (
    GridCorrectionLearningService,
    child_key,
)
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.jobs import JobExecutionSlot, JobType
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.grid_model_registry import SqlAlchemyGridModelRegistryRepository
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.source_recording_permissions_v5 import recording_permission_errors
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit disposable PostgreSQL only",
)


def test_parent_replay_cas_release_child_and_resume_original_budget(tmp_path, monkeypatch):
    with application_role_database("t1121", ("corrections",)) as db:
        game = next(iter(db.games.values()))
        factory = create_session_factory(db.app_engine)
        service = GridCorrectionLearningService(db.app_engine, factory, tmp_path)
        default = SimpleNamespace(version_id=uuid4(), revision=4)
        monkeypatch.setattr(SqlAlchemyGridModelRegistryRepository, "default", lambda self: default)
        preview = {
            "gameId": str(game),
            "baseVersionId": str(default.version_id),
            "defaultRevision": 4,
            "previewSha256": "a" * 64,
            "requiredGameIds": [str(game)],
            "exclusions": [],
            "canStart": True,
        }
        pins = {"defaultRevision": 4}
        monkeypatch.setattr(
            GridCorrectionLearningService, "_preview", lambda *args: (copy.deepcopy(preview), pins)
        )
        command = {
            "idempotencyKey": str(uuid4()),
            "previewSha256": "a" * 64,
            "importJobIds": [],
            "exclusions": [],
        }
        from fastapi.testclient import TestClient
        from test_grid_correction_learning_api import HEADERS, app_for

        with TestClient(app_for(service, tmp_path), client=("127.0.0.1", 12345)) as client:
            response = client.post(
                f"/api/v1/admin/games/{game}/grid-correction-learning",
                json=command,
                headers=HEADERS,
            )
            assert response.status_code == 200
            started = response.json()
        identifier = UUID(started["learningId"])
        # Fresh service after a lost HTTP response returns the original identity.
        restarted = GridCorrectionLearningService(db.app_engine, factory, tmp_path)
        assert restarted.start(game, command, "fixture:1121") == started
        assert restarted.get(game, identifier) == started
        with pytest.raises(GridCohortError, match="another command"):
            restarted.start(game, {**command, "previewSha256": "b" * 64}, "fixture:1121")
        default.revision = 5
        with pytest.raises(GridCohortError, match="default changed"):
            restarted.start(game, {**command, "idempotencyKey": str(uuid4())}, "fixture:1121")
        worker = SqlAlchemyWorkerJobStore(factory)

        def claim():
            return worker.claim_next(
                worker_id="fixture",
                worker_version="test",
                lease_duration=timedelta(seconds=60),
                claimed_at=datetime.now(UTC),
                allowed_job_types=frozenset(
                    {JobType.GRID_CORRECTION_LEARNING, JobType.GRID_MODEL_EVALUATION}
                ),
                execution_slot=JobExecutionSlot.GENERAL,
            )

        parent = claim()
        assert parent and parent.id == identifier
        from game_predictor_api.application import grid_model_evaluation as evaluation_module

        manifest = {
            "versionId": str(uuid4()),
            "baseVersionId": str(uuid4()),
            "familyId": str(uuid4()),
            "cohortId": str(uuid4()),
            "provenance": {"runId": str(uuid4())},
        }
        evaluator = restarted.evaluations
        monkeypatch.setattr(evaluator, "_candidate", lambda *args: (manifest, "b" * 64))
        monkeypatch.setattr(evaluator, "_cohort", lambda *args, **kwargs: "c" * 64)
        monkeypatch.setattr(evaluation_module, "candidate_parity", lambda *args: {"passed": True})
        child_view = evaluator.create(
            {
                "idempotencyKey": str(child_key(parent.id, "evaluation")),
                "versionId": manifest["versionId"],
                "cohorts": [{"gameId": str(game), "cohortId": manifest["cohortId"]}],
            }
        )
        with factory() as session:
            child = SqlAlchemyJobRepository(session).get_job(UUID(child_view["evaluationId"]))
            assert child is not None
        worker.defer_for_dependency(
            parent.id,
            lease_token=parent.lease_token,
            checkpoint_payload={
                "schema_version": 1,
                "waitingForJobId": str(child.id),
                "budgetPin": "original",
            },
            deferred_at=datetime.now(UTC),
        )
        # Parent is oldest, but cannot starve its child in the single general slot.
        active = claim()
        assert active and active.id == child.id
        with factory() as lock_session, lock_session.begin():
            restarted._lock_step(lock_session, identifier)
            with pytest.raises(GridCohortError) as busy:
                restarted.cancel(game, identifier, "fixture:1121")
            assert busy.value.code == "GRID_LEARNING_BUSY" and busy.value.status == 409
        # Cancel returns before the processing child acknowledges its request.
        assert restarted.cancel(game, identifier, "fixture:1121")["status"] == "cancelled"
        with pytest.raises(GridCohortError) as pending:
            restarted.resume(game, identifier, "fixture:1121")
        assert pending.value.code == "GRID_LEARNING_CANCELLATION_PENDING"
        assert pending.value.status == 409
        assert restarted.get(game, identifier)["status"] == "cancelled"
        worker.checkpoint(
            child.id,
            lease_token=active.lease_token,
            lease_duration=timedelta(seconds=60),
            checkpoint_payload={"schema_version": 1},
            stage="cancelled",
            current=0,
            total=None,
            success_count=0,
            failure_count=0,
            review_count=0,
            checkpointed_at=datetime.now(UTC),
        )
        # One accepted resume after acknowledgement requeues the original child and parent.
        restarted.resume(game, identifier, "fixture:1121")
        active = claim()
        assert active and active.id == child.id and active.cancel_requested_at is None
        worker.fail(
            child.id,
            lease_token=active.lease_token,
            error_code="FIXTURE_FAILURE",
            error_message="fixture",
            failed_at=datetime.now(UTC),
        )
        parent = claim()
        assert parent and parent.id == identifier
        worker.fail(
            parent.id,
            lease_token=parent.lease_token,
            error_code="FIXTURE_CHILD_FAILED",
            error_message="fixture",
            failed_at=datetime.now(UTC),
        )
        restarted.resume(game, identifier, "fixture:1121")
        active = claim()
        assert active and active.id == child.id
        worker.complete(active.id, lease_token=active.lease_token, completed_at=datetime.now(UTC))
        parent = claim()
        assert parent and parent.checkpoint_payload["budgetPin"] == "original"
        worker.defer_for_dependency(
            parent.id,
            lease_token=parent.lease_token,
            checkpoint_payload=parent.checkpoint_payload,
            deferred_at=datetime.now(UTC),
        )
        cancelled = restarted.cancel(game, identifier, "fixture:1121")
        assert cancelled["status"] == "cancelled"
        with db.app_engine.connect() as connection:
            assert recording_permission_errors(connection, db.role) == ()
