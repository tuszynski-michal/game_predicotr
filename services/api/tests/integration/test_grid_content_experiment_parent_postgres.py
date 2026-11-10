"""Owned real SQL parent/child protocol; no trainer, model inference or operator data."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.application import grid_correction_learning as learning
from game_predictor_api.domain.grid_content_experiment_inputs import require_inputs
from game_predictor_api.domain.grid_model_registry import descriptor_sha256
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_cell_content import SqlAlchemyGridCellContentRepository
from game_predictor_api.storage.grid_model_registry import SqlAlchemyGridModelRegistryRepository
from game_predictor_api.storage.job_repository import job_from_record
from game_predictor_api.storage.models import JobModel, SymbolModel
from game_predictor_worker.images.grid_cohort_dataset import GridCohortSnapshot
from game_predictor_worker.images.grid_content_experiment_data import verify_inputs
from game_predictor_worker.training_core.grid_content_experiment import require_plan
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from test_grid_content_cohort_reference_pipeline import (
    ACTOR,
    ContentSessionAdvance,
    ContentSessionCreate,
    ContentSessionTargetSelection,
    _cells,
    _freeze,
    _measured_nodes,
    _write_manual,
)
from test_grid_training_cohort_e2e_postgres import _install_base, _providers, _save_source
from test_v3_engine_acceptance_postgres import current_partition_budget  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1", reason="Owned disposable PG only"
)


def guarded_engine(url, expected):
    # Both values originate from the owned capability. Never resolve application defaults.
    if not expected or not re.fullmatch(r"game_predictor_t1167parent_[0-9a-f]{12}_test", expected):
        raise ValueError("Expected owned database required")
    parsed = make_url(url) if isinstance(url, str) else url
    if parsed.database != expected:
        raise ValueError("Explicit application database differs from owned capability")
    engine = create_engine(parsed, connect_args={"connect_timeout": 5})

    @event.listens_for(engine, "connect")
    def guard(connection, _record):
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            if cursor.fetchone()[0] != expected:
                raise ValueError("Connected database differs from owned capability")
            cursor.execute("SET statement_timeout='10s'")
            cursor.execute("SET lock_timeout='5s'")
        connection.commit()

    return engine


@contextmanager
def owned_database():
    with application_role_database("t1167parent", ("content-parent",)) as owned:
        expected = owned.owner_url.database
        Path("artifacts/TASK-1167-parent-owned.json").write_text(
            json.dumps({"database": expected, "role": owned.role}), encoding="utf-8"
        )
        owner, app = (
            guarded_engine(owned.owner_url, expected),
            guarded_engine(owned.app_url, expected),
        )
        try:
            yield replace(owned, owner_engine=owner, app_engine=app)
        finally:
            app.dispose()
            owner.dispose()


REPLAY = r"""
import json, os, re
from uuid import UUID
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
url, expected = os.environ['TEST_DATABASE_URL'], os.environ['TEST_DATABASE_NAME']
assert re.fullmatch(r'game_predictor_t1167parent_[0-9a-f]{12}_test', expected)
assert make_url(url).database == expected
engine = create_engine(url, connect_args={'connect_timeout':5})
with engine.connect() as connection:
    assert connection.scalar(text('SELECT current_database()')) == expected
    connection.execute(text("SET statement_timeout='10s'"))
from game_predictor_api.application.grid_correction_learning import GridCorrectionLearningService
from game_predictor_api.storage.database import create_session_factory
from pathlib import Path
service = GridCorrectionLearningService(
    engine,create_session_factory(engine),Path(os.environ['TEST_ROOT']),
    provider_index_sha256=os.environ['TEST_PROVIDER'])
