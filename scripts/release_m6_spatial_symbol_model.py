"""Build or reproduce the checksum-bound M6 spatial symbol model release."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import torch
from game_predictor_worker.images.symbol_classifier import (
    PREPROCESSING_VERSION,
    ClassifierSample,
    PreparedTrainingData,
    SymbolClassifierError,
    load_image_tensor,
    prepare_training_data,
    set_deterministic_runtime,
)
from game_predictor_worker.images.symbol_confidence import (
    AUTO_ACCEPT_MINIMUM_CLASS_PRECISION,
    AUTO_ACCEPT_MINIMUM_CLASS_SAMPLES,
    AUTO_ACCEPT_MINIMUM_SAMPLES,
    AUTO_ACCEPT_TARGET_PRECISION,
    CALIBRATION_VERSION,
    build_confidence_policy,
    calibrated_probabilities,
    calibration_metrics,
    fit_temperature,
    threshold_evidence,
)
from game_predictor_worker.images.symbol_model_benchmark import (
    SPATIAL_ARCHITECTURE_VERSION,
    SPATIAL_VARIANT,
)
from game_predictor_worker.images.symbol_model_release import (
    MAX_SYMBOL_ALTERNATIVES,
    SPATIAL_MODEL_VERSION,
    SPATIAL_ONNX_MODEL_VERSION,
    SPATIAL_RELEASE_VERSION,
    SymbolModelReleaseError,
    build_symbol_predictions,
    load_spatial_model_checkpoint,
    validate_release_manifest,
)
from game_predictor_worker.images.symbol_onnx import (
    MAX_PARITY_ABSOLUTE_ERROR,
    LocalSymbolOnnxAdapter,
    export_symbol_classifier_onnx,
    tensor_batch_to_numpy,
)
from game_predictor_worker.images.symbol_vertical_slice import (
    VERTICAL_SLICE_VERSION,
    build_review_replay,
    evaluate_probabilities,
)
from numpy.typing import NDArray

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RELEASE_ROOT = REPOSITORY_ROOT / "artifacts/m6-spatial-symbol-model-release-v1"
QUALITY_ROOT = REPOSITORY_ROOT / "ai_docs/quality"
INFERENCE_BATCH_SIZE = 64


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        default=QUALITY_ROOT / "m6-symbol-dataset-export-report-v3.json",
    )
    parser.add_argument(
        "--split",
        type=Path,
        default=QUALITY_ROOT / "m6-symbol-dataset-split-report-v3.json",
    )
    parser.add_argument(
        "--asset-root",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts/m6-symbol-dataset-v3",
    )
    parser.add_argument(
        "--source-checkpoint",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts/m6-symbol-model-benchmark/spatial-v1.pt",
    )
    parser.add_argument(
        "--benchmark-report",
        type=Path,
        default=QUALITY_ROOT / "m6-symbol-model-benchmark-spatial-report.json",
    )
    parser.add_argument(
        "--selection-report",
        type=Path,
        default=QUALITY_ROOT / "m6-symbol-model-validation-selection-report.json",
    )
    parser.add_argument(
        "--selected-test-report",
        type=Path,
        default=QUALITY_ROOT / "m6-symbol-model-selected-test-report.json",
    )
    parser.add_argument(
        "--benchmark-decision",
        type=Path,
        default=QUALITY_ROOT / "m6-symbol-model-benchmark-decision.json",
    )
    parser.add_argument(
        "--release-root",
        type=Path,
        default=RELEASE_ROOT,
    )
    parser.add_argument(
        "--quality-root",
        type=Path,
        default=QUALITY_ROOT,
    )
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode()


def _load_json(path: Path) -> tuple[bytes, Mapping[str, object]]:
    try:
        content = path.read_bytes()
        value: Any = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_RELEASE_INPUT_INVALID",
            f"Cannot read {path.name}.",
        ) from error
    if not isinstance(value, Mapping):
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_RELEASE_INPUT_INVALID",
            f"{path.name} must contain an object.",
        )
    return content, value


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _number(value: object, label: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_RELEASE_CONTRACT_INVALID",
            f"{label} must be numeric.",
        )
    return float(value)


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_RELEASE_CONTRACT_INVALID",
            f"{label} must be an integer.",
        )
    return value


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError as error:
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_RELEASE_PATH_INVALID",
            "Release paths must remain inside the repository.",
        ) from error


def _write_or_check(path: Path, content: bytes, *, check: bool) -> None:
    if check:
        try:
            existing = path.read_bytes()
        except OSError as error:
            raise SymbolModelReleaseError(
                "SYMBOL_MODEL_RELEASE_OUTPUT_MISSING",
                f"Cannot read expected output {path.name}.",
            ) from error
        if existing != content:
            raise SymbolModelReleaseError(
                "SYMBOL_MODEL_RELEASE_OUTPUT_DRIFT",
                f"Reproduced output differs from {path.name}.",
            )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _validate_selection(
    *,
    data: PreparedTrainingData,
    checkpoint_sha256: str,
    benchmark_report_path: Path,
    selection_report_path: Path,
    selected_test_report_path: Path,
    benchmark_decision_path: Path,
) -> dict[str, str]:
    benchmark_bytes, benchmark = _load_json(benchmark_report_path)
    selection_bytes, selection = _load_json(selection_report_path)
    test_bytes, test_report = _load_json(selected_test_report_path)
    decision_bytes, decision = _load_json(benchmark_decision_path)
    artifact = benchmark.get("artifact")
    selected_model = test_report.get("selectedModel")
    if (
        not isinstance(artifact, Mapping)
        or not isinstance(selected_model, Mapping)
        or benchmark.get("candidateId") != SPATIAL_VARIANT
        or benchmark.get("architectureVersion") != SPATIAL_ARCHITECTURE_VERSION
        or benchmark.get("datasetSha256") != data.dataset_sha256
        or benchmark.get("splitSha256") != data.split_sha256
        or artifact.get("sha256") != checkpoint_sha256
        or selection.get("selectedCandidateId") != SPATIAL_VARIANT
        or selection.get("datasetSha256") != data.dataset_sha256
        or selection.get("splitSha256") != data.split_sha256
        or test_report.get("selectedCandidateId") != SPATIAL_VARIANT
        or selected_model.get("artifactSha256") != checkpoint_sha256
        or test_report.get("selectionReportSha256") != _sha256(selection_bytes)
        or decision.get("selectedCandidateId") != SPATIAL_VARIANT
        or decision.get("selectionReportSha256") != _sha256(selection_bytes)
    ):
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_RELEASE_SELECTION_DRIFT",
            "The selected checkpoint no longer matches the benchmark decision chain.",
        )
    test_boundary = decision.get("testBoundary")
    if not isinstance(test_boundary, Mapping) or test_boundary.get(
        "selectedTestReportSha256"
    ) != _sha256(test_bytes):
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_RELEASE_TEST_BOUNDARY_DRIFT",
            "The frozen test report differs from the benchmark decision.",
        )
    return {
        "benchmarkDecisionSha256": _sha256(decision_bytes),
        "benchmarkReportSha256": _sha256(benchmark_bytes),
        "selectedTestReportSha256": _sha256(test_bytes),
        "selectionReportSha256": _sha256(selection_bytes),
    }


def _batches(
    values: Sequence[ClassifierSample],
    size: int = INFERENCE_BATCH_SIZE,
) -> Sequence[Sequence[ClassifierSample]]:
    return tuple(values[index : index + size] for index in range(0, len(values), size))


def _infer_split(
    samples: Sequence[ClassifierSample],
    *,
    model: torch.nn.Module,
    adapter: LocalSymbolOnnxAdapter,
    input_size: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.int64]]:
    pytorch_rows: list[NDArray[np.float32]] = []
    onnx_rows: list[NDArray[np.float32]] = []
    labels: list[int] = []
    with torch.inference_mode():
        for batch in _batches(samples):
            tensors = torch.stack(
                [load_image_tensor(sample.asset_path, input_size) for sample in batch]
            )
            pytorch_rows.append(
                model(tensors).detach().cpu().numpy().astype(np.float32, copy=False)
            )
            onnx_rows.append(adapter.infer(tensor_batch_to_numpy(tensors)).logits)
            labels.extend(sample.class_index for sample in batch)
    return (
        np.concatenate(pytorch_rows).astype(np.float64),
        np.concatenate(onnx_rows).astype(np.float64),
        np.asarray(labels, dtype=np.int64),
    )


def _parity(
    pytorch_logits: NDArray[np.float64],
    onnx_logits: NDArray[np.float64],
) -> dict[str, object]:
    absolute = np.abs(pytorch_logits - onnx_logits)
    mismatch = int(
        np.count_nonzero(np.argmax(pytorch_logits, axis=1) != np.argmax(onnx_logits, axis=1))
    )
    return {
        "maximumAbsoluteError": round(float(absolute.max()), 10),
        "meanAbsoluteError": round(float(absolute.mean()), 10),
        "sampleCount": int(pytorch_logits.shape[0]),
        "topOneMismatchCount": mismatch,
    }


def _threshold_measurement(
    probabilities: NDArray[np.float64],
    labels: NDArray[np.int64],
    threshold: float | None,
) -> dict[str, object] | None:
    if threshold is None:
        return None
    predictions = np.argmax(probabilities, axis=1)
    accepted = np.max(probabilities, axis=1) >= threshold
    count = int(accepted.sum())
    correct = int(np.count_nonzero(accepted & (predictions == labels)))
    return {
        "correctCount": correct,
        "coverage": round(count / len(labels), 8),
        "precision": round(correct / count if count else 0.0, 8),
        "sampleCount": count,
        "threshold": threshold,
    }


def _dataset_metadata(
    dataset_path: Path,
) -> dict[str, tuple[str, int]]:
    _, dataset = _load_json(dataset_path)
    samples = dataset.get("samples")
    if isinstance(samples, str | bytes) or not isinstance(samples, Sequence):
        raise SymbolModelReleaseError(
            "SYMBOL_MODEL_RELEASE_DATASET_INVALID",
            "The dataset samples array is missing.",
        )
    result: dict[str, tuple[str, int]] = {}
    for raw in samples:
        if not isinstance(raw, Mapping):
            raise SymbolModelReleaseError(
                "SYMBOL_MODEL_RELEASE_DATASET_INVALID",
                "A dataset sample is invalid.",
            )
        sample_id = raw.get("sampleId")
        board_id = raw.get("boardId")
        cell_index = raw.get("cellIndex")
        if (
            not isinstance(sample_id, str)
            or not isinstance(board_id, str)
            or not isinstance(cell_index, int)
            or isinstance(cell_index, bool)
        ):
            raise SymbolModelReleaseError(
                "SYMBOL_MODEL_RELEASE_DATASET_INVALID",
                "Dataset review identity is incomplete.",
            )
        result[sample_id] = (board_id, cell_index)
    return result


def _artifact_row(path: Path, content: bytes) -> dict[str, str]:
    return {
        "relativePath": _relative(path),
        "sha256": _sha256(content),
    }


def main() -> int:
    args = _args()
    try:
        set_deterministic_runtime(61061)
        data = prepare_training_data(args.dataset, args.split, args.asset_root)
        source_checkpoint = args.source_checkpoint.read_bytes()
        checkpoint_sha256 = _sha256(source_checkpoint)
        provenance = _validate_selection(
            data=data,
            checkpoint_sha256=checkpoint_sha256,
            benchmark_report_path=args.benchmark_report,
            selection_report_path=args.selection_report,
            selected_test_report_path=args.selected_test_report,
            benchmark_decision_path=args.benchmark_decision,
        )
        release_checkpoint = args.release_root / "spatial-symbol-cnn-v1.pt"
        _write_or_check(release_checkpoint, source_checkpoint, check=args.check)
        loaded = load_spatial_model_checkpoint(
            release_checkpoint,
            expected_sha256=checkpoint_sha256,
            expected_dataset_sha256=data.dataset_sha256,
            expected_split_sha256=data.split_sha256,
            expected_class_codes=data.class_codes,
        )

        onnx_content = export_symbol_classifier_onnx(
            loaded.model,
            input_size=loaded.input_size,
            class_count=len(loaded.class_codes),
            model_version=SPATIAL_ONNX_MODEL_VERSION,
        )
        if (
            export_symbol_classifier_onnx(
                loaded.model,
                input_size=loaded.input_size,
                class_count=len(loaded.class_codes),
                model_version=SPATIAL_ONNX_MODEL_VERSION,
            )
            != onnx_content
        ):
            raise SymbolModelReleaseError(
                "SYMBOL_MODEL_RELEASE_ONNX_NON_DETERMINISTIC",
                "Two immediate exports produced different ONNX bytes.",
            )
        onnx_path = args.release_root / "spatial-symbol-cnn-v1.onnx"
        _write_or_check(onnx_path, onnx_content, check=args.check)
        onnx_sha256 = _sha256(onnx_content)
        adapter = LocalSymbolOnnxAdapter(
            onnx_path,
            expected_sha256=onnx_sha256,
            class_codes=loaded.class_codes,
            input_size=loaded.input_size,
        )

        split_values: dict[
            str,
            tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.int64]],
        ] = {}
        for name, samples in (
            ("train", data.train),
            ("validation", data.validation),
            ("test", data.test),
        ):
            split_values[name] = _infer_split(
                samples,
                model=loaded.model,
                adapter=adapter,
                input_size=loaded.input_size,
            )
        parity = {name: _parity(pytorch, onnx) for name, (pytorch, onnx, _) in split_values.items()}
        if any(
            row["topOneMismatchCount"] != 0
            or _number(
                row["maximumAbsoluteError"],
                "parity.maximumAbsoluteError",
            )
            > MAX_PARITY_ABSOLUTE_ERROR
            for row in parity.values()
        ):
            raise SymbolModelReleaseError(
                "SYMBOL_MODEL_RELEASE_PARITY_FAILED",
                "PyTorch and ONNX exceeded the accepted parity contract.",
            )

        onnx_report: dict[str, object] = {
            "architectureVersion": SPATIAL_ARCHITECTURE_VERSION,
            "artifact": _artifact_row(onnx_path, onnx_content),
            "classes": list(loaded.class_codes),
            "datasetSha256": data.dataset_sha256,
            "inputSize": loaded.input_size,
            "modelVersion": SPATIAL_MODEL_VERSION,
            "onnxModelVersion": SPATIAL_ONNX_MODEL_VERSION,
            "parity": {
                "maximumAbsoluteErrorTolerance": MAX_PARITY_ABSOLUTE_ERROR,
                "splits": parity,
                "totalTopOneMismatchCount": sum(
                    _integer(
                        row["topOneMismatchCount"],
                        "parity.topOneMismatchCount",
                    )
                    for row in parity.values()
                ),
            },
            "preprocessingVersion": PREPROCESSING_VERSION,
            "schemaVersion": 1,
            "splitSha256": data.split_sha256,
            "status": "production_candidate",
        }
        onnx_report_content = _json_bytes(onnx_report)
        onnx_report_path = args.quality_root / "m6-spatial-symbol-model-onnx-report.json"
        _write_or_check(onnx_report_path, onnx_report_content, check=args.check)

        validation_logits = split_values["validation"][1]
        validation_labels = split_values["validation"][2]
        test_logits = split_values["test"][1]
        test_labels = split_values["test"][2]
        temperature = fit_temperature(validation_logits, validation_labels)
        validation_before = calibrated_probabilities(validation_logits, 1.0)
        validation_after = calibrated_probabilities(validation_logits, temperature)
        test_before = calibrated_probabilities(test_logits, 1.0)
        test_after = calibrated_probabilities(test_logits, temperature)
        rows = threshold_evidence(validation_after, validation_labels, loaded.class_codes)
        policy = build_confidence_policy(
            rows,
            model_status="production_candidate",
            bootstrap_target_met=True,
        )
        auto_accept = policy["autoAccept"]
        if not isinstance(auto_accept, Mapping):
            raise SymbolModelReleaseError(
                "SYMBOL_MODEL_RELEASE_POLICY_INVALID",
                "The confidence policy has no auto-accept decision.",
            )
        threshold_value = auto_accept.get("threshold")
        threshold = float(threshold_value) if isinstance(threshold_value, int | float) else None
        calibration_report: dict[str, object] = {
            "calibrationVersion": CALIBRATION_VERSION,
            "classes": list(loaded.class_codes),
            "fitBoundary": {
                "fitSampleCount": len(data.validation),
                "fitSplit": "validation",
                "testMeasuredOnceAfterFit": True,
                "testSampleCount": len(data.test),
                "testUsedForCalibration": False,
                "trainUsedForCalibration": False,
            },
            "inputs": {
                "datasetSha256": data.dataset_sha256,
                "modelVersion": SPATIAL_MODEL_VERSION,
                "onnxArtifactSha256": onnx_sha256,
                "onnxReportSha256": _sha256(onnx_report_content),
                "splitSha256": data.split_sha256,
            },
            "policy": policy,
            "schemaVersion": 1,
            "status": (
                "production_candidate_auto_accept_enabled"
                if auto_accept.get("enabled") is True
                else "production_candidate_manual_review_only"
            ),
            "temperature": round(temperature, 10),
            "test": {
                "after": calibration_metrics(test_after, test_labels, loaded.class_codes),
                "before": calibration_metrics(test_before, test_labels, loaded.class_codes),
                "frozenValidationThresholdMeasurement": _threshold_measurement(
                    test_after,
                    test_labels,
                    threshold,
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
                    loaded.class_codes,
                ),
                "before": calibration_metrics(
                    validation_before,
                    validation_labels,
                    loaded.class_codes,
                ),
                "thresholdEvidence": [dict(row) for row in rows],
            },
        }
        calibration_content = _json_bytes(calibration_report)
        calibration_path = (
            args.quality_root / "m6-spatial-symbol-model-confidence-calibration-report.json"
        )
        _write_or_check(calibration_path, calibration_content, check=args.check)

        ordered_samples: tuple[ClassifierSample, ...] = (
            *data.train,
            *data.validation,
            *data.test,
        )
        split_names = (
            *("train" for _ in data.train),
            *("validation" for _ in data.validation),
            *("test" for _ in data.test),
        )
        all_logits = np.concatenate(
            [
                split_values["train"][1],
                split_values["validation"][1],
                split_values["test"][1],
            ]
        )
        all_labels = np.concatenate(
            [
                split_values["train"][2],
                split_values["validation"][2],
                split_values["test"][2],
            ]
        )
        all_probabilities = calibrated_probabilities(all_logits, temperature)
        metadata = _dataset_metadata(args.dataset)
        evaluated, overall_metrics = evaluate_probabilities(
            sample_ids=[sample.sample_id for sample in ordered_samples],
            board_ids=[metadata[sample.sample_id][0] for sample in ordered_samples],
            cell_indexes=[metadata[sample.sample_id][1] for sample in ordered_samples],
            split_names=split_names,
            probabilities=all_probabilities,
            labels=all_labels,
            class_codes=loaded.class_codes,
        )
        predictions = build_symbol_predictions(
            all_logits,
            temperature=temperature,
            class_codes=loaded.class_codes,
        )
        if any(
            len(prediction.alternatives) > MAX_SYMBOL_ALTERNATIVES
            or prediction.symbol_code != prediction.alternatives[0].symbol_code
            for prediction in predictions
        ):
            raise SymbolModelReleaseError(
                "SYMBOL_MODEL_RELEASE_ALTERNATIVES_INVALID",
                "A vertical-slice prediction violates the alternatives contract.",
            )
        split_metrics = {
            name: calibration_metrics(
                calibrated_probabilities(values[1], temperature),
                values[2],
                loaded.class_codes,
            )
            for name, values in split_values.items()
        }
        vertical_report: dict[str, object] = {
            "alternativeContract": {
                "deterministicTieBreak": "confidence_desc_then_symbol_code",
                "maximumAlternatives": MAX_SYMBOL_ALTERNATIVES,
                "samplePrediction": predictions[0].to_dict(),
            },
            "classes": list(loaded.class_codes),
            "datasetSha256": data.dataset_sha256,
            "modelVersion": SPATIAL_MODEL_VERSION,
            "onnxArtifactSha256": onnx_sha256,
            "overallMetrics": overall_metrics,
            "reviewReplay": build_review_replay(evaluated),
            "sampleCount": len(ordered_samples),
            "schemaVersion": 1,
            "splitMetrics": split_metrics,
            "splitSampleCounts": {
                "test": len(data.test),
                "train": len(data.train),
                "validation": len(data.validation),
            },
            "splitSha256": data.split_sha256,
            "status": "passed",
            "verticalSliceVersion": VERTICAL_SLICE_VERSION,
        }
        vertical_content = _json_bytes(vertical_report)
        vertical_path = args.quality_root / "m6-spatial-symbol-model-vertical-slice-report.json"
        _write_or_check(vertical_path, vertical_content, check=args.check)

        symbol_auto_accept = auto_accept.get("enabled") is True
        decision_report: dict[str, object] = {
            "calibrationReportSha256": _sha256(calibration_content),
            "decisionVersion": "spatial-symbol-model-production-decision-v1",
            "globalBlockers": ["SEQUENCE_OCR_MANUAL_REVIEW_ONLY"],
            "manualSupervisedPublicationAllowed": True,
            "massImportAllowed": False,
            "modelVersion": SPATIAL_MODEL_VERSION,
            "onnxReportSha256": _sha256(onnx_report_content),
            "reason": (
                "Symbol confidence passed, but sequence OCR still requires human review."
                if symbol_auto_accept
                else "Symbol confidence and sequence OCR still require human review."
            ),
            "schemaVersion": 1,
            "status": "passed_supervised_path_global_auto_import_blocked",
            "symbolAutoAcceptEnabled": symbol_auto_accept,
            "symbolAutoAcceptThreshold": threshold,
            "verticalSliceReportSha256": _sha256(vertical_content),
        }
        decision_content = _json_bytes(decision_report)
        decision_path = args.quality_root / "m6-spatial-symbol-model-release-decision.json"
        _write_or_check(decision_path, decision_content, check=args.check)

        manifest: dict[str, object] = {
            "architectureVersion": SPATIAL_ARCHITECTURE_VERSION,
            "artifacts": {
                "calibrationReport": _artifact_row(calibration_path, calibration_content),
                "checkpoint": _artifact_row(release_checkpoint, source_checkpoint),
                "decisionReport": _artifact_row(decision_path, decision_content),
                "onnx": _artifact_row(onnx_path, onnx_content),
                "onnxReport": _artifact_row(onnx_report_path, onnx_report_content),
                "verticalSliceReport": _artifact_row(vertical_path, vertical_content),
            },
            "classes": list(loaded.class_codes),
            "inputSize": loaded.input_size,
            "inputs": {
                **provenance,
                "datasetSha256": data.dataset_sha256,
                "splitSha256": data.split_sha256,
            },
            "logicalStateSha256": loaded.logical_state_sha256,
            "modelVersion": SPATIAL_MODEL_VERSION,
            "onnxModelVersion": SPATIAL_ONNX_MODEL_VERSION,
            "preprocessingVersion": PREPROCESSING_VERSION,
            "releaseVersion": SPATIAL_RELEASE_VERSION,
            "schemaVersion": 1,
            "temperature": round(temperature, 10),
        }
        manifest_content = _json_bytes(manifest)
        manifest_path = args.quality_root / "m6-spatial-symbol-model-release-manifest.json"
        _write_or_check(manifest_path, manifest_content, check=args.check)
        validate_release_manifest(manifest, repository_root=REPOSITORY_ROOT)
        print(
            json.dumps(
                {
                    "manifestSha256": _sha256(manifest_content),
                    "massImportAllowed": False,
                    "onnxMaximumAbsoluteError": max(
                        _number(
                            row["maximumAbsoluteError"],
                            "parity.maximumAbsoluteError",
                        )
                        for row in parity.values()
                    ),
                    "sampleCount": len(ordered_samples),
                    "status": "passed",
                    "symbolAutoAcceptEnabled": symbol_auto_accept,
                    "symbolAutoAcceptThreshold": threshold,
                    "temperature": round(temperature, 10),
                },
                sort_keys=True,
            )
        )
        return 0
    except (
        OSError,
        SymbolClassifierError,
        SymbolModelReleaseError,
        ValueError,
    ) as error:
        code = getattr(error, "code", "SYMBOL_MODEL_RELEASE_FAILED")
        print(
            json.dumps(
                {"code": code, "message": str(error), "status": "failed"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
