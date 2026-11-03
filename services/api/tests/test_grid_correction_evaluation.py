"""Gate v2 and strict scoped report v3; legacy reports remain separate."""

from copy import deepcopy
from typing import Any
from uuid import UUID

import pytest
from game_predictor_api.domain.grid_correction_evaluation import (
    CHECKPOINT_RULE,
    GridEvaluationReportError,
    build_report,
    decide_game,
    require_metrics,
    require_report,
    require_scope,
)
from game_predictor_api.domain.grid_model_evaluation import require_report as require_legacy
from game_predictor_api.domain.grid_model_registry import canonical_json


def uid(number: int) -> str:
    return str(UUID(int=number))


def metrics(*, correct: int = 12, error: float = 0.02, full: bool = False) -> dict[str, Any]:
    expected = 45 if full else 15
    return {
        "photos": 5,
        "full_photos": 5 if full else 0,
        "partial_photos": 0 if full else 5,
        "boards_expected": expected,
        "boards_matched": expected,
        "boards_correct": correct,
        "board_correct_rate": correct / expected,
        "detection_recall": 1.0,
        "normalized_error": error,
        "photo_complete_correct": 0 if full else None,
        "photo_complete_correct_rate": 0.0 if full else None,
        "false_boards": 0 if full else None,
        "duplicate_predictions": 0 if full else None,
    }


def role(base: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "photos": 5,
        "inputSha256": "a" * 64,
        "base": base,
        "candidate": candidate,
        "recordings": [{"groupId": uid(100), "base": base, "candidate": candidate}],
        "detail": {"path": "grid-model-evaluations/role.json", "sha256": "b" * 64},
    }


def roles() -> dict[str, Any]:
    return {
        "VALIDATION": role(metrics(), metrics()),
        "REGRESSION": role(metrics(), metrics(correct=13)),
    }


def decide(value: dict[str, Any], *, current: bool = True) -> dict[str, Any]:
    return decide_game(mode="grid-only", training=current, parity_passed=True, roles=value)


def test_only_regression_improvement_admits_current_game() -> None:
    value = roles()
    assert decide(value)["regression"] == "pass"
    value["VALIDATION"], value["REGRESSION"] = value["REGRESSION"], value["VALIDATION"]
    assert decide(value)["regression"] == "fail"
    assert decide(value, current=False)["regression"] == "pass"


@pytest.mark.parametrize(
    ("base_error", "candidate_error", "expected"),
    [
        (0.02, 0.019, "pass"),
        (0.02, 0.0190000001, "fail"),
        (0.03, 0.0285, "pass"),
        (0.1, 0.096, "fail"),
        (0.01, 0.0094, "fail"),
        (0.0, 0.0, "fail"),
        (0.1, 0.09, "pass"),
    ],
)
def test_error_improvement_requires_relative_and_absolute_thresholds(
    base_error: float, candidate_error: float, expected: str
) -> None:
    value = roles()
    value["REGRESSION"] = role(metrics(error=base_error), metrics(error=candidate_error))
    assert decide(value)["regression"] == expected


@pytest.mark.parametrize("role_name", ["VALIDATION", "REGRESSION"])
@pytest.mark.parametrize("metric", ["boards_correct", "boards_matched", "normalized_error"])
def test_each_required_role_blocks_regression(role_name: str, metric: str) -> None:
    value = roles()
    candidate = value[role_name]["candidate"]
    candidate[metric] = candidate[metric] + 0.01 if metric == "normalized_error" else 11
    candidate["boards_correct"] = min(candidate["boards_correct"], candidate["boards_matched"])
    candidate["detection_recall"] = candidate["boards_matched"] / candidate["boards_expected"]
    assert decide(value, current=False)[role_name.lower()] == "fail"


def test_error_non_regression_epsilon_is_not_a_quality_claim() -> None:
    value = roles()
    value["VALIDATION"]["candidate"]["normalized_error"] += 0.5e-9
    assert decide(value)["validation"] == "pass"
    value["VALIDATION"]["candidate"]["normalized_error"] += 1e-9
    assert decide(value)["validation"] == "fail"


@pytest.mark.parametrize(
    "metric", ["false_boards", "duplicate_predictions", "photo_complete_correct"]
)
def test_full_photo_non_regression(metric: str) -> None:
    value = roles()
    base, candidate = metrics(full=True), metrics(full=True)
    if metric == "photo_complete_correct":
        base[metric], base["photo_complete_correct_rate"] = 1, 0.2
    else:
        candidate[metric] = 1
    value["VALIDATION"] = role(base, candidate)
    assert decide(value)["validation"] == "fail"


def fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = {
        "versionId": uid(1),
        "baseVersionId": uid(2),
        "familyId": uid(3),
        "cohortId": uid(4),
    }
    scope = {
        "currentGameId": uid(5),
        "trainingGameIds": [uid(5)],
        "priorVerifiedGameIds": [uid(6)],
        "priorScopeDocumented": True,
        "exclusions": [],
    }
    report = build_report(
        manifest=manifest,
        base_manifest_sha256="c" * 64,
        training_game_id=uid(5),
        parity={"passed": True, "bundleSha256": "d" * 64},
        cohorts=[
            {"gameId": uid(5), "cohortId": uid(4), "manifestSha256": "e" * 64},
            {"gameId": uid(6), "cohortId": uid(7), "manifestSha256": "f" * 64},
        ],
        measured={
            uid(5): {"mode": "grid-only", "roles": roles()},
            uid(6): {"mode": "grid-only", "roles": roles()},
        },
        scope=scope,
        checkpoint_selection={
            "rule": CHECKPOINT_RULE,
            "role": "VALIDATION",
            "step": 10,
            "metrics": {"boardCorrectRate": 0.8, "normalizedError": 0.02},
            "earlyStopping": {"patience": 3, "evaluationsWithoutImprovement": 1, "stopped": False},
        },
    )
    return manifest, report


def test_report_roundtrip_and_legacy_reader_rejects_new_semantics() -> None:
    manifest, report = fixture()
    assert report["verdict"] == "PASS"
    assert require_report(canonical_json(report), manifest=manifest, base_sha256="c" * 64) == report
    with pytest.raises(GridEvaluationReportError):
        require_legacy(canonical_json(report), manifest=manifest, base_sha256="c" * 64)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_game",
        "narrow_scope",
        "policy",
        "evidence",
        "extra",
        "checkpoint_role",
        "group_counts",
        "group_macro",
        "decision",
    ],
)
def test_closed_reader_rejects_forged_or_incomplete_evidence(mutation: str) -> None:
    manifest, report = fixture()
    if mutation == "missing_game":
        report["games"].pop()
    elif mutation == "narrow_scope":
        report["requiredGameIds"].pop()
    elif mutation == "policy":
        report["policy"]["epsilon"] = 1
    elif mutation == "evidence":
        report["limitations"] = []
    elif mutation == "extra":
        report["unverified"] = True
    elif mutation == "checkpoint_role":
        report["checkpointSelection"]["role"] = "REGRESSION"
    elif mutation == "group_counts":
        report["games"][0]["roles"]["VALIDATION"]["recordings"][0]["base"]["boards_correct"] = 1
    elif mutation == "group_macro":
        report["games"][0]["roles"]["VALIDATION"]["recordings"][0]["base"]["normalized_error"] = 0.5
    else:
        report["games"][0]["validation"] = "fail"
    with pytest.raises(GridEvaluationReportError):
        require_report(canonical_json(report), manifest=manifest, base_sha256="c" * 64)


def test_scope_exclusion_requires_reason_and_confirmation_and_preserves_train() -> None:
    _, report = fixture()
    scope = deepcopy(report["scope"])
    scope["exclusions"] = [
        {"gameId": uid(6), "reason": "No current labels remain", "confirmed": True}
    ]
    assert require_scope(scope)[1] == [uid(5)]
    scope["exclusions"][0]["confirmed"] = False
    with pytest.raises(GridEvaluationReportError):
        require_scope(scope)
    scope["exclusions"] = [{"gameId": uid(5), "reason": "Do not evaluate", "confirmed": True}]
    with pytest.raises(GridEvaluationReportError):
        require_scope(scope)
    scope["exclusions"] = []
    scope["priorScopeDocumented"] = False
    with pytest.raises(GridEvaluationReportError):
        require_scope(scope)
    scope["priorVerifiedGameIds"] = []
    assert require_scope(scope)[1] == [uid(5)]


def test_no_false_full_claims_nonfinite_rates_or_missing_boards() -> None:
    value = metrics()
    value["false_boards"] = 0
    with pytest.raises(GridEvaluationReportError):
        require_metrics(value)
    value = metrics(error=float("nan"))
    with pytest.raises(GridEvaluationReportError):
        require_metrics(value)
    value = roles()
    for model in ("base", "candidate"):
        value["VALIDATION"][model].update(boards_expected=14, boards_matched=14, detection_recall=1)
    assert decide(value)["coverage"] == "incomplete"
