import pytest
from game_predictor_api.domain.grid_correction_evaluation import (
    SCREEN_CHECKPOINT_RULE,
    decide_game,
    require_checkpoint_selection,
)
from test_grid_correction_evaluation import metrics, role, roles


def test_historical_selector_replaces_only_an_already_required_other_game():
    from game_predictor_api.application.grid_correction_history import select_historical_cohorts

    old = {"gameId": "other", "cohortId": "old", "manifestSha256": "a" * 64}
    new = {"gameId": "other", "cohortId": "full-screen", "manifestSha256": "b" * 64}
    args = dict(current_game="current", required_games=["current", "other"])
    assert select_historical_cohorts([old], [new], **args) == [new]
    assert old["cohortId"] == "old"
    for selected in ([{**new, "gameId": "foreign"}], [{**new, "gameId": "current"}], [new, new]):
        with pytest.raises(ValueError):
            select_historical_cohorts([old], selected, **args)
    assert select_historical_cohorts([old], [], **args) == [old]


def test_screen_gate_uses_full_selection_and_partial_regression():
    values = roles()
    values["VALIDATION"] = role(metrics(full=True), metrics(full=True))
    result = decide_game(
        mode="screen+grid", training=True, parity_passed=True, roles=values, screen=True
    )
    assert result["coverage"] == "complete" and result["regression"] == "pass"
    values["VALIDATION"] = role(metrics(), metrics())
    assert (
        "SCREEN_FULL_VALIDATION_REQUIRED"
        in decide_game(
            mode="screen+grid", training=True, parity_passed=True, roles=values, screen=True
        )["reasons"]
    )


def test_new_selection_contract_does_not_reinterpret_legacy():
    value = {
        "rule": SCREEN_CHECKPOINT_RULE,
        "role": "VALIDATION",
        "step": 2,
        "metrics": {"photoCorrectRate": 0.2, "boardCorrectRate": 0.8, "normalizedError": 0.1},
        "earlyStopping": {"patience": 4, "evaluationsWithoutImprovement": 0, "stopped": False},
        "selectionInputSha256": "a" * 64,
        "metricStateVersion": "photo-board-checkpoint-state-v1",
    }
    assert require_checkpoint_selection(value, screen=True) == value
    with pytest.raises(ValueError):
        require_checkpoint_selection(value)
    del value["selectionInputSha256"]
    with pytest.raises(ValueError):
        require_checkpoint_selection(value, screen=True)


def test_detector_exclusions_keep_all_qualified_partial_targets_visible():
    from game_predictor_api.domain.grid_correction_progress import correction_progress_counts

    sources = [
        {
            "representative": True,
            "buffer": False,
            "role": role,
            "qualifiedBoards": 3,
            "eligibleBoards": 3 if role == "REGRESSION" else 0,
            "detectorExcluded": role != "REGRESSION",
        }
        for role in ("TRAIN", "VALIDATION", "REGRESSION")
    ]
    result = correction_progress_counts(
        {"schemaVersion": "grid-correction-split-v3", "sources": sources}
    )
    assert result["approved"] == {"photos": 3, "boards": 9}
    assert result["excluded"] == {"photos": 2, "boards": 6}
    assert result["availableTrain"] == {"photos": 0, "boards": 0}
    assert result["regression"] == {"photos": 1, "boards": 3}
    assert result["exclusionReasons"] == [
        {"reason": "SCREEN_PARTIAL_PHOTO_EXCLUDED", "photos": 2, "boards": 6}
    ]
