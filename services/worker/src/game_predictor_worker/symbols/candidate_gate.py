"""ONNX export, calibration and fail-closed quality gate for one trained iteration."""

from __future__ import annotations

import hashlib
import json
import os
import statistics
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import torch
from numpy.typing import NDArray
from torch import Tensor, nn

from game_predictor_worker.images.symbol_classifier import (
    ClassifierSample,
    PreparedTrainingData,
    TrainingConfig,
    load_image_tensor,
)
from game_predictor_worker.images.symbol_confidence import (
    CALIBRATION_VERSION,
    calibrated_probabilities,
    calibration_metrics,
    fit_temperature,
)
from game_predictor_worker.images.symbol_model_benchmark import build_benchmark_model
from game_predictor_worker.images.symbol_model_release import SPATIAL_ONNX_MODEL_VERSION
from game_predictor_worker.images.symbol_onnx import (
    MAX_PARITY_ABSOLUTE_ERROR,
    LocalSymbolOnnxAdapter,
    export_symbol_classifier_onnx,
)

GATE_VERSION = "symbol-candidate-gate-v1"
ARTIFACT_MANIFEST_VERSION = "symbol-candidate-manifest-v1"


class SymbolCandidateGateError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class SymbolCandidateGateConfiguration:
    minimum_accuracy: float = 0.80
    minimum_macro_recall: float = 0.75
    maximum_accuracy_regression: float = 0.02
    maximum_per_symbol_recall_regression: float = 0.05
    maximum_parity_absolute_error: float = MAX_PARITY_ABSOLUTE_ERROR
    parity_sample_limit: int = 32
    inference_batch_size: int = 64
    performance_repetitions: int = 3

    def to_payload(self) -> dict[str, object]:
        if (
            not 0 <= self.minimum_accuracy <= 1
            or not 0 <= self.minimum_macro_recall <= 1
            or not 0 <= self.maximum_accuracy_regression <= 1
            or not 0 <= self.maximum_per_symbol_recall_regression <= 1
            or self.maximum_parity_absolute_error <= 0
            or self.parity_sample_limit < 1
            or self.inference_batch_size < 1
            or self.performance_repetitions < 1
        ):
            raise SymbolCandidateGateError(
                "SYMBOL_CANDIDATE_GATE_CONFIG_INVALID", "Candidate gate configuration is invalid."
            )
        return {
            "gateVersion": GATE_VERSION,
            "inferenceBatchSize": self.inference_batch_size,
            "maximumAccuracyRegression": self.maximum_accuracy_regression,
            "maximumParityAbsoluteError": self.maximum_parity_absolute_error,
            "maximumPerSymbolRecallRegression": self.maximum_per_symbol_recall_regression,
            "minimumAccuracy": self.minimum_accuracy,
            "minimumMacroRecall": self.minimum_macro_recall,
            "paritySampleLimit": self.parity_sample_limit,
            "performanceRepetitions": self.performance_repetitions,
        }

    @property
    def fingerprint(self) -> str:
        return _sha(_json_bytes(self.to_payload()))


@dataclass(frozen=True, slots=True)
class SymbolModelBaseline:
    iteration_id: str
    adapter: LocalSymbolOnnxAdapter
    temperature: float


@dataclass(frozen=True, slots=True)
class SymbolCandidateGateResult:
    passed: bool
    rejection_reasons: tuple[str, ...]
    configuration_fingerprint: str
    configuration_payload: dict[str, object]
    manifest_checksum_sha256: str
    manifest_relative_path: str
    report_checksum_sha256: str
    report_relative_path: str
    onnx_checksum_sha256: str
    onnx_relative_path: str
    metrics: dict[str, object]


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write_content_addressed(
    root: Path, directory: str, suffix: str, content: bytes
) -> tuple[Path, str]:
    checksum = _sha(content)
    destination = root / directory / f"{checksum}.{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != content:
            raise SymbolCandidateGateError(
                "SYMBOL_CANDIDATE_ARTIFACT_CONFLICT", "Candidate artifact checksum collided."
            )
        return destination, checksum
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".tmp-", delete=False) as file:
        temporary = Path(file.name)
        file.write(content)
        file.flush()
        os.fsync(file.fileno())
    try:
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination, checksum


