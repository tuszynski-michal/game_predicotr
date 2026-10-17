"""TASK-1001 acceptance: human correction -> frozen cohort -> GPU run -> per-game evaluation
-> publication -> activation -> a fresh process imports with the activated model.

Real: disposable PostgreSQL with the application role and RLS, the human geometry writers,
recordings, the cohort freeze, the run service, the durable grid-training lane with the real
CUDA trainer, the SQL training store and registry registration, the evaluation service,
handler and SQL store, publication and activation, the import snapshot resolver, the managed
model store and CPU ONNX inference of the activated candidate in a new interpreter.
Stand-ins: the two evaluation engines are deterministic fakes (model quality is not claimed;
TASK-0997 owns the measured gate) and the base weights are fresh, not production weights.
Runs only with ``GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`` and
``GAME_PREDICTOR_GRID_TRAINING_PYTHON`` (CUDA).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import numpy as np
import pytest
from _application_role_database import application_role_database
from _grid_training_e2e_support import base_descriptor
from game_predictor_api.application.grid_model_evaluation import (
    GridModelEvaluationService,
    report_id_for,
)
from game_predictor_api.application.grid_model_registry import GridModelRegistryService
from game_predictor_api.application.grid_training_cohorts import GridTrainingCohortService
from game_predictor_api.application.grid_training_runs import GridTrainingRunService
from game_predictor_api.domain.grid_model_registry import (
    canonical_json,
    descriptor_sha256,
    validate_manifest,
)
from game_predictor_api.domain.jobs import JobExecutionSlot, JobStatus, JobType
from game_predictor_api.security.local_admin import ADMIN_ACTOR
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_engine_model_store import receipt_bytes
from game_predictor_api.storage.grid_model_registry import (
    GridModelArtifactInspector,
    SqlAlchemyGridModelRegistryRepository,
)
from game_predictor_api.storage.grid_training_cohort_repository import (
    SqlAlchemyGridTrainingCohortRepository,
)
from game_predictor_api.storage.grid_training_run_jobs import SqlAlchemyGridTrainingRunJobs
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import SymbolModel
from game_predictor_worker.images.grid_cohort_dataset import GridBoardDataset, GridCohortSnapshot
from game_predictor_worker.images.grid_model_evaluation_handler import (
    GridModelEvaluationJobHandler,
)
from game_predictor_worker.images.grid_model_evaluation_store import SqlGridModelEvaluationStore
from game_predictor_worker.images.grid_training_handler import GridTrainingJobHandler
from game_predictor_worker.images.grid_training_store import SqlGridTrainingStore
from game_predictor_worker.jobs.runtime import JobExecutionResult, LocalJobWorker
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore
from PIL import Image
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_grid_model_evaluation_e2e_postgres import Context, Engine
from test_grid_training_cohort_e2e_postgres import (
    _freeze_body,
    _providers,
    _ready_cohort,
    _recording,
    _recorrect_first,
    _save_source,
    _service,
)
from test_virtual_deferred_resolution_postgres import _factory

PYTHON = os.environ.get("GAME_PREDICTOR_GRID_TRAINING_PYTHON", "")
REPOSITORY = Path(__file__).resolve().parents[4]
pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1" or not PYTHON,
    reason="Needs isolated PostgreSQL and GAME_PREDICTOR_GRID_TRAINING_PYTHON (CUDA).",
)

# A fresh interpreter after the API, worker and evaluation processes are gone: it reads only
# the database and the managed files, exactly as the next import of the game does.
RESTART = r"""
import json, os, sys
from pathlib import Path
from uuid import UUID
import numpy as np
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_engine_model_store import ManagedGridEngineModelStore
from game_predictor_api.storage.grid_profile_snapshot_resolver import (
    SqlAlchemyGridProfileSnapshotResolver,
)
from game_predictor_api.storage.models import GameModel
from game_predictor_worker.geometry_core.proposal_runtime import CPUGridProposalRunner

