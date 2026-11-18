"""Controlled evidence boundary; real apply receipts, PostgreSQL and manual geometry.

This does not claim a measured model PASS. Admission/evidence gates have separate
T2/T3 tests; this scenario exercises the write boundary after those gates.
"""

import copy
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from _application_role_database import application_role_database
from _private_grid_learning_support import private_frozen_cohort
from fastapi.testclient import TestClient
from game_predictor_api.application.grid_correction_apply import GridCorrectionApplyService
from game_predictor_api.application.grid_correction_learning import (
    LEARNING_KIND,
    GridCorrectionLearningService,
)
from game_predictor_api.application.grid_model_evaluation import report_id_for
from game_predictor_api.application.new_game_geometry import NewGameGeometryService
from game_predictor_api.domain.full_board_calibration_report import attach_calibration, unqualified
from game_predictor_api.domain.grid_correction_evaluation import CHECKPOINT_RULE, build_report
from game_predictor_api.domain.grid_model_registry import (
    GridModelRegistryError,
    canonical_json,
    descriptor_sha256,
    historical_catalogue,
)
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.jobs import (
    JobExecutionSlot,
    JobStatus,
    JobType,
    complete_job,
    create_job,
    execution_slot_for,
    fail_job,
    start_job,
)
from game_predictor_api.domain.production_cell_evaluation import attach_content
from game_predictor_api.main import create_app
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
    game_storage_scope,
)
from game_predictor_api.storage.grid_model_evaluation_repository import storage_location
from game_predictor_api.storage.grid_model_registry_models import (
    GridModelEvaluationCohortProofModel,
    GridModelEvaluationReportModel,
)
from game_predictor_api.storage.grid_private_learning import assignment_pin
from game_predictor_api.storage.grid_profile_snapshot_resolver import (
    SqlAlchemyGridProfileSnapshotResolver,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import GameModel
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore
from sqlalchemy import event, text
from sqlalchemy.orm import Session, sessionmaker
from test_grid_correction_evaluation import roles
from test_grid_correction_learning_api import HEADERS
from test_grid_model_publication_and_activation import execute, registry, seed_report
from test_grid_model_registry import candidate
from test_grid_training_cohort_e2e_postgres import _save_source
from test_production_cell_evaluation import evidence as content_evidence
from test_production_cell_evaluation import geometry as full_photo_roles

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit disposable PostgreSQL only",
)


def _completed(job):
    if job.status is JobStatus.PROCESSING:
        return complete_job(job, lease_token=job.lease_token)
    token = uuid4()
    running = start_job(
        job,
        worker_version="fixture1123",
        worker_id="no-worker-process",
        lease_token=token,
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=2),
        execution_slot=execution_slot_for(job.job_type),
    )
    return complete_job(running, lease_token=token)


def _manual_snapshot(engine, game):
    result = {}
    with game_storage_scope(game), Session(engine) as session:
        GameStorageRouter().bind(session, game, intent=GameStorageIntent.READ)
        for name in (
            "source_images",
            "image_source_geometry_revisions",
            "recognized_boards",
            "image_board_geometry_revisions",
            "image_board_geometry_review_events",
            "image_review_items",
            "image_symbol_review_cells",
        ):
            # These identifiers are a literal test-owned allowlist, never user input.
            rows = session.execute(
                text("SELECT to_jsonb(t) FROM " + name + " t WHERE game_id=:g"),
                {"g": game},
            ).scalars()
            result[name] = sorted(json.dumps(row, sort_keys=True, default=str) for row in rows)
    return result


def _asset_snapshot(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (root / "data").rglob("*")
        if p.is_file()
    }


def _pin(session, root, game):
    return SqlAlchemyGridProfileSnapshotResolver(session, root).resolve_neural_grid_proposal(
        game_id=game
    )


def _assert_fresh_process(db, root, game, manifest, old_job, new_job, original_pin, *, apply=None):
    program = """
import json, os
from pathlib import Path
from uuid import UUID
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from game_predictor_api.application.grid_correction_apply import GridCorrectionApplyService
from game_predictor_api.storage.grid_profile_snapshot_resolver import (
    SqlAlchemyGridProfileSnapshotResolver,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository

engine = create_engine(os.environ["T1122_TEST_URL"], connect_args={"connect_timeout": 5})
try:
    with Session(engine) as session:
        new = SqlAlchemyGridProfileSnapshotResolver(
            session, Path(os.environ["T1122_ROOT"])
        ).resolve_neural_grid_proposal(game_id=UUID(os.environ["T1122_GAME"]))
        assert new["catalogueManifest"]["versionId"] == os.environ["T1122_VERSION"]
        old = SqlAlchemyJobRepository(session).get_job(UUID(os.environ["T1122_JOB"]))
        assert old.input_payload["neural_grid_proposal"] == json.loads(os.environ["T1122_OLD_PIN"])
        persisted_new = SqlAlchemyJobRepository(session).get_job(UUID(os.environ["T1122_NEW_JOB"]))
        assert persisted_new.input_payload["neural_grid_proposal"] == new
        print("fresh-process-import-pin-preserved-history")
    if os.environ["T1255_APPLY"]:
        with Session(engine) as session:
            pending = SqlAlchemyJobRepository(session).get_job(UUID(os.environ["T1255_APPLY"]))
        assert pending.checkpoint_payload is None
        state, finished = GridCorrectionApplyService(
            engine, sessionmaker(engine), Path(os.environ["T1122_ROOT"])
        ).advance(pending)
        assert finished
        assert [step["status"] for step in state["steps"]] == ["completed", "completed"]
        print("fresh-process-private-apply-receipts-recovered")
finally:
    engine.dispose()
"""
    result = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        timeout=20,
        env=db.subprocess_environment(
            T1122_TEST_URL=db.app_url.render_as_string(hide_password=False),
            T1122_ROOT=str(root),
            T1122_GAME=str(game),
            T1122_VERSION=manifest["versionId"],
            T1122_JOB=str(old_job.id),
            T1122_NEW_JOB=str(new_job.id),
            T1122_OLD_PIN=json.dumps(original_pin),
            T1255_APPLY="" if apply is None else str(apply.id),
        ),
    )
    assert result.returncode == 0, result.stderr
    assert "fresh-process-import-pin-preserved-history" in result.stdout
    if apply is not None:
        assert "fresh-process-private-apply-receipts-recovered" in result.stdout


