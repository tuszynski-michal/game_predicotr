"""Bounded CPU fixtures prove contracts; they are not B/REG model evidence."""

from copy import deepcopy

import pytest
from game_predictor_api.domain.grid_model_registry import descriptor_sha256 as digest
from game_predictor_worker.images.grid_cohort_dataset import (
    GridAssessmentDataset,
    GridBoardDataset,
    GridCohortDatasetError,
)
from game_predictor_worker.images.grid_rescue_strategy import completeness_routing, execute_path
from test_full_board_input_diagnostics import sample  # noqa: F401
from test_grid_cohort_dataset import SnapshotFixture
from test_screen_rescue_contract import detection, variant


def test_only_new_frozen_routing_spends_existing_attempt_on_missing_input_cells(sample):  # noqa: F811
    baseline = [detection(position, bad=False) for position in range(9)]
    baseline[4].screen_quad[:2, 1] += 20
    board = sample[1].board_preset.model_copy(update={"margin": 0.0})
    route = completeness_routing({"policy": "validation-purpose-a-v1", "sha256": "a" * 64}, board)
    calls = []
    args = dict(
        width=400,
        height=400,
        variant=variant(),
        path="board_only",
        detect=lambda _: pytest.fail("Board path cannot redetect."),
        recrop=lambda position, *_: calls.append(position) or detection(position, bad=False),
    )
    assert execute_path(baseline, **args).crop_calls == {}
    result = execute_path(baseline, routing=route, **args)
    assert result.crop_calls == {4: 1} and calls == [4]
    invalid = deepcopy(route)
    invalid["coverageEpsilon"] = 0.5
    with pytest.raises(ValueError, match="ROUTING_PROOF"):
        execute_path(baseline, routing=invalid, **args)
    assert calls == [4]


def purpose_snapshot(tmp_path):
    fixture = SnapshotFixture(tmp_path)
    a, b, reg = (
        fixture.source("VALIDATION"),
        fixture.source("VALIDATION"),
        fixture.source("REGRESSION"),
    )
    for source, purpose in ((a, "A"), (b, "B"), (reg, None)):
        source.update(
            validationPurpose=purpose,
            purposeProofSha256="d" * 64,
            assessmentPolicy="human-labeled-targets-v1"
            if purpose == "B" or purpose is None
            else None,
        )
    split = {
        "schemaVersion": "grid-correction-split-v4",
        "purposeCounts": {
            "VALIDATION-A": {"photos": 1, "boards": 1, "fullPhotos": 0},
            "VALIDATION-B": {"photos": 1, "boards": 1, "fullPhotos": 0},
        },
        "sources": [
            {
                "sourceId": source["sourceId"],
                "role": source["role"],
                "validationPurpose": source["validationPurpose"],
                "representative": True,
                "purposeProofSha256": "d" * 64,
                "eligibleBoards": 1,
                "componentIds": [],
            }
            for source in (a, b, reg)
        ],
    }
    split["sha256"] = digest(split)

    def change(root):
        root.update(
            schemaVersion="application-grid-snapshot-v4",
            policyVersion="application-grid-corrections-v4",
            photoSplit=split,
        )

    snapshot = fixture.publish(change=change)
    return snapshot, (a, b, reg)


def test_changed_raster_cannot_reuse_rescue_baseline_or_replenish_attempts(tmp_path):
    from game_predictor_worker.geometry_core.bounded_runtime import GeometryRuntimeError
    from game_predictor_worker.images.grid_rescue_runtime import RescueAttemptStore

    identity = {
        "sourceSha256": "a" * 64,
        "positions": [0],
        "inputRaster": {"pixelSha256": "b" * 64, "validBox": [0, 0, 100, 100]},
    }
    first = RescueAttemptStore(tmp_path, identity)
    first.baseline(lambda: [detection(0)])
    first.attempt("crop-0", {"geometry": "same"}, lambda: [detection(0, bad=False)])
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    for raster in (
        {"pixelSha256": "c" * 64, "validBox": [0, 0, 100, 100]},
        {"pixelSha256": "b" * 64, "validBox": [0, 20, 100, 100]},
    ):
        changed = RescueAttemptStore(tmp_path, {**identity, "inputRaster": raster})
        with pytest.raises(GeometryRuntimeError, match="changed raster"):
            changed.baseline(lambda: pytest.fail("Changed raster must not run a new baseline."))
        assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


