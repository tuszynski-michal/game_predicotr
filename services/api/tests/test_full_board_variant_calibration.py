"""Controlled numeric observations exercise thresholds, not operator/model qualification."""

import json
from copy import deepcopy
from uuid import UUID

import pytest
from game_predictor_api.domain.full_board_calibration import AXES_V2
from game_predictor_api.domain.full_board_variant_calibration import (
    assess_variant_regression,
    build_variant_qualification,
    make_variant_plan,
    require_variant_plan,
    seal_variant_b,
)
from game_predictor_api.domain.full_board_variant_calibration_types import (
    VariantAutomaticCalibration,
)
from game_predictor_api.domain.full_board_variant_context import make_variant_context
from game_predictor_api.domain.grid_model_registry import descriptor_sha256 as digest
from game_predictor_worker.geometry_core.settings import BoardPreset, ScreenPreset
from game_predictor_worker.images.grid_training_child import RECIPE_FILE

GAME = UUID(int=11)


def _seal(body):
    return {**body, "sha256": digest(body)}


def stamp_fixture(context, detection):
    import numpy as np
    from game_predictor_worker.geometry_core.rescue import BoardCropGeometryV2
    from game_predictor_worker.images.full_board_completeness import input_support

    quad = np.array([[10.0, 10.0], [110.0, 10.0], [110.0, 70.0], [10.0, 70.0]], np.float32)
    geometry = (
        None
        if context["boardGeometry"] is None
        else BoardCropGeometryV2.model_validate(context["boardGeometry"])
    )
    support = input_support(quad, BoardPreset.model_validate(context["boardPreset"]), geometry)
    return _seal(
        {
            "version": "full-board-input-variant-v1",
            "variantKey": context["sha256"],
            "sourceSha256": "c" * 64,
            "modelManifestSha256": "a" * 64,
            "operationPinSha256": "b" * 64,
            "detectionId": detection["detectionId"],
            "nodesSha256": digest(detection["latticeNodes"]),
            "screenQuad": quad.tolist(),
            "boardInputSupport": support.tolist(),
            "availableSourceBox": [0, 0, 1000, 1000],
        }
    )


def contexts_fixture(combined=True):
    recipe = json.loads(RECIPE_FILE.read_text(encoding="utf-8"))
    board = BoardPreset.model_validate(recipe["board"]).model_dump(mode="json")
    screen = ScreenPreset.model_validate(recipe["screen"]).model_dump(mode="json")
    route = {"fixture": "fixed"} if combined else None
    path = "combined" if combined else None
    route_sha = digest(
        {
            "recognitionManifestSha256": "a" * 64,
            "boardPreset": board,
            "routing": route,
            "selectedPath": path,
        }
    )
    contexts = [
        make_variant_context(
            candidateManifestSha256="a" * 64,
            routingSha256=route_sha,
            selectedPath=path,
            stage=stage,
            screenPreset=screen,
            boardPreset=board,
            screenGeometry=None
            if stage == "baseline"
            else {"longSide": 1280, "trainCanvas": [1280, 960]},
            boardGeometry=None if stage == "baseline" else {"margin": 0.3, "canvas": [480, 288]},
        )
        for stage in (["baseline", "wide"] if combined else ["baseline"])
    ]
    return sorted(contexts, key=lambda c: c["sha256"]), route


