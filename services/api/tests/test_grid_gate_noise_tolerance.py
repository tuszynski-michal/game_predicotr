"""Gate v4 (D-604): only gross regressions reject; gate v2 history stays valid."""

from typing import Any

import pytest
from game_predictor_api.domain.grid_correction_evaluation import (
    POLICY,
    POLICY_VERSION,
    TOLERANT_POLICY,
    TOLERANT_POLICY_VERSION,
    GridEvaluationReportError,
    board_loss_allowance,
    decide_game,
    require_report,
)
from game_predictor_api.domain.grid_model_registry import canonical_json
from test_grid_correction_evaluation import fixture, metrics, role


def partial(photos: int, expected: int, correct: int, error: float) -> dict[str, Any]:
    return {
        "photos": photos,
        "full_photos": 0,
        "partial_photos": photos,
        "boards_expected": expected,
        "boards_matched": expected,
        "boards_correct": correct,
        "board_correct_rate": correct / expected,
        "detection_recall": 1.0,
        "normalized_error": error,
        "photo_complete_correct": None,
        "photo_complete_correct_rate": None,
        "false_boards": None,
        "duplicate_predictions": None,
    }


def roles_of(validation: tuple[Any, Any], regression: tuple[Any, Any]) -> dict[str, Any]:
    value = {"VALIDATION": role(*validation), "REGRESSION": role(*regression)}
    for name, (base, _) in (("VALIDATION", validation), ("REGRESSION", regression)):
        value[name]["photos"] = base["photos"]
    return value


def mumie_a2() -> dict[str, Any]:
    """Measured evaluation 8723857d of candidate bf327cfa (2026-11-12)."""
    return roles_of(
        (partial(13, 51, 48, 0.00958), partial(13, 51, 47, 0.01067)),
        (partial(13, 21, 17, 0.01181), partial(13, 21, 17, 0.01169)),
    )


def decide(value: dict[str, Any], *, tolerant: bool) -> dict[str, Any]:
    return decide_game(
        mode="grid-only", training=True, parity_passed=True, roles=value, tolerant=tolerant
    )


def test_mumie_a2_noise_passes_v4_but_not_v2() -> None:
    strict = decide(mumie_a2(), tolerant=False)
    assert (strict["validation"], strict["regression"]) == ("fail", "fail")
    tolerant = decide(mumie_a2(), tolerant=True)
    assert tolerant == {
        "validation": "pass",
        "regression": "pass",
        "coverage": "complete",
        "reasons": [],
    }


@pytest.mark.parametrize(("expected", "allowance"), [(15, 1), (51, 1), (100, 2), (151, 3)])
def test_board_allowance_is_one_board_or_two_percent(expected: int, allowance: int) -> None:
    assert board_loss_allowance(expected) == allowance


def test_losing_two_of_51_boards_is_gross() -> None:
    value = mumie_a2()
    value["VALIDATION"]["candidate"]["boards_correct"] = 46
    result = decide(value, tolerant=True)
    assert result["validation"] == "fail"
    assert result["reasons"] == ["VALIDATION_REGRESSED:boards_correct"]


@pytest.mark.parametrize(
    ("base", "candidate", "expected"),
    [
        (0.02, 0.023, "pass"),
        (0.02, 0.0231, "fail"),
        (0.004, 0.005, "pass"),
        (0.004, 0.0051, "fail"),
    ],
)
def test_error_increase_needs_fifteen_percent_or_absolute_floor(
    base: float, candidate: float, expected: str
) -> None:
    value = mumie_a2()
    value["REGRESSION"] = role(partial(13, 21, 17, base), partial(13, 21, 17, candidate))
    value["REGRESSION"]["photos"] = 13
    assert decide(value, tolerant=True)["regression"] == expected


def test_no_improvement_is_required_under_v4() -> None:
    value = mumie_a2()
    value["REGRESSION"] = role(partial(13, 21, 17, 0.01), partial(13, 21, 17, 0.01))
    value["REGRESSION"]["photos"] = 13
    assert decide(value, tolerant=True)["regression"] == "pass"
    assert (
        "REGRESSION_NOT_IMPROVED:boards_correct_or_normalized_error"
        in decide(value, tolerant=False)["reasons"]
    )


@pytest.mark.parametrize("metric", ["false_boards", "duplicate_predictions"])
def test_phantom_and_duplicate_boards_stay_strict(metric: str) -> None:
    base, candidate = metrics(full=True), metrics(full=True)
    candidate[metric] = 1
    value = mumie_a2()
    value["VALIDATION"] = role(base, candidate)
    assert decide(value, tolerant=True)["validation"] == "fail"


@pytest.mark.parametrize(("lost", "expected"), [(1, "pass"), (2, "fail")])
def test_complete_photo_loss_tolerates_one_photo(lost: int, expected: str) -> None:
    base, candidate = metrics(full=True), metrics(full=True)
    base["photo_complete_correct"], base["photo_complete_correct_rate"] = 3, 0.6
    candidate["photo_complete_correct"] = 3 - lost
    candidate["photo_complete_correct_rate"] = (3 - lost) / 5
    value = mumie_a2()
    value["VALIDATION"] = role(base, candidate)
    assert decide(value, tolerant=True)["validation"] == expected


def test_screen_gate_cannot_be_tolerant() -> None:
    with pytest.raises(GridEvaluationReportError):
        decide_game(
            mode="screen+grid",
            training=True,
            parity_passed=True,
            roles=mumie_a2(),
            screen=True,
            tolerant=True,
        )


def test_new_reports_use_v4_and_v2_history_still_validates() -> None:
    manifest, report = fixture()
    assert report["policyVersion"] == TOLERANT_POLICY_VERSION
    assert report["policy"] == TOLERANT_POLICY
    historical = {**report, "policyVersion": POLICY_VERSION, "policy": POLICY}
    assert (
        require_report(canonical_json(historical), manifest=manifest, base_sha256="c" * 64)
        == historical
    )


def test_relabelling_a_v4_decision_as_v2_is_rejected() -> None:
    manifest, report = fixture()
    for game in report["games"]:
        game["roles"] = mumie_a2()
        game.update(
            decide_game(
                mode="grid-only",
                training=game["gameId"] == report["trainingGameId"],
                parity_passed=True,
                roles=game["roles"],
                tolerant=True,
            )
        )
    report["verdict"] = "PASS"
    assert require_report(canonical_json(report), manifest=manifest, base_sha256="c" * 64)
    forged = {**report, "policyVersion": POLICY_VERSION, "policy": POLICY}
    with pytest.raises(GridEvaluationReportError):
        require_report(canonical_json(forged), manifest=manifest, base_sha256="c" * 64)
