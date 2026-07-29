"""Bounded validation-only architecture benchmark for the M6 symbol model."""

from __future__ import annotations

import copy
import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

import torch
from torch import Tensor, nn
from torch.utils.data import DataLoader, Dataset
from torchvision.transforms import functional as vision_functional  # type: ignore[import-untyped]

from .symbol_classifier import (
    ClassifierSample,
    EvaluationMetrics,
    PreparedTrainingData,
    SymbolClassifierError,
    TrainingConfig,
    TrainingOutcome,
    load_image_tensor,
    set_deterministic_runtime,
)

BENCHMARK_VERSION = "symbol-model-benchmark-v1"
SPATIAL_ARCHITECTURE_VERSION = "spatial-symbol-cnn-v1"
AUGMENTATION_VERSION = "bounded-affine-color-v1"
NO_AUGMENTATION_VERSION = "none"
SPATIAL_VARIANT = "spatial"
SPATIAL_AUGMENTED_VARIANT = "spatial_augmented"
SUPPORTED_VARIANTS = (SPATIAL_VARIANT, SPATIAL_AUGMENTED_VARIANT)


@dataclass(frozen=True, slots=True)
class ValidationCandidate:
    candidate_id: str
    validation_metrics: EvaluationMetrics
    parameter_count: int


class SpatialSymbolCnn(nn.Module):
    """Small CPU model that keeps a bounded 4 x 4 spatial feature map."""

    def __init__(self, class_count: int) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 24, kernel_size=3, padding=1),
            nn.BatchNorm2d(24),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(24, 48, kernel_size=3, padding=1),
            nn.BatchNorm2d(48),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(48, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((4, 4)),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(64 * 4 * 4, 128),
            nn.ReLU(),
            nn.Dropout(p=0.15),
            nn.Linear(128, class_count),
        )

    def forward(self, value: Tensor) -> Tensor:
        return cast(Tensor, self.classifier(self.features(value)))


def validate_variant(variant: str) -> None:
    if variant not in SUPPORTED_VARIANTS:
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_VARIANT_UNSUPPORTED",
            f"Unsupported benchmark variant: {variant}.",
        )


def augmentation_version(variant: str) -> str:
    validate_variant(variant)
    return (
        AUGMENTATION_VERSION
        if variant == SPATIAL_AUGMENTED_VARIANT
        else NO_AUGMENTATION_VERSION
    )


def build_benchmark_model(variant: str, class_count: int) -> SpatialSymbolCnn:
    validate_variant(variant)
    if class_count < 2:
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_CLASS_COUNT_INVALID",
            "At least two classes are required.",
        )
    return SpatialSymbolCnn(class_count)


def _augmentation_parameters(
    sample_id: str,
    *,
    seed: int,
    epoch: int,
) -> tuple[float, tuple[int, int], float, float, float]:
    digest = hashlib.sha256(f"{seed}:{epoch}:{sample_id}".encode()).digest()

    def unit(index: int) -> float:
        return int.from_bytes(digest[index : index + 2], "big") / 65535.0

    angle = -4.0 + unit(0) * 8.0
    translate = (
        int(round(-2.0 + unit(2) * 4.0)),
        int(round(-2.0 + unit(4) * 4.0)),
    )
    scale = 0.95 + unit(6) * 0.10
    brightness = 0.88 + unit(8) * 0.24
    contrast = 0.88 + unit(10) * 0.24
    return angle, translate, scale, brightness, contrast


def augment_training_tensor(
    tensor: Tensor,
    sample_id: str,
    *,
    seed: int,
    epoch: int,
) -> Tensor:
    """Apply deterministic bounded augmentation to one normalized train tensor."""

    angle, translate, scale, brightness, contrast = _augmentation_parameters(
        sample_id,
        seed=seed,
        epoch=epoch,
    )
    transformed = vision_functional.affine(
        tensor,
        angle=angle,
        translate=list(translate),
        scale=scale,
        shear=[0.0, 0.0],
        interpolation=vision_functional.InterpolationMode.BILINEAR,
        fill=0.0,
    )
    transformed = transformed.mul(brightness)
    channel_mean = transformed.mean(dim=(1, 2), keepdim=True)
    transformed = (transformed - channel_mean).mul(contrast).add(channel_mean)
    return cast(Tensor, transformed.clamp(-1.0, 1.0))


