"""Pinned classifier confidence is evaluation provenance, never a detector feature."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from game_predictor_api.domain.symbol_readability import BASE_ID, CHECKPOINT_SHA, DATASET_SHA

from game_predictor_worker.images.symbol_confidence import (
    CALIBRATION_VERSION,
    calibrated_probabilities,
)
from game_predictor_worker.images.symbol_onnx import preprocess_rgb_batch
from game_predictor_worker.symbols.readability_features import (
    PREPROCESSING,
    FrozenBase,
    ReadabilityError,
    checked_bytes,
    managed_path,
)

MANIFEST_SHA = "962769e1cd1b239049e755701ebc7ec8858ecb71b032adf9847bc0e1ed7c87fb"
CALIBRATION_SHA = "cc823212e15e597c8e871acb6034e6ecfb78516445bb453c02e3b514ed5bef5f"
ROOT = f"data/models/777a2/{BASE_ID}/candidate"
PROVENANCE = {
    "checkpointSha256": CHECKPOINT_SHA,
    "manifestSha256": MANIFEST_SHA,
    "calibrationSha256": CALIBRATION_SHA,
    "preprocessing": PREPROCESSING,
}


@dataclass(frozen=True)
class PinnedCalibration:
    temperature: float


def load_pinned_calibration(root: Path, base: FrozenBase) -> PinnedCalibration | None:
    """Missing confidence proof gives null, never imported historical confidence."""
    try:
        manifest = json.loads(
            checked_bytes(managed_path(root, f"{ROOT}/manifests/{MANIFEST_SHA}.json"), MANIFEST_SHA)
        )
        calibration = json.loads(
            checked_bytes(
                managed_path(root, f"{ROOT}/calibration/{CALIBRATION_SHA}.json"), CALIBRATION_SHA
            )
        )
    except ReadabilityError as error:
        if error.code == "READABILITY_INPUT_MISSING":
            return None
        raise
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ReadabilityError(
            "READABILITY_CALIBRATION_INVALID", "Malformed confidence proof."
        ) from error
    if not isinstance(manifest, dict) or not isinstance(calibration, dict):
        raise ReadabilityError(
            "READABILITY_CALIBRATION_INVALID", "Confidence proof must be an object."
        )
    artifacts = manifest.get("artifacts")
    if (
        not isinstance(artifacts, dict)
        or not isinstance(artifacts.get("checkpoint"), dict)
        or not isinstance(artifacts.get("calibration"), dict)
    ):
        raise ReadabilityError(
            "READABILITY_CALIBRATION_INVALID", "Confidence artifact bindings missing."
        )
    if (
        manifest.get("datasetManifestSha256") != DATASET_SHA
        or manifest.get("classCodes") != list(base.class_codes)
        or artifacts["checkpoint"].get("sha256") != CHECKPOINT_SHA
        or artifacts["calibration"].get("sha256") != CALIBRATION_SHA
        or calibration.get("version") != CALIBRATION_VERSION
    ):
        raise ReadabilityError(
            "READABILITY_CALIBRATION_INVALID", "Confidence proof belongs to another classifier."
        )
    temperature = calibration.get("temperature")
    if isinstance(temperature, bool) or not isinstance(temperature, int | float):
        raise ReadabilityError("READABILITY_CALIBRATION_INVALID", "Invalid pinned temperature.")
    if not math.isfinite(temperature) or temperature <= 0:
        raise ReadabilityError("READABILITY_CALIBRATION_INVALID", "Invalid pinned temperature.")
    return PinnedCalibration(float(temperature))


def pinned_top1(
    model: Any, crops: list[Any], calibration: PinnedCalibration | None
) -> list[float | None]:
    if calibration is None:
        return [None] * len(crops)
    results: list[float | None] = []
    model.eval()
    with torch.inference_mode():
        for start in range(0, len(crops), 128):
            batch = preprocess_rgb_batch(crops[start : start + 128], input_size=64)
            logits = model(torch.from_numpy(batch)).detach().cpu().numpy().astype(np.float64)
            probabilities = calibrated_probabilities(logits, calibration.temperature)
            results.extend(float(value) for value in probabilities.max(axis=1))
    return results
