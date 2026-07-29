"""Checksum-bound production contract for the selected spatial symbol model."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import torch
from numpy.typing import ArrayLike
from torch import Tensor

from .symbol_classifier import PREPROCESSING_VERSION, logical_state_sha256
from .symbol_confidence import calibrated_probabilities
from .symbol_model_benchmark import (
    BENCHMARK_VERSION,
    NO_AUGMENTATION_VERSION,
    SPATIAL_ARCHITECTURE_VERSION,
    SPATIAL_VARIANT,
    SpatialSymbolCnn,
)

SPATIAL_MODEL_VERSION = "production-spatial-symbol-cnn-v1"
SPATIAL_ONNX_MODEL_VERSION = "spatial-symbol-cnn-onnx-v1"
SPATIAL_RELEASE_VERSION = "spatial-symbol-model-release-v1"
MAX_SYMBOL_ALTERNATIVES = 4


class SymbolModelReleaseError(ValueError):
    """Stable selected-model artifact or release-manifest failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class LoadedSpatialModel:
    model: SpatialSymbolCnn
    class_codes: tuple[str, ...]
    input_size: int
    checkpoint_sha256: str
    logical_state_sha256: str
    dataset_sha256: str
    split_sha256: str


@dataclass(frozen=True, slots=True)
class SymbolAlternative:
    symbol_code: str
    confidence: float

    def to_dict(self) -> dict[str, object]:
        return {
            "confidence": round(self.confidence, 8),
            "symbolCode": self.symbol_code,
        }


@dataclass(frozen=True, slots=True)
class SymbolPrediction:
    symbol_code: str
    confidence: float
    alternatives: tuple[SymbolAlternative, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "alternatives": [alternative.to_dict() for alternative in self.alternatives],
            "confidence": round(self.confidence, 8),
            "symbolCode": self.symbol_code,
        }


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_RELEASE_CONTRACT_INVALID",
            f"{label} must be an object.",
        )
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_RELEASE_CONTRACT_INVALID",
            f"{label} must be a non-empty string.",
        )
    return value


def _sha256(value: object, label: str) -> str:
    text = _text(value, label).lower()
    if len(text) != 64:
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_RELEASE_CONTRACT_INVALID",
            f"{label} must be a SHA-256 value.",
        )
    try:
        int(text, 16)
    except ValueError as error:
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_RELEASE_CONTRACT_INVALID",
            f"{label} must be a SHA-256 value.",
        ) from error
    return text


def _codes(value: object, label: str) -> tuple[str, ...]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_RELEASE_CONTRACT_INVALID",
            f"{label} must be an array.",
        )
    codes = tuple(_text(item, label) for item in value)
    if len(codes) < 2 or len(codes) != len(set(codes)):
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_RELEASE_CONTRACT_INVALID",
            f"{label} must define at least two unique classes.",
        )
    return codes


def load_spatial_model_checkpoint(
    path: Path,
    *,
    expected_sha256: str,
    expected_dataset_sha256: str,
    expected_split_sha256: str,
    expected_class_codes: Sequence[str],
) -> LoadedSpatialModel:
    """Load the exact selected checkpoint and reject provenance drift."""

    try:
        content = path.read_bytes()
    except OSError as error:
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_CHECKPOINT_MISSING",
            "The selected spatial checkpoint cannot be read.",
        ) from error
    if hashlib.sha256(content).hexdigest() != _sha256(
        expected_sha256,
        "expectedSha256",
    ):
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_CHECKPOINT_DRIFT",
            "The selected spatial checkpoint checksum differs from the release input.",
        )
    try:
        payload: Any = torch.load(path, map_location="cpu", weights_only=True)
    except (OSError, RuntimeError, ValueError) as error:
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_CHECKPOINT_INVALID",
            "The selected spatial checkpoint cannot be decoded.",
        ) from error
    row = _mapping(payload, "checkpoint")
    if (
        row.get("architectureVersion") != SPATIAL_ARCHITECTURE_VERSION
        or row.get("benchmarkVersion") != BENCHMARK_VERSION
        or row.get("candidateVariant") != SPATIAL_VARIANT
        or row.get("augmentationVersion") != NO_AUGMENTATION_VERSION
    ):
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_CHECKPOINT_VERSION_UNSUPPORTED",
            "The checkpoint is not the selected non-augmented spatial architecture.",
        )
    class_codes = _codes(row.get("classCodes"), "classCodes")
    if class_codes != tuple(expected_class_codes):
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_CHECKPOINT_CLASS_DRIFT",
            "The checkpoint class order differs from the selected dataset.",
        )
    dataset_sha256 = _sha256(row.get("datasetSha256"), "datasetSha256")
    split_sha256 = _sha256(row.get("splitSha256"), "splitSha256")
    if dataset_sha256 != _sha256(
        expected_dataset_sha256, "expectedDatasetSha256"
    ) or split_sha256 != _sha256(expected_split_sha256, "expectedSplitSha256"):
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_CHECKPOINT_PROVENANCE_DRIFT",
            "The checkpoint references a different dataset or source-aware split.",
        )
    config = _mapping(row.get("config"), "config")
    input_size = config.get("inputSize")
    if not isinstance(input_size, int) or isinstance(input_size, bool) or input_size < 16:
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_CHECKPOINT_INVALID",
            "The checkpoint input size is invalid.",
        )
    state = row.get("stateDict")
    if not isinstance(state, Mapping) or not all(
        isinstance(name, str) and isinstance(value, Tensor) for name, value in state.items()
    ):
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_CHECKPOINT_INVALID",
            "The checkpoint state is invalid.",
        )
    model = SpatialSymbolCnn(len(class_codes))
    try:
        model.load_state_dict(dict(state), strict=True)
    except RuntimeError as error:
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_CHECKPOINT_INVALID",
            "The checkpoint state does not match the spatial architecture.",
        ) from error
    model.eval()
    return LoadedSpatialModel(
        model=model,
        class_codes=class_codes,
        input_size=input_size,
        checkpoint_sha256=hashlib.sha256(content).hexdigest(),
        logical_state_sha256=logical_state_sha256(state),
        dataset_sha256=dataset_sha256,
        split_sha256=split_sha256,
    )


