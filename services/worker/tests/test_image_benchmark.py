from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from game_predictor_worker.images.benchmark import (
    ImageBenchmarkError,
    benchmark_json_bytes,
    build_image_benchmark_report,
)


def _write_json(path: Path, value: object) -> bytes:
    content = (json.dumps(value, sort_keys=True) + "\n").encode()
    path.write_bytes(content)
    return content


def _artifact_root(tmp_path: Path, name: str) -> tuple[Path, str]:
    root = tmp_path / name
    root.mkdir()
    content = f"{name}-content".encode()
    (root / "artifact.bin").write_bytes(content)
    return root, hashlib.sha256(content).hexdigest()


def _fixture(tmp_path: Path) -> dict[str, object]:
    roots: dict[str, Path] = {}
    checksums: dict[str, str] = {}
    for name in (
        "normalization-root",
        "detection-root",
        "crop-root",
        "baseline-ocr-root",
        "alternative-ocr-root",
        "baseline-model-root",
        "alternative-model-root",
    ):
        roots[name], checksums[name] = _artifact_root(tmp_path, name)

    corpus = {
        "corpusId": "m5-representative-corpus-v2",
        "imageCount": 12,
        "limitations": ["synthetic"],
        "sourceGroupCount": 1,
        "status": "accepted",
        "images": [
            {
                "conditionTags": ["portrait", f"group-{index % 2}"],
                "expectedBoardCount": 9,
                "height": 1000,
                "id": f"image-{index:02d}",
                "sha256": f"{index + 1:064x}",
                "split": "held_out" if index >= 6 else "development",
                "width": 800,
            }
            for index in range(12)
        ],
    }
    corpus_path = tmp_path / "corpus.json"
    corpus_bytes = _write_json(corpus_path, corpus)
    golden_path = tmp_path / "golden.json"
    board_quad = [
        {"x": 10, "y": 10},
        {"x": 110, "y": 10},
        {"x": 110, "y": 70},
        {"x": 10, "y": 70},
    ]
    golden_bytes = _write_json(
        golden_path,
        {
            "corpusId": corpus["corpusId"],
            "images": [
                {
                    "boards": [
                        {
                            "boardQuad": board_quad,
                            "positionIndex": position,
                        }
                        for position in range(9)
                    ],
                    "imageId": f"image-{index:02d}",
                }
                for index in range(12)
            ],
        },
    )
    discovery_path = tmp_path / "discovery.json"
    discovery_bytes = _write_json(
        discovery_path,
        {"uniqueImageCount": 12, "images": []},
    )
    normalization_path = tmp_path / "normalization.json"
    normalization = {
        "sourceManifestSha256": hashlib.sha256(discovery_bytes).hexdigest(),
        "images": [
            {
                "diagnosticRelativePath": "artifact.bin",
                "normalizedChecksumSha256": checksums["normalization-root"],
                "normalizedRelativePath": "artifact.bin",
                "sourceChecksumSha256": f"{index + 1:064x}",
            }
            for index in range(12)
        ],
    }
    normalization_bytes = _write_json(normalization_path, normalization)
    detection_path = tmp_path / "detection.json"
    detection = {
        "detectedCount": 12,
        "imageCount": 12,
        "normalizationReportSha256": hashlib.sha256(normalization_bytes).hexdigest(),
        "detections": [
            {
                "overlayChecksumSha256": checksums["detection-root"],
                "overlayRelativePath": "artifact.bin",
                "result": {
                    "boards": [
                        {"positionIndex": position, "quad": board_quad} for position in range(9)
                    ],
                    "status": "detected",
                },
                "sourceChecksumSha256": f"{index + 1:064x}",
            }
            for index in range(12)
        ],
    }
    detection_bytes = _write_json(detection_path, detection)
    crop_path = tmp_path / "crops.json"
    crop = {
        "boardCount": 108,
        "cellCount": 1620,
        "detectionReportSha256": hashlib.sha256(detection_bytes).hexdigest(),
        "imageCount": 12,
        "normalizationReportSha256": hashlib.sha256(normalization_bytes).hexdigest(),
        "images": [
            {
                "boards": [
                    {
                        "boardChecksumSha256": checksums["crop-root"],
                        "boardRelativePath": "artifact.bin",
                        "cells": [
                            {
                                "checksumSha256": checksums["crop-root"],
                                "relativePath": "artifact.bin",
                            }
                            for _ in range(15)
                        ],
                        "overlayChecksumSha256": checksums["crop-root"],
                        "overlayRelativePath": "artifact.bin",
                    }
                    for _ in range(9)
                ]
            }
            for _ in range(12)
        ],
    }
    _write_json(crop_path, crop)

    def ocr_report(*, alternative: bool) -> dict[str, object]:
        results: list[dict[str, object]] = []
        number = 1
        for image_index in range(12):
            for position in range(9):
                incorrect = not alternative and number in {50, 51, 52}
                results.append(
                    {
                        "confidence": 0.9,
                        "exactMatch": not incorrect,
                        "expectedNumber": number,
                        "imageId": f"image-{image_index:02d}",
                        "normalizedNumber": 5 if incorrect else number,
                        "positionIndex": position,
                        "processedCropChecksumSha256": checksums[
                            "alternative-ocr-root" if alternative else "baseline-ocr-root"
                        ],
                        "processedCropRelativePath": "artifact.bin",
                        "rawCropChecksumSha256": checksums[
                            "alternative-ocr-root" if alternative else "baseline-ocr-root"
                        ],
                        "rawCropRelativePath": "artifact.bin",
                        "rawText": "5" if incorrect else str(number),
                        "reviewReasons": (["OCR_CONTINUITY_CONFLICT"] if incorrect else []),
                    }
                )
                number += 1
        exact_count = sum(item["exactMatch"] is True for item in results)
        return {
            "continuityConflictCount": 0 if alternative else 3,
            "corpusManifestSha256": hashlib.sha256(corpus_bytes).hexdigest(),
            "detectionReportSha256": hashlib.sha256(detection_bytes).hexdigest(),
            "exactAccuracy": round(exact_count / 108, 6),
            "exactCount": exact_count,
            "goldenAnnotationsSha256": hashlib.sha256(golden_bytes).hexdigest(),
            "modelFiles": {
                "artifact.bin": checksums[
                    "alternative-model-root" if alternative else "baseline-model-root"
                ]
            },
            "modelFingerprint": ("b" if alternative else "a") * 64,
            "modelName": "alternative" if alternative else "baseline",
            "normalizationReportSha256": hashlib.sha256(normalization_bytes).hexdigest(),
            "positionCount": 108,
            "results": results,
            "reviewCount": 0 if alternative else 3,
            "runtimeName": "fake",
            "runtimeVersion": "1",
            "unresolvedContinuityConflictRate": 0.0 if alternative else round(3 / 108, 6),
        }

    baseline_path = tmp_path / "baseline.json"
    _write_json(baseline_path, ocr_report(alternative=False))
    alternative_path = tmp_path / "alternative.json"
    _write_json(alternative_path, ocr_report(alternative=True))
    thresholds_path = tmp_path / "thresholds.json"
    _write_json(
        thresholds_path,
        {
            "corpusId": corpus["corpusId"],
            "status": "accepted",
            "metrics": {
                "expectedBoardSetDetectionRate": {
                    "minimum": 0.9,
                    "unit": "fraction",
                },
                "boardCornerErrorP95": {"maximum": 0.02, "unit": "fraction"},
                "boardPositionAssignmentAccuracy": {
                    "minimum": 0.99,
                    "unit": "fraction",
                },
                "pageDetectionRate": {"minimum": 0.95, "unit": "fraction"},
                "sequenceNumberExactAccuracy": {
                    "minimum": 0.98,
                    "unit": "fraction",
                },
                "unresolvedContinuityConflictRate": {
                    "maximum": 0.02,
                    "unit": "fraction",
                },
            },
        },
    )
    return {
        "alternative_model_root": roots["alternative-model-root"],
        "alternative_ocr_report_path": alternative_path,
        "alternative_ocr_root": roots["alternative-ocr-root"],
        "baseline_model_root": roots["baseline-model-root"],
        "baseline_ocr_report_path": baseline_path,
        "baseline_ocr_root": roots["baseline-ocr-root"],
        "corpus_manifest_path": corpus_path,
        "crop_report_path": crop_path,
        "crop_root": roots["crop-root"],
        "detection_report_path": detection_path,
        "detection_root": roots["detection-root"],
        "environment": {"pythonVersion": "test"},
        "golden_annotations_path": golden_path,
        "normalization_report_path": normalization_path,
        "normalization_root": roots["normalization-root"],
        "source_discovery_path": discovery_path,
        "thresholds_path": thresholds_path,
        "timing_samples": {
            stage: [1.0, 2.0, 3.0]
            for stage in (
                "discovery",
                "normalization",
                "geometry",
                "boardCrops",
                "baselineOcr",
                "alternativeOcr",
            )
        },
    }


