"""Measure the bounded, read-only V7 preparation and serial OCR runtime.

The command does not create a run, select a range, or write a JPEG.  It verifies
the frozen corpus inventory before decoding any source and defaults to the
development/calibration splits only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter

import numpy as np
from PIL import Image, ImageOps

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "services" / "worker" / "src"))

from game_predictor_worker.benchmarks.performance import PeakMemorySampler  # noqa: E402
from game_predictor_worker.semi_automatic_selection.middle_row_runtime import (  # noqa: E402
    build_middle_row_paddle_adapter,
)
from game_predictor_worker.semi_automatic_selection.v7_configuration import (  # noqa: E402
    V7CorpusSplit,
    load_v7_corpus_manifest,
)
from game_predictor_worker.semi_automatic_selection.v7_label_locator import (  # noqa: E402
    V7GridLabelLocator,
)
from game_predictor_worker.semi_automatic_selection.v7_ordered_runtime import (  # noqa: E402
    V7OrderedRuntimeInput,
    V7OrderedRuntimePolicy,
    run_v7_ordered_runtime,
)


@dataclass(frozen=True, slots=True)
class BenchmarkSource:
    case_id: str
    path: Path
    relative_path: str
    source_index: int
    source_sha256: str


@dataclass(frozen=True, slots=True)
class DecodedSource:
    case_id: str
    decode_milliseconds: float
    relative_path: str
    rgb: np.ndarray
    source_fingerprint_milliseconds: float
    source_sha256: str


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples-per-case", type=int, default=1)
    parser.add_argument(
        "--target-source-count",
        choices=(100, 300, 500),
        type=int,
        action="append",
        default=None,
        help=(
            "Measure one or more independent source counts. This enumerates every "
            "eligible source once; an undersized corpus is reported as not_evaluable."
        ),
    )
    parser.add_argument("--prepare-workers", type=int, action="append")
    parser.add_argument(
        "--include-split",
        choices=(V7CorpusSplit.DEVELOPMENT.value, V7CorpusSplit.CALIBRATION.value),
        action="append",
        default=None,
    )
    return parser.parse_args()


def _frozen_inventory(path: Path) -> tuple[str, tuple[dict[str, object], ...]]:
    try:
        payload = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Frozen V7 corpus inventory cannot be read.") from error
    cases = payload.get("cases") if isinstance(payload, dict) else None
    fingerprint = payload.get("manifestFingerprint") if isinstance(payload, dict) else None
    if (
        payload.get("schemaVersion") != 1
        or not isinstance(fingerprint, str)
        or not isinstance(cases, list)
        or not all(isinstance(item, dict) for item in cases)
    ):
        raise ValueError("Frozen V7 corpus inventory has an invalid contract.")
    return fingerprint, tuple(cases)


def _direct_jpegs(directory: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            (
                path
                for path in directory.iterdir()
                if path.is_file() and path.suffix.casefold() in {".jpg", ".jpeg"}
            ),
            key=lambda path: (path.name.casefold(), path.name),
        )
    )


def _select_sources(
    *,
    manifest_path: Path,
    inventory_path: Path,
    samples_per_case: int | None,
    splits: set[V7CorpusSplit],
) -> tuple[str, tuple[BenchmarkSource, ...]]:
    if samples_per_case is not None and not 1 <= samples_per_case <= 3:
        raise ValueError("--samples-per-case must be between one and three.")
    manifest = load_v7_corpus_manifest(manifest_path)
    frozen_fingerprint, frozen_cases = _frozen_inventory(inventory_path)
    inventory = manifest.freeze_inventory()
    if (
        manifest.fingerprint() != frozen_fingerprint
        or tuple(item.as_dict() for item in inventory) != frozen_cases
    ):
        raise ValueError("V7 corpus manifest or frozen inventory drifted; benchmark is blocked.")
    selected: list[BenchmarkSource] = []
    for case in manifest.cases:
        if case.split not in splits:
            continue
        directory = manifest.corpus_root / case.directory_name
        paths = _direct_jpegs(directory)
        if samples_per_case is not None:
            paths = paths[:samples_per_case]
        for path in paths:
            selected.append(
                BenchmarkSource(
                    case_id=case.case_id,
                    path=path,
                    relative_path=str(path.relative_to(manifest.corpus_root)).replace("\\", "/"),
                    source_index=len(selected),
                    source_sha256=_sha256_file(path),
                )
            )
    if not selected:
        raise ValueError("No JPEG sources match the requested V7 benchmark splits.")
    relative_paths = [source.relative_path for source in selected]
    if len(set(relative_paths)) != len(relative_paths):
        raise ValueError("V7 benchmark source inventory contains duplicate paths.")
    return manifest.fingerprint(), tuple(selected)


def _independent_sources(
    sources: Sequence[BenchmarkSource],
) -> tuple[BenchmarkSource, ...]:
    """Preserve the first path for each immutable JPEG payload identity."""

    seen_sha256: set[str] = set()
    independent: list[BenchmarkSource] = []
    for source in sources:
        if source.source_sha256 in seen_sha256:
            continue
        seen_sha256.add(source.source_sha256)
        independent.append(replace(source, source_index=len(independent)))
    return tuple(independent)


def _decode(source: BenchmarkSource) -> DecodedSource:
    fingerprint_started_at = perf_counter()
    source_sha256 = _sha256_file(source.path)
    if source_sha256 != source.source_sha256:
        raise ValueError("V7 benchmark source content changed after source selection.")
    source_fingerprint_milliseconds = round(
        (perf_counter() - fingerprint_started_at) * 1000,
        4,
    )
    started_at = perf_counter()
    with Image.open(source.path) as image:
        rgb = np.ascontiguousarray(
            np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
        )
    return DecodedSource(
        case_id=source.case_id,
        decode_milliseconds=round((perf_counter() - started_at) * 1000, 4),
        relative_path=source.relative_path,
        rgb=rgb,
        source_fingerprint_milliseconds=source_fingerprint_milliseconds,
        source_sha256=source_sha256,
    )


def _runtime_device() -> dict[str, object]:
    try:
        import paddle

        compiled_with_cuda = bool(paddle.is_compiled_with_cuda())
        gpu_device_count = int(paddle.device.cuda.device_count()) if compiled_with_cuda else 0
        gpu_available = compiled_with_cuda and gpu_device_count > 0
        return {
            "compiledWithCuda": compiled_with_cuda,
            "device": str(paddle.device.get_device()),
            "gpuDeviceCount": gpu_device_count,
            "vramBytes": None,
            "vramStatus": "not_collected" if gpu_available else "unavailable_cpu_runtime",
            "version": str(paddle.__version__),
        }
    except Exception as error:  # The report must explain an unavailable local runtime.
        return {
            "compiledWithCuda": None,
            "device": None,
            "error": f"{type(error).__name__}: {error}",
            "gpuDeviceCount": None,
            "vramBytes": None,
            "vramStatus": "unavailable_runtime_error",
            "version": None,
        }


def _run_profile(
    *,
    manifest_validation_milliseconds: float,
    model_root: Path,
    policy: V7OrderedRuntimePolicy,
    sources: Sequence[BenchmarkSource],
) -> dict[str, object]:
    initialization_started_at = perf_counter()
    recognizer = build_middle_row_paddle_adapter(model_root)
    model_initialization_milliseconds = round(
        (perf_counter() - initialization_started_at) * 1000,
        4,
    )
    locator = V7GridLabelLocator()
    locator_milliseconds = 0.0
    ocr_milliseconds = 0.0
    observations: list[dict[str, object]] = []

    def consume(source_index: int, decoded: DecodedSource) -> None:
        nonlocal locator_milliseconds, ocr_milliseconds
        locator_started_at = perf_counter()
        crops = locator.locate(decoded.rgb)
        locator_milliseconds += (perf_counter() - locator_started_at) * 1000
        ocr_started_at = perf_counter()
        recognized = recognizer.recognize_many([crop.rgb for crop in crops])
        ocr_milliseconds += (perf_counter() - ocr_started_at) * 1000
        recognized_labels: list[dict[str, object]] = []
        for crop, value in zip(crops, recognized, strict=True):
            raw_text = getattr(value, "raw_text", None)
            confidence = getattr(value, "confidence", 0.0)
            recognized_labels.append(
                {
                    "confidence": round(float(confidence), 6),
                    "positionIndex": crop.position_index,
                    "rawText": raw_text if isinstance(raw_text, str) else None,
                }
            )
        observations.append(
            {
                "case": decoded.case_id,
                "decodeMilliseconds": decoded.decode_milliseconds,
                "recognizedLabels": recognized_labels,
                "relativePath": decoded.relative_path,
                "sourceFingerprintMilliseconds": decoded.source_fingerprint_milliseconds,
                "sourceSha256": decoded.source_sha256,
                "sourceIndex": source_index,
            }
        )

    total_started_at = perf_counter()
    with PeakMemorySampler() as memory_sampler:
        runtime = run_v7_ordered_runtime(
            tuple(V7OrderedRuntimeInput(item.source_index, item) for item in sources),
            prepare=_decode,
            consume=consume,
            policy=policy,
        )
    finalization_started_at = perf_counter()
    digest = _observation_digest(observations)
    finalization_milliseconds = round((perf_counter() - finalization_started_at) * 1000, 4)
    total_milliseconds = round((perf_counter() - total_started_at) * 1000, 4)
    return {
        "memory": memory_sampler.summary().to_dict(),
        "observationDigest": digest,
        "policy": policy.as_dict(),
        "runtime": runtime.metrics.as_dict(),
        "stages": {
            "decodeMilliseconds": round(
                sum(float(item["decodeMilliseconds"]) for item in observations),
                4,
            ),
            "finalizationMilliseconds": finalization_milliseconds,
            "endToEndMilliseconds": round(
                manifest_validation_milliseconds
                + model_initialization_milliseconds
                + total_milliseconds,
                4,
            ),
            "locatorMilliseconds": round(locator_milliseconds, 4),
            "modelInitializationMilliseconds": model_initialization_milliseconds,
            "ocrMilliseconds": round(ocr_milliseconds, 4),
            "orderedConsumeMilliseconds": round(runtime.metrics.consume_seconds * 1000, 4),
            "sourceFingerprintMilliseconds": round(
                sum(float(item["sourceFingerprintMilliseconds"]) for item in observations),
                4,
            ),
            "totalMilliseconds": total_milliseconds,
            # This command is deliberately read-only while V7 is inactive.  A
            # zero is not a writer speed claim; the status prevents treating it
            # as an output benchmark.
            "writeMilliseconds": 0.0,
            "writeStatus": "not_run_read_only_v7_inactive",
        },
        "throughputSourcesPerSecond": round(
            len(sources) / (total_milliseconds / 1000), 4
        )
        if total_milliseconds > 0
        else None,
    }


def _recommended_profile(profiles: Sequence[dict[str, object]]) -> dict[str, object]:
    baseline_digest = profiles[0]["observationDigest"]
    deterministic = all(profile["observationDigest"] == baseline_digest for profile in profiles)
    if not deterministic:
        return {
            "deterministic": False,
            "reason": "V7_ORDERED_RUNTIME_DIGEST_MISMATCH",
            "selectedPrepareWorkers": 1,
        }
    selected = min(
        profiles,
        key=lambda profile: (
            float((profile["stages"])["totalMilliseconds"]),
            int((profile["policy"])["prepareWorkers"]),
        ),
    )
    policy = selected["policy"]
    assert isinstance(policy, dict)
    return {
        "deterministic": True,
        "maxInFlight": policy["maxInFlight"],
        "selectedPrepareWorkers": policy["prepareWorkers"],
    }


def _observation_digest(observations: Sequence[dict[str, object]]) -> str:
    """Exclude timing and memory data: only a logical ordered OCR result matters."""

    logical_observations = [
        {
            "case": item["case"],
            "recognizedLabels": item["recognizedLabels"],
            "relativePath": item["relativePath"],
            "sourceSha256": item["sourceSha256"],
            "sourceIndex": item["sourceIndex"],
        }
        for item in observations
    ]
    return hashlib.sha256(
        json.dumps(
            logical_observations,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def _write_report(path: Path, payload: dict[str, object]) -> None:
    target = path.resolve()
    checkout = REPOSITORY_ROOT.resolve()
    if not target.is_relative_to(checkout):
        raise ValueError("Benchmark report must remain inside the repository checkout.")
    if target.exists():
        raise FileExistsError("Benchmark report already exists; choose a new output path.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        "utf-8",
    )


def _scale_report(
    *,
    available_sources: Sequence[BenchmarkSource],
    manifest_validation_milliseconds: float,
    model_root: Path,
    policies: Sequence[V7OrderedRuntimePolicy],
    target_source_count: int,
) -> dict[str, object]:
    independent_sources = _independent_sources(available_sources)
    if len(independent_sources) < target_source_count:
        return {
            "availablePathCount": len(available_sources),
            "availableSourceCount": len(independent_sources),
            "profiles": [],
            "reason": "V7_BENCHMARK_INSUFFICIENT_INDEPENDENT_SOURCES",
            "stages": {
                "decodeMilliseconds": None,
                "finalizationMilliseconds": None,
                "locatorMilliseconds": None,
                "manifestValidationMilliseconds": manifest_validation_milliseconds,
                "ocrMilliseconds": None,
                "writeMilliseconds": 0.0,
                "writeStatus": "not_run_read_only_v7_inactive",
            },
            "status": "not_evaluable",
            "targetSourceCount": target_source_count,
        }
    sources = tuple(independent_sources[:target_source_count])
    profiles = tuple(
        _run_profile(
            manifest_validation_milliseconds=manifest_validation_milliseconds,
            model_root=model_root,
            policy=policy,
            sources=sources,
        )
        for policy in policies
    )
    return {
        "availablePathCount": len(available_sources),
        "availableSourceCount": len(independent_sources),
        "profiles": profiles,
        "recommendation": _recommended_profile(profiles),
        "status": "measured_read_only_v7_inactive",
        "targetSourceCount": target_source_count,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = _arguments()
    selected_splits = {
        V7CorpusSplit(value)
        for value in (
            args.include_split
            or [V7CorpusSplit.DEVELOPMENT.value, V7CorpusSplit.CALIBRATION.value]
        )
    }
    workers = tuple(args.prepare_workers or [1, 2, 4])
    if len(set(workers)) != len(workers):
        raise ValueError("Preparation worker profiles must be unique.")
    policies = tuple(V7OrderedRuntimePolicy.for_workers(worker) for worker in workers)
    manifest_started_at = perf_counter()
    manifest_fingerprint, sources = _select_sources(
        manifest_path=args.manifest,
        inventory_path=args.inventory,
        samples_per_case=(None if args.target_source_count else args.samples_per_case),
        splits=selected_splits,
    )
    manifest_validation_milliseconds = round((perf_counter() - manifest_started_at) * 1000, 4)
    device = _runtime_device()
    if args.target_source_count:
        targets = tuple(dict.fromkeys(args.target_source_count))
        independent_sources = _independent_sources(sources)
        payload: dict[str, object] = {
            "availablePathCount": len(sources),
            "availableSourceCount": len(independent_sources),
            "corpusManifestFingerprint": manifest_fingerprint,
            "device": device,
            "selectionRuntimeStatus": "not_activated_read_only",
            "measurementScope": (
                "legacy_v1_label_locator_and_read_only_ordered_runtime; "
                "excludes_v2_representative_ranking_and_output_writer"
            ),
            "sourcePaths": [item.relative_path for item in sources],
            "splits": sorted(item.value for item in selected_splits),
            "stages": {"manifestValidationMilliseconds": manifest_validation_milliseconds},
            "targetReports": [
                _scale_report(
                    available_sources=sources,
                    manifest_validation_milliseconds=manifest_validation_milliseconds,
                    model_root=args.model_root,
                    policies=policies,
                    target_source_count=target,
                )
                for target in targets
            ],
            "version": "v7-runtime-performance-v2",
        }
        _write_report(args.output, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    profiles = tuple(
        _run_profile(
            manifest_validation_milliseconds=manifest_validation_milliseconds,
            model_root=args.model_root,
            policy=policy,
            sources=sources,
        )
        for policy in policies
    )
    recommendation = _recommended_profile(profiles)
    payload: dict[str, object] = {
        "corpusManifestFingerprint": manifest_fingerprint,
        "device": device,
        "profiles": profiles,
        "recommendation": recommendation,
        "sampleCount": len(sources),
        "sourcePaths": [item.relative_path for item in sources],
        "splits": sorted(item.value for item in selected_splits),
        "stages": {"manifestValidationMilliseconds": manifest_validation_milliseconds},
        "version": "v7-runtime-performance-v1",
    }
    _write_report(args.output, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if recommendation["deterministic"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
