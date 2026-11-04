"""Strict artifact proof and operation pin for the opt-in rescue contract."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

from game_predictor_worker.geometry_core.rescue import GridRescueVariantV1
from game_predictor_worker.training_core.grid_rescue_training import require_recipe

from .grid_model_registry import descriptor_sha256 as digest

POLICY = "grid-rescue-policy-v1"
_SHA = re.compile(r"[0-9a-f]{64}")
COMPONENTS = {
    "screen_only": ("screen:variant", "board:baseline"),
    "board_only": ("screen:baseline", "board:variant"),
    "combined": ("screen:variant", "board:variant"),
}


def _sha(value: object) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _signed(value: Mapping[str, Any]) -> None:
    if value.get("sha256") != digest({key: item for key, item in value.items() if key != "sha256"}):
        raise ValueError("GRID_RESCUE_PROOF_CHECKSUM_MISMATCH")


def _rank(value: Mapping[str, Any]) -> tuple[float, float, float]:
    if set(value) != {"photoCorrectRate", "boardCorrectRate", "normalizedError"} or any(
        type(item) not in (float, int) or not math.isfinite(item) or not 0 <= item <= 1
        for item in value.values()
    ):
        raise ValueError("GRID_RESCUE_METRICS_INVALID")
    return value["photoCorrectRate"], value["boardCorrectRate"], -value["normalizedError"]


def require_rescue_evidence(bundle: Mapping[str, Any]) -> dict[str, Any]:
    proof = bundle["rescue"]
    if not isinstance(proof, dict) or set(proof) != {
        "contractVersion",
        "recipe",
        "selectionInput",
        "trainingExposure",
        "selection",
        "parity",
        "runId",
        "bestStep",
        "weightsSha256",
        "checkpointSha256",
        "trainingPresetFingerprint",
        "snapshotId",
        "sha256",
    }:
        raise ValueError("GRID_RESCUE_PROOF_INVALID")
    _signed(proof)
    if (
        proof["contractVersion"] != "grid-rescue-evidence-v1"
        or type(proof["bestStep"]) is not int
        or proof["bestStep"] < 1
    ):
        raise ValueError("GRID_RESCUE_PROOF_VERSION_INVALID")
    provenance = bundle["provenance"]
    if any(
        proof[key] != provenance[key]
        for key in (
            "runId",
            "bestStep",
            "weightsSha256",
            "checkpointSha256",
            "trainingPresetFingerprint",
            "snapshotId",
        )
    ):
        raise ValueError("GRID_RESCUE_PROVENANCE_MISMATCH")
    selection_input = proof["selectionInput"]
    _signed(selection_input)
    if (
        selection_input.get("contractVersion"),
        selection_input.get("policy"),
        selection_input.get("role"),
        selection_input.get("purpose"),
        selection_input.get("selectionExposed"),
    ) not in (
        (
            "grid-checkpoint-input-v1",
            "all-validation-v1",
            "VALIDATION",
            "checkpoint-selection",
            True,
        ),
        (
            "grid-checkpoint-input-v2",
            "validation-purpose-a-v1",
            "VALIDATION",
            "checkpoint-selection",
            True,
        ),
    ):
        raise ValueError("GRID_RESCUE_SELECTION_INPUT_INVALID")
    recipe = proof["recipe"]
    variant = require_recipe(recipe, recipe["baselinePresetSha256"], selection_input)
    if variant is not None:
        variant.require_baseline(bundle["preset"]["board"]["margin"])
    exposure = proof["trainingExposure"]
    _signed(exposure)
    if (
        exposure.get("contractVersion") != "stage-composed-train-v1"
        or exposure.get("architecture") != "neural-grid-independent-screen-board-v1"
        or exposure.get("recipeSha256") != recipe["sha256"]
        or not 0 <= exposure["lastStep"] <= proof["bestStep"]
    ):
        raise ValueError("GRID_RESCUE_TRAIN_EXPOSURE_INVALID")
    games = {item["gameId"] for item in selection_input["games"]}
    if not games or len(games) != len(selection_input["games"]):
        raise ValueError("GRID_RESCUE_SCOPE_INVALID")
    for item in selection_input["games"]:
        if len(item["sources"]) < 5 or len({s["sourceId"] for s in item["sources"]}) != len(
            item["sources"]
        ):
            raise ValueError("GRID_RESCUE_SELECTION_SOURCES_INVALID")
    selected = proof["selection"]
    from game_predictor_worker.images.grid_rescue_strategy import completeness_routing

    for path_proof in selected.get("pathProofs", {}).values():
        if selection_input["policy"] == "validation-purpose-a-v1":
            expected_routing = completeness_routing(selection_input, bundle["preset"]["board"])
            if (
                path_proof.get("routing") != expected_routing
                or path_proof.get("routingPolicy") != expected_routing["version"]
            ):
                raise ValueError("GRID_RESCUE_ROUTING_PROOF_REQUIRED")
        elif "routing" in path_proof:
            raise ValueError("GRID_RESCUE_ROUTING_PROOF_REQUIRED")
    if (
        selected.get("contractVersion") != "grid-rescue-selection-v1"
        or selected.get("selectionInputSha256") != selection_input["sha256"]
        or selected.get("tiePolicy") != "baseline-then-lexical-path-v1"
        or set(selected["baseline"]) != games
        or set(selected["pathProofs"]) != set(() if variant is None else variant.paths)
    ):
        raise ValueError("GRID_RESCUE_SELECTION_MISMATCH")
    parity = proof["parity"]
    _signed(parity)
    if (
        parity["contractVersion"] != "grid-rescue-parity-v1"
        or parity["boardCanvas"] != [320, 192]
        or parity["screenBounds"] != {"minimum": 64, "maximum": 2048, "multiple": 32}
    ):
        raise ValueError("GRID_RESCUE_PARITY_INVALID")
    for stage in ("screen", "board"):
        graph = parity["graphs"][stage]
        if graph["sha256"] != bundle["files"][stage + ".onnx"] or graph["dtype"] != "float32":
            raise ValueError("GRID_RESCUE_GRAPH_MISMATCH")
    for record in parity["inputs"]:
        verdict = record["verdict"]
        stage = record["stage"]
        shape = record["shape"]
        path = record["path"]
        expected_outputs = {f"{stage}.{i}" for i in range(2 if stage == "screen" else 3)}
        if (
            stage not in ("screen", "board")
            or path not in {"baseline", *selected["pathProofs"]}
            or len(shape) != 4
            or any(type(dim) is not int for dim in shape)
            or not 1 <= shape[0] <= 64
            or shape[1] != 3
            or (stage == "board" and shape[2:] != [192, 320])
            or (
                stage == "screen"
                and (
                    any(not 64 <= dim <= 2048 or dim % 32 for dim in shape[2:])
                    or max(shape[2:])
                    != (
                        variant.screen.longSide
                        if variant is not None
                        and variant.screen is not None
                        and path in ("screen_only", "combined")
                        else 768
                    )
                )
            )
            or set(verdict.get("maxScaledDelta", {})) != expected_outputs
            or set(verdict.get("maxDelta", {})) != expected_outputs
            or any(
                type(value) not in (float, int) or not math.isfinite(value) or value < 0
                for value in verdict["maxDelta"].values()
            )
            or not _sha(record["inputSha256"])
            or verdict.get("passed") is not True
            or verdict.get("tolerance") != 1e-4
            or verdict.get("toleranceScale") != "max(1,|torch|)"
            or any(
                not math.isfinite(value) or value > 1e-4 or value < 0
                for value in verdict["maxScaledDelta"].values()
            )
        ):
            raise ValueError("GRID_RESCUE_PARITY_UNPROVEN")
    active = selected["selectedPath"]
    _require_selection_choice(selected, exposure, selection_input, proof["bestStep"])
    if active is not None:
        if variant is None or active not in variant.paths:
            raise ValueError("GRID_RESCUE_PATH_UNSUPPORTED")
        item = selected["pathProofs"][active]
        if (
            item.get("admittedOnA") is not True
            or item["reasonCodes"]
            or set(item["games"]) != games
        ):
            raise ValueError("GRID_RESCUE_PATH_NOT_ADMITTED")
        ranks = [
            (_rank(item["games"][game]), _rank(selected["baseline"][game]))
            for game in sorted(games)
        ]
        if not all(new >= old for new, old in ranks) or not any(new > old for new, old in ranks):
            raise ValueError("GRID_RESCUE_A_IMPROVEMENT_REQUIRED")
        for game in games:
            for stage in COMPONENTS[active]:
                seen = exposure["games"].get(game, {}).get(stage, {})
                if (
                    not seen.get("sources")
                    or seen.get("confirmedItems", 0) < 1
                    or not 1 <= seen.get("maxStep", 0) <= proof["bestStep"]
                ):
                    raise ValueError("GRID_RESCUE_TRAIN_EXPOSURE_REQUIRED")
        expected_sources = {
            (g["gameId"], s["sourceId"]) for g in selection_input["games"] for s in g["sources"]
        }
        calls = item["invocations"]
        if (
            len(calls) != len(expected_sources)
            or {(r["gameId"], r["sourceId"]) for r in calls} != expected_sources
        ):
            raise ValueError("GRID_RESCUE_PATH_COVERAGE_INVALID")
        if (
            sum(r["redetect"] for r in calls) != item["redetectCalls"]
            or sum(len(r["cropPositions"]) for r in calls) != item["cropCalls"]
            or item["cropCalls"] < 1
            or any(
                r["redetect"] not in (0, 1)
                or len(set(r["cropPositions"])) != len(r["cropPositions"])
                or any(type(p) is not int or not 0 <= p <= 8 for p in r["cropPositions"])
                for r in calls
            )
            or (active != "board_only" and item["redetectCalls"] < 1)
            or (active == "board_only" and item["redetectCalls"] != 0)
        ):
            raise ValueError("GRID_RESCUE_PATH_CALLS_INVALID")
        stages = {r["stage"] for r in parity["inputs"] if r["path"] == active}
        if not {"board"}.issubset(stages) or (active != "board_only" and "screen" not in stages):
            raise ValueError("GRID_RESCUE_PATH_PARITY_REQUIRED")
    return proof


def _require_selection_choice(
    selected: Mapping[str, Any],
    exposure: Mapping[str, Any],
    selection_input: Mapping[str, Any],
    best_step: int,
) -> None:
    """Recompute the declared A rule, including baseline/lexical tie behavior."""
    games = sorted(selected["baseline"])

    def mean_rank(measured: Mapping[str, Any]) -> tuple[float, float, float]:
        if sorted(measured) != games:
            raise ValueError("GRID_RESCUE_SCOPE_INVALID")
        ranks = [_rank(measured[game]) for game in games]
        return (
            sum(row[0] for row in ranks) / len(ranks),
            sum(row[1] for row in ranks) / len(ranks),
            sum(row[2] for row in ranks) / len(ranks),
        )

    choice = None
    winner = mean_rank(selected["baseline"])
    expected_sources = {
        (g["gameId"], s["sourceId"]) for g in selection_input["games"] for s in g["sources"]
    }
    for path, item in sorted(selected["pathProofs"].items()):
        rank = mean_rank(item["games"])
        exposed = all(
            bool((seen := exposure["games"].get(game, {}).get(stage, {})).get("sources"))
            and seen.get("confirmedItems", 0) > 0
            and 1 <= seen.get("maxStep", 0) <= best_step
            for game in games
            for stage in COMPONENTS[path]
        )
        calls = item["invocations"]
        if (
            len(calls) != len(expected_sources)
            or {(row["gameId"], row["sourceId"]) for row in calls} != expected_sources
            or any(
                type(row["redetect"]) is not int
                or row["redetect"] not in (0, 1)
                or row["cropPositions"] != sorted(set(row["cropPositions"]))
                or any(
                    type(position) is not int or not 0 <= position <= 8
                    for position in row["cropPositions"]
                )
                for row in calls
            )
            or item["redetectCalls"] != sum(row["redetect"] for row in calls)
            or item["cropCalls"] != sum(len(row["cropPositions"]) for row in calls)
            or (path == "board_only" and item["redetectCalls"] != 0)
            or item.get("routingPolicy")
            != (
                "grid-rescue-exact-slots-input-completeness-v2"
                if selection_input.get("policy") == "validation-purpose-a-v1"
                else "grid-rescue-exact-slots-fit-or-pixels-v1"
            )
        ):
            raise ValueError("GRID_RESCUE_PATH_CALLS_INVALID")
        exercised = item["cropCalls"] > 0 and (path == "board_only" or item["redetectCalls"] > 0)
        nonregression = all(
            _rank(item["games"][game]) >= _rank(selected["baseline"][game]) for game in games
        )
        improved = any(
            _rank(item["games"][game]) > _rank(selected["baseline"][game]) for game in games
        )
        reasons = (
            (["GRID_RESCUE_TRAIN_EXPOSURE_REQUIRED"] if not exposed else [])
            + (["GRID_RESCUE_PATH_NOT_EXERCISED"] if not exercised else [])
            + (["GRID_RESCUE_A_NONREGRESSION_REQUIRED"] if not nonregression else [])
            + (["GRID_RESCUE_A_IMPROVEMENT_REQUIRED"] if not improved else [])
        )
        if item["admittedOnA"] is not (not reasons) or item["reasonCodes"] != reasons:
            raise ValueError("GRID_RESCUE_A_VERDICT_MISMATCH")
        if not reasons and rank > winner:
            choice, winner = path, rank
    if selected["selectedPath"] != choice or any(
        abs(left - right) > 1e-12
        for left, right in zip(_rank(selected["metrics"]), winner, strict=True)
    ):
        raise ValueError("GRID_RESCUE_SELECTION_MISMATCH")


def require_rescue_pin(value: object, *, bundle_sha: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "policyVersion",
        "variantId",
        "variant",
        "selectedPath",
        "bundleSha256",
        "proofSha256",
        "publicationEvidenceSha256",
    }:
        raise ValueError("GRID_RESCUE_PIN_INVALID")
    variant = GridRescueVariantV1.model_validate(value["variant"])
    if (
        value["policyVersion"] != POLICY
        or value["variantId"] != variant.sha256
        or value["selectedPath"] not in variant.paths
        or value["bundleSha256"] != bundle_sha
        or any(
            not _sha(value[key])
            for key in ("bundleSha256", "proofSha256", "publicationEvidenceSha256")
        )
    ):
        raise ValueError("GRID_RESCUE_PIN_INVALID")
    return dict(value)