def build_symbol_predictions(
    logits: ArrayLike,
    *,
    temperature: float,
    class_codes: Sequence[str],
    alternative_limit: int = MAX_SYMBOL_ALTERNATIVES,
) -> tuple[SymbolPrediction, ...]:
    """Return stable calibrated top-k suggestions with the top-one included."""

    codes = _codes(class_codes, "classCodes")
    if (
        not isinstance(alternative_limit, int)
        or isinstance(alternative_limit, bool)
        or alternative_limit < 1
        or alternative_limit > MAX_SYMBOL_ALTERNATIVES
    ):
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_ALTERNATIVE_LIMIT_INVALID",
            "The alternative limit must be between one and four.",
        )
    probabilities = calibrated_probabilities(logits, temperature)
    if probabilities.shape[1] != len(codes):
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_PREDICTION_CLASS_DRIFT",
            "The logits class count differs from the release class order.",
        )
    predictions: list[SymbolPrediction] = []
    for values in probabilities:
        ranked = sorted(
            range(len(codes)),
            key=lambda index: (-float(values[index]), codes[index]),
        )[:alternative_limit]
        alternatives = tuple(
            SymbolAlternative(codes[index], float(values[index])) for index in ranked
        )
        predictions.append(
            SymbolPrediction(
                symbol_code=alternatives[0].symbol_code,
                confidence=alternatives[0].confidence,
                alternatives=alternatives,
            )
        )
    return tuple(predictions)


def _safe_artifact(root: Path, relative_value: object) -> Path:
    relative = PurePosixPath(_text(relative_value, "relativePath"))
    if relative.is_absolute() or ".." in relative.parts:
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_RELEASE_PATH_UNSAFE",
            "Release artifact paths must remain below the repository root.",
        )
    resolved_root = root.resolve()
    resolved = resolved_root.joinpath(*relative.parts).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_RELEASE_PATH_UNSAFE",
            "A release artifact path escapes the repository root.",
        ) from error
    return resolved


def validate_release_manifest(
    manifest: Mapping[str, object],
    *,
    repository_root: Path,
) -> dict[str, Path]:
    """Validate the one-manifest boundary and every referenced artifact checksum."""

    if (
        manifest.get("releaseVersion") != SPATIAL_RELEASE_VERSION
        or manifest.get("modelVersion") != SPATIAL_MODEL_VERSION
        or manifest.get("architectureVersion") != SPATIAL_ARCHITECTURE_VERSION
        or manifest.get("onnxModelVersion") != SPATIAL_ONNX_MODEL_VERSION
        or manifest.get("preprocessingVersion") != PREPROCESSING_VERSION
    ):
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_RELEASE_VERSION_UNSUPPORTED",
            "The spatial model release versions are unsupported.",
        )
    _codes(manifest.get("classes"), "classes")
    artifacts = _mapping(manifest.get("artifacts"), "artifacts")
    required = {
        "checkpoint",
        "onnx",
        "onnxReport",
        "calibrationReport",
        "verticalSliceReport",
        "decisionReport",
    }
    if set(artifacts) != required:
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_RELEASE_ARTIFACT_SET_INVALID",
            "The release manifest must bind the exact required artifact set.",
        )
    resolved: dict[str, Path] = {}
    for name in sorted(required):
        artifact = _mapping(artifacts[name], f"artifacts.{name}")
        path = _safe_artifact(repository_root, artifact.get("relativePath"))
        expected = _sha256(artifact.get("sha256"), f"artifacts.{name}.sha256")
        try:
            content = path.read_bytes()
        except OSError as error:
            raise SymbolModelReleaseError(
                "SYMBOL_MODEL_RELEASE_ARTIFACT_MISSING",
                f"The release artifact {name} cannot be read.",
            ) from error
        if hashlib.sha256(content).hexdigest() != expected:
            raise SymbolModelReleaseError(
                "SYMBOL_MODEL_RELEASE_ARTIFACT_DRIFT",
                f"The release artifact {name} checksum differs from the manifest.",
            )
        resolved[name] = path
    return resolved


def load_release_manifest(path: Path, *, repository_root: Path) -> Mapping[str, object]:
    try:
        raw: Any = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_RELEASE_MANIFEST_INVALID",
            "The spatial model release manifest cannot be read.",
        ) from error
    manifest = _mapping(raw, "manifest")
    validate_release_manifest(manifest, repository_root=repository_root)
    return manifest


__all__ = [
    "MAX_SYMBOL_ALTERNATIVES",
    "SPATIAL_MODEL_VERSION",
    "SPATIAL_ONNX_MODEL_VERSION",
    "SPATIAL_RELEASE_VERSION",
    "LoadedSpatialModel",
    "SymbolAlternative",
    "SymbolModelReleaseError",
    "SymbolPrediction",
    "build_symbol_predictions",
    "load_release_manifest",
    "load_spatial_model_checkpoint",
    "validate_release_manifest",
]
