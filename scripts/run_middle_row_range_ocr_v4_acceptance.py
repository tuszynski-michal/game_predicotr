"""Run checksum-bound, read-only acceptance for middle-row range OCR v4.1.

The tool never derives expected ranges from source filenames or source indexes.
Quality labels come only from an explicit human-review manifest. A raw window
without such a manifest is a performance sample and cannot pass quality gates.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, Protocol, cast
from uuid import NAMESPACE_URL, uuid5

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "services" / "worker" / "src"))

from game_predictor_worker.semi_automatic_selection.contracts import (  # type: ignore[import-untyped] # noqa: E402
    RangeEvidenceResult,
    RangeEvidenceStatus,
    SemiAutomaticSelectionRange,
    SemiAutomaticSelectionSource,
    SemiAutomaticSequenceBounds,
)
from game_predictor_worker.semi_automatic_selection.middle_row_grouping import (  # type: ignore[import-untyped] # noqa: E402
    MiddleRowGroupingAccumulator,
)
from game_predictor_worker.semi_automatic_selection.middle_row_locator import (  # type: ignore[import-untyped] # noqa: E402
    MiddleRowTripleLocator,
)
from game_predictor_worker.semi_automatic_selection.middle_row_range import (  # type: ignore[import-untyped] # noqa: E402
    ExpectedRangeTable,
)
from game_predictor_worker.semi_automatic_selection.middle_row_runtime import (  # type: ignore[import-untyped] # noqa: E402
    DEFAULT_MIDDLE_ROW_RUNTIME_POLICY,
    MIDDLE_ROW_RECOGNIZER_CONTRACT_FINGERPRINT_V4,
    MiddleRowBatchRuntime,
    MiddleRowRunOrientation,
    MiddleRowSourcePayload,
    build_middle_row_paddle_adapter,
    calibrate_middle_row_orientation,
    deterministic_orientation_sample_indexes,
)

_JPEG_SUFFIXES = {".jpg", ".jpeg"}
_NATURAL_PART = re.compile(r"(\d+)")
_MANIFEST_CONTRACT = "middle-row-range-ocr-v4-corpus-v1"
_REPORT_CONTRACT = "middle-row-range-ocr-v4-acceptance-v1"
_REVIEW_CONTRACT = "middle-row-range-ocr-v4-selected-review-v1"

HumanLabelKind = Literal["human_readable_exact", "unreadable", "ambiguous"]


@dataclass(frozen=True, slots=True)
class HumanLabel:
    kind: HumanLabelKind
    expected_range: SemiAutomaticSelectionRange | None

    def __post_init__(self) -> None:
        if (self.kind == "human_readable_exact") != (self.expected_range is not None):
            raise ValueError("Only a human-readable label may contain an expected range.")


@dataclass(frozen=True, slots=True)
class AcceptanceCase:
    sample_index: int
    source_index: int
    relative_path: str
    checksum_sha256: str
    size_bytes: int
    human_label: HumanLabel | None = None


@dataclass(frozen=True, slots=True)
class SelectedReview:
    relative_path: str
    expected_range: SemiAutomaticSelectionRange
    correct_range: bool
    own_exact_proof_visible: bool
    near_evidence_midpoint: bool


class _RecognitionMetrics(Protocol):
    calls: int
    internal_batches: int
    crops: int
    recognition_seconds: float
    preprocessing_seconds: float
    inference_seconds: float

    @property
    def batch_fill_ratio(self) -> float: ...


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--first-sequence", type=int, required=True)
    parser.add_argument("--last-sequence", type=int, required=True)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--corpus-manifest", type=Path)
    parser.add_argument("--selected-review", type=Path)
    parser.add_argument(
        "--apply-selected-review-to-existing-report",
        action="store_true",
        help="Re-evaluate manual selected-frame gates without running OCR again.",
    )
    parser.add_argument("--warmup-count", type=int, default=6)
    parser.add_argument(
        "--orientation",
        choices=("auto", "0", "90", "180", "270"),
        default="auto",
    )
    parser.add_argument(
        "--ocr-model-root",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts" / "m5-models" / "sequence-number-ocr-v1",
    )
    return parser.parse_args()


def _natural_key(path: Path) -> tuple[object, ...]:
    return tuple(
        int(part) if part.isdigit() else part.casefold() for part in _NATURAL_PART.split(path.name)
    )


def _jpeg_inventory(source_root: Path) -> tuple[Path, ...]:
    root = source_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Source root must be a directory.")
    return tuple(
        sorted(
            (
                path.resolve(strict=True)
                for path in root.iterdir()
                if path.is_file() and path.suffix.casefold() in _JPEG_SUFFIXES
            ),
            key=_natural_key,
        )
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _range(value: object, context: str) -> SemiAutomaticSelectionRange:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{context} must be [start, end].")
    return SemiAutomaticSelectionRange(_integer(value[0], context), _integer(value[1], context))


def _integer(value: object, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context} must be an integer.")
    return value


def _mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be an object.")
    return cast(Mapping[str, object], value)


def _text(value: object, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a non-empty string.")
    return value


def _load_manifest(
    path: Path,
    *,
    source_root: Path,
    inventory: Sequence[Path],
) -> tuple[str, tuple[AcceptanceCase, ...]]:
    content = path.resolve(strict=True).read_bytes()
    raw = _mapping(json.loads(content), "corpus manifest")
    if raw.get("contract") != _MANIFEST_CONTRACT:
        raise ValueError("Corpus manifest contract is unsupported.")
    cases_raw = raw.get("cases")
    if not isinstance(cases_raw, list) or not cases_raw:
        raise ValueError("Corpus manifest must contain cases.")
    by_name = {item.name: (index, item) for index, item in enumerate(inventory)}
    cases: list[AcceptanceCase] = []
    seen: set[str] = set()
    for sample_index, item_raw in enumerate(cases_raw):
        item = _mapping(item_raw, f"cases[{sample_index}]")
        relative_path = _text(item.get("relativePath"), "relativePath")
        if relative_path in seen or Path(relative_path).name != relative_path:
            raise ValueError("Corpus manifest paths must be unique root-level filenames.")
        seen.add(relative_path)
        try:
            source_index, source_path = by_name[relative_path]
        except KeyError as error:
            raise ValueError(f"Manifest source is missing: {relative_path}") from error
        checksum = _text(item.get("sha256"), "sha256").lower()
        if len(checksum) != 64 or _sha256(source_path) != checksum:
            raise ValueError(f"Manifest checksum differs for {relative_path}.")
        label_raw = _mapping(item.get("humanLabel"), "humanLabel")
        kind = _text(label_raw.get("kind"), "humanLabel.kind")
        if kind not in {"human_readable_exact", "unreadable", "ambiguous"}:
            raise ValueError("Human label kind is unsupported.")
        expected = (
            _range(label_raw.get("expectedRange"), "humanLabel.expectedRange")
            if kind == "human_readable_exact"
            else None
        )
        cases.append(
            AcceptanceCase(
                sample_index=sample_index,
                source_index=source_index,
                relative_path=relative_path,
                checksum_sha256=checksum,
                size_bytes=source_path.stat().st_size,
                human_label=HumanLabel(cast(HumanLabelKind, kind), expected),
            )
        )
    return hashlib.sha256(content).hexdigest(), tuple(cases)


def _window_cases(
    inventory: Sequence[Path],
    *,
    offset: int,
    limit: int | None,
) -> tuple[AcceptanceCase, ...]:
    if offset < 0 or offset >= len(inventory):
        raise ValueError("Offset is outside the JPEG inventory.")
    stop = len(inventory) if limit is None else min(len(inventory), offset + limit)
    if limit is not None and limit < 1:
        raise ValueError("Limit must be positive.")
    return tuple(
        AcceptanceCase(
            sample_index=sample_index,
            source_index=source_index,
            relative_path=inventory[source_index].name,
            checksum_sha256=_sha256(inventory[source_index]),
            size_bytes=inventory[source_index].stat().st_size,
        )
        for sample_index, source_index in enumerate(range(offset, stop))
    )


def _load_selected_reviews(path: Path | None) -> tuple[str | None, dict[str, SelectedReview]]:
    if path is None:
        return None, {}
    content = path.resolve(strict=True).read_bytes()
    raw = _mapping(json.loads(content), "selected review")
    if raw.get("contract") != _REVIEW_CONTRACT:
        raise ValueError("Selected review contract is unsupported.")
    entries = raw.get("reviews")
    if not isinstance(entries, list):
        raise ValueError("Selected review must contain reviews.")
    result: dict[str, SelectedReview] = {}
    for index, value in enumerate(entries):
        item = _mapping(value, f"reviews[{index}]")
        relative_path = _text(item.get("relativePath"), "relativePath")
        if relative_path in result:
            raise ValueError("Selected review contains a duplicate source.")
        result[relative_path] = SelectedReview(
            relative_path=relative_path,
            expected_range=_range(item.get("expectedRange"), "expectedRange"),
            correct_range=bool(item.get("correctRange", False)),
            own_exact_proof_visible=bool(item.get("ownExactProofVisible", False)),
            near_evidence_midpoint=bool(item.get("nearEvidenceMidpoint", False)),
        )
    return hashlib.sha256(content).hexdigest(), result


def _source(case: AcceptanceCase) -> SemiAutomaticSelectionSource:
    return SemiAutomaticSelectionSource(
        source_index=case.sample_index,
        relative_path=case.relative_path,
        size_bytes=case.size_bytes,
        checksum_sha256=case.checksum_sha256,
    )


def _payload(case: AcceptanceCase, source_root: Path) -> MiddleRowSourcePayload:
    return MiddleRowSourcePayload(
        source=_source(case),
        content=(source_root / case.relative_path).read_bytes(),
    )


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * percentile))))
    return ordered[rank]


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
        get_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_memory_info.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)
        get_memory_info.restype = ctypes.c_bool
        process = ctypes.windll.kernel32.GetCurrentProcess()
        if get_memory_info(process, ctypes.byref(counters), counters.cb):
            return int(counters.peak)
    return None


def _quality_metrics(
    results: Sequence[tuple[AcceptanceCase, RangeEvidenceResult]],
) -> dict[str, object]:
    labelled = [(case, evidence) for case, evidence in results if case.human_label is not None]
    readable = [
        item
        for item in labelled
        if item[0].human_label is not None and item[0].human_label.kind == "human_readable_exact"
    ]
    unreadable = [
        item
        for item in labelled
        if item[0].human_label is not None and item[0].human_label.kind == "unreadable"
    ]
    exact = [item for item in labelled if item[1].status is RangeEvidenceStatus.EXACT_RANGE]
    correct_exact = [
        item
        for item in exact
        if item[0].human_label is not None
        and item[0].human_label.kind == "human_readable_exact"
        and item[1].observed_range == item[0].human_label.expected_range
    ]
    false_exact = len(exact) - len(correct_exact)
    readable_exact = sum(
        evidence.status is RangeEvidenceStatus.EXACT_RANGE
        and evidence.observed_range == case.human_label.expected_range
        for case, evidence in readable
        if case.human_label is not None
    )
    unreadable_unknown = sum(
        evidence.status is not RangeEvidenceStatus.EXACT_RANGE for _, evidence in unreadable
    )
    return {
        "labelledFrames": len(labelled),
        "allExactObservations": len(exact),
        "correctExactObservations": len(correct_exact),
        "exactPrecision": None if not exact else len(correct_exact) / len(exact),
        "falseExactCount": None if not labelled else false_exact,
        "humanAmbiguousFrames": sum(
            case.human_label is not None and case.human_label.kind == "ambiguous"
            for case, _ in labelled
        ),
        "humanReadableFrames": len(readable),
        "humanUnreadableFrames": len(unreadable),
        "readableFrameCoverage": None if not readable else readable_exact / len(readable),
        "unreadableUnknownRate": (None if not unreadable else unreadable_unknown / len(unreadable)),
    }


def _selected_metrics(
    selected: Sequence[dict[str, object]],
    reviews: Mapping[str, SelectedReview],
) -> dict[str, object]:
    reviewed = [
        (
            item,
            reviews[str(item["relativePath"])],
        )
        for item in selected
        if str(item["relativePath"]) in reviews
    ]
    all_reviewed = len(reviewed) == len(selected)
    return {
        "allSelectedReviewed": all_reviewed,
        "reviewedSelectedRanges": len(reviewed),
        "selectedFrameOwnProofRate": (
            None
            if not selected or not all_reviewed
            else sum(review.own_exact_proof_visible for _, review in reviewed) / len(reviewed)
        ),
        "selectedNearEvidenceMidpointRate": (
            None
            if not selected or not all_reviewed
            else sum(review.near_evidence_midpoint for _, review in reviewed) / len(reviewed)
        ),
        "selectedRangePrecision": (
            None
            if not selected or not all_reviewed
            else sum(
                review.correct_range
                and review.expected_range.start
                == _integer(item.get("rangeStart"), "selected.rangeStart")
                and review.expected_range.end == _integer(item.get("rangeEnd"), "selected.rangeEnd")
                for item, review in reviewed
            )
            / len(reviewed)
        ),
    }


def _apply_selected_review(
    payload: dict[str, object],
    *,
    selected_review_sha256: str | None,
    reviews: Mapping[str, SelectedReview],
) -> dict[str, object]:
    if payload.get("contract") != _REPORT_CONTRACT:
        raise ValueError("Acceptance report contract is unsupported.")
    grouping = _mapping(payload.get("grouping"), "grouping")
    selected_raw = grouping.get("selected")
    if not isinstance(selected_raw, list):
        raise ValueError("Acceptance report does not contain selected ranges.")
    selected = [dict(_mapping(item, "grouping.selected[]")) for item in selected_raw]
    selection = _selected_metrics(selected, reviews)
    mutable_grouping = dict(grouping)
    mutable_grouping.update(selection)
    payload["grouping"] = mutable_grouping
    gate_evaluation = dict(_mapping(payload.get("gateEvaluation"), "gateEvaluation"))
    results = payload.get("results")
    labelled_results = (
        [
            item
            for item in results
            if isinstance(item, Mapping) and item.get("humanLabel") is not None
        ]
        if isinstance(results, list)
        else []
    )
    quality = dict(_mapping(payload.get("quality"), "quality"))
    quality["labelledFrames"] = len(labelled_results)
    payload["quality"] = quality
    if isinstance(results, list) and not labelled_results:
        quality["falseExactCount"] = None
        quality["exactPrecision"] = None
        gate_evaluation["challengeOrGoldenPrecisionPassed"] = None
    gate_evaluation["selectedOwnProofPassed"] = selection["selectedFrameOwnProofRate"] == 1.0
    gate_evaluation["selectedPrecisionPassed"] = selection["selectedRangePrecision"] == 1.0
    payload["gateEvaluation"] = gate_evaluation
    payload["selectedReviewSha256"] = selected_review_sha256
    return payload


def run_acceptance(
    *,
    source_root: Path,
    cases: Sequence[AcceptanceCase],
    bounds: SemiAutomaticSequenceBounds,
    model_root: Path,
    orientation: MiddleRowRunOrientation,
    warmup_count: int,
    selected_reviews: Mapping[str, SelectedReview],
) -> dict[str, object]:
    if not cases:
        raise ValueError("Acceptance requires at least one source.")
    expected_ranges = ExpectedRangeTable.from_bounds(bounds)
    locator = MiddleRowTripleLocator()
    model_initialization_started = perf_counter()
    recognizer = build_middle_row_paddle_adapter(model_root.resolve(strict=True))
    model_initialization_seconds = perf_counter() - model_initialization_started
    sample_indexes = deterministic_orientation_sample_indexes(len(cases))
    calibration_payloads = tuple(_payload(cases[index], source_root) for index in sample_indexes)
    calibration_started = perf_counter()
    calibration = calibrate_middle_row_orientation(
        payloads=calibration_payloads,
        expected_ranges=expected_ranges,
        locator=locator,
        recognizer=recognizer,
        override=orientation,
    )
    calibration_seconds = perf_counter() - calibration_started
    if calibration.orientation is None:
        raise RuntimeError("V4.1 orientation could not be resolved for this corpus.")

    warmup_cases = tuple(cases[: min(max(0, warmup_count), len(cases))])
    warmup_started = perf_counter()
    if warmup_cases:
        warmup_runtime = MiddleRowBatchRuntime(
            run_id=uuid5(NAMESPACE_URL, "middle-row-v4-warmup"),
            expected_ranges=expected_ranges,
            rotation=calibration.orientation,
            locator=MiddleRowTripleLocator(),
            recognizer=recognizer,
        )
        for offset in range(0, len(warmup_cases), 6):
            warmup_runtime.process_batch(
                tuple(_payload(item, source_root) for item in warmup_cases[offset : offset + 6])
            )
    warmup_seconds = perf_counter() - warmup_started

    run_manifest = [
        {
            "relativePath": item.relative_path,
            "sha256": item.checksum_sha256,
            "sizeBytes": item.size_bytes,
            "sourceIndex": item.source_index,
        }
        for item in cases
    ]
    manifest_sha256 = hashlib.sha256(
        json.dumps(run_manifest, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    runtime = MiddleRowBatchRuntime(
        run_id=uuid5(NAMESPACE_URL, manifest_sha256),
        expected_ranges=expected_ranges,
        rotation=calibration.orientation,
        locator=MiddleRowTripleLocator(),
        recognizer=recognizer,
    )
    grouping = MiddleRowGroupingAccumulator()
    results: list[tuple[AcceptanceCase, RangeEvidenceResult]] = []
    selected: list[dict[str, object]] = []
    batch_seconds: list[float] = []
    source_seconds: list[float] = []
    source_read_seconds = 0.0
    grouping_seconds = 0.0
    scan_started = perf_counter()
    for offset in range(0, len(cases), 6):
        page = cases[offset : offset + 6]
        read_started = perf_counter()
        page_payloads = tuple(_payload(item, source_root) for item in page)
        source_read_seconds += perf_counter() - read_started
        started = perf_counter()
        evidence_page = runtime.process_batch(page_payloads)
        batch_duration = perf_counter() - started
        batch_seconds.append(batch_duration)
        source_seconds.extend([batch_duration / len(page)] * len(page))
        for case, evidence in zip(page, evidence_page, strict=True):
            results.append((case, evidence))
            grouping_started = perf_counter()
            finalized = grouping.consume(evidence)
            grouping_seconds += perf_counter() - grouping_started
            selected.extend(_selected_payload(item) for item in finalized)
    grouping_started = perf_counter()
    selected.extend(_selected_payload(item) for item in grouping.finish())
    grouping_seconds += perf_counter() - grouping_started
    scan_seconds = perf_counter() - scan_started

    quality = _quality_metrics(results)
    selection = _selected_metrics(selected, selected_reviews)
    reason_counts = Counter(reason for _, evidence in results for reason in evidence.reason_codes)
    exact_sources = sum(
        evidence.status is RangeEvidenceStatus.EXACT_RANGE for _, evidence in results
    )
    readable_groups = {
        case.human_label.expected_range
        for case, _ in results
        if case.human_label is not None
        and case.human_label.kind == "human_readable_exact"
        and case.human_label.expected_range is not None
    }
    selected_ranges = {
        (
            _integer(item["rangeStart"], "selected.rangeStart"),
            _integer(item["rangeEnd"], "selected.rangeEnd"),
        )
        for item in selected
    }
    captured_groups = sum((value.start, value.end) in selected_ranges for value in readable_groups)
    range_capture = None if not readable_groups else captured_groups / len(readable_groups)
    rejected_before_ocr = len(cases) - int(runtime.counters.values.get("locatedSources", 0))
    total_seconds = (
        model_initialization_seconds + calibration_seconds + warmup_seconds + scan_seconds
    )
    processing_time_totals: dict[str, float] = {}
    for _, evidence in results:
        processing_times = evidence.runtime_diagnostics.get("processingTimes", {})
        if isinstance(processing_times, Mapping):
            for key, value in processing_times.items():
                if isinstance(value, int | float) and not isinstance(value, bool):
                    name = str(key)
                    processing_time_totals[name] = processing_time_totals.get(name, 0.0) + float(
                        value
                    )
    results_payload = [
        {
            "actualRange": (
                None
                if evidence.observed_range is None
                else [evidence.observed_range.start, evidence.observed_range.end]
            ),
            "confidence": evidence.confidence,
            "humanLabel": (
                None
                if case.human_label is None
                else {
                    "expectedRange": (
                        None
                        if case.human_label.expected_range is None
                        else [
                            case.human_label.expected_range.start,
                            case.human_label.expected_range.end,
                        ]
                    ),
                    "kind": case.human_label.kind,
                }
            ),
            "minimumOcrConfidence": evidence.minimum_ocr_confidence,
            "observationKey": evidence.observation_key,
            "originalSourceIndex": case.source_index,
            "reasonCodes": list(evidence.reason_codes),
            "relativePath": case.relative_path,
            "runtimeDiagnostics": dict(evidence.runtime_diagnostics),
            "sha256": case.checksum_sha256,
            "status": evidence.status.value,
        }
        for case, evidence in results
    ]
    return {
        "contract": _REPORT_CONTRACT,
        "gateEvaluation": {
            "challengeOrGoldenPrecisionPassed": (
                None if quality["falseExactCount"] is None else quality["falseExactCount"] == 0
            ),
            "coveragePassed": (
                quality["readableFrameCoverage"] is not None
                and float(cast(float, quality["readableFrameCoverage"])) >= 0.50
            ),
            "groupCapturePassed": range_capture is not None and range_capture >= 0.90,
            "selectedOwnProofPassed": selection["selectedFrameOwnProofRate"] == 1.0,
            "selectedPrecisionPassed": selection["selectedRangePrecision"] == 1.0,
        },
        "grouping": {
            "capturedHumanReadableGroups": captured_groups,
            "humanReadableGroups": len(readable_groups),
            "rangeGroupCaptureRate": range_capture,
            "selected": selected,
            **selection,
        },
        "manifest": {
            "cases": run_manifest,
            "sha256": manifest_sha256,
        },
        "orientation": calibration.as_dict(),
        "quality": quality,
        "recognizer": {
            "contractFingerprint": MIDDLE_ROW_RECOGNIZER_CONTRACT_FINGERPRINT_V4,
            "runtimeFingerprint": runtime.runtime_fingerprint,
            **recognizer.identity,
        },
        "results": results_payload,
        "sample": {
            "firstOriginalSourceIndex": cases[0].source_index,
            "lastOriginalSourceIndex": cases[-1].source_index,
            "size": len(cases),
        },
        "timing": {
            "batchP50Seconds": _percentile(batch_seconds, 0.50),
            "batchP95Seconds": _percentile(batch_seconds, 0.95),
            "calibrationSeconds": calibration_seconds,
            "checkpointSeconds": 0.0,
            "decodeSeconds": processing_time_totals.get("decodeSeconds", 0.0),
            "exifSeconds": processing_time_totals.get("exifSeconds", 0.0),
            "groupingSeconds": grouping_seconds,
            "locatorSeconds": processing_time_totals.get("locatorSeconds", 0.0),
            "medianTimePerSource": _percentile(source_seconds, 0.50),
            "modelInitializationSeconds": model_initialization_seconds,
            "ocrCalls": recognizer.metrics.calls,
            "ocrCrops": recognizer.metrics.crops,
            "ocrInferenceSeconds": recognizer.metrics.inference_seconds,
            "ocrInternalBatches": recognizer.metrics.internal_batches,
            "ocrPreprocessingSeconds": recognizer.metrics.preprocessing_seconds,
            "ocrRecognitionSeconds": recognizer.metrics.recognition_seconds,
            "peakMemoryBytes": _peak_rss_bytes(),
            "p95TimePerSource": _percentile(source_seconds, 0.95),
            "projected42000ScanSeconds": 42_000 * scan_seconds / len(cases),
            "rotationSeconds": processing_time_totals.get("rotationSeconds", 0.0),
            "scanSeconds": scan_seconds,
            "sourceReadSeconds": source_read_seconds,
            "sourcesPerSecond": len(cases) / scan_seconds,
            "totalSeconds": total_seconds,
            "warmupSeconds": warmup_seconds,
        },
        "diagnostics": {
            "exactSources": exact_sources,
            "ocrBatchFillRatio": recognizer.metrics.batch_fill_ratio,
            "reasonCounts": dict(sorted(reason_counts.items())),
            "rejectedBeforeOcrCount": rejected_before_ocr,
            "rejectedBeforeOcrRatio": rejected_before_ocr / len(cases),
            "runtimeCounters": dict(sorted(runtime.counters.values.items())),
        },
        "versions": {
            "batchPolicy": DEFAULT_MIDDLE_ROW_RUNTIME_POLICY.batch.as_dict(),
            "report": _REPORT_CONTRACT,
        },
    }


def _selected_payload(value: object) -> dict[str, object]:
    finalized = cast(Any, value)
    evidence = finalized.selection.evidence
    sequence_range = finalized.group.sequence_range
    return {
        "evidenceDistanceFromMidpoint": abs(
            evidence.source.source_index
            - (finalized.group.first_source_index + finalized.group.last_source_index) / 2
        ),
        "evidenceSpan": [
            finalized.group.first_source_index,
            finalized.group.last_source_index,
        ],
        "observationKey": evidence.observation_key,
        "rangeEnd": sequence_range.end,
        "rangeStart": sequence_range.start,
        "relativePath": evidence.source.relative_path,
        "selectionMethod": finalized.selection.selection_method,
        "sourceIndex": evidence.source.source_index,
    }


def main() -> int:
    args = _arguments()
    report = args.report.resolve()
    selected_review_sha256, reviews = _load_selected_reviews(args.selected_review)
    if args.apply_selected_review_to_existing_report:
        if args.selected_review is None:
            raise ValueError("Applying a review requires --selected-review.")
        payload = _mapping(json.loads(report.resolve(strict=True).read_bytes()), "report")
        updated = _apply_selected_review(
            dict(payload),
            selected_review_sha256=selected_review_sha256,
            reviews=reviews,
        )
        report.write_text(
            json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "report": str(report),
                    "selectedRanges": len(updated["grouping"]["selected"]),  # type: ignore[index]
                    "selectedReviewApplied": True,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    source_root = args.source_root.resolve(strict=True)
    if report.is_relative_to(source_root):
        raise ValueError("Acceptance report must be outside the read-only source directory.")
    inventory = _jpeg_inventory(source_root)
    corpus_manifest_sha256: str | None = None
    if args.corpus_manifest is not None:
        corpus_manifest_sha256, cases = _load_manifest(
            args.corpus_manifest,
            source_root=source_root,
            inventory=inventory,
        )
    else:
        cases = _window_cases(inventory, offset=args.offset, limit=args.limit)
    payload = run_acceptance(
        source_root=source_root,
        cases=cases,
        bounds=SemiAutomaticSequenceBounds(args.first_sequence, args.last_sequence),
        model_root=args.ocr_model_root,
        orientation=MiddleRowRunOrientation(args.orientation),
        warmup_count=args.warmup_count,
        selected_reviews=reviews,
    )
    payload["corpusManifestSha256"] = corpus_manifest_sha256
    payload["selectedReviewSha256"] = selected_review_sha256
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = {
        "exactSources": payload["diagnostics"]["exactSources"],  # type: ignore[index]
        "falseExactCount": payload["quality"]["falseExactCount"],  # type: ignore[index]
        "report": str(report),
        "sampleSize": payload["sample"]["size"],  # type: ignore[index]
        "selectedRanges": len(payload["grouping"]["selected"]),  # type: ignore[index]
        "sourcesPerSecond": payload["timing"]["sourcesPerSecond"],  # type: ignore[index]
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
