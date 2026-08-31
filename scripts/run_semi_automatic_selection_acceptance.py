"""Run a bounded, read-only acceptance check for range-only image selection."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import statistics
import sys
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol, cast

import numpy as np
from PIL import Image, ImageOps

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "services" / "worker" / "src"))

from game_predictor_worker.semi_automatic_selection.contracts import (  # noqa: E402
    RangeEvidenceStatus,
    SemiAutomaticSelectionRange,
    SemiAutomaticSelectionSource,
    SemiAutomaticSequenceBounds,
)
from game_predictor_worker.semi_automatic_selection.range_only_ocr import (  # noqa: E402
    RangeOnlyOcrAdapter,
    RangeOnlyRecognition,
    build_paddle_range_only_recognizer,
)

_SEQ_NAME = re.compile(r"^seq_(?P<start>[1-9]\d*)-(?P<end>[1-9]\d*)\.(?:jpe?g)$", re.I)


class RangeRecognizer(Protocol):
    version: str
    fingerprint: str

    def recognize(
        self, rgb_image: np.ndarray[tuple[int, ...], np.dtype[np.uint8]]
    ) -> RangeOnlyRecognition: ...


@dataclass(frozen=True, slots=True)
class _Case:
    index: int
    path: Path
    expected: SemiAutomaticSelectionRange


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--sample-size", type=int, choices=(10, 100), required=True)
    parser.add_argument(
        "--expected-range",
        help=(
            "Optional inclusive start-end oracle for a raw directory containing one repeated range."
        ),
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--ocr-model-root",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts" / "m5-models" / "sequence-number-ocr-v1",
    )
    return parser.parse_args()


def _parse_expected_range(value: str | None) -> SemiAutomaticSelectionRange | None:
    if value is None:
        return None
    start, separator, end = value.partition("-")
    if not separator or not start.isdigit() or not end.isdigit():
        raise ValueError("Expected range must use the inclusive form start-end.")
    expected = SemiAutomaticSelectionRange(int(start), int(end))
    if expected.end - expected.start >= 9:
        raise ValueError("Expected range may contain at most nine boards.")
    return expected


def _natural_path_key(path: Path) -> tuple[object, ...]:
    return tuple(
        int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)
    )


def _load_cases(
    source_root: Path,
    sample_size: int,
    *,
    expected_range: SemiAutomaticSelectionRange | None = None,
) -> tuple[_Case, ...]:
    root = source_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Source root must be a directory.")
    cases: list[_Case] = []
    invalid: list[str] = []
    for path in root.iterdir():
        if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg"}:
            continue
        match = _SEQ_NAME.fullmatch(path.name)
        if expected_range is not None:
            cases.append(_Case(0, path.resolve(strict=True), expected_range))
        elif match is None:
            invalid.append(path.name)
            continue
        else:
            expected = SemiAutomaticSelectionRange(int(match["start"]), int(match["end"]))
            if expected.end - expected.start >= 9:
                invalid.append(path.name)
                continue
            cases.append(_Case(0, path.resolve(strict=True), expected))
    if invalid:
        raise ValueError(
            f"Source contains invalid selected JPEG names: {', '.join(sorted(invalid)[:5])}"
        )
    ordered = sorted(
        cases,
        key=(lambda item: _natural_path_key(item.path))
        if expected_range is not None
        else lambda item: (item.expected.start, item.expected.end, item.path.name),
    )
    if len(ordered) < sample_size:
        raise ValueError(
            f"Source contains only {len(ordered)} selected JPEGs; {sample_size} required."
        )
    if expected_range is None:
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current.expected.start <= previous.expected.end:
                raise ValueError("Source contains overlapping selected sequence ranges.")
    return tuple(
        _Case(index, item.path, item.expected) for index, item in enumerate(ordered[:sample_size])
    )


def _decode_and_hash(path: Path) -> tuple[bytes, np.ndarray[tuple[int, ...], np.dtype[np.uint8]]]:
    content = path.read_bytes()
    with Image.open(BytesIO(content)) as image:
        rgb = np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
    return content, rgb


def _peak_rss_bytes() -> int | None:
    if os.name == "nt":

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("page_fault_count", ctypes.c_ulong),
                ("peak", ctypes.c_size_t),
                ("working", ctypes.c_size_t),
                ("quota_peak_paged_pool", ctypes.c_size_t),
                ("quota_paged_pool", ctypes.c_size_t),
                ("quota_peak_non_paged_pool", ctypes.c_size_t),
                ("quota_non_paged_pool", ctypes.c_size_t),
                ("pagefile_usage", ctypes.c_size_t),
                ("peak_pagefile_usage", ctypes.c_size_t),
                ("private_usage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        get_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_memory_info.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)
        get_memory_info.restype = ctypes.c_bool
        process = kernel32.GetCurrentProcess()
        if get_memory_info(process, ctypes.byref(counters), counters.cb):
            return int(counters.peak)
        return None
    try:
        import resource

        resource_module = cast(Any, resource)
        value = resource_module.getrusage(resource_module.RUSAGE_SELF).ru_maxrss
        return int(value if sys.platform == "darwin" else value * 1024)
    except (ImportError, OSError):
        return None


def run_acceptance(
    *,
    source_root: Path,
    sample_size: int,
    recognizer: RangeRecognizer,
    expected_range: SemiAutomaticSelectionRange | None = None,
) -> dict[str, object]:
    cases = _load_cases(source_root, sample_size, expected_range=expected_range)
    bounds = SemiAutomaticSequenceBounds(cases[0].expected.start, cases[-1].expected.end)
    adapter = RangeOnlyOcrAdapter(bounds=bounds, recognizer=recognizer)
    results: list[dict[str, object]] = []
    started = perf_counter()
    for case in cases:
        case_started = perf_counter()
        content, rgb = _decode_and_hash(case.path)
        source = SemiAutomaticSelectionSource(
            source_index=case.index,
            relative_path=case.path.name,
            size_bytes=len(content),
            checksum_sha256=hashlib.sha256(content).hexdigest(),
        )
        evidence = adapter.recognize(source=source, rgb_image=rgb)
        diagnostics = dict(adapter.last_diagnostics)
        actual = evidence.observed_range
        false_assignment = (
            evidence.status is RangeEvidenceStatus.EXACT_RANGE and actual != case.expected
        )
        results.append(
            {
                "actualRange": None if actual is None else [actual.start, actual.end],
                "elapsedSeconds": round(perf_counter() - case_started, 6),
                "expectedRange": [case.expected.start, case.expected.end],
                "falseAssignment": false_assignment,
                "filename": case.path.name,
                "recognizerDiagnostics": diagnostics,
                "reasonCodes": list(evidence.reason_codes),
                "sha256": source.checksum_sha256,
                "status": evidence.status.value,
            }
        )
    elapsed = perf_counter() - started
    per_image_durations = [cast(float, item["elapsedSeconds"]) for item in results]
    exact = sum(item["status"] == RangeEvidenceStatus.EXACT_RANGE.value for item in results)
    ambiguous = sum(item["status"] == RangeEvidenceStatus.RANGE_AMBIGUOUS.value for item in results)
    false_assignments = sum(bool(item["falseAssignment"]) for item in results)
    exact_matches = sum(
        item["status"] == RangeEvidenceStatus.EXACT_RANGE.value
        and not bool(item["falseAssignment"])
        for item in results
    )
    rejected_raw_hypotheses = sum(
        item["actualRange"] is not None and item["status"] != RangeEvidenceStatus.EXACT_RANGE.value
        for item in results
    )
    exact_ranges = [
        tuple(item["actualRange"])
        for item in results
        if item["status"] == RangeEvidenceStatus.EXACT_RANGE.value
        and isinstance(item["actualRange"], list)
    ]
    exact_ranges_sorted = sorted(exact_ranges)
    overlapping_assignments = sum(
        current[0] <= previous[1]
        for previous, current in zip(exact_ranges_sorted, exact_ranges_sorted[1:], strict=False)
    )
    total_ocr_batches = sum(
        _metric_int(cast(dict[str, object], item["recognizerDiagnostics"]).get("ocrBatchCalls", 0))
        for item in results
    )
    total_ocr_crops = sum(
        _metric_int(cast(dict[str, object], item["recognizerDiagnostics"]).get("ocrCropCount", 0))
        for item in results
    )
    minimum_exact_matches = (len(results) + 1) // 2
    gate_passed = (
        false_assignments == 0
        and exact_matches >= minimum_exact_matches
        and (expected_range is not None or overlapping_assignments == 0)
    )
    source_manifest = [
        {
            "expectedRange": item["expectedRange"],
            "filename": item["filename"],
            "sha256": item["sha256"],
        }
        for item in results
    ]
    source_manifest_sha256 = hashlib.sha256(
        json.dumps(
            source_manifest,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "contract": "semi-automatic-selection-acceptance-v2",
        "elapsedSeconds": round(elapsed, 6),
        "falseAssignments": false_assignments,
        "exactMatches": exact_matches,
        "geometryCalls": 0,
        "gatePassed": gate_passed,
        "ocrCalls": len(results),
        "ocrBatchCalls": total_ocr_batches,
        "ocrCropCount": total_ocr_crops,
        "overlappingAssignments": overlapping_assignments,
        "rejectedRawHypotheses": rejected_raw_hypotheses,
        "minimumExactMatches": minimum_exact_matches,
        "medianPerJpegSeconds": round(statistics.median(per_image_durations), 6),
        "peakRssBytes": _peak_rss_bytes(),
        "perJpegSeconds": round(elapsed / len(results), 6),
        "results": results,
        "sampleSize": len(results),
        "sourceManifestSha256": source_manifest_sha256,
        "selection": {
            "autoSelected": exact,
            "ambiguous": ambiguous,
            "missing": len(results) - exact - ambiguous,
        },
        "symbolInferenceCalls": 0,
        "cropperCalls": 0,
        "recognizer": {"fingerprint": recognizer.fingerprint, "version": recognizer.version},
    }


def _metric_int(value: object) -> int:
    return int(value) if isinstance(value, int | str) and not isinstance(value, bool) else 0


def main() -> int:
    args = _arguments()
    source_root = args.source_root.resolve(strict=True)
    report = args.report.resolve()
    if report.is_relative_to(source_root):
        raise ValueError(
            "Acceptance report must not be written into the read-only source directory."
        )
    recognizer = build_paddle_range_only_recognizer(args.ocr_model_root.resolve(strict=True))
    report_payload = run_acceptance(
        source_root=source_root,
        sample_size=int(args.sample_size),
        recognizer=recognizer,
        expected_range=_parse_expected_range(args.expected_range),
    )
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report_payload, ensure_ascii=False, indent=2))
    return 0 if bool(report_payload["gatePassed"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
