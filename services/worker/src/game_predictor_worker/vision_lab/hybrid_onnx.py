"""Export and parity run inside the same worker deadline, not an extra experiment."""

import io
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort  # type: ignore[import-untyped]
import torch

from .hybrid_data import Proposal, normalized_batch
from .hybrid_model import HybridNetwork


def parity_errors(
    expected: np.ndarray, actual: np.ndarray, batch: list[Proposal]
) -> tuple[float, float]:
    if expected.shape != actual.shape or expected.shape != (len(batch), 8):
        raise ValueError("HYBRID_ONNX_PARITY_FAILED")
    if not np.isfinite(expected).all() or not np.isfinite(actual).all():
        raise ValueError("HYBRID_ONNX_PARITY_NONFINITE")
    delta = float(np.max(np.abs(expected - actual)))
    corner = 0.0
    for p, left, right in zip(batch, expected, actual, strict=True):
        left_source = p.source(p.normalize(p.quad) + left.reshape(4, 2))
        right_source = p.source(p.normalize(p.quad) + right.reshape(4, 2))
        if not np.isfinite(left_source).all() or not np.isfinite(right_source).all():
            raise ValueError("HYBRID_ONNX_PARITY_NONFINITE")
        corner = max(corner, float(np.max(np.abs(left_source - right_source))))
    return delta, corner


def export_and_check(
    model: HybridNetwork, values: list[Proposal], output: Path, heartbeat: Any
) -> tuple[bytes, bytes, dict[str, float]]:
    heartbeat()
    model = model.cpu().eval()
    sample = torch.zeros((2, 3, 224, 224))
    torch.onnx.export(
        model,
        (sample,),
        str(output),
        input_names=["pixels"],
        output_names=["delta"],
        opset_version=18,
        dynamo=True,
        verbose=False,
        external_data=False,
        dynamic_shapes=({0: torch.export.Dim("batch", min=1)},),
    )
    heartbeat()
    session = ort.InferenceSession(str(output), providers=["CPUExecutionProvider"])
    max_delta, max_corner = 0.0, 0.0
    for start in range(0, len(values), 8):
        heartbeat()
        batch = values[start : start + 8]
        pixels = normalized_batch(batch)
        with torch.no_grad():
            expected = model(torch.from_numpy(pixels)).numpy()
        actual = session.run(["delta"], {"pixels": pixels})[0]
        delta, corner = parity_errors(expected, actual, batch)
        max_delta, max_corner = max(max_delta, delta), max(max_corner, corner)
    if max_delta > 0.0001 or max_corner > 0.1:
        raise ValueError("HYBRID_ONNX_PARITY_FAILED")
    serialized = io.BytesIO()
    torch.save(model.state_dict(), serialized)
    heartbeat()
    return (
        output.read_bytes(),
        serialized.getvalue(),
        {"max_abs_delta": max_delta, "max_source_corner_px": max_corner},
    )