def _save(factory, job):
    with factory() as session, session.begin():
        return SqlAlchemyJobRepository(session).save_job(job)


def _get(factory, identifier):
    with factory() as session:
        return SqlAlchemyJobRepository(session).get_job(identifier)


def _claim(worker):
    return worker.claim_next(
        worker_id="fixture:1122",
        worker_version="test",
        lease_duration=timedelta(seconds=60),
        claimed_at=datetime.now(UTC),
        allowed_job_types=frozenset(
            {JobType.GRID_CORRECTION_LEARNING, JobType.GRID_MODEL_EVALUATION}
        ),
        execution_slot=JobExecutionSlot.GENERAL,
    )


def _waiting_apply_claim(factory, game, original, worker):
    """Queue-only controlled child: an older apply cannot occupy the slot it needs."""
    child = create_job(
        JobType.GRID_MODEL_EVALUATION,
        game_id=None,
        input_payload={
            "schema_version": 1,
            "evaluation_kind": "grid-assigned-comparison-v1",
            "idempotency_key": str(uuid4()),
        },
    )
    payload = copy.deepcopy(original.input_payload)
    payload["idempotency_key"] = str(uuid4())
    payload["command"]["idempotencyKey"] = payload["idempotency_key"]
    parent = create_job(
        JobType.GRID_CORRECTION_LEARNING,
        game_id=game,
        input_payload=payload,
        created_at=child.created_at - timedelta(seconds=1),
    )
    parent = replace(parent, checkpoint_payload={"waitingForJobId": str(child.id)})
    with factory() as session, session.begin():
        repository = SqlAlchemyJobRepository(session)
        repository.add_job(parent)
        repository.add_job(child)
    claimed = _claim(worker)
    assert claimed.id == child.id
    _save(factory, _completed(claimed))
    resumed = _claim(worker)
    assert resumed.id == parent.id
    _save(factory, _completed(resumed))


