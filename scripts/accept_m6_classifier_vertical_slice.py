"""Verify the bounded image-to-review acceptance slice for Milestone 6."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime  # type: ignore[import-untyped]
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api" / "src"))
sys.path.insert(0, str(ROOT / "services" / "worker" / "src"))

from game_predictor_api.domain.reviews import (  # noqa: E402
    ReviewResolutionAction,
    validate_review_resolution,
    validate_review_selection,
)
from game_predictor_api.domain.reviews import (  # noqa: E402
    canonical_report_bytes as canonical_selection_bytes,
)
from game_predictor_worker.images.reviewed_symbol_inventory import (  # noqa: E402
    build_reviewed_symbol_crop_inventory,
)
from game_predictor_worker.images.symbol_classifier import (  # noqa: E402
    ClassifierSample,
    load_image_tensor,
    prepare_training_data,
)
from game_predictor_worker.images.symbol_confidence import (  # noqa: E402
    calibrated_probabilities,
)
from game_predictor_worker.images.symbol_dataset import (  # noqa: E402
    SymbolCropInventory,
    load_symbol_crop_inventory,
)
from game_predictor_worker.images.symbol_onnx import (  # noqa: E402
    LocalSymbolOnnxAdapter,
    tensor_batch_to_numpy,
)
from game_predictor_worker.images.symbol_vertical_slice import (  # noqa: E402
    VERTICAL_SLICE_VERSION,
    EvaluatedSymbolSample,
    SymbolVerticalSliceError,
    build_review_replay,
    canonical_report_bytes,
    evaluate_probabilities,
    validate_runtime_observation,
)

QUALITY = ROOT / "ai_docs" / "quality"
DEFAULT_CORPUS = QUALITY / "m5-corpus-manifest.json"
DEFAULT_ANNOTATIONS = QUALITY / "m5-golden-annotations.json"
DEFAULT_GEOMETRY_REPORT = QUALITY / "m5-reviewed-manual-merge-v16-full-preflight-report.json"
DEFAULT_OWNER_ACCEPTANCE = QUALITY / "m5-reviewed-manual-merge-v16-owner-acceptance.json"
DEFAULT_CROP_ROOT = ROOT / "artifacts" / "m5-reviewed-manual-merge-v16-full-preflight"
DEFAULT_INVENTORY = QUALITY / "m6-symbol-crop-inventory-v3.json"
DEFAULT_DATASET = QUALITY / "m6-symbol-dataset-export-report.json"
DEFAULT_SPLIT = QUALITY / "m6-symbol-dataset-split-report.json"
DEFAULT_DATASET_ASSETS = ROOT / "artifacts" / "m6-symbol-dataset-v1"
DEFAULT_ONNX_REPORT = QUALITY / "m6-symbol-classifier-onnx-report.json"
DEFAULT_ONNX_ARTIFACT = (
    ROOT / "artifacts" / "m6-symbol-classifier-onnx" / "bootstrap-symbol-cnn-v1.onnx"
)
DEFAULT_CALIBRATION = QUALITY / "m6-symbol-confidence-calibration-report.json"
DEFAULT_SELECTION = QUALITY / "m6-symbol-active-learning-selection.json"
DEFAULT_OUTPUT = QUALITY / "m6-classifier-review-vertical-slice-report.json"
INFERENCE_BATCH_SIZE = 64


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--geometry-report", type=Path, default=DEFAULT_GEOMETRY_REPORT)
    parser.add_argument("--owner-acceptance", type=Path, default=DEFAULT_OWNER_ACCEPTANCE)
    parser.add_argument("--crop-root", type=Path, default=DEFAULT_CROP_ROOT)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--dataset-assets", type=Path, default=DEFAULT_DATASET_ASSETS)
    parser.add_argument("--onnx-report", type=Path, default=DEFAULT_ONNX_REPORT)
    parser.add_argument("--onnx-artifact", type=Path, default=DEFAULT_ONNX_ARTIFACT)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timing-runs", type=int, default=5)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--require-pass", action="store_true")
    return parser.parse_args()


def _load_json(path: Path, code: str) -> tuple[bytes, Mapping[str, object]]:
    try:
        content = path.read_bytes()
        value: Any = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise SymbolVerticalSliceError(code, f"Cannot read {path.name}.") from error
    if not isinstance(value, Mapping):
        raise SymbolVerticalSliceError(code, f"{path.name} must contain an object.")
    return content, value


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SymbolVerticalSliceError(
            "SYMBOL_VERTICAL_SLICE_PROVENANCE_INVALID",
            f"{label} must be an object.",
        )
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise SymbolVerticalSliceError(
            "SYMBOL_VERTICAL_SLICE_PROVENANCE_INVALID",
            f"{label} must be an array.",
        )
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise SymbolVerticalSliceError(
            "SYMBOL_VERTICAL_SLICE_PROVENANCE_INVALID",
            f"{label} must be a non-empty string.",
        )
    return value


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise SymbolVerticalSliceError(
            "SYMBOL_VERTICAL_SLICE_PROVENANCE_INVALID",
            f"{label} must be an integer.",
        )
    return value


def _sha256(value: object, label: str) -> str:
    text = _text(value, label).lower()
    try:
        if len(text) != 64:
            raise ValueError
        int(text, 16)
    except ValueError as error:
        raise SymbolVerticalSliceError(
            "SYMBOL_VERTICAL_SLICE_PROVENANCE_INVALID",
            f"{label} must be SHA-256.",
        ) from error
    return text


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _verify_inventory(args: argparse.Namespace) -> tuple[bytes, SymbolCropInventory, float]:
    started = time.perf_counter_ns()
    rebuilt = build_reviewed_symbol_crop_inventory(
        args.corpus,
        args.annotations,
        args.geometry_report,
        args.owner_acceptance,
        args.crop_root,
    )
    rebuilt_bytes = rebuilt.to_json_bytes()
    inventory_bytes, loaded = load_symbol_crop_inventory(args.inventory)
    if inventory_bytes != rebuilt_bytes or loaded.to_json_bytes() != rebuilt_bytes:
        raise SymbolVerticalSliceError(
            "SYMBOL_VERTICAL_SLICE_INVENTORY_DRIFT",
            "The accepted v16 geometry no longer reproduces the symbol inventory.",
        )
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    return inventory_bytes, rebuilt, elapsed_ms


def _dataset_metadata(
    *,
    dataset: Mapping[str, object],
    dataset_bytes: bytes,
    inventory: SymbolCropInventory,
    inventory_bytes: bytes,
    samples: Sequence[ClassifierSample],
) -> dict[str, Mapping[str, object]]:
    sample_count = _integer(dataset.get("sampleCount"), "dataset.sampleCount")
    pending_count = _integer(dataset.get("pendingCount"), "dataset.pendingCount")
    rejected_count = _integer(dataset.get("rejectedCount"), "dataset.rejectedCount")
    if (
        dataset.get("status") != "ready"
        or sample_count <= 0
        or len(samples) != sample_count
        or rejected_count != 0
        or sample_count + pending_count + rejected_count != len(inventory.samples)
        or _sha256(dataset.get("inventorySha256"), "dataset.inventorySha256")
        != _digest(inventory_bytes)
    ):
        raise SymbolVerticalSliceError(
            "SYMBOL_VERTICAL_SLICE_DATASET_DRIFT",
            "The labeled dataset does not match the accepted inventory.",
        )
    inventory_by_id = {sample.sample_id: sample for sample in inventory.samples}
    rows: dict[str, Mapping[str, object]] = {}
    for raw_row in _sequence(dataset.get("samples"), "dataset.samples"):
        row = _mapping(raw_row, "dataset.sample")
        sample_id = _sha256(row.get("sampleId"), "sampleId")
        source = inventory_by_id.get(sample_id)
        if (
            source is None
            or sample_id in rows
            or row.get("geometryStatus") != "accepted"
            or row.get("boardId") != source.board_id
            or row.get("cropSampleId") != source.crop_sample_id
            or row.get("cropChecksumSha256") != source.crop_checksum_sha256
            or row.get("cellIndex") != source.cell_index
            or row.get("sequenceNumber") != source.sequence_number
        ):
            raise SymbolVerticalSliceError(
                "SYMBOL_VERTICAL_SLICE_DATASET_SAMPLE_DRIFT",
                "A labeled sample differs from its accepted geometry observation.",
            )
        rows[sample_id] = row
    if set(rows) != {sample.sample_id for sample in samples}:
        raise SymbolVerticalSliceError(
            "SYMBOL_VERTICAL_SLICE_DATASET_SAMPLE_DRIFT",
            "The classifier sample set is incomplete or contains unknown samples.",
        )
    return rows


def _verified_onnx(
    *,
    report_path: Path,
    artifact_path: Path,
    dataset_sha256: str,
    split_sha256: str,
    class_codes: tuple[str, ...],
) -> tuple[LocalSymbolOnnxAdapter, Mapping[str, object], bytes, str, str]:
    report_bytes, report = _load_json(
        report_path,
        "SYMBOL_VERTICAL_SLICE_ONNX_REPORT_INVALID",
    )
    artifact = _mapping(report.get("artifact"), "onnx.artifact")
    artifact_sha256 = _sha256(artifact.get("sha256"), "onnx.artifact.sha256")
    report_classes = tuple(
        _text(_mapping(row, "onnx.class").get("symbolCode"), "symbolCode")
        for row in _sequence(report.get("classes"), "onnx.classes")
    )
    graph_input = _mapping(
        _mapping(report.get("graph"), "onnx.graph").get("input"),
        "onnx.graph.input",
    )
    shape = _sequence(graph_input.get("shape"), "onnx.graph.input.shape")
    if (
        report.get("status") != "bootstrap"
        or report.get("datasetSha256") != dataset_sha256
        or report.get("splitSha256") != split_sha256
        or report_classes != class_codes
        or len(shape) != 4
        or shape[0] != "batch"
        or shape[1] != 3
        or not isinstance(shape[2], int)
        or shape[2] != shape[3]
    ):
        raise SymbolVerticalSliceError(
            "SYMBOL_VERTICAL_SLICE_ONNX_PROVENANCE_DRIFT",
            "ONNX report, graph, classes or source dataset differ.",
        )
    adapter = LocalSymbolOnnxAdapter(
        artifact_path,
        expected_sha256=artifact_sha256,
        class_codes=class_codes,
        input_size=shape[2],
    )
    return (
        adapter,
        report,
        report_bytes,
        _text(report.get("modelVersion"), "onnx.modelVersion"),
        artifact_sha256,
    )


def _verified_calibration(
    *,
    path: Path,
    dataset_sha256: str,
    split_sha256: str,
    onnx_report_sha256: str,
    onnx_artifact_sha256: str,
    model_version: str,
) -> tuple[bytes, Mapping[str, object], float, Mapping[str, object]]:
    content, report = _load_json(
        path,
        "SYMBOL_VERTICAL_SLICE_CALIBRATION_INVALID",
    )
    inputs = _mapping(report.get("inputs"), "calibration.inputs")
    policy = _mapping(report.get("policy"), "calibration.policy")
    auto_accept = _mapping(policy.get("autoAccept"), "policy.autoAccept")
    auto_reject = _mapping(policy.get("automaticReject"), "policy.automaticReject")
    manual_review = _mapping(policy.get("manualReview"), "policy.manualReview")
    temperature = report.get("temperature")
    if (
        report.get("status") != "bootstrap_manual_review_only"
        or inputs.get("datasetSha256") != dataset_sha256
        or inputs.get("splitSha256") != split_sha256
        or inputs.get("onnxReportSha256") != onnx_report_sha256
        or inputs.get("onnxArtifactSha256") != onnx_artifact_sha256
        or inputs.get("modelVersion") != model_version
        or not isinstance(temperature, int | float)
        or isinstance(temperature, bool)
        or float(temperature) <= 0.0
        or auto_accept.get("enabled") is not False
        or auto_reject.get("enabled") is not False
        or manual_review.get("enabled") is not True
    ):
        raise SymbolVerticalSliceError(
            "SYMBOL_VERTICAL_SLICE_CALIBRATION_DRIFT",
            "Calibration provenance or fail-closed review policy differs.",
        )
    return content, report, float(temperature), policy


def _verified_selection(
    *,
    path: Path,
    class_codes: tuple[str, ...],
    dataset_sha256: str,
    split_sha256: str,
    inventory_sha256: str,
    calibration_sha256: str,
    model_version: str,
    onnx_artifact_sha256: str,
    temperature: float,
) -> tuple[bytes, Mapping[str, object]]:
    content, report = _load_json(
        path,
        "SYMBOL_VERTICAL_SLICE_SELECTION_INVALID",
    )
    canonical = canonical_selection_bytes(report)
    if canonical != content:
        raise SymbolVerticalSliceError(
            "SYMBOL_VERTICAL_SLICE_SELECTION_NOT_CANONICAL",
            "The active-learning selection is not canonical JSON.",
        )
    validated = validate_review_selection(
        report,
        source_report_sha256=_digest(content),
        active_symbol_codes=class_codes,
    )
    if (
        validated.dataset_sha256 != dataset_sha256
        or validated.split_sha256 != split_sha256
        or validated.inventory_sha256 != inventory_sha256
        or validated.calibration_report_sha256 != calibration_sha256
        or validated.model_version != model_version
        or validated.model_artifact_sha256 != onnx_artifact_sha256
        or not np.isclose(validated.temperature, temperature, atol=1e-12)
    ):
        raise SymbolVerticalSliceError(
            "SYMBOL_VERTICAL_SLICE_SELECTION_PROVENANCE_DRIFT",
            "The review batch does not reference the accepted model and data chain.",
        )
    return content, report


def _batches[T](values: Sequence[T]) -> tuple[Sequence[T], ...]:
    return tuple(
        values[index : index + INFERENCE_BATCH_SIZE]
        for index in range(0, len(values), INFERENCE_BATCH_SIZE)
    )


def _infer(
    adapter: LocalSymbolOnnxAdapter,
    samples: Sequence[ClassifierSample],
    *,
    timing_runs: int,
) -> tuple[np.ndarray, float, tuple[float, ...]]:
    if not 1 <= timing_runs <= 20:
        raise SymbolVerticalSliceError(
            "SYMBOL_VERTICAL_SLICE_TIMING_RUNS_INVALID",
            "timing-runs must remain between 1 and 20.",
        )
    preprocessing_started = time.perf_counter_ns()
    tensors = tuple(
        tensor_batch_to_numpy(
            torch.stack(
                [load_image_tensor(sample.asset_path, adapter.input_size) for sample in batch]
            )
        )
        for batch in _batches(samples)
    )
    preprocessing_ms = (time.perf_counter_ns() - preprocessing_started) / 1_000_000
    adapter.infer(tensors[0])
    durations: list[float] = []
    first_logits: list[np.ndarray] = []
    for run_index in range(timing_runs):
        started = time.perf_counter_ns()
        outputs = [adapter.infer(batch).logits for batch in tensors]
        durations.append((time.perf_counter_ns() - started) / 1_000_000)
        if run_index == 0:
            first_logits = outputs
    return np.concatenate(first_logits).astype(np.float64), preprocessing_ms, tuple(durations)


def _split_metrics(
    samples: Sequence[EvaluatedSymbolSample],
    probabilities: np.ndarray,
    labels: np.ndarray,
    class_codes: tuple[str, ...],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for split_name in ("train", "validation", "test"):
        indexes = [index for index, sample in enumerate(samples) if sample.split == split_name]
        _, metrics = evaluate_probabilities(
            sample_ids=[samples[index].sample_id for index in indexes],
            board_ids=[samples[index].board_id for index in indexes],
            cell_indexes=[samples[index].cell_index for index in indexes],
            split_names=[split_name] * len(indexes),
            probabilities=probabilities[indexes],
            labels=labels[indexes],
            class_codes=class_codes,
        )
        result[split_name] = metrics
    return result


def _validate_review_replay(
    samples: Sequence[EvaluatedSymbolSample],
    class_codes: tuple[str, ...],
) -> int:
    boards: dict[str, list[EvaluatedSymbolSample]] = defaultdict(list)
    for sample in samples:
        boards[sample.board_id].append(sample)
    validated_count = 0
    for board_samples in boards.values():
        if len(board_samples) != 15 or {sample.cell_index for sample in board_samples} != set(
            range(15)
        ):
            continue
        ordered = sorted(board_samples, key=lambda value: value.cell_index)
        changed = any(
            sample.expected_symbol_code != sample.predicted_symbol_code for sample in ordered
        )
        snapshot = {
            "cells": [
                {
                    "cellIndex": sample.cell_index,
                    "predictedSymbolCode": sample.predicted_symbol_code,
                    "sampleId": sample.sample_id,
                }
                for sample in ordered
            ]
        }
        labels = [
            {
                "cellIndex": sample.cell_index,
                "sampleId": sample.sample_id,
                "symbolCode": sample.expected_symbol_code,
            }
            for sample in ordered
        ]
        validate_review_resolution(
            action=(ReviewResolutionAction.CORRECT if changed else ReviewResolutionAction.ACCEPT),
            geometry_accepted=True,
            labels=labels,
            rejection_reason=None,
            resolved_by="m6-acceptance-runner",
            prediction_snapshot=snapshot,
            active_symbol_codes=class_codes,
        )
        validated_count += 1
    return validated_count


def _runtime_observation(
    *,
    inventory_ms: float,
    preprocessing_ms: float,
    durations: Sequence[float],
    sample_count: int,
) -> dict[str, object]:
    median = statistics.median(durations)
    return {
        "inferenceBatchSize": INFERENCE_BATCH_SIZE,
        "inferenceMaximumMilliseconds": round(max(durations), 4),
        "inferenceMedianMilliseconds": round(median, 4),
        "inferenceMedianMillisecondsPerSample": round(median / sample_count, 6),
        "inferenceMinimumMilliseconds": round(min(durations), 4),
        "inventoryVerificationMilliseconds": round(inventory_ms, 4),
        "onnxRuntimeVersion": onnxruntime.__version__,
        "preprocessingMilliseconds": round(preprocessing_ms, 4),
        "sampleCount": sample_count,
        "timingRuns": len(durations),
    }


def _build_report(args: argparse.Namespace) -> dict[str, object]:
    inventory_bytes, inventory, inventory_ms = _verify_inventory(args)
    prepared = prepare_training_data(args.dataset, args.split, args.dataset_assets)
    dataset_bytes, dataset = _load_json(
        args.dataset,
        "SYMBOL_VERTICAL_SLICE_DATASET_INVALID",
    )
    ordered_samples = prepared.train + prepared.validation + prepared.test
    metadata = _dataset_metadata(
        dataset=dataset,
        dataset_bytes=dataset_bytes,
        inventory=inventory,
        inventory_bytes=inventory_bytes,
        samples=ordered_samples,
    )
    adapter, onnx_report, onnx_report_bytes, model_version, onnx_artifact_sha256 = _verified_onnx(
        report_path=args.onnx_report,
        artifact_path=args.onnx_artifact,
        dataset_sha256=prepared.dataset_sha256,
        split_sha256=prepared.split_sha256,
        class_codes=prepared.class_codes,
    )
    calibration_bytes, calibration, temperature, policy = _verified_calibration(
        path=args.calibration,
        dataset_sha256=prepared.dataset_sha256,
        split_sha256=prepared.split_sha256,
        onnx_report_sha256=_digest(onnx_report_bytes),
        onnx_artifact_sha256=onnx_artifact_sha256,
        model_version=model_version,
    )
    selection_bytes, selection = _verified_selection(
        path=args.selection,
        class_codes=prepared.class_codes,
        dataset_sha256=prepared.dataset_sha256,
        split_sha256=prepared.split_sha256,
        inventory_sha256=_digest(inventory_bytes),
        calibration_sha256=_digest(calibration_bytes),
        model_version=model_version,
        onnx_artifact_sha256=onnx_artifact_sha256,
        temperature=temperature,
    )
    timing_runs = 1 if args.check else args.timing_runs
    logits, preprocessing_ms, durations = _infer(
        adapter,
        ordered_samples,
        timing_runs=timing_runs,
    )
    probabilities = calibrated_probabilities(logits, temperature)
    labels = np.asarray([sample.class_index for sample in ordered_samples], dtype=np.int64)
    split_names = (
        ("train",) * len(prepared.train)
        + ("validation",) * len(prepared.validation)
        + ("test",) * len(prepared.test)
    )
    evaluated, overall_metrics = evaluate_probabilities(
        sample_ids=[sample.sample_id for sample in ordered_samples],
        board_ids=[
            _text(metadata[sample.sample_id].get("boardId"), "boardId")
            for sample in ordered_samples
        ],
        cell_indexes=[
            _integer(metadata[sample.sample_id].get("cellIndex"), "cellIndex")
            for sample in ordered_samples
        ],
        split_names=split_names,
        probabilities=probabilities,
        labels=labels,
        class_codes=prepared.class_codes,
    )
    replay = build_review_replay(evaluated)
    resolved_sample_count = _integer(
        replay.get("resolvedSampleCount"),
        "reviewReplay.resolvedSampleCount",
    )
    partial_sample_count = _integer(
        replay.get("partialSampleCount"),
        "reviewReplay.partialSampleCount",
    )
    if resolved_sample_count + partial_sample_count != len(evaluated):
        raise SymbolVerticalSliceError(
            "SYMBOL_VERTICAL_SLICE_REVIEW_CORPUS_DRIFT",
            "The complete and partial review corpus does not cover the dataset.",
        )
    validated_resolution_count = _validate_review_replay(evaluated, prepared.class_codes)
    if validated_resolution_count != replay["completeBoardCount"]:
        raise SymbolVerticalSliceError(
            "SYMBOL_VERTICAL_SLICE_REVIEW_REPLAY_INVALID",
            "Not every complete golden board passed the review resolution contract.",
        )

    if args.check:
        _, existing = _load_json(
            args.output,
            "SYMBOL_VERTICAL_SLICE_REPORT_MISSING",
        )
        runtime = validate_runtime_observation(
            _mapping(existing.get("runtimeObservation"), "runtimeObservation")
        )
    else:
        runtime = _runtime_observation(
            inventory_ms=inventory_ms,
            preprocessing_ms=preprocessing_ms,
            durations=durations,
            sample_count=len(evaluated),
        )

    complete_board_ids = {
        _text(value, "completeBoardId")
        for value in _sequence(replay.get("completeBoardIds"), "completeBoardIds")
    }
    class_counts = Counter(
        sample.expected_symbol_code for sample in evaluated if sample.board_id in complete_board_ids
    )
    auto_accept = _mapping(policy.get("autoAccept"), "policy.autoAccept")
    auto_accept_enabled = auto_accept.get("enabled") is True
    return {
        "automaticQuality": {
            "overall": overall_metrics,
            "splits": _split_metrics(
                evaluated,
                probabilities,
                labels,
                prepared.class_codes,
            ),
        },
        "geometry": {
            "acceptedBoardCount": len({sample.sequence_number for sample in inventory.samples}),
            "acceptedCellCount": len(inventory.samples),
            "cropperVersion": inventory.cropper_version,
            "inventoryVersion": inventory.inventory_version,
            "trainingAllowed": inventory.to_dict().get("trainingAllowed") is True,
        },
        "goldenCorpus": {
            "inferredSampleCount": len(evaluated),
            "sourceImageCount": len({sample.source_image_checksum for sample in ordered_samples}),
            "splitCounts": {
                "test": len(prepared.test),
                "train": len(prepared.train),
                "validation": len(prepared.validation),
            },
        },
        "manualReview": {
            **replay,
            "manualReviewRequiredCount": len(evaluated),
            "manualReviewShare": 1.0,
            "postReviewPerSymbol": [
                {
                    "accuracy": 1.0,
                    "recall": 1.0,
                    "support": class_counts[code],
                    "symbolCode": code,
                }
                for code in prepared.class_codes
            ],
            "validatedResolutionCount": validated_resolution_count,
        },
        "model": {
            "adapterVersion": onnx_report.get("adapterVersion"),
            "autoAcceptEnabled": auto_accept_enabled,
            "autoAcceptReasonCodes": auto_accept.get("reasonCodes"),
            "automaticRejectEnabled": _mapping(
                policy.get("automaticReject"),
                "policy.automaticReject",
            ).get("enabled"),
            "confidencePolicyVersion": policy.get("policyVersion"),
            "modelVersion": model_version,
            "readiness": (
                "auto_accept_ready"
                if auto_accept_enabled
                else "retraining_required_before_auto_accept"
            ),
            "temperature": temperature,
        },
        "predictions": [sample.to_dict(model_version=model_version) for sample in evaluated],
        "provenance": {
            "calibrationReportSha256": _digest(calibration_bytes),
            "datasetSha256": prepared.dataset_sha256,
            "geometryReportSha256": _digest(args.geometry_report.read_bytes()),
            "inventorySha256": _digest(inventory_bytes),
            "onnxArtifactSha256": onnx_artifact_sha256,
            "onnxReportSha256": _digest(onnx_report_bytes),
            "ownerAcceptanceSha256": _digest(args.owner_acceptance.read_bytes()),
            "selectionReportSha256": _digest(selection_bytes),
            "splitSha256": prepared.split_sha256,
        },
        "qualityGate": {
            "autoAcceptQualityPassed": auto_accept_enabled,
            "massImportAllowed": auto_accept_enabled,
            "nextAction": (
                "start_large_dataset_publication"
                if auto_accept_enabled
                else "collect_review_feedback_and_retrain"
            ),
            "reviewBatchContractPassed": True,
            "verticalSlicePassed": True,
        },
        "reviewBatch": {
            "activeLearningVersion": selection.get("activeLearningVersion"),
            "selectedBoardCount": selection.get("selectedBoardCount"),
            "status": selection.get("status"),
        },
        "runtimeObservation": runtime,
        "schemaVersion": 1,
        "status": "passed",
        "verticalSliceVersion": VERTICAL_SLICE_VERSION,
    }


def main() -> int:
    args = _args()
    try:
        report = _build_report(args)
        content = canonical_report_bytes(report)
        if args.check:
            try:
                existing = args.output.read_bytes()
            except OSError as error:
                raise SymbolVerticalSliceError(
                    "SYMBOL_VERTICAL_SLICE_REPORT_MISSING",
                    "The expected acceptance report cannot be read.",
                ) from error
            if existing != content:
                raise SymbolVerticalSliceError(
                    "SYMBOL_VERTICAL_SLICE_REPORT_DRIFT",
                    "The acceptance report differs from the verified input chain.",
                )
        else:
            _write_atomic(args.output, content)
        report_model = _mapping(report.get("model"), "report.model")
        report_golden = _mapping(report.get("goldenCorpus"), "report.goldenCorpus")
        print(
            json.dumps(
                {
                    "autoAcceptEnabled": report_model.get("autoAcceptEnabled"),
                    "reportSha256": _digest(content),
                    "sampleCount": report_golden.get("inferredSampleCount"),
                    "status": report.get("status"),
                },
                sort_keys=True,
            )
        )
        return int(args.require_pass and report.get("status") != "passed")
    except (OSError, SymbolVerticalSliceError, ValueError) as error:
        code = getattr(error, "code", "SYMBOL_VERTICAL_SLICE_FAILED")
        print(json.dumps({"code": code, "message": str(error)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