game, root, photo = UUID(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
engine = create_engine(os.environ["ACCEPTANCE_APP_URL"], poolclass=NullPool)
with game_storage_scope(game), Session(engine) as session:
    resolver = SqlAlchemyGridProfileSnapshotResolver(session, root)
    payload = resolver.resolve_neural_grid_proposal(game_id=game)
    snapshot = resolver._assigned_snapshot(session.get(GameModel, game))
bundle = ManagedGridEngineModelStore(root).require(snapshot.version)
sha = next(item.sha256 for item in snapshot.version.files if item.name == "bundle.json")
rgb = np.ascontiguousarray(np.asarray(Image.open(photo).convert("RGB")))
found = CPUGridProposalRunner(threads=1).run(
    bundle, sha, rgb, heartbeat=lambda: None, max_seconds=90
)
descriptor = json.loads(snapshot.version.catalogue_manifest_json)
assert payload is not None, "the next import pins the activated model"
print(json.dumps({"versionId": descriptor["versionId"], "detections": len(found)}))
"""


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _registered_base(db: Any, game: UUID, root: Path) -> tuple[UUID, UUID, dict[str, Any]]:
    """A registry-compatible base with loadable training weights and inspectable files."""
    descriptor = base_descriptor(root)
    family, version = uuid4(), uuid4()
    descriptor.update(
        familyId=str(family),
        versionId=str(version),
        familyCode="accept_v3_" + family.hex[:12],
        familyLabel="Odbior V3",
    )
    directory = root / descriptor["managedDirectory"]
    training = directory / "training-base"
    weights = (training / "weights.pt").read_bytes()
    preset = (training / "preset.json").read_bytes()
    bundle = json.dumps({"parity": {"passed": True}}).encode()
    trained_bytes = {
        "checkpoint.pt": weights,
        "weights.pt": weights,
        "bundle.json": bundle,
        "preset.json": preset,
    }
    # The base is never executed here: the evaluation engines are fakes.
    served_bytes = {
        "screen.onnx": b"acceptance-base-screen",
        "board.onnx": b"acceptance-base-board",
        "bundle.json": bundle,
        "preset.json": preset,
    }
    for name, content in trained_bytes.items():
        (training / name).write_bytes(content)
    for name, content in served_bytes.items():
        (directory / name).write_bytes(content)
    files = [
        {"name": name, "sizeBytes": len(content), "sha256": _sha(content)}
        for name, content in served_bytes.items()
    ]
    trained = [
        {"name": name, "sizeBytes": len(content), "sha256": _sha(content)}
        for name, content in trained_bytes.items()
    ]
    descriptor["files"], descriptor["trainingArtifacts"] = files, trained
    for target in (descriptor["provenance"], descriptor["inferenceManifest"]):
        target["checkpointSha256"] = trained[0]["sha256"]
        target["weightsSha256"] = trained[1]["sha256"]
    descriptor["inferenceManifest"]["files"] = files
    (directory / "manifest.json").write_text(
        json.dumps(descriptor["inferenceManifest"]), encoding="utf-8"
    )
    identity = {
        "schemaVersion": "grid-engine-training-base-v1",
        "model": descriptor["inferenceManifest"],
        "files": trained,
        "sources": {item["name"]: str((training / item["name"]).resolve()) for item in trained},
    }
    (training / "receipt.json").write_bytes(receipt_bytes(identity))
    manifest = validate_manifest(descriptor)
    with db.owner_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE public.games SET shape_geometry_configuration='neural_grid_v3' WHERE id=:g"
            ),
            {"g": game},
        )
        connection.execute(
            text(
                "INSERT INTO public.grid_model_families(id,code,descriptor_json) "
                "VALUES(:id,:code,:doc)"
            ),
            {
                "id": family,
                "code": descriptor["familyCode"],
                "doc": canonical_json(
                    {
                        key: descriptor[key]
                        for key in ("familyCode", "familyLabel", "topology", "capabilities")
                    }
                ),
            },
        )
        connection.execute(
            text(
                "INSERT INTO public.grid_model_versions"
                "(id,family_id,version,manifest_json,manifest_sha256) "
                "VALUES(:id,:f,:v,:doc,:sha)"
            ),
            {
                "id": version,
                "f": family,
                "v": descriptor["version"],
                "doc": manifest,
                "sha": descriptor_sha256(descriptor),
            },
        )
    return version, family, descriptor


def _runs(session: Session, root: Path) -> GridTrainingRunService:
    return GridTrainingRunService(
        GridTrainingCohortService(SqlAlchemyGridTrainingCohortRepository(session, root), root),
        SqlAlchemyGridTrainingRunJobs(session),
    )


def _control(session: Session, root: Path) -> Any:
    return GridModelRegistryService(
        SqlAlchemyGridModelRegistryRepository(session), GridModelArtifactInspector(root)
    ).control


def test_correction_to_activated_model_survives_restart_and_lost_answers(monkeypatch):
    # A short root: evaluation temp names next to 36-character ids must stay under MAX_PATH.
    evidence = REPOSITORY / "artifacts/audits" / ("T1001_" + uuid4().hex[:12])
    evidence.mkdir(parents=True)
    monkeypatch.setenv("GAME_PREDICTOR_RECORDING_TEST_RESOURCE_ROOT", str(evidence / "resources"))
    started, progress = time.monotonic(), []

    def checkpoint(label: str) -> None:
        progress.append({"phase": label, "elapsedSeconds": round(time.monotonic() - started, 3)})
        (evidence / "progress.json").write_text(json.dumps(progress, indent=2), encoding="utf-8")

    with application_role_database("t1001a", ("accept-v3",)) as db:
        game = next(iter(db.games.values()))
        version, family, base = _registered_base(db, game, evidence)
        with game_storage_scope(game), _factory(db.owner_engine).begin() as session:
            for index, code in enumerate(("CYTRYNA", "WISNIA"), 1):
                session.add(
                    SymbolModel(
                        game_id=game,
                        code=code,
                        name=code,
                        mobile_code=index,
                        display_order=index,
                        status="active",
                    )
                )
        # 1. Human corrections in the application (TASK-0993/1017 writers).
        sources, expected = {}, {}
        for ordinal in range(20):
            role = "TRAIN" if ordinal < 10 else "VALIDATION" if ordinal < 15 else "REGRESSION"
            slots = 1 if ordinal == 0 else 5 if ordinal == 1 else 3 if ordinal < 10 else 9
            source, _identity, job = _save_source(db, evidence, game, ordinal, slots, expected)
            if ordinal == 0:
                _recorrect_first(db, evidence, game, job, source, expected)
            sources.setdefault(role, []).append(source)
        checkpoint("human_corrections_saved")

        # 2. Recordings and roles, then one frozen immutable cohort (TASK-1002/0995).
        providers = _providers(db, evidence, version)
        recordings = [
            _recording(db, evidence, game, values, role, family, version, providers, checkpoint)
            for role, values in sources.items()
        ]
        body = {
            "idempotencyKey": str(uuid4()),
            "familyId": str(family),
            "baseVersionId": str(version),
            "mode": "grid-only",
            "selector": {"sourceIds": [str(s) for values in sources.values() for s in values]},
            "recordings": recordings,
        }
        state, cohort = _ready_cohort(db, evidence, game, body, checkpoint)
        with Session(db.app_engine) as session:
            frozen = _service(session, evidence).command(
                game, cohort, "freeze", _freeze_body(state), "fixture-human:1001-acceptance"
            )
            session.commit()
        assert frozen["cohort"]["status"] == "frozen"
        checkpoint("cohort_frozen")

        # 3. The run service queues one durable run; a lost answer replays the same run.
        with game_storage_scope(game), Session(db.app_engine) as session:
            runs = _runs(session, evidence)
            preview = runs.cohorts.run_preview(game, cohort)
            preset = next(
                item
                for item in preview["presets"]
                if item["presetId"] == preview["selectedPresetId"]
            )
            command = {
                "idempotencyKey": str(uuid4()),
                "cohortId": str(cohort),
                "presetId": preset["presetId"],
                "presetFingerprint": preset["fingerprint"],
            }
            run = runs.create(game, command)
            session.commit()
        with game_storage_scope(game), Session(db.app_engine) as session:
            assert _runs(session, evidence).create(game, command) == run
        checkpoint("run_queued_and_replayed")

        # 4. The grid-training lane trains on the GPU and registers the candidate.
        factory = create_session_factory(db.app_engine)
        sources_path = [REPOSITORY / "services/worker/src", REPOSITORY / "services/api/src"]
        handler = GridTrainingJobHandler(
            SqlGridTrainingStore(factory, db.app_engine, evidence),
            artifact_root=evidence,
            python=Path(PYTHON),
            pythonpath=os.pathsep.join(str(path) for path in sources_path),
            repository_root=REPOSITORY,
            poll_seconds=2.0,
        )
        worker = LocalJobWorker(
            SqlAlchemyWorkerJobStore(factory),
            {JobType.GRID_TRAINING: handler},
            worker_id=f"acceptance-{os.getpid()}",
            worker_version="acceptance",
            execution_slot=JobExecutionSlot.GRID_TRAINING,
            lease_duration=timedelta(seconds=60),
        )
        trained_at = time.monotonic()
        result = worker.run_once()
        training_seconds = round(time.monotonic() - trained_at, 1)
        with game_storage_scope(game), Session(db.app_engine) as session:
            done = SqlAlchemyJobRepository(session).get_job(UUID(run["runId"]))
        assert result is JobExecutionResult.COMPLETED, (done.error_code, done.error_message)
        assert done.status is JobStatus.COMPLETED
        with db.owner_engine.connect() as connection:
            candidate = connection.execute(
                text(
                    "SELECT id, manifest_json FROM public.grid_model_versions "
                    "WHERE base_version_id=:b"
                ),
                {"b": version},
            ).one()
        candidate_id, descriptor = candidate.id, json.loads(candidate.manifest_json)
        assert descriptor["admission"] == "not_evaluated"
        assert descriptor["cohortId"] == str(cohort)
        with game_storage_scope(game), Session(db.app_engine) as session:
            view = _runs(session, evidence).view(
                SqlAlchemyJobRepository(session).get_job(UUID(run["runId"]))
            )
        assert view["candidateVersionId"] == str(candidate_id)
        checkpoint("trained_and_registered")

        # 5. Per-game evaluation of the trained candidate (fake engines, real gate).
        service = GridModelEvaluationService(db.app_engine, factory, evidence)
        evaluation_command = {
            "idempotencyKey": str(uuid4()),
            "versionId": str(candidate_id),
            "cohorts": [{"gameId": str(game), "cohortId": str(cohort)}],
        }
        queued = service.create(evaluation_command)
        assert service.create(evaluation_command) == queued
        with Session(db.app_engine) as session:
            cohorts = _service(session, evidence).repository
            cohorts.bind(game)
            row = cohorts.cohort(game, cohort)
            snapshot = GridCohortSnapshot(evidence, row.manifest_path, row.manifest_sha256)
        labels: dict[str, list[np.ndarray]] = {}
        first_validation, photo = None, evidence / "restart-photo.png"
        for role in ("VALIDATION", "REGRESSION"):
            for source, targets in GridBoardDataset(snapshot, role).indexed():
                rgb = np.ascontiguousarray(snapshot.frame(source, role).rgb)
                key = hashlib.sha256(rgb.tobytes()).hexdigest()
                labels[key] = [nodes for nodes, _ in targets]
                if first_validation is None and role == "VALIDATION":
                    first_validation = key
                    Image.fromarray(rgb).save(photo)
        assert first_validation is not None
        base_name = Path(base["managedDirectory"]).name

        def engine_factory(directory: Path, sha: str) -> Engine:
            is_base = directory.name == base_name
            return Engine(labels, {first_validation: 1} if is_base else {})

        with Session(db.app_engine) as session:
            job = SqlAlchemyJobRepository(session).get_job(UUID(queued["evaluationId"]))
        evaluator = GridModelEvaluationJobHandler(
            SqlGridModelEvaluationStore(factory, db.app_engine, evidence),
            evidence,
            engine_factory=engine_factory,
        )
        with game_storage_scope(game):
            evaluator(Context(job), job)
        report_id = report_id_for(job.id)
        detail = service.get(job.id)
        assert detail["report"]["verdict"] == "PASS"
        assert [item["state"] for item in detail["currentness"]] == ["current"]
        checkpoint("evaluated_pass_with_current_proof")

        # 6. Publication and activation are separate explicit commands; both replay.
        publish_key, activate_key = uuid4(), uuid4()
        with Session(db.app_engine) as session:
            published = _control(session, evidence).execute(
                kind="publish",
                key=publish_key,
                expected_revision=0,
                version_id=candidate_id,
                actor=ADMIN_ACTOR,
                evaluation_id=report_id,
            )
            session.commit()
        with game_storage_scope(game), Session(db.app_engine) as session:
            activated = _control(session, evidence).execute(
                kind="activate",
                key=activate_key,
                expected_revision=0,
                version_id=candidate_id,
                actor=ADMIN_ACTOR,
                game_id=game,
            )
            session.commit()
        with Session(db.app_engine) as session:
            assert (
                _control(session, evidence).execute(
                    kind="publish",
                    key=publish_key,
                    expected_revision=0,
                    version_id=candidate_id,
                    actor=ADMIN_ACTOR,
                    evaluation_id=report_id,
                )
                == published
            )
        with game_storage_scope(game), Session(db.app_engine) as session:
            assert (
                _control(session, evidence).execute(
                    kind="activate",
                    key=activate_key,
                    expected_revision=0,
                    version_id=candidate_id,
                    actor=ADMIN_ACTOR,
                    game_id=game,
                )
                == activated
            )
        checkpoint("published_activated_and_replayed")

        # 7. Restart: a new interpreter resolves the activated version for the next import
        # and runs the trained model on a photo of the game.
        db.app_engine.dispose()
        environment = db.subprocess_environment(
            ACCEPTANCE_APP_URL=db.app_url.render_as_string(hide_password=False)
        )
        completed = subprocess.run(
            [sys.executable, "-c", RESTART, str(game), str(evidence), str(photo)],
            capture_output=True,
            text=True,
            timeout=180,
            env=environment,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr[-4000:]
        restarted = json.loads(completed.stdout.strip().splitlines()[-1])
        assert restarted["versionId"] == str(candidate_id)
        checkpoint("restart_uses_activated_model")
        (evidence / "result.json").write_text(
            json.dumps(
                {
                    "trainingSeconds": training_seconds,
                    "plannedSteps": run.get("plannedSteps"),
                    "candidateVersionId": str(candidate_id),
                    "verdict": detail["report"]["verdict"],
                    "restartDetections": restarted["detections"],
                    "history": done.checkpoint_payload.get("history"),
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
