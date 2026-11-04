"""Real main dependency: routed qualified read, isolated failure, legacy HTTP replay."""

import os
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from _application_role_database import application_role_database
from fastapi.testclient import TestClient
from game_predictor_api.application.grid_correction_learning import GridCorrectionLearningService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.grid_model_registry import descriptor_sha256
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_api.main import create_app
from game_predictor_api.storage.game_storage_routing import (
    GameStorageRouter,
    current_game_storage_scope,
    game_storage_scope,
)
from game_predictor_api.storage.grid_model_registry_models import GameGridModelAssignmentModel
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import GameModel, JobModel
from sqlalchemy import Engine, event, select, text
from sqlalchemy.orm import Session
from test_calibrated_acceptance_postgres import calibrated_report
from test_grid_correction_learning_api import HEADERS, preview_value
from test_v3_engine_acceptance_postgres import current_partition_budget, execution  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit disposable PostgreSQL only",
)


def test_main_assignment_qualified_routed_projection_isolated_failure_and_legacy_retry(
    tmp_path, monkeypatch
):
    with application_role_database("t1159status", ("catalog",)) as db:
        game, factory, seed, _, _ = execution(
            SimpleNamespace(engine=db.owner_engine),
            tmp_path,
            acceptance_policy="v3-engine-acceptance-v4",
            crop_policy="neural-auto-crop-v2",
            evaluated_game=True,
            calibrated_report=calibrated_report,
        )
        with Session(db.owner_engine) as session, session.begin():
            pin = session.get(JobModel, seed.import_job_id).input_payload[
                "neural_grid_operation_pin"
            ]
            model = UUID(pin["modelVersionId"])
            row = session.get(GameModel, game)
            row.shape_geometry_configuration = "neural_grid_v3"
            row.expected_layout_count = 500000
            session.add(GameGridModelAssignmentModel(game_id=game, version_id=model, revision=1))
            location = session.execute(
                text(
                    "SELECT store_schema,status FROM public.game_storage_locations "
                    "WHERE game_id=:game"
                ),
                {"game": game},
            ).one()
            assert tuple(location) == ("game_data_v2", "active")
        settings = replace(
            ApiSettings.from_environment({}),
            database_url=db.app_url.render_as_string(hide_password=False),
            configured_owner_database_url=db.owner_url.render_as_string(hide_password=False),
            artifact_root=tmp_path,
        )
        app = create_app(settings)  # No service/dependency/reader replacement.
        client = TestClient(app, client=("127.0.0.1", 12345))
        observed_engines = set()
        catalog_sessions = set()
        catalog_commits = []
        cohort_reads = []
        failure = {"enabled": False}

        def connection_seen(connection):
            if connection.engine.url.database == db.app_engine.url.database:
                observed_engines.add(connection.engine)

        def catalog_statement(state):
            if type(state.session) is Session and "grid_model_" in str(state.statement):
                catalog_sessions.add(id(state.session))
                assert GameStorageRouter.bound_game_id(state.session) is None

        def catalog_commit(session):
            if id(session) in catalog_sessions:
                assert GameStorageRouter.bound_game_id(session) is None
                # The HTTP middleware owns an ambient game scope; catalogue
                # sessions must remain unbound even inside that request.
                scope = current_game_storage_scope()
                assert (scope is None or scope.game_id == game) and session.is_active
                catalog_commits.append(id(session))

        def observe_read(connection, cursor, statement, parameters, _context, _many):
            if (
                connection.engine.url.database == db.app_engine.url.database
                and "grid_training_cohorts" in statement.lower()
                and statement.lstrip().upper().startswith("SELECT")
            ):
                cursor.execute(
                    "SELECT current_setting('transaction_read_only'),"
                    "current_setting('game_predictor.game_id',true),current_schema()"
                )
                readonly, owner, schema = cursor.fetchone()
                assert readonly == "on" and owner == str(game) and schema == "game_data_v2"
                cohort_reads.append((readonly, owner, schema))
                if failure["enabled"]:
                    return statement.replace(
                        "grid_training_cohorts", "missing_t1159_projection_table"
                    ), parameters
            return statement, parameters

        event.listen(Engine, "engine_connect", connection_seen)
        event.listen(Session, "do_orm_execute", catalog_statement)
        event.listen(Session, "before_commit", catalog_commit)
        event.listen(Engine, "before_cursor_execute", observe_read, retval=True)
        path = f"/api/v1/admin/games/{game}/grid-model-assignment"
        try:
            positive = client.get(path)
            assert positive.status_code == 200, positive.text
            status = positive.json()["recognitionStatus"]
            assert status["automatic"]["state"] == status["evaluation"]["state"] == "qualified"
            assert (
                status["capabilities"]["boardRows"] == 3
                and status["capabilities"]["boardColumns"] == 5
            )
            assert cohort_reads and catalog_commits  # Real strict frozen reader executed.
            original_version = positive.json()["version"]
            failure["enabled"] = True
            failed = client.get(path)
            assert failed.status_code == 200, failed.text
            assert failed.json()["version"] == original_version
            assert failed.json()["recognitionStatus"]["automatic"] == {
                "state": "unavailable",
                "reasonCodes": ["NEURAL_GRID_STATUS_STORAGE_UNAVAILABLE"],
            }
            assert failed.json()["recognitionStatus"]["capabilities"] is None
            assert client.get("/api/v1/admin/grid-model-versions").status_code == 200
            failure["enabled"] = False
            assert client.get(path).json()["recognitionStatus"]["automatic"]["state"] == "qualified"
            with Session(db.owner_engine) as session, session.begin():
                session.get(GameModel, game).shape_geometry_configuration = None
            missing = client.get(path)
            assert missing.status_code == 200 and missing.json()["version"] == original_version
            assert missing.json()["recognitionStatus"]["automatic"] == {
                "state": "unavailable",
                "reasonCodes": ["GRID_MODEL_FORMAT_UNSUPPORTED"],
            }
            assert client.get("/api/v1/admin/grid-model-versions").status_code == 200
            _legacy_http_retry(client, game, model, factory, monkeypatch)
        finally:
            event.remove(Engine, "engine_connect", connection_seen)
            event.remove(Session, "do_orm_execute", catalog_statement)
            event.remove(Session, "before_commit", catalog_commit)
            event.remove(Engine, "before_cursor_execute", observe_read)
            client.close()
            for engine in observed_engines - {db.app_engine, db.owner_engine}:
                engine.dispose()