request=json.loads(os.environ['TEST_REQUEST'])
actual=service.start(UUID(os.environ['TEST_GAME']),request,'local-owner')
assert actual['learningId']==os.environ['TEST_PARENT']
engine.dispose()
print('Fresh process exact command replay PASS')
"""


@pytest.mark.parametrize("render_policy", [None, "active-symbol-render-v2"])
def test_real_parent_freezes_content_inputs_and_one_durable_experiment_child(
    tmp_path, monkeypatch, render_policy
):
    if os.environ.get("TASK1167_RETAIN_SETUP") != "1":
        pytest.skip("Explicit two-command setup; phase two exercises the parent protocol")
    started = time.monotonic()

    def stage(message):
        print(f"T1167 +{time.monotonic() - started:.2f}s {message}", flush=True)

    with owned_database() as db:
        stage("owned database migrated")
        game = next(iter(db.games.values()))
        base, family = _install_base(db, game)
        providers = _providers(db, tmp_path, base)
        factory = create_session_factory(db.app_engine)
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
            session.execute(
                text(
                    "INSERT INTO public.grid_model_default(id,version_id,revision) "
                    "VALUES('geometry-v3',:v,1)"
                ),
                {"v": base},
            )
        expected, sources, imports = {}, [], []
        for ordinal in range(1, 22):
            source, _, job = _save_source(
                db, tmp_path, game, ordinal, 9 if ordinal <= 15 else 3, expected
            )
            sources.append(source)
            imports.append(str(job))
            if ordinal % 5 == 0:
                stage(f"guarded photos {ordinal}/21")
        assignments = {**{str(source): "A" for source in sources[10:15]}, str(sources[-1]): "B"}
        legacy_command = dict(
            idempotencyKey=str(uuid4()),
            mode="screen+grid",
            familyId=str(family),
            baseVersionId=str(base),
            selector={"importJobIds": list(imports)},
            recordings=[],
            policyVersion="application-grid-corrections-v4",
            validationAssignments=assignments,
        )
        cohort, snapshot = _freeze(
            factory, tmp_path, game, legacy_command, providers.index_sha256, stage
        )
        selections = [
            ContentSessionTargetSelection(
                sourceId=source, positionIndices=list(range(9 if index >= 5 else 3))
            )
            for index, source in enumerate(sources[:5] + sources[10:15])
        ]
        if render_policy is not None:
            from _grid_render_lab_fixture import install_active_lab

            install_active_lab(db, tmp_path, game, factory, monkeypatch)
            stage("real LAB registry activation; old source import8 retained")
            abandoned_command = ContentSessionCreate(
                idempotencyKey=uuid4(),
                cohortId=cohort,
                expectedManifestSha256=snapshot.manifest_sha256,
                sourceIds=[s.sourceId for s in selections],
                targetSelection=selections,
            )
            with game_storage_scope(game), factory.begin() as session:
                abandoned = SqlAlchemyGridCellContentRepository(session, tmp_path).create_session(
                    game, abandoned_command, ACTOR
                )
            replay_script = r"""
import json, sys
from pathlib import Path
from uuid import UUID
from sqlalchemy import create_engine
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.grid_cell_content import SqlAlchemyGridCellContentRepository
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage import grid_content_oracle_context as oracle
from game_predictor_api.schemas.grid_cell_content import ContentSessionCreate
data=json.load(sys.stdin)
def changed_active(*args, **kwargs):
    raise AssertionError("replay tried to resolve changed active model")
oracle.resolve_evaluation_contract=changed_active
engine=create_engine(data['url'], connect_args={'connect_timeout':5})
try:
    game=UUID(data['game'])
    with game_storage_scope(game), create_session_factory(engine).begin() as session:
        result=SqlAlchemyGridCellContentRepository(session,Path(data['root'])).create_session(
            game, ContentSessionCreate.model_validate(data['body']), 'local-owner')
        assert result==data['expected']
    print('legacy create receipt cold replay PASS')
finally:
    engine.dispose()
