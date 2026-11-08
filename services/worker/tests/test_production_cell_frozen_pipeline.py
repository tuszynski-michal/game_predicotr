"""Synthetic metadata + real frozen pixels/rendering; not model qualification evidence."""

import json
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import numpy as np
import pytest
from game_predictor_api.domain.grid_cell_content import ContentRevision, content_source_identity
from game_predictor_api.domain.grid_training_cohorts import digest, exact_lattice
from game_predictor_api.domain.grid_visibility_contract import (
    BoardContentReference,
    CellContentReference,
    GridOutputContract,
    visibility_supervision,
)
from game_predictor_worker.geometry_core.inference import BoardDetection
from game_predictor_worker.images.full_board_calibration_run import FullBoardCalibrationRun
from game_predictor_worker.images.grid_model_evaluation_handler import (
    GridModelEvaluationJobHandler,
    _write_atomic,
)
from game_predictor_worker.images.production_cell_input import engine_input_context
from game_predictor_worker.images.production_cell_run import ProductionContentRun
from test_grid_cohort_dataset import SnapshotFixture
from test_grid_model_evaluation import Context
from test_production_cell_observations import board_preset


def frozen_fixture(root, *, regression_photos=1, configure=None):
    fixture = SnapshotFixture(root)
    rows = [
        fixture.source("VALIDATION"),
        fixture.source("VALIDATION"),
        *(fixture.source("REGRESSION") for _ in range(regression_photos)),
    ]
    session_id = uuid4()
    measurement = {
        "version": "cell-content-repeatability-v1",
        "quantile": "nearest-rank-p95-v1",
        "state": "ready",
        "qualificationState": "ready",
        "games": {fixture.game: {"state": "ready", "u": 0.001, "delta": 0.001}},
    }
    measurement["sha256"] = digest(measurement)
    now = datetime(2026, 11, 8, tzinfo=UTC)
    for source, purpose in zip(rows, ("A", "B", *([None] * regression_photos)), strict=True):
        source["sourceIdentity"]["coordinate_space"] = "exif-normalized-rgb-pixels-v1"
        source.update(
            validationPurpose=purpose,
            purposeProofSha256="d" * 64,
            assessmentPolicy=None if purpose == "A" else "human-labeled-targets-v1",
        )
        target = source["targets"][0]
        nodes = [[p["x"], p["y"]] for p in target["nodes"]]
        cells = []
        for j in range(15):
            y, x = divmod(j, 5)
            left, top = 7 * x + 3.0, 8 * y + 3.0
            cells.append(
                CellContentReference(
                    state="visible",
                    quad=((left, top), (left + 3, top), (left + 3, top + 4), (left, top + 4)),
                )
            )
        annotation = ContentRevision(
            source=content_source_identity({**source["sourceIdentity"], "id": source["sourceId"]}),
            reference=BoardContentReference(
                gameId=UUID(fixture.game),
                sourceRepresentativeSha256=source["sourceIdentity"][
                    "normalized_pixel_checksum_sha256"
                ],
                positionIndex=0,
                revision=1,
                humanApproved=True,
                cells=tuple(cells),
            ),
            sequenceNumber=target["sequenceNumber"],
            origin="manual_blind" if purpose == "A" else "manual",
            actor="local-owner",
            approvedBy="local-owner",
            approvedAt=now,
            recordedAt=now,
            sessionId=session_id if purpose == "A" else None,
            passNumber=2 if purpose == "A" else None,
            measuredNodes=nodes if purpose == "A" else None,
        )
        configuration = {
            "extractorVersion": "virtual-cell-renderer-source-direct-v4",
            "preprocessingVersion": "rgb-resize64-normalize-half-v1",
            "interpolation": "opencv-inter-linear-v1",
            "outputWidth": 64,
            "outputHeight": 64,
            "paddingFraction": 0.1,
        }
        target.update(
            contentAnnotation=annotation.model_dump(mode="json"),
            contentReferenceSha256=annotation.sha256,
            contentReferenceRevision=1,
            render={"configuration": configuration},
        )
        if purpose == "A":
            target["blindGeometry"] = {
                "version": "blind-content-geometry-reference-v1",
                "sessionId": str(session_id),
                "contentRevision": 1,
                "contentReferenceSha256": annotation.sha256,
                "nodesSha256": digest(target["nodes"]),
            }
            _, target["render"]["cellQuads"] = exact_lattice(
                {"latticeNodes": target["nodes"]}, 64, 48
            )
        context = {
            "state": "available",
            "classifier": {"syntheticPinnedSnapshot": "test-only"},
            "renderConfiguration": configuration,
            "importJobId": str(uuid4()),
            "fileExecutionKey": "c" * 64,
            "topologyRulesVersionId": str(uuid4()),
            "sequenceRangeStart": 17,
            "sequenceRangeEnd": 17,
        }
        body = {
            "version": "production-cell-evaluation-reference-v1",
            "sourceContext": context,
            "sourceContextSha256": digest(context),
            "measurement": {"sessionId": str(session_id), "report": measurement}
            if purpose == "A"
            else None,
        }
        target["productionContentReference"] = {**body, "sha256": digest(body)}
    split = {
        "schemaVersion": "grid-correction-split-v4",
        "purposeCounts": {
            "VALIDATION-" + p: {"photos": 1, "boards": 1, "fullPhotos": 0} for p in ("A", "B")
        },
        "sources": [
            {
                "sourceId": s["sourceId"],
                "role": s["role"],
                "validationPurpose": s["validationPurpose"],
                "representative": True,
                "purposeProofSha256": "d" * 64,
                "eligibleBoards": 1,
                "componentIds": [],
            }
            for s in rows
        ],
        "contentSampling": {
            "policy": "full-symbol-content-sampling-v1",
            "state": "ready",
            "sourceIds": [s["sourceId"] for s in rows[2:]],
        },
    }
    if configure is not None:
        configure(fixture, rows, split)
    split["sha256"] = digest(split)
    snapshot = fixture.publish(
        change=lambda doc: doc.update(
            schemaVersion="application-grid-snapshot-v4",
            policyVersion="application-grid-corrections-v4",
            photoSplit=split,
        )
    )
    return fixture, snapshot, rows