def _legacy_http_retry(client, game, model, factory, monkeypatch):
    command = {
        "idempotencyKey": str(uuid4()),
        "previewSha256": "c" * 64,
        "importJobIds": [],
        "exclusions": [],
    }
    preview = {**preview_value(), "gameId": str(game), "baseVersionId": str(model)}
    payload = {
        "schema_version": 1,
        "learning_kind": "grid-correction-learning-v1",
        "idempotency_key": command["idempotencyKey"],
        "command": command,
        "preview": preview,
        "pins": {"defaultRevision": 3, "budgetPin": "pre-T5-budget"},
        "actor": "fixture-human:legacy",
    }
    with game_storage_scope(game), factory.begin() as session:
        saved = SqlAlchemyJobRepository(session).add_job(
            create_job(JobType.GRID_CORRECTION_LEARNING, game_id=game, input_payload=payload)
        )
        original_key = saved.input_key
        before = session.scalar(select(text("count(*)")).select_from(JobModel))
    with monkeypatch.context() as patch:
        patch.setattr(
            GridCorrectionLearningService,
            "_preview",
            lambda *args: pytest.fail("pre-T5 exact HTTP retry must not resolve a new preview"),
        )
        path = f"/api/v1/admin/games/{game}/grid-correction-learning"
        first = client.post(path, json=command, headers=HEADERS)
        second = client.post(path, json=command, headers=HEADERS)
    assert first.status_code == second.status_code == 200, first.text
    assert first.json() == second.json() and first.json()["learningId"] == str(saved.id)
    assert first.json()["previewSha256"] == command["previewSha256"]
    with game_storage_scope(game), factory() as session:
        row = session.get(JobModel, saved.id)
        assert row.input_key == original_key and descriptor_sha256(
            row.input_payload
        ) == descriptor_sha256(payload)
        assert row.input_payload["pins"]["budgetPin"] == "pre-T5-budget"
        assert session.scalar(select(text("count(*)")).select_from(JobModel)) == before