"""
            cold = subprocess.run(
                [sys.executable, "-c", replay_script],
                input=json.dumps(
                    {
                        "url": db.app_url.render_as_string(hide_password=False),
                        "game": str(game),
                        "root": str(tmp_path),
                        "body": abandoned_command.model_dump(
                            mode="json", exclude={"renderReferencePolicy"}
                        ),
                        "expected": abandoned,
                    }
                ),
                capture_output=True,
                text=True,
                timeout=20,
                env=db.subprocess_environment(),
            )
            assert cold.returncode == 0, cold.stdout + cold.stderr
            stage("legacy create receipt replay in new process; abandoned pass1 retained")
        with game_storage_scope(game), factory.begin() as session:
            measured = SqlAlchemyGridCellContentRepository(session, tmp_path).create_session(
                game,
                ContentSessionCreate(
                    idempotencyKey=uuid4(),
                    cohortId=cohort,
                    expectedManifestSha256=snapshot.manifest_sha256,
                    sourceIds=[s.sourceId for s in selections],
                    targetSelection=selections,
                    renderReferencePolicy=render_policy,
                ),
                ACTOR,
            )["session"]
        identifier = UUID(measured["sessionId"])
        # Synthetic prior labels, not a replay or claim of the operator's blind protocol.
        # Real DTOs, immutable append storage, raster oracle and final u/delta reader apply.
        from datetime import UTC, datetime

        from game_predictor_api.domain.grid_cell_content import ContentRevision, ContentTarget
        from game_predictor_api.domain.grid_visibility_contract import BoardContentReference
        from game_predictor_worker.images.grid_cell_content_reference import (
            run_blind_content_oracle,
        )

        frames = {
            s["sourceId"]: snapshot.frame(s, s["role"], validation_purpose="A")
            for s in snapshot.sources()
            if s["sourceId"] in {str(t.sourceId) for t in selections}
        }
        for number, shift in ((1, 0.5), (2, 0.75)):
            with game_storage_scope(game), factory.begin() as session:
                repo = SqlAlchemyGridCellContentRepository(session, tmp_path)
                repo.bind(game, write=True)
                row = repo.measurement(game, identifier, lock=True)
                progress = {}
                for raw in row.document["targets"]:
                    target = ContentTarget.model_validate(raw)
                    now = datetime.now(UTC)
                    annotation = ContentRevision(
                        source=target.source,
                        reference=BoardContentReference(
                            gameId=game,
                            sourceRepresentativeSha256=target.source.sourceRepresentativeSha256,
                            positionIndex=target.positionIndex,
                            revision=number,
                            humanApproved=True,
                            cells=_cells(target.positionIndex, shift),
                        ),
                        sequenceNumber=target.sequenceNumber,
                        origin="manual_blind",
                        actor=ACTOR,
                        approvedBy=ACTOR,
                        approvedAt=now,
                        recordedAt=now,
                        sessionId=identifier,
                        passNumber=number,
                        measuredNodes=_measured_nodes(target.positionIndex, shift),
                    )
                    key = f"{target.source.sourceRepresentativeSha256}:{target.positionIndex}"
                    oracle = (
                        None
                        if number == 1
                        else run_blind_content_oracle(
                            frames[str(target.source.sourceId)],
                            annotation,
                            row.document["oracleContexts"][key],
                        )
                    )
                    repo.append(annotation, oracle=oracle)
                    progress[key] = number
                row.progress = {**row.progress, row.phase: progress}
                row.revision += 1
                session.flush()
                revision = row.revision
            with game_storage_scope(game), factory.begin() as session:
                measured = SqlAlchemyGridCellContentRepository(session, tmp_path).advance(
                    game,
                    identifier,
                    ContentSessionAdvance(idempotencyKey=uuid4(), expectedSessionRevision=revision),
                    ACTOR,
                )["session"]
            stage(f"synthetic prior pass {number}; real repeatability reader")
        assert measured["report"]["qualificationState"] == "ready"
        if render_policy is not None:
            assert (
                measured["report"]["evaluationContract"]["renderConfiguration"]["paddingFraction"]
                == 0
            )
        for ordinal in range(22, 27):
            source, _, job = _save_source(db, tmp_path, game, ordinal, 9, expected)
            imports.append(str(job))
            _write_manual(factory, tmp_path, game, source, expected)
        _write_manual(factory, tmp_path, game, sources[-1], expected, slots=3)
        stage("fresh REG labels ready")
        if os.environ.get("TASK1167_RETAIN_SETUP") == "1":
            # Explicit two-command harness. Preserve only this disposable resource;
            # cleanup uses the capability's exact OID/marker journal in a fresh process.
            # No operator/maintenance credential is written to the private handoff.
            private = (Path.cwd() / ".tmp" / "TASK1167-private-app.json").resolve()
            private.write_text(
                json.dumps(
                    {
                        "applicationUrl": db.app_url.render_as_string(hide_password=False),
                        "artifactRoot": str(tmp_path.resolve()),
                    }
                ),
                encoding="utf-8",
            )
            db.app_engine.dispose()
            db.owner_engine.dispose()
            stage(
                "SETUP COMPLETE; explicitly retained owned fixture for phase two (not suite PASS)"
            )
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(0)  # Deliberate retained capability; documented --cleanup is mandatory.


def _exercise_parent(
    db, tmp_path, monkeypatch, factory, game, base, provider_sha, assignments, imports, stage
):
    import faulthandler

    faulthandler.dump_traceback_later(20, repeat=True)
    try:
        with Session(db.app_engine) as session:
            manifest = json.loads(
                SqlAlchemyGridModelRegistryRepository(session).version(base).manifest_json
            )
        # No model files/trainer are exercised: only artifact availability and declared
        # historical game scope are substituted. Descriptor, lineage, source admission,
        # proof reader, prepare/capture/materialize/freeze and job protocol remain real.
        monkeypatch.setattr(
            learning.GridModelRegistryService,
            "view",
            lambda *a, **k: {
                "available": True,
                "manifest": manifest,
                "manifestSha256": descriptor_sha256(manifest),
            },
        )
        monkeypatch.setattr(
            learning,
            "verified_publication_scope",
            lambda *a: {"documented": True, "gameIds": [str(game)], "cohorts": []},
        )
        service = learning.GridCorrectionLearningService(
            db.app_engine, factory, tmp_path, provider_index_sha256=provider_sha
        )
        command = dict(
            trainingMode="screen+grid",
            policyVersion="application-grid-corrections-v4",
            validationAssignments=assignments,
            importJobIds=imports,
            historicalCohorts=[],
            exclusions=[],
            contentExperiment="full-symbol-content-experiment-v1",
        )
        preview, pins = service._preview(game, command)
        assert preview["canStart"], preview["blockers"]
        assert (
            preview["cost"] is None
            and preview["contentExperimentReadiness"]["state"] == "metadata_ready"
        )
        assert "EXPERIMENT_ARM_FEASIBILITY" in preview["pendingWorkerChecks"]
        request = {
            **command,
            "idempotencyKey": str(uuid4()),
            "previewSha256": preview["previewSha256"],
        }
        parent = service.start(game, request, ACTOR)
        result = subprocess.run(
            [sys.executable, "-c", REPLAY],
            timeout=20,
            capture_output=True,
            text=True,
            env=db.subprocess_environment(
                TEST_DATABASE_URL=db.app_url.render_as_string(hide_password=False),
                TEST_DATABASE_NAME=db.owner_url.database,
                TEST_ROOT=str(tmp_path),
                TEST_GAME=str(game),
                TEST_PROVIDER=provider_sha,
                TEST_REQUEST=json.dumps(request),
                TEST_PARENT=parent["learningId"],
            ),
        )
        assert result.returncode == 0, result.stdout + result.stderr
        stage("fresh-process command replay")
        with factory() as session:
            original = job_from_record(session.get(JobModel, UUID(parent["learningId"])))
        state = {}
        for _ in range(20):
            state, done = service.advance(
                replace(original, checkpoint_payload={"schema_version": 1, **state})
            )
            if "trainingRunId" in state:
                break
        else:
            pytest.fail("bounded parent did not create its child")
        with factory() as session:
            child = job_from_record(session.get(JobModel, UUID(state["trainingRunId"])))
        payload = child.input_payload
        plan, inputs = payload["content_experiment"], payload["content_experiment_inputs"]
        require_plan(plan)
        require_inputs(inputs, plan)
        assert inputs == pins["contentExperimentInputs"]
        assert payload["planned_steps"] == 4800 and payload["seed"] == 20261108
        assert plan["maxSeconds"] == 7200
        from game_predictor_api.storage.grid_training_cohort_models import GridTrainingCohortModel

        with game_storage_scope(game), factory() as session:
            service._cohorts(session).repository.bind(game)
            frozen = session.get(GridTrainingCohortModel, (game, UUID(state["cohortId"])))
            snapshot = GridCohortSnapshot(tmp_path, frozen.manifest_path, frozen.manifest_sha256)
        verify_inputs(plan, inputs, [snapshot])
        selected_contract = (
            snapshot.manifest["photoSplit"].get("contentSampling", {}).get("evaluationContract")
        )
        if selected_contract is not None:
            from game_predictor_worker.images.grid_content_experiment_data import (
                require_render_preflight,
            )

            require_render_preflight([snapshot])
            for source in snapshot.sources():
                if not source.get("used"):
                    continue
                for target in source["targets"]:
                    ref = target["productionContentReference"]
                    assert ref["evaluationContract"] == selected_contract
                    assert ref["sourceContext"]["renderConfiguration"]["paddingFraction"] == 0
                    assert ref["importProvenance"]["renderConfiguration"]["paddingFraction"] == 0.08
                    assert target["render"]["configuration"]["paddingFraction"] == 0.08
            from game_predictor_api.storage.grid_content_training_inventory import (
                training_inventory,
            )

            with game_storage_scope(game), factory() as session:
                report = training_inventory(
                    SqlAlchemyGridCellContentRepository(session, tmp_path),
                    game,
                    UUID(state["cohortId"]),
                    snapshot.manifest_sha256,
                )
                assert report["globalGameCounts"] is False and report["pixelsRead"] is False
                assert report["roles"]["A"]["frozenRenderReferenceBoards"] > 0
            stage("v2 exact render0/import8 and scoped inventory PASS")
        replay, _ = service.advance(
            replace(original, checkpoint_payload={"schema_version": 1, **state})
        )
        assert replay["trainingRunId"] == state["trainingRunId"]
        stage("actual freeze, full proof worker reread and exactly one child PASS")

    finally:
        faulthandler.cancel_dump_traceback_later()


def test_continue_explicit_owned_fixture(monkeypatch):
    if not os.environ.get("TASK1167_PRIVATE_APP_CONFIG"):
        pytest.skip("Only the explicit retained phase-one owned fixture")
    from _grid_render_lab_fixture import configure_lab_fixture

    configure_lab_fixture(monkeypatch)
    import hashlib
    from types import SimpleNamespace

    from game_predictor_api.storage.grid_training_cohort_repository import (
        SqlAlchemyGridTrainingCohortRepository,
    )

    private = Path(os.environ["TASK1167_PRIVATE_APP_CONFIG"]).resolve()
    assert private.is_relative_to((Path.cwd() / ".tmp").resolve())
    configuration = json.loads(private.read_text())
    expected = os.environ["TEST_DATABASE_NAME"]
    app_url = make_url(configuration["applicationUrl"])
    engine = guarded_engine(app_url, expected)
    root = Path(configuration["artifactRoot"])
    assert root.resolve().is_relative_to((Path.cwd() / ".tmp").resolve())
    factory = create_session_factory(engine)
    started = time.monotonic()

    def stage(message):
        print(f"T1167 retained phase +{time.monotonic() - started:.2f}s {message}", flush=True)

    try:
        with factory() as session:
            game = session.scalar(text("SELECT id FROM public.games WHERE code='content-parent'"))
            base = session.scalar(
                text("SELECT version_id FROM public.grid_model_default WHERE id='geometry-v3'")
            )
        with game_storage_scope(game), factory() as session:
            repo = SqlAlchemyGridTrainingCohortRepository(session, root)
            repo.bind(game)
            row = session.execute(
                text(
                    "SELECT document FROM grid_training_cohorts WHERE game_id=:g "
                    "AND status='frozen' ORDER BY created_at LIMIT 1"
                ),
                {"g": game},
            ).scalar_one()
            assignments = row["photoSplit"]["validationAssignments"]
            imports = sorted(
                str(i)
                for i in session.scalars(
                    text("SELECT DISTINCT import_job_id FROM source_images WHERE game_id=:g"),
                    {"g": game},
                )
            )
        assert len(imports) == 26
        provider_sha = hashlib.sha256(
            (root / "data/recording-providers/index.json").read_bytes()
        ).hexdigest()
        db = SimpleNamespace(
            app_engine=engine,
            app_url=app_url,
            owner_url=app_url,
            subprocess_environment=lambda **changes: {**os.environ, **changes},
        )
        _exercise_parent(
            db, root, monkeypatch, factory, game, base, provider_sha, assignments, imports, stage
        )
    finally:
        engine.dispose()


@pytest.mark.parametrize("missing", ["TEST_DATABASE_URL", "TEST_DATABASE_NAME"])
def test_fresh_process_refuses_missing_explicit_database_before_engine(missing):
    env = {
        k: v for k, v in os.environ.items() if k not in {"TEST_DATABASE_URL", "TEST_DATABASE_NAME"}
    }
    env[
        {"TEST_DATABASE_URL": "TEST_DATABASE_NAME", "TEST_DATABASE_NAME": "TEST_DATABASE_URL"}[
            missing
        ]
    ] = "invalid"
    result = subprocess.run(
        [sys.executable, "-c", REPLAY], env=env, timeout=10, capture_output=True, text=True
    )
    assert result.returncode != 0 and "KeyError" in result.stderr
