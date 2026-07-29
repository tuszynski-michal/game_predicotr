"""Versioned, deterministic PyTorch baseline for reviewed symbol crops."""

from __future__ import annotations

import copy
import hashlib
import json
import random
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

import numpy as np
import torch
import torchvision  # type: ignore[import-untyped]
from PIL import Image
from torch import Tensor, nn
from torch.utils.data import DataLoader, Dataset
from torchvision.transforms import functional as vision_functional  # type: ignore[import-untyped]

from .dataset_split import DATASET_SPLIT_VERSION, build_symbol_dataset_split

CLASSIFIER_VERSION = "bootstrap-symbol-cnn-v1"
ARCHITECTURE_VERSION = "small-symbol-cnn-v1"
PREPROCESSING_VERSION = "rgb-resize64-normalize-half-v1"
REPORT_VERSION = "symbol-classifier-training-report-v1"
DEFAULT_SEED = 61061


class SymbolClassifierError(ValueError):
    """Stable training or input-contract failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class TrainingConfig:
    seed: int = DEFAULT_SEED
    epochs: int = 40
    batch_size: int = 32
    learning_rate: float = 0.001
    weight_decay: float = 0.0001
    input_size: int = 64

    def validate(self) -> None:
        if self.seed < 0:
            raise SymbolClassifierError(
                "SYMBOL_CLASSIFIER_CONFIG_INVALID",
                "seed must be non-negative.",
            )
        if self.epochs < 1 or self.batch_size < 1 or self.input_size < 16:
            raise SymbolClassifierError(
                "SYMBOL_CLASSIFIER_CONFIG_INVALID",
                "epochs, batch_size and input_size must be positive.",
            )
        if self.learning_rate <= 0 or self.weight_decay < 0:
            raise SymbolClassifierError(
                "SYMBOL_CLASSIFIER_CONFIG_INVALID",
                "learning_rate must be positive and weight_decay non-negative.",
            )


@dataclass(frozen=True, slots=True)
class ClassifierSample:
    sample_id: str
    asset_path: Path
    asset_checksum: str
    source_image_checksum: str
    symbol_code: str
    class_index: int


@dataclass(frozen=True, slots=True)
class PreparedTrainingData:
    dataset_sha256: str
    split_sha256: str
    split_seed: str
    class_codes: tuple[str, ...]
    class_ids: tuple[str, ...]
    train: tuple[ClassifierSample, ...]
    validation: tuple[ClassifierSample, ...]
    test: tuple[ClassifierSample, ...]


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    loss: float
    accuracy: float
    macro_recall: float
    confusion_matrix: tuple[tuple[int, ...], ...]
    per_class: tuple[Mapping[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "accuracy": round(self.accuracy, 8),
            "confusionMatrix": [list(row) for row in self.confusion_matrix],
            "loss": round(self.loss, 8),
            "macroRecall": round(self.macro_recall, 8),
            "perClass": [dict(value) for value in self.per_class],
        }


@dataclass(frozen=True, slots=True)
class TrainingOutcome:
    state_dict: Mapping[str, Tensor]
    best_epoch: int
    history: tuple[Mapping[str, object], ...]
    validation_metrics: EvaluationMetrics


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _load_mapping(path: Path, code: str) -> tuple[bytes, Mapping[str, object]]:
    try:
        content = path.read_bytes()
        value: Any = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise SymbolClassifierError(code, f"Cannot read {path.name}.") from error
    if not isinstance(value, Mapping):
        raise SymbolClassifierError(code, f"{path.name} must contain an object.")
    return content, value


def _sequence(value: object, label: str) -> Sequence[object]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise SymbolClassifierError(
            "SYMBOL_CLASSIFIER_CONTRACT_INVALID",
            f"{label} must be an array.",
        )
    return value


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SymbolClassifierError(
            "SYMBOL_CLASSIFIER_CONTRACT_INVALID",
            f"{label} must be an object.",
        )
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise SymbolClassifierError(
            "SYMBOL_CLASSIFIER_CONTRACT_INVALID",
            f"{label} must be a non-empty string.",
        )
    return value


def _sha256(value: object, label: str) -> str:
    text = _text(value, label).lower()
    if len(text) != 64:
        raise SymbolClassifierError(
            "SYMBOL_CLASSIFIER_CONTRACT_INVALID",
            f"{label} must be a SHA-256 value.",
        )
    try:
        int(text, 16)
    except ValueError as error:
        raise SymbolClassifierError(
            "SYMBOL_CLASSIFIER_CONTRACT_INVALID",
            f"{label} must be a SHA-256 value.",
        ) from error
    return text


def _safe_asset_path(root: Path, relative_value: object) -> Path:
    relative = PurePosixPath(_text(relative_value, "assetRelativePath"))
    if relative.is_absolute() or ".." in relative.parts:
        raise SymbolClassifierError(
            "SYMBOL_CLASSIFIER_ASSET_PATH_UNSAFE",
            "Asset path must remain below the configured artifact root.",
        )
    root_resolved = root.resolve()
    resolved = root_resolved.joinpath(*relative.parts).resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as error:
        raise SymbolClassifierError(
            "SYMBOL_CLASSIFIER_ASSET_PATH_UNSAFE",
            "Asset path escapes the configured artifact root.",
        ) from error
    return resolved


def prepare_training_data(
    dataset_path: Path,
    split_path: Path,
    asset_root: Path,
) -> PreparedTrainingData:
    """Validate immutable inputs and resolve the exact samples for each split."""

    dataset_content, dataset = _load_mapping(
        dataset_path,
        "SYMBOL_CLASSIFIER_DATASET_INVALID",
    )
    split_content, split = _load_mapping(
        split_path,
        "SYMBOL_CLASSIFIER_SPLIT_INVALID",
    )
    if split.get("datasetSplitVersion") != DATASET_SPLIT_VERSION:
        raise SymbolClassifierError(
            "SYMBOL_CLASSIFIER_SPLIT_VERSION_UNSUPPORTED",
            "The source-aware split version is unsupported.",
        )
    split_seed = _text(split.get("seed"), "seed")
    expected_split = build_symbol_dataset_split(dataset_path, seed=split_seed).to_json_bytes()
    if expected_split != split_content:
        raise SymbolClassifierError(
            "SYMBOL_CLASSIFIER_SPLIT_DRIFT",
            "The split report does not match the dataset and seed.",
        )
    dataset_sha256 = hashlib.sha256(dataset_content).hexdigest()
    if _sha256(split.get("datasetSha256"), "datasetSha256") != dataset_sha256:
        raise SymbolClassifierError(
            "SYMBOL_CLASSIFIER_DATASET_DRIFT",
            "The split report references different dataset bytes.",
        )

    symbol_rows = _sequence(split.get("symbols"), "symbols")
    symbol_pairs = sorted(
        (
            _text(_mapping(row, "symbol").get("symbolCode"), "symbolCode"),
            _text(_mapping(row, "symbol").get("symbolId"), "symbolId"),
        )
        for row in symbol_rows
    )
    if not symbol_pairs:
        raise SymbolClassifierError(
            "SYMBOL_CLASSIFIER_CLASSES_MISSING",
            "The split report does not define classes.",
        )
    class_codes = tuple(code for code, _ in symbol_pairs)
    class_ids = tuple(symbol_id for _, symbol_id in symbol_pairs)
    class_indexes = {code: index for index, code in enumerate(class_codes)}

    sample_rows = _sequence(dataset.get("samples"), "samples")
    samples_by_id: dict[str, ClassifierSample] = {}
    for index, raw_sample in enumerate(sample_rows):
        sample = _mapping(raw_sample, f"samples[{index}]")
        sample_id = _sha256(sample.get("sampleId"), f"samples[{index}].sampleId")
        symbol_code = _text(
            sample.get("symbolCode"),
            f"samples[{index}].symbolCode",
        )
        if symbol_code not in class_indexes:
            raise SymbolClassifierError(
                "SYMBOL_CLASSIFIER_CLASS_UNKNOWN",
                "A dataset sample references an unknown class.",
            )
        asset_checksum = _sha256(
            sample.get("cropChecksumSha256"),
            f"samples[{index}].cropChecksumSha256",
        )
        asset_path = _safe_asset_path(asset_root, sample.get("assetRelativePath"))
        try:
            asset_content = asset_path.read_bytes()
        except OSError as error:
            raise SymbolClassifierError(
                "SYMBOL_CLASSIFIER_ASSET_MISSING",
                f"Cannot read asset for sample {sample_id}.",
            ) from error
        if hashlib.sha256(asset_content).hexdigest() != asset_checksum:
            raise SymbolClassifierError(
                "SYMBOL_CLASSIFIER_ASSET_DRIFT",
                f"Asset checksum mismatch for sample {sample_id}.",
            )
        samples_by_id[sample_id] = ClassifierSample(
            sample_id=sample_id,
            asset_path=asset_path,
            asset_checksum=asset_checksum,
            source_image_checksum=_sha256(
                sample.get("sourceImageChecksumSha256"),
                f"samples[{index}].sourceImageChecksumSha256",
            ),
            symbol_code=symbol_code,
            class_index=class_indexes[symbol_code],
        )

    split_samples: dict[str, tuple[ClassifierSample, ...]] = {}
    assigned: set[str] = set()
    for raw_split in _sequence(split.get("splits"), "splits"):
        split_row = _mapping(raw_split, "split")
        name = _text(split_row.get("name"), "split.name")
        if name not in {"train", "validation", "test"} or name in split_samples:
            raise SymbolClassifierError(
                "SYMBOL_CLASSIFIER_SPLIT_INVALID",
                "Split names must be unique train, validation and test.",
            )
        selected: list[ClassifierSample] = []
        for raw_sample_id in _sequence(split_row.get("sampleIds"), "sampleIds"):
            sample_id = _sha256(raw_sample_id, "sampleId")
            if sample_id in assigned or sample_id not in samples_by_id:
                raise SymbolClassifierError(
                    "SYMBOL_CLASSIFIER_SPLIT_SAMPLE_INVALID",
                    "Split sample identifiers must be known and disjoint.",
                )
            assigned.add(sample_id)
            selected.append(samples_by_id[sample_id])
        split_samples[name] = tuple(selected)
    if assigned != set(samples_by_id) or set(split_samples) != {
        "train",
        "validation",
        "test",
    }:
        raise SymbolClassifierError(
            "SYMBOL_CLASSIFIER_SPLIT_INCOMPLETE",
            "The split must assign every dataset sample exactly once.",
        )
    return PreparedTrainingData(
        dataset_sha256=dataset_sha256,
        split_sha256=hashlib.sha256(split_content).hexdigest(),
        split_seed=split_seed,
        class_codes=class_codes,
        class_ids=class_ids,
        train=split_samples["train"],
        validation=split_samples["validation"],
        test=split_samples["test"],
    )


class SymbolTensorDataset(Dataset[tuple[Tensor, Tensor]]):
    def __init__(self, samples: Sequence[ClassifierSample], input_size: int) -> None:
        self._samples = tuple(samples)
        self._input_size = input_size

    def __len__(self) -> int:
        return len(self._samples)

    def __getitem__(self, index: int) -> tuple[Tensor, Tensor]:
        sample = self._samples[index]
        tensor = load_image_tensor(sample.asset_path, self._input_size)
        return tensor, torch.tensor(sample.class_index, dtype=torch.long)


def load_image_tensor(path: Path, input_size: int) -> Tensor:
    """Apply the immutable classifier preprocessing contract to one crop."""

    try:
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            tensor = vision_functional.pil_to_tensor(rgb).to(dtype=torch.float32)
    except OSError as error:
        raise SymbolClassifierError(
            "SYMBOL_CLASSIFIER_ASSET_UNREADABLE",
            f"Cannot read classifier asset {path.name}.",
        ) from error
    tensor = vision_functional.resize(
        tensor,
        [input_size, input_size],
        antialias=True,
    )
    return cast(Tensor, tensor.div(255.0).sub(0.5).div(0.5))


class SmallSymbolCnn(nn.Module):
    def __init__(self, class_count: int) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 16, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(16, 32, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((1, 1)),
        )
        self.classifier = nn.Linear(64, class_count)

    def encode(self, value: Tensor) -> Tensor:
        features = self.features(value)
        return torch.flatten(features, 1)

    def forward(self, value: Tensor) -> Tensor:
        return cast(Tensor, self.classifier(self.encode(value)))


def load_classifier_artifact(
    path: Path,
) -> tuple[SmallSymbolCnn, tuple[str, ...], int]:
    """Load and validate the versioned CPU bootstrap checkpoint."""

    try:
        payload: Any = torch.load(path, map_location="cpu", weights_only=True)
    except (OSError, RuntimeError, ValueError) as error:
        raise SymbolClassifierError(
            "SYMBOL_CLASSIFIER_ARTIFACT_INVALID",
            "The classifier artifact cannot be read.",
        ) from error
    if not isinstance(payload, Mapping):
        raise SymbolClassifierError(
            "SYMBOL_CLASSIFIER_ARTIFACT_INVALID",
            "The classifier artifact must contain an object.",
        )
    if (
        payload.get("architectureVersion") != ARCHITECTURE_VERSION
        or payload.get("classifierVersion") != CLASSIFIER_VERSION
    ):
        raise SymbolClassifierError(
            "SYMBOL_CLASSIFIER_ARTIFACT_VERSION_UNSUPPORTED",
            "The classifier artifact version is unsupported.",
        )
    raw_codes = _sequence(payload.get("classCodes"), "classCodes")
    class_codes = tuple(_text(value, "classCodes") for value in raw_codes)
    config = _mapping(payload.get("config"), "config")
    input_size = config.get("inputSize")
    if not isinstance(input_size, int) or input_size < 16:
        raise SymbolClassifierError(
            "SYMBOL_CLASSIFIER_ARTIFACT_INVALID",
            "The classifier input size is invalid.",
        )
    raw_state = payload.get("stateDict")
    if not isinstance(raw_state, Mapping) or not all(
        isinstance(name, str) and isinstance(value, Tensor) for name, value in raw_state.items()
    ):
        raise SymbolClassifierError(
            "SYMBOL_CLASSIFIER_ARTIFACT_INVALID",
            "The classifier state is invalid.",
        )
    model = SmallSymbolCnn(len(class_codes))
    try:
        model.load_state_dict(dict(raw_state), strict=True)
    except RuntimeError as error:
        raise SymbolClassifierError(
            "SYMBOL_CLASSIFIER_ARTIFACT_INVALID",
            "The classifier state does not match its architecture.",
        ) from error
    model.eval()
    return model, class_codes, input_size


def set_deterministic_runtime(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)


def _loader(
    samples: Sequence[ClassifierSample],
    config: TrainingConfig,
    *,
    shuffle: bool,
) -> DataLoader[tuple[Tensor, Tensor]]:
    generator = torch.Generator(device="cpu")
    generator.manual_seed(config.seed)
    return DataLoader(
        SymbolTensorDataset(samples, config.input_size),
        batch_size=config.batch_size,
        shuffle=shuffle,
        generator=generator,
        num_workers=0,
    )


def _evaluate(
    model: nn.Module,
    samples: Sequence[ClassifierSample],
    config: TrainingConfig,
    class_codes: Sequence[str],
    criterion: nn.Module,
) -> EvaluationMetrics:
    model.eval()
    confusion = [[0 for _ in class_codes] for _ in class_codes]
    loss_total = 0.0
    sample_total = 0
    with torch.inference_mode():
        for inputs, targets in _loader(samples, config, shuffle=False):
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


def train_classifier(
    data: PreparedTrainingData,
    config: TrainingConfig,
) -> TrainingOutcome:
    """Train using train/validation only and return the best validation state."""

    config.validate()
    set_deterministic_runtime(config.seed)
    model = SmallSymbolCnn(len(data.class_codes))
    class_counts = Counter(sample.class_index for sample in data.train)
    weights = torch.tensor(
        [len(data.train) / class_counts[index] for index in range(len(data.class_codes))],
        dtype=torch.float32,
    )
    criterion = nn.CrossEntropyLoss(weight=weights / weights.mean())
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    train_loader = _loader(data.train, config, shuffle=True)
    best_key: tuple[float, float, float, int] | None = None
    best_state: Mapping[str, Tensor] | None = None
    best_metrics: EvaluationMetrics | None = None
    best_epoch = 0
    history: list[Mapping[str, object]] = []

    for epoch in range(1, config.epochs + 1):
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
        validation = _evaluate(
            model,
            data.validation,
            config,
            data.class_codes,
            criterion,
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
            "SYMBOL_CLASSIFIER_TRAINING_FAILED",
            "Training did not produce a validation checkpoint.",
        )
    return TrainingOutcome(
        state_dict=best_state,
        best_epoch=best_epoch,
        history=tuple(history),
        validation_metrics=best_metrics,
    )


def evaluate_classifier(
    state_dict: Mapping[str, Tensor],
    samples: Sequence[ClassifierSample],
    config: TrainingConfig,
    class_codes: Sequence[str],
) -> EvaluationMetrics:
    """Evaluate one immutable checkpoint on a held-out sample sequence."""

    set_deterministic_runtime(config.seed)
    model = SmallSymbolCnn(len(class_codes))
    model.load_state_dict(state_dict)
    return _evaluate(
        model,
        samples,
        config,
        class_codes,
        nn.CrossEntropyLoss(),
    )


def logical_state_sha256(state_dict: Mapping[str, Tensor]) -> str:
    digest = hashlib.sha256()
    for name in sorted(state_dict):
        tensor = state_dict[name].detach().cpu().contiguous()
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(str(tensor.dtype).encode())
        digest.update(b"\0")
        digest.update(json.dumps(list(tensor.shape)).encode())
        digest.update(b"\0")
        digest.update(tensor.numpy().tobytes(order="C"))
    return digest.hexdigest()


def parameter_count(state_dict: Mapping[str, Tensor]) -> int:
    return sum(tensor.numel() for tensor in state_dict.values())


def build_training_report(
    data: PreparedTrainingData,
    config: TrainingConfig,
    outcome: TrainingOutcome,
    test_metrics: EvaluationMetrics,
    *,
    artifact_relative_path: str,
    artifact_sha256: str,
) -> dict[str, object]:
    return {
        "architectureVersion": ARCHITECTURE_VERSION,
        "artifact": {
            "logicalStateSha256": logical_state_sha256(outcome.state_dict),
            "parameterCount": parameter_count(outcome.state_dict),
            "relativePath": artifact_relative_path,
            "sha256": artifact_sha256,
        },
        "bestEpoch": outcome.best_epoch,
        "classes": [
            {"classIndex": index, "symbolCode": code, "symbolId": data.class_ids[index]}
            for index, code in enumerate(data.class_codes)
        ],
        "classifierVersion": CLASSIFIER_VERSION,
        "config": asdict(config),
        "datasetSha256": data.dataset_sha256,
        "history": [dict(row) for row in outcome.history],
        "preprocessingVersion": PREPROCESSING_VERSION,
        "reportVersion": REPORT_VERSION,
        "runtime": {
            "device": "cpu",
            "torchVersion": torch.__version__,
            "torchvisionVersion": torchvision.__version__,
        },
        "schemaVersion": 1,
        "splitSha256": data.split_sha256,
        "splitSeed": data.split_seed,
        "status": "bootstrap",
        "testMetrics": test_metrics.to_dict(),
        "trainingSampleCount": len(data.train),
        "validationMetrics": outcome.validation_metrics.to_dict(),
        "validationSampleCount": len(data.validation),
        "testSampleCount": len(data.test),
    }


def training_report_json_bytes(value: Mapping[str, object]) -> bytes:
    return _json_bytes(value)
