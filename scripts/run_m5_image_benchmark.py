"""Measure and verify the local M5 geometry/OCR prototype."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from collections.abc import Callable, Mapping
from importlib.metadata import version
from pathlib import Path
from time import perf_counter_ns

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.benchmark import (  # noqa: E402
    ImageBenchmarkError,
    benchmark_json_bytes,
    build_image_benchmark_report,
)
from game_predictor_worker.images.discovery import discover_images  # noqa: E402
from game_predictor_worker.images.geometry import detect_normalized_corpus  # noqa: E402
from game_predictor_worker.images.normalization import normalize_images  # noqa: E402
from game_predictor_worker.images.rectification import crop_detected_corpus  # noqa: E402
from game_predictor_worker.images.sequence_ocr import (  # noqa: E402
    PaddleSequenceNumberRecognizer,
    run_sequence_ocr_corpus,
)


def _repo_path(value: str) -> Path:
    return REPOSITORY_ROOT / value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=_repo_path("ai_docs/quality/m5-image-benchmark-report.json"),
    )
    parser.add_argument(
        "--alternative-ocr-output",
        type=Path,
        default=_repo_path("ai_docs/quality/m5-sequence-ocr-raw-input-report.json"),
    )
    return parser.parse_args()


def _paths() -> dict[str, Path]:
    return {
        "alternative_model_root": _repo_path("artifacts/m5-models/sequence-number-ocr-v1"),
        "alternative_ocr_root": _repo_path("artifacts/m5-sequence-ocr-raw-input"),
        "baseline_model_root": _repo_path("artifacts/m5-models/sequence-number-ocr-v1"),
        "baseline_ocr_report": _repo_path("ai_docs/quality/m5-sequence-ocr-report.json"),
        "baseline_ocr_root": _repo_path("artifacts/m5-sequence-ocr"),
        "corpus": _repo_path("ai_docs/quality/m5-corpus-manifest.json"),
        "crop_report": _repo_path("ai_docs/quality/m5-board-cell-crops-report.json"),
        "crop_root": _repo_path("artifacts/m5-board-crops"),
        "detection_report": _repo_path("ai_docs/quality/m5-page-board-detection-report.json"),
        "detection_root": _repo_path("artifacts/m5-page-detection"),
        "discovery": _repo_path("ai_docs/quality/m5-source-discovery.json"),
        "golden": _repo_path("ai_docs/quality/m5-golden-annotations.json"),
        "normalization_report": _repo_path("ai_docs/quality/m5-normalization-report.json"),
        "normalization_root": _repo_path("artifacts/m5-normalization"),
        "source_root": _repo_path("examples/imgs"),
        "thresholds": _repo_path("ai_docs/quality/m5-quality-thresholds.json"),
    }


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def _measure(
    operation: Callable[[], bytes],
    expected: bytes,
    *,
    iterations: int,
    stage: str,
) -> list[float]:
    samples: list[float] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        actual = operation()
        elapsed_ms = (perf_counter_ns() - started) / 1_000_000
        if actual != expected:
            raise ImageBenchmarkError(
                "M5_BENCHMARK_STAGE_DRIFT",
                f"{stage} output differs from its committed report.",
            )
        samples.append(round(elapsed_ms, 6))
    return samples


def _environment() -> dict[str, object]:
    return {
        "cpuLogicalCount": __import__("os").cpu_count(),
        "numpyVersion": version("numpy"),
        "opencvVersion": version("opencv-python-headless"),
        "operatingSystem": platform.system(),
        "paddlepaddleVersion": version("paddlepaddle"),
        "pillowVersion": version("Pillow"),
        "pythonVersion": platform.python_version(),
    }


def _alternative_report(paths: Mapping[str, Path]) -> bytes:
    recognizer = PaddleSequenceNumberRecognizer(paths["alternative_model_root"])
    return run_sequence_ocr_corpus(
        paths["corpus"],
        paths["golden"],
        paths["normalization_report"],
        paths["detection_report"],
        paths["normalization_root"],
        paths["alternative_model_root"],
        paths["alternative_ocr_root"],
        recognizer=recognizer,
        recognition_input_policy="raw-warp-v1",
    ).to_json_bytes()


def _timings(
    paths: Mapping[str, Path],
    alternative_report_bytes: bytes,
    *,
    iterations: int,
) -> dict[str, list[float]]:
    expected_discovery = paths["discovery"].read_bytes()
    expected_normalization = paths["normalization_report"].read_bytes()
    expected_detection = paths["detection_report"].read_bytes()
    expected_crops = paths["crop_report"].read_bytes()
    expected_baseline = paths["baseline_ocr_report"].read_bytes()
    return {
        "discovery": _measure(
            lambda: discover_images(paths["source_root"]).to_json_bytes(),
            expected_discovery,
            iterations=iterations,
            stage="discovery",
        ),
        "normalization": _measure(
            lambda: normalize_images(
                paths["source_root"],
                paths["discovery"],
                paths["normalization_root"],
            ).to_json_bytes(),
            expected_normalization,
            iterations=iterations,
            stage="normalization",
        ),
        "geometry": _measure(
            lambda: detect_normalized_corpus(
                paths["normalization_report"],
                paths["normalization_root"],
                paths["detection_root"],
            ).to_json_bytes(),
            expected_detection,
            iterations=iterations,
            stage="geometry",
        ),
        "boardCrops": _measure(
            lambda: crop_detected_corpus(
                paths["normalization_report"],
                paths["detection_report"],
                paths["normalization_root"],
                paths["crop_root"],
            ).to_json_bytes(),
            expected_crops,
            iterations=iterations,
            stage="boardCrops",
        ),
        "baselineOcr": _measure(
            lambda: run_sequence_ocr_corpus(
                paths["corpus"],
                paths["golden"],
                paths["normalization_report"],
                paths["detection_report"],
                paths["normalization_root"],
                paths["baseline_model_root"],
                paths["baseline_ocr_root"],
            ).to_json_bytes(),
            expected_baseline,
            iterations=iterations,
            stage="baselineOcr",
        ),
        "alternativeOcr": _measure(
            lambda: _alternative_report(paths),
            alternative_report_bytes,
            iterations=iterations,
            stage="alternativeOcr",
        ),
    }


def _build(
    paths: Mapping[str, Path],
    alternative_report_path: Path,
    timing_samples: Mapping[str, list[float]],
    environment: Mapping[str, object],
) -> bytes:
    report = build_image_benchmark_report(
        corpus_manifest_path=paths["corpus"],
        golden_annotations_path=paths["golden"],
        source_discovery_path=paths["discovery"],
        normalization_report_path=paths["normalization_report"],
        detection_report_path=paths["detection_report"],
        crop_report_path=paths["crop_report"],
        baseline_ocr_report_path=paths["baseline_ocr_report"],
        alternative_ocr_report_path=alternative_report_path,
        thresholds_path=paths["thresholds"],
        normalization_root=paths["normalization_root"],
        detection_root=paths["detection_root"],
        crop_root=paths["crop_root"],
        baseline_ocr_root=paths["baseline_ocr_root"],
        alternative_ocr_root=paths["alternative_ocr_root"],
        baseline_model_root=paths["baseline_model_root"],
        alternative_model_root=paths["alternative_model_root"],
        timing_samples=timing_samples,
        environment=environment,
    )
    return benchmark_json_bytes(report)


def main() -> int:
    args = _parse_args()
    if args.iterations < 3:
        print(
            json.dumps(
                {
                    "code": "M5_BENCHMARK_ITERATIONS_INVALID",
                    "message": "--iterations must be at least 3.",
                    "status": "failed",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    paths = _paths()
    try:
        if args.check:
            existing = args.output.read_bytes()
            existing_value = json.loads(existing)
            timing_value = existing_value["timing"]["stages"]
            timing_samples = {
                stage: [float(value) for value in timing_value[stage]["samplesMs"]]
                for stage in (
                    "discovery",
                    "normalization",
                    "geometry",
                    "boardCrops",
                    "baselineOcr",
                    "alternativeOcr",
                )
            }
            rebuilt = _build(
                paths,
                args.alternative_ocr_output,
                timing_samples,
                _environment(),
            )
            if rebuilt != existing:
                raise ImageBenchmarkError(
                    "M5_BENCHMARK_REPORT_DRIFT",
                    "Benchmark report differs from current inputs or summaries.",
                )
            content = existing
        else:
            alternative = _alternative_report(paths)
            _write_atomic(args.alternative_ocr_output, alternative)
            timing_samples = _timings(
                paths,
                alternative,
                iterations=args.iterations,
            )
            content = _build(
                paths,
                args.alternative_ocr_output,
                timing_samples,
                _environment(),
            )
            _write_atomic(args.output, content)
        payload = json.loads(content)
        print(
            json.dumps(
                {
                    "alternativeExactAccuracy": payload["ocrComparison"]["alternative"][
                        "exactAccuracy"
                    ],
                    "baselineExactAccuracy": payload["ocrComparison"]["baseline"]["exactAccuracy"],
                    "benchmarkSha256": hashlib.sha256(content).hexdigest(),
                    "decision": payload["decision"]["recommendation"],
                    "status": payload["status"],
                },
                sort_keys=True,
            )
        )
        return 0
    except (ImageBenchmarkError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        code = (
            error.code
            if isinstance(error, ImageBenchmarkError)
            else "M5_BENCHMARK_EXECUTION_FAILED"
        )
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
