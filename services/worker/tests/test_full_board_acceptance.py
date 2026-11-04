"""Whole-handler and runtime-boundary acceptance; synthetic CPU data, never NN quality."""

import copy
import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import numpy as np
import pytest
from game_predictor_api.domain.full_board_calibration import AssessedTarget
from game_predictor_api.domain.full_board_calibration_report import require_report
from game_predictor_api.domain.grid_model_registry import descriptor_sha256 as digest
from game_predictor_api.storage.full_board_calibration_evidence import (
    snapshot_assessment_references,
)
from game_predictor_worker.geometry_core.inference import BoardDetection, DecodeSettings
from game_predictor_worker.images.grid_cohort_dataset import GridBoardDataset
from game_predictor_worker.images.grid_model_evaluation_handler import GridModelEvaluationJobHandler
from game_predictor_worker.images.grid_training_child import RECIPE_FILE
from game_predictor_worker.training_core.grid_training import namespace
from test_grid_correction_evaluation_pipeline import correction
from test_grid_model_evaluation import Context, add_source, colour

pytest_plugins = ["test_grid_model_evaluation"]


def labels():
    return [
        np.array(
            [
                ((slot % 3) * 20 + 2 + c * 2, (slot // 3) * 15 + 2 + r * 2)
                for r in range(4)
                for c in range(6)
            ],
            np.float32,
        )
        for slot in range(9)
    ]


def detection(nodes):
    return BoardDetection(
        0.99,
        nodes[[0, 5, 23, 18]].copy(),
        nodes.copy(),
        nodes.copy(),
        np.ones(24),
        np.ones(24),
        0.0,
        0.0,
        24,
        [],
    )


@pytest.mark.parametrize("interrupt_after", ["VALIDATION", "REGRESSION"])
def test_grid_only_v4_real_handler_keeps_every_partial_a_target_and_raw_quality(
    scenario, interrupt_after
):
    s = scenario
    job = correction(s)
    lattice = labels()
    snapshots = {}
    for ordinal, (game, fixture) in enumerate(s.store.games.items()):
        b = add_source(fixture, "VALIDATION", 21 + ordinal)
        s.store.groups[game][b["sourceId"]] = b["sourceId"]
        pins = []
        for source in fixture.sources:
            source["targets"] = [copy.deepcopy(source["targets"][0]) for _ in range(3)]
            source["screenEligible"] = False
            purpose = "B" if source is b else "A" if source["role"] == "VALIDATION" else None
            source.update(validationPurpose=purpose, purposeProofSha256="d" * 64)
            for target, position in zip(source["targets"], (0, 4, 8), strict=True):
                target.update(
                    positionIndex=position,
                    sequenceNumber=17 + position,
                    nodes=[{"x": float(x), "y": float(y)} for x, y in lattice[position]],
                )
            pins.append(
                {
                    "sourceId": source["sourceId"],
                    "role": source["role"],
                    "validationPurpose": purpose,
                    "purposeProofSha256": "d" * 64,
                    "componentIds": [source["sourceId"]],
                    "representative": True,
                    "eligibleBoards": 3,
                }
            )
        split = {
            "schemaVersion": "grid-correction-split-v4",
            "sources": pins,
            "purposeCounts": {
                "VALIDATION-A": {"photos": 5, "boards": 15, "fullPhotos": 0},
                "VALIDATION-B": {"photos": 1, "boards": 3, "fullPhotos": 0},
            },
        }
        split["sha256"] = digest(split)
        snapshots[game] = fixture.publish(
            change=lambda root, split=split: root.update(
                schemaVersion="application-grid-snapshot-v4",
                policyVersion="application-grid-corrections-v4",
                photoSplit=split,
            )
        )
    recipe = json.loads(RECIPE_FILE.read_bytes())
    bundle_path = s.root / s.candidate["managedDirectory"] / "bundle.json"
    bundle = json.loads(bundle_path.read_bytes())
    bundle["preset"] = recipe
    bundle_bytes = json.dumps(bundle).encode()
    bundle_path.write_bytes(bundle_bytes)
    for entry in s.candidate["files"]:
        if entry["name"] == "bundle.json":
            entry.update(
                sha256=hashlib.sha256(bundle_bytes).hexdigest(), sizeBytes=len(bundle_bytes)
            )
    payload = copy.deepcopy(job.input_payload)
    payload["manifest_sha256"] = digest(s.candidate)
    for pin in payload["cohorts"]:
        pin["manifest_sha256"] = snapshots[pin["game_id"]].manifest_sha256
    job = dataclasses.replace(job, input_payload=payload)
    calls = []

    class Engine:
        settings = SimpleNamespace(board=DecodeSettings.of(namespace(recipe)).board)

        def __init__(self, base, call_log):
            self.base, self.call_log = base, call_log

        def analyse(self, rgb):
            self.call_log.append((self.base, colour(rgb)))
            missing = self.base and colour(rgb) == s.keys[s.training]["REGRESSION"][0]
            return [
                detection(nodes)
                for slot, nodes in enumerate(lattice)
                if not (missing and slot == 4)
            ]

    def factory(directory, _sha):
        return Engine(directory.name != "candidate", calls)

    reference_root = s.root.with_name(s.root.name + "-reference")
    shutil.copytree(s.root, reference_root)
    reference_store = copy.copy(s.store)
    reference_store.root, reference_store.reports, reference_store.proofs = reference_root, {}, []
    reference_calls = []
    GridModelEvaluationJobHandler(
        reference_store,
        reference_root,
        engine_factory=lambda directory, _sha: Engine(
            directory.name != "candidate", reference_calls
        ),
    )(Context(job), job)
    reference_report = next(iter(reference_store.reports.values()))

    class Interrupted(Exception):
        pass

    class InterruptingContext(Context):
        def checkpoint(self, **kwargs):
            super().checkpoint(**kwargs)
            state = kwargs["checkpoint_payload"]
            if f"{s.training}:{interrupt_after}" in state["units"] and s.training not in state.get(
                "automaticCalibration", {}
            ):
                raise Interrupted

    interrupted = InterruptingContext(job)
    with pytest.raises(Interrupted):
        GridModelEvaluationJobHandler(s.store, s.root, engine_factory=factory)(interrupted, job)
    assert s.store.reports == {}
    execution = s.root / "grid-model-evaluations" / str(job.id)
    assert not (execution / f"{s.training}-calibration-final.json").exists()
    if interrupt_after == "VALIDATION":
        assert not (execution / f"{s.training}-REGRESSION.json").exists()
    else:
        assert (execution / f"{s.training}-calibration-b.json").exists()
    persisted = {p.relative_to(s.root): p.read_bytes() for p in execution.glob("*.json")}
    completed_calls = Counter(calls)
    resumed = dataclasses.replace(job, checkpoint_payload=interrupted.states[-1])
    context = Context(resumed)
    GridModelEvaluationJobHandler(s.store, s.root, engine_factory=factory)(context, resumed)
    assert all((s.root / path).read_bytes() == content for path, content in persisted.items())
    assert all(Counter(calls)[key] == count for key, count in completed_calls.items())
    assert Counter(calls) == Counter(reference_calls)

    report_json, report_sha = next(iter(s.store.reports.values()))
    assert (report_json, report_sha) == reference_report
    report = require_report(report_json, manifest=s.candidate, base_sha256=digest(s.base))
    assert report["schemaVersion"] == "grid-model-evaluation-read-v5"
    assert report["rawQualitySchemaVersion"] == "grid-model-evaluation-read-v3"
    assert report["verdict"] == "PASS"
    assert len(report["automaticCalibration"]) == 2
    cold = []
    for game, snapshot in snapshots.items():
        frozen = snapshot_assessment_references(snapshot)
        detail_path = s.root / "grid-model-evaluations" / str(job.id) / f"{game}-VALIDATION.json"
        detail = json.loads(detail_path.read_bytes())
        observed = [
            AssessedTarget.model_validate(t)
            for photo in detail["photos"]
            for t in photo["calibrationTargets"]
        ]
        frozen.require_targets("A", observed)
        a_sources = {
            source["sourceId"] for source, _ in GridBoardDataset(snapshot, "VALIDATION").indexed()
        }
        assert len(observed) == 15 and {str(t.sourceId) for t in observed} == a_sources
        assert {t.positionIndex for t in observed} == {0, 4, 8}
        with pytest.raises(ValueError, match="FROZEN_TARGET_SET_CHANGED:A"):
            frozen.require_targets("A", observed[:-1])
        raw = next(g for g in report["games"] if g["gameId"] == game)
        for role in raw["roles"].values():
            assert role["candidate"]["boards_expected"] == 15
            assert role["candidate"]["full_photos"] == 0
            assert role["candidate"]["false_boards"] is None
            assert role["candidate"]["duplicate_predictions"] is None
            assert role["base"]["duplicate_predictions"] is None
        automatic = next(v for v in report["automaticCalibration"] if v["gameId"] == game)
        assert automatic["state"] == "unqualified" and automatic["profile"] is None
        assert "CALIBRATION_MINIMUM:baselineBadSources" in automatic["reasonCodes"]
        assert automatic["b"]["sources"] == 1 and automatic["b"]["targets"] == 3
        assert automatic["b"]["scope"] == automatic["regression"]["scope"] == "labelled_targets"
        final_path = automatic["evidence"]["path"]
        final_bytes = (s.root / final_path).read_bytes()
        assert final_bytes == (reference_root / final_path).read_bytes()
        final_result = json.loads(final_bytes)["payload"]["result"]
        assert final_result["assessmentScope"] == "labelled_targets"
        assert final_result["wholePhotoClaims"] is False
        cold.append(
            {
                "manifestPath": s.store.games[game].manifest_pin["path"],
                "manifestSha256": snapshot.manifest_sha256,
                "detailPath": detail_path.relative_to(s.root).as_posix(),
                "automatic": automatic,
            }
        )
    before = len(calls)
    restarted = dataclasses.replace(job, checkpoint_payload=context.states[-1])
    GridModelEvaluationJobHandler(s.store, s.root, engine_factory=factory)(
        Context(restarted), restarted
    )
    assert len(calls) == before and next(iter(s.store.reports.values())) == (
        report_json,
        report_sha,
    )
    process = subprocess.run(
        [sys.executable, "-c", COLD_READ],
        input=json.dumps(
            {
                "root": str(s.root),
                "snapshots": cold,
                "candidate": payload["manifest_sha256"],
                "base": digest(s.base),
                "workspace": str(Path(__file__).resolve().parents[3]),
            }
        ),
        text=True,
        capture_output=True,
        timeout=30,
        check=True,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                str(Path(__file__).resolve().parents[3] / path)
                for path in ("services/api/src", "services/worker/src")
            ),
        },
    )
    assert json.loads(process.stdout) == [15, 15]


