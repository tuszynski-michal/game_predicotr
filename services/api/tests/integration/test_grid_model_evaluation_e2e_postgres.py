"""TASK-0997 real writer -> own-game binding -> notice -> publication barrier (D-556, D-559).

A genuinely frozen, eligible TASK-0995 cohort; the real evaluation service, job handler,
SQL store, SECURITY DEFINER recording bind and publication service. Only the two ONNX
engines are deterministic fakes (no production weights are fabricated), and the base
descriptor's artifact check is accepted for the historical base only.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import numpy as np
import pytest
from _application_role_database import application_role_database
from game_predictor_api.application.geometry_correction_reverts import (
    GeometryCorrectionRevertService,
    VirtualRestoredRenderVerifier,
)
from game_predictor_api.application.grid_model_evaluation import (
    GridModelEvaluationService,
    binding_key,
    report_id_for,
)
from game_predictor_api.application.grid_model_registry import GridModelRegistryService
from game_predictor_api.domain.grid_model_registry import (
    GridModelRegistryError,
    descriptor_sha256,
    historical_catalogue,
    validate_manifest,
)
from game_predictor_api.security.local_admin import ADMIN_ACTOR
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.geometry_correction_revert_repository import (
    SqlAlchemyGeometryCorrectionRevertRepository,
)
from game_predictor_api.storage.grid_engine_model_store import receipt_bytes
from game_predictor_api.storage.grid_model_registry import (
    GridModelArtifactInspector,
    SqlAlchemyGridModelRegistryRepository,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import SymbolModel
from game_predictor_worker.images.grid_cohort_dataset import GridBoardDataset, GridCohortSnapshot
from game_predictor_worker.images.grid_model_evaluation_handler import (
    GridModelEvaluationJobHandler,
)
from game_predictor_worker.images.grid_model_evaluation_store import SqlGridModelEvaluationStore
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_grid_training_cohort_e2e_postgres import (
    _freeze_body,
    _install_base,
    _providers,
    _ready_cohort,
    _recording,
    _recorrect_first,
    _save_source,
    _service,
)
from test_virtual_deferred_resolution_postgres import _factory

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit exact-owned disposable PostgreSQL and twenty generated JPEGs only",
)


def _candidate(root: Path, base: dict[str, Any], cohort: UUID) -> dict[str, Any]:
    payload = copy.deepcopy(base)
    payload.update(
        versionId=str(uuid4()),
        version="v2-e2e",
        baseVersionId=base["versionId"],
        cohortId=str(cohort),
        admission="not_evaluated",
        managedDirectory="models/grid-engine/e2e/candidate",
    )
    directory = root / payload["managedDirectory"]
    (directory / "training-base").mkdir(parents=True)
    contents = {
        "screen.onnx": b"fixture-screen",
        "board.onnx": b"fixture-board",
        "bundle.json": json.dumps({"parity": {"passed": True}}).encode(),
        "preset.json": b"{}",
        "checkpoint.pt": b"fixture-checkpoint",
        "weights.pt": b"fixture-weights",
    }

    def pin(name: str) -> dict[str, Any]:
        content = contents[name]
        return {
            "name": name,
            "sizeBytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    files = [pin(name) for name in ("screen.onnx", "board.onnx", "bundle.json", "preset.json")]
    training = [pin(name) for name in ("checkpoint.pt", "weights.pt", "bundle.json", "preset.json")]
    for name in ("screen.onnx", "board.onnx", "bundle.json", "preset.json"):
        (directory / name).write_bytes(contents[name])
    for name in ("checkpoint.pt", "weights.pt", "bundle.json", "preset.json"):
        (directory / "training-base" / name).write_bytes(contents[name])
    payload["files"], payload["trainingArtifacts"] = files, training
    for target in (payload["provenance"], payload["inferenceManifest"]):
        target["checkpointSha256"] = training[0]["sha256"]
        target["weightsSha256"] = training[1]["sha256"]
    payload["inferenceManifest"].update(version="v2-e2e", files=files)
    (directory / "manifest.json").write_text(
        json.dumps(payload["inferenceManifest"]), encoding="utf-8"
    )
    identity = {
        "schemaVersion": "grid-engine-training-base-v1",
        "model": payload["inferenceManifest"],
        "files": training,
        "sources": {
            item["name"]: str((directory / "training-base" / item["name"]).resolve())
            for item in training
        },
    }
    (directory / "training-base" / "receipt.json").write_bytes(receipt_bytes(identity))
    return payload


class Engine:
    """Returns the human label nodes of the decoded photo, minus ``drop`` boards."""

    def __init__(self, labels: dict[str, list[np.ndarray]], drop: dict[str, int]) -> None:
        self.labels, self.drop, self.calls = labels, drop, 0

    def analyse(self, rgb: np.ndarray) -> list[Any]:
        self.calls += 1
        key = hashlib.sha256(np.ascontiguousarray(rgb).tobytes()).hexdigest()
        boards = self.labels[key][self.drop.get(key, 0) :]
        return [SimpleNamespace(nodes=np.asarray(nodes, np.float32)) for nodes in boards]


def _commit_revert(db, root: Path, game: UUID, job: UUID) -> None:
    """A genuine human revert of the last correction of a used TRAIN photo."""
    with game_storage_scope(game), _factory(db.app_engine).begin() as session:
        service = GeometryCorrectionRevertService(
            SqlAlchemyGeometryCorrectionRevertRepository(session),
            render_verifier=VirtualRestoredRenderVerifier(root),
        )
        entries = service.list_recent(game_id=game, import_job_id=job)
        entry = service.preview(
            game_id=game,
            import_job_id=job,
            board_geometry_revision_id=entries[0].board_geometry_revision_id,
        ).correction
        assert entry.revertable, entry
        result = service.revert(
            game_id=game,
            import_job_id=job,
            board_geometry_revision_id=entry.board_geometry_revision_id,
            idempotency_key=uuid4(),
            expected_geometry_revision=entry.geometry_revision,
            expected_resolution_revision=entry.resolution_revision,
            actor="fixture-human:0997-e2e-revert",
            reverted_at=datetime.now(UTC),
        )
        assert result.created


class Context:
    def __init__(self, job: Any) -> None:
        self._job, self.states = job, []

    @property
    def job(self) -> Any:
        return self._job

    def heartbeat(self) -> None:
        pass

    def checkpoint(self, *, checkpoint_payload: dict[str, Any], **_progress: Any) -> None:
        self.states.append(copy.deepcopy(checkpoint_payload))


def test_real_writer_binds_proves_and_a_later_notice_blocks_publication(monkeypatch):
    repository = Path(__file__).resolve().parents[4]
    evidence = repository / "artifacts/audits" / ("TASK-0997_E2E_" + uuid4().hex)
    evidence.mkdir(parents=True)
    monkeypatch.setenv("GAME_PREDICTOR_RECORDING_TEST_RESOURCE_ROOT", str(evidence / "resources"))
    started, progress = time.monotonic(), []

    def checkpoint(label: str) -> None:
        progress.append({"phase": label, "elapsedSeconds": round(time.monotonic() - started, 3)})
        (evidence / "progress.json").write_text(json.dumps(progress, indent=2), encoding="utf-8")

    with application_role_database("t0997e", ("eval-e2e",)) as db:
        game = next(iter(db.games.values()))
        version, family = _install_base(db, game)
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
        sources, expected, jobs = {}, {}, []
        for ordinal in range(20):
            role = "TRAIN" if ordinal < 10 else "VALIDATION" if ordinal < 15 else "REGRESSION"
            slots = 1 if ordinal == 0 else 5 if ordinal == 1 else 3 if ordinal < 10 else 9
            source, _identity, job = _save_source(db, evidence, game, ordinal, slots, expected)
            if ordinal == 0:
                _recorrect_first(db, evidence, game, job, source, expected)
            sources.setdefault(role, []).append(source)
            jobs.append(job)
        checkpoint("sources_saved")
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
                game, cohort, "freeze", _freeze_body(state), "fixture-human:0997-e2e"
            )
            session.commit()
        assert frozen["cohort"]["status"] == "frozen"
        checkpoint("frozen")

        with Session(db.owner_engine) as session:
            base = json.loads(
                SqlAlchemyGridModelRegistryRepository(session).version(version).manifest_json
            )
        payload = _candidate(evidence, base, cohort)

        class Inspector(GridModelArtifactInspector):
            """The historical base weights are pinned production files: never fabricated."""

            def inspect(self, descriptor: dict[str, Any]) -> tuple[bool, str]:
                if descriptor["versionId"] == str(version):
                    return True, "GRID_MODEL_ARTIFACT_AVAILABLE"
                return super().inspect(descriptor)

        def registry(session: Session) -> GridModelRegistryService:
            return GridModelRegistryService(
                SqlAlchemyGridModelRegistryRepository(session), Inspector(evidence)
            )

        # The 0995 fixture family keeps its own descriptor; insert the immutable
        # version row as that fixture inserts its base (artifacts are checked on read).
        with db.owner_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.grid_model_versions"
                    "(id,family_id,version,base_version_id,manifest_json,manifest_sha256) "
                    "VALUES(:id,:f,:v,:b,:doc,:sha)"
                ),
                {
                    "id": UUID(payload["versionId"]),
                    "f": family,
                    "v": payload["version"],
                    "b": version,
                    "doc": validate_manifest(payload),
                    "sha": descriptor_sha256(payload),
                },
            )
        factory = create_session_factory(db.app_engine)
        with (
            patch(
                "game_predictor_api.application.grid_model_evaluation.GridModelArtifactInspector",
                Inspector,
            ),
            patch(
                "game_predictor_worker.images.grid_model_evaluation_store.GridModelArtifactInspector",
                Inspector,
            ),
        ):
            service = GridModelEvaluationService(db.app_engine, factory, evidence)
            command = {
                "idempotencyKey": str(uuid4()),
                "versionId": payload["versionId"],
                "cohorts": [{"gameId": str(game), "cohortId": str(cohort)}],
            }
            view = service.create(command)
            assert service.create(command) == view, "the same key replays the same job"
            checkpoint("evaluation_queued")
            with Session(db.app_engine) as session:
                cohorts = _service(session, evidence).repository
                cohorts.bind(game)
                row = cohorts.cohort(game, cohort)
                snapshot = GridCohortSnapshot(evidence, row.manifest_path, row.manifest_sha256)
            labels: dict[str, list[np.ndarray]] = {}
            first_validation = None
            for role in ("VALIDATION", "REGRESSION"):
                for source, targets in GridBoardDataset(snapshot, role).indexed():
                    rgb = np.ascontiguousarray(snapshot.frame(source, role).rgb)
                    key = hashlib.sha256(rgb.tobytes()).hexdigest()
                    labels[key] = [nodes for nodes, _ in targets]
                    first_validation = first_validation or (key if role == "VALIDATION" else None)
            assert first_validation is not None and len(labels) == 10
            engines: dict[str, Engine] = {}

            def engine_factory(directory: Path, sha: str) -> Engine:
                name = "candidate" if directory.name == "candidate" else "base"
                engines[name] = Engine(labels, {first_validation: 1} if name == "base" else {})
                return engines[name]

            with Session(db.app_engine) as session:
                job = SqlAlchemyJobRepository(session).get_job(UUID(view["evaluationId"]))
            store = SqlGridModelEvaluationStore(factory, db.app_engine, evidence)
            handler = GridModelEvaluationJobHandler(store, evidence, engine_factory=engine_factory)
            context = Context(job)
            with game_storage_scope(game):  # as the worker runtime does
                handler(context, job)
            assert engines["base"].calls == engines["candidate"].calls == 10
            checkpoint("evaluation_measured_and_proven")
            report_id = report_id_for(job.id)
            detail = service.get(job.id)
            report = detail["report"]
            assert report["verdict"] == "PASS"
            assert report["games"][0]["roles"]["VALIDATION"]["base"]["boards_matched"] == 44
            assert [state["state"] for state in detail["currentness"]] == ["current"]
            with db.owner_engine.connect() as connection:
                binding = connection.execute(
                    text(
                        "SELECT receipt FROM public.recording_commands WHERE game_id=:g "
                        "AND kind='bind_existing_report' AND idempotency_key=:k"
                    ),
                    {"g": game, "k": binding_key(report_id, game)},
                ).scalar_one()
                assert binding["reportId"] == str(report_id)
                uses = connection.scalar(
                    text(
                        "SELECT count(*) FROM public.recording_evidence WHERE kind='use' "
                        "AND payload->>'reportId'=:r"
                    ),
                    {"r": str(report_id)},
                )
                assert uses == len(recordings), "one report-bound use per recording group"

            # A restart after completion measures nothing and rewrites nothing.
            restarted = dataclasses.replace(job, checkpoint_payload=context.states[-1])
            engines.clear()
            with game_storage_scope(game):
                handler(Context(restarted), restarted)
            assert engines == {}

            with Session(db.app_engine) as session:
                publication = registry(session).control
                publication.execute(
                    kind="publish",
                    key=uuid4(),
                    expected_revision=0,
                    version_id=UUID(payload["versionId"]),
                    actor=ADMIN_ACTOR,
                    evaluation_id=report_id,
                )
                session.commit()
            with Session(db.app_engine) as session:
                registry(session).control.eligible(UUID(payload["versionId"]), game_id=game)
            checkpoint("published_with_current_proof")

            # A later human revert of a used photo raises the shared notice watermark.
            _commit_revert(db, evidence, game, jobs[0])
            with (
                Session(db.app_engine) as session,
                pytest.raises(GridModelRegistryError, match="GRID_MODEL_EVALUATION_STALE"),
            ):
                registry(session).control.eligible(UUID(payload["versionId"]), game_id=game)
            result = service.verify_currentness(report_id, ADMIN_ACTOR)
            assert result["failures"] and result["failures"][0]["gameId"] == str(game)
            assert [state["state"] for state in result["currentness"]] == ["stale"]
            with (
                Session(db.app_engine) as session,
                pytest.raises(GridModelRegistryError, match="GRID_MODEL_EVALUATION_STALE"),
            ):
                registry(session).control.eligible(UUID(payload["versionId"]), game_id=game)
            checkpoint("notice_blocks_and_withdrawn_label_is_not_reproven")
        (evidence / "result.json").write_text(
            json.dumps(
                {
                    "reportSha256": descriptor_sha256(report),
                    "verdict": report["verdict"],
                    "failures": result["failures"],
                    "baseVersion": historical_catalogue()[0]["version"],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
