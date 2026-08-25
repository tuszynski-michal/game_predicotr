"""Deterministic training and strict comparison for the verified v19 cohort."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

import numpy as np
import torch
from numpy.typing import NDArray

from game_predictor_worker.images.board_cell_geometry_contract import canonical_json_bytes
from game_predictor_worker.images.symbol_classifier import (
    ClassifierSample,
    PreparedTrainingData,
    TrainingConfig,
    TrainingOutcome,
    load_image_tensor,
)
from game_predictor_worker.images.symbol_confidence import (
    TEMPERATURE_MAXIMUM,
    TEMPERATURE_MINIMUM,
    calibrated_probabilities,
)
from game_predictor_worker.images.symbol_model_benchmark import (
    SPATIAL_VARIANT,
    train_validation_candidate,
)
from game_predictor_worker.images.symbol_onnx import LocalSymbolOnnxAdapter
from game_predictor_worker.images.v19_symbol_residuals import (
    COHORT_VERSION,
    PREPROCESSING_VERSION,
)
from game_predictor_worker.symbols.candidate_gate import (
    SymbolCandidateGateConfiguration,
    SymbolCandidateGateResult,
    SymbolModelBaseline,
    build_symbol_candidate,
)

V19_CANDIDATE_WORKFLOW_VERSION = "v19-symbol-model-candidate-v1"
V19_DATASET_VERSION = "verified-v19-symbol-training-dataset-v1"
V19_GATE_VERSION = "verified-v19-symbol-candidate-gate-v1"
V19_AUDIT_BOARD_LIMIT = 100
V19_HIGH_CONFIDENCE_THRESHOLD = 0.99
V19_MINIMUM_SYMBOL_ACCURACY_IMPROVEMENT = 0.01
V19_MINIMUM_WHOLE_BOARD_ACCURACY_IMPROVEMENT = 0.02
V19_MAXIMUM_CLASS_RECALL_REGRESSION = 0.01


class V19SymbolCandidateError(ValueError):
    """Stable fail-closed error for a v19 candidate input or decision."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class V19SampleIdentity:
    board_id: str
    sequence_number: int
    cell_index: int
    source_family: str
    staging_label: str


@dataclass(frozen=True, slots=True)
class V19CandidateDataset:
    prepared: PreparedTrainingData
    identities: Mapping[str, V19SampleIdentity]
    cohort_checksum_sha256: str
    manifest: Mapping[str, object]
    board_count: int
    crop_count: int
    source_family_count: int
    staging_count: int


@dataclass(frozen=True, slots=True)
class V19CandidateRun:
    base_candidate: SymbolCandidateGateResult
    decision: Mapping[str, object]
    decision_checksum_sha256: str
    decision_relative_path: str
    checkpoint_checksum_sha256: str
    checkpoint_relative_path: str


def _error(code: str, message: str) -> V19SymbolCandidateError:
    return V19SymbolCandidateError(code, message)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise _error("V19_CANDIDATE_CONTRACT_INVALID", f"{label} must be an object.")
    return cast(Mapping[str, object], value)


