"""ONNX export of both stages, PyTorch-ONNX parity (T05 tolerances) and CPU timing."""

from __future__ import annotations

import hashlib
import io
import json
import os
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch

from .neural_grid_data import PhotoSample, read_rgb
from .neural_grid_inference import (
    BUNDLE_FILE,
    NeuralGridEngine,
    file_sha256,
    onnx_engine,
)
from .neural_grid_model import BoardExport, NeuralGridNetwork, ScreenExport
from .neural_grid_protocol import MODEL_VERSION, Preset

OPSET = 18
# T05 (hybrid_protocol): raw output delta 1e-4, source coordinates 0.1 px.
RAW_TOLERANCE = 1e-4
SOURCE_TOLERANCE_PX = 0.1


def export_graphs(network: NeuralGridNetwork, preset: Preset, directory: Path) -> None:
    network = network.cpu().eval()
    canvas_w, canvas_h = preset.screen.train_canvas
    batch = torch.export.Dim("batch", min=1, max=64)
    height = torch.export.Dim("height32", min=2, max=64)
    width = torch.export.Dim("width32", min=2, max=64)
    torch.onnx.export(
        ScreenExport(network.screen).eval(),
        (torch.zeros((1, 3, canvas_h, canvas_w)),),
        str(directory / "screen.onnx"),
        input_names=["pixels"],
        output_names=["heat", "offsets"],
        opset_version=OPSET,
        dynamo=True,
        verbose=False,
        external_data=False,
        dynamic_shapes=({0: batch, 2: 32 * height, 3: 32 * width},),
    )
    board_w, board_h = preset.board.canvas
    torch.onnx.export(
        BoardExport(network.board).eval(),
        (torch.zeros((2, 3, board_h, board_w)),),
        str(directory / "board.onnx"),
        input_names=["crops"],
        output_names=["nodes", "peak", "visibility"],
        opset_version=OPSET,
        dynamo=True,
        verbose=False,
        external_data=False,
        dynamic_shapes=({0: torch.export.Dim("crops", min=1, max=64)},),
    )


def _max_delta(left: np.ndarray, right: np.ndarray) -> float:
    if left.shape != right.shape:
        raise ValueError("NEURAL_GRID_ONNX_PARITY_SHAPE")
    if not np.isfinite(left).all() or not np.isfinite(right).all():
        raise ValueError("NEURAL_GRID_ONNX_PARITY_NONFINITE")
    return float(np.max(np.abs(left - right))) if left.size else 0.0


def parity(
    torch_engine: NeuralGridEngine,
    ort_engine: NeuralGridEngine,
    samples: list[PhotoSample],
    board_width: int,
) -> dict[str, Any]:
    """Raw outputs on identical inputs and final nodes in source pixels."""

    from .neural_grid_data import board_rectifier, crop_board, screen_input

    raw = {"heat": 0.0, "offsets": 0.0, "nodes_normalized": 0.0, "peak": 0.0, "visibility": 0.0}
    source = 0.0
    source_raw = 0.0
    boards = 0
    for sample in samples:
        rgb = read_rgb(sample)
        canvas, _, _ = screen_input(rgb, torch_engine.settings.screen)
        pixels = canvas.transpose(2, 0, 1)[None].astype(np.float32)
        expected = torch_engine.screen_runner(pixels)
        actual = ort_engine.screen_runner(pixels)
        raw["heat"] = max(raw["heat"], _max_delta(expected[0], actual[0]))
        raw["offsets"] = max(raw["offsets"], _max_delta(expected[1], actual[1]))
        left = torch_engine.analyse(rgb)
        right = ort_engine.analyse(rgb)
        if len(left) != len(right):
            raise ValueError("NEURAL_GRID_ONNX_PARITY_BOARD_COUNT")
        crops = [
            crop_board(
                rgb,
                board_rectifier(d.screen_quad, torch_engine.settings.board),
                torch_engine.settings.board,
            ).transpose(2, 0, 1)
            for d in left
        ]
        if crops:
            batch = np.stack(crops).astype(np.float32)
            e_nodes, e_peak, e_visibility = torch_engine.board_runner(batch)
            a_nodes, a_peak, a_visibility = ort_engine.board_runner(batch)
            raw["nodes_normalized"] = max(
                raw["nodes_normalized"], _max_delta(e_nodes / board_width, a_nodes / board_width)
            )
            raw["peak"] = max(raw["peak"], _max_delta(e_peak, a_peak))
            raw["visibility"] = max(raw["visibility"], _max_delta(e_visibility, a_visibility))
        for a, b in zip(left, right, strict=True):
            if (a.nodes is None) != (b.nodes is None):
                raise ValueError("NEURAL_GRID_ONNX_PARITY_FIT")
            if a.raw_nodes is not None and b.raw_nodes is not None:
                source_raw = max(source_raw, _max_delta(a.raw_nodes, b.raw_nodes))
            if a.nodes is not None and b.nodes is not None:
                source = max(source, _max_delta(a.nodes, b.nodes))
                boards += 1
    passed = max(raw.values()) <= RAW_TOLERANCE and source <= SOURCE_TOLERANCE_PX
    return {
        "photos": len(samples),
        "boards": boards,
        "max_abs_raw": raw,
        "max_source_node_px": source,
        "max_source_raw_node_px": source_raw,
        "raw_tolerance": RAW_TOLERANCE,
        "source_tolerance_px": SOURCE_TOLERANCE_PX,
        "passed": passed,
    }


