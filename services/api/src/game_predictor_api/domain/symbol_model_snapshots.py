"""Pinned, checksum-bound symbol model descriptor stored in image import jobs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

BOOTSTRAP_SYMBOL_MODEL_VERSION = "bootstrap-symbol-cnn-onnx-v1"
BOOTSTRAP_SYMBOL_MODEL_SHA256 = "e03f66f2ab092b6049920fee6fb2839900a95eb94af42fbd5ef7e35c473b5fb8"
BOOTSTRAP_SYMBOL_MODEL_PATH = "artifacts/m6-symbol-classifier-onnx/bootstrap-symbol-cnn-v1.onnx"
BOOTSTRAP_SYMBOL_CLASS_CODES = (
    "cherries",
    "grapes",
    "lemon",
    "orange",
    "plum",
    "seven",
    "star",
    "watermelon",
)
BOOTSTRAP_SYMBOL_INPUT_SIZE = 64
BOOTSTRAP_SYMBOL_TEMPERATURE = 1.0338382913


class SymbolModelStorageRoot(StrEnum):
    REPOSITORY = "repository"
    ARTIFACT = "artifact"


@dataclass(frozen=True, slots=True)
class SymbolModelJobSnapshot:
    iteration_id: UUID | None
    model_version: str
    manifest_checksum_sha256: str
    onnx_checksum_sha256: str
    onnx_relative_path: str
    storage_root: SymbolModelStorageRoot
    class_codes: tuple[str, ...]
    input_size: int
    temperature: float

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "classCodes": list(self.class_codes),
            "inferenceFingerprint": self.inference_fingerprint,
            "inputSize": self.input_size,
            "manifestChecksumSha256": self.manifest_checksum_sha256,
            "modelVersion": self.model_version,
            "onnxChecksumSha256": self.onnx_checksum_sha256,
            "onnxRelativePath": self.onnx_relative_path,
            "storageRoot": self.storage_root.value,
            "temperature": self.temperature,
        }
        if self.iteration_id is not None:
            payload["iterationId"] = str(self.iteration_id)
        return payload

    @property
    def inference_fingerprint(self) -> str:
        payload = {
            "classCodes": list(self.class_codes),
            "inputSize": self.input_size,
            "manifestChecksumSha256": self.manifest_checksum_sha256,
            "modelVersion": self.model_version,
            "onnxChecksumSha256": self.onnx_checksum_sha256,
            "onnxRelativePath": self.onnx_relative_path,
            "storageRoot": self.storage_root.value,
            "temperature": self.temperature,
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()


def bootstrap_symbol_model_snapshot() -> SymbolModelJobSnapshot:
    manifest_checksum = hashlib.sha256(
        b"game-predictor-bootstrap-symbol-model-job-snapshot-v1"
    ).hexdigest()
    return SymbolModelJobSnapshot(
        iteration_id=None,
        model_version=BOOTSTRAP_SYMBOL_MODEL_VERSION,
        manifest_checksum_sha256=manifest_checksum,
        onnx_checksum_sha256=BOOTSTRAP_SYMBOL_MODEL_SHA256,
        onnx_relative_path=BOOTSTRAP_SYMBOL_MODEL_PATH,
        storage_root=SymbolModelStorageRoot.REPOSITORY,
        class_codes=BOOTSTRAP_SYMBOL_CLASS_CODES,
        input_size=BOOTSTRAP_SYMBOL_INPUT_SIZE,
        temperature=BOOTSTRAP_SYMBOL_TEMPERATURE,
    )


__all__ = [
    "BOOTSTRAP_SYMBOL_CLASS_CODES",
    "BOOTSTRAP_SYMBOL_INPUT_SIZE",
    "BOOTSTRAP_SYMBOL_MODEL_PATH",
    "BOOTSTRAP_SYMBOL_MODEL_SHA256",
    "BOOTSTRAP_SYMBOL_MODEL_VERSION",
    "BOOTSTRAP_SYMBOL_TEMPERATURE",
    "SymbolModelJobSnapshot",
    "SymbolModelStorageRoot",
    "bootstrap_symbol_model_snapshot",
]