@pytest.mark.parametrize("output_v2", [False, True])
def test_runtime_uses_attested_available_box_not_padded_original_canvas(
    tmp_path,
    sample,  # noqa: F811
    output_v2,
):
    import hashlib
    import json

    import numpy as np
    from game_predictor_api.domain.calibrated_neural_evidence import calibrated_result_blockers
    from game_predictor_api.domain.full_board_calibration import AXES, MINIMUM_AXES
    from game_predictor_worker.images.full_board_runtime_evidence import runtime_evidence
    from test_full_board_completeness import detection as measured_detection

    found = [measured_detection(10 + c * 80, 10 + r * 60) for r in range(3) for c in range(3)]
    if not output_v2:
        # Historical v1 fixture explicitly preserves the old 24-value interpretation.
        for item in found:
            item.visibility = np.ones(24)
    documents = [
        {"detectionId": str(i), "latticeNodes": item.nodes.tolist()} for i, item in enumerate(found)
    ]
    board = sample[1].board_preset
    bundle = {"preset": {"board": board.model_dump(mode="json")}}
    axes = AXES
    if output_v2:
        from game_predictor_api.domain.full_board_calibration import AXES_V2
        from game_predictor_api.domain.grid_visibility_contract import GridOutputContract
        from test_grid_visibility_contract import qualified

        axes = AXES_V2
        bundle.update(
            format="neural-grid-bundle-v2",
            model_version="neural-grid-v2",
            provenance={
                "bestStep": 1,
                "visibilityExposure": {
                    "positiveTargets": 1,
                    "negativeTargets": 1,
                    "optimizerSteps": 1,
                },
            },
            gridOutputContract=GridOutputContract(
                supervision=qualified(), trainedVisibility=True
            ).model_dump(mode="json"),
        )
    raw = json.dumps(bundle).encode()
    (tmp_path / "bundle.json").write_bytes(raw)
    profile = {
        "version": "full-board-auto-profile-v2" if output_v2 else "full-board-auto-profile-v1",
        "sha256": "a" * 64,
        "gameLogAspectReference": 0.0,
        "configuration": {
            axis: 0.0 if axis in MINIMUM_AXES or axis == "inputEdgeClearance" else 10.0
            for axis in axes
        },
        "routingSha256": digest(
            {
                "recognitionManifestSha256": "b" * 64,
                "boardPreset": board.model_dump(mode="json"),
                "routing": None,
                "selectedPath": None,
            }
        ),
    }
    pin = {
        "contractVersion": "neural-grid-operation-pin-v3",
        "pinSha256": "c" * 64,
        "catalogueManifestSha256": "b" * 64,
        "automaticQualification": {"state": "qualified", "profile": profile},
    }
    args = dict(
        found=found,
        detections=documents,
        observation={},
        pin=pin,
        bundle=tmp_path,
        bundle_sha=hashlib.sha256(raw).hexdigest(),
        source_sha="d" * 64,
        width=300,
        height=220,
    )
    assert runtime_evidence(**args) == {}  # unknown mapping is not full support
    full = runtime_evidence(**args, available_source_box=[0, 0, 300, 220])
    assert (
        calibrated_result_blockers(
            full["0"], pin=pin, proposal={"sourceChecksumSha256": "d" * 64}, detection=documents[0]
        )
        == ()
    )
    cropped = runtime_evidence(**args, available_source_box=[0, 20, 300, 220])
    assert "COMPLETENESS_PIXELS_MISSING" in calibrated_result_blockers(
        cropped["0"], pin=pin, proposal={"sourceChecksumSha256": "d" * 64}, detection=documents[0]
    )

    # The observer must receive the attested extent of the exact frame analysed by both
    # engines; v1 keeps its historical feature/SHA semantics when this metadata is added.
    from dataclasses import replace
    from types import SimpleNamespace
    from uuid import UUID

    from game_predictor_api.domain.grid_visibility_contract import require_output_contract
    from game_predictor_worker.images.full_board_calibration_observations import CalibrationObserver
    from game_predictor_worker.images.grid_cohort_dataset import frame_rgb_and_box
    from game_predictor_worker.training_core.grid_correction_metrics import (
        CorrectionControlPhoto,
        measure_role,
    )

    class Engine:
        settings = SimpleNamespace(board=board)
        output_contract = require_output_contract(bundle) if output_v2 else None

        def analyse(self, rgb):
            return found

    source_id = str(UUID(int=11))
    observer = CalibrationObserver(
        game_id=str(UUID(int=12)),
        game_aspect=0.0,
        routing=None,
        role="VALIDATION-A",
        routing_sha="e" * 64,
        sources={
            source_id: {
                "sourceId": source_id,
                "sourceIdentity": {"normalized_pixel_checksum_sha256": "d" * 64},
                "targets": [{"positionIndex": index} for index in range(9)],
            }
        },
    )
    rgb = np.zeros((220, 300, 3), np.uint8)
    photo = CorrectionControlPhoto(
        source_id,
        "group",
        "f" * 64,
        tuple(item.nodes for item in found),
        lambda: rgb,
        full_geometry=True,
    )

    def observed(box):
        calls = []

        def load_with_support():
            calls.append(1)
            left, top, right, bottom = box
            return frame_rgb_and_box(
                SimpleNamespace(
                    rgb=rgb,
                    crop=SimpleNamespace(
                        valid_box=SimpleNamespace(
                            left=left,
                            top=top,
                            right=right,
                            bottom=bottom,
                        )
                    ),
                )
            )

        control = photo if box is None else replace(photo, load_with_support=load_with_support)
        _, rows = measure_role([control], Engine(), Engine(), observation=observer)
        assert len(calls) == (0 if box is None else 1)
        return rows[0]["calibrationTargets"][0]["candidateFeatures"]

    missing, whole, padded = observed(None), observed((0, 0, 300, 220)), observed((0, 20, 300, 220))
    if output_v2:
        assert padded == cropped["0"]["features"]
        assert padded["values"]["inputEdgeClearance"] < whole["values"]["inputEdgeClearance"]
        assert missing["values"]["inputEdgeClearance"] is None
        assert "COMPLETENESS_PIXEL_SUPPORT_REQUIRED" in missing["hardReasons"]
    else:
        assert missing == whole == padded
        assert digest(missing) == digest(whole) == digest(padded)


