"""Joined frozen pixels -> observer/calibration/replay; controlled detections, no ORT/GPU."""

import hashlib
import json
import os
import subprocess
import sys
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from game_predictor_api.domain.canonical_source import decode_canonical_source_bytes
from game_predictor_api.domain.grid_cell_content import ContentRevision, content_source_identity
from game_predictor_api.domain.grid_training_cohorts import digest, exact_lattice
from game_predictor_api.domain.grid_visibility_contract import (
    GridOutputContract,
    VisibilitySupervision,
)
from game_predictor_api.storage.full_board_calibration_evidence import (
    require_calibration_evidence,
    snapshot_assessment_references,
)
from game_predictor_worker.geometry_core.inference import BoardDetection
from game_predictor_worker.geometry_core.settings import ScreenPreset
from game_predictor_worker.images.full_board_variant_calibration_run import VariantCalibrationRun
from game_predictor_worker.images.full_board_variant_context import (
    resolve_final_stage,
)
from game_predictor_worker.images.grid_content_experiment_data import ContentAssessmentEngine
from game_predictor_worker.images.grid_model_evaluation_handler import (
    GridModelEvaluationJobHandler,
    _write_atomic,
)
from game_predictor_worker.images.grid_rescue_strategy import completeness_routing
from game_predictor_worker.images.production_cell_input import engine_input_context
from game_predictor_worker.images.production_cell_run import ProductionContentRun
from PIL import Image
from test_grid_model_evaluation import Context
from test_production_cell_frozen_pipeline import frozen_fixture
from test_production_cell_observations import board_preset


