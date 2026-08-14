"""Calibrate M6 symbol confidence and select the next whole-layout review batch."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
import torch
from numpy.typing import NDArray

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "worker" / "src"))

from game_predictor_worker.images.symbol_classifier import (  # noqa: E402
    ClassifierSample,
    SymbolClassifierError,
    load_image_tensor,
    prepare_training_data,
)
from game_predictor_worker.images.symbol_confidence import (  # noqa: E402
    ACTIVE_LEARNING_VERSION,
    AUTO_ACCEPT_MINIMUM_CLASS_PRECISION,
    AUTO_ACCEPT_MINIMUM_CLASS_SAMPLES,
    AUTO_ACCEPT_MINIMUM_SAMPLES,
    AUTO_ACCEPT_TARGET_PRECISION,
    CALIBRATION_VERSION,
    DEFAULT_ACTIVE_LEARNING_BATCH_SIZE,
    ActiveLearningBoard,
    ActiveLearningCell,
    SymbolConfidenceError,
    build_confidence_policy,
    calibrated_probabilities,
    calibration_metrics,
    fit_temperature,
    select_active_learning_boards,
    threshold_evidence,
)
from game_predictor_worker.images.symbol_dataset import (  # noqa: E402
    SymbolCropInventory,
    SymbolCropSample,
    SymbolDatasetError,
    load_symbol_crop_inventory,
)
from game_predictor_worker.images.symbol_onnx import (  # noqa: E402
    LocalSymbolOnnxAdapter,
    SymbolOnnxError,
    tensor_batch_to_numpy,
)

QUALITY = ROOT / "ai_docs" / "quality"
DEFAULT_DATASET = QUALITY / "m6-symbol-dataset-export-report.json"
DEFAULT_SPLIT = QUALITY / "m6-symbol-dataset-split-report.json"
DEFAULT_DATASET_ASSETS = ROOT / "artifacts" / "m6-symbol-dataset-v1"
DEFAULT_INVENTORY = QUALITY / "m6-symbol-crop-inventory-v3.json"
DEFAULT_CROP_ROOT = ROOT / "artifacts" / "m5-reviewed-manual-merge-v16-full-preflight"
DEFAULT_ONNX_REPORT = QUALITY / "m6-symbol-classifier-onnx-report.json"
DEFAULT_ONNX_ARTIFACT = (
    ROOT / "artifacts" / "m6-symbol-classifier-onnx" / "bootstrap-symbol-cnn-v1.onnx"
)
DEFAULT_CALIBRATION_REPORT = QUALITY / "m6-symbol-confidence-calibration-report.json"
DEFAULT_SELECTION_REPORT = QUALITY / "m6-symbol-active-learning-selection.json"
INFERENCE_BATCH_SIZE = 64


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--dataset-assets", type=Path, default=DEFAULT_DATASET_ASSETS)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--crop-root", type=Path, default=DEFAULT_CROP_ROOT)
    parser.add_argument("--onnx-report", type=Path, default=DEFAULT_ONNX_REPORT)
    parser.add_argument("--onnx-artifact", type=Path, default=DEFAULT_ONNX_ARTIFACT)
    parser.add_argument("--calibration-report", type=Path, default=DEFAULT_CALIBRATION_REPORT)
    parser.add_argument("--selection-report", type=Path, default=DEFAULT_SELECTION_REPORT)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_ACTIVE_LEARNING_BATCH_SIZE,
    )
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def _json_bytes(value: Mapping[str, object]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SymbolConfidenceError(
            "SYMBOL_CONFIDENCE_PROVENANCE_INVALID",
            f"{label} must be an object.",
        )
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise SymbolConfidenceError(
            "SYMBOL_CONFIDENCE_PROVENANCE_INVALID",
            f"{label} must be an array.",
        )
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise SymbolConfidenceError(
            "SYMBOL_CONFIDENCE_PROVENANCE_INVALID",
            f"{label} must be a non-empty string.",
        )
    return value


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise SymbolConfidenceError(
            "SYMBOL_CONFIDENCE_PROVENANCE_INVALID",
            f"{label} must be an integer.",
        )
    return value


def _number(value: object, label: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise SymbolConfidenceError(
            "SYMBOL_CONFIDENCE_PROVENANCE_INVALID",
            f"{label} must be numeric.",
        )
    return float(value)


def _sha256(value: object, label: str) -> str:
    text = _text(value, label).lower()
    if len(text) != 64:
        raise SymbolConfidenceError(
            "SYMBOL_CONFIDENCE_PROVENANCE_INVALID",
            f"{label} must be a SHA-256 value.",
        )
    try:
        int(text, 16)
    except ValueError as error:
        raise SymbolConfidenceError(
            "SYMBOL_CONFIDENCE_PROVENANCE_INVALID",
            f"{label} must be a SHA-256 value.",
        ) from error
    return text


def _load_json(path: Path) -> tuple[bytes, Mapping[str, object]]:
    try:
        content = path.read_bytes()
        value: Any = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise SymbolConfidenceError(
            "SYMBOL_CONFIDENCE_PROVENANCE_INVALID",
            f"Cannot read {path.name}.",
        ) from error
    return content, _mapping(value, path.name)


def _batches[T](values: Sequence[T], batch_size: int) -> tuple[Sequence[T], ...]:
    return tuple(values[index : index + batch_size] for index in range(0, len(values), batch_size))


def _validate_onnx_provenance(
    report: Mapping[str, object],
    report_bytes: bytes,
    artifact_path: Path,
    *,
    dataset_sha256: str,
    split_sha256: str,
    class_codes: tuple[str, ...],
) -> tuple[str, int, str, str]:
    artifact = _mapping(report.get("artifact"), "onnxReport.artifact")
    expected_artifact_sha256 = _sha256(artifact.get("sha256"), "artifact.sha256")
    try:
        artifact_sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    except OSError as error:
        raise SymbolConfidenceError(
            "SYMBOL_CONFIDENCE_ONNX_MISSING",
            "The immutable ONNX artifact cannot be read.",
        ) from error
    classes = tuple(
        _text(_mapping(row, "class").get("symbolCode"), "class.symbolCode")
        for row in _sequence(report.get("classes"), "onnxReport.classes")
    )
    graph_input = _mapping(
        _mapping(report.get("graph"), "onnxReport.graph").get("input"),
        "onnxReport.graph.input",
    )
    shape = _sequence(graph_input.get("shape"), "onnxReport.graph.input.shape")
    if (
        report.get("status") != "bootstrap"
        or report.get("datasetSha256") != dataset_sha256
        or report.get("splitSha256") != split_sha256
        or classes != class_codes
        or artifact_sha256 != expected_artifact_sha256
        or len(shape) != 4
        or shape[0] != "batch"
        or shape[1] != 3
        or shape[2] != shape[3]
    ):
        raise SymbolConfidenceError(
            "SYMBOL_CONFIDENCE_ONNX_PROVENANCE_DRIFT",
            "ONNX report, artifact, classes or source data differ.",
        )
    return (
        expected_artifact_sha256,
        _integer(shape[2], "onnxReport.graph.input.shape[2]"),
        _text(report.get("modelVersion"), "onnxReport.modelVersion"),
        hashlib.sha256(report_bytes).hexdigest(),
    )


def _infer_classifier_samples(
    adapter: LocalSymbolOnnxAdapter,
    samples: Sequence[ClassifierSample],
) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
    logits: list[NDArray[np.float64]] = []
    labels: list[int] = []
    for batch in _batches(tuple(samples), INFERENCE_BATCH_SIZE):
        tensors = torch.stack(
            [load_image_tensor(sample.asset_path, adapter.input_size) for sample in batch]
        )
        result = adapter.infer(tensor_batch_to_numpy(tensors))
        logits.append(result.logits.astype(np.float64, copy=False))
        labels.extend(sample.class_index for sample in batch)
    return (
        np.concatenate(logits).astype(np.float64, copy=False),
        np.asarray(labels, dtype=np.int64),
    )


def _best_threshold_candidate(
    rows: Sequence[Mapping[str, object]],
) -> Mapping[str, object] | None:
    passing = [row for row in rows if row.get("qualityGatePassed") is True]
    if passing:
        return max(
            passing,
            key=lambda row: (
                _integer(row.get("sampleCount"), "threshold.sampleCount"),
                -_number(row.get("threshold"), "threshold.threshold"),
            ),
        )
    nonempty = [
        row for row in rows if _integer(row.get("sampleCount"), "threshold.sampleCount") > 0
    ]
    return (
        max(
            nonempty,
            key=lambda row: (
                _number(row.get("precision"), "threshold.precision"),
                _integer(row.get("sampleCount"), "threshold.sampleCount"),
                -_number(row.get("threshold"), "threshold.threshold"),
            ),
        )
        if nonempty
        else None
    )


def _threshold_measurement(
    probabilities: NDArray[np.float64],
    labels: NDArray[np.int64],
    threshold: float | None,
) -> dict[str, object] | None:
    if threshold is None:
        return None
    confidence = probabilities.max(axis=1)
    predictions = probabilities.argmax(axis=1)
    accepted = confidence >= threshold
    count = int(accepted.sum())
    correct = int(np.count_nonzero(accepted & (predictions == labels)))
    return {
        "correctCount": correct,
        "coverage": round(count / labels.size, 8),
        "precision": round(correct / count if count else 0.0, 8),
        "sampleCount": count,
        "thresholdSelectedOnValidation": round(threshold, 8),
    }


def _safe_crop_path(root: Path, sample: SymbolCropSample) -> Path:
    relative = PurePosixPath(sample.crop_relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise SymbolConfidenceError(
            "SYMBOL_ACTIVE_LEARNING_CROP_PATH_UNSAFE",
            "A pending crop path escapes the configured artifact root.",
        )
    try:
        root_resolved = root.resolve(strict=True)
        path = root_resolved.joinpath(*relative.parts).resolve(strict=True)
        path.relative_to(root_resolved)
        content = path.read_bytes()
    except (OSError, ValueError) as error:
        raise SymbolConfidenceError(
            "SYMBOL_ACTIVE_LEARNING_CROP_MISSING",
            f"Cannot read pending crop {sample.sample_id}.",
        ) from error
    if hashlib.sha256(content).hexdigest() != sample.crop_checksum_sha256:
        raise SymbolConfidenceError(
            "SYMBOL_ACTIVE_LEARNING_CROP_DRIFT",
            f"Pending crop checksum differs for {sample.sample_id}.",
        )
    return path


def _pending_samples(
    dataset: Mapping[str, object],
    inventory: SymbolCropInventory,
    inventory_bytes: bytes,
) -> tuple[SymbolCropSample, ...]:
    if (
        _sha256(dataset.get("inventorySha256"), "dataset.inventorySha256")
        != hashlib.sha256(inventory_bytes).hexdigest()
    ):
        raise SymbolConfidenceError(
            "SYMBOL_ACTIVE_LEARNING_INVENTORY_DRIFT",
            "The labeled dataset references different inventory bytes.",
        )
    pending_ids = {
        _sha256(value, "pendingSampleId")
        for value in _sequence(dataset.get("pendingSampleIds"), "pendingSampleIds")
    }
    rejected_ids = {
        _sha256(value, "rejectedSampleId")
        for value in _sequence(dataset.get("rejectedSampleIds"), "rejectedSampleIds")
    }
    accepted_ids = {
        _sha256(_mapping(row, "sample").get("sampleId"), "sample.sampleId")
        for row in _sequence(dataset.get("samples"), "dataset.samples")
    }
    inventory_by_id = {sample.sample_id: sample for sample in inventory.samples}
    if (
        len(pending_ids) != dataset.get("pendingCount")
        or len(rejected_ids) != dataset.get("rejectedCount")
        or len(accepted_ids) != dataset.get("sampleCount")
        or pending_ids & accepted_ids
        or pending_ids & rejected_ids
        or accepted_ids & rejected_ids
        or pending_ids | accepted_ids | rejected_ids != set(inventory_by_id)
    ):
        raise SymbolConfidenceError(
            "SYMBOL_ACTIVE_LEARNING_PENDING_SET_DRIFT",
            "Accepted, rejected and pending sample identities are inconsistent.",
        )
    return tuple(
        inventory_by_id[sample_id]
        for sample_id in sorted(
            pending_ids,
            key=lambda value: (
                inventory_by_id[value].sequence_number,
                inventory_by_id[value].cell_index,
                value,
            ),
        )
    )


def _infer_pending_boards(
    adapter: LocalSymbolOnnxAdapter,
    pending: Sequence[SymbolCropSample],
    crop_root: Path,
    temperature: float,
) -> tuple[tuple[ActiveLearningBoard, ...], int]:
    sample_probabilities: dict[str, tuple[float, ...]] = {}
    for batch in _batches(tuple(pending), INFERENCE_BATCH_SIZE):
        paths = [_safe_crop_path(crop_root, sample) for sample in batch]
        tensors = torch.stack([load_image_tensor(path, adapter.input_size) for path in paths])
        result = adapter.infer(tensor_batch_to_numpy(tensors))
        probabilities = calibrated_probabilities(result.logits, temperature)
        for sample, vector in zip(batch, probabilities, strict=True):
            sample_probabilities[sample.sample_id] = tuple(float(value) for value in vector)

    grouped: dict[str, list[SymbolCropSample]] = defaultdict(list)
    for sample in pending:
        if sample.board_id is None:
            raise SymbolConfidenceError(
                "SYMBOL_ACTIVE_LEARNING_BOARD_ID_MISSING",
                "A reviewed inventory sample has no stable board identity.",
            )
        grouped[sample.board_id].append(sample)
    boards: list[ActiveLearningBoard] = []
    partial_count = 0
    for board_id, samples in sorted(
        grouped.items(),
        key=lambda item: (item[1][0].sequence_number, item[0]),
    ):
        ordered = sorted(samples, key=lambda sample: sample.cell_index)
        if len(ordered) != 15:
            partial_count += 1
            continue
        first = ordered[0]
        boards.append(
            ActiveLearningBoard(
                board_id=board_id,
                sequence_number=first.sequence_number,
                source_image_id=first.source_image_id,
                source_image_checksum=first.source_image_checksum_sha256,
                source_group=first.source_group,
                board_relative_path=first.board_relative_path or "",
                cells=tuple(
                    ActiveLearningCell(
                        sample_id=sample.sample_id,
                        cell_index=sample.cell_index,
                        row_index=sample.row_index,
                        column_index=sample.column_index,
                        probabilities=sample_probabilities[sample.sample_id],
                        crop_relative_path=sample.crop_relative_path,
                        observation_id=sample.observation_id or "",
                    )
                    for sample in ordered
                ),
            )
        )
    return tuple(boards), partial_count


def main() -> int:
    args = _args()
    try:
        if args.batch_size <= 0:
            raise SymbolConfidenceError(
                "SYMBOL_ACTIVE_LEARNING_BATCH_INVALID",
                "The active-learning batch size must be positive.",
            )
        data = prepare_training_data(args.dataset, args.split, args.dataset_assets)
        onnx_report_bytes, onnx_report = _load_json(args.onnx_report)
        (
            onnx_artifact_sha256,
            input_size,
            onnx_model_version,
            onnx_report_sha256,
        ) = _validate_onnx_provenance(
            onnx_report,
            onnx_report_bytes,
            args.onnx_artifact,
            dataset_sha256=data.dataset_sha256,
            split_sha256=data.split_sha256,
            class_codes=data.class_codes,
        )
        adapter = LocalSymbolOnnxAdapter(
            args.onnx_artifact,
            expected_sha256=onnx_artifact_sha256,
            class_codes=data.class_codes,
            input_size=input_size,
        )
        validation_logits, validation_labels = _infer_classifier_samples(
            adapter,
            data.validation,
        )
        test_logits, test_labels = _infer_classifier_samples(adapter, data.test)
        temperature = fit_temperature(validation_logits, validation_labels)
        validation_before = calibrated_probabilities(validation_logits, 1.0)
        validation_after = calibrated_probabilities(validation_logits, temperature)
        test_before = calibrated_probabilities(test_logits, 1.0)
        test_after = calibrated_probabilities(test_logits, temperature)
        rows = threshold_evidence(validation_after, validation_labels, data.class_codes)
        _, split_report = _load_json(args.split)
        model_status = _text(onnx_report.get("status"), "onnxReport.status")
        bootstrap_target_met = split_report.get("bootstrapTargetMet") is True
        policy = build_confidence_policy(
            rows,
            model_status=model_status,
            bootstrap_target_met=bootstrap_target_met,
        )
        candidate = _best_threshold_candidate(rows)
        candidate_threshold = (
            _number(candidate.get("threshold"), "threshold.threshold")
            if candidate is not None
            else None
        )
        calibration_report: dict[str, object] = {
            "calibrationVersion": CALIBRATION_VERSION,
            "classes": list(data.class_codes),
            "fitBoundary": {
                "fitSplit": "validation",
                "fitSampleCount": len(data.validation),
                "testMeasuredOnceAfterFit": True,
                "testSampleCount": len(data.test),
                "trainUsedForCalibration": False,
            },
            "inputs": {
                "datasetSha256": data.dataset_sha256,
                "modelVersion": onnx_model_version,
                "onnxArtifactSha256": onnx_artifact_sha256,
                "onnxReportSha256": onnx_report_sha256,
                "splitSha256": data.split_sha256,
            },
            "policy": policy,
            "schemaVersion": 1,
            "status": "bootstrap_manual_review_only",
            "temperature": round(temperature, 10),
            "test": {
                "after": calibration_metrics(
                    test_after,
                    test_labels,
                    data.class_codes,
                ),
                "before": calibration_metrics(
                    test_before,
                    test_labels,
                    data.class_codes,
                ),
                "validationSelectedCandidateMeasurement": _threshold_measurement(
                    test_after,
                    test_labels,
                    candidate_threshold,
                ),
            },
            "thresholdRequirements": {
                "minimumClassPrecision": AUTO_ACCEPT_MINIMUM_CLASS_PRECISION,
                "minimumClassSamples": AUTO_ACCEPT_MINIMUM_CLASS_SAMPLES,
                "minimumOverallPrecision": AUTO_ACCEPT_TARGET_PRECISION,
                "minimumOverallSamples": AUTO_ACCEPT_MINIMUM_SAMPLES,
            },
            "validation": {
                "after": calibration_metrics(
                    validation_after,
                    validation_labels,
                    data.class_codes,
                ),
                "before": calibration_metrics(
                    validation_before,
                    validation_labels,
                    data.class_codes,
                ),
                "bestMeasuredCandidate": dict(candidate) if candidate else None,
                "thresholdEvidence": [dict(row) for row in rows],
            },
        }
        calibration_bytes = _json_bytes(calibration_report)

        _, dataset = _load_json(args.dataset)
        inventory_bytes, inventory = load_symbol_crop_inventory(args.inventory)
        pending_without_paths = _pending_samples(
            dataset,
            inventory,
            inventory_bytes,
        )
        boards, partial_board_count = _infer_pending_boards(
            adapter,
            pending_without_paths,
            args.crop_root,
            temperature,
        )
        selected = select_active_learning_boards(
            boards,
            data.class_codes,
            batch_size=args.batch_size,
        )
        selection_report: dict[str, object] = {
            "activeLearningVersion": ACTIVE_LEARNING_VERSION,
            "batchSize": args.batch_size,
            "calibrationReportSha256": hashlib.sha256(calibration_bytes).hexdigest(),
            "candidateCompletePendingBoardCount": len(boards),
            "classes": list(data.class_codes),
            "datasetSha256": data.dataset_sha256,
            "excludedPartialPendingBoardCount": partial_board_count,
            "inventorySha256": hashlib.sha256(inventory_bytes).hexdigest(),
            "inventoryVersion": inventory.inventory_version,
            "model": {
                "modelVersion": onnx_model_version,
                "onnxArtifactSha256": onnx_artifact_sha256,
                "temperature": round(temperature, 10),
            },
            "pendingCellCount": len(pending_without_paths),
            "schemaVersion": 1,
            "scoreWeights": {
                "predictedClassRarity": 0.05,
                "predictionDiversity": 0.15,
                "sourceNovelty": 0.15,
                "uncertainty": 0.65,
            },
            "selectedBoardCount": len(selected),
            "selectedBoards": list(selected),
            "selectionBoundary": {
                "completePendingBoardsOnly": True,
                "maximumOneBoardPerSourceUntilAllSourcesCovered": True,
                "mutatesReviewedLabels": False,
            },
            "splitSha256": data.split_sha256,
            "status": "ready_for_manual_review",
        }
        selection_bytes = _json_bytes(selection_report)
        if args.check:
            if (
                args.calibration_report.read_bytes() != calibration_bytes
                or args.selection_report.read_bytes() != selection_bytes
            ):
                raise SymbolConfidenceError(
                    "SYMBOL_CONFIDENCE_REPORT_DRIFT",
                    "Repeated calibration or selection differs from the saved report.",
                )
        else:
            _write_atomic(args.calibration_report, calibration_bytes)
            _write_atomic(args.selection_report, selection_bytes)
    except (
        OSError,
        SymbolClassifierError,
        SymbolConfidenceError,
        SymbolDatasetError,
        SymbolOnnxError,
    ) as error:
        code = getattr(error, "code", "SYMBOL_CONFIDENCE_EXECUTION_FAILED")
        print(f"ERROR [{code}]: {error}", file=sys.stderr)
        return 1

    print("M6 symbol confidence calibration is reproducible.")
    print(f"Temperature: {temperature:.10f}")
    auto_accept = _mapping(policy.get("autoAccept"), "policy.autoAccept")
    print(f"Auto-accept enabled: {auto_accept.get('enabled')}")
    print(f"Pending cells verified: {len(pending_without_paths)}")
    print(f"Complete pending boards: {len(boards)}")
    print(f"Selected boards: {len(selected)}")
    print(f"Calibration report SHA-256: {hashlib.sha256(calibration_bytes).hexdigest()}")
    print(f"Selection report SHA-256: {hashlib.sha256(selection_bytes).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