def _load_checkpoint_model(
    checkpoint_path: Path,
    checkpoint_checksum: str,
    class_count: int,
) -> nn.Module:
    try:
        content = checkpoint_path.read_bytes()
    except OSError as error:
        raise SymbolCandidateGateError(
            "SYMBOL_CANDIDATE_CHECKPOINT_MISSING", "Training checkpoint is unavailable."
        ) from error
    if _sha(content) != checkpoint_checksum:
        raise SymbolCandidateGateError(
            "SYMBOL_CANDIDATE_CHECKPOINT_DRIFT", "Training checkpoint checksum changed."
        )
    try:
        payload: Any = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    except (OSError, RuntimeError, ValueError) as error:
        raise SymbolCandidateGateError(
            "SYMBOL_CANDIDATE_CHECKPOINT_INVALID", "Training checkpoint cannot be decoded."
        ) from error
    if not isinstance(payload, Mapping):
        raise SymbolCandidateGateError(
            "SYMBOL_CANDIDATE_CHECKPOINT_INVALID", "Training checkpoint must be an object."
        )
    state = payload.get("bestState")
    if state is None:
        state = payload.get("modelState")
    if not isinstance(state, Mapping) or not all(
        isinstance(name, str) and isinstance(value, Tensor) for name, value in state.items()
    ):
        raise SymbolCandidateGateError(
            "SYMBOL_CANDIDATE_CHECKPOINT_INVALID", "Training checkpoint has no model state."
        )
    model = build_benchmark_model("spatial", class_count)
    try:
        model.load_state_dict(dict(state), strict=True)
    except RuntimeError as error:
        raise SymbolCandidateGateError(
            "SYMBOL_CANDIDATE_CHECKPOINT_INVALID", "Checkpoint does not match the model."
        ) from error
    model.eval()
    return model


def _sample_batch(samples: Sequence[ClassifierSample], input_size: int) -> NDArray[np.float32]:
    return np.stack(
        [load_image_tensor(sample.asset_path, input_size).numpy() for sample in samples]
    ).astype(np.float32, copy=False)


def _infer(
    adapter: LocalSymbolOnnxAdapter,
    samples: Sequence[ClassifierSample],
    *,
    batch_size: int,
    heartbeat: Callable[[], None],
) -> tuple[NDArray[np.float32], NDArray[np.int64]]:
    logits: list[NDArray[np.float32]] = []
    labels: list[int] = []
    for start in range(0, len(samples), batch_size):
        current = samples[start : start + batch_size]
        logits.append(adapter.infer(_sample_batch(current, adapter.input_size)).logits)
        labels.extend(sample.class_index for sample in current)
        heartbeat()
    if not logits:
        raise SymbolCandidateGateError(
            "SYMBOL_CANDIDATE_SPLIT_EMPTY", "Candidate evaluation split cannot be empty."
        )
    return np.concatenate(logits), np.asarray(labels, dtype=np.int64)


def _quality_metrics(
    logits: NDArray[np.float32],
    labels: NDArray[np.int64],
    class_codes: Sequence[str],
    temperature: float,
) -> dict[str, object]:
    probabilities = calibrated_probabilities(logits, temperature)
    values: dict[str, object] = dict(calibration_metrics(probabilities, labels, class_codes))
    predictions = np.argmax(probabilities, axis=1)
    confusion: NDArray[np.int64] = np.zeros((len(class_codes), len(class_codes)), dtype=np.int64)
    for target, prediction in zip(labels, predictions, strict=True):
        confusion[int(target), int(prediction)] += 1
    recalls = [
        float(confusion[index, index] / confusion[index].sum()) if confusion[index].sum() else 0.0
        for index in range(len(class_codes))
    ]
    values.update(
        {
            "confusionMatrix": confusion.tolist(),
            "macroRecall": round(sum(recalls) / len(recalls), 8),
        }
    )
    return values


def _regression_reasons(
    candidate: Mapping[str, object],
    baseline: Mapping[str, object] | None,
    config: SymbolCandidateGateConfiguration,
    label: str,
) -> list[str]:
    reasons: list[str] = []
    accuracy = float(cast(float, candidate["accuracy"]))
    macro_recall = float(cast(float, candidate["macroRecall"]))
    if accuracy < config.minimum_accuracy:
        reasons.append(f"{label.upper()}_ACCURACY_BELOW_MINIMUM")
    if macro_recall < config.minimum_macro_recall:
        reasons.append(f"{label.upper()}_MACRO_RECALL_BELOW_MINIMUM")
    if baseline is None:
        return reasons
    if accuracy + config.maximum_accuracy_regression < float(cast(float, baseline["accuracy"])):
        reasons.append(f"{label.upper()}_ACCURACY_REGRESSION")
    baseline_rows = {
        str(row["symbolCode"]): row
        for row in cast(Sequence[Mapping[str, object]], baseline["perClass"])
    }
    for row in cast(Sequence[Mapping[str, object]], candidate["perClass"]):
        code = str(row["symbolCode"])
        previous = baseline_rows.get(code)
        if previous is None:
            continue
        if float(cast(float, row["recall"])) + config.maximum_per_symbol_recall_regression < float(
            cast(float, previous["recall"])
        ):
            reasons.append(f"{label.upper()}_SYMBOL_RECALL_REGRESSION:{code}")
    return reasons