class BenchmarkTensorDataset(Dataset[tuple[Tensor, Tensor]]):
    def __init__(
        self,
        samples: Sequence[ClassifierSample],
        input_size: int,
        *,
        augment: bool,
        seed: int,
    ) -> None:
        self._samples = tuple(samples)
        self._input_size = input_size
        self._augment = augment
        self._seed = seed
        self._epoch = 0

    def set_epoch(self, epoch: int) -> None:
        self._epoch = epoch

    def __len__(self) -> int:
        return len(self._samples)

    def __getitem__(self, index: int) -> tuple[Tensor, Tensor]:
        sample = self._samples[index]
        tensor = load_image_tensor(sample.asset_path, self._input_size)
        if self._augment:
            tensor = augment_training_tensor(
                tensor,
                sample.sample_id,
                seed=self._seed,
                epoch=self._epoch,
            )
        return tensor, torch.tensor(sample.class_index, dtype=torch.long)


def _loader(
    dataset: BenchmarkTensorDataset,
    config: TrainingConfig,
    *,
    shuffle: bool,
) -> DataLoader[tuple[Tensor, Tensor]]:
    generator = torch.Generator(device="cpu")
    generator.manual_seed(config.seed)
    return DataLoader(
        dataset,
        batch_size=config.batch_size,
        shuffle=shuffle,
        generator=generator,
        num_workers=0,
    )


def evaluate_benchmark_model(
    model: nn.Module,
    samples: Sequence[ClassifierSample],
    config: TrainingConfig,
    class_codes: Sequence[str],
) -> EvaluationMetrics:
    model.eval()
    dataset = BenchmarkTensorDataset(
        samples,
        config.input_size,
        augment=False,
        seed=config.seed,
    )
    confusion = [[0 for _ in class_codes] for _ in class_codes]
    criterion = nn.CrossEntropyLoss()
    loss_total = 0.0
    sample_total = 0
    with torch.inference_mode():
        for inputs, targets in _loader(dataset, config, shuffle=False):
            logits = model(inputs)
            loss = criterion(logits, targets)
            predictions = torch.argmax(logits, dim=1)
            loss_total += float(loss.item()) * len(targets)
            sample_total += len(targets)
            for target, prediction in zip(
                targets.tolist(),
                predictions.tolist(),
                strict=True,
            ):
                confusion[target][prediction] += 1
    if sample_total == 0:
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_SPLIT_EMPTY",
            "The evaluated split cannot be empty.",
        )
    per_class: list[Mapping[str, object]] = []
    recalls: list[float] = []
    correct = 0
    for index, code in enumerate(class_codes):
        true_positive = confusion[index][index]
        support = sum(confusion[index])
        predicted = sum(row[index] for row in confusion)
        recall = true_positive / support if support else 0.0
        precision = true_positive / predicted if predicted else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        recalls.append(recall)
        correct += true_positive
        per_class.append(
            {
                "f1": round(f1, 8),
                "precision": round(precision, 8),
                "recall": round(recall, 8),
                "support": support,
                "symbolCode": code,
            }
        )
    return EvaluationMetrics(
        loss=loss_total / sample_total,
        accuracy=correct / sample_total,
        macro_recall=sum(recalls) / len(recalls),
        confusion_matrix=tuple(tuple(row) for row in confusion),
        per_class=tuple(per_class),
    )


