"""A private game pins its own base across command replay, data preparation and SQL admission."""

import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from _application_role_database import application_role_database
from _private_grid_learning_support import private_frozen_cohort
from game_predictor_api.application.grid_correction_learning import GridCorrectionLearningService
from game_predictor_api.application.grid_learning_preparation import prepare
from game_predictor_api.application.new_game_geometry import NewGameGeometryService
from game_predictor_api.domain.grid_model_registry import (
    canonical_json,
    descriptor_sha256,
    historical_catalogue,
)
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_api.domain.worker_lanes import WorkerLaneName
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.worker_lane_repository import SqlAlchemyWorkerLaneRepository
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_grid_model_publication_and_activation import execute, registry

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Dedicated PostgreSQL fixture required",
)


def test_private_readiness_background_replay_and_child_pins(tmp_path):
    with application_role_database("t1254", ("owned", "other")) as db:
        game, other = db.games.values()
        base, unrelated = historical_catalogue()
        factory = create_session_factory(db.app_engine)
        with db.owner_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.games SET shape_geometry_configuration='neural_grid_v3' "
                    "WHERE id=:game"
                ),
                {"game": game},
            )
        with factory() as session, session.begin():
            control = registry(session, tmp_path)
            execute(control, "publish", base["versionId"])
            execute(control, "publish", unrelated["versionId"])
            execute(control, "activate", base["versionId"], game=game)
            NewGameGeometryService(None, control.repository, control).enable_private_model(
                game_id=game, key=uuid4(), expected_revision=1, actor="fixture:private"
            )
        SqlAlchemyWorkerLaneRepository(factory).register(
            lane=WorkerLaneName.GENERAL,
            instance_token=uuid4(),
            worker_id="test",
            worker_version="test-grid-preparation-v1",
            process_id=1,
            thread_budget=1,
            started_at=datetime.now(UTC),
        )
        service = GridCorrectionLearningService(db.app_engine, factory, tmp_path)
        ready = service.ready(game, lightweight=True)
        assert ready["learningScope"] == "private_game" and ready["gameName"] == "owned"
        assert ready["baseVersionId"] == base["versionId"] and ready["defaultRevision"] is None
        assert ready["targetFamilyId"] != base["familyId"]
        assert (
            ready["trainingMode"] == "screen+grid"
            and ready["weightInitialization"] == "from_scratch"
        )
        blocked = service.preview(
            game, {"learningScope": "private_game", "trainingMode": "grid-only"}
        )
        assert blocked["blockers"] == ["GRID_LEARNING_PRIVATE_SCREEN_REQUIRED"]
        command = {
            "idempotencyKey": str(uuid4()),
            "prepareInBackground": True,
            "preparationOnly": True,
        }
        with pytest.raises(GridCohortError) as rejected:
            service.start(game, command, "test")
        assert rejected.value.code == "GRID_LEARNING_PRIVATE_SCOPE_REQUIRED"
        command["learningScope"] = "private_game"
        queued = service.start(game, command, "test")
        with factory() as session, session.begin():
            execute(registry(session, tmp_path), "set_default", unrelated["versionId"])
        fresh = GridCorrectionLearningService(db.app_engine, factory, tmp_path)
        assert fresh.start(game, command, "test") == queued
        assert queued["weightInitialization"] == "from_scratch"
        assert fresh.ready(game, lightweight=True) == ready
        full = fresh.preview(game, {"learningScope": "private_game"})
        assert full["targetFamilyId"] == ready["targetFamilyId"] and full["requiredGameIds"] == [
            str(game)
        ]
        with factory() as session:
            parent = fresh._job(session, game, UUID(queued["learningId"]))
        pin = parent.input_payload["pins"]["privateLearning"]
        with db.owner_engine.begin() as connection:
            cohort = private_frozen_cohort(connection, pin)

        def run_payload():
            return {
                "schema_version": 1,
                "training_kind": "grid-training-run-v1",
                "private_learning": pin,
                "idempotency_key": str(uuid4()),
                "family_id": pin["targetFamilyId"],
                "base_version_id": pin["baseVersionId"],
                "cohort_id": str(cohort),
                "cohort_manifest_sha256": "c" * 64,
                "mode": "grid-only",
            }

        def insert(payload, primary=game):
            with factory() as session, session.begin():
                return SqlAlchemyJobRepository(session).add_job(
                    create_job(JobType.GRID_TRAINING, game_id=primary, input_payload=payload)
                )

        with pytest.raises(DBAPIError, match="GRID_LEARNING_PRIVATE_SCOPE_REQUIRED"):
            insert({k: v for k, v in run_payload().items() if k != "private_learning"})
        with pytest.raises(DBAPIError, match="GRID_LEARNING_PRIVATE_COHORTS_INVALID"):
            insert({**run_payload(), "cohort_manifest_sha256": "f" * 64})
        payload = run_payload()
        with pytest.raises(
            DBAPIError, match="GRID_SHARED_PRIVATE_GAME|GRID_LEARNING_PRIVATE_COHORTS_INVALID"
        ):
            insert(
                {**payload, "shared_cohorts": [{"game_id": str(other), "cohort_id": str(uuid4())}]}
            )
        # A run is committed only with the original frozen owner/base/manifest.
        assert insert(run_payload()).game_id == game
        with db.owner_engine.begin() as connection:
            independent_cohort = private_frozen_cohort(
                connection, pin, initialization="from_scratch"
            )
        independent = {
            **run_payload(),
            "cohort_id": str(independent_cohort),
            "mode": "screen+grid",
            "preset_id": "screen-grid-corrections-v1",
            "weight_initialization": "from_scratch",
        }
        run = insert(independent)
        assert run.game_id == game
        candidate_id = uuid4()
        descriptor = {
            "versionId": str(candidate_id),
            "familyId": pin["targetFamilyId"],
            "cohortId": str(independent_cohort),
            "baseVersionId": pin["baseVersionId"],
            "provenance": {
                "runId": str(run.id),
                "independentGameId": str(game),
                "weightInitialization": "from_scratch",
            },
        }

        def register_descriptor(document):
            with db.app_engine.begin() as connection:
                connection.execute(
                    text("""INSERT INTO public.grid_model_versions
                        (id,family_id,version,base_version_id,manifest_json,manifest_sha256)
                        VALUES (:version,:family,'independent-test',:base,:doc,:sha)"""),
                    {
                        "version": candidate_id,
                        "family": pin["targetFamilyId"],
                        "base": pin["baseVersionId"],
                        "doc": canonical_json(document),
                        "sha": descriptor_sha256(document),
                    },
                )

        with pytest.raises(DBAPIError, match="GRID_PRIVATE_INITIALIZATION_INVALID"):
            register_descriptor(descriptor)
        with db.owner_engine.begin() as connection:
            connection.execute(
                text("UPDATE public.jobs SET checkpoint_payload=CAST(:seal AS jsonb) WHERE id=:id"),
                {
                    "id": run.id,
                    "seal": canonical_json({"export": {"descriptor": {"payload": descriptor}}}),
                },
            )
        with pytest.raises(DBAPIError, match="GRID_PRIVATE_INITIALIZATION_INVALID"):
            register_descriptor(
                {
                    **descriptor,
                    "provenance": {**descriptor["provenance"], "independentGameId": str(other)},
                }
            )
        register_descriptor(descriptor)
        for overrides in (
            {"weight_initialization": "assigned_weights"},
            {"weight_initialization": None},
            {"mode": "grid-only"},
        ):
            with pytest.raises(DBAPIError, match="GRID_PRIVATE_INITIALIZATION_INVALID"):
                insert({**independent, **overrides})
        with db.owner_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.game_grid_model_assignments SET revision=revision+1, "
                    "version_id=:candidate "
                    "WHERE game_id=:g"
                ),
                {"g": game, "candidate": candidate_id},
            )
        successor = fresh.ready(game, lightweight=True)
        assert successor["weightInitialization"] == "assigned_weights"
        next_pin = {
            **pin,
            "assignmentRevision": successor["assignmentRevision"],
            "baseVersionId": str(candidate_id),
            "baseManifestSha256": descriptor_sha256(descriptor),
        }
        with db.owner_engine.begin() as connection:
            next_cohort = private_frozen_cohort(
                connection, next_pin, initialization="assigned_weights"
            )
        next_run = {
            **run_payload(),
            "private_learning": next_pin,
            "base_version_id": str(candidate_id),
            "cohort_id": str(next_cohort),
            "weight_initialization": "assigned_weights",
        }
        assert insert(next_run).game_id == game
        with pytest.raises(DBAPIError, match="GRID_LEARNING_PRIVATE_ASSIGNMENT_CHANGED"):
            insert(run_payload())
        with pytest.raises(GridCohortError) as changed, prepare(fresh, parent):
            pytest.fail("Changed assignment must block before writing prepared data.")
        assert changed.value.code == "GRID_LEARNING_PRIVATE_ASSIGNMENT_CHANGED"