COLD_READ = r"""
import json,sys
from pathlib import Path
from game_predictor_api.domain import full_board_calibration as calibration_module
from game_predictor_api.domain.full_board_calibration import AssessedTarget
from game_predictor_api.storage.full_board_calibration_evidence import (
    snapshot_assessment_references,require_calibration_evidence,
)
from game_predictor_worker.images.grid_cohort_dataset import GridCohortSnapshot
from game_predictor_worker.images import grid_cohort_dataset as dataset_module
body=json.load(sys.stdin)
root=Path(body['root'])
assert Path(calibration_module.__file__).resolve() == (
    Path(body['workspace'])/'services/api/src/game_predictor_api/domain/full_board_calibration.py'
).resolve(), 'Cold reader must load this worktree, not main.'
assert Path(dataset_module.__file__).resolve() == (
    Path(body['workspace'])/'services/worker/src/game_predictor_worker/images/grid_cohort_dataset.py'
).resolve(), 'Cold worker reader must load this worktree, not main.'
counts=[]
for item in body['snapshots']:
    snapshot=GridCohortSnapshot(root,item['manifestPath'],item['manifestSha256'])
    frozen=snapshot_assessment_references(snapshot)
    detail=json.loads((root/item['detailPath']).read_bytes())
    targets=[AssessedTarget.model_validate(t)
             for p in detail['photos'] for t in p['calibrationTargets']]
    frozen.require_targets('A',targets)
    require_calibration_evidence(root,item['automatic'],frozen=frozen,
        candidate_sha=body['candidate'],baseline_sha=body['base'])
    counts.append(len(targets))
print(json.dumps(counts))
"""


