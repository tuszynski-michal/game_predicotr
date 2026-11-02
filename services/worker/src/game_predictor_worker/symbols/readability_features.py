"""Read-only frozen spatial features for the independent quality experiment."""

from __future__ import annotations

import hashlib
import io
import json
import pickle
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np
import torch
from numpy.typing import NDArray
from PIL import Image

from game_predictor_worker.images.normalization import rgb_pixel_checksum_sha256
from game_predictor_worker.images.symbol_model_benchmark import SpatialSymbolCnn
from game_predictor_worker.images.symbol_onnx import preprocess_rgb_batch

FEATURE_VERSION = "spatial1024-native-quality-v1"
PREPROCESSING = {"inputSize": 64, "resize": "INTER_AREA", "scale": "rgb/127.5-1"}
NATIVE_NAMES = (
    "laplacianVariance",
    "sobelMean",
    "sobelStd",
    "contrastP95P5",
    "entropy",
    "darkFraction16",
    "brightFraction239",
    "directionality",
)
FEATURE_COUNT = 1024 + len(NATIVE_NAMES)
FloatArray = NDArray[np.float64]
RgbArray = NDArray[np.uint8]


class ReadabilityError(ValueError):
    """Fail closed before using incomplete experimental evidence."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def checked_bytes(path: Path, expected_sha: str) -> bytes:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise ReadabilityError("READABILITY_INPUT_MISSING", str(path)) from error
    if hashlib.sha256(content).hexdigest() != expected_sha:
        raise ReadabilityError("READABILITY_INPUT_DRIFT", str(path))
    return content


def managed_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or Path(relative).is_absolute():
        raise ReadabilityError("READABILITY_PATH_INVALID", relative)
    return path


@dataclass(frozen=True)
class FrozenBase:
    checkpoint_sha256: str
    dataset_sha256: str
    split_sha256: str
    class_codes: tuple[str, ...]
    # Complete sample/source/pixel provenance is used by family merging in A2.
    members: tuple[dict[str, Any], ...]

    def binding(self) -> dict[str, object]:
        return {
            "checkpointSha256": self.checkpoint_sha256,
            "datasetSha256": self.dataset_sha256,
            "splitSha256": self.split_sha256,
            "classCodes": list(self.class_codes),
            "preprocessing": PREPROCESSING,
            "architecture": "spatial-symbol-cnn-v1",
        }


def preflight_base(
    checkpoint: Path,
    dataset: Path,
    data_root: Path,
    *,
    checkpoint_sha256: str,
    dataset_sha256: str,
    preprocessing: Mapping[str, object],
) -> tuple[FrozenBase, SpatialSymbolCnn]:
    """Verify every asset and split, then load the exact bestState; never write."""
    try:
        return _preflight_base(
            checkpoint,
            dataset,
            data_root,
            checkpoint_sha256=checkpoint_sha256,
            dataset_sha256=dataset_sha256,
            preprocessing=preprocessing,
        )
    except ReadabilityError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ReadabilityError(
            "READABILITY_DATASET_INVALID", "Malformed frozen dataset manifest."
        ) from error


def _preflight_base(
    checkpoint: Path,
    dataset: Path,
    data_root: Path,
    *,
    checkpoint_sha256: str,
    dataset_sha256: str,
    preprocessing: Mapping[str, object],
) -> tuple[FrozenBase, SpatialSymbolCnn]:
    if dict(preprocessing) != PREPROCESSING:
        raise ReadabilityError("READABILITY_PREPROCESSING_DRIFT", "Frozen preprocessing differs.")
    document = json.loads(checked_bytes(dataset, dataset_sha256))
    if document.get("status") != "ready" or document.get("schemaVersion") != 1:
        raise ReadabilityError("READABILITY_DATASET_INVALID", "Dataset must be ready v1.")
    codes = tuple(row["symbolCode"] for row in document["catalog"])
    if len(codes) < 2 or len(codes) != len(set(codes)):
        raise ReadabilityError("READABILITY_DATASET_INVALID", "Invalid catalogue.")
    rows = document["samples"]
    assignments = document["configuration"]["sourceAssignments"]
    if not rows or len(rows) != document["sampleCount"]:
        raise ReadabilityError("READABILITY_DATASET_INVALID", "Incomplete sample inventory.")
    seen: set[str] = set()
    members: list[dict[str, Any]] = []
    family_splits: dict[str, str] = {}
    pixel_splits: dict[str, str] = {}
    for row in rows:
        split, family = row["split"], row["sourceFamily"]
        sample_id = row["cropSampleId"]
        if (
            split not in ("train", "validation", "test", "regression")
            or assignments.get(family) != split
            or sample_id in seen
            or row["symbolCode"] not in codes
            or not family
            or not row.get("sourceImageChecksumSha256")
            or not row.get("sourceImageId")
        ):
            raise ReadabilityError("READABILITY_DATASET_INVALID", "Invalid membership/provenance.")
        seen.add(sample_id)
        path = managed_path(
            data_root, document["artifactBaseRelativePath"] + "/" + row["assetRelativePath"]
        )
        try:
            content = path.read_bytes()
            with Image.open(io.BytesIO(content)) as image:
                rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
        except OSError as error:
            raise ReadabilityError("READABILITY_INPUT_MISSING", str(path)) from error
        if rgb.shape != (64, 64, 3):
            raise ReadabilityError(
                "READABILITY_PREPROCESSING_DRIFT", "Frozen base assets must be RGB64x64."
            )
        pixel_sha = rgb_pixel_checksum_sha256(rgb)
        kind = row.get("assetChecksumKind", "sha256-bytes")
        checksum = pixel_sha if kind == "rgb-pixel-v1" else hashlib.sha256(content).hexdigest()
        if kind not in ("rgb-pixel-v1", "sha256-bytes") or checksum != row["cropChecksumSha256"]:
            raise ReadabilityError("READABILITY_INPUT_DRIFT", "Dataset asset checksum differs.")
        for key, index in ((family, family_splits), (pixel_sha, pixel_splits)):
            if index.setdefault(key, split) != split:
                raise ReadabilityError(
                    "READABILITY_BASE_LEAKAGE", "Base family/RGB crosses splits."
                )
        members.append(
            {
                "sampleId": sample_id,
                "sourceId": row["sourceImageId"],
                "sourceSha256": row["sourceImageChecksumSha256"],
                "family": family,
                "rgbSha256": pixel_sha,
                "split": split,
            }
        )
    actual = {family: split for family, split in family_splits.items()}
    if (
        actual != assignments
        or len(document["splits"]) != 4
        or {summary["name"] for summary in document["splits"]}
        != {"train", "validation", "test", "regression"}
    ):
        raise ReadabilityError("READABILITY_DATASET_INVALID", "Incomplete family inventory.")
    for summary in document["splits"]:
        split = summary["name"]
        selected = [row for row in rows if row["split"] == split]
        families = {row["sourceFamily"] for row in selected}
        if (
            not selected
            or len(selected) != summary["sampleCount"]
            or families != set(summary["sourceFamilies"])
            or len(families) != summary["sourceFamilyCount"]
        ):
            raise ReadabilityError("READABILITY_DATASET_INVALID", "Split summary differs.")
    content = checked_bytes(checkpoint, checkpoint_sha256)
    try:
        payload: Any = torch.load(io.BytesIO(content), map_location="cpu", weights_only=True)
    except (RuntimeError, ValueError, TypeError, pickle.UnpicklingError, EOFError) as error:
        raise ReadabilityError(
            "READABILITY_CHECKPOINT_INVALID", "Checkpoint cannot be decoded."
        ) from error
    if not isinstance(payload, Mapping) or tuple(payload.get("classCodes", ())) != codes:
        raise ReadabilityError("READABILITY_CHECKPOINT_INVALID", "Checkpoint catalogue differs.")
    model = SpatialSymbolCnn(len(codes))
    try:
        model.load_state_dict(payload["bestState"], strict=True)
    except (KeyError, TypeError, RuntimeError) as error:
        raise ReadabilityError(
            "READABILITY_CHECKPOINT_INVALID", "Invalid spatial state."
        ) from error
    model.eval().requires_grad_(False)
    if not all(torch.isfinite(value).all() for value in model.state_dict().values()):
        raise ReadabilityError("READABILITY_CHECKPOINT_INVALID", "Nonfinite spatial state.")
    base = FrozenBase(
        checkpoint_sha256, dataset_sha256, fingerprint(members), codes, tuple(members)
    )
    return base, model


def require_rgb(rgb: RgbArray) -> None:
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3 or min(rgb.shape[:2]) < 2:
        raise ReadabilityError("READABILITY_RGB_INVALID", "Native RGB uint8 HxWx3 required.")


def native_features(rgb: RgbArray) -> FloatArray:
    """Compute texture on native pixels, before resizing for the frozen network."""
    require_rgb(rgb)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float64)
    dx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    dy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    magnitude = np.hypot(dx, dy)
    probabilities = np.bincount(gray.astype(np.uint8).ravel(), minlength=256) / gray.size
    positive = probabilities[probabilities > 0]
    xx, yy, xy = np.mean(dx * dx), np.mean(dy * dy), np.mean(dx * dy)
    directionality = np.hypot(xx - yy, 2 * xy) / max(float(xx + yy), 1e-12)
    return np.array(
        [
            cv2.Laplacian(gray, cv2.CV_64F).var(),
            magnitude.mean(),
            magnitude.std(),
            np.percentile(gray, 95) - np.percentile(gray, 5),
            -np.sum(positive * np.log2(positive)),
            np.mean(gray <= 16),
            np.mean(gray >= 239),
            directionality,
        ],
        dtype=np.float64,
    )


def extract_features(model: SpatialSymbolCnn, crops: Sequence[RgbArray]) -> FloatArray:
    """Bounded caller batch; independent of classifier logits/confidence and approvals."""
    if not crops:
        return np.empty((0, FEATURE_COUNT), dtype=np.float64)
    if len(crops) > 128:
        raise ReadabilityError(
            "READABILITY_BATCH_LIMIT", "Extract at most 128 native crops per call."
        )
    stats = np.stack([native_features(rgb) for rgb in crops])
    tensor = torch.from_numpy(preprocess_rgb_batch(crops, input_size=64))
    model.cpu().eval().requires_grad_(False)
    with torch.inference_mode():
        spatial = model.features(tensor).flatten(1).numpy().astype(np.float64)
    values = np.concatenate((spatial, stats), axis=1)
    if values.shape != (len(crops), FEATURE_COUNT) or not np.isfinite(values).all():
        raise ReadabilityError("READABILITY_FEATURES_INVALID", "Invalid frozen features.")
    return cast(FloatArray, values)
