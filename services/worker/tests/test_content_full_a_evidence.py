"""Read-only API proof validation cannot accept a sampled or tampered full-A receipt."""

from copy import deepcopy

import pytest
from game_predictor_api.domain.grid_content_experiment_evidence import _require_full_a
from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_worker.training_core.grid_content_experiment import selection_record
from test_grid_content_experiment import game


def sealed(value):
    return {
        **value,
        "sha256": digest({key: item for key, item in value.items() if key != "sha256"}),
    }


def evidence():
    games = [game(game_id="first"), game(game_id="second")]
    selected = selection_record(games, "R0", 200)
    arms = [selection_record(games, arm, 200) for arm in ("R0", "R1", "R2")]
    history = [
        {"contentSelection": selection_record(games, "R0", step)} for step in range(200, 1201, 200)
    ]
    proof = {
        "plan": {
            "selectionRosterSha256": "a" * 64,
            "cohorts": [
                {"gameId": game_id, "manifestSha256": "c" * 64} for game_id in ("first", "second")
            ],
        },
        "selectedArm": "R0",
        "state": {"arms": {arm["arm"]: {"status": "complete", "selection": arm} for arm in arms}},
        "inputs": {
            "selectionRoster": {
                "games": [
                    {"gameId": game_id, "sources": [{"sourceId": "source-" + game_id}]}
                    for game_id in ("first", "second")
                ]
            }
        },
    }
    photos = [
        {
            "gameId": game_id,
            "sourceId": "source-" + game_id,
            "manifestSha256": "c" * 64,
            "referenceSha256": "d" * 64,
            "outcomeSha256": "e" * 64,
        }
        for game_id in ("first", "second")
    ]
    inputs = [
        {
            "stage": "screen",
            "shape": [1, 3, 64, 64],
            "inputSha256": "f" * 64,
            "verdict": {
                "passed": True,
                "tolerance": 1e-4,
                "toleranceScale": "max(1,|torch|)",
                "maxDelta": {"screen.0": 0, "screen.1": 0},
                "maxScaledDelta": {"screen.0": 0, "screen.1": 0},
            },
        }
        for _ in photos
    ]
    value = sealed(
        {
            "version": "full-a-content-v1",
            "precision": "torch-fp32-no-tf32-v1",
            "selectionRosterSha256": "a" * 64,
            "selectedSha256": selected["sha256"],
            "history": history,
            "historySha256": digest(history),
            "armSelectionsSha256": digest(arms),
            "reference": {"selection": selected, "photos": photos},
            "onnx": {"selection": deepcopy(selected), "photos": deepcopy(photos)},
            "inputs": inputs,
            "passed": True,
            "reasonCodes": [],
        }
    )
    return value, proof


def test_full_a_receipt_binds_every_game_source_and_completed_checkpoint_history():
    value, proof = evidence()
    _require_full_a(value, proof)


@pytest.mark.parametrize("mutation", ["sample", "cell", "raw", "history", "precision", "rank"])
def test_rehashed_receipt_cannot_hide_incomplete_or_changed_a(mutation):
    value, proof = evidence()
    if mutation == "sample":
        value["reference"]["photos"].pop()
        value["onnx"]["photos"].pop()
    elif mutation == "cell":
        value["onnx"]["photos"][-1]["outcomeSha256"] = "0" * 64
    elif mutation == "raw":
        value["inputs"][-1]["verdict"]["maxScaledDelta"]["screen.0"] = 0.1
    elif mutation == "history":
        value["history"].pop()
        value["historySha256"] = digest(value["history"])
    elif mutation == "precision":
        value["precision"] = "tf32"
    else:
        games = deepcopy(value["onnx"]["selection"]["games"])
        games[0]["quality"]["candidate"]["normalized_error"] += 1e-7
        value["onnx"]["selection"] = selection_record(games, "R0", 200)
    with pytest.raises(ValueError, match="CONTENT_EXPERIMENT_FULL_A"):
        _require_full_a(sealed(value), proof)
