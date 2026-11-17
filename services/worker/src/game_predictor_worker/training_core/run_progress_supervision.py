"""An explicit, single-run operator grant; preserve consumed work and input pins."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from typing import Any

from .grid_training_admission import PRESETS, TRAIN_LIMIT_POLICY, RunBudget, digest
from .run_activity import PROGRESS_LIMIT_POLICY, PROGRESS_STALL_SECONDS

FORMAT = "grid-run-progress-supervision-grant-v1"
EVENT = "operator_progress_supervision"


def prepare_supervision(
    row: Mapping[str, Any], pointer: Mapping[str, Any], *, at: str, reason: str
) -> dict[str, Any]:
    if row["status"] not in {"failed", "cancelled"} or row["job_type"] != "grid_training":
        raise ValueError("RUN_NOT_STOPPED")
    if any(row.get(key) is not None for key in ("lease_owner", "lease_token", "lease_expires_at")):
        raise ValueError("RUN_LEASE_ACTIVE")
    if not datetime.fromisoformat(at).tzinfo or not reason.strip() or len(reason) > 240:
        raise ValueError("APPROVAL_INVALID")
    inputs = row["input_payload"]
    preset = PRESETS["grid-corrections-v1"]
    if (
        inputs.get("training_kind") != "grid-training-run-v1"
        or inputs.get("preset_id") != preset.preset_id
        or inputs.get("preset_fingerprint") != preset.fingerprint
        or inputs.get("mode") != "grid-only"
        or any(
            inputs.get(key) is not None
            for key in (
                "content_experiment",
                "shared_cohorts",
                "rescue_recipe",
                "grid_output_contract",
            )
        )
    ):
        raise ValueError("RUN_POLICY_UNSUPPORTED")
    before = row["checkpoint_payload"]
    if before.get("format") != "grid-training-state-v1" or before.get("chargedAt") is not None:
        raise ValueError("RUN_CHARGE_UNSETTLED")
    if before.get("export") is not None or before.get("registered") is not None:
        raise ValueError("RUN_ALREADY_EXPORTED")
    budget = RunBudget.from_payload(before["budget"])
    if (
        budget.limit_policy != TRAIN_LIMIT_POLICY
        or budget.purpose != "train"
        or budget.preset_id != preset.preset_id
        or budget.preset_fingerprint != preset.fingerprint
        or budget.max_steps != 8000
        or budget.max_seconds != 7200
    ):
        raise ValueError("RUN_BUDGET_UNSUPPORTED")
    pointer = dict(pointer)
    sha = pointer.get("sha256")
    if (
        set(pointer) != {"path", "sha256", "step"}
        or not isinstance(sha, str)
        or len(sha) != 64
        or any(c not in "0123456789abcdef" for c in sha)
        or pointer.get("path") != sha + ".pt"
        or type(pointer.get("step")) is not int
        or not 0 < pointer["step"] < inputs["planned_steps"]
        or pointer["step"] > budget.reserved_steps
    ):
        raise ValueError("CHECKPOINT_INVALID")
    existing = before.get("checkpoint")
    if existing and (
        existing["step"] > pointer["step"]
        or existing["step"] == pointer["step"]
        and existing != pointer
    ):
        raise ValueError("CHECKPOINT_REGRESSION")
    payload = {
        "format": FORMAT,
        "runId": str(row["id"]),
        "gameId": str(row["game_id"]),
        "inputSha256": digest(inputs),
        "beforeSha256": digest(before),
        "status": row["status"],
        "at": at,
        "reason": reason,
        "checkpoint": pointer,
        "oldMaxSeconds": budget.max_seconds,
        "maxSeconds": None,
        "stallSeconds": PROGRESS_STALL_SECONDS,
    }
    event = {**payload, "status": EVENT, "grantSha256": digest(payload)}
    after = deepcopy(before)
    after["budget"] = replace(
        budget, max_seconds=None, limit_policy=PROGRESS_LIMIT_POLICY
    ).to_payload()
    after["checkpoint"] = pointer
    after["history"] = [*before.get("history", []), event]
    payload["afterState"] = after
    return {"payload": payload, "sha256": digest(payload)}


def verify_supervision(
    row: Mapping[str, Any], preview: Mapping[str, Any], expected_sha: str
) -> bool:
    payload = preview["payload"]
    if preview["sha256"] != expected_sha or digest(payload) != expected_sha:
        raise ValueError("PREVIEW_CHECKSUM_MISMATCH")
    if (
        payload["format"] != FORMAT
        or str(row["id"]) != payload["runId"]
        or str(row["game_id"]) != payload["gameId"]
        or digest(row["input_payload"]) != payload["inputSha256"]
    ):
        raise ValueError("RUN_INPUT_DRIFT")
    base = {key: value for key, value in payload.items() if key != "afterState"}
    event = {**base, "status": EVENT, "grantSha256": digest(base)}
    if payload["afterState"]["history"][-1] != event:
        raise ValueError("PREVIEW_CHANGE_INVALID")
    current = row["checkpoint_payload"]
    if event in current.get("history", []):
        budget = RunBudget.from_payload(current["budget"])
        prior = RunBudget.from_payload(payload["afterState"]["budget"])
        if (
            budget.max_seconds is not None
            or budget.limit_policy != PROGRESS_LIMIT_POLICY
            or budget.max_steps != prior.max_steps
            or budget.used_seconds < prior.used_seconds
            or budget.reserved_steps < prior.reserved_steps
            or budget.attempts < prior.attempts
        ):
            raise ValueError("APPLIED_GRANT_DRIFT")
        return False
    if digest(current) != payload["beforeSha256"]:
        raise ValueError("RUN_STATE_DRIFT")
    if prepare_supervision(
        row, payload["checkpoint"], at=payload["at"], reason=payload["reason"]
    ) != dict(preview):
        raise ValueError("PREVIEW_CHANGE_INVALID")
    return True
