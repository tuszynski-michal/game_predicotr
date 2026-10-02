"""Small ONNX export/parity proof with fixture pixels, never operator images."""

import json
import tempfile
from pathlib import Path
from typing import cast

import numpy as np
import torch
from game_predictor_worker.vision_lab.contracts import Topology
from game_predictor_worker.vision_lab.hybrid_data import grid_from_quad, prepare_proposal
from game_predictor_worker.vision_lab.hybrid_inference import HybridGeometryEngine
from game_predictor_worker.vision_lab.hybrid_model import HybridNetwork
from game_predictor_worker.vision_lab.hybrid_onnx import export_and_check

torch.set_num_threads(1)
torch.manual_seed(17)
model = HybridNetwork(None)
with torch.no_grad():
    output_layer = cast(torch.nn.Linear, model.head[-1])
    output_layer.weight.normal_(0, 0.001)
    output_layer.bias.fill_(0.001)
rgb = np.zeros((120, 200, 3), dtype=np.uint8)
quad = np.array([[20, 20], [120, 20], [120, 80], [20, 80]], dtype=np.float32)
p = prepare_proposal("fixture", rgb, grid_from_quad(quad, 200, 120, 0))
with tempfile.TemporaryDirectory(prefix="hybrid-parity-fixture-") as temporary:
    onnx_bytes, weights, parity = export_and_check(
        model, [p, p, p], Path(temporary) / "model.onnx", lambda: None
    )
    engine = HybridGeometryEngine(onnx_bytes)
    assert engine.detect("fixture", rgb, Topology(columns=3)).status == "unsupported"
    assert weights and len(onnx_bytes) > 100
print(
    json.dumps(
        {
            "fixture": "synthetic-only",
            "operator_images": 0,
            "parity": parity,
            "onnx_bytes": len(onnx_bytes),
            "dynamic_batch": True,
        }
    )
)
