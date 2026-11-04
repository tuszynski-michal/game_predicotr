"""Protocol fixtures, never human calibration evidence or a production model."""

import copy
import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
import torch
from game_predictor_api.domain.grid_rescue_policy import require_rescue_evidence
from game_predictor_api.storage.grid_engine_model_store import receipt_bytes
from game_predictor_api.storage.grid_model_registry import GridModelArtifactInspector
from game_predictor_worker.geometry_core.inference import BoardDetection
from game_predictor_worker.images.grid_rescue_evaluation import ScreenCorrectionEvaluator
from game_predictor_worker.images.grid_rescue_export import RescueParity
from game_predictor_worker.images.grid_rescue_runtime import run_with_rescue
from game_predictor_worker.images.grid_training_child import RECIPE_FILE, canonical
from game_predictor_worker.images.grid_training_data import CohortPhotos
from game_predictor_worker.images.grid_training_handler import GridTrainingJobHandler
from game_predictor_worker.training_core.grid_rescue_training import (
    TrainingExposure,
    rescue_recipe,
    selection_input,
)
from game_predictor_worker.training_core.grid_training import export_graphs, namespace
from game_predictor_worker.training_core.grid_training_admission import digest
from test_grid_cohort_dataset import SnapshotFixture
from test_screen_rescue_contract import variant
from test_screen_rescue_onnx import TinyExport


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def rescue_fixture(tmp_path):
    fixture = SnapshotFixture(tmp_path)
    labels = [
        np.array(
            [
                ((i % 3) * 20 + 2 + c * 2, (i // 3) * 15 + 2 + r * 2)
                for r in range(4)
                for c in range(6)
            ],
            np.float32,
        )
        for i in range(9)
    ]
    for role, count in (("TRAIN", 10), ("VALIDATION", 5)):
        for _ in range(count):
            source = fixture.source(role, full=True)
            for target, nodes in zip(source["targets"], labels, strict=True):
                target["nodes"] = [{"x": float(x), "y": float(y)} for x, y in nodes]
    pins = [
        {
            "sourceId": s["sourceId"],
            "sourceSha256": s["sourceIdentity"]["checksum_sha256"],
            "pixelSha256": s["sourceIdentity"]["normalized_pixel_checksum_sha256"],
            "qualifiedLabelsSha256": digest(s["targets"]),
            "role": s["role"],
            "representative": True,
            "eligibleBoards": 9,
        }
        for s in fixture.sources
    ]
    split = {"schemaVersion": "grid-correction-split-v3", "sources": pins}
    split["sha256"] = digest(split)
    snapshot = fixture.publish(
        mode="screen+grid",
        change=lambda root: root.update(
            schemaVersion="application-grid-snapshot-v3",
            policyVersion="application-grid-corrections-v3",
            photoSplit=split,
        ),
    )
    selection = selection_input([(fixture.game, split)])
    recipe_payload = json.loads(RECIPE_FILE.read_bytes())
    recipe = namespace(recipe_payload)
    sealed = rescue_recipe(checksum(RECIPE_FILE), variant().model_dump(mode="json"), selection)
    exposure = TrainingExposure(sealed)
    members = [
        {
            "gameId": fixture.game,
            "sourceId": s["sourceId"],
            "sourceSha256": s["sourceIdentity"]["checksum_sha256"],
            "cohortSha256": snapshot.manifest_sha256,
        }
        for s in fixture.sources
        if s["role"] == "TRAIN"
    ]
    exposure.confirm(1, members)
    exposure.confirm(2, members)

    def detection(index, bad=False):
        item = BoardDetection(0.99, labels[index][[0, 5, 23, 18]].copy())
        item.nodes = labels[index].copy() + (np.array([1.5, 0], np.float32) if bad else 0)
        item.raw_nodes = item.nodes.copy()
        item.reasons = ["NEURAL_GRID_FIT_OUTLIERS"] if bad else []
        return item

    class Engine:
        def analyse(self, rgb):
            return [detection(i, i == 4) for i in range(9)]

        def detect(self, rgb, geometry=None):
            return [detection(i) for i in range(9)]

        def recrop(self, rgb, found, geometry=None):
            index = min(range(9), key=lambda i: np.linalg.norm(labels[i][0] - found.screen_quad[0]))
            return detection(index)

    evaluator = ScreenCorrectionEvaluator(
        [CohortPhotos(snapshot, "VALIDATION", full_only=True)],
        recipe,
        "cpu",
        variant(),
        selection,
        exposure,
    )
    measured = evaluator.measure(Engine(), exposure.state())
    assert measured["selectedPath"] == "board_only"
    assert all(item["admittedOnA"] for item in measured["pathProofs"].values())
    run_id = str(uuid4())
    run = tmp_path / "grid-training" / "runs" / run_id
    exported = run / "export-fixture"
    exported.mkdir(parents=True)
    network = TinyExport().eval()
    export_graphs(network, recipe, exported)
    parity = RescueParity(network, recipe, exported)
    with torch.no_grad():
        for path in ("baseline", "screen_only", "board_only", "combined"):
            parity.path = path
            if path != "board_only":
                parity.engine.screen_runner(
                    np.zeros(
                        (1, 3, 768, 1024) if path != "baseline" else (1, 3, 576, 768), np.float32
                    )
                )
            parity.engine.board_runner(np.zeros((1, 3, 192, 320), np.float32))
    for name, content in (
        ("weights.pt", b"protocol-fixture-weights"),
        ("checkpoint.pt", b"protocol-fixture-checkpoint"),
        ("preset.json", RECIPE_FILE.read_bytes()),
    ):
        (exported / name).write_bytes(content)
    checkpoint_selection = {
        "rule": "validation-photo-board-correct-photo-macro-error-earliest-v1",
        "role": "VALIDATION",
        "step": 2,
        "metrics": measured["metrics"],
        "earlyStopping": {"patience": 4, "evaluationsWithoutImprovement": 0, "stopped": False},
        "selectionInputSha256": selection["sha256"],
        "metricStateVersion": "photo-board-checkpoint-state-v1",
    }
    provenance = {
        "runId": run_id,
        "bestStep": 2,
        "weightsSha256": checksum(exported / "weights.pt"),
        "checkpointSha256": checksum(exported / "checkpoint.pt"),
        "trainingPresetFingerprint": "e" * 64,
        "trainingPresetId": "screen-grid-corrections-v1",
        "snapshotId": snapshot.manifest_sha256,
        "checkpointSelection": checkpoint_selection,
    }
    proof = {
        "contractVersion": "grid-rescue-evidence-v1",
        "recipe": sealed,
        "selectionInput": selection,
        "trainingExposure": exposure.state(),
        "selection": measured,
        "parity": parity.document(),
        **{
            key: value
            for key, value in provenance.items()
            if key not in ("trainingPresetId", "checkpointSelection")
        },
    }
    proof["sha256"] = digest(proof)
    bundle = {
        "rescue": proof,
        "provenance": provenance,
        "preset": recipe_payload,
        "files": {
            name: checksum(exported / name) for name in ("screen.onnx", "board.onnx", "weights.pt")
        },
    }
    (exported / "bundle.json").write_bytes(canonical(bundle))
    spec = {
        "format": "grid-training-spec-v1",
        "jobId": run_id,
        "preset": {"id": "screen-grid-corrections-v1", "fingerprint": "e" * 64},
        "base": {"presetSha256": checksum(RECIPE_FILE)},
        "cohort": {
            "manifestPath": fixture.manifest_pin["path"],
            "manifestSha256": snapshot.manifest_sha256,
        },
        "rescueRecipe": sealed,
    }
    (run / "spec.json").write_bytes(canonical({"payload": spec, "sha256": digest(spec)}))
    directory = tmp_path / "models/grid-engine/rescue-fixture"
    directory.mkdir(parents=True)
    training = directory / "training-base"
    training.mkdir()
    files = []
    train_files = []
    for target, names, entries in (
        (directory, ("screen.onnx", "board.onnx", "preset.json", "bundle.json"), files),
        (training, ("weights.pt", "checkpoint.pt", "preset.json", "bundle.json"), train_files),
    ):
        for name in names:
            content = (exported / name).read_bytes()
            (target / name).write_bytes(content)
            entries.append(
                {
                    "name": name,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "sizeBytes": len(content),
                }
            )
    inference = {"fixture": "protocol-only"}
    (directory / "manifest.json").write_bytes(canonical(inference))
    receipt = {
        "schemaVersion": "grid-engine-training-base-v1",
        "model": inference,
        "files": train_files,
        "sources": {item["name"]: str(exported / item["name"]) for item in train_files},
    }
    (training / "receipt.json").write_bytes(receipt_bytes(receipt))
    descriptor = {
        "managedDirectory": directory.relative_to(tmp_path).as_posix(),
        "inferenceManifest": inference,
        "files": files,
        "trainingArtifacts": train_files,
    }
    return SimpleNamespace(
        root=tmp_path,
        fixture=fixture,
        descriptor=descriptor,
        bundle=bundle,
        run=run,
        exported=exported,
        engine=Engine(),
        snapshot=snapshot,
        evaluator=evaluator,
        exposure=exposure,
        directory=directory,
    )


def test_all_three_paths_require_their_own_train_and_selection_evidence(rescue_fixture):
    s = rescue_fixture
    assert require_rescue_evidence(s.bundle)["selection"]["selectedPath"] == "board_only"
    broken = copy.deepcopy(s.bundle)
    del broken["rescue"]["trainingExposure"]["games"][s.fixture.game]["board:variant"]
    exp = broken["rescue"]["trainingExposure"]
    exp["sha256"] = digest({key: value for key, value in exp.items() if key != "sha256"})
    broken["rescue"]["sha256"] = digest(
        {key: value for key, value in broken["rescue"].items() if key != "sha256"}
    )
    with pytest.raises(ValueError, match="VERDICT|EXPOSURE"):
        require_rescue_evidence(broken)
    empty = TrainingExposure(s.bundle["rescue"]["recipe"])
    result = s.evaluator.measure(s.engine, empty.state())
    assert result["selectedPath"] is None
    assert all(
        "GRID_RESCUE_TRAIN_EXPOSURE_REQUIRED" in item["reasonCodes"]
        for item in result["pathProofs"].values()
    )


def test_inspector_reconciles_real_receipt_spec_graphs_and_frozen_sources(rescue_fixture):
    s = rescue_fixture
    inspector = GridModelArtifactInspector(s.root)
    assert inspector.inspect(s.descriptor) == (True, "GRID_MODEL_ARTIFACT_AVAILABLE")
    pin, reason = inspector.inspect_rescue(
        s.descriptor, game_id=s.fixture.game, publication_evidence={"verified": "fixture"}
    )
    assert reason == "GRID_RESCUE_PATH_AVAILABLE" and pin["selectedPath"] == "board_only"
    GridTrainingJobHandler._verify_screen_export(s.run, s.bundle, required=True)
    (s.run / "spec.json").write_text("{}")
    assert (
        inspector.inspect_rescue(s.descriptor, game_id=s.fixture.game, publication_evidence={})[1]
        == "GRID_RESCUE_PROOF_INVALID"
    )


def test_runtime_uses_same_path_and_replays_receipts_without_new_calls(rescue_fixture):
    s = rescue_fixture
    pin, reason = GridModelArtifactInspector(s.root).inspect_rescue(
        s.descriptor, game_id=s.fixture.game, publication_evidence={}
    )
    assert pin is not None, reason
    calls = []

    class Runner:
        def run(self, *args, **kwargs):
            calls.append("baseline")
            return s.engine.analyse(args[2])

        def run_stage(self, *args, request, **kwargs):
            from game_predictor_worker.geometry_core.rescue_serialization import (
                detection_from_document,
            )

            calls.append(request["kind"])
            return [s.engine.recrop(args[2], detection_from_document(request["detection"]))]

    args = dict(
        runner=Runner(),
        bundle=s.directory,
        bundle_sha=pin["bundleSha256"],
        rgb=np.zeros((48, 64, 3), np.uint8),
        heartbeat=lambda: None,
        max_seconds=30,
        directory=s.root / "operation/rescue",
        source_sha="a" * 64,
        pin=pin,
        expected_positions=set(range(9)),
    )
    first = {}
    second = {}
    found = run_with_rescue(**args, summary_sink=first)
    replay = run_with_rescue(**args, summary_sink=second)
    assert calls == ["baseline", "board"] and first == second
    assert first["attempts"][0]["state"] == "completed"
    assert first["attempts"][0]["request"]["geometry"]["margin"] == 0.2
    assert found[4].reasons == replay[4].reasons == []
    alias_summary = {}
    alias = run_with_rescue(**{**args, "expected_positions": {4, 5}}, summary_sink=alias_summary)
    assert calls == ["baseline", "board"]
    assert alias_summary["reasonCodes"] == ["GRID_RESCUE_SLOT_BINDING_REQUIRED"]
    assert alias_summary["attempts"] == first["attempts"]
    assert alias_summary["identity"] == first["identity"]
    assert all("NEURAL_GRID_SLOT_BINDING_REQUIRED" in item.reasons for item in alias)
    assert (
        "NEURAL_GRID_FIT_OUTLIERS" in alias[4].reasons
    )  # original baseline, not another scope's rescue
