"""Real small CPU graphs, frozen pixels and export/install/recovery; no trained-model claim."""

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
import torch
from game_predictor_api.domain.grid_cell_content import ContentRevision, content_source_identity
from game_predictor_api.domain.grid_content_experiment_inputs import (
    build_inputs,
    training_eligibility,
)
from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_api.domain.grid_visibility_contract import (
    GridOutputContract,
    visibility_supervision,
)
from game_predictor_api.storage.grid_model_registry import GridModelArtifactInspector
from game_predictor_worker.images.grid_content_experiment_data import measure_bank, torch_engine
from game_predictor_worker.images.grid_training_child import (
    RECIPE_FILE,
    _export,
    sha256_file,
    write_json_atomic,
)
from game_predictor_worker.images.grid_training_data import (
    CohortPhotos,
    content_references,
    validation_crops,
)
from game_predictor_worker.images.grid_training_handler import GridTrainingJobHandler, RunState
from game_predictor_worker.training_core.grid_content_experiment import build_plan
from game_predictor_worker.training_core.grid_training import namespace
from game_predictor_worker.training_core.grid_training_admission import (
    SCREEN_GRID_CORRECTIONS_V1,
    RunBudget,
)
from game_predictor_worker.training_core.neural_grid_network import BoardNetwork, ScreenNetwork
from test_production_cell_frozen_pipeline import frozen_fixture


def actual_inputs(root, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "api" / "tests"))
    from test_grid_content_experiment_inputs import inputs_fixture

    saved = {}

    def configure(fixture, rows, split):
        train = fixture.source("TRAIN", full=True)
        train["sourceIdentity"]["coordinate_space"] = "exif-normalized-rgb-pixels-v1"
        train["validationPurpose"] = None
        train["purposeProofSha256"] = "d" * 64
        annotation = deepcopy(rows[1]["targets"][0]["contentAnnotation"])
        annotation["source"] = content_source_identity(
            {**train["sourceIdentity"], "id": train["sourceId"]}
        ).model_dump(mode="json")
        annotation["reference"]["sourceRepresentativeSha256"] = train["sourceIdentity"][
            "normalized_pixel_checksum_sha256"
        ]
        parsed = ContentRevision.model_validate(annotation)
        train["targets"][0].update(
            contentAnnotation=parsed.model_dump(mode="json"),
            contentReferenceSha256=parsed.sha256,
            contentReferenceRevision=parsed.reference.revision,
        )
        split["sources"].append(
            {
                "sourceId": train["sourceId"],
                "role": "TRAIN",
                "validationPurpose": None,
                "representative": True,
                "eligibleBoards": 9,
                "componentIds": [],
                "purposeProofSha256": "d" * 64,
            }
        )
        sources = {s["sourceId"]: s for s in fixture.sources}
        for pin in split["sources"]:
            source = sources[pin["sourceId"]]
            pin.update(
                sourceSha256=source["sourceIdentity"]["checksum_sha256"],
                pixelSha256=source["sourceIdentity"]["normalized_pixel_checksum_sha256"],
                qualifiedLabelsSha256=digest(source["targets"]),
                registryProofSha256="b" * 64,
            )
        saved["split"] = split

    fixture, _, _ = frozen_fixture(root, configure=configure)
    split = saved["split"]
    snapshot = fixture.publish(
        mode="screen+grid",
        change=lambda doc: doc.update(
            schemaVersion="application-grid-snapshot-v4",
            policyVersion="application-grid-corrections-v4",
            photoSplit=split,
        ),
    )
    args, _, _ = inputs_fixture()
    ancestor = {
        "versionId": fixture.base["versionId"],
        "manifestSha256": snapshot.manifest["base"]["manifestSha256"],
    }
    provider = deepcopy(next(iter(args["providers"].values())))
    provider["ancestor"] = ancestor
    contexts = {
        pin["sourceId"]: {
            "sourceId": pin["sourceId"],
            "componentIds": [],
            "aliasComponentIds": [],
            "allowedRoles": [pin["role"]],
            "priorRoles": [],
            "proofSha256": "c" * 64,
            "diagnosticExposed": False,
            "selectionExposed": False,
            "validationPurposes": [],
        }
        for pin in split["sources"]
    }
    # A positive source component independent from the ancestor recording is explicit.
    train_pin = next(pin for pin in split["sources"] if pin["role"] == "TRAIN")
    contexts[train_pin["sourceId"]]["componentIds"] = [str(uuid4())]
    eligibility = training_eligibility(
        game=fixture.game,
        base=fixture.base,
        base_sha256=ancestor["manifestSha256"],
        lineage={"ancestors": [ancestor]},
        providers={ancestor["versionId"]: provider},
        split=split,
        contexts=contexts,
    )
    inputs = build_inputs([eligibility], [(fixture.game, split)])
    plan = build_plan(
        base_version_id=fixture.base["versionId"],
        base_manifest_sha256=ancestor["manifestSha256"],
        base_weights_sha256="e" * 64,
        cohorts=[
            {
                "gameId": fixture.game,
                "cohortId": fixture.cohort,
                "manifestSha256": snapshot.manifest_sha256,
            }
        ],
        train_eligibility_sha256=inputs["trainEligibility"]["sha256"],
        selection_roster_sha256=inputs["selectionRoster"]["sha256"],
        calibration_roster_sha256=inputs["calibrationRoster"]["sha256"],
        regression_roster_sha256=inputs["regressionRoster"]["sha256"],
    )
    return fixture, snapshot, inputs, plan