def observation_fixture(context, source_number, slot=0, *, selection=False, good=True, route=None):
    source = str(UUID(int=source_number))
    pixel = f"{source_number:064x}"
    value = 0.5 if context["stage"] == "baseline" else 0.7
    clearance = value if good or not selection else value / 5
    quad = [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]
    nodes = [[float(x * 20), float(y * 30)] for y in range(4) for x in range(6)]
    proof = _seal(
        {
            "sourceId": source,
            "sourceRepresentativeSha256": pixel,
            "positionIndex": slot,
            "boardPreset": context["boardPreset"],
            "geometry": context["boardGeometry"],
            "routing": route,
            "path": context["selectedPath"],
            "screenQuad": quad,
            "contentReferenceSha256": "d" * 64,
            "contentReferenceRevision": 1,
            "inputCropped": bool(selection and not good),
        }
    )
    witness = _seal(
        {
            "version": "full-board-final-variant-witness-v1",
            "sourceId": source,
            "sourceRepresentativeSha256": pixel,
            "positionIndex": slot,
            "variantKey": context["sha256"],
            "finalDetection": {"nodes": nodes, "screenQuad": quad},
            "detectionNodesSha256": digest(nodes),
            "origin": "baseline" if context["stage"] == "baseline" else "replacement",
            "inputContentEvidence": proof,
        }
    )
    features = {
        "version": "full-board-completeness-features-v2",
        "values": {**dict.fromkeys(AXES_V2, value), "inputEdgeClearance": clearance},
        "hardReasons": [],
    }
    target = {"gameId": str(GAME), "sourceRepresentativeSha256": pixel, "positionIndex": slot}
    if selection:
        target.update(
            role="VALIDATION-A",
            humanGood=good,
            features=features,
            inputEdgeReference={
                "role": "VALIDATION-A",
                "sourceRepresentativeSha256": pixel,
                "positionIndex": slot,
                "variantSha256": context["sha256"],
                "clearance": clearance,
                "inputCropped": not good,
                "synthetic": False,
                "referenceKind": "verified_content",
                "contentReferenceSha256": "d" * 64,
                "contentRevision": 1,
            },
        )
    else:
        target.update(
            sourceId=source,
            groundTruthSha256=digest([source, slot]),
            baselineGood=good,
            candidateGood=True,
            candidateCropped=False,
            baselinePreT0Accepted=True,
            baselineT0Accepted=good,
            candidateFeatures=features,
            synthetic=False,
        )
    return {
        **({"sourceId": source} if selection else {}),
        "variantKey": context["sha256"],
        "target": target,
        "witness": witness,
        "reasonCode": None,
    }


def variant_fixture(
    *, combined=True, sources_per_variant=30, only_baseline=False, inactive_axes=()
):
    contexts, route = contexts_fixture(combined)
    active = [c for c in contexts if not only_baseline or c["stage"] == "baseline"]
    refs, b, reg = [], [], []
    for index, context in enumerate(active):
        start = 100 + index * 1000
        refs += [
            observation_fixture(
                context, start + n // 2, n % 2, selection=True, good=n == 5, route=route
            )
            for n in range(6)
        ]
        for n in range(sources_per_variant):
            for slot in range(2):
                b.append(
                    observation_fixture(
                        context, start + 100 + n, slot, good=bool(slot), route=route
                    )
                )
                reg.append(
                    observation_fixture(
                        context, start + 10000 + n, slot, good=bool(slot), route=route
                    )
                )
    for row in [*refs, *b, *reg]:
        features = row["target"].get("features", row["target"].get("candidateFeatures"))
        features["notApplicable"] = list(inactive_axes)
        for axis in inactive_axes:
            features["values"][axis] = None
    prepared = make_variant_plan(
        game_id=GAME,
        candidate_sha="a" * 64,
        baseline_sha="b" * 64,
        cohort_id=UUID(int=12),
        cohort_manifest_sha="c" * 64,
        role_proof_sha="d" * 64,
        reference_assessment_sha="e" * 64,
        b_assessment_sha="f" * 64,
        regression_assessment_sha="1" * 64,
        allowed_variants=contexts,
        selection_references=refs,
        game_log_aspect_reference=0.0,
        b_targets=len(b),
        b_sources=len(active) * sources_per_variant,
        regression_targets=len(reg),
        regression_sources=len(active) * sources_per_variant,
    )
    return prepared, b, reg


def qualify(prepared, b, reg):
    sealed = seal_variant_b(prepared, b)
    result = assess_variant_regression(prepared, sealed, reg)
    return build_variant_qualification(
        prepared,
        sealed,
        result,
        {"path": "grid-model-evaluations/test/evidence.json", "sha256": "2" * 64},
    )


def test_complete_variants_have_separate_thresholds_and_no_aggregate_counts():
    prepared, b, reg = variant_fixture()
    value = qualify(prepared, b, reg)
    assert value["state"] == "qualified"
    assert "b" not in value and "regression" not in value
    assert {v["profile"]["configuration"]["peak"] for v in value["variants"]} == {0.5, 0.7}
    assert all(
        v["b"]["baselineBadSources"] == v["regression"]["baselineGoodSources"] == 30
        for v in value["variants"]
    )
    assert VariantAutomaticCalibration.model_validate(value).model_dump(mode="json") == value