def _private_learning_evidence(session, db, root, game, iteration, *, report_variant="raw"):
    """Persist evaluator-owned test evidence at the boundary after model measurement."""
    control = registry(session, root)
    pin = assignment_pin(control.repository, game)
    family = control.repository.private_family(game)
    descriptor = json.loads(family.descriptor_json)
    cohort_sha = "f" * 64
    with db.owner_engine.begin() as connection:
        cohort_id = private_frozen_cohort(connection, pin, manifest_sha=cohort_sha)
    manifest = candidate(root, directory=descriptor["familyCode"], version=f"v{iteration}")
    manifest.update(
        familyId=pin["targetFamilyId"],
        familyCode=descriptor["familyCode"],
        familyLabel=descriptor["familyLabel"],
        baseVersionId=pin["baseVersionId"],
        cohortId=str(cohort_id),
    )
    repository = SqlAlchemyJobRepository(session)
    training = repository.add_job(
        create_job(
            JobType.GRID_TRAINING,
            game_id=game,
            input_payload={
                "schema_version": 1,
                "training_kind": "grid-training-run-v1",
                "private_learning": pin,
                "family_id": pin["targetFamilyId"],
                "base_version_id": pin["baseVersionId"],
                "base_manifest_sha256": pin["baseManifestSha256"],
                "cohort_id": manifest["cohortId"],
                "cohort_manifest_sha256": cohort_sha,
                "mode": "grid-only",
            },
        )
    )
    repository.save_job(_completed(training))
    manifest["provenance"]["runId"] = str(training.id)
    manifest["inferenceManifest"]["runId"] = str(training.id)
    directory = root / manifest["managedDirectory"]
    (directory / "manifest.json").write_text(
        json.dumps(manifest["inferenceManifest"]), encoding="utf-8"
    )
    from game_predictor_api.storage.grid_engine_model_store import receipt_bytes

    receipt_path = directory / "training-base" / "receipt.json"
    receipt = json.loads(receipt_path.read_bytes())["payload"]
    receipt["model"] = manifest["inferenceManifest"]
    receipt_path.write_bytes(receipt_bytes(receipt))
    control.register(uuid4(), manifest)

    game_key = str(game)
    scope = {
        "currentGameId": game_key,
        "trainingGameIds": [game_key],
        "priorVerifiedGameIds": [],
        "priorScopeDocumented": False,
        "exclusions": [],
    }
    cohort = {"gameId": game_key, "cohortId": str(cohort_id), "manifestSha256": cohort_sha}
    measured = build_report(
        manifest=manifest,
        base_manifest_sha256=pin["baseManifestSha256"],
        training_game_id=game_key,
        parity={"passed": True, "bundleSha256": "d" * 64},
        cohorts=[cohort],
        measured={
            game_key: {
                "mode": "grid-only",
                "roles": full_photo_roles() if report_variant == "content" else roles(),
            }
        },
        scope=scope,
        checkpoint_selection={
            "rule": CHECKPOINT_RULE,
            "role": "VALIDATION",
            "step": 10,
            "metrics": {"boardCorrectRate": 0.8, "normalizedError": 0.02},
            "earlyStopping": {"patience": 3, "evaluationsWithoutImprovement": 1, "stopped": False},
        },
    )
    if report_variant == "calibrated":
        measured = attach_calibration(
            measured, [unqualified(game_key, "CALIBRATION_PURPOSE_COHORT_REQUIRED")]
        )
    elif report_variant == "content":
        measured = attach_content(measured, [content_evidence(game_key)])
    assert measured["verdict"] == ("NOT_EVALUABLE" if report_variant == "content" else "PASS")
    evaluation = repository.add_job(
        create_job(
            JobType.GRID_MODEL_EVALUATION,
            game_id=game,
            input_payload={
                "schema_version": 1,
                "evaluation_kind": "grid-correction-evaluation-v1",
                "training_run_id": str(training.id),
                "training_game_id": game_key,
                "version_id": manifest["versionId"],
                "family_id": pin["targetFamilyId"],
                "manifest_sha256": descriptor_sha256(manifest),
                "base_version_id": pin["baseVersionId"],
                "base_manifest_sha256": pin["baseManifestSha256"],
                "private_learning": pin,
                "scope": scope,
                "cohorts": [
                    {
                        "game_id": game_key,
                        "cohort_id": manifest["cohortId"],
                        "manifest_sha256": cohort["manifestSha256"],
                    }
                ],
            },
        )
    )
    repository.save_job(_completed(evaluation))
    report_id = report_id_for(evaluation.id)
    session.add(
        GridModelEvaluationReportModel(
            id=report_id,
            version_id=UUID(manifest["versionId"]),
            producer=measured["producer"],
            report_json=canonical_json(measured),
            report_sha256=descriptor_sha256(measured),
        )
    )
    session.flush()
    session.add(
        GridModelEvaluationCohortProofModel(
            id=uuid4(),
            report_id=report_id,
            game_id=game,
            cohort_id=UUID(cohort["cohortId"]),
            manifest_sha256=cohort["manifestSha256"],
            notice_count=0,
            storage_generation=storage_location(session, game)["generation"],
            bind_receipt_sha256="a" * 64,
            eligibility_sha256="b" * 64,
            actor="fixture:1255",
        )
    )
    learning = repository.add_job(
        replace(
            create_job(
                JobType.GRID_CORRECTION_LEARNING,
                game_id=game,
                input_payload={
                    "schema_version": 1,
                    "learning_kind": LEARNING_KIND,
                    "idempotency_key": str(uuid4()),
                    "preview": {
                        **pin,
                        "learningScope": "private_game",
                        "exclusions": [],
                        "requiredGameIds": [game_key],
                    },
                    "pins": {"privateLearning": pin},
                    "command": {"learningScope": "private_game"},
                    "actor": "fixture:1255",
                },
            ),
            checkpoint_payload={
                "candidateVersionId": manifest["versionId"],
                "evaluationId": str(evaluation.id),
                "reportId": str(report_id),
            },
        )
    )
    repository.save_job(_completed(learning))
    return manifest, learning, report_id


