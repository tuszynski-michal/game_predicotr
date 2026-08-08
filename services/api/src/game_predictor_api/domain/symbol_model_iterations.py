"""Domain contract for immutable symbol-model training iterations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class SymbolModelIterationStatus(StrEnum):
    CREATED = "created"
    DATASET_BUILD = "dataset_build"
    TRAINING = "training"
    TRAINED = "trained"
    EVALUATING = "evaluating"
    CANDIDATE_READY = "candidate_ready"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class SymbolTrainingConfiguration:
    architecture_version: str = "spatial-symbol-cnn-v1"
    variant: str = "spatial"
    seed: int = 61061
    epochs: int = 40
    batch_size: int = 32
    learning_rate: float = 0.001
    weight_decay: float = 0.0001
    input_size: int = 64

    def validate(self) -> None:
        if self.architecture_version != "spatial-symbol-cnn-v1" or self.variant != "spatial":
            raise ValueError("Only the selected spatial-symbol-cnn-v1 model is supported.")
        if self.seed < 0 or self.epochs < 1 or self.batch_size < 1 or self.input_size < 16:
            raise ValueError("Invalid symbol training integer configuration.")
        if self.learning_rate <= 0 or self.weight_decay < 0:
            raise ValueError("Invalid symbol training optimizer configuration.")

    def to_payload(self) -> dict[str, object]:
        self.validate()
        return {
            "architectureVersion": self.architecture_version,
            "batchSize": self.batch_size,
            "epochs": self.epochs,
            "inputSize": self.input_size,
            "learningRate": self.learning_rate,
            "seed": self.seed,
            "variant": self.variant,
            "weightDecay": self.weight_decay,
        }

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.to_payload(), ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class SymbolModelIteration:
    id: UUID
    game_id: UUID
    cohort_id: UUID
    job_id: UUID
    iteration_number: int
    status: SymbolModelIterationStatus
    configuration_fingerprint: str
    configuration_payload: dict[str, object]
    dataset_manifest_checksum_sha256: str | None
    dataset_manifest_relative_path: str | None
    checkpoint_checksum_sha256: str | None
    checkpoint_relative_path: str | None
    gate_configuration_fingerprint: str | None
    gate_configuration_payload: dict[str, object] | None
    candidate_manifest_checksum_sha256: str | None
    candidate_manifest_relative_path: str | None
    gate_report_checksum_sha256: str | None
    gate_report_relative_path: str | None
    gate_metrics: dict[str, object]
    rejection_reasons: tuple[str, ...]
    last_completed_epoch: int
    partial_metrics: dict[str, object]
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


__all__ = [
    "SymbolModelIteration",
    "SymbolModelIterationStatus",
    "SymbolTrainingConfiguration",
]