def test_v4_partial_b_survives_assessment_and_is_inaccessible_to_legacy_selection(tmp_path):
    snapshot, (a, b, reg) = purpose_snapshot(tmp_path)
    assert [
        source["sourceId"] for source, _ in GridBoardDataset(snapshot, "VALIDATION").indexed()
    ] == [a["sourceId"]]
    assessment = GridAssessmentDataset(snapshot, "VALIDATION")
    assert assessment[0]["sourceId"] == b["sourceId"]
    with pytest.raises(GridCohortDatasetError, match="Legacy validation"):
        snapshot.frame(b, "VALIDATION")
    assert len(GridAssessmentDataset(snapshot, "REGRESSION")) == 1


def test_existing_screen_evaluator_exercises_new_a_routing_and_excludes_b(tmp_path):
    import hashlib
    import json
    from copy import deepcopy
    from types import SimpleNamespace
    from uuid import UUID, uuid4

    import numpy as np
    from game_predictor_api.domain.calibrated_neural_evidence import calibrated_result_blockers
    from game_predictor_api.domain.full_board_calibration import (
        AssessedTarget,
        ReferenceTarget,
        assess_regression,
        make_plan,
        seal_b,
    )
    from game_predictor_worker.geometry_core.inference import BoardDetection, DecodeSettings
    from game_predictor_worker.images.full_board_calibration_run import FullBoardCalibrationRun
    from game_predictor_worker.images.full_board_runtime_evidence import runtime_evidence
    from game_predictor_worker.images.grid_model_evaluation_handler import _write_atomic
    from game_predictor_worker.images.grid_rescue_assessment import RescueAssessmentEngine
    from game_predictor_worker.images.grid_rescue_evaluation import ScreenCorrectionEvaluator
    from game_predictor_worker.images.grid_training_child import RECIPE_FILE
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
    from game_predictor_worker.training_core.grid_training import namespace

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
    for purpose in ["A"] * 5 + ["B"]:
        source = fixture.source("VALIDATION", full=True)
        source.update(
            validationPurpose=purpose,
            purposeProofSha256="d" * 64,
            assessmentPolicy="human-labeled-targets-v1" if purpose == "B" else None,
        )
        for target, nodes in zip(source["targets"], labels, strict=True):
            target["nodes"] = [{"x": float(x), "y": float(y)} for x, y in nodes]
    pins = [
        {
            "sourceId": s["sourceId"],
            "role": "VALIDATION",
            "validationPurpose": s["validationPurpose"],
            "sourceSha256": s["sourceIdentity"]["checksum_sha256"],
            "pixelSha256": s["sourceIdentity"]["normalized_pixel_checksum_sha256"],
            "qualifiedLabelsSha256": digest(s["targets"]),
            "componentIds": [],
            "representative": True,
            "eligibleBoards": 9,
            "purposeProofSha256": "d" * 64,
        }
        for s in fixture.sources
    ]
    split = {
        "schemaVersion": "grid-correction-split-v4",
        "sources": pins,
        "purposeCounts": {
            "VALIDATION-A": {"photos": 5, "boards": 45, "fullPhotos": 5},
            "VALIDATION-B": {"photos": 1, "boards": 9, "fullPhotos": 1},
        },
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
    selection = selection_input([(fixture.game, split)])
    assert len(selection["games"][0]["sources"]) == 5
    assert fixture.sources[-1]["sourceId"] not in {
        s["sourceId"] for s in selection["games"][0]["sources"]
    }
    recipe = namespace(json.loads(RECIPE_FILE.read_bytes()))
    exposure = TrainingExposure(
        rescue_recipe("a" * 64, variant().model_dump(mode="json"), selection)
    )
    member = {
        "gameId": fixture.game,
        "sourceId": "synthetic-training",
        "sourceSha256": "b" * 64,
        "cohortSha256": snapshot.manifest_sha256,
    }
    exposure.confirm(1, [member])
    exposure.confirm(2, [member])

    def found(index, bad=False):
        item = BoardDetection(0.99, labels[index][[0, 5, 23, 18]].copy())
        item.nodes = labels[index].copy() + (np.array([1.5, 0], np.float32) if bad else 0)
        item.raw_nodes = item.nodes.copy()
        item.node_peak, item.visibility = np.ones(24), np.ones(24)
        item.fit_residual, item.fit_max_error, item.fit_inliers = 0.0, 0.0, 24
        if bad:
            item.screen_quad[:2, 1] += 3  # fitted cells outside the real board input
        return item

    class Engine:
        settings = SimpleNamespace(board=DecodeSettings.of(recipe).board)

        def analyse(self, _):
            return [found(i, i == 4) for i in range(9)]

        def detect(self, _, geometry=None):
            return [found(i) for i in range(9)]

        def recrop(self, _, detection, geometry=None):
            return found(4)

    evaluator = ScreenCorrectionEvaluator(
        [CohortPhotos(snapshot, "VALIDATION", full_only=True)],
        recipe,
        "cpu",
        variant(),
        selection,
        exposure,
    )
    measured = evaluator.measure(Engine(), exposure.state())
    proof = measured["pathProofs"]["board_only"]
    assert proof["admittedOnA"] and proof["cropCalls"] == 5
    assert proof["routing"]["selectionInputSha256"] == selection["sha256"]
    assert proof["routingPolicy"] == "grid-rescue-exact-slots-input-completeness-v2"
    assert measured["selectedPath"] == "board_only"
    # Same A-selected path, real assessment wrapper and archived board preset feed
    # calibration and runtime. Controlled detections replace NN, not routing/SHA.
    bundle = {
        "preset": json.loads(RECIPE_FILE.read_bytes()),
        "rescue": {"selection": measured, "recipe": {"variant": variant().model_dump(mode="json")}},
    }
    bundle_bytes = json.dumps(bundle).encode()
    (tmp_path / "bundle.json").write_bytes(bundle_bytes)
    routed = RescueAssessmentEngine(Engine(), bundle["rescue"])
    run = FullBoardCalibrationRun(
        root=tmp_path,
        job_id=uuid4(),
        snapshot=snapshot,
        candidate_sha="a" * 64,
        baseline_sha="b" * 64,
        engines=(Engine(), routed),
        write=_write_atomic,
    )
    source, targets = run.rows["A"][0]
    rgb = snapshot.frame(source, "VALIDATION").rgb
    photo = CorrectionControlPhoto(
        source["sourceId"],
        source["sourceId"],
        source["original"]["sha256"],
        tuple(nodes for nodes, _ in targets),
        lambda: rgb,
        True,
    )
    _, observations = measure_role(
        [photo], Engine(), routed, observation=run.observer("VALIDATION")
    )
    actual = [AssessedTarget.model_validate(t) for t in observations[0]["calibrationTargets"]]
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
            for t in actual
        ],
        game_id=UUID(fixture.game),
        candidate_sha="a" * 64,
        baseline_sha="b" * 64,
        routing_sha=run.routing_sha,
        role_proof_sha=run.role_proof,
        b_assessment_sha=run.references["B"],
        regression_assessment_sha=run.references["REGRESSION"],
    )
    # Numeric 30/30 observations exercise final profile selection; they are not a
    # claim of independent human data or the target-set test (covered separately).
    controls = [
        actual[0].model_copy(
            update={
                "sourceId": UUID(int=i + 1),
                "sourceRepresentativeSha256": f"{i + 1:064x}",
                "positionIndex": slot,
                "groundTruthSha256": f"{2 * i + slot:064x}",
                "baselineGood": bool(slot),
                "baselineT0Accepted": bool(slot),
                "candidateGood": True,
                "candidateCropped": False,
            }
        )
        for i in range(30)
        for slot in (0, 1)
    ]
    sealed = seal_b(plan, controls)
    regression = [
        t.model_copy(
            update={
                "sourceId": UUID(int=t.sourceId.int + 100),
                "sourceRepresentativeSha256": f"{t.sourceId.int + 100:064x}",
            }
        )
        for t in controls
    ]
    assert assess_regression(plan, sealed, regression)["state"] == "qualified"
    profile = dict(
        version="full-board-auto-profile-v1",
        gameId=fixture.game,
        candidateManifestSha256="a" * 64,
        planSha256=plan.sha256,
        sealedSha256=sealed["sha256"],
        routingSha256=plan.routingSha256,
        configuration=sealed["configuration"],
        gameLogAspectReference=run.aspect,
        assessmentScope="labelled_targets",
    )
    profile["sha256"] = digest(profile)
    pin = dict(
        contractVersion="neural-grid-operation-pin-v3",
        pinSha256="c" * 64,
        catalogueManifestSha256="a" * 64,
        automaticQualification={"state": "qualified", "profile": profile},
    )
    result = routed.analyse(rgb)
    assert routed.last_result.crop_calls == {4: 1}
    documents = [
        {"detectionId": str(i), "latticeNodes": item.nodes.tolist()}
        for i, item in enumerate(result)
    ]
    observation = dict(
        baseline=routed.last_baseline,
        cropPositions=list(routed.last_result.crop_calls),
        selectedPath=routed.path,
        routing=routed.routing,
        boardGeometry=routed.variant.board,
    )
    evidence = runtime_evidence(
        found=result,
        detections=documents,
        observation=observation,
        pin=pin,
        bundle=tmp_path,
        bundle_sha=hashlib.sha256(bundle_bytes).hexdigest(),
        source_sha="d" * 64,
        width=rgb.shape[1],
        height=rgb.shape[0],
        available_source_box=[0, 0, rgb.shape[1], rgb.shape[0]],
    )
    assert (
        calibrated_result_blockers(
            evidence["0"],
            pin=pin,
            proposal={"sourceChecksumSha256": "d" * 64},
            detection=documents[0],
        )
        == ()
    )
    drift = deepcopy(observation)
    drift["selectedPath"] = "combined"
    assert (
        runtime_evidence(
            found=result,
            detections=documents,
            observation=drift,
            pin=pin,
            bundle=tmp_path,
            bundle_sha=hashlib.sha256(bundle_bytes).hexdigest(),
            source_sha="d" * 64,
            width=rgb.shape[1],
            height=rgb.shape[0],
            available_source_box=[0, 0, rgb.shape[1], rgb.shape[0]],
        )
        == {}
    )
    changed = deepcopy(selection)
    changed["games"][0]["sources"].append({"sourceId": fixture.sources[-1]["sourceId"]})
    with pytest.raises(ValueError, match="SELECTION_INPUT_DRIFT"):
        ScreenCorrectionEvaluator(
            [CohortPhotos(snapshot, "VALIDATION", full_only=True)],
            recipe,
            "cpu",
            variant(),
            changed,
            exposure,
        )


