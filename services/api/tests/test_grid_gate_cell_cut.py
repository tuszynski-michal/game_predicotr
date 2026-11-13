"""Gate v5 (D-609): gate v4 plus boards whose cells stay within 10 % of the label cell."""

import copy
from typing import Any

import pytest
from game_predictor_api.domain.grid_correction_evaluation import (
    CELL_CUT_POLICY,
    CELL_CUT_POLICY_VERSION,
    TOLERANT_POLICY,
    TOLERANT_POLICY_VERSION,
    GridEvaluationReportError,
    build_report,
    decide_game,
    require_report,
)
from game_predictor_api.domain.grid_model_registry import canonical_json
from test_grid_correction_evaluation import CHECKPOINT_RULE, metrics, role, uid


def cut(base: int, candidate: int) -> dict[str, Any]:
    return {"version": "grid-cell-cut-v1", "tolerance": 0.10, "base": base, "candidate": candidate}


def roles(validation: tuple[int, int] = (15, 15), regression: tuple[int, int] = (15, 15)):
    value = {"VALIDATION": role(metrics(), metrics()), "REGRESSION": role(metrics(), metrics())}
    value["VALIDATION"]["cellCut"] = cut(*validation)
    value["REGRESSION"]["cellCut"] = cut(*regression)
    return value


def decide(value: dict[str, Any]) -> dict[str, Any]:
    return decide_game(
        mode="grid-only",
        training=True,
        parity_passed=True,
        roles=value,
        tolerant=True,
        cell_cut=True,
    )


def report_for(measured_roles: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = {
        "versionId": uid(1),
        "baseVersionId": uid(2),
        "familyId": uid(3),
        "cohortId": uid(4),
    }
    report = build_report(
        manifest=manifest,
        base_manifest_sha256="c" * 64,
        training_game_id=uid(5),
        parity={"passed": True, "bundleSha256": "d" * 64},
        cohorts=[{"gameId": uid(5), "cohortId": uid(4), "manifestSha256": "e" * 64}],
        measured={uid(5): {"mode": "grid-only", "roles": measured_roles}},
        scope={
            "currentGameId": uid(5),
            "trainingGameIds": [uid(5)],
            "priorVerifiedGameIds": [],
            "priorScopeDocumented": True,
            "exclusions": [],
        },
        checkpoint_selection={
            "rule": CHECKPOINT_RULE,
            "role": "VALIDATION",
            "step": 100,
            "metrics": {"boardCorrectRate": 0.8, "normalizedError": 0.02},
            "earlyStopping": {"patience": 3, "evaluationsWithoutImprovement": 0, "stopped": False},
        },
    )
    return manifest, report


def test_equal_boards_within_cells_pass() -> None:
    assert decide(roles()) == {
        "validation": "pass",
        "regression": "pass",
        "coverage": "complete",
        "reasons": [],
    }


def test_one_more_cut_board_is_noise_but_two_reject() -> None:
    assert decide(roles(validation=(15, 14)))["validation"] == "pass"
    result = decide(roles(validation=(15, 13)))
    assert result["validation"] == "fail"
    assert result["reasons"] == ["VALIDATION_REGRESSED:boards_within_cells"]


def test_cell_cut_rejects_even_when_v4_metrics_are_identical() -> None:
    value = roles(regression=(12, 9))
    plain = {
        name: {k: v for k, v in entry.items() if k != "cellCut"} for name, entry in value.items()
    }
    assert (
        decide_game(
            mode="grid-only", training=True, parity_passed=True, roles=plain, tolerant=True
        )["regression"]
        == "pass"
    )
    assert decide(value)["regression"] == "fail"


def test_v5_extends_only_the_tolerant_gate() -> None:
    with pytest.raises(GridEvaluationReportError):
        decide_game(
            mode="grid-only", training=True, parity_passed=True, roles=roles(), cell_cut=True
        )


def test_measured_cell_cut_makes_a_v5_report_and_it_replays() -> None:
    manifest, report = report_for(roles(validation=(15, 13)))
    assert report["policyVersion"] == CELL_CUT_POLICY_VERSION
    assert report["policy"] == CELL_CUT_POLICY
    assert report["verdict"] != "PASS"
    assert report["games"][0]["reasons"] == ["VALIDATION_REGRESSED:boards_within_cells"]
    assert require_report(canonical_json(report), manifest=manifest, base_sha256="c" * 64)


def test_older_measurement_without_cell_cut_stays_v4() -> None:
    plain = {"VALIDATION": role(metrics(), metrics()), "REGRESSION": role(metrics(), metrics())}
    _, report = report_for(plain)
    assert report["policyVersion"] == TOLERANT_POLICY_VERSION
    assert report["policy"] == TOLERANT_POLICY
    assert "cellCut" not in report["games"][0]["roles"]["VALIDATION"]


def test_forged_cell_cut_evidence_or_relabel_is_rejected() -> None:
    manifest, report = report_for(roles(validation=(15, 13)))
    relabelled = {**report, "policyVersion": TOLERANT_POLICY_VERSION, "policy": TOLERANT_POLICY}
    with pytest.raises(GridEvaluationReportError):
        require_report(canonical_json(relabelled), manifest=manifest, base_sha256="c" * 64)
    for change in (
        lambda entry: entry["cellCut"].update(candidate=99),
        lambda entry: entry["cellCut"].update(tolerance=0.2),
        lambda entry: entry["cellCut"].pop("version"),
        lambda entry: entry.pop("cellCut"),
        lambda entry: entry["cellCut"].update(candidate=15),
    ):
        forged = copy.deepcopy(report)
        change(forged["games"][0]["roles"]["VALIDATION"])
        with pytest.raises(GridEvaluationReportError):
            require_report(canonical_json(forged), manifest=manifest, base_sha256="c" * 64)
