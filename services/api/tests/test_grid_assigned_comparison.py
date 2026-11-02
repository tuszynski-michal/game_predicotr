"""Assigned model pins remain distinct from training ancestry; both roles must preserve quality."""

from copy import deepcopy
from typing import Any
from uuid import UUID

import pytest
from game_predictor_api.domain.grid_assigned_comparison import (
    GridEvaluationReportError,
    build_report,
    require_report,
)
from game_predictor_api.domain.grid_correction_evaluation import CHECKPOINT_RULE
from game_predictor_api.domain.grid_correction_evaluation import (
    build_report as build_correction_report,
)
from game_predictor_api.domain.grid_model_evaluation import REPORT_KEYS as LEGACY_REPORT_KEYS
from game_predictor_api.domain.grid_model_registry import canonical_json
from game_predictor_api.schemas.grid_model_evaluations import (
    GridAssignedComparisonCreate,
    GridAssignedComparisonReport,
    GridCorrectionEvaluationReport,
    GridModelEvaluationCreate,
    GridModelEvaluationReport,
    GridModelEvaluationView,
)
from pydantic import ValidationError


def uid(number: int) -> str:
    return str(UUID(int=number))


def metrics() -> dict[str, Any]:
    return {
        "photos": 5,
        "full_photos": 0,
        "partial_photos": 5,
        "boards_expected": 15,
        "boards_matched": 15,
        "boards_correct": 12,
        "board_correct_rate": 0.8,
        "detection_recall": 1.0,
        "normalized_error": 0.02,
        "photo_complete_correct": None,
        "photo_complete_correct_rate": None,
        "false_boards": None,
        "duplicate_predictions": None,
    }


def role() -> dict[str, Any]:
    return {
        "photos": 5,
        "inputSha256": "a" * 64,
        "base": metrics(),
        "candidate": metrics(),
        "recordings": [{"groupId": uid(100), "base": metrics(), "candidate": metrics()}],
        "detail": {"path": "grid-model-evaluations/assigned-role.json", "sha256": "b" * 64},
    }


def arguments() -> dict[str, Any]:
    return {
        "manifest": {
            "versionId": uid(1),
            "baseVersionId": uid(2),
            "familyId": uid(3),
            "cohortId": uid(4),
        },
        "baseline_manifest_sha256": "c" * 64,
        "baseline_version_id": uid(5),
        "game_id": uid(6),
        "assignment_revision": 7,
        "cohort": {"gameId": uid(6), "cohortId": uid(8), "manifestSha256": "d" * 64},
        "measured": {"mode": "grid-only", "roles": {"VALIDATION": role(), "REGRESSION": role()}},
        "parity": {"passed": True, "bundleSha256": "e" * 64},
    }