class Engine:
    def __init__(self, nodes):
        self.nodes, self.calls = nodes, 0
        self.settings = SimpleNamespace(board=board_preset())
        self.output_contract = GridOutputContract(supervision=visibility_supervision([]))

    def analyse(self, _rgb):
        self.calls += 1
        return [
            BoardDetection(
                1.0,
                self.nodes[[0, 5, 23, 18]].copy(),
                self.nodes.copy(),
                self.nodes.copy(),
                np.ones(24),
                np.ones(15),
                0.0,
                0.0,
                24,
                [],
            )
        ]


def test_actual_frozen_a_input_adapter_renderer_restart_and_cold_replay(tmp_path, monkeypatch):
    fixture, snapshot, rows = frozen_fixture(tmp_path)
    nodes = np.asarray([[p["x"], p["y"]] for p in rows[0]["targets"][0]["nodes"]], np.float32)
    engines = Engine(nodes), Engine(nodes)
    input_contexts = {
        name: engine_input_context(engine)
        for name, engine in zip(("base", "candidate"), engines, strict=True)
    }
    job = SimpleNamespace(
        id=uuid4(),
        input_payload={"evaluation_kind": "grid-correction-evaluation-v1"},
        cancel_requested_at=None,
    )
    calibration = FullBoardCalibrationRun(
        root=tmp_path,
        job_id=job.id,
        snapshot=snapshot,
        candidate_sha="a" * 64,
        baseline_sha="b" * 64,
        engines=engines,
        write=_write_atomic,
    )
    production = ProductionContentRun(snapshot)
    handler = GridModelEvaluationJobHandler(None, tmp_path, threads=1)
    context = Context(job)
    groups = {s["sourceId"]: s["sourceId"] for s in rows}
    entry = {"game_id": fixture.game, "cohort_id": fixture.cohort}
    state = {"units": {}, "reportSha256": None, "proven": []}
    for role in ("VALIDATION", "REGRESSION"):
        if role == "REGRESSION":
            calibration.prepare_b(lambda _: None)
        handler._measure_unit(
            context, job, state, 1, entry, role, snapshot, groups, engines, calibration, production
        )
    result = production.finish(tmp_path, job.id)
    assert result["u"] == result["delta"] == 0.001
    assert result["roles"]["VALIDATION"]["candidate"]["usableBoards"] == 1
    assert result["roles"]["REGRESSION"]["fullPhotos"] == 0  # no whole-photo claim
    prepared = calibration._read(calibration._path("plan"))
    assert len(prepared["inputContentEvidence"]) == 1
    edge = prepared["selectionReferences"][0]["inputEdgeReference"]
    assert edge["referenceKind"] == "verified_content" and edge["inputCropped"] is False
    calibration.frozen.require_plan(prepared)
    changed = deepcopy(prepared)
    changed["inputContentEvidence"][0]["inputCropped"] = True
    changed["inputContentEvidence"][0]["sha256"] = digest(
        {k: v for k, v in changed["inputContentEvidence"][0].items() if k != "sha256"}
    )
    with pytest.raises(ValueError, match="INPUT_CONTENT_EVIDENCE_CHANGED"):
        calibration.frozen.require_plan(changed)
    before = [engine.calls for engine in engines]
    calibration.prepare_b(lambda _: pytest.fail("B must not run on resume"))
    assert before == [engine.calls for engine in engines]
    for role in ("VALIDATION", "REGRESSION"):
        document = json.loads(
            (
                tmp_path / "grid-model-evaluations" / str(job.id) / f"{fixture.game}-{role}.json"
            ).read_bytes()
        )
        production.verify_photo_details(role, document["photos"], input_contexts=input_contexts)
        altered = deepcopy(document["photos"])
        altered[0]["contentEvaluation"]["models"]["candidate"]["crops"][0][
            "renderedPixelSha256"
        ] = "f" * 64
        with pytest.raises(ValueError, match="RENDER_CHANGED"):
            production.verify_photo_details(role, altered, input_contexts=input_contexts)
    context_path = tmp_path / "synthetic-input-context.json"
    context_path.write_text(json.dumps(input_contexts), encoding="utf-8")
    script = """import json,sys
from pathlib import Path
from game_predictor_worker.images.grid_cohort_dataset import GridCohortSnapshot
from game_predictor_worker.images.production_cell_run import ProductionContentRun
from game_predictor_api.storage.full_board_calibration_evidence import (
 snapshot_assessment_references,
)
root=Path(sys.argv[1])
snapshot=GridCohortSnapshot(root,sys.argv[2],sys.argv[3])
run=ProductionContentRun(snapshot)
game=snapshot.manifest['gameId']
job=sys.argv[4]
contexts=json.loads(Path(sys.argv[5]).read_text())
for role in ('VALIDATION','REGRESSION'):
 doc=json.loads((root/'grid-model-evaluations'/job/f'{game}-{role}.json').read_bytes())
 run.verify_photo_details(role,doc['photos'],input_contexts=contexts)
plan=json.loads((root/'grid-model-evaluations'/job/f'{game}-calibration-plan.json').read_bytes())['payload']
snapshot_assessment_references(snapshot,input_context=contexts['candidate']).require_plan(plan)
print(json.dumps(run.finish(root,job),sort_keys=True))
"""
    cold = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(tmp_path),
            fixture.manifest_pin["path"],
            fixture.manifest_pin["sha256"],
            str(job.id),
            str(context_path),
        ],
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert cold.returncode == 0, cold.stderr
    assert json.loads(cold.stdout) == result
    # The storage freshness reader uses actual frozen files and pinned bundle bytes.
    # Only the database rows/current classifier resolver are boundary doubles here;
    # PG separately covers the authority/RLS/retention and report-bind functions.
    import hashlib

    from game_predictor_api.domain.grid_model_registry import GridModelRegistryError
    from game_predictor_api.storage.grid_training_cohort_models import GridTrainingCohortModel
    from game_predictor_api.storage.production_cell_reference import (
        require_production_content_freshness,
    )
    from game_predictor_api.storage.symbol_model_snapshot_resolver import (
        SqlAlchemySymbolModelSnapshotResolver,
    )

    bundle = json.dumps({"preset": {"board": board_preset().model_dump(mode="json")}}).encode()
    bundle_path = tmp_path / "models" / "input-proof" / "bundle.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_bytes(bundle)
    descriptor = {
        "managedDirectory": "models/input-proof",
        "files": [{"name": "bundle.json", "sha256": hashlib.sha256(bundle).hexdigest()}],
    }
    version = SimpleNamespace(manifest_json=json.dumps(descriptor))
    cohort = SimpleNamespace(
        status="frozen",
        manifest_path=fixture.manifest_pin["path"],
        manifest_sha256=fixture.manifest_pin["sha256"],
    )
    session = SimpleNamespace(
        get=lambda kind, key: cohort if kind is GridTrainingCohortModel else version
    )
    from contextlib import contextmanager

    from game_predictor_api.storage import production_cell_reference

    @contextmanager
    def read_game(_session, game):
        assert str(game) == fixture.game
        yield session

    monkeypatch.setattr(production_cell_reference, "production_reference_reader", read_game)
    model = SimpleNamespace(crop_output_size=64, crop_padding_fraction=0.1)
    monkeypatch.setattr(SqlAlchemySymbolModelSnapshotResolver, "resolve", lambda *_a, **_k: model)
    role_details = {}
    for role in ("VALIDATION", "REGRESSION"):
        path = tmp_path / "grid-model-evaluations" / str(job.id) / f"{fixture.game}-{role}.json"
        role_details[role] = {
            "detail": {
                "path": path.relative_to(tmp_path).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        }
    report = {
        "schemaVersion": "grid-model-evaluation-read-v6",
        "baseVersionId": str(uuid4()),
        "versionId": str(uuid4()),
        "cohorts": [
            {
                "gameId": fixture.game,
                "cohortId": fixture.cohort,
                "manifestSha256": fixture.manifest_pin["sha256"],
            }
        ],
        "contentEvaluation": [result],
        "rawQuality": {"games": [{"gameId": fixture.game, "roles": role_details}]},
    }
    require_production_content_freshness(session, tmp_path, report)
    # Same verified bytes under a noncanonical name must not authorize another artifact.
    altered_path_report = deepcopy(report)
    original_pin = role_details["VALIDATION"]["detail"]
    original_path = tmp_path / original_pin["path"]
    alternate_path = original_path.with_name("alternate-validation.json")
    alternate_path.write_bytes(original_path.read_bytes())
    altered_path_report["rawQuality"]["games"][0]["roles"]["VALIDATION"]["detail"]["path"] = (
        alternate_path.relative_to(tmp_path).as_posix()
    )
    with pytest.raises(GridModelRegistryError, match="CONTENT_DETAIL_CANONICAL_PATH_REQUIRED"):
        require_production_content_freshness(session, tmp_path, altered_path_report)
    # A concurrent file replacement after verification cannot change the summarized document.
    regression_path = tmp_path / role_details["REGRESSION"]["detail"]["path"]
    regression_bytes = regression_path.read_bytes()
    real_verify = ProductionContentRun.verify_photo_details

    def verify_then_replace(self, role, photos, **kwargs):
        real_verify(self, role, photos, **kwargs)
        if role == "REGRESSION":
            regression_path.write_bytes(b"changed after verified read")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(ProductionContentRun, "verify_photo_details", verify_then_replace)
            require_production_content_freshness(session, tmp_path, report)
        with pytest.raises(GridModelRegistryError, match="CONTENT_DETAIL_CHECKSUM"):
            require_production_content_freshness(session, tmp_path, report)
    finally:
        regression_path.write_bytes(regression_bytes)
    model.crop_padding_fraction = 0.2
    with pytest.raises(GridModelRegistryError, match="CONTENT_RENDER_CONFIGURATION_CHANGED"):
        require_production_content_freshness(session, tmp_path, report)
    model.crop_padding_fraction = 0.1
    altered_report = deepcopy(report)
    altered_report["contentEvaluation"][0]["roles"]["VALIDATION"]["candidate"]["usableBoards"] = 0
    with pytest.raises(GridModelRegistryError, match="CONTENT_REPORT_EVIDENCE_CHANGED"):
        require_production_content_freshness(session, tmp_path, altered_report)
    from game_predictor_api.storage.game_storage_routing import GameStorageRoutingError

    @contextmanager
    def unavailable_game(_session, _game):
        raise GameStorageRoutingError("GAME_STORAGE_BLOCKED", "blocked game", details={})
        yield  # pragma: no cover - context manager never opens unavailable storage

    monkeypatch.setattr(production_cell_reference, "production_reference_reader", unavailable_game)
    with pytest.raises(GridModelRegistryError, match="blocked game") as stale:
        require_production_content_freshness(session, tmp_path, report)
    assert stale.value.code == "GRID_MODEL_EVALUATION_STALE"


def test_pinned_model_input_variant_cannot_be_replaced_with_self_hashed_larger_input():
    from game_predictor_worker.images.production_cell_input import require_input_context

    expected = engine_input_context(Engine(np.zeros((24, 2))))
    proof = {key: expected[key] for key in ("boardPreset", "routing", "path")}
    proof["geometry"] = None
    require_input_context(proof, expected)
    with pytest.raises(ValueError, match="MODEL_CONTEXT_CHANGED"):
        require_input_context(proof, None)
    changed = deepcopy(proof)
    changed["boardPreset"]["canvas"] = [480, 288]
    with pytest.raises(ValueError, match="MODEL_CONTEXT_CHANGED"):
        require_input_context(changed, expected)
    changed = deepcopy(proof)
    changed["geometry"] = {"margin": 0.4}
    with pytest.raises(ValueError, match="VARIANT_CHANGED"):
        require_input_context(changed, expected)


def test_freshness_requires_artifact_root_and_only_crop_settings_bind_classifier_weights(
    tmp_path, monkeypatch
):
    from game_predictor_api.domain.grid_model_registry import GridModelRegistryError
    from game_predictor_api.storage.production_cell_reference import (
        current_render_configuration,
        require_production_content_freshness,
    )
    from game_predictor_api.storage.symbol_model_snapshot_resolver import (
        SqlAlchemySymbolModelSnapshotResolver,
    )

    with pytest.raises(GridModelRegistryError, match="CONTENT_ARTIFACT_ROOT_REQUIRED"):
        require_production_content_freshness(
            None, None, {"schemaVersion": "grid-model-evaluation-read-v6"}
        )
    model = SimpleNamespace(crop_output_size=64, crop_padding_fraction=0.1, weights="old")
    monkeypatch.setattr(SqlAlchemySymbolModelSnapshotResolver, "resolve", lambda *_a, **_k: model)
    first = current_render_configuration(None, tmp_path, uuid4())
    model.weights = "new"
    assert current_render_configuration(None, tmp_path, uuid4()) == first
    model.crop_padding_fraction = 0.2
    assert current_render_configuration(None, tmp_path, uuid4()) != first
