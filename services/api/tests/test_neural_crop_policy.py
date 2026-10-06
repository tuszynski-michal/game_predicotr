from copy import deepcopy

import pytest
from game_predictor_api.domain.neural_crop_policy import (
    NEURAL_AUTO_CROP_POLICY,
    full_neural_prediction_geometry,
    pin_neural_crop_policy,
)
from game_predictor_api.domain.neural_grid_proposal import associate_expected_slots
from test_neural_grid_proposal import proposal

BASE_PROPOSAL = proposal()
IDENTITY = {
    "game_id": BASE_PROPOSAL["gameId"],
    "source_checksum_sha256": BASE_PROPOSAL["sourceChecksumSha256"],
}


def geometry():
    value = deepcopy(BASE_PROPOSAL)
    detection = value["detections"][0]
    return {
        "neuralExecutionPolicy": NEURAL_AUTO_CROP_POLICY,
        "neuralProposalChecksumSha256": value["proposalChecksumSha256"],
        "detectionId": detection["detectionId"],
        "neuralProposalBinding": associate_expected_slots(value),
        "latticeNodes": detection["latticeNodes"],
        "quad": [detection["latticeNodes"][index] for index in (0, 5, 23, 18)],
    }


def test_full_prediction_has_operational_availability_without_human_approval():
    assert full_neural_prediction_geometry(
        geometry(), position=0, sequence=101, width=500, height=300, **IDENTITY
    )


@pytest.mark.parametrize(
    "fault",
    [
        "policy",
        "checksum",
        "missing",
        "outside",
        "duplicate",
        "outline",
        "sequence",
        "game",
        "source",
        "dimensions",
    ],
)
def test_unbound_drift_or_partial_geometry_is_not_admitted(fault):
    value = deepcopy(geometry())
    sequence = 101
    if fault == "policy":
        value.pop("neuralExecutionPolicy")
    elif fault == "checksum":
        value["neuralProposalChecksumSha256"] = "x" * 64
    elif fault == "missing":
        value["latticeNodes"] = value["latticeNodes"][:-1]
    elif fault == "outside":
        value["latticeNodes"][8]["x"] = -1
    elif fault == "duplicate":
        value["neuralProposalBinding"]["assignments"].append(
            {"positionIndex": 5, "detectionId": "a"}
        )
    elif fault == "outline":
        value["quad"] = list(reversed(value["quad"]))
    elif fault == "sequence":
        sequence = 102
    elif fault == "game":
        value["neuralProposalBinding"]["gameId"] = "another-game"
    elif fault == "source":
        value["neuralProposalBinding"]["sourceChecksumSha256"] = "f" * 64
    elif fault == "dimensions":
        value["neuralProposalBinding"]["sourceWidth"] = 501
    assert not full_neural_prediction_geometry(
        value, position=0, sequence=sequence, width=500, height=300, **IDENTITY
    )


def test_policy_changes_only_neural_pipeline_identity():
    old = {"symbol_model": {}}
    assert pin_neural_crop_policy(old, "a" * 64) == "a" * 64
    assert "neural_grid_execution_policy_version" not in old
    neural = {"neural_grid_proposal": {"frozen": True}}
    assert pin_neural_crop_policy(neural, "a" * 64) != "a" * 64
    assert neural["neural_grid_execution_policy_version"] == NEURAL_AUTO_CROP_POLICY