def export_bundle(
    network: NeuralGridNetwork,
    preset: Preset,
    preset_fingerprint: str,
    provenance: dict[str, Any],
    destination: Path,
    parity_samples: list[PhotoSample],
) -> dict[str, Any]:
    """Write screen.onnx, board.onnx, weights.pt and bundle.json; fail on parity."""

    from .neural_grid_training import torch_engine

    if destination.exists():
        raise ValueError("NEURAL_GRID_EXPORT_EXISTS")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".export-", dir=destination.parent))
    network = network.cpu().eval()
    weights = io.BytesIO()
    torch.save(network.state_dict(), weights)
    (staging / "weights.pt").write_bytes(weights.getvalue())
    weights_sha = hashlib.sha256(weights.getvalue()).hexdigest()
    export_graphs(network, preset, staging)
    files = {
        name: file_sha256(staging / name) for name in ("screen.onnx", "board.onnx", "weights.pt")
    }
    bundle = {
        "format": "neural-grid-bundle-v1",
        "model_version": MODEL_VERSION,
        "preset": preset.model_dump(mode="json"),
        "preset_fingerprint": preset_fingerprint,
        "weights_sha256": weights_sha,
        "opset": OPSET,
        "files": files,
        "provenance": provenance,
    }
    (staging / BUNDLE_FILE).write_text(json.dumps(bundle, indent=2, sort_keys=True), "utf-8")
    torch.set_num_threads(max(1, (os.cpu_count() or 2) // 2))
    result = parity(
        torch_engine(network, preset, "cpu"),
        onnx_engine(staging),
        parity_samples,
        preset.board.canvas[0],
    )
    bundle["parity"] = result
    (staging / BUNDLE_FILE).write_text(json.dumps(bundle, indent=2, sort_keys=True), "utf-8")
    if not result["passed"]:
        raise ValueError(f"NEURAL_GRID_ONNX_PARITY_FAILED:{json.dumps(result)}")
    os.replace(staging, destination)
    return bundle


def cpu_timing(bundle: Path, samples: list[PhotoSample], threads: int | None) -> dict[str, Any]:
    engine = onnx_engine(bundle, threads)
    decode, inference, screen = [], [], []
    for index, sample in enumerate(samples):
        started = time.perf_counter()
        rgb = read_rgb(sample)
        decoded = time.perf_counter()
        engine.analyse(rgb)
        finished = time.perf_counter()
        if index == 0:
            continue  # warm-up photo excluded
        decode.append(decoded - started)
        inference.append(finished - decoded)
        screen.append(engine.timings["screen_seconds"])

    def stats(values: list[float]) -> dict[str, float]:
        ordered = sorted(values)
        return {
            "mean": statistics.fmean(values),
            "median": statistics.median(values),
            "p95": ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))],
        }

    return {
        "photos_timed": len(inference),
        "threads": threads,
        "provider": "CPUExecutionProvider",
        "inference_seconds_per_photo": stats(inference),
        "screen_stage_seconds_per_photo": stats(screen),
        "jpeg_decode_seconds_per_photo": stats(decode),
    }
