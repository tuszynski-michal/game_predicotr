"""Export and verify the immutable M6 symbol classifier ONNX artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from collections.abc import Mapping, Sequence
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

import numpy as np
import onnx
import onnxruntime as ort  # type: ignore[import-untyped]
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "worker" / "src"))

from game_predictor_worker.images.symbol_classifier import (  # noqa: E402
    PREPROCESSING_VERSION,
    ClassifierSample,
    SymbolClassifierError,
    load_classifier_artifact,
    load_image_tensor,
    prepare_training_data,
)
from game_predictor_worker.images.symbol_onnx import (  # noqa: E402
    MAX_PARITY_ABSOLUTE_ERROR,
    ONNX_ADAPTER_VERSION,
    ONNX_INPUT_NAME,
    ONNX_MODEL_VERSION,
    ONNX_OPSET_VERSION,
    ONNX_OUTPUT_NAME,
    LocalSymbolOnnxAdapter,
    SymbolOnnxError,
    export_symbol_classifier_onnx,
    tensor_batch_to_numpy,
)
from game_predictor_worker.images.symbol_suggestions import (  # noqa: E402
    SymbolSuggestionError,
    validate_classifier_provenance,
)

QUALITY = ROOT / "ai_docs" / "quality"
DEFAULT_DATASET = QUALITY / "m6-symbol-dataset-export-report.json"
DEFAULT_SPLIT = QUALITY / "m6-symbol-dataset-split-report.json"
DEFAULT_ASSETS = ROOT / "artifacts" / "m6-symbol-dataset-v1"
DEFAULT_PYTORCH_ARTIFACT = (
    ROOT / "artifacts" / "m6-symbol-classifier-baseline" / "bootstrap-symbol-cnn-v1.pt"
)
DEFAULT_PYTORCH_REPORT = QUALITY / "m6-symbol-classifier-baseline-report.json"
DEFAULT_ONNX_ARTIFACT = (
    ROOT / "artifacts" / "m6-symbol-classifier-onnx" / "bootstrap-symbol-cnn-v1.onnx"
)
DEFAULT_REPORT = QUALITY / "m6-symbol-classifier-onnx-report.json"
BATCH_SIZE = 32


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--asset-root", type=Path, default=DEFAULT_ASSETS)
    parser.add_argument("--pytorch-artifact", type=Path, default=DEFAULT_PYTORCH_ARTIFACT)
    parser.add_argument("--pytorch-report", type=Path, default=DEFAULT_PYTORCH_REPORT)
    parser.add_argument("--onnx-artifact", type=Path, default=DEFAULT_ONNX_ARTIFACT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
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
        raise SymbolOnnxError(
            "SYMBOL_ONNX_REPORT_INVALID",
            f"{label} must be an object.",
        )
    return value


def _load_report(path: Path) -> Mapping[str, object]:
    try:
        value: Any = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise SymbolOnnxError(
            "SYMBOL_ONNX_REPORT_INVALID",
            f"Cannot read {path.name}.",
        ) from error
    return _mapping(value, path.name)


def _number(value: object, label: str) -> float:
    if not isinstance(value, int | float):
        raise SymbolOnnxError(
            "SYMBOL_ONNX_REPORT_INVALID",
            f"{label} must be numeric.",
        )
    return float(value)


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as error:
        raise SymbolOnnxError(
            "SYMBOL_ONNX_ARTIFACT_PATH_INVALID",
            "The ONNX artifact must remain inside the repository.",
        ) from error


def _batches(
    samples: Sequence[ClassifierSample],
    batch_size: int,
) -> Sequence[Sequence[ClassifierSample]]:
    return tuple(
        samples[index : index + batch_size] for index in range(0, len(samples), batch_size)
    )


def _runtime_observation(
    batch_durations_ms: Sequence[float],
    sample_count: int,
) -> dict[str, object]:
    ordered = sorted(batch_durations_ms)
    p95_index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    total_ms = sum(ordered)
    return {
        "batchCount": len(ordered),
        "batchSize": BATCH_SIZE,
        "medianBatchMs": round(statistics.median(ordered), 6),
        "observedOnce": True,
        "p95BatchMs": round(ordered[p95_index], 6),
        "sampleCount": sample_count,
        "totalInferenceMs": round(total_ms, 6),
        "throughputSamplesPerSecond": round(sample_count / (total_ms / 1000.0), 4),
    }


def _validate_preserved_observation(value: object) -> Mapping[str, object]:
    observation = _mapping(value, "runtimeObservation")
    required = (
        "batchCount",
        "batchSize",
        "medianBatchMs",
        "p95BatchMs",
        "sampleCount",
        "totalInferenceMs",
        "throughputSamplesPerSecond",
    )
    for key in required:
        if _number(observation.get(key), f"runtimeObservation.{key}") < 0:
            raise SymbolOnnxError(
                "SYMBOL_ONNX_REPORT_INVALID",
                "The preserved runtime observation is invalid.",
            )
    return observation


def _parity(
    *,
    samples_by_split: Mapping[str, tuple[ClassifierSample, ...]],
    model: torch.nn.Module,
    adapter: LocalSymbolOnnxAdapter,
    input_size: int,
) -> tuple[dict[str, object], dict[str, object]]:
    max_logits_error = 0.0
    max_probability_error = 0.0
    top_one_mismatches = 0
    total = 0
    batch_durations_ms: list[float] = []
    split_rows: list[dict[str, object]] = []
    for split_name in ("train", "validation", "test"):
        samples = tuple(sorted(samples_by_split[split_name], key=lambda value: value.sample_id))
        split_max_logits = 0.0
        split_max_probability = 0.0
        split_mismatches = 0
        for batch in _batches(samples, BATCH_SIZE):
            tensors = torch.stack(
                [load_image_tensor(sample.asset_path, input_size) for sample in batch]
            )
            with torch.inference_mode():
                pytorch_logits = model(tensors).cpu()
                pytorch_probabilities = torch.softmax(pytorch_logits, dim=1)
            started = time.perf_counter()
            onnx_result = adapter.infer(tensor_batch_to_numpy(tensors))
            batch_durations_ms.append((time.perf_counter() - started) * 1000.0)
            logits_error = float(
                np.max(np.abs(tensor_batch_to_numpy(pytorch_logits) - onnx_result.logits))
            )
            probability_error = float(
                np.max(
                    np.abs(tensor_batch_to_numpy(pytorch_probabilities) - onnx_result.probabilities)
                )
            )
            pytorch_top_one = (
                torch.argmax(pytorch_logits, dim=1).numpy().astype(np.int64, copy=False)
            )
            mismatches = int(np.count_nonzero(pytorch_top_one != onnx_result.class_indexes))
            split_max_logits = max(split_max_logits, logits_error)
            split_max_probability = max(split_max_probability, probability_error)
            split_mismatches += mismatches
        split_rows.append(
            {
                "maxAbsoluteLogitsError": round(split_max_logits, 10),
                "maxAbsoluteProbabilityError": round(split_max_probability, 10),
                "name": split_name,
                "sampleCount": len(samples),
                "topOneMismatchCount": split_mismatches,
            }
        )
        max_logits_error = max(max_logits_error, split_max_logits)
        max_probability_error = max(max_probability_error, split_max_probability)
        top_one_mismatches += split_mismatches
        total += len(samples)
    parity = {
        "maxAbsoluteLogitsError": round(max_logits_error, 10),
        "maxAbsoluteProbabilityError": round(max_probability_error, 10),
        "sampleCount": total,
        "splits": split_rows,
        "tolerance": MAX_PARITY_ABSOLUTE_ERROR,
        "topOneMismatchCount": top_one_mismatches,
    }
    return parity, _runtime_observation(batch_durations_ms, total)


def main() -> int:
    args = _args()
    try:
        data = prepare_training_data(args.dataset, args.split, args.asset_root)
        validate_classifier_provenance(
            args.pytorch_report,
            args.pytorch_artifact,
            data,
        )
        model, class_codes, input_size = load_classifier_artifact(args.pytorch_artifact)
        if class_codes != data.class_codes:
            raise SymbolOnnxError(
                "SYMBOL_ONNX_CLASS_CONTRACT_INVALID",
                "Checkpoint classes differ from the approved dataset.",
            )
        onnx_content = export_symbol_classifier_onnx(
            model,
            input_size=input_size,
            class_count=len(class_codes),
        )
        if (
            export_symbol_classifier_onnx(
                model,
                input_size=input_size,
                class_count=len(class_codes),
            )
            != onnx_content
        ):
            raise SymbolOnnxError(
                "SYMBOL_ONNX_EXPORT_NONDETERMINISTIC",
                "Two immediate ONNX exports produced different bytes.",
            )
        if args.check:
            if args.onnx_artifact.read_bytes() != onnx_content:
                raise SymbolOnnxError(
                    "SYMBOL_ONNX_ARTIFACT_DRIFT",
                    "The local ONNX artifact differs from a repeated export.",
                )
        else:
            _write_atomic(args.onnx_artifact, onnx_content)
        onnx_sha256 = hashlib.sha256(onnx_content).hexdigest()
        adapter = LocalSymbolOnnxAdapter(
            args.onnx_artifact,
            expected_sha256=onnx_sha256,
            class_codes=class_codes,
            input_size=input_size,
        )
        parity, measured_observation = _parity(
            samples_by_split={
                "train": data.train,
                "validation": data.validation,
                "test": data.test,
            },
            model=model,
            adapter=adapter,
            input_size=input_size,
        )
        if (
            parity["topOneMismatchCount"] != 0
            or _number(
                parity["maxAbsoluteLogitsError"],
                "parity.maxAbsoluteLogitsError",
            )
            > MAX_PARITY_ABSOLUTE_ERROR
            or _number(
                parity["maxAbsoluteProbabilityError"],
                "parity.maxAbsoluteProbabilityError",
            )
            > MAX_PARITY_ABSOLUTE_ERROR
        ):
            raise SymbolOnnxError(
                "SYMBOL_ONNX_PARITY_FAILED",
                "ONNX output differs from PyTorch beyond the accepted tolerance.",
            )
        pytorch_report = _load_report(args.pytorch_report)
        pytorch_artifact = _mapping(
            pytorch_report.get("artifact"),
            "pytorchReport.artifact",
        )
        model_proto = onnx.load_model_from_string(onnx_content)
        runtime_observation: Mapping[str, object] = measured_observation
        if args.check:
            existing_report = _load_report(args.report)
            runtime_observation = _validate_preserved_observation(
                existing_report.get("runtimeObservation")
            )
        report: dict[str, object] = {
            "adapterVersion": ONNX_ADAPTER_VERSION,
            "artifact": {
                "relativePath": _relative(args.onnx_artifact),
                "sha256": onnx_sha256,
                "sizeBytes": len(onnx_content),
            },
            "classes": [
                {"classIndex": index, "symbolCode": code} for index, code in enumerate(class_codes)
            ],
            "datasetSha256": data.dataset_sha256,
            "graph": {
                "input": {
                    "dataType": "float32",
                    "name": ONNX_INPUT_NAME,
                    "shape": ["batch", 3, input_size, input_size],
                },
                "irVersion": int(model_proto.ir_version),
                "opsetVersion": ONNX_OPSET_VERSION,
                "output": {
                    "dataType": "float32",
                    "name": ONNX_OUTPUT_NAME,
                    "shape": ["batch", len(class_codes)],
                },
            },
            "modelVersion": ONNX_MODEL_VERSION,
            "parity": parity,
            "preprocessingVersion": PREPROCESSING_VERSION,
            "provider": "CPUExecutionProvider",
            "pytorchSource": {
                "artifactSha256": pytorch_artifact.get("sha256"),
                "logicalStateSha256": pytorch_artifact.get("logicalStateSha256"),
            },
            "runtime": {
                "onnxRuntimeVersion": ort.__version__,
                "onnxScriptVersion": package_version("onnxscript"),
                "onnxVersion": onnx.__version__,
                "torchVersion": torch.__version__,
            },
            "runtimeObservation": dict(runtime_observation),
            "schemaVersion": 1,
            "splitSha256": data.split_sha256,
            "status": "bootstrap",
        }
        report_content = _json_bytes(report)
        if args.check:
            if args.report.read_bytes() != report_content:
                raise SymbolOnnxError(
                    "SYMBOL_ONNX_REPORT_DRIFT",
                    "The ONNX report differs from the verified export and parity run.",
                )
        else:
            _write_atomic(args.report, report_content)
        print(
            json.dumps(
                {
                    "artifactSha256": onnx_sha256,
                    "maxAbsoluteLogitsError": parity["maxAbsoluteLogitsError"],
                    "maxAbsoluteProbabilityError": parity["maxAbsoluteProbabilityError"],
                    "reportSha256": hashlib.sha256(report_content).hexdigest(),
                    "sampleCount": parity["sampleCount"],
                    "status": "passed",
                    "topOneMismatchCount": parity["topOneMismatchCount"],
                },
                sort_keys=True,
            )
        )
        return 0
    except (
        OSError,
        SymbolClassifierError,
        SymbolOnnxError,
        SymbolSuggestionError,
    ) as error:
        code = getattr(error, "code", "SYMBOL_ONNX_IO_ERROR")
        print(
            json.dumps({"code": code, "message": str(error), "status": "failed"}),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
