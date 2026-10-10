"""Closed D-457 protocol; deliberately independent of torch and training imports."""

import hashlib
import os
from pathlib import Path
from typing import Any

from game_predictor_worker.images.screen_layout_v3.engine import SCREEN_LAYOUT_V3_VERSION

from .annotations import digest, read_checked
from .run_contracts import StartRunRequest
from .snapshot import canonical, safe_file

MODEL_VERSION = "hybrid-mobilenet-v1"
PREPROCESSING_VERSION = "baseline-crop-rgb224-v1"
WEIGHTS_FILENAME = "mobilenet_v3_small-047dcff4.pth"
WEIGHTS_SHA256 = "047dcff4addef86ea5bc2eff13c9614dc11f47ab1160d0a71a25e7db994f4e1f"


def protocol() -> dict[str, Any]:
    return {
        "version": "D-457-v1",
        "model": MODEL_VERSION,
        "architecture": "MobileNetV3Small-features-avgpool-Linear576x128-Hardswish-Linear128x8",
        "torchvision": "0.27.1",
        "pretrained_sha256": WEIGHTS_SHA256,
        "backbone": "frozen-eval",
        "determinism": {
            "algorithms": True,
            "cudnn_deterministic": True,
            "cudnn_benchmark": False,
            "cublas_workspace_config": ":4096:8",
        },
        "last_layer": "zeros",
        "presence_head": False,
        "proposals": SCREEN_LAYOUT_V3_VERSION,
        "preprocessing": PREPROCESSING_VERSION,
        "crop_margin_per_side": 0.2,
        "letterbox": 224,
        "letterbox_padding_rgb": [114, 114, 114],
        "mean": [0.485, 0.456, 0.406],
        "std": [0.229, 0.224, 0.225],
        "matching": {"same_board_index": True, "min_quad_iou": 0.25, "unknown": "masked"},
        "optimizer": {"name": "AdamW", "lr": 0.001, "weight_decay": 0.0001},
        "loss": {"name": "SmoothL1", "beta": 0.02, "coordinates": "normalized-corners"},
        "augmentation": {"brightness": 0.1, "contrast": 0.1, "scale": 0.05, "flip": False},
        "selection": "image-macro-mean24nodeNME-diagonal-cap1-missing1-earliest-trained-epoch",
        "reference": "original-baseline-24nodes; zero-delta-homography-reported-separately",
        "gate": "structural-only-uncalibrated-always-review",
        "onnx": {
            "opset": 18,
            "dynamic_batch": True,
            "delta_tolerance": 0.0001,
            "source_corner_tolerance_px": 0.1,
        },
    }


def protocol_digest() -> str:
    return digest(protocol())


def freeze_protocol(cache: Path) -> Path:
    path = safe_file(cache, f"protocols/{protocol_digest()}.json")
    payload = protocol()
    if path.exists():
        if read_checked(path) != payload:
            raise ValueError("RUN_PROTOCOL_MISMATCH")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    # Create-only: a concurrent or partially written registration fails closed, never overwrites.
    with path.open("xb") as stream:
        stream.write(canonical({"payload": payload, "sha256": protocol_digest()}))
        stream.flush()
        os.fsync(stream.fileno())
    return path


def validate_protocol(request: StartRunRequest, weights: Path) -> None:
    if request.model_version != MODEL_VERSION:
        return
    configuration = request.configuration
    registered = safe_file(weights.parent, f"protocols/{protocol_digest()}.json")
    if (
        request.protocol_digest != protocol_digest()
        or request.preprocessing_version != PREPROCESSING_VERSION
        or request.seed != 20260927
        or request.topology.columns != 5
        or configuration.batch_size != 8
        or configuration.learning_rate != 0.001
        or (request.purpose == "smoke" and configuration.epochs != 1)
        or not weights.is_file()
        or hashlib.sha256(weights.read_bytes()).hexdigest() != WEIGHTS_SHA256
        or not registered.is_file()
        or read_checked(registered) != protocol()
    ):
        raise ValueError("RUN_PROTOCOL_MISMATCH")
