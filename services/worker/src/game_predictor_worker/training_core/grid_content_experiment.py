"""Closed content experiment plan, A-only ranking and durable arm transitions.

No I/O, GPU, application or database dependencies. Callers atomically persist returned
state and independently verify the source documents behind every SHA pin.
"""

from __future__ import annotations

import copy
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from decimal import Decimal
from typing import Any

from .grid_training_admission import SCREEN_GRID_CORRECTIONS_V1, GridTrainingPreset, digest

EXPERIMENT_VERSION = "full-symbol-content-experiment-v1"
STATE_VERSION = "full-symbol-content-experiment-state-v1"
CONDITIONAL_STATE_VERSION = "full-symbol-content-experiment-state-v2"
R3_ADMISSION_POLICY = "human-labels-conditional-v1"
RANK_VERSION = "production-content-a-rank-v1"
CONTENT_HEAD_VERSION = "local-content-quads-visibility-v1"
ARMS = ("R0", "R1", "R2", "R3")
ARM_SECONDS = (1500, 1500, 2100, 2100)
ARM_STEPS = 1200
EVALUATION_STEPS = 200


def _sha(value: Any) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("CONTENT_EXPERIMENT_SHA_INVALID")
    return value


def _sealed(body: Mapping[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(dict(body))
    return {**value, "sha256": digest(value)}


def _body(value: Mapping[str, Any]) -> dict[str, Any]:
    result = {k: copy.deepcopy(v) for k, v in value.items() if k != "sha256"}
    if value.get("sha256") != digest(result):
        raise ValueError("CONTENT_EXPERIMENT_CHECKSUM_INVALID")
    return result


def _arm(arm: str) -> int:
    if arm not in ARMS:
        raise ValueError("CONTENT_EXPERIMENT_ARM_INVALID")
    return ARMS.index(arm)


def _spec(arm: str) -> dict[str, Any]:
    index = _arm(arm)
    return {
        "arm": arm,
        "plannedSteps": ARM_STEPS,
        "evaluationSteps": EVALUATION_STEPS,
        "reservedSeconds": ARM_SECONDS[index],
        "frozenModules": [] if index == 0 else ["batchnorm_stats"],
        "contentHead": index == 3,
        "multiscale": index >= 2,
    }


def build_plan(
    *,
    base_version_id: str,
    base_manifest_sha256: str,
    base_weights_sha256: str,
    cohorts: Sequence[Mapping[str, Any]],
    train_eligibility_sha256: str,
    selection_roster_sha256: str,
    calibration_roster_sha256: str,
    regression_roster_sha256: str,
    seed: int = 20261108,
    r3_admission_policy: str | None = None,
    crop_policy_version: str | None = None,
    export_evaluation_policy: str | None = None,
) -> dict[str, Any]:
    if (
        not isinstance(base_version_id, str)
        or not base_version_id
        or type(seed) is not int
        or seed != 20261108
        or r3_admission_policy not in (None, R3_ADMISSION_POLICY)
        or crop_policy_version not in (None, "full-cell-v2")
        or export_evaluation_policy not in (None, "full-a-content-v1")
    ):
        raise ValueError("CONTENT_EXPERIMENT_IDENTITY_INVALID")
    pins = [dict(item) for item in cohorts]
    if not 1 <= len(pins) <= 8 or any(
        set(item) != {"gameId", "cohortId", "manifestSha256"}
        or not all(isinstance(item[k], str) and item[k] for k in ("gameId", "cohortId"))
        for item in pins
    ):
        raise ValueError("CONTENT_EXPERIMENT_COHORTS_INVALID")
    if any(len({p[key] for p in pins}) != len(pins) for key in ("gameId", "cohortId")):
        raise ValueError("CONTENT_EXPERIMENT_COHORTS_INVALID")
    for pin in pins:
        _sha(pin["manifestSha256"])
    return _sealed(
        {
            "schemaVersion": EXPERIMENT_VERSION,
            "baseVersionId": base_version_id,
            "baseManifestSha256": _sha(base_manifest_sha256),
            "baseWeightsSha256": _sha(base_weights_sha256),
            "cohorts": sorted(pins, key=lambda item: item["gameId"]),
            "trainEligibilitySha256": _sha(train_eligibility_sha256),
            "selectionRosterSha256": _sha(selection_roster_sha256),
            "calibrationRosterSha256": _sha(calibration_roster_sha256),
            "regressionRosterSha256": _sha(regression_roster_sha256),
            "seed": seed,
            "arms": [_spec(arm) for arm in ARMS],
            "maxSteps": 4800,
            "maxSeconds": 7200,
            **({"r3AdmissionPolicy": r3_admission_policy} if r3_admission_policy else {}),
            **({"cropPolicyVersion": crop_policy_version} if crop_policy_version else {}),
            **(
                {"exportEvaluationPolicy": export_evaluation_policy}
                if export_evaluation_policy
                else {}
            ),
        }
    )


def require_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    try:
        expected = build_plan(
            base_version_id=plan["baseVersionId"],
            base_manifest_sha256=plan["baseManifestSha256"],
            base_weights_sha256=plan["baseWeightsSha256"],
            cohorts=plan["cohorts"],
            train_eligibility_sha256=plan["trainEligibilitySha256"],
            selection_roster_sha256=plan["selectionRosterSha256"],
            calibration_roster_sha256=plan["calibrationRosterSha256"],
            regression_roster_sha256=plan["regressionRosterSha256"],
            seed=plan["seed"],
            r3_admission_policy=plan.get("r3AdmissionPolicy"),
            crop_policy_version=plan.get("cropPolicyVersion"),
            export_evaluation_policy=plan.get("exportEvaluationPolicy"),
        )
        if dict(plan) != expected:
            raise ValueError("CONTENT_EXPERIMENT_PLAN_CHANGED")
        return expected
    except (KeyError, TypeError) as error:
        raise ValueError("CONTENT_EXPERIMENT_PLAN_INVALID") from error


def arm_spec(plan: Mapping[str, Any], arm: str) -> dict[str, Any]:
    return dict(require_plan(plan)["arms"][_arm(arm)])


def arm_preset(arm: str) -> GridTrainingPreset:
    spec = _spec(arm)
    return replace(
        SCREEN_GRID_CORRECTIONS_V1,
        preset_id="content-experiment-" + arm.lower() + "-v1",
        version=1,
        max_steps=ARM_STEPS,
        max_run_seconds=float(spec["reservedSeconds"]),
        frozen_modules=tuple(spec["frozenModules"]),
        early_stopping=replace(
            SCREEN_GRID_CORRECTIONS_V1.early_stopping,
            metric=RANK_VERSION,
            evaluation_interval_seconds=EVALUATION_STEPS
            / SCREEN_GRID_CORRECTIONS_V1.steps_per_second_estimate,
        ),
        approval_basis="TASK-1167/D-592: immutable closed content experiment arm",
    )


def _number(value: Any, maximum: float | None = None) -> float:
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or value < 0
        or (maximum is not None and value > maximum)
    ):
        raise ValueError("CONTENT_SELECTION_NUMBER_INVALID")
    return float(value)


def _count(value: Any, maximum: int | None = None) -> int:
    if type(value) is not int or value < 0 or (maximum is not None and value > maximum):
        raise ValueError("CONTENT_SELECTION_COUNT_INVALID")
    return value


def selection_record(games: Sequence[Mapping[str, Any]], arm: str, step: int) -> dict[str, Any]:
    """Recompute rank and every A gate; a caller-provided pass flag is never trusted."""
    index = _arm(arm)
    if type(step) is not int or not 1 <= step <= ARM_STEPS or step % EVALUATION_STEPS:
        raise ValueError("CONTENT_SELECTION_STEP_INVALID")
    if not games or len({g["gameId"] for g in games}) != len(games):
        raise ValueError("CONTENT_SELECTION_SCOPE_INVALID")
    vectors, gate = [], True
    for game in games:
        if set(game) != {
            "gameId",
            "quality",
            "content",
            "u",
            "delta",
            "measurementSha256",
            "auxiliary",
        }:
            raise ValueError("CONTENT_SELECTION_SCOPE_INVALID")
        u, delta = _number(game["u"], 0.02), _number(game["delta"], 0.002)
        del u
        _sha(game["measurementSha256"])
        quality, content, aux = game["quality"], game["content"], game["auxiliary"]
        if set(aux) != {
            "baselineUsablePhotos",
            "candidateUsablePhotos",
            "newClipped",
            "newBorderline",
            "newDamagedInstances",
        }:
            raise ValueError("CONTENT_SELECTION_AUXILIARY_INVALID")
        before, after = quality["base"], quality["candidate"]
        photos = _count(before["photos"])
        boards = _count(before["boards_expected"])
        visible = _count(content["visible"])
        if not photos or not boards or not visible:
            raise ValueError("CONTENT_SELECTION_DENOMINATOR_INVALID")
        if any(
            before[k] != after[k]
            for k in ("photos", "full_photos", "partial_photos", "boards_expected")
        ):
            raise ValueError("CONTENT_SELECTION_COVERAGE_INVALID")
        if (
            content["photos"] != photos
            or content["slots"] != boards * 15
            or quality["photos"] != photos
        ):
            raise ValueError("CONTENT_SELECTION_COVERAGE_INVALID")
        _sha(content["referenceSha256"])
        if (
            content["state"] not in ("ready", "not_evaluable")
            or _count(content["fullPhotos"], photos) > before["full_photos"]
            or sum(_count(content[k]) for k in ("visible", "unknown", "occluded", "outOfFrame"))
            != content["slots"]
        ):
            raise ValueError("CONTENT_SELECTION_COVERAGE_INVALID")
        for counts, quality_counts in ((content["base"], before), (content["candidate"], after)):
            if (
                sum(_count(counts[k]) for k in ("preserved", "borderline", "clipped", "missing"))
                != visible
            ):
                raise ValueError("CONTENT_SELECTION_COUNTS_INVALID")
            for key in ("wrongCells", "ties", "foreignSymbols"):
                _count(counts[key], visible)
            _count(counts["ambiguousBoards"], boards)
            if (
                _count(counts["usableBoards"], boards) > quality_counts["boards_correct"]
                or counts["usableBoards"] * 15 > counts["preserved"]
            ):
                raise ValueError("CONTENT_SELECTION_COUNTS_INVALID")
        damaged = _count(aux["newDamagedInstances"], visible)
        for field in ("newClipped", "newBorderline"):
            if _count(aux[field], visible) > damaged:
                raise ValueError("CONTENT_SELECTION_UNION_INVALID")
        candidate_photos = _count(aux["candidateUsablePhotos"], photos)
        _count(aux["baselineUsablePhotos"], photos)
        usable = _count(content["candidate"]["usableBoards"], boards)
        if candidate_photos * 9 > usable:
            raise ValueError("CONTENT_SELECTION_USABLE_INVALID")
        nme = _number(after["normalized_error"], 1)
        reasons = content["state"] != "ready" or bool(content["reasonCodes"])
        reasons |= _count(content["unknown"]) * 10 > content["slots"]
        for key in (
            "degradedInstances",
            "newWrongCells",
            "newTies",
            "newForeignSymbols",
            "newMatchAmbiguities",
        ):
            count = _count(content[key])
            reasons |= count > 0
            if key != "newMatchAmbiguities" and count > damaged:
                raise ValueError("CONTENT_SELECTION_UNION_INVALID")
        for key in ("boards_matched", "boards_correct", "board_correct_rate", "detection_recall"):
            reasons |= _number(after[key]) < _number(before[key])
        reasons |= Decimal(str(nme)) > Decimal(
            str(_number(before["normalized_error"], 1))
        ) + Decimal(str(delta))
        if before["full_photos"]:
            for key in ("photo_complete_correct", "photo_complete_correct_rate"):
                reasons |= _number(after[key]) < _number(before[key])
            for key in ("false_boards", "duplicate_predictions"):
                reasons |= _number(after[key]) > _number(before[key])
        reasons |= damaged > 0
        reasons |= content["candidate"]["usableBoards"] < content["base"]["usableBoards"]
        reasons |= candidate_photos < aux["baselineUsablePhotos"]
        gate &= not reasons
        vectors.append((damaged / visible, -candidate_photos / photos, -usable / boards, nme))
    rank = [sum(v[i] for v in vectors) / len(vectors) for i in range(4)] + [
        float(index),
        float(step),
    ]
    return _sealed(
        {
            "schemaVersion": RANK_VERSION,
            "role": "VALIDATION",
            "arm": arm,
            "step": step,
            "rank": rank,
            "gatePassed": gate,
            "games": sorted((dict(g) for g in games), key=lambda g: g["gameId"]),
        }
    )


def require_selection(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = selection_record(value["games"], value["arm"], value["step"])
    if dict(value) != expected:
        raise ValueError("CONTENT_SELECTION_CHANGED")
    return expected


def selection_key(value: Mapping[str, Any]) -> tuple[float, ...]:
    verified = require_selection(value)
    return (0.0 if verified["gatePassed"] else 1.0, *verified["rank"])


def content_rank(games: Sequence[Mapping[str, Any]], arm: str, step: int) -> tuple[float, ...]:
    return tuple(selection_record(games, arm, step)["rank"])


def init_state(plan: Mapping[str, Any], bank_sha256: str) -> dict[str, Any]:
    frozen = require_plan(plan)
    return _sealed(
        {
            "schemaVersion": CONDITIONAL_STATE_VERSION
            if frozen.get("r3AdmissionPolicy") == R3_ADMISSION_POLICY
            else STATE_VERSION,
            **({"r3SkipReason": None} if frozen.get("r3AdmissionPolicy") else {}),
            "planSha256": frozen["sha256"],
            "bankSha256": _sha(bank_sha256),
            "chargedSeconds": 0.0,
            "selectedArm": None,
            "arms": {
                arm: {
                    "status": "pending",
                    "completedSteps": 0,
                    "chargedSeconds": 0.0,
                    "checkpointSha256": None,
                    "selection": None,
                }
                for arm in ARMS
            },
        }
    )


def require_state(plan: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    frozen, body = require_plan(plan), _body(state)
    conditional = frozen.get("r3AdmissionPolicy") == R3_ADMISSION_POLICY
    if (
        set(body)
        != {
            "schemaVersion",
            "planSha256",
            "bankSha256",
            "chargedSeconds",
            "selectedArm",
            "arms",
            *({"r3SkipReason"} if conditional else set()),
        }
        or body["schemaVersion"] != (CONDITIONAL_STATE_VERSION if conditional else STATE_VERSION)
        or body["planSha256"] != frozen["sha256"]
        or set(body["arms"]) != set(ARMS)
    ):
        raise ValueError("CONTENT_EXPERIMENT_STATE_INVALID")
    _sha(body["bankSha256"])
    total, running = 0.0, 0
    for arm, row in body["arms"].items():
        if set(row) != {
            "status",
            "completedSteps",
            "chargedSeconds",
            "checkpointSha256",
            "selection",
        } or row["status"] not in {
            "pending",
            "running",
            "complete",
            *({"skipped_not_ready"} if conditional else set()),
        }:
            raise ValueError("CONTENT_EXPERIMENT_STATE_INVALID")
        steps = _count(row["completedSteps"], ARM_STEPS)
        total += _number(row["chargedSeconds"], ARM_SECONDS[_arm(arm)])
        running += row["status"] == "running"
        if row["checkpointSha256"] is not None:
            _sha(row["checkpointSha256"])
        if row["selection"] is not None:
            selected = require_selection(row["selection"])
            if (
                selected["arm"] != arm
                or selected["step"] > steps
                or [g["gameId"] for g in selected["games"]]
                != [c["gameId"] for c in frozen["cohorts"]]
            ):
                raise ValueError("CONTENT_EXPERIMENT_SELECTION_INVALID")
        if row["status"] in ("pending", "skipped_not_ready") and (
            steps or row["chargedSeconds"] or row["checkpointSha256"] or row["selection"]
        ):
            raise ValueError("CONTENT_EXPERIMENT_STATE_INVALID")
        if row["status"] == "skipped_not_ready" and arm != "R3":
            raise ValueError("CONTENT_EXPERIMENT_STATE_INVALID")
        if row["status"] == "complete" and (
            steps != ARM_STEPS or row["checkpointSha256"] is None or row["selection"] is None
        ):
            raise ValueError("CONTENT_EXPERIMENT_INCOMPLETE_ARM")
    if running > 1 or not math.isclose(
        total, _number(body["chargedSeconds"], 7200), abs_tol=1e-9, rel_tol=0
    ):
        raise ValueError("CONTENT_EXPERIMENT_BUDGET_INVALID")
    if body["selectedArm"] is not None and (
        body["selectedArm"] not in ARMS or body["arms"][body["selectedArm"]]["status"] != "complete"
    ):
        raise ValueError("CONTENT_EXPERIMENT_INCOMPLETE_ARM")
    for index, arm in enumerate(ARMS):
        if body["arms"][arm]["status"] != "pending" and any(
            body["arms"][prior]["status"] != "complete" for prior in ARMS[:index]
        ):
            raise ValueError("CONTENT_EXPERIMENT_ARM_ORDER_INVALID")
    if body["arms"]["R3"]["status"] != "pending" and body["arms"]["R2"]["selection"]["gatePassed"]:
        raise ValueError("CONTENT_EXPERIMENT_R3_NOT_ELIGIBLE")
    if conditional and body["r3SkipReason"] != (
        "CONTENT_EXPERIMENT_R3_LABELS_REQUIRED"
        if body["arms"]["R3"]["status"] == "skipped_not_ready"
        else None
    ):
        raise ValueError("CONTENT_EXPERIMENT_STATE_INVALID")
    if body["selectedArm"] is not None and body["selectedArm"] != _winner(body):
        raise ValueError("CONTENT_EXPERIMENT_WINNER_CHANGED")
    return _sealed(body)


def start_arm(
    plan: Mapping[str, Any],
    state: Mapping[str, Any],
    arm: str,
    *,
    feasible_seconds: float,
    r2_gate_passed: bool | None = None,
    human_labels_ready: bool = False,
) -> dict[str, Any]:
    body = _body(require_state(plan, state))
    index = _arm(arm)
    row = body["arms"][arm]
    estimate = _number(feasible_seconds)
    if (
        estimate <= 0
        or row["status"] not in ("pending", "running")
        or body["selectedArm"] is not None
    ):
        raise ValueError("CONTENT_EXPERIMENT_START_INVALID")
    if any(body["arms"][a]["status"] != "complete" for a in ARMS[:index]) or any(
        body["arms"][a]["status"] == "running" for a in ARMS if a != arm
    ):
        raise ValueError("CONTENT_EXPERIMENT_ARM_ORDER_INVALID")
    remaining = ARM_SECONDS[index] - row["chargedSeconds"]
    if estimate > remaining or 7200 - body["chargedSeconds"] < remaining:
        raise ValueError("CONTENT_EXPERIMENT_RESERVE_REQUIRED")
    if arm == "R3":
        r2 = body["arms"]["R2"]["selection"]
        if (
            r2 is None
            or r2["gatePassed"]
            or r2_gate_passed is not False
            or human_labels_ready is not True
        ):
            raise ValueError("CONTENT_EXPERIMENT_R3_NOT_ELIGIBLE")
    row["status"] = "running"
    return require_state(plan, _sealed(body))


def advance_state(
    plan: Mapping[str, Any],
    state: Mapping[str, Any],
    arm: str,
    *,
    completed_steps: int,
    charged_seconds: float,
    checkpoint_sha256: str | None = None,
    selection: Mapping[str, Any] | None = None,
    complete: bool = False,
) -> dict[str, Any]:
    """Absolute cumulative counters make replay idempotent; decreasing them is invalid."""
    body = _body(require_state(plan, state))
    row = body["arms"][_spec(arm)["arm"]]
    if row["status"] not in ("running", "complete") or body["selectedArm"] is not None:
        raise ValueError("CONTENT_EXPERIMENT_ADVANCE_INVALID")
    _count(completed_steps, ARM_STEPS)
    _number(charged_seconds, ARM_SECONDS[_arm(arm)])
    if completed_steps < row["completedSteps"] or charged_seconds < row["chargedSeconds"]:
        raise ValueError("CONTENT_EXPERIMENT_BUDGET_RESET")
    old = copy.deepcopy(row)
    row.update(completedSteps=completed_steps, chargedSeconds=charged_seconds)
    if checkpoint_sha256 is not None:
        row["checkpointSha256"] = _sha(checkpoint_sha256)
    if selection is not None:
        verified = require_selection(selection)
        if (
            verified["arm"] != arm
            or verified["step"] > completed_steps
            or [g["gameId"] for g in verified["games"]] != [c["gameId"] for c in plan["cohorts"]]
        ):
            raise ValueError("CONTENT_EXPERIMENT_SELECTION_INVALID")
        if row["selection"] is None or selection_key(verified) < selection_key(row["selection"]):
            row["selection"] = verified
    if complete:
        row["status"] = "complete"
    if old["status"] == "complete" and row != old:
        raise ValueError("CONTENT_EXPERIMENT_COMPLETE_IMMUTABLE")
    body["chargedSeconds"] = sum(r["chargedSeconds"] for r in body["arms"].values())
    return require_state(plan, _sealed(body))


def _winner(body: Mapping[str, Any]) -> str:
    if any(r["status"] == "running" for r in body["arms"].values()):
        raise ValueError("CONTENT_EXPERIMENT_ARM_RUNNING")
    if any(body["arms"][arm]["status"] != "complete" for arm in ARMS[:3]):
        raise ValueError("CONTENT_EXPERIMENT_REQUIRED_ARM_INCOMPLETE")
    if not body["arms"]["R2"]["selection"]["gatePassed"] and body["arms"]["R3"]["status"] not in (
        "complete",
        "skipped_not_ready",
    ):
        raise ValueError("CONTENT_EXPERIMENT_REQUIRED_ARM_INCOMPLETE")
    passed = [
        arm
        for arm, row in body["arms"].items()
        if row["status"] == "complete" and row["selection"]["gatePassed"]
    ]
    eligible = [
        (r["selection"]["rank"], arm)
        for arm, r in body["arms"].items()
        if r["status"] == "complete" and (not passed or arm in passed)
    ]
    if not eligible:
        raise ValueError("CONTENT_EXPERIMENT_NO_COMPLETE_ARM")
    return str(min(eligible)[1])


def skip_unready_r3(
    plan: Mapping[str, Any], state: Mapping[str, Any], *, human_labels_ready: bool
) -> dict[str, Any]:
    """New-policy only: missing human labels do not discard completed legal arms."""
    body = _body(require_state(plan, state))
    if (
        plan.get("r3AdmissionPolicy") != R3_ADMISSION_POLICY
        or human_labels_ready is not False
        or body["selectedArm"] is not None
        or body["arms"]["R3"]["status"] != "pending"
        or any(body["arms"][arm]["status"] != "complete" for arm in ARMS[:3])
        or body["arms"]["R2"]["selection"]["gatePassed"]
    ):
        raise ValueError("CONTENT_EXPERIMENT_R3_NOT_ELIGIBLE")
    body["arms"]["R3"]["status"] = "skipped_not_ready"
    body["r3SkipReason"] = "CONTENT_EXPERIMENT_R3_LABELS_REQUIRED"
    return require_state(plan, _sealed(body))


def select_winner(plan: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    body = _body(require_state(plan, state))
    body["selectedArm"] = _winner(body)
    return require_state(plan, _sealed(body))


def charge_selected_export(
    plan: Mapping[str, Any], state: Mapping[str, Any], *, charged_seconds: float
) -> dict[str, Any]:
    """Charge final export/parity to the chosen arm without changing its result."""
    body = _body(require_state(plan, state))
    arm = body["selectedArm"]
    if arm is None:
        raise ValueError("CONTENT_EXPERIMENT_WINNER_REQUIRED")
    row = body["arms"][arm]
    _number(charged_seconds, ARM_SECONDS[_arm(arm)])
    if charged_seconds < row["chargedSeconds"]:
        raise ValueError("CONTENT_EXPERIMENT_BUDGET_RESET")
    row["chargedSeconds"] = charged_seconds
    body["chargedSeconds"] = sum(r["chargedSeconds"] for r in body["arms"].values())
    return require_state(plan, _sealed(body))