def test_benchmark_passes_geometry_with_manual_review_only_ocr(tmp_path: Path) -> None:
    report = build_image_benchmark_report(**_fixture(tmp_path))  # type: ignore[arg-type]

    assert report["status"] == "measured_passed_manual_review_only_ocr"
    assert report["decision"]["g5Status"] == "passed_manual_review_only_ocr"  # type: ignore[index]
    metrics = {item["metric"]: item for item in report["metrics"]}  # type: ignore[union-attr]
    assert metrics["pageDetectionRate"]["comparison"] == "meets_accepted"
    assert metrics["boardCornerErrorP95"]["comparison"] == "meets_accepted"
    assert metrics["sequenceNumberExactAccuracy"]["comparison"] == "below_accepted"
    comparison = report["ocrComparison"]
    assert comparison["baseline"]["exactCount"] == 105  # type: ignore[index]
    assert comparison["alternative"]["exactCount"] == 108  # type: ignore[index]
    assert report["errorCatalog"]["incorrectCount"] == 3  # type: ignore[index]
    assert report["artifactSizes"]["boardCrops"]["referencedFileCount"] == 1  # type: ignore[index]
    assert benchmark_json_bytes(report) == benchmark_json_bytes(report)


def test_benchmark_rejects_upstream_checksum_drift(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    detection_path = fixture["detection_report_path"]
    assert isinstance(detection_path, Path)
    detection = json.loads(detection_path.read_text())
    detection["normalizationReportSha256"] = "0" * 64
    _write_json(detection_path, detection)

    with pytest.raises(ImageBenchmarkError) as raised:
        build_image_benchmark_report(**fixture)  # type: ignore[arg-type]

    assert raised.value.code == "M5_BENCHMARK_UPSTREAM_DRIFT"


def test_benchmark_requires_three_positive_timing_samples(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    timings = fixture["timing_samples"]
    assert isinstance(timings, dict)
    timings["geometry"] = [1.0, 2.0]

    with pytest.raises(ImageBenchmarkError) as raised:
        build_image_benchmark_report(**fixture)  # type: ignore[arg-type]

    assert raised.value.code == "M5_BENCHMARK_TIMING_INVALID"
