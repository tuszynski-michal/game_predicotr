"""Measured per-game evaluation report v2 and its gate policy (TASK-0997, D-559).

The server evaluator writes the report; the publication reader recomputes every
decision from the stored measures with the same ``decide_game`` and rejects a
report whose decisions differ. Base and candidate are measured on identical
control photos; REGRESSION only feeds the final non-regression check.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, Final
from uuid import UUID

from .grid_model_registry import canonical_json, descriptor_sha256

REPORT_SCHEMA: Final = "grid-model-evaluation-read-v2"
PRODUCER: Final = "server:grid-model-evaluator-v1"
POLICY_VERSION: Final = "grid-model-per-game-gate-v1"
METRICS_VERSION: Final = "neural-grid-metrics-v1"
EVALUATION_KIND: Final = "grid-model-evaluation-v1"
ROLES: Final = ("VALIDATION", "REGRESSION")
MODES: Final = ("grid-only", "screen+grid")
MAX_GAMES: Final = 100
MAX_REPORT_BYTES: Final = 1024 * 1024
MIN_CONTROL_PHOTOS: Final = 5
MACRO_EPSILON: Final = 1e-9
COUNT_KEYS: Final = (
    "photos",
    "photo_complete_correct",
    "boards_expected",
    "boards_correct",
    "boards_matched",
    "false_boards",
    "duplicate_predictions",
)
RATE_KEYS: Final = (
    "photo_complete_correct_rate",
    "board_correct_rate",
    "detection_recall",
    "image_macro",
    "nme_p95",
    "max_node_error_p95",
)
METRIC_KEYS: Final = (*COUNT_KEYS, *RATE_KEYS)
# A missing board lowers the matched/correct counts and costs 1 in image_macro. An extra
# detection is a false board, or a duplicate when it overlaps an already matched board.
NON_REGRESSION: Final = (
    ("photo_complete_correct", "higher"),
    ("boards_correct", "higher"),
    ("boards_matched", "higher"),
    ("false_boards", "lower"),
    ("duplicate_predictions", "lower"),
    ("image_macro", "lower"),
)
TARGET_METRIC: Final = {"grid-only": "boards_correct", "screen+grid": "photo_complete_correct"}
POLICY: Final[dict[str, Any]] = {
    "policyVersion": POLICY_VERSION,
    "metricsVersion": METRICS_VERSION,
    "minimumControlPhotos": MIN_CONTROL_PHOTOS,
    "nonRegression": [{"metric": name, "better": better} for name, better in NON_REGRESSION],
    "targetMetric": dict(TARGET_METRIC),
    "trainingGameValidation": "strict_improvement",
    "otherGameValidation": "non_regression",
    "regressionRole": "final_non_regression_only",
    "imageMacroEpsilon": MACRO_EPSILON,
}
REPORT_KEYS: Final = frozenset(
    {
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
    }
)
GAME_KEYS: Final = frozenset(
    {
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
)
ROLE_KEYS: Final = frozenset({"photos", "inputSha256", "base", "candidate", "recordings", "detail"})
_SHA = re.compile(r"[0-9a-f]{64}")


class GridEvaluationReportError(ValueError):
    """A report differs from the closed v2 contract; never a partial PASS."""


def _uuid(value: object) -> str:
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise GridEvaluationReportError("A canonical UUID is required.")
    return value


def _sha(value: object) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise GridEvaluationReportError("A lowercase SHA-256 is required.")
    return value


def _count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GridEvaluationReportError("Counts are non-negative integers.")
    return value


def _rate(value: object, *, unit: bool) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise GridEvaluationReportError("Rates are finite numbers or null.")
    if value < 0 or (unit and value > 1):
        raise GridEvaluationReportError("A rate is outside its range.")
    return float(value)


def require_metrics(value: object) -> dict[str, Any]:
    """Closed metric block of one model on one role or recording."""
    if not isinstance(value, dict) or value.keys() != set(METRIC_KEYS):
        raise GridEvaluationReportError("Metric keys differ from the v2 contract.")
    for key in COUNT_KEYS:
        _count(value[key])
    for key in RATE_KEYS:
        _rate(value[key], unit=key != "nme_p95" and key != "max_node_error_p95")
    if (
        value["photo_complete_correct"] > value["photos"]
        or value["boards_correct"] > value["boards_matched"]
        or value["boards_matched"] > value["boards_expected"]
    ):
        raise GridEvaluationReportError("Metric counts are inconsistent.")
    return value


def _better(base: float, candidate: float, better: str) -> int:
    """1 when the candidate improves, -1 when it regresses, 0 when equal."""
    difference = candidate - base if better == "higher" else base - candidate
    if abs(difference) <= MACRO_EPSILON:
        return 0
    return 1 if difference > 0 else -1


def _macro(value: float | None) -> float:
    # An unknown quality is never a zero error: a missing macro costs the maximum.
    return 1.0 if value is None else value


def _compare(
    base: Mapping[str, Any], candidate: Mapping[str, Any], metric: str, better: str
) -> int:
    if metric == "image_macro":
        return _better(_macro(base[metric]), _macro(candidate[metric]), better)
    return _better(float(base[metric]), float(candidate[metric]), better)


def decide_game(
    *, mode: str, training: bool, parity_passed: bool, roles: Mapping[str, Any]
) -> dict[str, Any]:
    """Validation, regression, coverage and reasons of one game (policy v1)."""
    reasons: list[str] = []
    if not parity_passed:
        reasons.append("CANDIDATE_PARITY_FAILED")
    for role in ROLES:
        entry = roles[role]
        photos = entry["photos"]
        if photos < MIN_CONTROL_PHOTOS:
            reasons.append(f"COVERAGE_PHOTOS_BELOW_MINIMUM:{role}")
        if entry["base"]["photos"] != photos or entry["candidate"]["photos"] != photos:
            reasons.append(f"COVERAGE_INCOMPLETE:{role}")
    coverage = "complete" if not reasons else "incomplete"
    if coverage != "complete":
        return {
            "validation": "not_evaluable",
            "regression": "not_evaluable",
            "coverage": coverage,
            "reasons": reasons,
        }
    outcome: dict[str, str] = {}
    for role in ROLES:
        base, candidate = roles[role]["base"], roles[role]["candidate"]
        passed = True
        for metric, better in NON_REGRESSION:
            if _compare(base, candidate, metric, better) < 0:
                reasons.append(f"{role}_REGRESSED:{metric}")
                passed = False
        if role == "VALIDATION" and training:
            target = TARGET_METRIC[mode]
            if _compare(base, candidate, target, "higher") <= 0:
                reasons.append(f"VALIDATION_NOT_IMPROVED:{target}")
                passed = False
        outcome[role] = "pass" if passed else "fail"
    return {
        "validation": outcome["VALIDATION"],
        "regression": outcome["REGRESSION"],
        "coverage": coverage,
        "reasons": reasons,
    }


def verdict_of(games: Sequence[Mapping[str, Any]]) -> str:
    if any(game["coverage"] != "complete" for game in games):
        return "NOT_EVALUABLE"
    if all(game["validation"] == "pass" and game["regression"] == "pass" for game in games):
        return "PASS"
    return "REVISE"


def build_report(
    *,
    manifest: Mapping[str, Any],
    base_manifest_sha256: str,
    training_game_id: str,
    parity: Mapping[str, Any],
    cohorts: Sequence[Mapping[str, Any]],
    measured: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Assemble the closed report; ``measured`` maps a game ID to its mode and roles."""
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
            parity_passed=bool(parity["passed"]),
            roles=game["roles"],
        )
        games.append(
            {
                "gameId": entry["gameId"],
                "cohortId": entry["cohortId"],
                "mode": game["mode"],
                "targetMetric": TARGET_METRIC[game["mode"]],
                **decision,
                "roles": {role: dict(game["roles"][role]) for role in ROLES},
            }
        )
    report = {
        "schemaVersion": REPORT_SCHEMA,
        "producer": PRODUCER,
        "policyVersion": POLICY_VERSION,
        "policy": POLICY,
        "versionId": manifest["versionId"],
        "manifestSha256": descriptor_sha256(dict(manifest)),
        "baseVersionId": manifest["baseVersionId"],
        "baseManifestSha256": base_manifest_sha256,
        "familyId": manifest["familyId"],
        "trainingGameId": training_game_id,
        "parity": {"passed": bool(parity["passed"]), "bundleSha256": parity["bundleSha256"]},
        "cohorts": ordered,
        "requiredGameIds": [entry["gameId"] for entry in ordered],
        "games": games,
        "verdict": verdict_of(games),
    }
    require_report(canonical_json(report), manifest=manifest, base_sha256=base_manifest_sha256)
    return report


