"""Closed photo-only report v3 and gate v2, independent of legacy policies."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, Final

from .grid_model_evaluation import (
    MAX_GAMES,
    MAX_REPORT_BYTES,
    ROLES,
    _count,
    _sha,
    _uuid,
    verdict_of,
)
from .grid_model_evaluation import (
    GridEvaluationReportError as GridEvaluationReportError,
)
from .grid_model_registry import canonical_json, descriptor_sha256

REPORT_SCHEMA: Final = "grid-model-evaluation-read-v3"
PRODUCER: Final = "server:grid-model-evaluator-v1"
POLICY_VERSION: Final = "grid-model-per-game-gate-v2"
METRICS_VERSION: Final = "grid-correction-metrics-v1"
CHECKPOINT_RULE: Final = "validation-board-correct-photo-macro-error-earliest-v1"
SCREEN_REPORT_SCHEMA: Final = "grid-model-evaluation-read-v4"
SCREEN_POLICY_VERSION: Final = "grid-model-per-game-gate-v3"
SCREEN_CHECKPOINT_RULE: Final = "validation-photo-board-correct-photo-macro-error-earliest-v1"
EPSILON: Final = 1e-9
PHOTO_ONLY_LIMITATIONS: Final = [
    "Session independence is not proven by photo-only evidence.",
    "Unknown ancestor training use cannot be excluded.",
    "Partial photos measure labelled targets only; unlabelled detections are not assessed.",
    "Improvement thresholds are product gates, not statistical significance.",
]
COUNT_KEYS: Final = (
    "photos",
    "full_photos",
    "partial_photos",
    "boards_expected",
    "boards_matched",
    "boards_correct",
)
FULL_COUNT_KEYS: Final = ("photo_complete_correct", "false_boards", "duplicate_predictions")
RATE_KEYS: Final = ("board_correct_rate", "detection_recall", "normalized_error")
METRIC_KEYS: Final = {*COUNT_KEYS, *FULL_COUNT_KEYS, *RATE_KEYS, "photo_complete_correct_rate"}
POLICY: Final[dict[str, Any]] = {
    "policyVersion": POLICY_VERSION,
    "metricsVersion": METRICS_VERSION,
    "minimumControlPhotos": 5,
    "minimumControlBoards": 15,
    "nonRegression": ["boards_matched", "boards_correct", "normalized_error"],
    "fullPhotoNonRegression": ["false_boards", "duplicate_predictions", "photo_complete_correct"],
    "currentGameImprovementRole": "REGRESSION",
    "minimumCorrectBoardGain": 1,
    "minimumRelativeErrorReduction": 0.05,
    "minimumAbsoluteErrorReduction": 0.001,
    "epsilon": EPSILON,
    "checkpointRule": CHECKPOINT_RULE,
}
SCREEN_POLICY: Final[dict[str, Any]] = {
    **POLICY,
    "policyVersion": SCREEN_POLICY_VERSION,
    "checkpointRule": SCREEN_CHECKPOINT_RULE,
    "validationAssessment": "full-photos-v1",
    "regressionAssessment": "human-labeled-targets-v1",
}
REPORT_KEYS: Final = {
    "schemaVersion",
    "producer",
    "policyVersion",
    "policy",
    "versionId",
    "manifestSha256",
    "baseVersionId",
    "baseManifestSha256",
    "familyId",
    "trainingGameId",
    "parity",
    "cohorts",
    "requiredGameIds",
    "games",
    "verdict",
    "scope",
    "evidenceLevel",
    "limitations",
    "checkpointSelection",
}
GAME_KEYS: Final = {
    "gameId",
    "cohortId",
    "mode",
    "targetMetric",
    "validation",
    "regression",
    "coverage",
    "reasons",
    "roles",
}


def _closed(value: object, keys: set[str], description: str) -> dict[str, Any]:
    if not isinstance(value, dict) or value.keys() != keys:
        raise GridEvaluationReportError(f"{description} keys differ from the v3 contract.")
    return value


def _unit(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise GridEvaluationReportError("A finite unit rate is required.")
    if not 0 <= value <= 1:
        raise GridEvaluationReportError("A rate is outside its range.")
    return float(value)


def require_metrics(value: object) -> dict[str, Any]:
    result = _closed(value, METRIC_KEYS, "Metrics")
    for key in COUNT_KEYS:
        _count(result[key])
    photos, full, partial = (result[key] for key in ("photos", "full_photos", "partial_photos"))
    if (
        full + partial != photos
        or not 0
        <= result["boards_correct"]
        <= result["boards_matched"]
        <= result["boards_expected"]
        or not 9 * full + partial <= result["boards_expected"] <= 9 * photos
    ):
        raise GridEvaluationReportError("Metric counts are inconsistent.")
    for key in RATE_KEYS:
        if photos:
            _unit(result[key])
        elif result[key] is not None:
            raise GridEvaluationReportError("An empty measurement has no rates.")
    if (
        photos
        and abs(result["detection_recall"] - result["boards_matched"] / result["boards_expected"])
        > EPSILON
    ):
        raise GridEvaluationReportError("Detection recall differs from the counts.")
    if not full:
        if any(
            result[key] is not None for key in (*FULL_COUNT_KEYS, "photo_complete_correct_rate")
        ):
            raise GridEvaluationReportError("Partial photos cannot claim full-photo evidence.")
    else:
        for key in FULL_COUNT_KEYS:
            _count(result[key])
        _unit(result["photo_complete_correct_rate"])
        if (
            result["photo_complete_correct"] > full
            or abs(result["photo_complete_correct_rate"] - result["photo_complete_correct"] / full)
            > EPSILON
        ):
            raise GridEvaluationReportError("Full-photo rates differ from the counts.")
    return result


def decide_game(
    *,
    mode: str,
    training: bool,
    parity_passed: bool,
    roles: Mapping[str, Any],
    screen: bool = False,
) -> dict[str, Any]:
    """Require every role to preserve quality; current-game REGRESSION must improve."""
    if mode != ("screen+grid" if screen else "grid-only") or set(roles) != set(ROLES):
        raise GridEvaluationReportError(
            "Correction gate requires grid-only and both control roles."
        )
    reasons = [] if parity_passed else ["CANDIDATE_PARITY_FAILED"]
    for role in ROLES:
        entry = roles[role]
        _count(entry["photos"])
        base, candidate = (require_metrics(entry[name]) for name in ("base", "candidate"))
        if (
            screen
            and role == "VALIDATION"
            and (
                base["full_photos"] != entry["photos"]
                or candidate["full_photos"] != entry["photos"]
            )
        ):
            reasons.append("SCREEN_FULL_VALIDATION_REQUIRED")
        if entry["photos"] < 5:
            reasons.append(f"COVERAGE_PHOTOS_BELOW_MINIMUM:{role}")
        if base["boards_expected"] < 15:
            reasons.append(f"COVERAGE_BOARDS_BELOW_MINIMUM:{role}")
        if (
            any(
                base[key] != candidate[key]
                for key in ("photos", "full_photos", "partial_photos", "boards_expected")
            )
            or base["photos"] != entry["photos"]
        ):
            reasons.append(f"COVERAGE_INCOMPLETE:{role}")
    if reasons:
        return {
            "validation": "not_evaluable",
            "regression": "not_evaluable",
            "coverage": "incomplete",
            "reasons": reasons,
        }
    outcome = {}
    for role in ROLES:
        base, candidate = roles[role]["base"], roles[role]["candidate"]
        before = len(reasons)
        for metric in ("boards_matched", "boards_correct"):
            if candidate[metric] < base[metric]:
                reasons.append(f"{role}_REGRESSED:{metric}")
        if candidate["normalized_error"] > base["normalized_error"] + EPSILON:
            reasons.append(f"{role}_REGRESSED:normalized_error")
        if base["full_photos"]:
            for metric in ("false_boards", "duplicate_predictions", "photo_complete_correct"):
                difference = candidate[metric] - base[metric]
                if difference > 0 if metric != "photo_complete_correct" else difference < 0:
                    reasons.append(f"{role}_REGRESSED:{metric}")
        if training and role == "REGRESSION":
            # Compare the serialized decimal measures at the product thresholds;
            # non-regression's epsilon must not relax the minimum improvement.
            base_error = Decimal(str(base["normalized_error"]))
            reduction = base_error - Decimal(str(candidate["normalized_error"]))
            improved = candidate["boards_correct"] >= base["boards_correct"] + 1 or (
                reduction >= Decimal("0.001") and reduction >= Decimal("0.05") * base_error
            )
            if not improved:
                reasons.append("REGRESSION_NOT_IMPROVED:boards_correct_or_normalized_error")
        outcome[role.lower()] = "pass" if len(reasons) == before else "fail"
    return {**outcome, "coverage": "complete", "reasons": reasons}


def _ids(value: object) -> list[str]:
    if not isinstance(value, list):
        raise GridEvaluationReportError("Game scope must be a sorted list.")
    ids = [_uuid(item) for item in value]
    if ids != sorted(set(ids)) or len(ids) > MAX_GAMES:
        raise GridEvaluationReportError("Game scope must be distinct and sorted.")
    return ids


def require_scope(value: object) -> tuple[dict[str, Any], list[str]]:
    scope = _closed(
        value,
        {
            "currentGameId",
            "trainingGameIds",
            "priorVerifiedGameIds",
            "priorScopeDocumented",
            "exclusions",
        },
        "Scope",
    )
    current = _uuid(scope["currentGameId"])
    training = _ids(scope["trainingGameIds"])
    prior = _ids(scope["priorVerifiedGameIds"])
    if (
        type(scope["priorScopeDocumented"]) is not bool
        or current not in training
        or (not scope["priorScopeDocumented"] and prior)
    ):
        raise GridEvaluationReportError("Training or historical scope evidence is inconsistent.")
    exclusions = scope["exclusions"]
    if not isinstance(exclusions, list):
        raise GridEvaluationReportError("Scope exclusions must be explicit.")
    excluded = []
    for item in exclusions:
        item = _closed(item, {"gameId", "reason", "confirmed"}, "Exclusion")
        game = _uuid(item["gameId"])
        if (
            game not in prior
            or game in training
            or item["confirmed"] is not True
            or not isinstance(item["reason"], str)
            or not item["reason"].strip()
        ):
            raise GridEvaluationReportError(
                "An exclusion needs a reason, confirmation and historical scope."
            )
        excluded.append(game)
    if excluded != sorted(set(excluded)):
        raise GridEvaluationReportError("Exclusions must be distinct and sorted.")
    required = sorted((set(training) | set(prior) | {current}) - set(excluded))
    if len(required) > MAX_GAMES:
        raise GridEvaluationReportError("The required scope is too large.")
    return scope, required


def require_checkpoint_selection(value: object, *, screen: bool = False) -> dict[str, Any]:
    keys = {"rule", "role", "step", "metrics", "earlyStopping"}
    if screen:
        keys |= {"selectionInputSha256", "metricStateVersion"}
    selection = _closed(value, keys, "Checkpoint")
    if screen:
        _sha(selection["selectionInputSha256"])
        if selection["metricStateVersion"] != "photo-board-checkpoint-state-v1":
            raise GridEvaluationReportError("Unknown screen checkpoint metric state.")
    if (
        selection["rule"] != (SCREEN_CHECKPOINT_RULE if screen else CHECKPOINT_RULE)
        or selection["role"] != "VALIDATION"
    ):
        raise GridEvaluationReportError("Only VALIDATION selects a checkpoint.")
    _count(selection["step"])
    metrics = _closed(
        selection["metrics"],
        {"boardCorrectRate", "normalizedError"} | ({"photoCorrectRate"} if screen else set()),
        "Checkpoint metrics",
    )
    for number in metrics.values():
        _unit(number)
    stopping = _closed(
        selection["earlyStopping"],
        {"patience", "evaluationsWithoutImprovement", "stopped"},
        "Early stopping",
    )
    if (
        _count(stopping["patience"]) < 1
        or type(stopping["stopped"]) is not bool
        or stopping["stopped"]
        != (_count(stopping["evaluationsWithoutImprovement"]) >= stopping["patience"])
    ):
        raise GridEvaluationReportError("Early stopping evidence is inconsistent.")
    return selection


def _require_role(value: object) -> dict[str, Any]:
    role = _closed(
        value, {"photos", "inputSha256", "base", "candidate", "recordings", "detail"}, "Role"
    )
    _count(role["photos"])
    _sha(role["inputSha256"])
    for model in ("base", "candidate"):
        require_metrics(role[model])
    groups = role["recordings"]
    if not isinstance(groups, list) or (role["photos"] > 0 and not groups):
        raise GridEvaluationReportError("Measured photos require their source groups.")
    ids = []
    for group in groups:
        group = _closed(group, {"groupId", "base", "candidate"}, "Source group")
        ids.append(_uuid(group["groupId"]))
        for model in ("base", "candidate"):
            require_metrics(group[model])
        if any(
            group["base"][key] != group["candidate"][key]
            for key in ("photos", "full_photos", "partial_photos", "boards_expected")
        ):
            raise GridEvaluationReportError("Models must measure identical source groups.")
    if ids != sorted(set(ids)):
        raise GridEvaluationReportError("Source groups must be distinct and sorted.")
    for model in ("base", "candidate"):
        total = role[model]
        if any(sum(group[model][key] for group in groups) != total[key] for key in COUNT_KEYS):
            raise GridEvaluationReportError("Source group counts differ from the role.")
        for key in FULL_COUNT_KEYS:
            if (
                total["full_photos"]
                and sum(group[model][key] or 0 for group in groups) != total[key]
            ):
                raise GridEvaluationReportError("Full-photo counts differ from the role.")
        for key in ("board_correct_rate", "normalized_error"):
            if (
                total["photos"]
                and abs(
                    sum((group[model][key] or 0) * group[model]["photos"] for group in groups)
                    / total["photos"]
                    - total[key]
                )
                > EPSILON
            ):
                raise GridEvaluationReportError("Source group photo means differ from the role.")
    detail = _closed(role["detail"], {"path", "sha256"}, "Detail pin")
    if not isinstance(detail["path"], str) or not detail["path"] or ".." in detail["path"]:
        raise GridEvaluationReportError("Detail path is invalid.")
    _sha(detail["sha256"])
    return role


def build_report(
    *,
    manifest: Mapping[str, Any],
    base_manifest_sha256: str,
    training_game_id: str,
    parity: Mapping[str, Any],
    cohorts: Sequence[Mapping[str, Any]],
    measured: Mapping[str, Mapping[str, Any]],
    scope: Mapping[str, Any],
    checkpoint_selection: Mapping[str, Any],
) -> dict[str, Any]:
    screen = checkpoint_selection.get("rule") == SCREEN_CHECKPOINT_RULE
    require_checkpoint_selection(dict(checkpoint_selection), screen=screen)
    scope_value, required = require_scope(dict(scope))
    ordered = sorted(
        (
            {key: entry[key] for key in ("gameId", "cohortId", "manifestSha256")}
            for entry in cohorts
        ),
        key=lambda entry: entry["gameId"],
    )
    games = []
    for entry in ordered:
        game = measured[entry["gameId"]]
        decision = decide_game(
            mode=game["mode"],
            training=entry["gameId"] == training_game_id,
            parity_passed=parity["passed"],
            roles=game["roles"],
            screen=screen,
        )
        games.append(
            {
                "gameId": entry["gameId"],
                "cohortId": entry["cohortId"],
                "mode": game["mode"],
                "targetMetric": "boards_correct_or_normalized_error",
                **decision,
                "roles": {role: dict(game["roles"][role]) for role in ROLES},
            }
        )
    report = {
        "schemaVersion": SCREEN_REPORT_SCHEMA if screen else REPORT_SCHEMA,
        "producer": PRODUCER,
        "policyVersion": SCREEN_POLICY_VERSION if screen else POLICY_VERSION,
        "policy": SCREEN_POLICY if screen else POLICY,
        "versionId": manifest["versionId"],
        "manifestSha256": descriptor_sha256(dict(manifest)),
        "baseVersionId": manifest["baseVersionId"],
        "baseManifestSha256": base_manifest_sha256,
        "familyId": manifest["familyId"],
        "trainingGameId": training_game_id,
        "parity": dict(parity),
        "cohorts": ordered,
        "requiredGameIds": required,
        "games": games,
        "verdict": verdict_of(games),
        "scope": scope_value,
        "evidenceLevel": "photo-only",
        "limitations": PHOTO_ONLY_LIMITATIONS,
        "checkpointSelection": dict(checkpoint_selection),
    }
    return require_report(
        canonical_json(report), manifest=manifest, base_sha256=base_manifest_sha256
    )


def require_report(
    report_json: str, *, manifest: Mapping[str, Any], base_sha256: str
) -> dict[str, Any]:
    """Recompute scope and decisions; reject any unsigned interpretation or unknown field."""
    try:
        if len(report_json.encode("utf-8")) > MAX_REPORT_BYTES:
            raise GridEvaluationReportError("The report is too large.")
        report = _closed(json.loads(report_json), REPORT_KEYS, "Report")
        screen = report["schemaVersion"] == SCREEN_REPORT_SCHEMA
        if canonical_json(report) != report_json:
            raise GridEvaluationReportError("The report is not canonical JSON.")
        if (
            report["schemaVersion"] != (SCREEN_REPORT_SCHEMA if screen else REPORT_SCHEMA)
            or report["producer"] != PRODUCER
            or report["policyVersion"] != (SCREEN_POLICY_VERSION if screen else POLICY_VERSION)
            or report["policy"] != (SCREEN_POLICY if screen else POLICY)
            or report["versionId"] != manifest["versionId"]
            or report["manifestSha256"] != descriptor_sha256(dict(manifest))
            or report["baseVersionId"] != manifest["baseVersionId"]
            or report["baseManifestSha256"] != base_sha256
            or report["familyId"] != manifest["familyId"]
            or manifest["cohortId"] is None
            or report["evidenceLevel"] != "photo-only"
            or report["limitations"] != PHOTO_ONLY_LIMITATIONS
        ):
            raise GridEvaluationReportError("Report identity, policy or evidence differs.")
        for key in ("versionId", "baseVersionId", "familyId", "trainingGameId"):
            _uuid(report[key])
        _sha(report["manifestSha256"])
        _sha(report["baseManifestSha256"])
        scope, required = require_scope(report["scope"])
        if (
            report["trainingGameId"] != scope["currentGameId"]
            or report["requiredGameIds"] != required
        ):
            raise GridEvaluationReportError("Report scope differs from its required games.")
        require_checkpoint_selection(report["checkpointSelection"], screen=screen)
        parity = _closed(report["parity"], {"passed", "bundleSha256"}, "Parity")
        if type(parity["passed"]) is not bool:
            raise GridEvaluationReportError("Parity requires a boolean result.")
        _sha(parity["bundleSha256"])
        cohorts = report["cohorts"]
        if not isinstance(cohorts, list) or not 1 <= len(cohorts) <= MAX_GAMES:
            raise GridEvaluationReportError("The cohort scope is incomplete.")
        for entry in cohorts:
            entry = _closed(entry, {"gameId", "cohortId", "manifestSha256"}, "Cohort")
            _uuid(entry["gameId"])
            _uuid(entry["cohortId"])
            _sha(entry["manifestSha256"])
        if [entry["gameId"] for entry in cohorts] != required or len(
            {entry["cohortId"] for entry in cohorts}
        ) != len(cohorts):
            raise GridEvaluationReportError("Every required game needs one distinct pinned cohort.")
        current = next(entry for entry in cohorts if entry["gameId"] == report["trainingGameId"])
        if current["cohortId"] != manifest["cohortId"]:
            raise GridEvaluationReportError("The training cohort differs from the candidate.")
        games = report["games"]
        if not isinstance(games, list) or len(games) != len(cohorts):
            raise GridEvaluationReportError("Every required game needs measurements.")
        for entry, game in zip(cohorts, games, strict=True):
            game = _closed(game, GAME_KEYS, "Game")
            if (
                game["gameId"] != entry["gameId"]
                or game["cohortId"] != entry["cohortId"]
                or game["mode"] != ("screen+grid" if screen else "grid-only")
                or game["targetMetric"] != "boards_correct_or_normalized_error"
            ):
                raise GridEvaluationReportError("Measured game differs from its cohort.")
            roles = _closed(game["roles"], set(ROLES), "Roles")
            for role in ROLES:
                _require_role(roles[role])
            decision = decide_game(
                mode=game["mode"],
                training=game["gameId"] == report["trainingGameId"],
                parity_passed=parity["passed"],
                roles=roles,
                screen=screen,
            )
            if any(game[key] != value for key, value in decision.items()):
                raise GridEvaluationReportError("Stored decisions differ from gate v2.")
        if report["verdict"] != verdict_of(games):
            raise GridEvaluationReportError("Stored verdict differs from gate v2.")
        return report
    except (KeyError, TypeError, AttributeError, ValueError, StopIteration) as error:
        if isinstance(error, GridEvaluationReportError):
            raise
        raise GridEvaluationReportError("The report does not follow the v3 contract.") from error