def physical_fixture(root, count=30, *, combined=True):
    fixture, _, templates = frozen_fixture(root)
    fixture.sources = []
    by_colour = {}
    for _role, purpose, amount, template in (
        ("VALIDATION", "A", 4, templates[0]),
        ("VALIDATION", "B", count, templates[1]),
        ("REGRESSION", None, count, templates[2]),
    ):
        for _ in range(amount):
            ordinal = len(fixture.sources) + 1
            stream = BytesIO()
            Image.new("RGB", (192, 160), (ordinal * 3, 70, 90)).save(
                stream, format="JPEG", quality=100, subsampling=0
            )
            raw = stream.getvalue()
            import hashlib

            sha = hashlib.sha256(raw).hexdigest()
            decoded = decode_canonical_source_bytes(raw, expected_source_checksum_sha256=sha)
            canonical = decoded.source
            source = deepcopy(template)
            source.update(sourceId=str(uuid4()), screenEligible=False, targets=[])
            source["sourceIdentity"].update(
                checksum_sha256=sha,
                normalized_pixel_checksum_sha256=canonical.normalized_pixel_checksum_sha256,
                oriented_width=192,
                oriented_height=160,
                exif_orientation=canonical.exif_orientation,
            )
            source["original"] = fixture.pin(
                f"{fixture.directory}/originals/variant-{ordinal}.jpg", raw
            )
            for position in range(9):
                offset = np.array([10 + 60 * (position % 3), 10 + 50 * (position // 3)])
                target = deepcopy(template["targets"][0])
                nodes = np.array([[p["x"], p["y"]] for p in target["nodes"]]) + offset
                target.update(
                    positionIndex=position,
                    sequenceNumber=17 + position,
                    nodes=[{"x": float(x), "y": float(y)} for x, y in nodes],
                )
                annotation = deepcopy(target["contentAnnotation"])
                annotation["source"] = content_source_identity(
                    {**source["sourceIdentity"], "id": source["sourceId"]}
                ).model_dump(mode="json")
                annotation["sequenceNumber"] = target["sequenceNumber"]
                annotation["reference"].update(
                    positionIndex=position,
                    sourceRepresentativeSha256=canonical.normalized_pixel_checksum_sha256,
                )
                for cell in annotation["reference"]["cells"]:
                    cell["quad"] = (np.array(cell["quad"]) + offset).tolist()
                if purpose == "A" and ordinal <= 3 and position in (0, 4):
                    # Human symbol extends beyond a fitted cell while all nodes
                    # still fit the narrower input: a real, non-triggered cut.
                    annotation["reference"]["cells"][0]["quad"][0][0] = float(offset[0])
                    annotation["reference"]["cells"][0]["quad"][3][0] = float(offset[0])
                if purpose == "A":
                    annotation["measuredNodes"] = nodes.tolist()
                parsed = ContentRevision.model_validate(annotation)
                target.update(
                    contentAnnotation=parsed.model_dump(mode="json"),
                    contentReferenceSha256=parsed.sha256,
                )
                reference = target["productionContentReference"]
                reference["sourceContext"]["sequenceRangeEnd"] = 25
                reference["sourceContextSha256"] = digest(reference["sourceContext"])
                reference["sha256"] = digest({k: v for k, v in reference.items() if k != "sha256"})
                if purpose == "A":
                    target["blindGeometry"].update(
                        contentReferenceSha256=parsed.sha256, nodesSha256=digest(target["nodes"])
                    )
                    _, target["render"]["cellQuads"] = exact_lattice(
                        {"latticeNodes": target["nodes"]}, 192, 160
                    )
                source["targets"].append(target)
            wanted = (0, 1, 2, 3, 4, 5) if purpose == "A" else (0, 1, 2, 3)
            if not combined:
                wanted = (0, 2, 4) if purpose == "A" else (0, 2)
            source["targets"] = [t for t in source["targets"] if t["positionIndex"] in wanted]
            fixture.sources.append(source)
            colour = int(decoded.rgb[0, 0, 0])
            assert colour not in by_colour
            by_colour[colour] = source
    split = {
        "schemaVersion": "grid-correction-split-v4",
        "purposeCounts": {
            "VALIDATION-A": {"photos": 4, "boards": 24 if combined else 12, "fullPhotos": 0},
            "VALIDATION-B": {
                "photos": count,
                "boards": (4 if combined else 2) * count,
                "fullPhotos": 0,
            },
        },
        "sources": [
            {
                "sourceId": s["sourceId"],
                "role": s["role"],
                "validationPurpose": s["validationPurpose"],
                "representative": True,
                "purposeProofSha256": "d" * 64,
                "eligibleBoards": len(s["targets"]),
                "componentIds": [],
            }
            for s in fixture.sources
        ],
        "contentSampling": {
            "policy": "full-symbol-content-sampling-v1",
            "state": "ready",
            "sourceIds": [s["sourceId"] for s in fixture.sources if s["role"] == "REGRESSION"],
        },
    }
    split["sha256"] = digest(split)
    snapshot = fixture.publish(
        mode="screen+grid",
        change=lambda d: d.update(
            schemaVersion="application-grid-snapshot-v4",
            policyVersion="application-grid-corrections-v4",
            photoSplit=split,
        ),
    )
    return fixture, snapshot, by_colour


class Predict:
    def __init__(self, sources, *, base=False, combined=True, force_failure=False):
        self.sources, self.base, self.combined = sources, base, combined
        self.calls = 0
        self.force_failure = force_failure
        self.cut_ids = {s["sourceId"] for s in list(sources.values())[:3]}
        self.settings = SimpleNamespace(
            board=board_preset(0.15),
            screen=ScreenPreset(
                heat_sigma_fraction=0.1,
                min_heat_sigma=1,
                offset_scale=1,
                positive_radius=0.2,
                offset_loss_weight=1,
                decode_threshold=0.5,
                nms_iou=0.3,
                top_k=32,
            ),
        )
        # Controlled already-trained metadata; this test does not claim actual training.
        counts = dict(positiveCells=40, negativeCells=35, positivePhotos=5, negativePhotos=5)
        game = next(iter(sources.values()))["targets"][0]["contentAnnotation"]["reference"][
            "gameId"
        ]
        self.output_contract = GridOutputContract(
            trainedVisibility=True,
            supervision=VisibilitySupervision(
                **counts, referencesSha256="f" * 64, games={game: counts}
            ),
        )

    def _detection(self, source, position, *, final=False):
        nodes = np.array(
            [
                [7 * c + 1 + 10 + 60 * (position % 3), 8 * r + 1 + 10 + 50 * (position // 3)]
                for r in range(4)
                for c in range(6)
            ],
            np.float32,
        )
        nodes[8, 0] += 0.375
        if self.base and position in (2, 3, 6, 7):
            nodes += np.array([3, 0], np.float32)
        quad = nodes[[0, 5, 23, 18]].copy()
        wide = self.combined and position in (1, 3, 5, 7)
        cut = source["sourceId"] in self.cut_ids and position in (0, 1, 4, 5)
        if cut and ((not wide) or final):
            scale = 0.4 if wide or self.force_failure else 0.8
            quad = quad.mean(axis=0) + (quad - quad.mean(axis=0)) * scale
        reasons = ["NEURAL_GRID_FIT_FAILED"] if wide and not self.base and not final else []
        peak = 0.8 if wide and final else 0.6
        return BoardDetection(
            1.0, quad, nodes, nodes.copy(), np.full(24, peak), np.ones(15), 0.0, 0.0, 24, reasons
        )

    def analyse(self, rgb):
        self.calls += 1
        source = self.sources[int(rgb[0, 0, 0])]
        return [
            self._detection(source, p)
            for p in range(9)
            if p != getattr(self, "drop_position", None)
        ]

    def detect(self, rgb, **kwargs):
        return self.analyse(rgb)

    def recrop(self, rgb, detection, **kwargs):
        source = self.sources[int(rgb[0, 0, 0])]
        centers = [self._detection(source, p).nodes.mean(axis=0) for p in range(9)]
        position = int(
            np.argmin([np.linalg.norm(detection.screen_quad.mean(axis=0) - c) for c in centers])
        )
        if source["sourceId"] in self.cut_ids and position in (0, 4):
            return None  # actual attempted-but-failed crop stays BASE
        return self._detection(source, position, final=True)


def execute_fixture(root, *, count=30, combined=True, drop_position=None):
    import cv2

    cv2.setNumThreads(1)
    fixture, snapshot, sources = physical_fixture(root, count, combined=combined)
    base, core = Predict(sources, base=True), Predict(sources, combined=combined)
    core.drop_position = drop_position
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api/tests"))
    from test_grid_content_experiment_evidence import evidence_fixture
    from test_grid_model_registry import candidate as model_descriptor

    bundle = evidence_fixture("R2" if combined else "R0")
    routing = (
        completeness_routing(
            {
                "policy": "validation-purpose-a-v1",
                "sha256": bundle["provenance"]["contentExperiment"]["plan"][
                    "selectionRosterSha256"
                ],
            },
            core.settings.board,
        )
        if combined
        else None
    )
    bundle["contentRescue"]["routing"] = routing
    bundle["contentRescue"]["sha256"] = digest(
        {k: v for k, v in bundle["contentRescue"].items() if k != "sha256"}
    )
    bundle["preset"] = {
        "screen": core.settings.screen.model_dump(mode="json"),
        "board": core.settings.board.model_dump(mode="json"),
    }
    bundle["gridOutputContract"] = core.output_contract.model_dump(mode="json")
    bundle["provenance"]["visibilityExposure"] = {
        "positiveTargets": 40,
        "negativeTargets": 35,
        "optimizerSteps": 1,
    }
    manifest = model_descriptor(root)
    manifest.update(modelVersion="neural-grid-v2", bundleFormat="neural-grid-bundle-v2")
    manifest["inferenceManifest"].update(
        modelVersion="neural-grid-v2", bundleFormat="neural-grid-bundle-v2"
    )
    bundle_data = json.dumps(bundle, sort_keys=True).encode()
    bundle_dir = root / manifest["managedDirectory"]
    (bundle_dir / "bundle.json").write_bytes(bundle_data)
    for files in (
        manifest["files"],
        manifest["inferenceManifest"]["files"],
        manifest["trainingArtifacts"],
    ):
        for file in files:
            if file["name"] == "bundle.json":
                file.update(
                    sha256=hashlib.sha256(bundle_data).hexdigest(), sizeBytes=len(bundle_data)
                )
    candidate_sha = digest(manifest)
    candidate = ContentAssessmentEngine(core, routing) if combined else core
    engines = (base, candidate)
    job = SimpleNamespace(
        id=uuid4(),
        input_payload={"evaluation_kind": "grid-correction-evaluation-v1"},
        cancel_requested_at=None,
    )
    run = VariantCalibrationRun(
        root=root,
        job_id=job.id,
        snapshot=snapshot,
        candidate_sha=candidate_sha,
        baseline_sha="b" * 64,
        engines=engines,
        write=_write_atomic,
    )
    handler = GridModelEvaluationJobHandler(None, root, threads=1)
    state = {"units": {}, "reportSha256": None, "proven": []}
    groups = {s["sourceId"]: s["sourceId"] for s in sources.values()}
    for role in ("VALIDATION", "REGRESSION"):
        print("variant phase", role, flush=True)
        if role == "REGRESSION":
            run.prepare_b(lambda _: None)
        handler._measure_unit(
            Context(job),
            job,
            state,
            1,
            {"game_id": fixture.game, "cohort_id": fixture.cohort},
            role,
            snapshot,
            groups,
            engines,
            run,
            ProductionContentRun(snapshot),
        )
    result = run.finish()
    print("variant finished; independent replay", flush=True)
    frozen = snapshot_assessment_references(
        snapshot, input_context=engine_input_context(candidate), variant_contexts=run.contexts
    )
    assert (
        require_calibration_evidence(
            root, result, frozen=frozen, candidate_sha=candidate_sha, baseline_sha="b" * 64
        )
        == result
    )
    case = {
        "schemaVersion": "test-variant-physical-case-v1",
        "root": str(root),
        "snapshotPath": f"{fixture.directory}/manifest.json",
        "snapshotSha": snapshot.manifest_sha256,
        "result": result,
        "contexts": run.contexts,
        "inputContext": engine_input_context(candidate),
        "manifest": manifest,
        "jobId": str(job.id),
    }
    case["sha256"] = digest(case)
    (root / "variant-case.json").write_text(json.dumps(case), encoding="utf-8")
    return fixture, snapshot, run, result, engines


def test_joined_real_pixels_separate_variants(tmp_path):
    _, _, run, result, engines = execute_fixture(tmp_path)
    assert result["state"] == "qualified", result["reasonCodes"]
    assert len(result["usedVariantKeys"]) == 2
    peaks = sorted(v["profile"]["configuration"]["peak"] for v in result["variants"])
    assert peaks == pytest.approx([0.6, 0.8])


def test_joined_none_route_needs_only_used_baseline(tmp_path):
    _, _, _, result, _ = execute_fixture(tmp_path, combined=False)
    assert result["state"] == "qualified", result["reasonCodes"]
    assert len(result["allowedVariants"]) == len(result["usedVariantKeys"]) == 1
    assert result["allowedVariants"][0]["stage"] == "baseline"


def test_joined_missing_detection_preserves_full_roster(tmp_path):
    _, _, run, result, _ = execute_fixture(tmp_path, count=1, combined=False, drop_position=0)
    assert result["state"] == "unqualified"
    assert "VARIANT_BINDING_UNRESOLVED" in result["reasonCodes"]
    prepared = run._read(run._path("plan"))
    assert len(prepared["selectionReferences"]) == 12
    missing = [r for r in prepared["selectionReferences"] if r["target"]["positionIndex"] == 0]
    assert len(missing) == 4
    assert all(r["variantKey"] is None and r["witness"] is None for r in missing)


def test_actual_failed_recrop_and_mixed_stage_binding(tmp_path):
    _, snapshot, sources = physical_fixture(tmp_path, 1)
    core = Predict(sources, force_failure=True)
    route = completeness_routing(
        {"policy": "validation-purpose-a-v1", "sha256": "c" * 64}, core.settings.board
    )
    engine = ContentAssessmentEngine(core, route)
    source = next(iter(sources.values()))
    found = engine.analyse(snapshot.frame(source, "VALIDATION", validation_purpose="A").rgb)
    assert 0 in engine.last_result.crop_calls and 0 not in engine.last_result.replacement_positions
    assert (
        resolve_final_stage(
            found[0],
            0,
            engine.last_baseline,
            engine.last_result.replacement_positions,
            combined=True,
        )
        == "baseline"
    )
    assert (
        resolve_final_stage(
            found[1],
            1,
            engine.last_baseline,
            engine.last_result.replacement_positions,
            combined=True,
        )
        == "wide"
    )
    assert resolve_final_stage(found[1], 1, engine.last_baseline, (), combined=True) is None


def test_saved_joined_case_cold_replay_and_runtime():
    """Second bounded phase consumes, never rewrites, the successful frozen fixture."""
    from game_predictor_api.domain.calibrated_neural_evidence import calibrated_result_blockers
    from game_predictor_api.domain.neural_grid_operation_pin import make_operation_pin
    from game_predictor_api.domain.neural_grid_proposal import NeuralGridSnapshot
    from game_predictor_worker.images.full_board_runtime_evidence import runtime_evidence
    from game_predictor_worker.images.grid_cohort_dataset import GridCohortSnapshot

    path = os.environ.get("GAME_PREDICTOR_VARIANT_CASE")
    if path is None:
        pytest.skip("Explicit durable first-phase fixture is required")
    case = json.loads(Path(path).read_text(encoding="utf-8"))
    assert case["schemaVersion"] == "test-variant-physical-case-v1"
    assert case["sha256"] == digest({k: v for k, v in case.items() if k != "sha256"})
    root = Path(case["root"])
    script = """
import json,sys
from pathlib import Path
from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_api.storage.full_board_calibration_evidence import (
    snapshot_assessment_references, require_calibration_evidence,
)
from game_predictor_worker.images.grid_cohort_dataset import GridCohortSnapshot
from game_predictor_worker.images.full_board_variant_context import manifest_variant_contexts
c=json.loads(Path(sys.argv[1]).read_text());root=Path(c['root'])
s=GridCohortSnapshot(root,c['snapshotPath'],c['snapshotSha'])
contexts=manifest_variant_contexts(root,c['manifest'])
assert contexts==c['contexts']
f=snapshot_assessment_references(s,input_context=c['inputContext'],variant_contexts=contexts)
assert require_calibration_evidence(
    root,c['result'],frozen=f,candidate_sha=digest(c['manifest']),baseline_sha='b'*64
)==c['result']
print('cold physical replay PASS',flush=True)
"""
    cold = subprocess.run(
        [sys.executable, "-c", script, path], capture_output=True, text=True, timeout=90
    )
    assert cold.returncode == 0, cold.stdout + cold.stderr
    print(cold.stdout, flush=True)
    snapshot = GridCohortSnapshot(root, case["snapshotPath"], case["snapshotSha"])
    sources = {}
    for source in snapshot.sources():
        role = source["role"]
        frame = snapshot.frame(
            source,
            role,
            validation_purpose=source.get("validationPurpose") if role == "VALIDATION" else None,
        )
        sources[int(frame.rgb[0, 0, 0])] = source
    source = next(s for s in sources.values() if s["role"] == "REGRESSION")
    game = case["result"]["gameId"]
    bundle_dir = root / case["manifest"]["managedDirectory"]
    raw = (bundle_dir / "bundle.json").read_bytes()
    bundle = json.loads(raw)
    core = Predict(sources)
    engine = ContentAssessmentEngine(core, bundle["contentRescue"]["routing"])
    found = engine.analyse(snapshot.frame(source, "REGRESSION").rgb)
    docs = [
        {
            "detectionId": str(uuid4()),
            "latticeNodes": [{"x": float(x), "y": float(y)} for x, y in d.nodes],
        }
        for d in found
    ]
    publication = "e" * 64
    rescue = {
        "policyVersion": "grid-content-rescue-policy-v1",
        "variantId": engine.variant.sha256,
        "variant": bundle["contentRescue"]["variant"],
        "selectedPath": "combined",
        "bundleSha256": hashlib.sha256(raw).hexdigest(),
        "proofSha256": bundle["contentRescue"]["sha256"],
        "publicationEvidenceSha256": publication,
    }
    model = NeuralGridSnapshot.from_catalogue(
        game_id=game,
        game_configuration="neural_grid_v3",
        expected_layout_count=9,
        descriptor=case["manifest"],
    )
    pin = make_operation_pin(
        snapshot=model,
        game_id=game,
        rules_version_id=str(uuid4()),
        rows=3,
        columns=5,
        qualification={
            "state": "qualified",
            "reasonCodes": [],
            "evaluationId": str(uuid4()),
            "evaluationSha256": "d" * 64,
            "publicationEvidenceSha256": publication,
        },
        rescue=rescue,
        automatic_qualification={
            "state": "qualified",
            "reasonCodes": [],
            "reportId": str(uuid4()),
            "reportSha256": digest(case["result"]),
            "profile": case["result"]["profile"],
        },
    )
    observation = {
        "baseline": engine.last_baseline,
        "cropPositions": engine.last_result.crop_calls,
        "replacementPositions": engine.last_result.replacement_positions,
        "selectedPath": "combined",
        "routing": engine.routing,
        "boardGeometry": engine.variant.board,
    }
    source_sha = source["sourceIdentity"]["checksum_sha256"]
    evidence = runtime_evidence(
        found=found,
        detections=docs,
        observation=observation,
        pin=pin,
        bundle=bundle_dir,
        bundle_sha=hashlib.sha256(raw).hexdigest(),
        source_sha=source_sha,
        width=192,
        height=160,
        available_source_box=[0, 0, 192, 160],
    )
    proposal = {"sourceChecksumSha256": source_sha, "sourceWidth": 192, "sourceHeight": 160}
    for index in range(4):
        assert (
            calibrated_result_blockers(
                evidence[docs[index]["detectionId"]],
                pin=pin,
                proposal=proposal,
                detection=docs[index],
            )
            == ()
        )
    for index in (0, 1):
        value = deepcopy(evidence[docs[index]["detectionId"]])
        value["features"]["values"]["peak"] = 0.7
        value["sha256"] = digest({k: v for k, v in value.items() if k != "sha256"})
        blockers = calibrated_result_blockers(
            value, pin=pin, proposal=proposal, detection=docs[index]
        )
        assert bool(blockers) == (index == 1)
    stale = deepcopy(evidence[docs[1]["detectionId"]])
    stale["variantProfileSha256"] = "a" * 64
    stale["sha256"] = digest({k: v for k, v in stale.items() if k != "sha256"})
    assert calibrated_result_blockers(stale, pin=pin, proposal=proposal, detection=docs[1]) == (
        "COMPLETENESS_VARIANT_PROFILE_CHANGED",
    )
    for field in ("boardInputSupport", "sourceSha256", "variantKey"):
        changed = deepcopy(docs[1])
        stamp = changed["inputVariant"]
        if field == "boardInputSupport":
            stamp[field][0][0] += 1
        elif field == "sourceSha256":
            stamp[field] = "f" * 64
        else:
            stamp[field] = docs[0]["inputVariant"]["variantKey"]
        stamp["sha256"] = digest({k: v for k, v in stamp.items() if k != "sha256"})
        assert calibrated_result_blockers(
            evidence[docs[1]["detectionId"]], pin=pin, proposal=proposal, detection=changed
        )
    # Internally valid prior BASE proof, same node/ID, different actual WIDE trace.
    old = deepcopy(evidence[docs[1]["detectionId"]])
    old["features"] = deepcopy(evidence[docs[0]["detectionId"]]["features"])
    base_child = next(
        v
        for v in pin["automaticQualification"]["profile"]["variants"]
        if v["variantKey"] == docs[0]["inputVariant"]["variantKey"]
    )
    old["variantKey"] = base_child["variantKey"]
    old["variantProfileSha256"] = base_child["profile"]["sha256"]
    old_stamp = deepcopy(docs[1]["inputVariant"])
    old_stamp["variantKey"] = old["variantKey"]
    from game_predictor_worker.images.full_board_completeness import input_support

    old_stamp["boardInputSupport"] = input_support(
        found[1].screen_quad, core.settings.board
    ).tolist()
    old_stamp["sha256"] = digest({k: v for k, v in old_stamp.items() if k != "sha256"})
    old["inputVariantSha256"] = old_stamp["sha256"]
    old["sha256"] = digest({k: v for k, v in old.items() if k != "sha256"})
    old_doc = {**docs[1], "inputVariant": old_stamp}
    assert calibrated_result_blockers(old, pin=pin, proposal=proposal, detection=old_doc) == ()
    assert calibrated_result_blockers(old, pin=pin, proposal=proposal, detection=docs[1]) == (
        "COMPLETENESS_INPUT_VARIANT_CHANGED",
    )


def test_replacement_metadata_does_not_change_legacy_receipt_bytes(tmp_path):
    from game_predictor_worker.geometry_core.rescue_serialization import detection_document
    from game_predictor_worker.images.grid_rescue_runtime import RescueAttemptStore
    from game_predictor_worker.images.grid_rescue_strategy import RescueResult
    from game_predictor_worker.training_core.grid_training_admission import canonical
    from test_screen_rescue_contract import detection

    item = detection(4, bad=False)
    result = RescueResult([item], 1, {4: 1}, (), (4,))
    identity = {"operation": "legacy", "source": "a"}
    reservation = {"state": "reserved", "request": {"geometry": 0.2}}
    payload = {"reservationSha256": digest(reservation), "detections": [detection_document(item)]}
    store = RescueAttemptStore(tmp_path, identity)
    store.attempt("crop-4", reservation["request"], lambda: result.detections)
    for name, body in (("reserved", reservation), ("result", payload)):
        expected = {"identity": identity, "payload": body}
        expected["sha256"] = digest(expected)
        assert (tmp_path / f"crop-4.{name}.json").read_bytes() == canonical(expected)

    def forbidden():
        raise AssertionError("Receipt replay must not repeat work")

    assert (
        RescueAttemptStore(tmp_path, identity).attempt("crop-4", reservation["request"], forbidden)
        is not None
    )
