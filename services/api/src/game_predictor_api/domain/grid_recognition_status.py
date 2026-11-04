"""Safe presentation projections, never an admission or human approval authority."""

from collections.abc import Mapping
from typing import Any


def decision(state: str, *reasons: str) -> dict[str, Any]:
    return {"state": state, "reasonCodes": list(reasons)}


def unavailable_game_recognition_status(reason: str) -> dict[str, Any]:
    return {
        "scope": "current_game",
        "capabilities": None,
        "evaluation": decision("unavailable", reason),
        "automatic": decision("unavailable", reason),
    }


def frozen_recognition_status(pin: object, result: object = None) -> dict[str, Any]:
    """Project the stored operation, without resolving a newer assignment/report."""
    p = pin if isinstance(pin, Mapping) else {}
    r = result if isinstance(result, Mapping) else {}
    evaluation = p.get("qualification", {})
    automatic = p.get("automaticQualification", {})
    rescue = r.get("rescueExecution", {})
    if not isinstance(rescue, Mapping):
        rescue = {}
    reasons = list(r.get("reasonCodes", []))
    if isinstance(r.get("reason"), str):
        reasons.append(r["reason"])
    attempts = rescue.get("attempts", [])
    foreign = "GRID_RESCUE_SLOT_BINDING_REQUIRED" in rescue.get("reasonCodes", [])
    completed = sum(x.get("state") == "completed" for x in attempts if isinstance(x, Mapping))
    consumed = sum(
        x.get("state") == "consumed_without_result" for x in attempts if isinstance(x, Mapping)
    )
    measurements = r.get("calibrationEvidence", {})
    vectors = (
        [item.get("features", {}) for item in measurements.values() if isinstance(item, Mapping)]
        if isinstance(measurements, Mapping)
        else []
    )
    return {
        "scope": "frozen_operation",
        "evaluation": decision(
            str(evaluation.get("state", "unavailable")), *evaluation.get("reasonCodes", [])
        ),
        "automatic": decision(
            str(automatic.get("state", "unavailable")), *automatic.get("reasonCodes", [])
        ),
        "reasonCodes": reasons,
        "completeness": {
            "state": "measured" if vectors else "unavailable",
            "measuredTargets": len(vectors),
            "reasonCodes": sorted(
                {reason for vector in vectors for reason in vector.get("hardReasons", [])}
            ),
        },
        "rescue": {
            "state": "foreign_scope"
            if foreign
            else "completed"
            if completed
            else "consumed_without_result"
            if consumed
            else "unavailable",
            "completedAttempts": 0 if foreign else completed,
            "consumedAttempts": consumed,
            "reasonCodes": list(rescue.get("reasonCodes", [])),
        },
    }
