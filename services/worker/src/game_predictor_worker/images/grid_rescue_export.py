"""Actual-graph and actual-input parity for each evaluated rescue path."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np

from ..geometry_core.inference import NeuralGridEngine, file_sha256
from ..training_core.grid_training import parity_verdict
from ..training_core.grid_training_admission import digest
from .grid_rescue_evaluation import torch_engine


class RescueParity:
    def __init__(self, network: Any, recipe: Any, directory: Path) -> None:
        import onnxruntime as ort  # type: ignore[import-untyped]

        reference = torch_engine(network, recipe, "cpu")
        sessions = {
            stage: ort.InferenceSession(
                str(directory / f"{stage}.onnx"), providers=["CPUExecutionProvider"]
            )
            for stage in ("screen", "board")
        }
        self.records: list[dict[str, Any]] = []
        self.graphs = {}
        self.path = "baseline"
        for stage, session in sessions.items():
            inputs = session.get_inputs()
            expected_name = "pixels" if stage == "screen" else "crops"
            if (
                len(inputs) != 1
                or inputs[0].name != expected_name
                or inputs[0].type != "tensor(float)"
            ):
                raise ValueError("GRID_RESCUE_GRAPH_INPUT_INVALID")
            shape = inputs[0].shape
            if len(shape) != 4 or shape[1] != 3 or (stage == "board" and shape[2:] != [192, 320]):
                raise ValueError("GRID_RESCUE_GRAPH_SHAPE_INVALID")
            self.graphs[stage] = {
                "sha256": file_sha256(directory / f"{stage}.onnx"),
                "inputName": expected_name,
                "dtype": "float32",
                "shape": shape,
            }

        def runner(stage: str, pixels: np.ndarray) -> Any:
            shape = self.graphs[stage]["shape"]
            if (
                pixels.dtype != np.float32
                or not 1 <= pixels.shape[0] <= 64
                or any(
                    type(dim) is int and dim != actual
                    for dim, actual in zip(shape, pixels.shape, strict=True)
                )
                or (
                    stage == "screen"
                    and any(not 64 <= dim <= 2048 or dim % 32 for dim in pixels.shape[2:])
                )
            ):
                raise ValueError("GRID_RESCUE_GRAPH_SHAPE_UNPROVEN")
            expected = (
                reference.screen_runner(pixels)
                if stage == "screen"
                else reference.board_runner(pixels)
            )
            actual = sessions[stage].run(None, {self.graphs[stage]["inputName"]: pixels})
            verdict = parity_verdict(
                [
                    (f"{stage}.{index}", left, right)
                    for index, (left, right) in enumerate(zip(expected, actual, strict=True))
                ]
            )
            if not verdict["passed"]:
                raise ValueError("GRID_RESCUE_ONNX_PARITY_FAILED")
            self.records.append(
                {
                    "path": self.path,
                    "stage": stage,
                    "shape": list(pixels.shape),
                    "inputSha256": hashlib.sha256(
                        np.ascontiguousarray(pixels).tobytes()
                    ).hexdigest(),
                    "verdict": verdict,
                }
            )
            return tuple(actual)

        self.engine = NeuralGridEngine(
            lambda pixels: runner("screen", pixels),
            lambda pixels: runner("board", pixels),
            reference.settings,
        )

    def document(self) -> dict[str, Any]:
        value = {
            "contractVersion": "grid-rescue-parity-v1",
            "graphs": self.graphs,
            "inputs": self.records,
            "screenBounds": {"minimum": 64, "maximum": 2048, "multiple": 32},
            "boardCanvas": [320, 192],
        }
        return {**value, "sha256": digest(value)}