def test_actual_rescue_observation_sink_matches_a_routing_and_runtime_evidence(
    tmp_path, monkeypatch
):
    from game_predictor_api.domain.calibrated_neural_evidence import calibrated_result_blockers
    from game_predictor_api.domain.full_board_calibration import ReferenceTarget, make_plan
    from game_predictor_api.domain.full_board_calibration_report import AutomaticProfile
    from game_predictor_api.domain.grid_rescue_policy import POLICY, require_rescue_evidence
    from game_predictor_worker.geometry_core.rescue_serialization import detection_from_document
    from game_predictor_worker.images import full_board_runtime_evidence as evidence_module
    from game_predictor_worker.images.full_board_calibration_observations import CalibrationObserver
    from game_predictor_worker.images.full_board_completeness import (
        calibration_routing_sha,
        log_aspect,
    )
    from game_predictor_worker.images.full_board_runtime_evidence import runtime_evidence
    from game_predictor_worker.images.grid_rescue_assessment import RescueAssessmentEngine
    from game_predictor_worker.images.grid_rescue_evaluation import ScreenCorrectionEvaluator
    from game_predictor_worker.images.grid_rescue_runtime import run_with_rescue
    from game_predictor_worker.images.grid_training_data import CohortPhotos
    from game_predictor_worker.training_core.grid_correction_metrics import (
        CorrectionControlPhoto,
        measure_role,
    )
    from game_predictor_worker.training_core.grid_rescue_training import (
        TrainingExposure,
        rescue_recipe,
        selection_input,
    )
    from test_grid_cohort_dataset import SnapshotFixture
    from test_screen_rescue_contract import variant

    fixture, lattice = SnapshotFixture(tmp_path), labels()
    for role, count in (("TRAIN", 10), ("VALIDATION", 5)):
        for _ in range(count):
            source = fixture.source(role, full=True)
            source.update(
                validationPurpose="A" if role == "VALIDATION" else None, purposeProofSha256="d" * 64
            )
            for target, nodes in zip(source["targets"], lattice, strict=True):
                target["nodes"] = [{"x": float(x), "y": float(y)} for x, y in nodes]
    split = {
        "schemaVersion": "grid-correction-split-v4",
        "purposeCounts": {"VALIDATION-A": {"photos": 5, "boards": 45, "fullPhotos": 5}},
        "sources": [
            {
                "sourceId": s["sourceId"],
                "role": s["role"],
                "validationPurpose": s["validationPurpose"],
                "purposeProofSha256": "d" * 64,
                "componentIds": [s["sourceId"]],
                "sourceSha256": s["sourceIdentity"]["checksum_sha256"],
                "pixelSha256": s["sourceIdentity"]["normalized_pixel_checksum_sha256"],
                "qualifiedLabelsSha256": digest(s["targets"]),
                "representative": True,
                "eligibleBoards": 9,
            }
            for s in fixture.sources
        ],
    }
    split["sha256"] = digest(split)
    snapshot = fixture.publish(
        mode="screen+grid",
        change=lambda root: root.update(
            schemaVersion="application-grid-snapshot-v4",
            policyVersion="application-grid-corrections-v4",
            photoSplit=split,
        ),
    )
    preset = json.loads(RECIPE_FILE.read_bytes())
    selection = selection_input([(fixture.game, split)])
    recipe = rescue_recipe(
        hashlib.sha256(RECIPE_FILE.read_bytes()).hexdigest(),
        variant().model_dump(mode="json"),
        selection,
    )
    exposure = TrainingExposure(recipe)
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

    class Engine:
        settings = SimpleNamespace(board=DecodeSettings.of(namespace(preset)).board)

        def analyse(self, _rgb):
            found = [detection(nodes) for nodes in lattice]
            found[4].nodes += np.array([1.5, 0], np.float32)
            found[4].raw_nodes = found[4].nodes.copy()
            found[4].screen_quad[:2, 1] += 3
            return found

        def detect(self, _rgb, geometry=None):
            return [detection(nodes) for nodes in lattice]

        def recrop(self, _rgb, found, geometry=None):
            return detection(lattice[4])

    measured = ScreenCorrectionEvaluator(
        [CohortPhotos(snapshot, "VALIDATION", full_only=True)],
        namespace(preset),
        "cpu",
        variant(),
        selection,
        exposure,
    ).measure(Engine(), exposure.state())
    assert measured["selectedPath"] == "board_only"
    assert measured["pathProofs"]["board_only"]["cropCalls"] == 5
    # Only a trusted-metadata contract fixture, not newly measured graph parity.
    # T3's actual tiny ONNX parity remains the independent executed evidence.
    parity = {
        "contractVersion": "grid-rescue-parity-v1",
        "boardCanvas": [320, 192],
        "screenBounds": {"minimum": 64, "maximum": 2048, "multiple": 32},
        "graphs": {
            stage: {"sha256": char * 64, "dtype": "float32"}
            for stage, char in (("screen", "e"), ("board", "f"))
        },
        "inputs": [
            {
                "stage": "board",
                "path": "board_only",
                "shape": [1, 3, 192, 320],
                "inputSha256": "b" * 64,
                "verdict": {
                    "passed": True,
                    "tolerance": 1e-4,
                    "toleranceScale": "max(1,|torch|)",
                    "maxDelta": {f"board.{i}": 0.0 for i in range(3)},
                    "maxScaledDelta": {f"board.{i}": 0.0 for i in range(3)},
                },
            }
        ],
    }
    parity["sha256"] = digest(parity)
    provenance = {
        "runId": str(uuid4()),
        "bestStep": 2,
        "weightsSha256": "c" * 64,
        "checkpointSha256": "d" * 64,
        "trainingPresetFingerprint": "e" * 64,
        "snapshotId": snapshot.manifest_sha256,
    }
    proof = {
        "contractVersion": "grid-rescue-evidence-v1",
        "recipe": recipe,
        "selectionInput": selection,
        "trainingExposure": exposure.state(),
        "selection": measured,
        "parity": parity,
        **provenance,
    }
    proof["sha256"] = digest(proof)
    bundle = {
        "rescue": proof,
        "provenance": provenance,
        "preset": preset,
        "files": {"screen.onnx": "e" * 64, "board.onnx": "f" * 64},
    }
    assert require_rescue_evidence(bundle) == proof
    bundle_bytes = json.dumps(bundle).encode()
    (tmp_path / "bundle.json").write_bytes(bundle_bytes)
    bundle_sha = hashlib.sha256(bundle_bytes).hexdigest()
    routed = RescueAssessmentEngine(Engine(), proof)
    rows = GridBoardDataset(snapshot, "VALIDATION").indexed()
    aspect = log_aspect(lattice[0])
    observer = CalibrationObserver(
        game_id=fixture.game,
        sources={s["sourceId"]: s for s, _ in rows},
        game_aspect=aspect,
        routing=routed.routing,
    )
    photos = [
        CorrectionControlPhoto(
            s["sourceId"],
            s["sourceId"],
            s["original"]["sha256"],
            tuple(n for n, _ in targets),
            lambda s=s: snapshot.frame(s, "VALIDATION").rgb,
            True,
        )
        for s, targets in rows
    ]
    _, details = measure_role(photos, Engine(), routed, observation=observer)
    targets = [AssessedTarget.model_validate(t) for p in details for t in p["calibrationTargets"]]
    routing_sha = calibration_routing_sha(
        "a" * 64, Engine.settings.board, routed.routing, routed.path
    )
    plan = make_plan(
        [
            ReferenceTarget(
                gameId=t.gameId,
                sourceRepresentativeSha256=t.sourceRepresentativeSha256,
                positionIndex=t.positionIndex,
                role="VALIDATION-A",
                humanGood=t.candidateGood,
                features=t.candidateFeatures,
            )
            for t in targets
        ],
        game_id=UUID(fixture.game),
        candidate_sha="a" * 64,
        baseline_sha="b" * 64,
        routing_sha=routing_sha,
        role_proof_sha="c" * 64,
        b_assessment_sha="d" * 64,
        regression_assessment_sha="e" * 64,
    )
    # Synthetic qualified-pin witness exercises result binding, not B/REG admission.
    profile = {
        "version": "full-board-auto-profile-v1",
        "gameId": fixture.game,
        "candidateManifestSha256": "a" * 64,
        "planSha256": plan.sha256,
        "sealedSha256": "f" * 64,
        "routingSha256": routing_sha,
        "configuration": plan.menu[0],
        "gameLogAspectReference": aspect,
        "assessmentScope": "labelled_targets",
    }
    profile["sha256"] = digest(profile)
    AutomaticProfile.model_validate(profile)
    operation_pin = {
        "contractVersion": "neural-grid-operation-pin-v3",
        "pinSha256": "c" * 64,
        "catalogueManifestSha256": "a" * 64,
        "automaticQualification": {"state": "qualified", "profile": profile},
    }
    rescue_pin = {
        "policyVersion": POLICY,
        "variantId": variant().sha256,
        "variant": variant().model_dump(mode="json"),
        "selectedPath": "board_only",
        "bundleSha256": bundle_sha,
        "proofSha256": proof["sha256"],
        "publicationEvidenceSha256": "f" * 64,
    }
    source, _ = rows[0]
    rgb = snapshot.frame(source, "VALIDATION").rgb
    calls = []

    class Runner:
        def run(self, _bundle, _sha, rgb, **kwargs):
            calls.append("baseline")
            return Engine().analyse(rgb)

        def run_stage(self, _bundle, _sha, rgb, *, request, **kwargs):
            calls.append(request["kind"])
            return [Engine().recrop(rgb, detection_from_document(request["detection"]))]

    args = dict(
        runner=Runner(),
        bundle=tmp_path,
        bundle_sha=bundle_sha,
        rgb=rgb,
        heartbeat=lambda: None,
        max_seconds=30,
        directory=tmp_path / "rescue",
        source_sha=source["sourceIdentity"]["checksum_sha256"],
        pin=rescue_pin,
        expected_positions=set(range(9)),
    )
    actual, summary = {}, {}
    found = run_with_rescue(**args, observation_sink=actual, summary_sink=summary)
    assert calls == ["baseline", "board"] and actual["cropPositions"] == [4]
    assert actual["selectedPath"] == routed.path and actual["routing"] == routed.routing
    assert actual["boardGeometry"] == routed.variant.board
    expected = routed.analyse(rgb)
    for runtime, assessment in zip(found, expected, strict=True):
        np.testing.assert_array_equal(runtime.nodes, assessment.nodes)
    documents = [
        {"detectionId": str(i), "latticeNodes": item.nodes.tolist()} for i, item in enumerate(found)
    ]
    evidence_args = dict(
        found=found,
        detections=documents,
        pin=operation_pin,
        bundle=tmp_path,
        bundle_sha=bundle_sha,
        source_sha=args["source_sha"],
        width=64,
        height=48,
        available_source_box=[0, 0, 64, 48],
    )
    real_support, support_calls = evidence_module.input_support, []

    def observe_support(quad, board, geometry):
        support_calls.append((np.asarray(quad).copy(), geometry))
        return real_support(quad, board, geometry)

    monkeypatch.setattr(evidence_module, "input_support", observe_support)
    evidence = runtime_evidence(**evidence_args, observation=actual)
    unchanged = [
        geometry
        for quad, geometry in support_calls
        if np.array_equal(quad, lattice[0][[0, 5, 23, 18]])
    ]
    assert unchanged == [None]
    assert "rescueDisagreement" in evidence["0"]["features"]["notApplicable"]
    assert evidence["0"]["features"]["values"]["rescueDisagreement"] is None
    assert "COMPLETENESS_RESCUE_REQUIRED" not in evidence["0"]["features"]["hardReasons"]
    assert (
        calibrated_result_blockers(
            evidence["4"],
            pin=operation_pin,
            proposal={"sourceChecksumSha256": args["source_sha"]},
            detection=documents[4],
        )
        == ()
    )
    for field, value in (
        ("selectedPath", "combined"),
        ("routing", {**actual["routing"], "selectionInputSha256": "0" * 64}),
    ):
        changed = {**actual, field: value}
        assert runtime_evidence(**evidence_args, observation=changed) == {}
    replay_sink, replay_summary = {}, {}
    replay = run_with_rescue(**args, observation_sink=replay_sink, summary_sink=replay_summary)
    assert calls == ["baseline", "board"] and summary == replay_summary
    assert replay_sink["cropPositions"] == [4]
    replay_evidence = runtime_evidence(
        **{**evidence_args, "found": replay}, observation=replay_sink
    )
    assert replay_evidence["0"] == evidence["0"]
    for first, again in zip(found, replay, strict=True):
        np.testing.assert_array_equal(first.nodes, again.nodes)
    alias_sink = {}
    run_with_rescue(**{**args, "expected_positions": {4, 5}}, observation_sink=alias_sink)
    assert alias_sink == {} and calls == ["baseline", "board"]
    assert runtime_evidence(**evidence_args, observation=alias_sink) == {}
    changed_bundle = copy.deepcopy(bundle)
    changed_bundle["preset"]["board"]["margin"] += 0.01
    changed_bytes = json.dumps(changed_bundle).encode()
    (tmp_path / "bundle.json").write_bytes(changed_bytes)
    assert (
        runtime_evidence(
            **{**evidence_args, "bundle_sha": hashlib.sha256(changed_bytes).hexdigest()},
            observation=actual,
        )
        == {}
    )
