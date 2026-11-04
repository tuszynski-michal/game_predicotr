"""Real guarded synthetic GT, split, parent, cohort freeze and child bindings; no NN."""

import faulthandler
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.application import grid_correction_learning as learning
from game_predictor_api.application import grid_model_evaluation as evaluation_module
from game_predictor_api.domain.grid_model_registry import descriptor_sha256
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_model_registry import SqlAlchemyGridModelRegistryRepository
from game_predictor_api.storage.grid_training_cohort_models import GridTrainingCohortModel
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository, job_from_record
from game_predictor_api.storage.models import JobModel
from sqlalchemy import event, text
from sqlalchemy.orm import Session
from test_grid_training_cohort_e2e_postgres import _install_base, _save_source
from test_v3_engine_acceptance_postgres import current_partition_budget  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit disposable PostgreSQL only",
)


def test_v4_preview_parent_freeze_training_evaluation_bind_exact_purposes(tmp_path, monkeypatch):
    start = time.monotonic()

    def stage(name):
        print(f"v4 +{time.monotonic() - start:.2f}s: {name}", flush=True)

    with application_role_database("t1159v4", ("v4-parent",)) as db:

        @event.listens_for(db.app_engine, "connect")
        def bounded_reads(connection, _record):
            with connection.cursor() as cursor:
                cursor.execute("SET statement_timeout='10s'")
                cursor.execute("SET lock_timeout='5s'")
            connection.commit()

        game = next(iter(db.games.values()))
        base, family = _install_base(db, game)
        factory = create_session_factory(db.app_engine)
        from game_predictor_api.storage.models import SymbolModel

        with Session(db.owner_engine) as session, session.begin():
            session.add(
                SymbolModel(
                    game_id=game,
                    code="FIXTURE",
                    name="Fixture",
                    mobile_code=1,
                    display_order=1,
                    status="active",
                )
            )
        stage("database ready")
        sources, imports = [], []
        expected = {}
        for index in range(21):
            source, _, job = _save_source(
                db, tmp_path, game, index + 1, 3 if index >= 15 else 9, expected
            )
            sources.append(source)
            imports.append(str(job))
            if index % 5 == 4:
                stage(f"guarded human photos {index + 1}/21")
        with Session(db.owner_engine) as session, session.begin():
            session.execute(
                text(
                    "INSERT INTO public.grid_model_default(id,version_id,revision) "
                    "VALUES('geometry-v3',:v,1)"
                ),
                {"v": base},
            )
        with Session(db.app_engine) as session:
            manifest = json.loads(
                SqlAlchemyGridModelRegistryRepository(session).version(base).manifest_json
            )
        # Only the unavailable trained-model backend is controlled. All human GT,
        # population/registry reads, split, prepare, capture, materialization, freeze,
        # run admission and evaluation cohort binding below remain production code.
        manifest["trainingArtifacts"] = [
            {"name": name, "sha256": "a" * 64}
            for name in ("weights.pt", "checkpoint.pt", "bundle.json", "preset.json")
        ]
        monkeypatch.setattr(
            learning.GridModelRegistryService,
            "view",
            lambda *args, **kwargs: {
                "available": True,
                "manifest": manifest,
                "manifestSha256": descriptor_sha256(manifest),
            },
        )
        monkeypatch.setattr(
            learning,
            "verified_history",
            lambda *args: {"documented": True, "gameIds": [str(game)], "cohorts": []},
        )
        service = learning.GridCorrectionLearningService(db.app_engine, factory, tmp_path)
        command = {
            "trainingMode": "screen+grid",
            "policyVersion": "application-grid-corrections-v4",
            "validationAssignments": {str(source): "B" for source in sources[20:]},
            "importJobIds": imports,
            "historicalCohorts": [],
            "exclusions": [],
        }
        with db.owner_engine.connect() as connection:
            before = connection.scalar(text("SELECT count(*) FROM public.recording_photo_uses"))
        preview, pins = service._preview(game, command)
        assert preview["canStart"], preview["blockers"]
        assert preview["validationPurposeCounts"]["B"]["boards"] == 3
        assert preview["roleCounts"][1] == {"role": "VALIDATION", "photos": 5, "boards": 45}
        assert pins["selectionInput"]["policy"] == "validation-purpose-a-v1"
        assert not (
            {str(source) for source in sources[20:]}
            & {s["sourceId"] for g in pins["selectionInput"]["games"] for s in g["sources"]}
        )
        with db.owner_engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT count(*) FROM public.recording_photo_uses"))
                == before
            )
        stage("real readonly preview ready")
        request = {
            **command,
            "idempotencyKey": str(uuid4()),
            "previewSha256": preview["previewSha256"],
        }
        started = service.start(game, request, "fixture-human:1159")
        identifier = UUID(started["learningId"])
        fresh = learning.GridCorrectionLearningService(db.app_engine, factory, tmp_path)
        # Exact replay reads the stored command/pins before any current requalification.
        with monkeypatch.context() as patch:
            patch.setattr(
                fresh, "_preview", lambda *args: pytest.fail("retry must not refresh pins")
            )
            assert fresh.start(game, request, "fixture-human:1159") == started
            with pytest.raises(GridCohortError):
                fresh.start(game, {**request, "validationAssignments": {}}, "fixture-human:1159")
        with factory() as session:
            original = job_from_record(session.get(JobModel, identifier))
        assert original.input_payload["pins"] == pins
        assert original.input_payload["preview"]["policyVersion"] == command["policyVersion"]
        state = {}
        for _ in range(20):
            state, done = fresh.advance(
                replace(original, checkpoint_payload={"schema_version": 1, **state})
            )
            with game_storage_scope(game), factory() as session:
                row = session.get(GridTrainingCohortModel, (game, UUID(state["cohortId"])))
                if row.status == "frozen":
                    frozen_sha = row.manifest_sha256
                    assert row.document["policyVersion"] == pins["policyVersion"]
                    assert (
                        row.document["photoSplit"]["validationAssignments"]
                        == command["validationAssignments"]
                    )
                    break
        else:
            pytest.fail("bounded parent did not freeze its cohort")
        stage("real cohort frozen")
        state, done = fresh.advance(
            replace(original, checkpoint_payload={"schema_version": 1, **state})
        )
        run_id = UUID(state["trainingRunId"])
        with factory() as session:
            run = session.get(JobModel, run_id)
            assert run.input_payload["cohort_manifest_sha256"] == frozen_sha
            assert (
                run.input_payload["rescue_recipe"]["selectionInputSha256"]
                == pins["selectionInput"]["sha256"]
            )
            assert run.input_payload["mode"] == "screen+grid"
            planned_steps = run.input_payload["planned_steps"]
        stage("real training admission ready")
        # No trainer executes. Substitute its completed candidate result, then let
        # the real evaluation create path verify the exact frozen cohort and SHA.
        candidate = uuid4()
        with Session(db.owner_engine) as session, session.begin():
            session.execute(
                text(
                    "INSERT INTO public.grid_model_versions(id,family_id,version,base_version_id,"
                    "manifest_json,manifest_sha256) "
                    "VALUES(:v,:f,'synthetic-v4-output',:b,'{}',:s)"
                ),
                {"v": candidate, "f": family, "b": base, "s": "b" * 64},
            )
        with factory() as session, session.begin():
            run = session.get(JobModel, run_id)
            run.status = "completed"
            run.checkpoint_payload = {
                "schema_version": 1,
                "registered": {"versionId": str(candidate)},
            }
        candidate_manifest = {
            "versionId": str(candidate),
            "baseVersionId": str(base),
            "familyId": str(family),
            "cohortId": state["cohortId"],
            "provenance": {"runId": str(run_id)},
            "managedDirectory": "synthetic-v4-output",
        }
        output = tmp_path / "synthetic-v4-output"
        output.mkdir()
        checkpoint = {
            "rule": "validation-photo-board-correct-photo-macro-error-earliest-v1",
            "role": "VALIDATION",
            "step": 1,
            "metrics": {"boardCorrectRate": 0.8, "normalizedError": 0.02, "photoCorrectRate": 0.7},
            "earlyStopping": {"patience": 3, "evaluationsWithoutImprovement": 0, "stopped": False},
            "selectionInputSha256": pins["selectionInput"]["sha256"],
            "metricStateVersion": "photo-board-checkpoint-state-v1",
        }
        (output / "bundle.json").write_text(
            json.dumps({"provenance": {"checkpointSelection": checkpoint}})
        )
        monkeypatch.setattr(
            fresh.evaluations, "_candidate", lambda *args: (candidate_manifest, "b" * 64)
        )
        monkeypatch.setattr(evaluation_module, "candidate_parity", lambda *args: {"passed": True})
        from game_predictor_api.application import grid_correction_history

        monkeypatch.setattr(
            grid_correction_history,
            "verified_history",
            lambda *args: {"documented": True, "gameIds": [str(game)], "cohorts": []},
        )
        stage("enter real evaluation cohort read")

        def dump_waits():
            with db.owner_engine.connect() as connection:
                connection.execute(text("SET statement_timeout='2s'"))
                waits = connection.execute(
                    text(
                        "SELECT pid,wait_event_type,wait_event,"
                        "pg_blocking_pids(pid),left(query,180) "
                        "FROM pg_stat_activity WHERE datname=current_database() "
                        "AND pid<>pg_backend_pid()"
                    )
                ).all()
                locks = connection.execute(
                    text(
                        "SELECT pid,locktype,mode FROM pg_locks WHERE NOT granted AND "
                        "database=(SELECT oid FROM pg_database WHERE datname=current_database())"
                    )
                ).all()
                print(
                    "v4 owned-DB waits",
                    [tuple(row) for row in waits],
                    "ungranted",
                    [tuple(row) for row in locks],
                    flush=True,
                )

        timer = threading.Timer(3, dump_waits)
        timer.start()
        faulthandler.dump_traceback_later(15, repeat=True, file=sys.stdout)
        try:
            state, done = fresh.advance(
                replace(original, checkpoint_payload={"schema_version": 1, **state})
            )
        finally:
            faulthandler.cancel_dump_traceback_later()
            timer.cancel()
            timer.join(timeout=3)
        with factory() as session:
            child = SqlAlchemyJobRepository(session).get_job(UUID(state["evaluationId"]))
            assert child.input_payload["cohorts"][0]["manifest_sha256"] == frozen_sha
            assert child.input_payload["cohorts"][0]["cohort_id"] == state["cohortId"]
        stage("training and evaluation exact frozen bindings ready")
        with monkeypatch.context() as patch:
            patch.setattr(
                fresh,
                "_preview",
                lambda *args: pytest.fail("cold lost reply must not resolve new pins"),
            )
            patch.setattr(
                fresh.evaluations,
                "_candidate",
                lambda *args: pytest.fail("evaluation replay must not reload candidate"),
            )
            assert fresh.start(game, request, "fixture-human:1159") == started
            replay, _ = fresh.advance(
                replace(original, checkpoint_payload={"schema_version": 1, **state})
            )
            assert (
                replay["trainingRunId"] == state["trainingRunId"]
                and replay["evaluationId"] == state["evaluationId"]
            )
        cold = _fresh_read(db, game, identifier, UUID(state["cohortId"]), run_id)
        assert cold["policyVersion"] == command["policyVersion"]
        assert cold["trainingMode"] == command["trainingMode"]
        assert cold["validationAssignments"] == command["validationAssignments"]
        assert cold["pinSha256"] == descriptor_sha256(pins)
        assert cold["manifestSha256"] == cold["runManifestSha256"] == frozen_sha
        assert cold["parentCount"] == cold["trainingCount"] == cold["evaluationCount"] == 1
        assert cold["plannedSteps"] == planned_steps
        stage("fresh-process exact pins/manifest/count/budget replay ready")


def _fresh_read(db, game, parent, cohort, run):
    code = Path(__file__).with_name("_grid_learning_v4_cold_reader.py")
    payload = {
        "url": db.app_engine.url.render_as_string(hide_password=False),
        "game": str(game),
        "parent": str(parent),
        "cohort": str(cohort),
        "run": str(run),
        "evaluationKey": str(learning.child_key(parent, "evaluation")),
    }
    result = subprocess.run(
        [sys.executable, str(code)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=20,
        check=True,
    )
    return json.loads(result.stdout)