def test_aggregate_thirty_per_stratum_does_not_qualify_two_fifteen_source_variants():
    p, b, reg = variant_fixture(sources_per_variant=15)
    value = qualify(p, b, reg)
    assert value["state"] == "unqualified" and value["profile"] is None
    assert sum(v["b"]["baselineGoodSources"] for v in value["variants"]) == 30
    assert all(v["state"] == "unqualified" for v in value["variants"])


@pytest.mark.parametrize("combined", [False, True])
def test_none_or_unused_wide_does_not_invent_a_wide_threshold(combined):
    p, b, reg = variant_fixture(combined=combined, only_baseline=True)
    value = qualify(p, b, reg)
    assert value["state"] == "qualified"
    assert len(value["profile"]["variants"]) == 1
    assert len(value["allowedVariants"]) == (2 if combined else 1)


def test_unresolved_target_remains_in_roster_and_blocks_whole_game():
    p, b, reg = variant_fixture()
    b[0] = {**b[0], "variantKey": None, "witness": None, "reasonCode": "OUTPUT_MISSING"}
    sealed = seal_variant_b(p, b)
    result = assess_variant_regression(p, sealed, reg)
    assert len(sealed["observations"]) == len(b)
    assert (
        result["state"] == "unqualified" and "VARIANT_BINDING_UNRESOLVED" in result["reasonCodes"]
    )
    with pytest.raises(ValueError, match="TARGET_COUNT"):
        seal_variant_b(p, b[1:])


def test_resealed_child_threshold_or_foreign_context_does_not_change_plan():
    p, b, _ = variant_fixture()
    changed = deepcopy(p)
    changed["children"][0]["plan"]["menu"][0]["peak"] = 0.999
    changed["children"][0]["plan"] = _seal(
        {k: v for k, v in changed["children"][0]["plan"].items() if k != "sha256"}
    )
    changed = _seal({k: v for k, v in changed.items() if k != "sha256"})
    with pytest.raises(ValueError, match="VARIANT_PLAN_CHANGED"):
        require_variant_plan(changed)
    b[0]["variantKey"] = "0" * 64
    with pytest.raises(ValueError):
        seal_variant_b(p, b)


def test_none_inactive_axes_keep_none_and_legacy_seal_stays_strict():
    from game_predictor_api.domain.full_board_calibration import AssessedTarget, seal_b

    p, b, reg = variant_fixture(
        combined=False, inactive_axes=("rescueDisagreement", "neighborDeviation")
    )
    value = qualify(p, b, reg)
    assert value["state"] == "qualified"
    profile = value["profile"]["variants"][0]["profile"]
    assert profile["configuration"]["rescueDisagreement"] is None
    plan = require_variant_plan(p).children[0].plan
    legacy = seal_b(plan, [AssessedTarget.model_validate(r["target"]) for r in b])
    assert "COMPLETENESS_REFERENCE_MISSING:rescueDisagreement" in legacy["reasonCodes"]
    reg[0]["target"]["candidateFeatures"]["notApplicable"].remove("rescueDisagreement")
    reg[0]["target"]["candidateFeatures"]["values"]["rescueDisagreement"] = 0.1
    value = qualify(p, b, reg)
    assert value["state"] == "unqualified"
    assert (
        "COMPLETENESS_REFERENCE_MISSING:rescueDisagreement" in value["variants"][0]["reasonCodes"]
    )


