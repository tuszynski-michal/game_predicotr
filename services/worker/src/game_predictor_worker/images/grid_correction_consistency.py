"""One frozen-A evaluator and full-runtime export proof for correction training."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import numpy as np
import torch

from ..geometry_core.inference import NeuralGridEngine, file_sha256
from ..training_core.evaluation_precision import EVALUATION_PRECISION
from ..training_core.grid_correction_metrics import (
    aggregate_checkpoint_metrics,
    checkpoint_metrics,
    evaluate_photo,
    photo_selection_key,
    selection_key,
)
from ..training_core.grid_evaluation import predictions
from ..training_core.grid_training import parity_verdict
from ..training_core.grid_training_admission import digest
from .grid_cohort_dataset import has_full_geometry
from .grid_rescue_evaluation import torch_engine

CONSISTENCY_VERSION = "grid-correction-evaluation-consistency-v1"


class CorrectionConsistencyError(ValueError):
    def __init__(self, proof: dict[str, Any]) -> None:
        super().__init__("GRID_TRAINING_EVALUATION_INCONSISTENT")
        self.proof = proof


def proof_binding(proof: Mapping[str, Any]) -> dict[str, Any]:
    """Identity checked when recovering a previously published immutable export."""
    return {
        key: proof[key]
        for key in (
            "contractVersion",
            "precision",
            "graphs",
            "selectedStep",
            "historySha256",
            "baselineIdentity",
        )
    } | {
        "photos": [
            {
                key: row[key]
                for key in (
                    "gameId",
                    "manifestSha256",
                    "sourceId",
                    "rgbSha256",
                    "labelsSha256",
                )
            }
            for row in proof["onnx"]["photos"]
        ]
    }


def discrete_outcome(photo: Mapping[str, Any]) -> dict[str, Any]:
    """Keep assignment and per-target decisions, not just cancelable aggregate counts."""
    return {
        key: photo[key]
        for key in (
            "expected",
            "predicted",
            "matched",
            "correct",
            "full_geometry",
            "false_boards",
            "duplicates",
            "complete_correct_strict",
        )
    } | {
        "matches": [
            {key: match[key] for key in ("prediction", "label", "valid", "correct")}
            for match in photo["matches"]
        ]
    }


def checkpoint_order_preserved(
    selected: Mapping[str, Any], history: Sequence[Mapping[str, Any]], actual: Mapping[str, float]
) -> bool:
    """A small numerical delta is not permission to reverse the recorded preference."""
    key = photo_selection_key if "photoCorrectRate" in actual else selection_key
    step = selected["step"]
    # Discrete selected metrics must survive replay, including old interrupted runs.
    if any(
        actual[name] != value
        for name, value in selected["metrics"].items()
        if name != "normalizedError"
    ):
        return False
    original = key(selected["metrics"], step)
    replay = key(actual, step)
    for item in history:
        if item["step"] == step:
            continue
        other = key(item["selectionMetrics"], item["step"])
        if (original > other) != (replay > other):
            return False
    return True


class CorrectionEvaluator:
    def __init__(
        self, parts: Sequence[Any], recipe: Any, device: str, *, photo_first: bool = False
    ) -> None:
        if not parts or any(part.role != "VALIDATION" for part in parts):
            raise ValueError("GRID_TRAINING_VALIDATION_ONLY")
        self.parts, self.recipe, self.device = list(parts), recipe, device
        self.photo_first = photo_first

    def __call__(self, network: Any) -> dict[str, float]:
        with torch.no_grad():
            return cast(
                dict[str, float],
                self.measure(torch_engine(network, self.recipe, self.device))["metrics"],
            )

    def measure(self, engine: NeuralGridEngine) -> dict[str, Any]:
        games, rows = {}, []
        for part in self.parts:
            evaluated = []
            for index, (source, _) in enumerate(part.rows):
                rgb = part.rgb(index)
                labels = [label for label, _ in part.targets(index)]
                detections = engine.analyse(rgb)
                result = evaluate_photo(
                    str(source["sourceId"]),
                    str(source["sourceId"]),
                    labels,
                    predictions(detections),
                    full_geometry=has_full_geometry(source),
                )
                evaluated.append(result)
                rows.append(
                    {
                        "gameId": str(part.snapshot.manifest["gameId"]),
                        "manifestSha256": part.snapshot.manifest_sha256,
                        "sourceId": str(source["sourceId"]),
                        "rgbSha256": hashlib.sha256(
                            np.ascontiguousarray(rgb).tobytes()
                        ).hexdigest(),
                        "labelsSha256": digest([label.tolist() for label in labels]),
                        "fit": [
                            {
                                "inliers": getattr(item, "fit_inliers", None),
                                "reasons": getattr(item, "reasons", []),
                            }
                            for item in detections
                        ],
                        "evaluation": result.as_dict(),
                    }
                )
            game_id = str(part.snapshot.manifest["gameId"])
            if game_id in games:
                raise ValueError("GRID_TRAINING_DUPLICATE_VALIDATION_GAME")
            games[game_id] = checkpoint_metrics(evaluated, photo_first=self.photo_first)
        return {
            "metrics": aggregate_checkpoint_metrics(
                list(games.values()), photo_first=self.photo_first
            ),
            "games": games,
            "photos": rows,
        }

    def verify_export(
        self,
        network: Any,
        directory: Path,
        selected: Mapping[str, Any],
        history: Sequence[Mapping[str, Any]],
        *,
        baseline: NeuralGridEngine | None = None,
        baseline_identity: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Compare both complete pipelines and raw graphs on every actual ONNX input."""
        import onnxruntime as ort  # type: ignore[import-untyped]

        reference_network = copy.deepcopy(network).to(self.device).eval()
        reference = torch_engine(reference_network, self.recipe, self.device)
        sessions = {
            stage: ort.InferenceSession(
                str(directory / f"{stage}.onnx"), providers=["CPUExecutionProvider"]
            )
            for stage in ("screen", "board")
        }
        records: list[dict[str, Any]] = []

        def runner(stage: str, pixels: np.ndarray) -> Any:
            expected = getattr(reference, f"{stage}_runner")(pixels)
            actual = sessions[stage].run(None, {"pixels" if stage == "screen" else "crops": pixels})
            verdict = parity_verdict(
                [
                    (f"{stage}.{index}", left, right)
                    for index, (left, right) in enumerate(zip(expected, actual, strict=True))
                ]
            )
            records.append(
                {
                    "stage": stage,
                    "shape": list(pixels.shape),
                    "inputSha256": hashlib.sha256(
                        np.ascontiguousarray(pixels).tobytes()
                    ).hexdigest(),
                    "verdict": verdict,
                }
            )
            return tuple(actual)

        runtime = NeuralGridEngine(
            lambda pixels: runner("screen", pixels),
            lambda pixels: runner("board", pixels),
            reference.settings,
        )
        with torch.no_grad():
            expected, actual = self.measure(reference), self.measure(runtime)
        reasons = []
        if any(not record["verdict"]["passed"] for record in records):
            reasons.append("RAW_OUTPUT_DIFFERENCE")
        mismatches = []
        for left, right in zip(expected["photos"], actual["photos"], strict=True):
            if {k: v for k, v in left.items() if k != "evaluation"} != {
                k: v for k, v in right.items() if k != "evaluation"
            } or discrete_outcome(left["evaluation"]) != discrete_outcome(right["evaluation"]):
                mismatches.append(left["sourceId"])
        if mismatches:
            reasons.append("MATCHING_OR_BOARD_VERDICT_DIFFERENCE")
        if not checkpoint_order_preserved(selected, history, actual["metrics"]):
            reasons.append("CHECKPOINT_PREFERENCE_DIFFERENCE")
        baseline_metrics = None
        if baseline is not None:
            from game_predictor_api.domain.grid_correction_evaluation import EPSILON

            baseline_metrics = self.measure(baseline)["games"]
            for game, metrics in baseline_metrics.items():
                limit = metrics["normalizedError"] + EPSILON
                if (expected["games"][game]["normalizedError"] <= limit) != (
                    actual["games"][game]["normalizedError"] <= limit
                ):
                    reasons.append("VALIDATION_NONREGRESSION_VERDICT_DIFFERENCE")
                    break
        body = {
            "contractVersion": CONSISTENCY_VERSION,
            "precision": EVALUATION_PRECISION,
            "referenceDevice": self.device,
            "role": "VALIDATION",
            "passed": not reasons,
            "reasonCodes": reasons,
            "mismatchedSources": mismatches,
            "graphs": {stage: file_sha256(directory / f"{stage}.onnx") for stage in sessions},
            "reference": expected,
            "onnx": actual,
            "inputs": records,
            "selectedStep": selected["step"],
            "historySha256": digest(list(history)),
            "baselineMetrics": baseline_metrics,
            "baselineIdentity": None if baseline_identity is None else dict(baseline_identity),
        }
        proof = {**body, "sha256": digest(body)}
        if reasons:
            raise CorrectionConsistencyError(proof)
        return proof