def read(report: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    return require_report(
        canonical_json(report),
        manifest=args["manifest"],
        baseline_sha256=args["baseline_manifest_sha256"],
        expected_baseline_version_id=args["baseline_version_id"],
        expected_game_id=args["game_id"],
        expected_assignment_revision=args["assignment_revision"],
        expected_cohort=args["cohort"],
    )


def test_actual_assigned_baseline_and_cohort_are_not_training_base_or_training_cohort() -> None:
    args = arguments()
    original = deepcopy(args)
    report = build_report(**args)
    assert args == original
    assert report["baselineVersionId"] != args["manifest"]["baseVersionId"]
    assert report["cohort"]["cohortId"] != args["manifest"]["cohortId"]
    assert "baseVersionId" not in report
    assert report["verdict"] == "PASS"
    assert report["decision"] == {
        "validation": "pass",
        "regression": "pass",
        "coverage": "complete",
        "reasons": [],
    }
    assert read(report, args) == report
    args["measured"]["roles"]["VALIDATION"]["base"]["boards_correct"] = 1
    assert report["roles"]["VALIDATION"]["base"]["boards_correct"] == 12


@pytest.mark.parametrize("role_name", ["VALIDATION", "REGRESSION"])
@pytest.mark.parametrize(
    "metric,value", [("boards_correct", 11), ("boards_matched", 14), ("normalized_error", 0.03)]
)
def test_any_role_regression_cannot_pass(role_name: str, metric: str, value: int | float) -> None:
    args = arguments()
    chosen = args["measured"]["roles"][role_name]
    for model in (chosen["candidate"], chosen["recordings"][0]["candidate"]):
        model[metric] = value
        model["detection_recall"] = model["boards_matched"] / model["boards_expected"]
        model["board_correct_rate"] = model["boards_correct"] / model["boards_expected"]
    report = build_report(**args)
    assert report["verdict"] == "REVISE"
    assert report["decision"][role_name.lower()] == "fail"
    report["verdict"] = "PASS"
    with pytest.raises(GridEvaluationReportError):
        read(report, args)


def test_failed_parity_is_not_evaluable_and_no_improvement_is_required() -> None:
    args = arguments()
    assert build_report(**args)["verdict"] == "PASS"
    args["parity"]["passed"] = False
    report = build_report(**args)
    assert report["verdict"] == "NOT_EVALUABLE"
    assert report["decision"]["reasons"] == ["CANDIDATE_PARITY_FAILED"]


@pytest.mark.parametrize(
    "key,value",
    [
        ("versionId", uid(101)),
        ("manifestSha256", "f" * 64),
        ("baselineVersionId", uid(102)),
        ("baselineManifestSha256", "f" * 64),
        ("gameId", uid(103)),
        ("assignmentRevision", 8),
        ("assignmentRevision", -1),
        ("assignmentRevision", True),
        ("producer", "client:spoof"),
        ("policyVersion", "grid-model-per-game-gate-v2"),
        ("schemaVersion", "grid-model-evaluation-read-v3"),
        ("evidenceLevel", "independent"),
        ("limitations", []),
        ("extra", True),
    ],
)
def test_forged_identity_scope_and_provenance_are_rejected(key: str, value: Any) -> None:
    args = arguments()
    report = build_report(**args)
    report[key] = value
    with pytest.raises(GridEvaluationReportError):
        read(report, args)


@pytest.mark.parametrize("target", ["cohort", "detail", "role", "decision", "training_base"])
def test_nested_pins_and_candidate_ancestry_are_bound(target: str) -> None:
    args = arguments()
    report = build_report(**args)
    if target == "cohort":
        report["cohort"]["cohortId"] = uid(90)
    elif target == "detail":
        report["roles"]["VALIDATION"]["detail"]["sha256"] = "invalid"
    elif target == "role":
        report["roles"]["VALIDATION"]["recordings"][0]["candidate"]["normalized_error"] = 0.03
    elif target == "decision":
        report["decision"]["extra"] = True
    else:
        args["manifest"]["baseVersionId"] = report["baselineVersionId"]
    with pytest.raises(GridEvaluationReportError):
        read(report, args)


def correction_report() -> dict[str, Any]:
    args = arguments()
    args["cohort"]["cohortId"] = args["manifest"]["cohortId"]
    chosen = args["measured"]["roles"]["REGRESSION"]
    for model in (chosen["candidate"], chosen["recordings"][0]["candidate"]):
        model.update(boards_correct=13, board_correct_rate=13 / 15)
    return build_correction_report(
        manifest=args["manifest"],
        base_manifest_sha256="f" * 64,
        training_game_id=uid(6),
        parity=args["parity"],
        cohorts=[args["cohort"]],
        measured={uid(6): args["measured"]},
        scope={
            "currentGameId": uid(6),
            "trainingGameIds": [uid(6)],
            "priorVerifiedGameIds": [],
            "priorScopeDocumented": False,
            "exclusions": [],
        },
        checkpoint_selection={
            "rule": CHECKPOINT_RULE,
            "role": "VALIDATION",
            "step": 10,
            "metrics": {"boardCorrectRate": 0.8, "normalizedError": 0.02},
            "earlyStopping": {"patience": 3, "evaluationsWithoutImprovement": 1, "stopped": False},
        },
    )


def view(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "evaluationId": uid(20),
        "reportId": uid(21),
        "status": "completed",
        "stage": None,
        "versionId": uid(1),
        "baseVersionId": uid(2),
        "trainingGameId": uid(6),
        "cohorts": [{"gameId": uid(6), "cohortId": uid(8)}],
        "progressCurrent": 2,
        "progressTotal": 2,
        "verdict": "PASS",
        "cancelRequested": False,
        "errorCode": None,
        "createdAt": "now",
        "updatedAt": "now",
        "report": report,
        "currentness": [],
    }


def test_typed_report_union_keeps_v2_contract_and_separates_assigned_pins() -> None:
    assert set(GridModelEvaluationReport.model_fields) == LEGACY_REPORT_KEYS
    assigned = build_report(**arguments())
    parsed = GridModelEvaluationView.model_validate(
        {**view(assigned), "assignedBaselineVersionId": uid(5), "assignmentRevision": 7}
    )
    assert isinstance(parsed.report, GridAssignedComparisonReport)
    assert str(parsed.baseVersionId) == uid(2)
    assert str(parsed.assignedBaselineVersionId) == uid(5)
    assert parsed.report.model_dump(mode="json") == assigned
    correction = correction_report()
    parsed = GridModelEvaluationView.model_validate(view(correction))
    assert isinstance(parsed.report, GridCorrectionEvaluationReport)
    assert parsed.report.model_dump(mode="json") == correction
    assert parsed.assignedBaselineVersionId is None and parsed.assignmentRevision is None
    assigned["roles"]["VALIDATION"]["base"]["unknown"] = 1
    with pytest.raises(ValidationError):
        GridModelEvaluationView.model_validate(view(assigned))


def test_assigned_create_accepts_only_identity_and_scope_not_client_baseline() -> None:
    command = {"idempotencyKey": uid(30), "versionId": uid(1), "gameId": uid(6), "cohortId": uid(8)}
    assert GridAssignedComparisonCreate.model_validate(command).model_dump(mode="json") == command
    for key in ("baselineVersionId", "assignmentRevision", "baselineManifestSha256"):
        with pytest.raises(ValidationError):
            GridAssignedComparisonCreate.model_validate({**command, key: uid(5)})
    ordinary = {
        "idempotencyKey": uid(30),
        "versionId": uid(1),
        "cohorts": [{"gameId": uid(6), "cohortId": uid(8)}],
    }
    assert GridModelEvaluationCreate.model_validate(ordinary).exclusions == []
    excluded = {"gameId": uid(50), "reason": "Labels withdrawn", "confirmed": True}
    assert (
        GridModelEvaluationCreate.model_validate({**ordinary, "exclusions": [excluded]})
        .exclusions[0]
        .reason
        == excluded["reason"]
    )


def test_closed_typed_v3_nested_policy_checkpoint_and_scope() -> None:
    original = correction_report()
    for block in ("policy", "scope", "checkpointSelection"):
        forged = deepcopy(original)
        forged[block]["unverified"] = True
        with pytest.raises(ValidationError):
            GridCorrectionEvaluationReport.model_validate(forged)
