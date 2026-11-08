"""Closed content-experiment export proof; proposal validity is not publication PASS."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

from game_predictor_worker.geometry_core.rescue import GridRescueVariantV2
from game_predictor_worker.images.grid_rescue_strategy import require_completeness_routing
from game_predictor_worker.training_core.grid_content_experiment import (
    require_plan,
    require_state,
    select_winner,
)
from game_predictor_worker.training_core.grid_rescue_training import ContentTrainingExposure

from .grid_content_experiment_inputs import checked, require_inputs

POLICY = "grid-content-rescue-policy-v1"


def _sha(value: object) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("CONTENT_EXPERIMENT_PROOF_SHA_INVALID")


def _number(value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError("CONTENT_EXPERIMENT_PROOF_NUMBER_INVALID")
    return float(value)


def require_bank(
    bank: Mapping[str, Any], plan: Mapping[str, Any], inputs: Mapping[str, Any]
) -> None:
    checked(
        bank,
        {"schemaVersion", "planSha256", "baseWeightsSha256", "trainEligibilitySha256", "games"},
    )
    if (
        bank["schemaVersion"] != "content-base-error-bank-v1"
        or bank["planSha256"] != plan["sha256"]
        or bank["baseWeightsSha256"] != plan["baseWeightsSha256"]
        or bank["trainEligibilitySha256"] != inputs["trainEligibility"]["sha256"]
        or [g["gameId"] for g in bank["games"]]
        != [g["gameId"] for g in inputs["trainEligibility"]["games"]]
    ):
        raise ValueError("CONTENT_EXPERIMENT_BANK_INVALID")
    for game, eligible in zip(bank["games"], inputs["trainEligibility"]["games"], strict=True):
        if (
            set(game) != {"gameId", "eligibilitySha256", "sources", "reasonCodes"}
            or game["eligibilitySha256"] != eligible["sha256"]
            or [s["source"] for s in game["sources"]] != eligible["sources"]
        ):
            raise ValueError("CONTENT_EXPERIMENT_BANK_SCOPE_INVALID")
        reasons = (
            ["CONTENT_BANK_NO_ELIGIBLE_SOURCES"]
            if not game["sources"]
            else ["CONTENT_BANK_NO_GEOMETRY_ERRORS"]
            if all(
                row["metrics"].get("full_geometry") is True
                and row["metrics"].get("complete_correct_strict") is True
                for row in game["sources"]
            )
            else []
        )
        if game["reasonCodes"] != reasons:
            raise ValueError("CONTENT_EXPERIMENT_BANK_REASONS_CHANGED")
        for source in game["sources"]:
            if set(source) != {"source", "metrics", "detections"} or not isinstance(
                source["metrics"], dict
            ):
                raise ValueError("CONTENT_EXPERIMENT_BANK_INVALID")
            for metric in source["metrics"].values():
                if isinstance(metric, int | float) and not isinstance(metric, bool):
                    _number(metric)
            for detection in source["detections"]:
                if set(detection) != {"screenQuad", "nodes"}:
                    raise ValueError("CONTENT_EXPERIMENT_BANK_INVALID")
                for name, count in (("screenQuad", 4), ("nodes", 24)):
                    points = detection[name]
                    if name == "nodes" and points is None:
                        continue
                    if len(points) != count or any(
                        len(p) != 2
                        or any(type(n) not in (int, float) or not math.isfinite(n) for n in p)
                        for p in points
                    ):
                        raise ValueError("CONTENT_EXPERIMENT_BANK_INVALID")


def require_content_experiment_evidence(bundle: Mapping[str, Any]) -> dict[str, Any]:
    provenance = bundle["provenance"]
    proof = provenance["contentExperiment"]
    if not isinstance(proof, dict) or set(proof) != {
        "plan",
        "inputs",
        "state",
        "bank",
        "selectedArm",
        "bestStep",
        "exposure",
        "preflight",
        "contentHeadExposure",
    }:
        raise ValueError("CONTENT_EXPERIMENT_PROOF_INVALID")
    plan = require_plan(proof["plan"])
    require_inputs(proof["inputs"], plan)
    state = require_state(plan, proof["state"])
    selected = proof["selectedArm"]
    if (
        selected != state["selectedArm"]
        or select_winner(plan, state)["selectedArm"] != selected
        or selected is None
    ):
        raise ValueError("CONTENT_EXPERIMENT_WINNER_CHANGED")
    selection = state["arms"][selected]["selection"]
    if (
        proof["bestStep"] != selection["step"]
        or proof["bestStep"] != provenance["bestStep"]
        or selection != provenance["checkpointSelection"]
        or state["arms"][selected]["checkpointSha256"] != provenance["checkpointSha256"]
        or state["bankSha256"] != proof["bank"]["sha256"]
    ):
        raise ValueError("CONTENT_EXPERIMENT_PROVENANCE_CHANGED")
    require_bank(proof["bank"], plan, proof["inputs"])
    exposure = ContentTrainingExposure(plan, selected)
    exposure.restore(proof["exposure"], proof["bestStep"])
    head = proof["contentHeadExposure"]
    if selected == "R3":
        if (
            not isinstance(head, dict)
            or set(head) != {"quadTargets", "localVisibilityTargets", "optimizerSteps"}
            or any(type(n) is not int or n < 1 for n in head.values())
            or head["optimizerSteps"] > proof["bestStep"]
        ):
            raise ValueError("CONTENT_EXPERIMENT_HEAD_EXPOSURE_REQUIRED")
    elif head is not None:
        raise ValueError("CONTENT_EXPERIMENT_HEAD_EXPOSURE_INVALID")
    required_stages = {"screen:baseline", "board:baseline"}
    if selected in ("R2", "R3"):
        required_stages |= {"screen:variant", "board:variant"}
    if any(
        not required_stages.issubset(proof["exposure"]["games"].get(pin["gameId"], {}))
        for pin in proof["inputs"]["trainEligibility"]["games"]
        if pin["trainingSourceIds"]
    ):
        raise ValueError("CONTENT_EXPERIMENT_EXPOSURE_REQUIRED")
    completed = {arm for arm, row in state["arms"].items() if row["status"] == "complete"}
    if set(proof["preflight"]) != completed:
        raise ValueError("CONTENT_EXPERIMENT_PREFLIGHT_REQUIRED")
    for arm, timing in proof["preflight"].items():
        if set(timing) != {
            "stepSeconds",
            "validationSeconds",
            "exportSeconds",
            "estimatedSeconds",
            "device",
        }:
            raise ValueError("CONTENT_EXPERIMENT_PREFLIGHT_INVALID")
        step, validation, export, estimate = (
            _number(timing[k])
            for k in ("stepSeconds", "validationSeconds", "exportSeconds", "estimatedSeconds")
        )
        reserve = next(row["reservedSeconds"] for row in plan["arms"] if row["arm"] == arm)
        if (
            timing["device"] not in ("cpu", "cuda")
            or min(step, validation, export) <= 0
            or not math.isclose(estimate, step * 1200 + validation * 6 + export, rel_tol=1e-12)
            or estimate > reserve
        ):
            raise ValueError("CONTENT_EXPERIMENT_PREFLIGHT_INVALID")
    _require_rescue(bundle, proof)
    return dict(proof)


def _require_rescue(bundle: Mapping[str, Any], proof: Mapping[str, Any]) -> None:
    rescue = bundle["contentRescue"]
    checked(
        rescue,
        {
            "schemaVersion",
            "planSha256",
            "selectedArm",
            "bestStep",
            "variant",
            "selectedPath",
            "routing",
            "parity",
        },
    )
    plan, arm = proof["plan"], proof["selectedArm"]
    variant = arm in ("R2", "R3")
    if (
        rescue["schemaVersion"] != "content-rescue-evidence-v1"
        or rescue["planSha256"] != plan["sha256"]
        or rescue["selectedArm"] != arm
        or rescue["bestStep"] != proof["bestStep"]
        or rescue["variant"] != (GridRescueVariantV2().model_dump(mode="json") if variant else None)
        or rescue["selectedPath"] != ("combined" if variant else None)
    ):
        raise ValueError("CONTENT_EXPERIMENT_RESCUE_CHANGED")
    if variant:
        routing = require_completeness_routing(rescue["routing"])
        if routing["selectionInputSha256"] != plan["selectionRosterSha256"]:
            raise ValueError("CONTENT_EXPERIMENT_ROUTING_CHANGED")
    elif rescue["routing"] is not None:
        raise ValueError("CONTENT_EXPERIMENT_ROUTING_CHANGED")
    parity = rescue["parity"]
    checked(parity, {"schemaVersion", "cases", "graphs"})
    expected = [(768, [320, 192], 0.15)] + ([(1280, [480, 288], 0.30)] if variant else [])
    if (
        parity["schemaVersion"] != "content-runtime-parity-v1"
        or [(r["screenLongSide"], r["boardCanvas"], r["boardMargin"]) for r in parity["cases"]]
        != expected
        or set(parity["graphs"])
        != {"screen.onnx", "board.onnx", *(("content.onnx",) if arm == "R3" else ())}
    ):
        raise ValueError("CONTENT_EXPERIMENT_PARITY_INVALID")
    for sha in parity["graphs"].values():
        _sha(sha)
    for case in parity["cases"]:
        if set(case) != {
            "screenLongSide",
            "boardCanvas",
            "boardMargin",
            "inputSha256s",
            "result",
        } or set(case["inputSha256s"]) != {"screen", "board"}:
            raise ValueError("CONTENT_EXPERIMENT_PARITY_INVALID")
        for sha in case["inputSha256s"].values():
            _sha(sha)
        result = case["result"]
        if set(result) != {
            "tolerance",
            "toleranceScale",
            "maxDelta",
            "maxScaledDelta",
            "passed",
        } or (
            result["passed"] is not True
            or result["tolerance"] != 1e-4
            or result["toleranceScale"] != "max(1,|torch|)"
            or not result["maxDelta"]
            or result["maxDelta"].keys() != result["maxScaledDelta"].keys()
        ):
            raise ValueError("CONTENT_EXPERIMENT_PARITY_INVALID")
        if set(result["maxDelta"]) != {
            "screen.heat",
            "screen.offsets",
            "board.nodes",
            "board.peak",
            "board.visibility",
            *(("content.content_quads", "content.local_visibility") if arm == "R3" else ()),
        }:
            raise ValueError("CONTENT_EXPERIMENT_PARITY_INVALID")
        if any(_number(v) > 1e-4 for v in result["maxScaledDelta"].values()):
            raise ValueError("CONTENT_EXPERIMENT_PARITY_INVALID")
        for value in result["maxDelta"].values():
            _number(value)


def require_content_rescue_pin(value: Mapping[str, Any], *, bundle_sha: str) -> dict[str, Any]:
    if set(value) != {
        "policyVersion",
        "variantId",
        "variant",
        "selectedPath",
        "bundleSha256",
        "proofSha256",
        "publicationEvidenceSha256",
    }:
        raise ValueError("CONTENT_RESCUE_PIN_INVALID")
    variant = GridRescueVariantV2.model_validate(value["variant"])
    if (
        value["policyVersion"] != POLICY
        or value["variantId"] != variant.sha256
        or value["selectedPath"] != "combined"
        or value["bundleSha256"] != bundle_sha
    ):
        raise ValueError("CONTENT_RESCUE_PIN_INVALID")
    for key in ("bundleSha256", "proofSha256", "publicationEvidenceSha256"):
        _sha(value[key])
    return dict(value)