def _rows(value: object, label: str) -> Sequence[Mapping[str, object]]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise _error("V19_CANDIDATE_CONTRACT_INVALID", f"{label} must be an array.")
    return tuple(_mapping(row, label) for row in value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise _error("V19_CANDIDATE_CONTRACT_INVALID", f"{label} must be non-empty text.")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _error("V19_CANDIDATE_CONTRACT_INVALID", f"{label} must be an integer.")
    return value


def _sha256(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64:
        raise _error("V19_CANDIDATE_CONTRACT_INVALID", f"{label} must be SHA-256.")
    try:
        int(text, 16)
    except ValueError as error:
        raise _error("V19_CANDIDATE_CONTRACT_INVALID", f"{label} must be SHA-256.") from error
    if text != text.lower():
        raise _error("V19_CANDIDATE_CONTRACT_INVALID", f"{label} must be lowercase SHA-256.")
    return text


def _read_json(path: Path, expected_checksum: str, label: str) -> Mapping[str, object]:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise _error("V19_CANDIDATE_INPUT_MISSING", f"Cannot read {label}.") from error
    if hashlib.sha256(content).hexdigest() != expected_checksum:
        raise _error("V19_CANDIDATE_INPUT_DRIFT", f"The pinned {label} checksum changed.")
    try:
        value: Any = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _error(
            "V19_CANDIDATE_INPUT_INVALID", f"The pinned {label} is invalid JSON."
        ) from error
    return _mapping(value, label)


def _asset_path(root: Path, relative_value: object, checksum: str) -> Path:
    relative_text = _text(relative_value, "cropRelativePath")
    relative = PurePosixPath(relative_text)
    if (
        relative.is_absolute()
        or "\\" in relative_text
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise _error("V19_CANDIDATE_CROP_PATH_UNSAFE", "A v19 crop path is unsafe.")
    managed_root = root.resolve()
    candidate = managed_root.joinpath(*relative.parts)
    if candidate.is_symlink():
        raise _error("V19_CANDIDATE_CROP_PATH_UNSAFE", "A v19 crop cannot be a symlink.")
    try:
        resolved = candidate.resolve(strict=True)
        content = resolved.read_bytes()
    except OSError as error:
        raise _error("V19_CANDIDATE_CROP_MISSING", "A pinned v19 crop is unavailable.") from error
    if not resolved.is_relative_to(managed_root) or not resolved.is_file():
        raise _error("V19_CANDIDATE_CROP_PATH_UNSAFE", "A v19 crop escapes its artifact root.")
    if hashlib.sha256(content).hexdigest() != checksum:
        raise _error("V19_CANDIDATE_CROP_DRIFT", "A pinned v19 crop checksum changed.")
    return resolved


def load_v19_candidate_dataset(
    *,
    cohort_path: Path,
    expected_cohort_checksum_sha256: str,
    crop_root: Path,
    class_ids_by_code: Mapping[str, str],
) -> V19CandidateDataset:
    """Validate the frozen v19 cohort and expose its exact source-disjoint split."""

    expected = _sha256(expected_cohort_checksum_sha256, "cohort checksum")
    cohort = _read_json(cohort_path, expected, "v19 cohort")
    scope = _mapping(cohort.get("scope"), "scope")
    split = _mapping(cohort.get("split"), "split")
    if (
        cohort.get("version") != COHORT_VERSION
        or cohort.get("preprocessingVersion") != PREPROCESSING_VERSION
        or split.get("policyVersion") != "source-family-balanced-split-v2"
    ):
        raise _error(
            "V19_CANDIDATE_COHORT_UNSUPPORTED",
            "The cohort, preprocessing or split policy is not the verified v19 contract.",
        )
    boards = _rows(cohort.get("boards"), "boards")
    board_count = _integer(scope.get("boardCount"), "scope.boardCount")
    source_count = _integer(scope.get("sourceFamilyCount"), "scope.sourceFamilyCount")
    staging_count = _integer(scope.get("stagingCount"), "scope.stagingCount")
    if board_count != len(boards) or board_count < 300 or staging_count < 6:
        raise _error(
            "V19_CANDIDATE_COHORT_INSUFFICIENT",
            "The candidate requires at least 300 verified boards from six stagings.",
        )
    raw_assignments = _mapping(split.get("assignments"), "split.assignments")
    assignments = {str(source): str(name) for source, name in raw_assignments.items()}
    allowed_splits = {"train", "validation", "test", "regression"}
    if set(assignments.values()) != allowed_splits or len(assignments) != source_count:
        raise _error("V19_CANDIDATE_SPLIT_INVALID", "The pinned source split is incomplete.")
    split_source_counts = Counter(assignments.values())
    if split_source_counts != Counter({"train": 38, "validation": 1, "test": 1, "regression": 1}):
        raise _error(
            "V19_CANDIDATE_SPLIT_INVALID",
            "The v19 candidate requires the frozen 38/1/1/1 source-family split.",
        )
    class_codes = tuple(sorted(class_ids_by_code))
    if len(class_codes) < 2 or any(not class_ids_by_code[code] for code in class_codes):
        raise _error("V19_CANDIDATE_CATALOG_INVALID", "The active symbol catalog is invalid.")
    class_indexes = {code: index for index, code in enumerate(class_codes)}
    samples: dict[str, list[ClassifierSample]] = {name: [] for name in allowed_splits}
    identities: dict[str, V19SampleIdentity] = {}
    board_ids: set[str] = set()
    sequences: set[int] = set()
    observed_sources: set[str] = set()
    observed_stagings: set[str] = set()
    crop_labels: dict[str, str] = {}
    for board in boards:
        board_id = _text(board.get("boardId"), "boardId")
        sequence_number = _integer(board.get("sequenceNumber"), "sequenceNumber")
        source = _mapping(board.get("source"), "source")
        source_family = _sha256(source.get("checksumSha256"), "source checksum")
        staging_label = _text(board.get("stagingLabel"), "stagingLabel")
        split_name = _text(board.get("split"), "split")
        if (
            board.get("decisionStatus") not in {"accepted", "corrected"}
            or board_id in board_ids
            or sequence_number in sequences
            or split_name not in allowed_splits
            or assignments.get(source_family) != split_name
        ):
            raise _error(
                "V19_CANDIDATE_BOARD_INVALID",
                "A board is unresolved, duplicated or assigned to another source split.",
            )
        board_ids.add(board_id)
        sequences.add(sequence_number)
        observed_sources.add(source_family)
        observed_stagings.add(staging_label)
        cells = _rows(board.get("cells"), "cells")
        if [cell.get("cellIndex") for cell in cells] != list(range(15)):
            raise _error(
                "V19_CANDIDATE_BOARD_INCOMPLETE",
                "Every v19 board must contain exactly 15 row-major cells.",
            )
        for cell in cells:
            cell_index = _integer(cell.get("cellIndex"), "cellIndex")
            symbol_code = _text(cell.get("symbolCode"), "symbolCode")
            if symbol_code not in class_indexes:
                raise _error(
                    "V19_CANDIDATE_SYMBOL_UNKNOWN",
                    "A verified v19 label is absent from the active catalog.",
                )
            checksum = _sha256(cell.get("cropChecksumSha256"), "crop checksum")
            prior_label = crop_labels.setdefault(checksum, symbol_code)
            if prior_label != symbol_code:
                raise _error(
                    "V19_CANDIDATE_LABEL_CONFLICT",
                    "Identical v19 crop bytes have conflicting labels.",
                )
            sample_id = _sha256(cell.get("cropSampleId"), "cropSampleId")
            if sample_id in identities:
                raise _error("V19_CANDIDATE_SAMPLE_DUPLICATE", "A v19 sample occurs twice.")
            path = _asset_path(crop_root, cell.get("cropRelativePath"), checksum)
            samples[split_name].append(
                ClassifierSample(
                    sample_id=sample_id,
                    asset_path=path,
                    asset_checksum=checksum,
                    source_image_checksum=source_family,
                    symbol_code=symbol_code,
                    class_index=class_indexes[symbol_code],
                )
            )
            identities[sample_id] = V19SampleIdentity(
                board_id=board_id,
                sequence_number=sequence_number,
                cell_index=cell_index,
                source_family=source_family,
                staging_label=staging_label,
            )
    if observed_sources != set(assignments) or len(observed_stagings) != staging_count:
        raise _error(
            "V19_CANDIDATE_SCOPE_DRIFT",
            "The v19 boards no longer match the pinned source or staging scope.",
        )
    crop_count = sum(len(values) for values in samples.values())
    if crop_count != board_count * 15 or crop_count != _integer(
        cohort.get("cropCount"), "cropCount"
    ):
        raise _error("V19_CANDIDATE_CROP_COUNT_INVALID", "The v19 crop count is incomplete.")
    for name, values in samples.items():
        if not values:
            raise _error("V19_CANDIDATE_SPLIT_EMPTY", f"The {name} split is empty.")
    class_ids = tuple(class_ids_by_code[code] for code in class_codes)
    split_checksum = hashlib.sha256(canonical_json_bytes(split)).hexdigest()
    prepared = PreparedTrainingData(
        dataset_sha256=hashlib.sha256(
            canonical_json_bytes(
                {
                    "cohortChecksumSha256": expected,
                    "datasetVersion": V19_DATASET_VERSION,
                    "preprocessingVersion": PREPROCESSING_VERSION,
                    "splitChecksumSha256": split_checksum,
                }
            )
        ).hexdigest(),
        split_sha256=split_checksum,
        split_seed=_text(split.get("seed"), "split.seed"),
        class_codes=class_codes,
        class_ids=class_ids,
        train=tuple(samples["train"]),
        validation=tuple(samples["validation"]),
        test=tuple(samples["test"]),
        regression=tuple(samples["regression"]),
    )
    return V19CandidateDataset(
        prepared=prepared,
        identities=identities,
        cohort_checksum_sha256=expected,
        manifest=cohort,
        board_count=board_count,
        crop_count=crop_count,
        source_family_count=source_count,
        staging_count=staging_count,
    )


def _write_checkpoint(
    root: Path,
    *,
    outcome: TrainingOutcome,
    data: PreparedTrainingData,
    config: TrainingConfig,
) -> tuple[Path, str]:
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "architectureVersion": "spatial-symbol-cnn-v1",
        "bestEpoch": outcome.best_epoch,
        "bestState": outcome.state_dict,
        "classCodes": data.class_codes,
        "config": asdict(config),
        "datasetSha256": data.dataset_sha256,
        "history": outcome.history,
        "modelState": outcome.state_dict,
        "splitSha256": data.split_sha256,
        "trainingOrigin": "random_initialization",
        "workflowVersion": V19_CANDIDATE_WORKFLOW_VERSION,
    }
    with tempfile.NamedTemporaryFile(dir=root, prefix=".tmp-", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with temporary.open("wb") as writer:
            torch.save(payload, writer)
            writer.flush()
            os.fsync(writer.fileno())
        content = temporary.read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        destination = root / f"spatial-symbol-cnn-v19-{checksum}.pt"
        if destination.exists() and destination.read_bytes() != content:
            raise _error("V19_CANDIDATE_ARTIFACT_CONFLICT", "Checkpoint checksum collided.")
        if not destination.exists():
            os.replace(temporary, destination)
        return destination, checksum
    finally:
        temporary.unlink(missing_ok=True)


def _infer(
    adapter: LocalSymbolOnnxAdapter,
    samples: Sequence[ClassifierSample],
    *,
    batch_size: int = 64,
) -> tuple[NDArray[np.float32], NDArray[np.int64]]:
    logits: list[NDArray[np.float32]] = []
    labels: list[int] = []
    for start in range(0, len(samples), batch_size):
        batch = samples[start : start + batch_size]
        tensors = np.stack(
            [load_image_tensor(sample.asset_path, adapter.input_size).numpy() for sample in batch]
        ).astype(np.float32, copy=False)
        logits.append(adapter.infer(tensors).logits)
        labels.extend(sample.class_index for sample in batch)
    if not logits:
        raise _error("V19_CANDIDATE_SPLIT_EMPTY", "Candidate comparison split is empty.")
    return np.concatenate(logits), np.asarray(labels, dtype=np.int64)


def _comparison_metrics(
    *,
    adapter: LocalSymbolOnnxAdapter,
    temperature: float,
    samples: Sequence[ClassifierSample],
    identities: Mapping[str, V19SampleIdentity],
    class_codes: Sequence[str],
) -> dict[str, object]:
    logits, labels = _infer(adapter, samples)
    probabilities = calibrated_probabilities(logits, temperature)
    predictions = np.argmax(probabilities, axis=1)
    confusion: NDArray[np.int64] = np.zeros((len(class_codes), len(class_codes)), dtype=np.int64)
    board_results: dict[str, list[bool]] = {}
    for sample, expected, predicted in zip(samples, labels, predictions, strict=True):
        confusion[int(expected), int(predicted)] += 1
        identity = identities[sample.sample_id]
        board_results.setdefault(identity.board_id, []).append(int(expected) == int(predicted))
    correct = int(np.count_nonzero(predictions == labels))
    per_class = []
    for index, code in enumerate(class_codes):
        support = int(confusion[index].sum())
        recall = float(confusion[index, index] / support) if support else 0.0
        per_class.append({"recall": round(recall, 8), "support": support, "symbolCode": code})
    return {
        "accuracy": round(correct / len(samples), 8),
        "boardCount": len(board_results),
        "cellCount": len(samples),
        "correctCount": correct,
        "perClass": per_class,
        "wholeBoardAccuracy": round(
            sum(all(values) for values in board_results.values()) / len(board_results), 8
        ),
    }


def _audit_samples(
    dataset: V19CandidateDataset,
    *,
    board_limit: int = V19_AUDIT_BOARD_LIMIT,
) -> tuple[ClassifierSample, ...]:
    all_samples = tuple(
        (
            *dataset.prepared.train,
            *dataset.prepared.validation,
            *dataset.prepared.test,
            *dataset.prepared.regression,
        )
    )
    board_ids = sorted(
        {dataset.identities[sample.sample_id].board_id for sample in all_samples},
        key=lambda board_id: hashlib.sha256(
            f"{dataset.cohort_checksum_sha256}\0{board_id}".encode()
        ).hexdigest(),
    )[:board_limit]
    selected = set(board_ids)
    return tuple(
        sample
        for sample in all_samples
        if dataset.identities[sample.sample_id].board_id in selected
    )


def _high_confidence_errors(
    *,
    adapter: LocalSymbolOnnxAdapter,
    temperature: float,
    samples: Sequence[ClassifierSample],
    identities: Mapping[str, V19SampleIdentity],
    class_codes: Sequence[str],
) -> list[dict[str, object]]:
    logits, labels = _infer(adapter, samples)
    probabilities = calibrated_probabilities(logits, temperature)
    predictions = np.argmax(probabilities, axis=1)
    confidence = np.max(probabilities, axis=1)
    rows = []
    for sample, expected, predicted, score in zip(
        samples, labels, predictions, confidence, strict=True
    ):
        if expected == predicted or float(score) < V19_HIGH_CONFIDENCE_THRESHOLD:
            continue
        identity = identities[sample.sample_id]
        rows.append(
            {
                "boardId": identity.board_id,
                "cellIndex": identity.cell_index,
                "confidence": round(float(score), 8),
                "expectedSymbolCode": class_codes[int(expected)],
                "predictedSymbolCode": class_codes[int(predicted)],
                "sampleId": sample.sample_id,
                "sequenceNumber": identity.sequence_number,
                "stagingLabel": identity.staging_label,
            }
        )
    return sorted(
        rows, key=lambda row: (cast(int, row["sequenceNumber"]), cast(int, row["cellIndex"]))
    )


def _write_json_artifact(root: Path, directory: str, value: object) -> tuple[Path, str]:
    content = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    checksum = hashlib.sha256(content).hexdigest()
    destination = root / directory / f"{checksum}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != content:
            raise _error("V19_CANDIDATE_ARTIFACT_CONFLICT", "Decision checksum collided.")
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


def train_v19_symbol_candidate(
    *,
    artifact_root: Path,
    candidate_root: Path,
    dataset: V19CandidateDataset,
    baseline: SymbolModelBaseline,
    baseline_fingerprint_sha256: str,
    config: TrainingConfig | None = None,
    progress: Callable[[str], None] = lambda _message: None,
) -> V19CandidateRun:
    """Train from scratch, export ONNX and apply the strict v19 comparison gate."""

    resolved_config = config or TrainingConfig()
    resolved_config.validate()
    if baseline.adapter.class_codes != dataset.prepared.class_codes:
        raise _error(
            "V19_CANDIDATE_BASELINE_CLASS_DRIFT",
            "The active baseline and v19 dataset have another class order.",
        )
    progress("training")
    outcome = train_validation_candidate(dataset.prepared, resolved_config, SPATIAL_VARIANT)
    checkpoint, checkpoint_checksum = _write_checkpoint(
        candidate_root / "checkpoints",
        outcome=outcome,
        data=dataset.prepared,
        config=resolved_config,
    )
    progress("onnx_and_candidate_gate")
    base = build_symbol_candidate(
        artifact_root=artifact_root,
        candidate_root=candidate_root / "candidate",
        checkpoint_path=checkpoint,
        checkpoint_checksum=checkpoint_checksum,
        data=dataset.prepared,
        training_config=resolved_config,
        configuration=SymbolCandidateGateConfiguration(
            minimum_accuracy=0.0,
            minimum_macro_recall=0.0,
            maximum_accuracy_regression=0.0,
            maximum_per_symbol_recall_regression=V19_MAXIMUM_CLASS_RECALL_REGRESSION,
        ),
        baseline=baseline,
    )
    manifest_path = artifact_root.joinpath(*PurePosixPath(base.manifest_relative_path).parts)
    manifest = _read_json(manifest_path, base.manifest_checksum_sha256, "candidate manifest")
    artifacts = _mapping(manifest.get("artifacts"), "candidate artifacts")
    calibration_row = _mapping(artifacts.get("calibration"), "calibration artifact")
    calibration_path = artifact_root.joinpath(
        *PurePosixPath(_text(calibration_row.get("relativePath"), "calibration path")).parts
    )
    calibration = _read_json(
        calibration_path,
        _sha256(calibration_row.get("sha256"), "calibration checksum"),
        "candidate calibration",
    )
    temperature_value = calibration.get("temperature")
    if isinstance(temperature_value, bool) or not isinstance(temperature_value, int | float):
        raise _error("V19_CANDIDATE_CALIBRATION_INVALID", "Candidate temperature is invalid.")
    temperature = float(temperature_value)
    candidate_adapter = LocalSymbolOnnxAdapter(
        artifact_root.joinpath(*PurePosixPath(base.onnx_relative_path).parts),
        expected_sha256=base.onnx_checksum_sha256,
        class_codes=dataset.prepared.class_codes,
        input_size=resolved_config.input_size,
    )
    held_out = tuple((*dataset.prepared.test, *dataset.prepared.regression))
    candidate_metrics = _comparison_metrics(
        adapter=candidate_adapter,
        temperature=temperature,
        samples=held_out,
        identities=dataset.identities,
        class_codes=dataset.prepared.class_codes,
    )
    baseline_metrics = _comparison_metrics(
        adapter=baseline.adapter,
        temperature=baseline.temperature,
        samples=held_out,
        identities=dataset.identities,
        class_codes=dataset.prepared.class_codes,
    )
    symbol_improvement = float(cast(float, candidate_metrics["accuracy"])) - float(
        cast(float, baseline_metrics["accuracy"])
    )
    board_improvement = float(cast(float, candidate_metrics["wholeBoardAccuracy"])) - float(
        cast(float, baseline_metrics["wholeBoardAccuracy"])
    )
    baseline_recall = {
        str(row["symbolCode"]): float(cast(float, row["recall"]))
        for row in cast(Sequence[Mapping[str, object]], baseline_metrics["perClass"])
    }
    recall_regressions = []
    for row in cast(Sequence[Mapping[str, object]], candidate_metrics["perClass"]):
        code = str(row["symbolCode"])
        delta = float(cast(float, row["recall"])) - baseline_recall[code]
        if delta < -V19_MAXIMUM_CLASS_RECALL_REGRESSION:
            recall_regressions.append({"delta": round(delta, 8), "symbolCode": code})
    audit = _audit_samples(dataset)
    high_confidence_errors = _high_confidence_errors(
        adapter=candidate_adapter,
        temperature=temperature,
        samples=audit,
        identities=dataset.identities,
        class_codes=dataset.prepared.class_codes,
    )
    audit_board_count = len({dataset.identities[sample.sample_id].board_id for sample in audit})
    rejection_reasons = list(base.rejection_reasons)
    if not (
        symbol_improvement >= V19_MINIMUM_SYMBOL_ACCURACY_IMPROVEMENT
        or board_improvement >= V19_MINIMUM_WHOLE_BOARD_ACCURACY_IMPROVEMENT
    ):
        rejection_reasons.append("V19_CANDIDATE_IMPROVEMENT_BELOW_MINIMUM")
    if recall_regressions:
        rejection_reasons.append("V19_CANDIDATE_CLASS_RECALL_REGRESSION")
    if high_confidence_errors:
        rejection_reasons.append("V19_CANDIDATE_HIGH_CONFIDENCE_AUDIT_FAILED")
    if audit_board_count != V19_AUDIT_BOARD_LIMIT:
        rejection_reasons.append("V19_CANDIDATE_AUDIT_INCOMPLETE")
    if not TEMPERATURE_MINIMUM <= temperature <= TEMPERATURE_MAXIMUM or not math.isfinite(
        temperature
    ):
        rejection_reasons.append("V19_CANDIDATE_CALIBRATION_UNSAFE")
    rejection_reasons = sorted(set(rejection_reasons))
    status = "candidate_ready" if not rejection_reasons else "rejected"
    decision: dict[str, object] = {
        "activeModelFingerprintSha256": baseline_fingerprint_sha256,
        "audit": {
            "boardCount": audit_board_count,
            "cellCount": len(audit),
            "highConfidenceErrorCount": len(high_confidence_errors),
            "highConfidenceErrors": high_confidence_errors,
            "selection": "sha256(cohortChecksum, boardId), first 100",
            "threshold": V19_HIGH_CONFIDENCE_THRESHOLD,
        },
        "baseCandidateManifestChecksumSha256": base.manifest_checksum_sha256,
        "baseCandidateReportChecksumSha256": base.report_checksum_sha256,
        "baseline": baseline_metrics,
        "candidate": candidate_metrics,
        "cohortChecksumSha256": dataset.cohort_checksum_sha256,
        "comparison": {
            "maximumClassRecallRegression": V19_MAXIMUM_CLASS_RECALL_REGRESSION,
            "minimumSymbolAccuracyImprovement": V19_MINIMUM_SYMBOL_ACCURACY_IMPROVEMENT,
            "minimumWholeBoardAccuracyImprovement": V19_MINIMUM_WHOLE_BOARD_ACCURACY_IMPROVEMENT,
            "observedSymbolAccuracyImprovement": round(symbol_improvement, 8),
            "observedWholeBoardAccuracyImprovement": round(board_improvement, 8),
            "recallRegressions": recall_regressions,
        },
        "dataset": {
            "boardCount": dataset.board_count,
            "cropCount": dataset.crop_count,
            "datasetSha256": dataset.prepared.dataset_sha256,
            "preprocessingVersion": PREPROCESSING_VERSION,
            "sourceFamilyCount": dataset.source_family_count,
            "splitSha256": dataset.prepared.split_sha256,
            "splitSourceFamilyCounts": {
                "regression": len(
                    {sample.source_image_checksum for sample in dataset.prepared.regression}
                ),
                "test": len({sample.source_image_checksum for sample in dataset.prepared.test}),
                "train": len({sample.source_image_checksum for sample in dataset.prepared.train}),
                "validation": len(
                    {sample.source_image_checksum for sample in dataset.prepared.validation}
                ),
            },
            "stagingCount": dataset.staging_count,
            "version": V19_DATASET_VERSION,
        },
        "gateVersion": V19_GATE_VERSION,
        "onnxParity": base.metrics.get("onnxParity"),
        "rejectionReasons": rejection_reasons,
        "safeCalibration": {
            "maximumTemperature": TEMPERATURE_MAXIMUM,
            "minimumTemperature": TEMPERATURE_MINIMUM,
            "temperature": temperature,
        },
        "schemaVersion": 1,
        "status": status,
        "training": {
            "bestEpoch": outcome.best_epoch,
            "configuration": asdict(resolved_config),
            "origin": "random_initialization",
            "workflowVersion": V19_CANDIDATE_WORKFLOW_VERSION,
        },
    }
    decision_path, decision_checksum = _write_json_artifact(candidate_root, "decisions", decision)
    progress(status)
    return V19CandidateRun(
        base_candidate=base,
        decision=decision,
        decision_checksum_sha256=decision_checksum,
        decision_relative_path=decision_path.relative_to(artifact_root).as_posix(),
        checkpoint_checksum_sha256=checkpoint_checksum,
        checkpoint_relative_path=checkpoint.relative_to(artifact_root).as_posix(),
    )


__all__ = [
    "V19_AUDIT_BOARD_LIMIT",
    "V19_CANDIDATE_WORKFLOW_VERSION",
    "V19_DATASET_VERSION",
    "V19_GATE_VERSION",
    "V19CandidateDataset",
    "V19CandidateRun",
    "V19SampleIdentity",
    "V19SymbolCandidateError",
    "load_v19_candidate_dataset",
    "train_v19_symbol_candidate",
]
