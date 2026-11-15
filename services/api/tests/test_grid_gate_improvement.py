"""Gate v6 (D-613): gate v5 plus a real gain of the training game."""

import copy
from typing import Any

import pytest
from game_predictor_api.domain.grid_correction_evaluation import (
    CELL_CUT_POLICY,
    CELL_CUT_POLICY_VERSION,
    IMPROVEMENT_POLICY,
    IMPROVEMENT_POLICY_VERSION,
    IMPROVEMENT_REASON,
    GridEvaluationReportError,
    decide_game,
    require_report,
)
from game_predictor_api.domain.grid_model_evaluation import verdict_of
from game_predictor_api.domain.grid_model_registry import canonical_json
from game_predictor_api.schemas.grid_model_evaluations import (
    GridCorrectionEvaluationReport,
    GridCorrectionImprovementEvaluationPolicy,
)
from test_grid_correction_evaluation import metrics, role
from test_grid_gate_cell_cut import cut, report_for


def measured(
    correct: tuple[tuple[int, int], tuple[int, int]],
    within: tuple[tuple[int, int], tuple[int, int]],
) -> dict[str, Any]:
    value = {}
    for name, (base, candidate), cells in zip(
        ("VALIDATION", "REGRESSION"), correct, within, strict=True
    ):
        value[name] = role(metrics(correct=base), metrics(correct=candidate))
        value[name]["cellCut"] = cut(*cells)
    return value


def decide(value: dict[str, Any], *, training: bool = True) -> dict[str, Any]:
    return decide_game(
        mode="grid-only",
        training=training,
        parity_passed=True,
        roles=value,
        tolerant=True,
        cell_cut=True,
        improvement=True,
    )


@pytest.mark.parametrize(
    ("correct", "within", "improved"),
    [
        (((12, 13), (12, 12)), ((10, 10), (10, 10)), True),  # one more correct board
        (((12, 12), (12, 12)), ((10, 10), (10, 11)), True),  # one more uncut board
        (((12, 12), (12, 12)), ((10, 10), (10, 10)), False),  # equal is no gain
        # The 01767a49 case: one board lost, error and cut also slightly worse.
        (((12, 11), (12, 12)), ((10, 9), (8, 7)), False),
        (((12, 14), (12, 12)), ((10, 9), (10, 10)), False),  # a gain bought with a cut board
        (((12, 13), (12, 11)), ((10, 10), (10, 10)), False),  # roles cancel out
    ],
)
def test_training_game_needs_a_real_gain(correct, within, improved) -> None:
    result = decide(measured(correct, within))
    assert (IMPROVEMENT_REASON in result["reasons"]) is (not improved)
    if not improved:
        assert result["validation"] == "fail"
        assert verdict_of([{**result}]) == "REVISE"


def test_error_only_gain_is_not_an_improvement() -> None:
    value = measured(((12, 12), (12, 12)), ((10, 10), (10, 10)))
    for name in ("VALIDATION", "REGRESSION"):
        value[name]["candidate"] = metrics(correct=12, error=0.01)
        value[name]["recordings"][0]["candidate"] = value[name]["candidate"]
    assert IMPROVEMENT_REASON in decide(value)["reasons"]


def test_other_required_games_only_keep_the_v5_rules() -> None:
    result = decide(measured(((12, 12), (12, 12)), ((10, 10), (10, 10))), training=False)
    assert result == {
        "validation": "pass",
        "regression": "pass",
        "coverage": "complete",
        "reasons": [],
    }


def test_v6_extends_only_gate_v5() -> None:
    with pytest.raises(GridEvaluationReportError):
        decide_game(
            mode="grid-only",
            training=True,
            parity_passed=True,
            roles=measured(((12, 13), (12, 12)), ((10, 10), (10, 10))),
            tolerant=True,
            improvement=True,
        )


def test_new_report_is_v6_and_the_schema_accepts_its_policy() -> None:
    manifest, report = report_for(measured(((12, 13), (12, 12)), ((10, 10), (10, 10))))
    assert report["policyVersion"] == IMPROVEMENT_POLICY_VERSION
    assert report["policy"] == IMPROVEMENT_POLICY and report["verdict"] == "PASS"
    GridCorrectionImprovementEvaluationPolicy.model_validate(report["policy"])
    parsed = GridCorrectionEvaluationReport.model_validate(report)
    assert parsed.model_dump(mode="json", exclude_none=True)["policy"] == IMPROVEMENT_POLICY
    _, failed = report_for(measured(((12, 12), (12, 12)), ((10, 10), (10, 10))))
    assert failed["verdict"] == "REVISE"
    assert failed["games"][0]["reasons"] == [IMPROVEMENT_REASON]


def test_historical_v5_report_still_replays_and_relabels_are_rejected() -> None:
    manifest, report = report_for(measured(((12, 12), (12, 12)), ((10, 10), (10, 10))))
    historical = copy.deepcopy(report)
    historical.update(policyVersion=CELL_CUT_POLICY_VERSION, policy=CELL_CUT_POLICY)
    game = historical["games"][0]
    game.update(validation="pass", reasons=[])
    historical["verdict"] = "PASS"
    assert require_report(canonical_json(historical), manifest=manifest, base_sha256="c" * 64)
    # A v6 REVISE cannot be rewritten as a v5 PASS without its stored decision changing,
    # and a v5 PASS cannot be relabelled v6.
    relabelled = {**historical, "policyVersion": IMPROVEMENT_POLICY_VERSION}
    relabelled["policy"] = IMPROVEMENT_POLICY
    with pytest.raises(GridEvaluationReportError):
        require_report(canonical_json(relabelled), manifest=manifest, base_sha256="c" * 64)
    forged = copy.deepcopy(report)
    forged["games"][0].update(validation="pass", reasons=[])
    forged["verdict"] = "PASS"
    with pytest.raises(GridEvaluationReportError):
        require_report(canonical_json(forged), manifest=manifest, base_sha256="c" * 64)
