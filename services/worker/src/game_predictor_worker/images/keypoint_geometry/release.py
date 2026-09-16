"""Immutable shadow release manifest for the experimental keypoint model."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from game_predictor_api.domain.image_geometry_v2 import canonical_json_bytes

from .dataset import FrozenKeypointGeometryDataset, KeypointSplit
from .model import (
    KEYPOINT_GEOMETRY_MODEL_VERSION,
    KeypointGeometryModelConfiguration,
    KeypointTrainingConfiguration,
    KeypointTrainingResult,
)
from .onnx_adapter import (
    KEYPOINT_ONNX_ADAPTER_VERSION,
    KEYPOINT_ONNX_MAX_PARITY_ERROR,
    KeypointCpuTiming,
    KeypointOnnxArtifact,
    KeypointOnnxParityReport,
)

KEYPOINT_GEOMETRY_RELEASE_VERSION = "keypoint-geometry-shadow-release-v1"


class KeypointGeometryReleaseError(ValueError):
    """Stable rejection before a keypoint artifact can become a shadow release."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class KeypointGeometryReleaseManifest:
    payload: dict[str, object]
    manifest_checksum_sha256: str
    shadow_only: bool = True

    def to_payload(self) -> dict[str, object]:
        return {
            **self.payload,
            "manifestChecksumSha256": self.manifest_checksum_sha256,
        }


def build_keypoint_geometry_release_manifest(
    *,
    dataset: FrozenKeypointGeometryDataset,
    model_configuration: KeypointGeometryModelConfiguration,
    training_configuration: KeypointTrainingConfiguration,
    training_result: KeypointTrainingResult,
    onnx_artifact: KeypointOnnxArtifact,
    parity: KeypointOnnxParityReport,
    cpu_timing: KeypointCpuTiming,
) -> KeypointGeometryReleaseManifest:
    if (
        parity.maximum_absolute_error > KEYPOINT_ONNX_MAX_PARITY_ERROR
        or not parity.heatmap_argmax_equal
        or not parity.presence_mask_equal
    ):
        raise KeypointGeometryReleaseError(
            "KEYPOINT_ONNX_PARITY_FAILED",
            "The keypoint ONNX artifact differs from its PyTorch checkpoint.",
        )
    if training_result.model_version != KEYPOINT_GEOMETRY_MODEL_VERSION:
        raise KeypointGeometryReleaseError(
            "KEYPOINT_MODEL_VERSION_MISMATCH",
            "The trained keypoint model version differs from the release contract.",
        )
    if (
        onnx_artifact.model_version != training_result.model_version
        or onnx_artifact.adapter_version != KEYPOINT_ONNX_ADAPTER_VERSION
        or onnx_artifact.input_size != model_configuration.input_size
        or onnx_artifact.heatmap_size != model_configuration.heatmap_size
    ):
        raise KeypointGeometryReleaseError(
            "KEYPOINT_ONNX_RELEASE_CONTRACT_MISMATCH",
            "The keypoint ONNX artifact differs from the trained model configuration.",
        )
    split_names: tuple[KeypointSplit, ...] = ("train", "validation", "test")
    split_counts = {split: len(dataset.samples_for(split)) for split in split_names}
    if training_result.training_sample_count != split_counts["train"]:
        raise KeypointGeometryReleaseError(
            "KEYPOINT_TRAINING_DATASET_MISMATCH",
            "The keypoint checkpoint was not trained on the frozen train split.",
        )
    payload: dict[str, object] = {
        "activationAllowed": False,
        "adapterVersion": onnx_artifact.adapter_version,
        "cpuTiming": {
            "measurementCount": cpu_timing.measurement_count,
            "medianMilliseconds": round(cpu_timing.median_milliseconds, 6),
            "p95Milliseconds": round(cpu_timing.p95_milliseconds, 6),
            "warmupCount": cpu_timing.warmup_count,
        },
        "datasetManifestChecksumSha256": dataset.manifest_checksum_sha256,
        "gaussianSigma": model_configuration.gaussian_sigma,
        "inputSize": model_configuration.input_size,
        "heatmapSize": model_configuration.heatmap_size,
        "modelVersion": onnx_artifact.model_version,
        "onnxChecksumSha256": onnx_artifact.checksum_sha256,
        "onnxParity": {
            "heatmapArgmaxEqual": parity.heatmap_argmax_equal,
            "maximumAbsoluteError": parity.maximum_absolute_error,
            "presenceMaskEqual": parity.presence_mask_equal,
        },
        "releaseVersion": KEYPOINT_GEOMETRY_RELEASE_VERSION,
        "shadowOnly": True,
        "splitCounts": split_counts,
        "splitSeed": dataset.split_seed,
        "splitVersion": dataset.split_version,
        "training": {
            "batchSize": training_configuration.batch_size,
            "epochs": training_configuration.epochs,
            "finalLoss": training_result.losses[-1],
            "learningRate": training_configuration.learning_rate,
            "sampleCount": training_result.training_sample_count,
            "seed": training_configuration.seed,
        },
    }
    checksum = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return KeypointGeometryReleaseManifest(
        payload=payload,
        manifest_checksum_sha256=checksum,
    )


__all__ = [
    "KEYPOINT_GEOMETRY_RELEASE_VERSION",
    "KeypointGeometryReleaseError",
    "KeypointGeometryReleaseManifest",
    "build_keypoint_geometry_release_manifest",
]
