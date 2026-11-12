"""Current state of a learning candidate next to its immutable learning verdict (TASK-1189)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def candidate_status(
    *,
    candidate_version_id: str,
    learning_evaluation_id: str | None,
    default_version_id: str | None,
    assigned_version_id: str | None,
    evaluations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """``evaluations`` are completed quality evaluations of the candidate, newest first.

    The learning keeps its pinned verdict; this only reports what happened later.
    """
    latest = next(iter(evaluations), None)
    return {
        "versionId": candidate_version_id,
        "isDefault": default_version_id == candidate_version_id,
        "assignedToGame": assigned_version_id == candidate_version_id,
        "latestEvaluation": None
        if latest is None
        else {
            "evaluationId": str(latest["evaluationId"]),
            "reportId": str(latest["reportId"]),
            "verdict": latest["verdict"],
            "policyVersion": latest["policyVersion"],
            "createdAt": latest["createdAt"],
        },
        "laterEvaluation": latest is not None
        and str(latest["evaluationId"]) != (learning_evaluation_id or ""),
    }