def test_private_http_apply_twice_then_rollback_without_switching_another_game(
    tmp_path, monkeypatch
):
    with application_role_database("t1255apply", ("private-one", "private-two")) as db:
        game, other = db.games.values()
        settings = db.settings(tmp_path)
        root = settings.artifact_root
        baseline, other_default = historical_catalogue()
        admin = "/api/v1/admin"
        owner_endpoint = admin + f"/games/{game}/grid-model-assignment"
        other_endpoint = admin + f"/games/{other}/grid-model-assignment"
        factory = sessionmaker(db.app_engine)
        worker = SqlAlchemyWorkerJobStore(factory)
        with db.owner_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.games SET shape_geometry_configuration='neural_grid_v3' "
                    "WHERE id IN (:game,:other)"
                ),
                {"game": game, "other": other},
            )
        with factory() as session, session.begin():
            control = registry(session, root)
            execute(control, "publish", baseline["versionId"])
            execute(control, "publish", other_default["versionId"])
            execute(control, "set_default", baseline["versionId"])
            for owner in (game, other):
                execute(control, "activate", baseline["versionId"], game=owner)
                NewGameGeometryService(None, control.repository, control).enable_private_model(
                    game_id=owner, key=uuid4(), expected_revision=1, actor="fixture:1255"
                )

        monkeypatch.setattr(
            GridCorrectionApplyService, "_registry", lambda self, s: registry(s, root)
        )

        def registry_dependency():
            with factory() as session, session.begin():
                yield registry(session, root)

        def service():
            return GridCorrectionApplyService(db.app_engine, factory, root)

        def assignment_command(version, revision):
            return {
                "idempotencyKey": str(uuid4()),
                "versionId": version,
                "expectedRevision": revision,
            }

        with ExitStack() as app_resources:
            app = create_app(settings, grid_model_registry_service_dependency=registry_dependency)
            app_resources.callback(app.state.database_engine.dispose)
            client = app_resources.enter_context(TestClient(app, client=("127.0.0.1", 12345)))

            def reject(endpoint, command, code):
                response = client.post(endpoint, json=command, headers=HEADERS)
                assert response.status_code == 409, response.text
                assert response.json()["code"] == code, response.text

            first_version = None
            original_import = None
            original_pin = None
            expected = 2
            for iteration in (1, 2):
                with game_storage_scope(game), factory() as session, session.begin():
                    GameStorageRouter().bind(session, game, intent=GameStorageIntent.WRITE)
                    manifest, learning, report = _private_learning_evidence(
                        session,
                        db,
                        root,
                        game,
                        iteration,
                        report_variant="raw" if iteration == 1 else "calibrated",
                    )
                version = manifest["versionId"]
                path = admin + f"/games/{game}/grid-correction-learning/{learning.id}/apply"

                reject(
                    admin + f"/grid-model-versions/{version}/publish",
                    {
                        "idempotencyKey": str(uuid4()),
                        "expectedRevision": 0,
                        "evaluationId": str(report),
                    },
                    "GRID_MODEL_PRIVATE_APPLY_REQUIRED",
                )
                reject(
                    other_endpoint + "/activate",
                    assignment_command(version, 2),
                    "GRID_MODEL_PRIVATE_SCOPE_CONFLICT",
                )
                reject(
                    owner_endpoint + "/activate",
                    assignment_command(version, expected),
                    "GRID_MODEL_PRIVATE_APPLY_REQUIRED",
                )
                reject(
                    admin + "/grid-model-default",
                    assignment_command(version, 1 if iteration == 1 else 2),
                    "GRID_MODEL_PRIVATE_SCOPE_CONFLICT",
                )
                preview = client.get(path + "/preview").json()
                assert preview["canApply"] and preview["scope"] == "private_game", preview
                assert preview["baseVersionId"] == (first_version or baseline["versionId"])
                other_preview = client.get(
                    path + "/preview", params={"additionalGameIds": str(other)}
                ).json()
                assert other_preview["blockers"] == ["GRID_APPLY_PRIVATE_SCOPE_CONFLICT"]
                if iteration == 1:
                    switch = client.post(
                        admin + "/grid-model-default",
                        json=assignment_command(other_default["versionId"], 1),
                        headers=HEADERS,
                    )
                    assert switch.status_code == 200, switch.text
                    assert client.get(path + "/preview").json() == preview
                old_client = {
                    "idempotencyKey": str(uuid4()),
                    "previewSha256": preview["previewSha256"],
                    "confirmLimitedEvidence": True,
                }
                assert client.post(path, json=old_client, headers=HEADERS).status_code == 422
                body = {**old_client, "scope": "private_game"}
                competing = {**body, "idempotencyKey": str(uuid4())}
                with ThreadPoolExecutor(max_workers=2) as commands:
                    results = [
                        (data, commands.submit(client.post, path, json=data, headers=HEADERS))
                        for data in (body, competing)
                    ]
                    outcomes = [(data, result.result(timeout=15)) for data, result in results]
                assert sorted(response.status_code for _, response in outcomes) == [200, 409]
                blocked = next(response for _, response in outcomes if response.status_code == 409)
                assert blocked.json()["code"] == "GRID_APPLY_BUSY", blocked.text
                winner, accepted = next(
                    (data, response.json())
                    for data, response in outcomes
                    if response.status_code == 200
                )
                assert client.post(path, json=winner, headers=HEADERS).json() == accepted
                job = _claim(worker)
                assert accepted["applyId"] == str(job.id)
                if iteration == 1:
                    # Publishing and assigning must roll back together.
                    def fail_assignment(_conn, _cursor, statement, *_):
                        if statement.startswith(
                            "INSERT INTO public.game_grid_model_assignment_events"
                        ):
                            raise RuntimeError("injected private apply interruption")

                    event.listen(db.app_engine, "before_cursor_execute", fail_assignment)
                    try:
                        with pytest.raises(RuntimeError, match="private apply interruption"):
                            service().advance(job)
                    finally:
                        event.remove(db.app_engine, "before_cursor_execute", fail_assignment)
                    with factory() as session:
                        control = registry(session, root)
                        assert control.repository.publication(UUID(version)) is None
                        assert control.repository.assignment(game)[0].revision == expected

                state, done = service().advance(job)
                assert done and [step["kind"] for step in state["steps"]] == ["publish", "activate"]
                # Lose the worker's acknowledgement, then read and recover from committed receipts.
                observed = client.get(path + f"/{job.id}").json()
                assert [step["status"] for step in observed["steps"]] == ["completed", "completed"]
                if iteration == 1:
                    _save(
                        factory,
                        fail_job(
                            job,
                            lease_token=job.lease_token,
                            error_code="FIXTURE_INTERRUPTED",
                            error_message="Lost apply checkpoint",
                        ),
                    )
                    resumed = client.post(path + f"/{job.id}/resume", headers=HEADERS)
                    assert resumed.status_code == 200, resumed.text
                    assert resumed.json()["status"] == "created"
                    job = _claim(worker)
                    assert str(job.id) == observed["applyId"]
                assert service().advance(job) == (state, True)
                expected += 1
                owner_state = client.get(owner_endpoint).json()
                assert owner_state["gridModelPrivate"] and owner_state["revision"] == expected
                assert owner_state["version"]["ownerGameId"] == str(game)
                assert owner_state["version"]["manifest"]["versionId"] == version
                assert (
                    client.get(other_endpoint).json()["version"]["manifest"]["versionId"]
                    == (baseline["versionId"])
                )
                with factory() as session, session.begin():
                    current_pin = _pin(session, root, game)
                    assert current_pin["catalogueManifest"]["versionId"] == version
                    new_import = _completed(
                        create_job(
                            JobType.IMPORT,
                            game_id=game,
                            input_payload={
                                "schema_version": 2,
                                "import_kind": "image_directory",
                                "neural_grid_proposal": current_pin,
                            },
                        )
                    )
                    SqlAlchemyJobRepository(session).add_job(new_import)
                if iteration == 1:
                    first_version, original_pin, original_import = version, current_pin, new_import
                else:
                    _assert_fresh_process(
                        db,
                        root,
                        game,
                        manifest,
                        original_import,
                        new_import,
                        original_pin,
                        apply=job,
                    )
                _save(factory, _completed(replace(job, checkpoint_payload=state)))

            with game_storage_scope(game), factory() as session, session.begin():
                GameStorageRouter().bind(session, game, intent=GameStorageIntent.WRITE)
                stale_version, stale_learning, _ = _private_learning_evidence(
                    session, db, root, game, 3, report_variant="content"
                )
            stale_path = admin + f"/games/{game}/grid-correction-learning/{stale_learning.id}/apply"
            # The production-content gate still requires its configured comparison base.
            stale = client.get(stale_path + "/preview").json()
            assert not stale["canApply"] and stale["blockers"] == [
                "GRID_MODEL_EVALUATION_REQUIRED"
            ], stale
            reject(
                stale_path,
                {
                    "idempotencyKey": str(uuid4()),
                    "previewSha256": stale["previewSha256"],
                    "scope": "private_game",
                    "confirmLimitedEvidence": True,
                },
                "GRID_MODEL_EVALUATION_REQUIRED",
            )
            with factory() as session:
                assert (
                    registry(session, root).repository.publication(UUID(stale_version["versionId"]))
                    is None
                )

            reject(
                owner_endpoint + "/rollback",
                assignment_command(first_version, expected - 1),
                "GRID_MODEL_REVISION_CONFLICT",
            )
            reject(
                owner_endpoint + "/rollback",
                assignment_command(other_default["versionId"], expected),
                "GRID_MODEL_ROLLBACK_TARGET_INVALID",
            )
            rollback = assignment_command(first_version, expected)
            response = client.post(owner_endpoint + "/rollback", json=rollback, headers=HEADERS)
            assert response.status_code == 200, response.text
            assert (
                client.post(owner_endpoint + "/rollback", json=rollback, headers=HEADERS).json()
                == response.json()
            )
            fallback = client.post(
                owner_endpoint + "/rollback",
                json=assignment_command(baseline["versionId"], expected + 1),
                headers=HEADERS,
            )
            assert fallback.status_code == 200, fallback.text
            other_history = client.get(other_endpoint + "/history").json()
            assert [item["kind"] for item in other_history] == ["private_enable", "activate"]
            assert (
                client.get(admin + "/grid-model-default").json()["version"]["manifest"]["versionId"]
                == other_default["versionId"]
            )
            assert client.get(owner_endpoint).json()["trainingFamilyId"] == manifest["familyId"]