def _require_role(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or value.keys() != ROLE_KEYS:
        raise GridEvaluationReportError("Role keys differ from the v2 contract.")
    _count(value["photos"])
    _sha(value["inputSha256"])
    require_metrics(value["base"])
    require_metrics(value["candidate"])
    recordings = value["recordings"]
    if not isinstance(recordings, list) or not recordings:
        raise GridEvaluationReportError("Each role reports its recordings.")
    groups = []
    for recording in recordings:
        if not isinstance(recording, dict) or recording.keys() != {"groupId", "base", "candidate"}:
            raise GridEvaluationReportError("Recording keys differ from the v2 contract.")
        groups.append(_uuid(recording["groupId"]))
        require_metrics(recording["base"])
        require_metrics(recording["candidate"])
    if groups != sorted(set(groups)):
        raise GridEvaluationReportError("Recordings must be unique and sorted.")
    for model in ("base", "candidate"):
        if sum(item[model]["photos"] for item in recordings) != value[model]["photos"]:
            raise GridEvaluationReportError("Recording photos differ from the role total.")
    detail = value["detail"]
    if not isinstance(detail, dict) or detail.keys() != {"path", "sha256"}:
        raise GridEvaluationReportError("Detail pin differs from the v2 contract.")
    if not isinstance(detail["path"], str) or not detail["path"] or ".." in detail["path"]:
        raise GridEvaluationReportError("Detail path is invalid.")
    _sha(detail["sha256"])
    return value


def require_report(
    report_json: str, *, manifest: Mapping[str, Any], base_sha256: str
) -> dict[str, Any]:
    """Closed v2 reader: identity, scope, measures and recomputed decisions."""
    try:
        if len(report_json.encode("utf-8")) > MAX_REPORT_BYTES:
            raise GridEvaluationReportError("The report is too large.")
        report = json.loads(report_json)
        if not isinstance(report, dict) or canonical_json(report) != report_json:
            raise GridEvaluationReportError("The report is not canonical JSON.")
        if (
            report.keys() != REPORT_KEYS
            or report["schemaVersion"] != REPORT_SCHEMA
            or report["producer"] != PRODUCER
            or report["policyVersion"] != POLICY_VERSION
            or report["policy"] != POLICY
            or report["versionId"] != manifest["versionId"]
            or report["manifestSha256"] != descriptor_sha256(dict(manifest))
            or report["baseVersionId"] != manifest["baseVersionId"]
            or report["baseManifestSha256"] != base_sha256
            or report["familyId"] != manifest["familyId"]
            or manifest["cohortId"] is None
        ):
            raise GridEvaluationReportError("Report identity or policy differs.")
        for key in ("versionId", "baseVersionId", "familyId", "trainingGameId"):
            _uuid(report[key])
        parity = report["parity"]
        if (
            not isinstance(parity, dict)
            or parity.keys() != {"passed", "bundleSha256"}
            or type(parity["passed"]) is not bool
        ):
            raise GridEvaluationReportError("Parity evidence differs.")
        _sha(parity["bundleSha256"])
        cohorts = report["cohorts"]
        if not isinstance(cohorts, list) or not 1 <= len(cohorts) <= MAX_GAMES:
            raise GridEvaluationReportError("The cohort scope is incomplete.")
        for entry in cohorts:
            if not isinstance(entry, dict) or entry.keys() != {
                "gameId",
                "cohortId",
                "manifestSha256",
            }:
                raise GridEvaluationReportError("Cohort keys differ.")
            _uuid(entry["gameId"])
            _uuid(entry["cohortId"])
            _sha(entry["manifestSha256"])
        game_ids = [entry["gameId"] for entry in cohorts]
        if (
            game_ids != sorted(set(game_ids))
            or len({entry["cohortId"] for entry in cohorts}) != len(cohorts)
            or report["requiredGameIds"] != game_ids
        ):
            raise GridEvaluationReportError("Cohorts must name distinct sorted games.")
        training = [entry for entry in cohorts if entry["gameId"] == report["trainingGameId"]]
        if len(training) != 1 or training[0]["cohortId"] != manifest["cohortId"]:
            raise GridEvaluationReportError("The training cohort is not in the report.")
        games = report["games"]
        if not isinstance(games, list) or len(games) != len(cohorts):
            raise GridEvaluationReportError("Every cohort needs one measured game.")
        for entry, game in zip(cohorts, games, strict=True):
            if (
                not isinstance(game, dict)
                or game.keys() != GAME_KEYS
                or game["gameId"] != entry["gameId"]
                or game["cohortId"] != entry["cohortId"]
                or game["mode"] not in MODES
                or game["targetMetric"] != TARGET_METRIC[game["mode"]]
                or not isinstance(game["roles"], dict)
                or game["roles"].keys() != set(ROLES)
            ):
                raise GridEvaluationReportError("Measured game differs from its cohort.")
            for role in ROLES:
                _require_role(game["roles"][role])
            decision = decide_game(
                mode=game["mode"],
                training=game["gameId"] == report["trainingGameId"],
                parity_passed=parity["passed"],
                roles=game["roles"],
            )
            if any(game[key] != value for key, value in decision.items()):
                raise GridEvaluationReportError("A stored decision differs from the policy.")
        if report["verdict"] != verdict_of(games):
            raise GridEvaluationReportError("The stored verdict differs from the policy.")
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        if isinstance(error, GridEvaluationReportError):
            raise
        raise GridEvaluationReportError("The report does not follow the v2 contract.") from error
    return report


def proof_state(
    cohorts: Sequence[Mapping[str, Any]],
    proofs: Mapping[tuple[str, str], Mapping[str, Any]],
    counts: Mapping[tuple[str, str], int],
    locations: Mapping[str, Mapping[str, Any] | None],
) -> list[dict[str, Any]]:
    """Currentness of each cohort: its latest proof, the notice watermark and storage now.

    A deleted, deleting or otherwise inactive game store is ``unavailable``; a store of a
    different generation than the one proven is ``stale``.
    """
    states = []
    for entry in cohorts:
        key = (entry["gameId"], entry["cohortId"])
        proof = proofs.get(key)
        current = int(counts.get(key, 0))
        location = locations.get(entry["gameId"])
        if proof is None or proof["manifestSha256"] != entry["manifestSha256"]:
            state = "missing"
        elif location is None or location["status"] != "active":
            state = "unavailable"
        elif int(proof["noticeCount"]) != current or int(proof["storageGeneration"]) != int(
            location["generation"]
        ):
            state = "stale"
        else:
            state = "current"
        states.append(
            {
                "gameId": entry["gameId"],
                "cohortId": entry["cohortId"],
                "state": state,
                "noticeCount": current,
                "provenNoticeCount": None if proof is None else int(proof["noticeCount"]),
                "provenAt": None if proof is None else proof.get("createdAt"),
            }
        )
    return states
