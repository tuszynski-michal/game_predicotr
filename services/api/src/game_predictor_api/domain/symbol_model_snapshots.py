"""Pinned, checksum-bound symbol model descriptor stored in image import jobs."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import cast
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

    @classmethod
    def from_payload(cls, value: object) -> SymbolModelJobSnapshot:
        if not isinstance(value, Mapping):
            raise ValueError("The symbol model snapshot must be an object.")
        try:
            iteration_value = value.get("iterationId")
            iteration_id = None if iteration_value is None else UUID(str(iteration_value))
            class_values = value["classCodes"]
            if isinstance(class_values, str | bytes) or not isinstance(class_values, Sequence):
                raise ValueError("classCodes must be an array.")
            class_codes = cast(tuple[str, ...], tuple(class_values))
            if (
                len(class_codes) < 2
                or not all(isinstance(item, str) and item for item in class_codes)
                or len(set(class_codes)) != len(class_codes)
            ):
                raise ValueError("classCodes must contain unique non-empty values.")
            input_size = value["inputSize"]
            temperature = value["temperature"]
            if (
                isinstance(input_size, bool)
                or not isinstance(input_size, int)
                or input_size < 16
                or isinstance(temperature, bool)
                or not isinstance(temperature, int | float)
                or not math.isfinite(float(temperature))
                or float(temperature) <= 0
            ):
                raise ValueError("The symbol model runtime values are invalid.")
            onnx_relative_path = _required_text(value, "onnxRelativePath")
            relative = PurePosixPath(onnx_relative_path)
            if (
                relative.is_absolute()
                or "\\" in onnx_relative_path
                or any(part in {"", ".", ".."} for part in relative.parts)
            ):
                raise ValueError("The symbol model path is unsafe.")
            snapshot = cls(
                iteration_id=iteration_id,
                model_version=_required_text(value, "modelVersion"),
                manifest_checksum_sha256=_required_sha256(value, "manifestChecksumSha256"),
                onnx_checksum_sha256=_required_sha256(value, "onnxChecksumSha256"),
                onnx_relative_path=onnx_relative_path,
                storage_root=SymbolModelStorageRoot(_required_text(value, "storageRoot")),
                class_codes=class_codes,
                input_size=input_size,
                temperature=float(temperature),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("The pinned symbol model snapshot is invalid.") from error
        if value.get("inferenceFingerprint") != snapshot.inference_fingerprint:
            raise ValueError("The pinned symbol model inference fingerprint changed.")
        return snapshot


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


def _required_text(value: Mapping[str, object], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result:
        raise ValueError(f"{field} must be a non-empty string.")
    return result


def _required_sha256(value: Mapping[str, object], field: str) -> str:
    result = _required_text(value, field)
    if len(result) != 64:
        raise ValueError(f"{field} must be a SHA-256 checksum.")
    try:
        int(result, 16)
    except ValueError as error:
        raise ValueError(f"{field} must be a SHA-256 checksum.") from error
    if result != result.lower():
        raise ValueError(f"{field} must be lowercase.")
    return result


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