def build_symbol_candidate(
    *,
    artifact_root: Path,
    candidate_root: Path,
    checkpoint_path: Path,
    checkpoint_checksum: str,
    data: PreparedTrainingData,
    training_config: TrainingConfig,
    configuration: SymbolCandidateGateConfiguration | None = None,
    baseline: SymbolModelBaseline | None = None,
    stage: Callable[[str], None] = lambda _stage: None,
    heartbeat: Callable[[], None] = lambda: None,
) -> SymbolCandidateGateResult:
    """Build one immutable candidate without mutating an active model pointer."""

    gate = configuration or SymbolCandidateGateConfiguration()
    gate_payload = gate.to_payload()
    model = _load_checkpoint_model(checkpoint_path, checkpoint_checksum, len(data.class_codes))
    stage("onnx_export")
    onnx_content = export_symbol_classifier_onnx(
        model,
        input_size=training_config.input_size,
        class_count=len(data.class_codes),
        model_version=SPATIAL_ONNX_MODEL_VERSION,
    )
    onnx_path, onnx_checksum = _write_content_addressed(
        candidate_root, "onnx", "onnx", onnx_content
    )
    adapter = LocalSymbolOnnxAdapter(
        onnx_path,
        expected_sha256=onnx_checksum,
        class_codes=data.class_codes,
        input_size=training_config.input_size,
    )
    parity_samples = tuple((*data.validation, *data.test, *data.regression))[
        : gate.parity_sample_limit
    ]
    if not parity_samples:
        raise SymbolCandidateGateError(
            "SYMBOL_CANDIDATE_PARITY_SPLIT_EMPTY", "No held-out parity samples are available."
        )
    parity_images = _sample_batch(parity_samples, training_config.input_size)
    with torch.inference_mode():
        torch_logits = model(torch.from_numpy(parity_images)).numpy()
    onnx_logits = adapter.infer(parity_images).logits
    maximum_error = float(np.max(np.abs(torch_logits - onnx_logits)))
    top_one_equal = bool(
        np.array_equal(np.argmax(torch_logits, axis=1), np.argmax(onnx_logits, axis=1))
    )
    stage("calibration")
    validation_logits, validation_labels = _infer(
        adapter,
        data.validation,
        batch_size=gate.inference_batch_size,
        heartbeat=heartbeat,
    )
    temperature = fit_temperature(validation_logits, validation_labels)
    calibration = {
        "after": calibration_metrics(
            calibrated_probabilities(validation_logits, temperature),
            validation_labels,
            data.class_codes,
        ),
        "before": calibration_metrics(
            calibrated_probabilities(validation_logits, 1.0),
            validation_labels,
            data.class_codes,
        ),
        "temperature": round(temperature, 8),
        "version": CALIBRATION_VERSION,
    }
    stage("evaluation")
    candidate_metrics: dict[str, object] = {}
    baseline_metrics: dict[str, object] | None = None
    rejection_reasons: list[str] = []
    for label, samples in (("test", data.test), ("regression", data.regression)):
        logits, labels = _infer(
            adapter,
            samples,
            batch_size=gate.inference_batch_size,
            heartbeat=heartbeat,
        )
        current = _quality_metrics(logits, labels, data.class_codes, temperature)
        candidate_metrics[label] = current
        previous: dict[str, object] | None = None
        if baseline is not None:
            if baseline.adapter.class_codes != data.class_codes:
                raise SymbolCandidateGateError(
                    "SYMBOL_CANDIDATE_BASELINE_CLASS_DRIFT",
                    "Active baseline class order differs from the candidate.",
                )
            baseline_logits, baseline_labels = _infer(
                baseline.adapter,
                samples,
                batch_size=gate.inference_batch_size,
                heartbeat=heartbeat,
            )
            if not np.array_equal(labels, baseline_labels):
                raise SymbolCandidateGateError(
                    "SYMBOL_CANDIDATE_BASELINE_SPLIT_DRIFT",
                    "Candidate and baseline were not evaluated on identical samples.",
                )
            previous = _quality_metrics(
                baseline_logits, baseline_labels, data.class_codes, baseline.temperature
            )
            if baseline_metrics is None:
                baseline_metrics = {"iterationId": baseline.iteration_id}
            baseline_metrics[label] = previous
        rejection_reasons.extend(_regression_reasons(current, previous, gate, label))
    if maximum_error > gate.maximum_parity_absolute_error or not top_one_equal:
        rejection_reasons.append("ONNX_PARITY_FAILED")
    timings: list[float] = []
    adapter.infer(parity_images)
    for _ in range(gate.performance_repetitions):
        started = time.perf_counter()
        adapter.infer(parity_images)
        timings.append((time.perf_counter() - started) * 1000 / len(parity_samples))
    report: dict[str, object] = {
        "baseline": baseline_metrics or {"status": "baseline_unavailable"},
        "calibration": calibration,
        "candidate": candidate_metrics,
        "classCodes": list(data.class_codes),
        "datasetManifestSha256": data.dataset_sha256,
        "gateConfiguration": gate_payload,
        "gateConfigurationFingerprint": gate.fingerprint,
        "gateVersion": GATE_VERSION,
        "onnxParity": {
            "maximumAbsoluteError": round(maximum_error, 10),
            "sampleCount": len(parity_samples),
            "topOneEqual": top_one_equal,
        },
        "performance": {
            "cpuProvider": "CPUExecutionProvider",
            "medianMillisecondsPerSample": round(statistics.median(timings), 6),
            "repetitions": gate.performance_repetitions,
            "sampleCountPerRepetition": len(parity_samples),
        },
        "rejectionReasons": sorted(set(rejection_reasons)),
        "status": "candidate_ready" if not rejection_reasons else "rejected",
    }
    stage("manifest")
    report_path, report_checksum = _write_content_addressed(
        candidate_root, "reports", "json", _json_bytes(report)
    )
    classes_path, classes_checksum = _write_content_addressed(
        candidate_root,
        "classes",
        "json",
        _json_bytes({"classCodes": list(data.class_codes), "classIds": list(data.class_ids)}),
    )
    calibration_path, calibration_checksum = _write_content_addressed(
        candidate_root, "calibration", "json", _json_bytes(calibration)
    )

    def artifact(path: Path, checksum: str) -> dict[str, object]:
        return {
            "relativePath": path.relative_to(artifact_root).as_posix(),
            "sha256": checksum,
        }

    manifest = {
        "artifacts": {
            "calibration": artifact(calibration_path, calibration_checksum),
            "checkpoint": artifact(checkpoint_path, checkpoint_checksum),
            "classes": artifact(classes_path, classes_checksum),
            "onnx": artifact(onnx_path, onnx_checksum),
            "report": artifact(report_path, report_checksum),
        },
        "classCodes": list(data.class_codes),
        "datasetManifestSha256": data.dataset_sha256,
        "gateConfigurationFingerprint": gate.fingerprint,
        "manifestVersion": ARTIFACT_MANIFEST_VERSION,
        "status": report["status"],
    }
    manifest_path, manifest_checksum = _write_content_addressed(
        candidate_root, "manifests", "json", _json_bytes(manifest)
    )
    return SymbolCandidateGateResult(
        passed=not rejection_reasons,
        rejection_reasons=tuple(sorted(set(rejection_reasons))),
        configuration_fingerprint=gate.fingerprint,
        configuration_payload=gate_payload,
        manifest_checksum_sha256=manifest_checksum,
        manifest_relative_path=manifest_path.relative_to(artifact_root).as_posix(),
        report_checksum_sha256=report_checksum,
        report_relative_path=report_path.relative_to(artifact_root).as_posix(),
        onnx_checksum_sha256=onnx_checksum,
        onnx_relative_path=onnx_path.relative_to(artifact_root).as_posix(),
        metrics=report,
    )


__all__ = [
    "ARTIFACT_MANIFEST_VERSION",
    "GATE_VERSION",
    "SymbolCandidateGateConfiguration",
    "SymbolCandidateGateError",
    "SymbolCandidateGateResult",
    "SymbolModelBaseline",
    "build_symbol_candidate",
]