def train_validation_candidate(
    data: PreparedTrainingData,
    config: TrainingConfig,
    variant: str,
) -> TrainingOutcome:
    """Train one candidate using train and validation without reading test."""

    validate_variant(variant)
    config.validate()
    set_deterministic_runtime(config.seed)
    model = build_benchmark_model(variant, len(data.class_codes))
    class_counts = Counter(sample.class_index for sample in data.train)
    weights = torch.tensor(
        [len(data.train) / class_counts[index] for index in range(len(data.class_codes))],
        dtype=torch.float32,
    )
    criterion = nn.CrossEntropyLoss(weight=weights / weights.mean())
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    train_dataset = BenchmarkTensorDataset(
        data.train,
        config.input_size,
        augment=variant == SPATIAL_AUGMENTED_VARIANT,
        seed=config.seed,
    )
    train_loader = _loader(train_dataset, config, shuffle=True)
    best_key: tuple[float, float, float, int] | None = None
    best_state: Mapping[str, Tensor] | None = None
    best_metrics: EvaluationMetrics | None = None
    best_epoch = 0
    history: list[Mapping[str, object]] = []
    for epoch in range(1, config.epochs + 1):
        train_dataset.set_epoch(epoch)
        model.train()
        loss_total = 0.0
        sample_total = 0
        for inputs, targets in train_loader:
            optimizer.zero_grad(set_to_none=True)
            logits = model(inputs)
            loss = criterion(logits, targets)
            loss.backward()
            optimizer.step()
            loss_total += float(loss.item()) * len(targets)
            sample_total += len(targets)
        validation = evaluate_benchmark_model(
            model,
            data.validation,
            config,
            data.class_codes,
        )
        training_loss = loss_total / sample_total
        history.append(
            {
                "epoch": epoch,
                "trainingLoss": round(training_loss, 8),
                "validationAccuracy": round(validation.accuracy, 8),
                "validationLoss": round(validation.loss, 8),
                "validationMacroRecall": round(validation.macro_recall, 8),
            }
        )
        key = (
            validation.macro_recall,
            validation.accuracy,
            -validation.loss,
            -epoch,
        )
        if best_key is None or key > best_key:
            best_key = key
            best_epoch = epoch
            best_metrics = validation
            best_state = copy.deepcopy(model.state_dict())
    if best_state is None or best_metrics is None:
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_TRAINING_FAILED",
            "Training did not produce a validation checkpoint.",
        )
    return TrainingOutcome(
        state_dict=best_state,
        best_epoch=best_epoch,
        history=tuple(history),
        validation_metrics=best_metrics,
    )


def select_validation_candidate(
    candidates: Sequence[ValidationCandidate],
) -> ValidationCandidate:
    if len(candidates) < 2:
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_CANDIDATES_MISSING",
            "At least two validation candidates are required.",
        )
    identifiers = [candidate.candidate_id for candidate in candidates]
    if len(set(identifiers)) != len(identifiers):
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_CANDIDATE_DUPLICATE",
            "Candidate identifiers must be unique.",
        )
    return max(
        candidates,
        key=lambda candidate: (
            candidate.validation_metrics.macro_recall,
            candidate.validation_metrics.accuracy,
            -candidate.validation_metrics.loss,
            -candidate.parameter_count,
            candidate.candidate_id,
        ),
    )


__all__ = [
    "AUGMENTATION_VERSION",
    "BENCHMARK_VERSION",
    "NO_AUGMENTATION_VERSION",
    "SPATIAL_ARCHITECTURE_VERSION",
    "SPATIAL_AUGMENTED_VARIANT",
    "SPATIAL_VARIANT",
    "SUPPORTED_VARIANTS",
    "BenchmarkTensorDataset",
    "SpatialSymbolCnn",
    "ValidationCandidate",
    "augment_training_tensor",
    "augmentation_version",
    "build_benchmark_model",
    "evaluate_benchmark_model",
    "select_validation_candidate",
    "train_validation_candidate",
    "validate_variant",
]