@pytest.mark.parametrize("peer_scope", ["training", "cohort"])
def test_shared_apply_refuses_a_private_peer_through_http_and_database(
    tmp_path, monkeypatch, peer_scope
):
    with application_role_database("t1255shared", ("shared-a", "shared-b")) as db:
        peer, game = db.games.values()
        settings = db.settings(tmp_path)
        root = settings.artifact_root
        baseline = historical_catalogue()[0]
        manifest = candidate(root)
        manifest["cohortId"] = str(uuid4())
        factory = sessionmaker(db.app_engine)
        with db.owner_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.games SET shape_geometry_configuration='neural_grid_v3' "
                    "WHERE id IN (:game,:peer)"
                ),
                {"game": game, "peer": peer},
            )
        with factory() as session, session.begin():
            control = registry(session, root)
            control.register(uuid4(), manifest)
            report_id = seed_report(session, manifest, [game, peer])
            execute(control, "publish", baseline["versionId"])
            execute(control, "set_default", baseline["versionId"])
            for owner in (game, peer):
                execute(control, "activate", baseline["versionId"], game=owner)
            repository = SqlAlchemyJobRepository(session)
            training = create_job(
                JobType.GRID_TRAINING,
                game_id=game,
                input_payload={
                    "schema_version": 1,
                    "training_kind": (
                        "grid-shared-training-run-v1"
                        if peer_scope == "training"
                        else "grid-training-run-v1"
                    ),
                    "shared_cohorts": (
                        [{"game_id": str(peer), "cohort_id": str(uuid4())}]
                        if peer_scope == "training"
                        else []
                    ),
                },
            )
            repository.add_job(training)
            repository.save_job(_completed(training))
            learning = _completed(
                replace(
                    create_job(
                        JobType.GRID_CORRECTION_LEARNING,
                        game_id=game,
                        input_payload={
                            "schema_version": 1,
                            "learning_kind": LEARNING_KIND,
                            "preview": {"baseVersionId": baseline["versionId"], "exclusions": []},
                            "pins": {},
                        },
                    ),
                    checkpoint_payload={
                        "trainingRunId": str(training.id),
                        "candidateVersionId": manifest["versionId"],
                        "evaluationId": str(uuid4()),
                        "reportId": str(report_id),
                    },
                )
            )
            repository.add_job(learning)

        # Keep model measurements controlled. SQL admission, job transitions and HTTP are real.
        report = {
            "scope": {
                "trainingGameIds": (
                    sorted(map(str, (peer, game))) if peer_scope == "training" else [str(game)]
                )
            },
            "cohorts": [{"gameId": str(owner)} for owner in (peer, game)],
            "requiredGameIds": sorted(map(str, (peer, game))),
        }

        def evidence(_self, session, control, game_id, learning_id):
            assert (game_id, learning_id) == (game, learning.id)
            return (
                learning,
                control.control._version(UUID(manifest["versionId"])),
                report,
                session.get(GridModelEvaluationReportModel, report_id),
            )

        monkeypatch.setattr(GridCorrectionApplyService, "_evidence", evidence)
        app = create_app(settings)
        endpoint = f"/api/v1/admin/games/{game}/grid-correction-learning/{learning.id}/apply"
        try:
            with TestClient(app, client=("127.0.0.1", 12345)) as client:
                preview = client.get(endpoint + "/preview").json()
                assert preview["canApply"] and preview["additionalGameIds"] == [], preview
                assert [target["gameId"] for target in preview["targets"]] == [str(game)]
                command = {
                    "idempotencyKey": str(uuid4()),
                    "previewSha256": preview["previewSha256"],
                    "confirmLimitedEvidence": True,
                }
                started = client.post(endpoint, json=command, headers=HEADERS)
                assert started.status_code == 200, started.text
                job = _claim(SqlAlchemyWorkerJobStore(factory))
                assert started.json()["applyId"] == str(job.id)
                with (
                    pytest.raises(
                        GridModelRegistryError, match="GRID_MODEL_PRIVATE_OPERATION_ACTIVE"
                    ),
                    factory() as session,
                    session.begin(),
                ):
                    control = registry(session, root)
                    scoped_games = set(
                        session.scalars(
                            text(
                                "SELECT * FROM public.grid_operation_game_ids(:g,CAST(:p AS jsonb))"
                            ),
                            {"g": game, "p": json.dumps(job.input_payload)},
                        )
                    )
                    assert scoped_games == {game, peer}
                    assert control.repository.active_grid_operation(peer) == job.id
                    NewGameGeometryService(None, control.repository, control).enable_private_model(
                        game_id=peer, key=uuid4(), expected_revision=1, actor="fixture:1255"
                    )
                _save(
                    factory,
                    fail_job(
                        job,
                        lease_token=job.lease_token,
                        error_code="FIXTURE_INTERRUPTED",
                        error_message="Shared apply paused",
                    ),
                )
                with factory() as session, session.begin():
                    control = registry(session, root)
                    NewGameGeometryService(None, control.repository, control).enable_private_model(
                        game_id=peer, key=uuid4(), expected_revision=1, actor="fixture:1255"
                    )

                code = "GRID_APPLY_SHARED_PRIVATE_GAME"
                assert client.get(endpoint + "/preview").json()["blockers"] == [code]
                second = {**command, "idempotencyKey": str(uuid4())}

                def reject_shared_commands():
                    for target, body in (
                        (endpoint, second),
                        (endpoint + f"/{job.id}/resume", None),
                    ):
                        response = client.post(target, json=body, headers=HEADERS)
                        assert response.status_code == 409, response.text
                        assert response.json()["code"] == code

                reject_shared_commands()
                with pytest.raises(GridCohortError) as refusal:
                    GridCorrectionApplyService(db.app_engine, factory, root).advance(job)
                assert refusal.value.code == code
                with monkeypatch.context() as simulated_race:
                    simulated_race.setattr(
                        GridCorrectionApplyService, "_require_shared_scope", lambda *_: None
                    )
                    # SQL sees A as private even if application scope validation had raced.
                    reject_shared_commands()
                assert client.get(endpoint + f"/{job.id}").json()["status"] == "failed"
                with factory() as session:
                    control = registry(session, root)
                    assert control.repository.publication(UUID(manifest["versionId"])) is None
                    assert str(control.repository.default().version_id) == baseline["versionId"]
        finally:
            app.state.database_engine.dispose()


