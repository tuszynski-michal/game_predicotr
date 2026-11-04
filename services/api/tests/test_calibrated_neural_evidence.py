"""Result evidence is bound to the source, operation, profile and exact nodes."""

from copy import deepcopy

import pytest
from game_predictor_api.domain.calibrated_neural_evidence import calibrated_result_blockers
from game_predictor_api.domain.full_board_calibration import AXES
from game_predictor_api.domain.grid_model_registry import descriptor_sha256 as digest
from game_predictor_api.domain.v3_engine_acceptance import acceptance_for_operation_pin


def fixture():
    configuration = dict.fromkeys(AXES, 0.5)
    profile = {"configuration": configuration, "sha256": "1" * 64}
    pin = {
        "contractVersion": "neural-grid-operation-pin-v3",
        "automaticQualification": {"state": "qualified", "profile": profile},
        "catalogueManifestSha256": "2" * 64,
        "pinSha256": "3" * 64,
    }
    proposal = {"sourceChecksumSha256": "4" * 64}
    detection = {"detectionId": "result-0", "latticeNodes": [{"x": 1, "y": 2}]}
    evidence = {
        "version": "full-board-result-evidence-v1",
        "sourceSha256": proposal["sourceChecksumSha256"],
        "modelManifestSha256": pin["catalogueManifestSha256"],
        "operationPinSha256": pin["pinSha256"],
        "profileSha256": profile["sha256"],
        "detectionId": detection["detectionId"],
        "nodesSha256": digest(detection["latticeNodes"]),
        "features": {"values": configuration},
    }
    evidence["sha256"] = digest(evidence)
    return evidence, dict(pin=pin, proposal=proposal, detection=detection)


def test_exact_features_pass_but_missing_evidence_and_unknown_axis_are_manual():
    evidence, args = fixture()
    assert calibrated_result_blockers(evidence, **args) == ()
    assert calibrated_result_blockers(None, **args) == ("COMPLETENESS_EVIDENCE_REQUIRED",)
    evidence["features"]["values"]["peak"] = None
    evidence["sha256"] = digest({k: v for k, v in evidence.items() if k != "sha256"})
    assert calibrated_result_blockers(evidence, **args)


@pytest.mark.parametrize(
    "field",
    ["sourceSha256", "modelManifestSha256", "operationPinSha256", "profileSha256", "nodesSha256"],
)
def test_recomputed_envelope_cannot_rebind_another_result(field):
    evidence, args = fixture()
    evidence[field] = "f" * 64
    evidence["sha256"] = digest({k: v for k, v in evidence.items() if k != "sha256"})
    assert calibrated_result_blockers(evidence, **args) == ("COMPLETENESS_EVIDENCE_MISMATCH",)


def test_policy_recovery_preserves_historical_pair_and_new_unqualified_is_manual():
    evidence, args = fixture()
    assert acceptance_for_operation_pin(args["pin"]) == "v3-engine-acceptance-v4"
    for version in ("neural-grid-operation-pin-v1", "neural-grid-operation-pin-v2"):
        historical = {**args["pin"], "contractVersion": version}
        assert acceptance_for_operation_pin(historical) == "v3-engine-acceptance-v3"
    unqualified = deepcopy(args["pin"])
    unqualified["automaticQualification"] = {"state": "unqualified"}
    assert calibrated_result_blockers(evidence, **{**args, "pin": unqualified}) == (
        "NEURAL_GRID_CALIBRATION_REQUIRED",
    )