def test_v3_requires_explicit_report_dispatch_and_finalizer_uses_exact_child_profile():
    from game_predictor_api.domain.calibrated_neural_evidence import calibrated_result_blockers
    from game_predictor_api.domain.full_board_calibration_report import parse_calibration
    from game_predictor_api.domain.neural_grid_operation_pin import require_automatic_qualification

    p, b, reg = variant_fixture(only_baseline=True)
    value = qualify(p, b, reg)
    with pytest.raises(ValueError, match="DISPATCH_REQUIRED"):
        parse_calibration(value)
    assert parse_calibration(value, allow_variant_calibration=True) == value
    qualification = {
        "state": "qualified",
        "reasonCodes": [],
        "reportId": str(UUID(int=99)),
        "reportSha256": "f" * 64,
        "profile": value["profile"],
    }
    assert (
        require_automatic_qualification(qualification, game_id=str(GAME), manifest_sha="a" * 64)
        == qualification
    )
    child = value["profile"]["variants"][0]
    detection = {"detectionId": "det-1", "latticeNodes": b[0]["witness"]["finalDetection"]["nodes"]}
    context = next(c for c in p["allowedVariants"] if c["sha256"] == child["variantKey"])
    detection["inputVariant"] = stamp_fixture(context, detection)
    pin = {
        "contractVersion": "neural-grid-operation-pin-v3",
        "automaticQualification": qualification,
        "catalogueManifestSha256": "a" * 64,
        "pinSha256": "b" * 64,
    }
    evidence = _seal(
        {
            "version": "full-board-result-evidence-v3",
            "sourceSha256": "c" * 64,
            "modelManifestSha256": "a" * 64,
            "operationPinSha256": "b" * 64,
            "profileSha256": value["profile"]["sha256"],
            "detectionId": "det-1",
            "nodesSha256": digest(detection["latticeNodes"]),
            "features": b[0]["target"]["candidateFeatures"],
            "variantKey": child["variantKey"],
            "variantProfileSha256": child["profile"]["sha256"],
            "inputVariantSha256": detection["inputVariant"]["sha256"],
        }
    )
    args = {
        "pin": pin,
        "proposal": {"sourceChecksumSha256": "c" * 64, "sourceWidth": 1000, "sourceHeight": 1000},
        "detection": detection,
    }
    assert calibrated_result_blockers(evidence, **args) == ()
    changed = {**evidence, "variantProfileSha256": "e" * 64}
    changed = _seal({k: v for k, v in changed.items() if k != "sha256"})
    assert calibrated_result_blockers(changed, **args) == ("COMPLETENESS_VARIANT_PROFILE_CHANGED",)
    wide = next(c for c in p["allowedVariants"] if c["stage"] == "wide")
    detection["inputVariant"] = stamp_fixture(wide, detection)
    changed = _seal(
        {
            **{k: v for k, v in evidence.items() if k != "sha256"},
            "variantKey": wide["sha256"],
            "inputVariantSha256": detection["inputVariant"]["sha256"],
        }
    )
    assert calibrated_result_blockers(changed, **args) == ("COMPLETENESS_VARIANT_UNQUALIFIED",)


def test_runtime_applicable_axis_without_own_reference_remains_manual():
    from game_predictor_api.domain.calibrated_neural_evidence import calibrated_result_blockers

    p, b, reg = variant_fixture(combined=False, inactive_axes=("rescueDisagreement",))
    qualification = qualify(p, b, reg)
    profile = qualification["profile"]
    assert profile is not None
    child = profile["variants"][0]
    detection = {"detectionId": "det-1", "latticeNodes": b[0]["witness"]["finalDetection"]["nodes"]}
    context = next(c for c in p["allowedVariants"] if c["sha256"] == child["variantKey"])
    detection["inputVariant"] = stamp_fixture(context, detection)
    pin = {
        "contractVersion": "neural-grid-operation-pin-v3",
        "automaticQualification": {"state": "qualified", "profile": profile},
        "catalogueManifestSha256": "a" * 64,
        "pinSha256": "b" * 64,
    }
    features = deepcopy(b[0]["target"]["candidateFeatures"])
    body = {
        "version": "full-board-result-evidence-v3",
        "sourceSha256": "c" * 64,
        "modelManifestSha256": "a" * 64,
        "operationPinSha256": "b" * 64,
        "profileSha256": profile["sha256"],
        "detectionId": "det-1",
        "nodesSha256": digest(detection["latticeNodes"]),
        "features": features,
        "variantKey": child["variantKey"],
        "variantProfileSha256": child["profile"]["sha256"],
        "inputVariantSha256": detection["inputVariant"]["sha256"],
    }
    args = {
        "pin": pin,
        "proposal": {"sourceChecksumSha256": "c" * 64, "sourceWidth": 1000, "sourceHeight": 1000},
        "detection": detection,
    }
    assert calibrated_result_blockers(_seal(body), **args) == ()
    features["notApplicable"].remove("rescueDisagreement")
    features["values"]["rescueDisagreement"] = 0.0
    assert "COMPLETENESS_REFERENCE_MISSING:rescueDisagreement" in calibrated_result_blockers(
        _seal(body), **args
    )