@pytest.mark.parametrize("publication_origin", ["first_apply", "manual", "different_evidence"])
def test_real_apply_republication_recovery_import_and_history(
    tmp_path, monkeypatch, publication_origin
):
    # Expensive model evidence is controlled, but no preview/query/control/queue write is mocked.
    with application_role_database("t1122apply", ("apply-import",)) as db:
        print("1122 disposable database ready: " + publication_origin, flush=True)
        game = next(iter(db.games.values()))
        root = tmp_path / "assets"
        root.mkdir()
        with db.owner_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.games SET shape_geometry_configuration='neural_grid_v3' "
                    "WHERE id=:g"
                ),
                {"g": game},
            )
        expected = {}
        _save_source(db, root, game, 1, 1, expected)
        before_manual, before_assets = _manual_snapshot(db.app_engine, game), _asset_snapshot(root)
        assert (
            before_manual["image_board_geometry_revisions"] and before_assets and len(expected) == 1
        )
        baseline, manifest = historical_catalogue()[0], candidate(root)
        manifest["cohortId"] = str(uuid4())
        factory = sessionmaker(db.app_engine)
        with factory() as session, session.begin():
            control = registry(session, root)
            control.register(uuid4(), manifest)
            report_id = seed_report(session, manifest, [game])
            other_report = seed_report(session, manifest, [game])
            execute(control, "publish", baseline["versionId"])
            execute(control, "set_default", baseline["versionId"])
            execute(control, "activate", baseline["versionId"], game=game)
            original_pin = (
                SqlAlchemyGridProfileSnapshotResolver(session, root)
                ._assigned_snapshot(session.get(GameModel, game))
                .to_payload()
            )
            old_job = _completed(
                create_job(
                    JobType.IMPORT,
                    game_id=game,
                    input_payload={
                        "schema_version": 2,
                        "import_kind": "image_directory",
                        "neural_grid_proposal": original_pin,
                    },
                )
            )
            repository = SqlAlchemyJobRepository(session)
            repository.add_job(old_job)
            initial = {
                "gameId": str(game),
                "baseVersionId": baseline["versionId"],
                "defaultRevision": control.repository.default().revision,
                "previewSha256": "c" * 64,
                "requiredGameIds": [str(game)],
                "exclusions": [],
            }
            learning = _completed(
                replace(
                    create_job(
                        JobType.GRID_CORRECTION_LEARNING,
                        game_id=game,
                        input_payload={
                            "schema_version": 1,
                            "learning_kind": LEARNING_KIND,
                            "idempotency_key": str(uuid4()),
                            "preview": initial,
                            "command": {},
                            "pins": {},
                            "actor": "fixture:1122",
                        },
                    ),
                    checkpoint_payload={
                        "candidateVersionId": manifest["versionId"],
                        "evaluationId": str(uuid4()),
                        "reportId": str(report_id),
                    },
                )
            )
            repository.add_job(learning)
            before_receipts = session.scalar(
                text("SELECT count(*) FROM public.grid_model_control_events")
            )
            before_assignments = session.scalar(
                text(
                    "SELECT count(*) FROM public.game_grid_model_assignment_events WHERE game_id=:g"
                ),
                {"g": game},
            )
        cohort = {"gameId": str(game), "cohortId": manifest["cohortId"], "manifestSha256": "f" * 64}
        controlled_report = {
            "scope": {
                "currentGameId": str(game),
                "trainingGameIds": [str(game)],
                "priorVerifiedGameIds": [],
                "priorScopeDocumented": False,
                "exclusions": [],
            },
            "cohorts": [cohort],
            "requiredGameIds": [str(game)],
            "verdict": "PASS",
        }

        def controlled_evidence(self, session, control, actual_game, actual_learning):
            assert (actual_game, actual_learning) == (game, learning.id)
            return (
                _get(factory, learning.id),
                control.control._version(UUID(manifest["versionId"])),
                copy.deepcopy(controlled_report),
                session.get(GridModelEvaluationReportModel, report_id),
            )

        monkeypatch.setattr(
            GridCorrectionApplyService, "_registry", lambda self, s: registry(s, root)
        )
        monkeypatch.setattr(GridCorrectionApplyService, "_evidence", controlled_evidence)

        def service():
            return GridCorrectionApplyService(db.app_engine, factory, root)

        def command(preview):
            return {
                "idempotencyKey": str(uuid4()),
                "previewSha256": preview["previewSha256"],
                "additionalGameIds": [],
                "confirmLimitedEvidence": True,
            }

        worker = SqlAlchemyWorkerJobStore(factory)
        conflicted_history = None
        if publication_origin == "different_evidence":
            before_publication = service().preview(game, learning.id, [])
            historical = service().start(
                game, learning.id, command(before_publication), "fixture:1122"
            )
            claimed = _claim(worker)
            assert str(claimed.id) == historical["applyId"]
            _save(
                factory,
                fail_job(
                    claimed,
                    lease_token=claimed.lease_token,
                    error_code="COMPARISON_INTERRUPTED",
                    error_message="fixture before publication",
                ),
            )
            conflicted_history = claimed.id
        if publication_origin in {"manual", "different_evidence"}:
            with factory() as session, session.begin():
                execute(
                    registry(session, root),
                    "publish",
                    manifest["versionId"],
                    evaluation=report_id if publication_origin == "manual" else other_report,
                )
        preview = service().preview(game, learning.id, [])
        if publication_origin == "different_evidence":
            assert not preview["canApply"]
            assert "GRID_APPLY_PUBLICATION_EVIDENCE_CONFLICT" in preview["blockers"]
            with pytest.raises(GridCohortError) as error:
                service().start(game, learning.id, command(preview), "fixture:1122")
            assert error.value.code == "GRID_APPLY_PUBLICATION_EVIDENCE_CONFLICT"
            history = service().list(game, learning.id)["items"]
            assert len(history) == 1 and history[0]["applyId"] == str(conflicted_history)
            assert history[0]["status"] == "failed"
            assert history[0]["steps"][0]["status"] == "pending"
            assert service().get(game, learning.id, conflicted_history) == history[0]
            assert _manual_snapshot(db.app_engine, game) == before_manual
            assert _asset_snapshot(root) == before_assets
            return
        assert preview["canApply"], preview
        first_command = command(preview)
        started = service().start(game, learning.id, first_command, "fixture:1122")
        assert service().start(game, learning.id, first_command, "fixture:1122") == started
        identifier = UUID(started["applyId"])
        assert service().get(game, learning.id, identifier) == started
        assert [item["applyId"] for item in service().list(game, learning.id)["items"]] == [
            str(identifier)
        ]
        with pytest.raises(GridCohortError) as busy:
            service().start(game, learning.id, command(preview), "fixture:1122")
        assert busy.value.code == "GRID_APPLY_BUSY"
        assert [
            item["learningId"]
            for item in GridCorrectionLearningService(db.app_engine, factory, root).list(game)[
                "items"
            ]
        ] == [str(learning.id)]
        if publication_origin == "first_apply":
            claimed = _claim(worker)
            assert claimed.id == identifier
            state, finished = service().advance(claimed)
            assert not finished and state["steps"][0]["status"] == "completed"
            assert service().advance(claimed) == (state, finished)
            with factory() as session, session.begin():
                control = registry(session, root)
                execute(
                    control,
                    "set_default",
                    baseline["versionId"],
                    expected=control.repository.default().revision,
                )
            with pytest.raises(GridCohortError) as changed:
                service().advance(replace(claimed, checkpoint_payload=state))
            assert changed.value.code == "GRID_APPLY_DEFAULT_CHANGED"
            # Crash before checkpoint: receipt survives independently of the failed parent.
            _save(
                factory,
                fail_job(
                    claimed,
                    lease_token=claimed.lease_token,
                    error_code="GRID_APPLY_DEFAULT_CHANGED",
                    error_message="fixture",
                ),
            )
            assert service().get(game, learning.id, identifier)["steps"][0]["status"] == "completed"
            fresh = service().preview(game, learning.id, [])
            assert fresh["canApply"] and fresh["previewSha256"] != preview["previewSha256"]
            started = service().start(game, learning.id, command(fresh), "fixture:1122")
            assert started["applyId"] != str(identifier)
            with pytest.raises(GridCohortError) as competing_resume:
                service().resume(game, learning.id, identifier, "fixture:1122")
            assert competing_resume.value.code == "GRID_APPLY_BUSY"
            assert _get(factory, identifier).status is JobStatus.FAILED
            identifier = UUID(started["applyId"])
        for index in range(3):
            job = _get(factory, identifier)
            if job.status is JobStatus.CREATED:
                job = _claim(worker)
                assert job.id == identifier
            state, finished = service().advance(job)
            assert service().advance(job) == (state, finished)
            assert state["steps"][0]["receipt"]["kind"] == "already-published"
            updated = replace(job, checkpoint_payload=state)
            if index == 0:
                _save(
                    factory,
                    fail_job(
                        updated,
                        lease_token=job.lease_token,
                        error_code="FIXTURE_INTERRUPTED",
                        error_message="fixture",
                    ),
                )
                resumed = service().resume(game, learning.id, identifier, "fixture:1122")
                assert resumed["applyId"] == str(identifier) and resumed["status"] == "created"
                assert service().resume(game, learning.id, identifier, "fixture:1122") == resumed
            else:
                _save(factory, _completed(updated) if finished else updated)
            print("1122 recovered apply step " + str(index + 1), flush=True)
        assert finished
        complete = service().get(game, learning.id, identifier)
        assert complete["status"] == "completed"
        assert service().resume(game, learning.id, identifier, "fixture:1122") == complete
        assert "GRID_APPLY_ALREADY_DEFAULT" in service().preview(game, learning.id, [])["blockers"]
        with factory() as session, session.begin():
            assert registry(session, root).repository.default().version_id == UUID(
                manifest["versionId"]
            )
            new_pin = _pin(session, root, game)
            assert new_pin["catalogueManifest"]["versionId"] == manifest["versionId"]
            new_job = create_job(
                JobType.IMPORT,
                game_id=game,
                input_payload={
                    "schema_version": 2,
                    "import_kind": "image_directory",
                    "neural_grid_proposal": new_pin,
                },
            )
            repository = SqlAlchemyJobRepository(session)
            repository.add_job(new_job)
            assert repository.get_job(old_job.id).input_payload == old_job.input_payload
            assert repository.get_job(old_job.id).input_key == old_job.input_key
            assert session.scalar(
                text("SELECT count(*) FROM public.grid_model_control_events")
            ) == (before_receipts + (3 if publication_origin == "first_apply" else 2))
            assert (
                session.scalar(
                    text(
                        "SELECT count(*) FROM public.game_grid_model_assignment_events "
                        "WHERE game_id=:g"
                    ),
                    {"g": game},
                )
                == before_assignments + 1
            )
            assert (
                session.scalar(
                    text("SELECT count(*) FROM public.grid_model_publications WHERE version_id=:v"),
                    {"v": UUID(manifest["versionId"])},
                )
                == 1
            )
        assert _manual_snapshot(db.app_engine, game) == before_manual
        assert _asset_snapshot(root) == before_assets
        _assert_fresh_process(db, root, game, manifest, old_job, new_job, original_pin)
        _waiting_apply_claim(factory, game, _get(factory, identifier), worker)
