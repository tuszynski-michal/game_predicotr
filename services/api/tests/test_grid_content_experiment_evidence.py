"""Closed export provenance, exact selected route and proposal-only admission boundary."""

from copy import deepcopy
from typing import Any

import pytest
from game_predictor_api.domain.grid_content_experiment_evidence import (
    require_content_experiment_evidence,
)
from game_predictor_api.domain.grid_content_experiment_inputs import sealed
from game_predictor_api.domain.grid_correction_evaluation import require_checkpoint_selection
from game_predictor_api.domain.grid_model_evaluation import GridEvaluationReportError
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_worker.geometry_core.rescue import GridRescueVariantV2
from game_predictor_worker.geometry_core.settings import BoardPreset
from game_predictor_worker.images.grid_rescue_strategy import completeness_routing
from game_predictor_worker.training_core.grid_content_experiment import (
    advance_state,
    init_state,
    select_winner,
    selection_record,
    start_arm,
)
from game_predictor_worker.training_core.grid_rescue_training import ContentTrainingExposure
from test_grid_content_experiment_inputs import inputs_fixture


def evidence_fixture(
    arm: str = "R2",
    passing: bool = True,
    *,
    inputs_override: dict[str, Any] | None = None,
    plan_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Synthetic metadata only; callers supply real graphs/files when testing inspection."""
    _, inputs, plan = inputs_fixture()
    inputs = inputs if inputs_override is None else inputs_override
    plan = plan if plan_override is None else plan_override
    game_id = plan["cohorts"][0]["gameId"]
    metrics = dict(
        photos=5,
        full_photos=5,
        partial_photos=0,
        boards_expected=45,
        boards_matched=45,
        boards_correct=45,
        board_correct_rate=1.0,
        detection_recall=1.0,
        normalized_error=0.01,
        photo_complete_correct=5,
        photo_complete_correct_rate=1.0,
        false_boards=0,
        duplicate_predictions=0,
    )
    bank = sealed(
        dict(
            schemaVersion="content-base-error-bank-v1",
            planSha256=plan["sha256"],
            baseWeightsSha256=plan["baseWeightsSha256"],
            trainEligibilitySha256=plan["trainEligibilitySha256"],
            games=[
                dict(
                    gameId=game_id,
                    eligibilitySha256=inputs["trainEligibility"]["games"][0]["sha256"],
                    reasonCodes=[],
                    sources=[
                        dict(source=s, metrics=metrics, detections=[])
                        for s in inputs["trainEligibility"]["games"][0]["sources"]
                    ],
                )
            ],
        )
    )
    state = init_state(plan, bank["sha256"])
    preflight = {}
    required = ["R0", "R1", "R2"] + (["R3"] if arm == "R3" or not passing else [])
    for current in required:
        good = passing and (current == arm or (arm in ("R0", "R1") and current == "R2"))
        damaged = 0 if good else 1
        counts = dict(
            preserved=675,
            borderline=0,
            clipped=0,
            missing=0,
            wrongCells=0,
            ties=0,
            foreignSymbols=0,
            ambiguousBoards=0,
            usableBoards=45,
        )
        content = dict(
            state="ready",
            reasonCodes=[],
            photos=5,
            fullPhotos=5,
            slots=675,
            visible=675,
            unknown=0,
            occluded=0,
            outOfFrame=0,
            referenceSha256="a" * 64,
            base=counts,
            candidate={
                **counts,
                "preserved": 675 - damaged,
                "clipped": damaged,
                "usableBoards": 45 - damaged,
            },
            degradedInstances=damaged,
            newWrongCells=0,
            newTies=0,
            newForeignSymbols=0,
            newMatchAmbiguities=0,
        )
        game = dict(
            gameId=game_id,
            u=0.02,
            delta=0.002,
            measurementSha256="b" * 64,
            quality=dict(
                photos=5,
                base=metrics,
                candidate={**metrics, "normalized_error": 0.009 if current == arm else 0.01},
            ),
            content=content,
            auxiliary=dict(
                baselineUsablePhotos=4,
                candidateUsablePhotos=4,
                newClipped=damaged,
                newBorderline=0,
                newDamagedInstances=damaged,
            ),
        )
        selection = selection_record([game], current, 200)
        state = start_arm(
            plan,
            state,
            current,
            feasible_seconds=128.0,
            r2_gate_passed=False if current == "R3" else None,
            human_labels_ready=True,
        )
        state = advance_state(
            plan,
            state,
            current,
            completed_steps=1200,
            charged_seconds=130.0,
            checkpoint_sha256="c" * 64,
            selection=selection,
            complete=True,
        )
        preflight[current] = dict(
            stepSeconds=0.1,
            validationSeconds=1.0,
            exportSeconds=2.0,
            estimatedSeconds=128.0,
            device="cpu",
        )
    state = select_winner(plan, state)
    assert state["selectedArm"] == arm
    exposure = ContentTrainingExposure(plan, arm)
    member = dict(
        gameId=game_id,
        sourceId=inputs["trainEligibility"]["games"][0]["sources"][0]["sourceId"],
        sourceSha256=inputs["trainEligibility"]["games"][0]["sources"][0]["sourceSha256"],
        cohortSha256=plan["cohorts"][0]["manifestSha256"],
    )
    exposure.confirm_components(
        1,
        screen_members=[member],
        board_members=[member],
        screen_canvas=(768, 576),
        board_canvas=(320, 192),
    )
    variant = arm in ("R2", "R3")
    if variant:
        exposure.confirm_components(
            2,
            screen_members=[member],
            board_members=[member],
            screen_canvas=(1280, 960),
            board_canvas=(480, 288),
        )
    proof = dict(
        plan=plan,
        inputs=inputs,
        state=state,
        bank=bank,
        selectedArm=arm,
        bestStep=200,
        exposure=exposure.state(),
        preflight=preflight,
        contentHeadExposure=(
            dict(quadTargets=15, localVisibilityTargets=15, optimizerSteps=1)
            if arm == "R3"
            else None
        ),
    )
    keys = [
        "board.nodes",
        "board.peak",
        "board.visibility",
        "screen.heat",
        "screen.offsets",
        *(("content.content_quads", "content.local_visibility") if arm == "R3" else ()),
    ]
    result = dict(
        tolerance=1e-4,
        toleranceScale="max(1,|torch|)",
        maxDelta={k: 0.0 for k in keys},
        maxScaledDelta={k: 0.0 for k in keys},
        passed=True,
    )
    cases = [
        dict(
            screenLongSide=768,
            boardCanvas=[320, 192],
            boardMargin=0.15,
            inputSha256s=dict(screen="d" * 64, board="e" * 64),
            result=result,
        )
    ]
    if variant:
        cases.append(
            {
                **deepcopy(cases[0]),
                "screenLongSide": 1280,
                "boardCanvas": [480, 288],
                "boardMargin": 0.30,
            }
        )
    parity = sealed(
        dict(
            schemaVersion="content-runtime-parity-v1",
            cases=cases,
            graphs={
                name: "f" * 64
                for name in [
                    "screen.onnx",
                    "board.onnx",
                    *(("content.onnx",) if arm == "R3" else ()),
                ]
            },
        )
    )
    rescue = sealed(
        dict(
            schemaVersion="content-rescue-evidence-v1",
            planSha256=plan["sha256"],
            selectedArm=arm,
            bestStep=200,
            variant=GridRescueVariantV2().model_dump(mode="json") if variant else None,
            selectedPath="combined" if variant else None,
            routing=completeness_routing(
                {"policy": "validation-purpose-a-v1", "sha256": plan["selectionRosterSha256"]},
                BoardPreset(
                    margin=0.15,
                    corner_jitter=0.0,
                    shift_jitter=0.0,
                    scale_jitter=0.0,
                    rotation_jitter_degrees=0.0,
                    boards_per_image=9,
                    coordinate_loss_weight=1.0,
                    heatmap_loss_weight=1.0,
                    heatmap_sigma=2.0,
                    visibility_loss_weight=1.0,
                ),
            )
            if variant
            else None,
            parity=parity,
        )
    )
    return dict(
        format="neural-grid-bundle-v2",
        model_version="neural-grid-v2",
        provenance=dict(
            contentExperiment=proof,
            checkpointSelection=state["arms"][arm]["selection"],
            bestStep=200,
            checkpointSha256="c" * 64,
        ),
        contentRescue=rescue,
    )


@pytest.mark.parametrize(
    "arm,passing", [("R0", True), ("R1", True), ("R2", True), ("R2", False), ("R3", True)]
)
def test_export_retains_exact_selected_route_even_when_proposal_only(arm, passing):
    bundle = evidence_fixture(arm, passing)
    proof = require_content_experiment_evidence(bundle)
    assert proof["state"]["arms"][arm]["selection"]["gatePassed"] is passing
    assert bundle["contentRescue"]["selectedPath"] == ("combined" if arm in ("R2", "R3") else None)


@pytest.mark.parametrize(
    "mutation", ["input", "bank", "checkpoint", "head", "parity", "route", "exposure", "budget"]
)
def test_tampered_export_is_not_accepted(mutation):
    bundle = evidence_fixture("R3")
    proof = bundle["provenance"]["contentExperiment"]
    if mutation == "input":
        proof["inputs"]["selectionRoster"]["games"][0]["sources"].clear()
    elif mutation == "bank":
        proof["bank"]["games"][0]["sources"].clear()
    elif mutation == "checkpoint":
        bundle["provenance"]["checkpointSha256"] = "e" * 64
    elif mutation == "head":
        proof["contentHeadExposure"]["quadTargets"] = 0
    elif mutation == "parity":
        bundle["contentRescue"]["parity"]["cases"][1]["result"]["passed"] = False
    elif mutation == "route":
        bundle["contentRescue"]["selectedPath"] = None
    elif mutation == "exposure":
        proof["exposure"]["games"].clear()
    else:
        proof["preflight"]["R3"]["estimatedSeconds"] = 2101.0
    with pytest.raises((ValueError, GridCohortError)):
        require_content_experiment_evidence(bundle)


def test_new_selection_requires_explicit_dispatch_and_legacy_default_stays_closed():
    selection = evidence_fixture()["provenance"]["checkpointSelection"]
    with pytest.raises(GridEvaluationReportError):
        require_checkpoint_selection(selection, screen=True)
    assert (
        require_checkpoint_selection(selection, screen=True, allow_content_selection=True)
        == selection
    )


def test_proposal_only_is_inspectable_but_cannot_supply_publication_evidence(tmp_path):
    import json

    from game_predictor_api.domain.grid_model_registry import GridModelRegistryError
    from game_predictor_api.storage.grid_model_registry import GridModelArtifactInspector

    bundle = evidence_fixture("R2", passing=False)
    (tmp_path / "candidate").mkdir()
    (tmp_path / "candidate/bundle.json").write_text(json.dumps(bundle))
    assert require_content_experiment_evidence(bundle)["selectedArm"] == "R2"
    with pytest.raises(GridModelRegistryError) as error:
        GridModelArtifactInspector(tmp_path).require_content_publication(
            {"modelVersion": "neural-grid-v2", "managedDirectory": "candidate"}
        )
    assert error.value.code == "CONTENT_EXPERIMENT_PROPOSAL_ONLY"


def test_resealed_parity_cannot_omit_a_visibility_output():
    bundle = evidence_fixture("R3")
    rescue = bundle["contentRescue"]
    parity = rescue["parity"]
    for case in parity["cases"]:
        for field in ("maxDelta", "maxScaledDelta"):
            del case["result"][field]["content.local_visibility"]
    rescue["parity"] = sealed({k: v for k, v in parity.items() if k != "sha256"})
    bundle["contentRescue"] = sealed({k: v for k, v in rescue.items() if k != "sha256"})
    with pytest.raises(ValueError, match="PARITY_INVALID"):
        require_content_experiment_evidence(bundle)
