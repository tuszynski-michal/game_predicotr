"""Full frozen A, actual runtime inputs and production-cell decisions at export."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import torch
from game_predictor_api.domain.grid_training_cohorts import digest

from ..geometry_core.inference import NeuralGridEngine
from ..training_core.evaluation_precision import EVALUATION_PRECISION, evaluation_precision
from ..training_core.grid_content_consistency import selection_preserved
from ..training_core.grid_training import parity_verdict
from .grid_correction_consistency import discrete_outcome

CONTENT_CONSISTENCY_POLICY = "full-a-content-v1"


class ContentConsistencyError(ValueError):
    def __init__(self, proof: dict[str, Any]) -> None:
        super().__init__(
            "CONTENT_EXPERIMENT_FULL_A_PARITY_FAILED: " + ",".join(proof["reasonCodes"])
        )
        self.proof = proof


def photo_outcome(detail: Mapping[str, Any]) -> dict[str, Any]:
    """Keep every discrete assignment/cell decision; numerical coverage is checked raw."""
    content = detail["contentEvaluation"]
    return {
        "candidate": discrete_outcome(detail["candidate"]),
        "reasonCodes": content["reasonCodes"],
        "fullGeometry": content["fullGeometry"],
        "boards": [
            {
                "positionIndex": board["positionIndex"],
                "referenceSha256": board["referenceSha256"],
                **{
                    key: board["candidate"][key]
                    for key in ("matchAmbiguous", "matchedPrediction", "usable")
                },
                "cells": [
                    {
                        "cellIndex": cell["cellIndex"],
                        "contentState": cell["contentState"],
                        "candidate": None
                        if "candidate" not in cell
                        else {
                            key: cell["candidate"].get(key)
                            for key in (
                                "finalContentState",
                                "inputContentState",
                                "wrongCell",
                                "tie",
                                "foreignFullSymbol",
                                "cropIndex",
                                "reason",
                            )
                        },
                    }
                    for cell in board["cells"]
                ],
            }
            for board in content["boards"]
        ],
    }


def verify_content_export(
    evaluator: Any,
    network: Any,
    directory: Path,
    *,
    roster_sha256: str,
    selected: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]],
    arm_selections: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    import onnxruntime as ort  # type: ignore[import-untyped]

    from ..training_core.neural_grid_network import ContentExport
    from .grid_content_experiment_data import torch_engine

    reference_network = copy.deepcopy(network).to(evaluator.device).eval()
    reference = torch_engine(reference_network, evaluator.recipe, evaluator.device)
    stages = ("screen", "board", *(("content",) if evaluator.arm == "R3" else ()))
    sessions = {
        stage: ort.InferenceSession(
            str(directory / f"{stage}.onnx"), providers=["CPUExecutionProvider"]
        )
        for stage in stages
    }
    inputs: list[dict[str, Any]] = []
    content_graph = ContentExport(reference_network.board).eval() if evaluator.arm == "R3" else None

    def runner(stage: str, pixels: np.ndarray) -> Any:
        expected = getattr(reference, stage + "_runner")(pixels)
        actual = sessions[stage].run(None, {"pixels" if stage == "screen" else "crops": pixels})
        pairs = [
            (f"{stage}.{index}", left, right)
            for index, (left, right) in enumerate(zip(expected, actual, strict=True))
        ]
        if stage == "board" and content_graph is not None:
            with torch.inference_mode(), evaluation_precision():
                auxiliary = content_graph(torch.from_numpy(pixels).to(evaluator.device))
            exported = sessions["content"].run(None, {"crops": pixels})
            pairs.extend(
                (f"content.{index}", left.float().cpu().numpy(), right)
                for index, (left, right) in enumerate(zip(auxiliary, exported, strict=True))
            )
        verdict = parity_verdict(pairs)
        inputs.append(
            {
                "stage": stage,
                "shape": list(pixels.shape),
                "inputSha256": hashlib.sha256(np.ascontiguousarray(pixels).tobytes()).hexdigest(),
                "verdict": verdict,
            }
        )
        return tuple(actual)

    runtime = NeuralGridEngine(
        lambda pixels: runner("screen", pixels),
        lambda pixels: runner("board", pixels),
        reference.settings,
    )
    expected, actual = evaluator.measure(reference), evaluator.measure(runtime)
    reasons = []
    if not inputs or any(not row["verdict"]["passed"] for row in inputs):
        reasons.append("CONTENT_RAW_OUTPUT_DIFFERENCE")
    if expected["photos"] != actual["photos"]:
        reasons.append("CONTENT_MATCHING_OR_CELL_VERDICT_DIFFERENCE")
    competitors = [item["contentSelection"] for item in history] + list(arm_selections)
    if any(
        not selection_preserved(selected, result["selection"], competitors)
        for result in (expected, actual)
    ):
        reasons.append("CONTENT_CHECKPOINT_OR_ARM_PREFERENCE_DIFFERENCE")
    body = {
        "version": CONTENT_CONSISTENCY_POLICY,
        "precision": EVALUATION_PRECISION,
        "selectionRosterSha256": roster_sha256,
        "selectedSha256": selected["sha256"],
        "historySha256": digest(list(history)),
        "history": list(history),
        "armSelectionsSha256": digest(list(arm_selections)),
        "reference": expected,
        "onnx": actual,
        "inputs": inputs,
        "passed": not reasons,
        "reasonCodes": reasons,
    }
    proof = {**body, "sha256": digest(body)}
    if reasons:
        raise ContentConsistencyError(proof)
    return proof
