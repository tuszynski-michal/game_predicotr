"""Advisory audit inference using the frozen classifier's training RGB contract."""

from __future__ import annotations

import hashlib
import io
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import numpy as np
import torch
from numpy.typing import NDArray

from game_predictor_worker.images.symbol_model_benchmark import SpatialSymbolCnn

from .reference_library import CROP_SIZE, FloatArray, gray_world


def rgb_batch(crops: NDArray[np.uint8]) -> torch.Tensor:
    """Keep RGB, shape and texture; apply only the classifier's /127.5 - 1 scale."""

    if crops.dtype != np.uint8 or crops.ndim != 4 or crops.shape[1:] != (CROP_SIZE, CROP_SIZE, 3):
        raise ValueError("Audit classifier requires a batch of 64 x 64 RGB uint8 crops.")
    values = crops.transpose(0, 3, 1, 2).astype(np.float32) / 127.5 - 1.0
    return torch.from_numpy(values)


class AuditRgbClassifier:
    """Load a frozen existing checkpoint once; never train or activate a model."""

    def __init__(self, path: Path, sha256: str, class_codes: Sequence[str]) -> None:
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != sha256:
            raise ValueError("Audit RGB checkpoint differs from its frozen checksum.")
        payload: Any = torch.load(io.BytesIO(content), map_location="cpu", weights_only=True)
        self.class_codes = tuple(class_codes)
        if (
            not isinstance(payload, Mapping)
            or tuple(payload.get("classCodes", ())) != self.class_codes
            or len(self.class_codes) < 2
            or len(set(self.class_codes)) != len(self.class_codes)
        ):
            raise ValueError("Audit RGB checkpoint catalogue differs from the frozen library.")
        self.network = SpatialSymbolCnn(len(self.class_codes))
        # Legacy checkpoints lack architecture/inputSize fields. Strict state
        # loading validates the actual spatial architecture; rgb_batch pins 64px.
        try:
            self.network.load_state_dict(payload["bestState"], strict=True)
        except (KeyError, RuntimeError, TypeError) as error:
            raise ValueError("Audit RGB checkpoint has an incompatible spatial state.") from error
        self.network.eval()
        torch.set_num_threads(1)

    def candidates(self, crops: NDArray[np.uint8]) -> NDArray[np.int64]:
        batch = rgb_batch(crops)
        if len(batch) == 0:
            return np.empty(0, dtype=np.int64)
        with torch.inference_mode():
            logits = self.network(batch)
        if logits.shape != (len(crops), len(self.class_codes)) or not torch.isfinite(logits).all():
            raise ValueError("Audit RGB classifier returned invalid logits.")
        # Stable class catalogue order resolves equal logits. A maximum is a
        # candidate, not calibrated confidence or a human approval.
        return cast(NDArray[np.int64], logits.argmax(dim=1).numpy().astype(np.int64))

    def reference_features(self, crops: NDArray[np.uint8]) -> FloatArray:
        """Reuse the loaded network with the frozen library's legacy preprocessing."""

        # This separate branch only confirms proposals against the unchanged
        # reference cache. The primary classifier always sees original RGB.
        batch = rgb_batch(np.stack([gray_world(crop) for crop in crops]))
        with torch.inference_mode():
            features = self.network.features(batch)
        return cast(FloatArray, features.flatten(1).numpy().astype(np.float32))


def candidate_is_tentative(candidate: int, strict_reference_class: int | None) -> bool:
    """Only the unchanged reference consensus can additionally confirm RGB."""

    return strict_reference_class != candidate