def test_real_selected_r3_export_install_and_lost_response_reuse(tmp_path, monkeypatch):
    torch.set_num_threads(1)
    fixture, snapshot, inputs, plan = actual_inputs(tmp_path, monkeypatch)
    from test_grid_content_experiment_evidence import evidence_fixture

    proof = evidence_fixture("R3", inputs_override=inputs, plan_override=plan)["provenance"][
        "contentExperiment"
    ]

    class Network(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.screen = ScreenNetwork(width=8)
            self.board = BoardNetwork(width=8, content_head=True)

    network = Network().eval()
    recipe_bytes = RECIPE_FILE.read_bytes()
    payload = json.loads(recipe_bytes)
    recipe = namespace(payload)
    bank = measure_bank(
        plan, inputs, [snapshot], torch_engine(network, recipe, "cpu"), lambda: None
    )
    proof["bank"] = bank
    state = {k: v for k, v in proof["state"].items() if k != "sha256"}
    state["bankSha256"] = bank["sha256"]
    job_id = uuid4()
    run = tmp_path / "grid-training" / "runs" / str(job_id)
    (run / "checkpoints").mkdir(parents=True)
    checkpoint = run / "checkpoints" / "selected.pt"
    torch.save({"model": network.state_dict(), "step": 1200, "bestStep": 200}, checkpoint)
    checksum = sha256_file(checkpoint)
    state["arms"]["R3"]["checkpointSha256"] = checksum
    proof["state"] = {**state, "sha256": digest(state)}
    train = CohortPhotos(snapshot, "TRAIN", full_only=True)
    refs = [
        ref for i in range(len(train)) for ref in content_references(train, i) if ref is not None
    ]
    contract = GridOutputContract(supervision=visibility_supervision(refs, game_ids=[fixture.game]))
    preset = SCREEN_GRID_CORRECTIONS_V1
    spec = {
        "format": "grid-training-spec-v1",
        "jobId": str(job_id),
        "preset": {"id": preset.preset_id, "fingerprint": preset.fingerprint},
        "base": {"versionId": plan["baseVersionId"], "weightsSha256": plan["baseWeightsSha256"]},
        "cohort": {
            "gameId": fixture.game,
            "cohortId": fixture.cohort,
            "manifestPath": fixture.manifest_pin["path"],
            "manifestSha256": snapshot.manifest_sha256,
        },
        "contentExperiment": plan,
        "contentExperimentInputs": inputs,
        "gridOutputContract": contract.model_dump(mode="json"),
    }
    write_json_atomic(run / "spec.json", {"payload": spec, "sha256": digest(spec)})
    result = SimpleNamespace(
        checkpoint_sha256=checksum,
        checkpoint_path=checkpoint,
        best_step=200,
        checkpoint_selection=state["arms"]["R3"]["selection"],
        visibility_exposure={"positiveTargets": 0, "negativeTargets": 0, "optimizerSteps": 0},
        exposure=proof["exposure"],
        content_head_exposure=proof["contentHeadExposure"],
    )
    validation = CohortPhotos(snapshot, "VALIDATION", full_only=False, content_selection=True)
    assert len(validation) == 1 and len(validation.targets(0)) == 1
    assert validation.rows[0][0]["validationPurpose"] == "A"
    # All actual A consumers now share the same explicit content-policy gate.
    ordinary = CohortPhotos(snapshot, "VALIDATION", full_only=False)
    assert len(ordinary.rows) == len(validation.rows)
    for (source, targets), (expected_source, expected_targets) in zip(
        ordinary.rows, validation.rows, strict=True
    ):
        assert source == expected_source
        for (nodes, weight), (expected_nodes, expected_weight) in zip(
            targets, expected_targets, strict=True
        ):
            np.testing.assert_array_equal(nodes, expected_nodes)
            assert weight == expected_weight
    crops, _ = validation_crops(validation, recipe)
    exported = _export(
        spec,
        run,
        network,
        recipe,
        payload,
        recipe_bytes,
        result,
        (crops, validation),
        content_experiment=proof,
        content_finalize=lambda p: p,
    )
    assert "content.onnx" in exported["files"]
    bundle = json.loads((run / exported["directory"] / "bundle.json").read_bytes())
    assert [p["boardCanvas"] for p in bundle["contentRescue"]["parity"]["cases"]] == [
        [320, 192],
        [480, 288],
    ]
    assert all(p["result"]["passed"] for p in bundle["contentRescue"]["parity"]["cases"])
    # Recovered export never invokes the network/exporter again, even after lost delivery.
    from game_predictor_worker.training_core import grid_training

    monkeypatch.setattr(
        grid_training, "export_graphs", lambda *a, **k: pytest.fail("duplicate export")
    )
    assert (
        _export(
            spec,
            run,
            network,
            recipe,
            payload,
            recipe_bytes,
            result,
            (crops, validation),
            content_experiment=proof,
            content_finalize=lambda p: p,
        )
        == exported
    )
    handler = GridTrainingJobHandler(
        None, artifact_root=tmp_path, python=None, pythonpath="", repository_root=tmp_path
    )
    job = SimpleNamespace(
        id=job_id,
        game_id=fixture.game,
        input_payload={
            "base_version_id": plan["baseVersionId"],
            "cohort_id": fixture.cohort,
            "preset_id": preset.preset_id,
            "content_experiment": plan,
        },
    )
    runtime = RunState(RunBudget.for_preset(preset, "train", content_experiment=plan))
    runtime.export = {**exported, "metric": "production-content-a-rank-v1", "bestMetric": 0.0}
    _, descriptor = handler._descriptor(job, runtime, fixture.base)
    handler._install(run, exported, descriptor)
    assert GridModelArtifactInspector(tmp_path).inspect(descriptor) == (
        True,
        "GRID_MODEL_ARTIFACT_AVAILABLE",
    )
    recovered = handler._verified_export_without_result(job, run)
    assert recovered["export"]["files"] == exported["files"]
    descriptor_path = tmp_path / "cold-descriptor.json"
    descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")
    cold = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json,sys; from pathlib import Path; "
            "from game_predictor_api.storage.grid_model_registry "
            "import GridModelArtifactInspector; "
            "p=Path(sys.argv[1]); assert GridModelArtifactInspector(p.parent).inspect("
            "json.loads(p.read_text()))[0]; print('cold-content-export-pass')",
            str(descriptor_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert "cold-content-export-pass" in cold.stdout
    graph = tmp_path / descriptor["managedDirectory"] / "content.onnx"
    graph.write_bytes(graph.read_bytes() + b"changed")
    assert GridModelArtifactInspector(tmp_path).inspect(descriptor)[0] is False
