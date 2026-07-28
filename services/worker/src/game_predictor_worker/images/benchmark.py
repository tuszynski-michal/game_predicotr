"""Auditable quality, size, and timing report for the M5 image prototype."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, cast

BENCHMARK_VERSION = "m5-image-benchmark-v1"
EXPECTED_IMAGE_COUNT = 12
EXPECTED_POSITION_COUNT = 108
EXPECTED_BOARD_COUNT = 108
EXPECTED_CELL_COUNT = 1620
TIMING_STAGES = (
    "discovery",
    "normalization",
    "geometry",
    "boardCrops",
    "baselineOcr",
    "alternativeOcr",
)


class ImageBenchmarkError(ValueError):
    """Stable benchmark assembly or validation error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ImageBenchmarkError("M5_BENCHMARK_INPUT_INVALID", f"{label} must be an object.")
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise ImageBenchmarkError("M5_BENCHMARK_INPUT_INVALID", f"{label} must be an array.")
    return cast(Sequence[object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ImageBenchmarkError(
            "M5_BENCHMARK_INPUT_INVALID",
            f"{label} must be a non-empty string.",
        )
    return value


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ImageBenchmarkError(
            "M5_BENCHMARK_INPUT_INVALID",
            f"{label} must be an integer.",
        )
    return value


def _number(value: object, label: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ImageBenchmarkError(
            "M5_BENCHMARK_INPUT_INVALID",
            f"{label} must be a number.",
        )
    result = float(value)
    if not math.isfinite(result):
        raise ImageBenchmarkError(
            "M5_BENCHMARK_INPUT_INVALID",
            f"{label} must be finite.",
        )
    return result


def _load(path: Path, label: str) -> tuple[bytes, Mapping[str, object]]:
    try:
        content = path.read_bytes()
        value: Any = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise ImageBenchmarkError(
            "M5_BENCHMARK_INPUT_UNREADABLE",
            f"{label} cannot be read.",
        ) from error
    return content, _mapping(value, label)


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ImageBenchmarkError(
            "M5_BENCHMARK_TIMING_INVALID",
            "Timing samples cannot be empty.",
        )
    rank = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[rank]


def _timing_summary(
    timing_samples: Mapping[str, Sequence[float]],
    image_count: int,
) -> dict[str, object]:
    if set(timing_samples) != set(TIMING_STAGES):
        raise ImageBenchmarkError(
            "M5_BENCHMARK_TIMING_INVALID",
            "Timing samples must contain every benchmark stage exactly once.",
        )
    stages: dict[str, object] = {}
    for stage in TIMING_STAGES:
        samples = tuple(
            round(_number(value, f"timing.{stage}"), 6) for value in timing_samples[stage]
        )
        if len(samples) < 3 or any(value <= 0 for value in samples):
            raise ImageBenchmarkError(
                "M5_BENCHMARK_TIMING_INVALID",
                "Every stage requires at least three positive timing samples.",
            )
        p50 = round(_percentile(samples, 0.50), 6)
        p95 = round(_percentile(samples, 0.95), 6)
        stages[stage] = {
            "iterations": len(samples),
            "p50Ms": p50,
            "p95Ms": p95,
            "p95MsPerImage": round(p95 / image_count, 6),
            "samplesMs": list(samples),
        }
    return {
        "clock": "perf_counter_ns",
        "measurementMode": "local-cpu-existing-immutable-artifacts",
        "stages": stages,
    }


def _safe_artifact(root: Path, value: object, label: str) -> Path:
    relative = PurePosixPath(_text(value, label))
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ImageBenchmarkError(
            "M5_BENCHMARK_ARTIFACT_PATH_UNSAFE",
            f"{label} must be a safe relative POSIX path.",
        )
    try:
        base = root.resolve(strict=True)
        path = (base / Path(*relative.parts)).resolve(strict=True)
    except OSError as error:
        raise ImageBenchmarkError(
            "M5_BENCHMARK_ARTIFACT_MISSING",
            f"{label} does not exist.",
        ) from error
    if not base.is_dir() or not path.is_relative_to(base) or not path.is_file():
        raise ImageBenchmarkError(
            "M5_BENCHMARK_ARTIFACT_PATH_UNSAFE",
            f"{label} is outside its artifact root.",
        )
    return path


def _artifact_summary(
    root: Path,
    references: Sequence[tuple[object, object, str]],
) -> dict[str, object]:
    unique: dict[str, tuple[Path, str]] = {}
    for relative, checksum_value, label in references:
        path = _safe_artifact(root, relative, label)
        checksum = _text(checksum_value, f"{label}.checksum")
        if len(checksum) != 64 or checksum != _sha256(path.read_bytes()):
            raise ImageBenchmarkError(
                "M5_BENCHMARK_ARTIFACT_CHECKSUM_MISMATCH",
                f"{label} checksum differs from its report.",
            )
        relative_text = _text(relative, label)
        if relative_text in unique and unique[relative_text][1] != checksum:
            raise ImageBenchmarkError(
                "M5_BENCHMARK_ARTIFACT_REFERENCE_CONFLICT",
                f"{label} has conflicting checksums.",
            )
        unique[relative_text] = (path, checksum)
    return {
        "referencedFileCount": len(unique),
        "totalBytes": sum(path.stat().st_size for path, _ in unique.values()),
    }


def _normalization_references(report: Mapping[str, object]) -> list[tuple[object, object, str]]:
    result: list[tuple[object, object, str]] = []
    for index, value in enumerate(_sequence(report.get("images"), "normalization.images")):
        image = _mapping(value, f"normalization.images[{index}]")
        result.append(
            (
                image.get("normalizedRelativePath"),
                image.get("normalizedChecksumSha256"),
                f"normalization.images[{index}].normalized",
            )
        )
        diagnostic_path = image.get("diagnosticRelativePath")
        diagnostic = _safe_artifact_placeholder_checksum
        result.append(
            (
                diagnostic_path,
                diagnostic,
                f"normalization.images[{index}].diagnostic",
            )
        )
    return result


_safe_artifact_placeholder_checksum = "__COMPUTE__"


def _artifact_summary_with_computed(
    root: Path,
    references: Sequence[tuple[object, object, str]],
) -> dict[str, object]:
    expanded: list[tuple[object, object, str]] = []
    for relative, checksum, label in references:
        if checksum == _safe_artifact_placeholder_checksum:
            path = _safe_artifact(root, relative, label)
            checksum = _sha256(path.read_bytes())
        expanded.append((relative, checksum, label))
    return _artifact_summary(root, expanded)


def _detection_references(report: Mapping[str, object]) -> list[tuple[object, object, str]]:
    return [
        (
            item.get("overlayRelativePath"),
            item.get("overlayChecksumSha256"),
            f"detection.detections[{index}].overlay",
        )
        for index, value in enumerate(_sequence(report.get("detections"), "detection.detections"))
        for item in [_mapping(value, f"detection.detections[{index}]")]
    ]


def _crop_references(report: Mapping[str, object]) -> list[tuple[object, object, str]]:
    result: list[tuple[object, object, str]] = []
    for image_index, value in enumerate(_sequence(report.get("images"), "crops.images")):
        image = _mapping(value, f"crops.images[{image_index}]")
        for board_index, board_value in enumerate(
            _sequence(image.get("boards"), f"crops.images[{image_index}].boards")
        ):
            board = _mapping(board_value, f"crops.images[{image_index}].boards[{board_index}]")
            prefix = f"crops.images[{image_index}].boards[{board_index}]"
            result.extend(
                [
                    (
                        board.get("boardRelativePath"),
                        board.get("boardChecksumSha256"),
                        f"{prefix}.board",
                    ),
                    (
                        board.get("overlayRelativePath"),
                        board.get("overlayChecksumSha256"),
                        f"{prefix}.overlay",
                    ),
                ]
            )
            for cell_index, cell_value in enumerate(
                _sequence(board.get("cells"), f"{prefix}.cells")
            ):
                cell = _mapping(cell_value, f"{prefix}.cells[{cell_index}]")
                result.append(
                    (
                        cell.get("relativePath"),
                        cell.get("checksumSha256"),
                        f"{prefix}.cells[{cell_index}]",
                    )
                )
    return result


def _ocr_references(report: Mapping[str, object], label: str) -> list[tuple[object, object, str]]:
    result: list[tuple[object, object, str]] = []
    for index, value in enumerate(_sequence(report.get("results"), f"{label}.results")):
        item = _mapping(value, f"{label}.results[{index}]")
        result.extend(
            [
                (
                    item.get("rawCropRelativePath"),
                    item.get("rawCropChecksumSha256"),
                    f"{label}.results[{index}].raw",
                ),
                (
                    item.get("processedCropRelativePath"),
                    item.get("processedCropChecksumSha256"),
                    f"{label}.results[{index}].processed",
                ),
            ]
        )
    return result


def _model_summary(root: Path, report: Mapping[str, object], label: str) -> dict[str, object]:
    files = _mapping(report.get("modelFiles"), f"{label}.modelFiles")
    references = [
        (name, checksum, f"{label}.modelFiles.{name}") for name, checksum in files.items()
    ]
    summary = _artifact_summary(root, references)
    return {
        **summary,
        "modelFingerprint": _text(report.get("modelFingerprint"), f"{label}.modelFingerprint"),
        "modelName": _text(report.get("modelName"), f"{label}.modelName"),
    }


def _metric(
    name: str,
    value: float | None,
    threshold: Mapping[str, object],
    *,
    unavailable_reason: str | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "metric": name,
        "thresholdStatus": "proposed",
    }
    if value is None:
        return {
            **result,
            "measurementStatus": "not_measurable",
            "reason": unavailable_reason or "Ground truth is unavailable.",
        }
    result["measurementStatus"] = "measured"
    result["value"] = round(value, 6)
    if "minimum" in threshold:
        limit = _number(threshold["minimum"], f"thresholds.{name}.minimum")
        result["proposedMinimum"] = limit
        result["comparison"] = "meets_proposed" if value >= limit else "below_proposed"
    elif "maximum" in threshold:
        limit = _number(threshold["maximum"], f"thresholds.{name}.maximum")
        result["proposedMaximum"] = limit
        result["comparison"] = "meets_proposed" if value <= limit else "above_proposed"
    else:
        raise ImageBenchmarkError(
            "M5_BENCHMARK_THRESHOLD_INVALID",
            f"Threshold {name} has no minimum or maximum.",
        )
    result["unit"] = threshold.get("unit")
    return result


def _ocr_summary(report: Mapping[str, object]) -> dict[str, object]:
    results = [
        _mapping(value, f"ocr.results[{index}]")
        for index, value in enumerate(_sequence(report.get("results"), "ocr.results"))
    ]
    exact = sum(value.get("exactMatch") is True for value in results)
    conflicts = sum(
        any(
            _text(reason, "reviewReason").startswith("OCR_CONTINUITY_")
            for reason in _sequence(value.get("reviewReasons"), "reviewReasons")
        )
        for value in results
    )
    reviews = sum(bool(_sequence(value.get("reviewReasons"), "reviewReasons")) for value in results)
    return {
        "continuityConflictCount": conflicts,
        "exactAccuracy": round(exact / len(results), 6) if results else 0.0,
        "exactCount": exact,
        "modelFingerprint": report.get("modelFingerprint"),
        "modelName": report.get("modelName"),
        "positionCount": len(results),
        "preprocessingVersion": report.get("preprocessingVersion"),
        "reviewCount": reviews,
        "runtimeName": report.get("runtimeName"),
        "runtimeVersion": report.get("runtimeVersion"),
        "unresolvedContinuityConflictRate": (
            round(conflicts / len(results), 6) if results else 0.0
        ),
    }


def _image_and_condition_metrics(
    corpus: Mapping[str, object],
    ocr: Mapping[str, object],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    corpus_images = {
        _text(image.get("id"), f"corpus.images[{index}].id"): image
        for index, value in enumerate(_sequence(corpus.get("images"), "corpus.images"))
        for image in [_mapping(value, f"corpus.images[{index}]")]
    }
    grouped: dict[str, list[Mapping[str, object]]] = {}
    for index, value in enumerate(_sequence(ocr.get("results"), "ocr.results")):
        item = _mapping(value, f"ocr.results[{index}]")
        grouped.setdefault(_text(item.get("imageId"), f"ocr.results[{index}].imageId"), []).append(
            item
        )
    per_image: list[dict[str, object]] = []
    by_tag: dict[str, list[Mapping[str, object]]] = {}
    for image_id, corpus_image in corpus_images.items():
        results = grouped.get(image_id, [])
        if len(results) != 9:
            raise ImageBenchmarkError(
                "M5_BENCHMARK_OCR_COVERAGE_INVALID",
                f"{image_id} must have exactly nine OCR results.",
            )
        tags = sorted(
            _text(tag, f"{image_id}.conditionTag")
            for tag in _sequence(corpus_image.get("conditionTags"), f"{image_id}.conditionTags")
        )
        for tag in tags:
            by_tag.setdefault(tag, []).extend(results)
        exact = sum(item.get("exactMatch") is True for item in results)
        reviews = sum(
            bool(_sequence(item.get("reviewReasons"), "reviewReasons")) for item in results
        )
        conflicts = sum(
            any(
                _text(reason, "reviewReason").startswith("OCR_CONTINUITY_")
                for reason in _sequence(item.get("reviewReasons"), "reviewReasons")
            )
            for item in results
        )
        per_image.append(
            {
                "conditionTags": tags,
                "exactAccuracy": round(exact / len(results), 6),
                "exactCount": exact,
                "imageId": image_id,
                "positionCount": len(results),
                "reviewCount": reviews,
                "continuityConflictCount": conflicts,
            }
        )
    per_condition: list[dict[str, object]] = []
    for tag, results in sorted(by_tag.items()):
        exact = sum(item.get("exactMatch") is True for item in results)
        reviews = sum(
            bool(_sequence(item.get("reviewReasons"), "reviewReasons")) for item in results
        )
        per_condition.append(
            {
                "conditionTag": tag,
                "exactAccuracy": round(exact / len(results), 6),
                "exactCount": exact,
                "imageCount": len({_text(item.get("imageId"), "ocr.imageId") for item in results}),
                "positionCount": len(results),
                "reviewCount": reviews,
            }
        )
    return per_image, per_condition


def _digit_length_metrics(ocr: Mapping[str, object]) -> list[dict[str, object]]:
    grouped: dict[int, list[Mapping[str, object]]] = {}
    for index, value in enumerate(_sequence(ocr.get("results"), "ocr.results")):
        item = _mapping(value, f"ocr.results[{index}]")
        expected = _integer(item.get("expectedNumber"), f"ocr.results[{index}].expectedNumber")
        grouped.setdefault(len(str(expected)), []).append(item)
    result: list[dict[str, object]] = []
    for length, items in sorted(grouped.items()):
        exact = sum(item.get("exactMatch") is True for item in items)
        result.append(
            {
                "digitLength": length,
                "exactAccuracy": round(exact / len(items), 6),
                "exactCount": exact,
                "positionCount": len(items),
            }
        )
    return result


def _error_catalog(ocr: Mapping[str, object]) -> dict[str, object]:
    errors: list[dict[str, object]] = []
    reasons: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    high_confidence_incorrect = 0
    unrecognized = 0
    for index, value in enumerate(_sequence(ocr.get("results"), "ocr.results")):
        item = _mapping(value, f"ocr.results[{index}]")
        for reason in _sequence(item.get("reviewReasons"), f"ocr.results[{index}].reviewReasons"):
            reasons[_text(reason, "reviewReason")] += 1
        if item.get("exactMatch") is True:
            continue
        expected = str(_integer(item.get("expectedNumber"), "expectedNumber"))
        raw = item.get("rawText")
        raw_text = raw if isinstance(raw, str) else ""
        normalized = item.get("normalizedNumber")
        confidence = _number(item.get("confidence"), "confidence")
        if normalized is None:
            category = "unrecognized"
            unrecognized += 1
        elif len(raw_text) < len(expected):
            category = "deletion_or_missing_digit"
        elif len(raw_text) > len(expected):
            category = "insertion_or_extra_digit"
        else:
            category = "same_length_substitution"
        categories[category] += 1
        if confidence >= 0.8:
            high_confidence_incorrect += 1
        errors.append(
            {
                "confidence": confidence,
                "editCategory": category,
                "expectedNumber": int(expected),
                "imageId": item.get("imageId"),
                "normalizedNumber": normalized,
                "positionIndex": item.get("positionIndex"),
                "rawText": raw_text,
                "reviewReasons": list(_sequence(item.get("reviewReasons"), "reviewReasons")),
            }
        )
    return {
        "categoryCounts": dict(sorted(categories.items())),
        "highConfidenceIncorrectCountAtOrAbove0.8": high_confidence_incorrect,
        "incorrectCount": len(errors),
        "items": errors,
        "reviewReasonCounts": dict(sorted(reasons.items())),
        "unrecognizedCount": unrecognized,
    }


def build_image_benchmark_report(
    *,
    corpus_manifest_path: Path,
    golden_annotations_path: Path,
    source_discovery_path: Path,
    normalization_report_path: Path,
    detection_report_path: Path,
    crop_report_path: Path,
    baseline_ocr_report_path: Path,
    alternative_ocr_report_path: Path,
    thresholds_path: Path,
    normalization_root: Path,
    detection_root: Path,
    crop_root: Path,
    baseline_ocr_root: Path,
    alternative_ocr_root: Path,
    baseline_model_root: Path,
    alternative_model_root: Path,
    timing_samples: Mapping[str, Sequence[float]],
    environment: Mapping[str, object],
) -> dict[str, object]:
    """Build the deterministic portion of a benchmark from measured inputs."""

    corpus_bytes, corpus = _load(corpus_manifest_path, "corpusManifest")
    golden_bytes, _ = _load(golden_annotations_path, "goldenAnnotations")
    discovery_bytes, discovery = _load(source_discovery_path, "sourceDiscovery")
    normalization_bytes, normalization = _load(normalization_report_path, "normalization")
    detection_bytes, detection = _load(detection_report_path, "detection")
    crop_bytes, crops = _load(crop_report_path, "crops")
    baseline_bytes, baseline = _load(baseline_ocr_report_path, "baselineOcr")
    alternative_bytes, alternative = _load(alternative_ocr_report_path, "alternativeOcr")
    thresholds_bytes, thresholds = _load(thresholds_path, "thresholds")

    corpus_id = _text(corpus.get("corpusId"), "corpus.corpusId")
    image_count = _integer(corpus.get("imageCount"), "corpus.imageCount")
    if (
        corpus_id != thresholds.get("corpusId")
        or thresholds.get("status") != "proposed"
        or image_count != EXPECTED_IMAGE_COUNT
    ):
        raise ImageBenchmarkError(
            "M5_BENCHMARK_CORPUS_MISMATCH",
            "Corpus and proposed thresholds do not match the expected prototype.",
        )
    input_sha = {
        "alternativeOcrReportSha256": _sha256(alternative_bytes),
        "baselineOcrReportSha256": _sha256(baseline_bytes),
        "boardCropReportSha256": _sha256(crop_bytes),
        "corpusManifestSha256": _sha256(corpus_bytes),
        "detectionReportSha256": _sha256(detection_bytes),
        "goldenAnnotationsSha256": _sha256(golden_bytes),
        "normalizationReportSha256": _sha256(normalization_bytes),
        "sourceDiscoverySha256": _sha256(discovery_bytes),
        "thresholdsSha256": _sha256(thresholds_bytes),
    }
    if (
        normalization.get("sourceManifestSha256") != input_sha["sourceDiscoverySha256"]
        or detection.get("normalizationReportSha256") != input_sha["normalizationReportSha256"]
        or crops.get("normalizationReportSha256") != input_sha["normalizationReportSha256"]
        or crops.get("detectionReportSha256") != input_sha["detectionReportSha256"]
    ):
        raise ImageBenchmarkError(
            "M5_BENCHMARK_UPSTREAM_DRIFT",
            "Geometry reports do not form one checksum-linked chain.",
        )
    for label, report in (("baseline", baseline), ("alternative", alternative)):
        if (
            report.get("corpusManifestSha256") != input_sha["corpusManifestSha256"]
            or report.get("goldenAnnotationsSha256") != input_sha["goldenAnnotationsSha256"]
            or report.get("normalizationReportSha256") != input_sha["normalizationReportSha256"]
            or report.get("detectionReportSha256") != input_sha["detectionReportSha256"]
        ):
            raise ImageBenchmarkError(
                "M5_BENCHMARK_UPSTREAM_DRIFT",
                f"{label} OCR report does not match benchmark inputs.",
            )
    if (
        discovery.get("uniqueImageCount") != image_count
        or detection.get("imageCount") != image_count
        or crops.get("imageCount") != image_count
        or baseline.get("positionCount") != EXPECTED_POSITION_COUNT
        or alternative.get("positionCount") != EXPECTED_POSITION_COUNT
        or crops.get("boardCount") != EXPECTED_BOARD_COUNT
        or crops.get("cellCount") != EXPECTED_CELL_COUNT
    ):
        raise ImageBenchmarkError(
            "M5_BENCHMARK_COVERAGE_INVALID",
            "An upstream report does not cover the complete prototype corpus.",
        )

    threshold_metrics = _mapping(thresholds.get("metrics"), "thresholds.metrics")
    detected_count = _integer(detection.get("detectedCount"), "detection.detectedCount")
    all_nine = sum(
        item.get("result") is not None
        and _mapping(item.get("result"), "detection.result").get("status") == "detected"
        and len(
            _sequence(
                _mapping(item.get("result"), "detection.result").get("boards"),
                "detection.result.boards",
            )
        )
        == 9
        for value in _sequence(detection.get("detections"), "detection.detections")
        for item in [_mapping(value, "detection.item")]
    )
    baseline_summary = _ocr_summary(baseline)
    alternative_summary = _ocr_summary(alternative)
    metrics = [
        _metric(
            "pageDetectionRate",
            detected_count / image_count,
            _mapping(threshold_metrics.get("pageDetectionRate"), "pageDetectionRate"),
        ),
        _metric(
            "allNineBoardsDetectionRate",
            all_nine / image_count,
            _mapping(
                threshold_metrics.get("allNineBoardsDetectionRate"),
                "allNineBoardsDetectionRate",
            ),
        ),
        _metric(
            "boardPositionAssignmentAccuracy",
            None,
            _mapping(
                threshold_metrics.get("boardPositionAssignmentAccuracy"),
                "boardPositionAssignmentAccuracy",
            ),
            unavailable_reason=(
                "Golden annotations contain sequence numbers but no independent board positions."
            ),
        ),
        _metric(
            "boardCornerErrorP95",
            None,
            _mapping(threshold_metrics.get("boardCornerErrorP95"), "boardCornerErrorP95"),
            unavailable_reason="Independent golden board corners are not available.",
        ),
        _metric(
            "sequenceNumberExactAccuracy",
            _number(baseline_summary["exactAccuracy"], "baseline.exactAccuracy"),
            _mapping(
                threshold_metrics.get("sequenceNumberExactAccuracy"),
                "sequenceNumberExactAccuracy",
            ),
        ),
        _metric(
            "unresolvedContinuityConflictRate",
            _number(
                baseline_summary["unresolvedContinuityConflictRate"],
                "baseline.unresolvedContinuityConflictRate",
            ),
            _mapping(
                threshold_metrics.get("unresolvedContinuityConflictRate"),
                "unresolvedContinuityConflictRate",
            ),
        ),
    ]
    per_image, per_condition = _image_and_condition_metrics(corpus, baseline)
    artifact_sizes = {
        "alternativeModel": _model_summary(alternative_model_root, alternative, "alternative"),
        "alternativeOcr": _artifact_summary(
            alternative_ocr_root,
            _ocr_references(alternative, "alternativeOcr"),
        ),
        "baselineModel": _model_summary(baseline_model_root, baseline, "baseline"),
        "baselineOcr": _artifact_summary(
            baseline_ocr_root,
            _ocr_references(baseline, "baselineOcr"),
        ),
        "boardCrops": _artifact_summary(crop_root, _crop_references(crops)),
        "geometry": _artifact_summary(
            detection_root,
            _detection_references(detection),
        ),
        "normalization": _artifact_summary_with_computed(
            normalization_root,
            _normalization_references(normalization),
        ),
    }
    return {
        "artifactSizes": artifact_sizes,
        "benchmarkVersion": BENCHMARK_VERSION,
        "corpus": {
            "corpusId": corpus_id,
            "imageCount": image_count,
            "limitations": list(_sequence(corpus.get("limitations"), "corpus.limitations")),
            "sourceGroupCount": corpus.get("sourceGroupCount"),
            "status": corpus.get("status"),
        },
        "decision": {
            "g5Status": "not_passed",
            "recommendation": "rework",
            "reasons": [
                "The corpus has 12 images from one game/session, below the 20-image minimum.",
                "Independent board position and corner ground truth is unavailable.",
                "Baseline sequence OCR is below the proposed exact-accuracy threshold.",
                "Baseline continuity conflicts exceed the proposed maximum.",
            ],
            "thresholdsAccepted": False,
        },
        "digitLengthMetrics": _digit_length_metrics(baseline),
        "environment": dict(environment),
        "errorCatalog": _error_catalog(baseline),
        "inputs": input_sha,
        "metrics": metrics,
        "ocrComparison": {
            "alternative": alternative_summary,
            "baseline": baseline_summary,
            "selectionDeferredToTask0058": True,
        },
        "perConditionTag": per_condition,
        "perImage": per_image,
        "schemaVersion": 1,
        "status": "measured_rework",
        "timing": _timing_summary(timing_samples, image_count),
    }


def benchmark_json_bytes(report: Mapping[str, object]) -> bytes:
    return (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