@pytest.mark.parametrize("output_v2", [False, True])
def test_calibration_phases_resume_without_reobserving_b_or_tuning_regression(
    tmp_path,
    sample,  # noqa: F811
    output_v2,
):
    import json
    from types import SimpleNamespace
    from uuid import uuid4

    import numpy as np
    from game_predictor_api.storage.full_board_calibration_evidence import (
        require_calibration_evidence,
    )
    from game_predictor_worker.geometry_core.inference import BoardDetection
    from game_predictor_worker.images.full_board_calibration_run import FullBoardCalibrationRun
    from game_predictor_worker.images.grid_model_evaluation_handler import _write_atomic
    from game_predictor_worker.training_core.grid_correction_metrics import (
        CorrectionControlPhoto,
        measure_role,
    )

    snapshot, (a, _, _) = purpose_snapshot(tmp_path)
    nodes = np.array([[p["x"], p["y"]] for p in a["targets"][0]["nodes"]], np.float32)

    class Engine:
        def __init__(self):
            self.calls = 0
            self.settings = SimpleNamespace(board=sample[1].board_preset)
            if output_v2:
                from game_predictor_api.domain.grid_visibility_contract import (
                    GridOutputContract,
                    visibility_supervision,
                )

                self.output_contract = GridOutputContract(supervision=visibility_supervision([]))

        def analyse(self, _rgb):
            self.calls += 1
            return [
                BoardDetection(
                    1.0,
                    nodes[[0, 5, 23, 18]].copy(),
                    nodes.copy(),
                    nodes.copy(),
                    np.ones(24),
                    np.ones(15 if output_v2 else 24),
                    0.0,
                    0.0,
                    24,
                    [],
                )
            ]

    engines = Engine(), Engine()
    job = uuid4()
    args = dict(
        root=tmp_path,
        job_id=job,
        snapshot=snapshot,
        candidate_sha="a" * 64,
        baseline_sha="b" * 64,
        engines=engines,
        write=_write_atomic,
    )
    run = FullBoardCalibrationRun(**args)

    def measure(role):
        key = "A" if role == "VALIDATION" else role
        photos = [
            CorrectionControlPhoto(
                source["sourceId"],
                source["sourceId"],
                source["original"]["sha256"],
                tuple(n for n, _ in targets),
                lambda source=source: snapshot.frame(source, role).rgb,
                False,
            )
            for source, targets in run.rows[key]
        ]
        _, rows = measure_role(photos, *engines, observation=run.observer(role))
        path = tmp_path / "grid-model-evaluations" / str(job) / f"{run.game}-{role}.json"
        _write_atomic(
            path, json.dumps({"jobId": str(job), "gameId": run.game, "photos": rows}).encode()
        )

    measure("VALIDATION")
    run.prepare_b(lambda _: None)
    assert engines[0].calls == engines[1].calls == 2
    assert run._path("plan").exists() and run._path("b").exists()
    measure("REGRESSION")
    summary = run.finish()
    assert summary["state"] == "unqualified" and summary["b"]["sources"] == 1
    resumed = FullBoardCalibrationRun(**args)
    resumed.prepare_b(lambda _: pytest.fail("B must not run again."))
    assert resumed.finish() == summary
    assert engines[0].calls == engines[1].calls == 3
    assert (
        require_calibration_evidence(
            tmp_path, summary, frozen=run.frozen, candidate_sha="a" * 64, baseline_sha="b" * 64
        )
        == summary
    )
    from game_predictor_api.domain.full_board_calibration import (
        AssessedTarget,
        CalibrationPlan,
        seal_b,
    )

    b_path = run._path("b")
    original_b = b_path.read_bytes()
    prepared = run._read(run._path("plan"))
    plan = CalibrationPlan.model_validate(prepared["plan"])
    for fault in ("removed", "replaced", "duplicate"):
        body = json.loads(original_b)["payload"]
        if fault == "removed":
            body["targets"].clear()
        elif fault == "replaced":
            body["targets"][0]["groundTruthSha256"] = "9" * 64
        else:
            body["targets"].append(deepcopy(body["targets"][0]))
        body["sealed"] = seal_b(plan, [AssessedTarget.model_validate(t) for t in body["targets"]])
        b_path.write_text(json.dumps({"payload": body, "sha256": digest(body)}), encoding="utf-8")
        with pytest.raises(ValueError, match="FROZEN_TARGET_SET_CHANGED:B"):
            resumed.prepare_b(lambda _: pytest.fail("Corrupt B must not renew attempts."))
        with pytest.raises(ValueError, match="FROZEN_TARGET_SET_CHANGED:B"):
            resumed.finish()
    b_path.write_bytes(original_b)
    for role in ("VALIDATION", "REGRESSION"):
        detail = tmp_path / "grid-model-evaluations" / str(job) / f"{run.game}-{role}.json"
        original = detail.read_bytes()
        for fault in ("removed", "replaced", "duplicate"):
            body = json.loads(original)
            values = body["photos"][0]["calibrationTargets"]
            if fault == "removed":
                values.clear()
            elif fault == "replaced":
                values[0]["sourceId"] = str(uuid4())
            else:
                values.append(deepcopy(values[0]))
            detail.write_text(json.dumps(body), encoding="utf-8")
            with pytest.raises(ValueError, match="FROZEN_TARGET_SET_CHANGED"):
                if role == "VALIDATION":
                    resumed.prepare_b(lambda _: pytest.fail("Corrupt A must not read B."))
                else:
                    resumed.finish()
        detail.write_bytes(original)
    assert resumed.finish() == summary
    assert engines[0].calls == engines[1].calls == 3
