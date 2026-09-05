"""Run checksum-bound, read-only acceptance for row-first range OCR v5.

The harness deliberately reuses the immutable human labels and review protocol
from the v4.1 acceptance utility, but never changes v4.1's runtime, reports or
fingerprints.  Source filenames and inventory indexes identify bytes only;
expected ranges come solely from explicit run bounds and human labels are used
only for evaluation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from time import perf_counter
from typing import cast
from uuid import NAMESPACE_URL, uuid5

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPOSITORY_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "services" / "worker" / "src"))

from game_predictor_worker.semi_automatic_selection.contracts import (  # type: ignore[import-untyped] # noqa: E402
    RangeEvidenceResult,
    RangeEvidenceStatus,
    SemiAutomaticSelectionSource,
    SemiAutomaticSequenceBounds,
)
from game_predictor_worker.semi_automatic_selection.middle_row_grouping import (  # type: ignore[import-untyped] # noqa: E402
    ROW_FIRST_EVIDENCE_SELECTOR_VERSION,
    ROW_FIRST_GROUPING_VERSION,
    MiddleRowGroupingAccumulator,
)
from game_predictor_worker.semi_automatic_selection.middle_row_runtime import (  # type: ignore[import-untyped] # noqa: E402
    MiddleRowPaddleRecognitionAdapter,
    build_middle_row_paddle_adapter,
)
from game_predictor_worker.semi_automatic_selection.range_proof_v5 import (  # type: ignore[import-untyped] # noqa: E402
    RowExpectedRangeTable,
)
from game_predictor_worker.semi_automatic_selection.row_first_locator_v5 import (  # type: ignore[import-untyped] # noqa: E402
    RowFirstTripleLocator,
)
from game_predictor_worker.semi_automatic_selection.row_first_runtime_v5 import (  # type: ignore[import-untyped] # noqa: E402
    DEFAULT_ROW_FIRST_RUNTIME_POLICY,
    ROW_FIRST_RECOGNIZER_CONTRACT_FINGERPRINT_V5,
    RowFirstBatchRuntime,
    RowFirstSourcePayload,
)
from run_middle_row_range_ocr_v4_acceptance import (  # noqa: E402
    AcceptanceCase,
    HumanLabel,
    SelectedReview,
    _jpeg_inventory,
    _load_manifest,
    _load_selected_reviews,
    _peak_rss_bytes,
    _percentile,
    _quality_metrics,
    _selected_metrics,
    _selected_payload,
    _window_cases,
)

_REPORT_CONTRACT = "row-first-range-ocr-v5-acceptance-v1"
_HARNESS_VERSION = "row-first-range-ocr-v5-harness-v1"

__all__ = ["AcceptanceCase", "HumanLabel", "SelectedReview", "run_acceptance"]

RecognizerFactory = Callable[[Path], MiddleRowPaddleRecognitionAdapter]
LocatorFactory = Callable[[], RowFirstTripleLocator]


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
    parser.add_argument("--warmup-count", type=int, default=6)
    parser.add_argument(
        "--ocr-model-root",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts" / "m5-models" / "sequence-number-ocr-v1",
    )
    return parser.parse_args()


def _source(case: AcceptanceCase) -> SemiAutomaticSelectionSource:
    return SemiAutomaticSelectionSource(
        source_index=case.sample_index,
        relative_path=case.relative_path,
        size_bytes=case.size_bytes,
        checksum_sha256=case.checksum_sha256,
    )


def _payload(case: AcceptanceCase, source_root: Path) -> RowFirstSourcePayload:
    return RowFirstSourcePayload(
        source=_source(case),
        content=(source_root / case.relative_path).read_bytes(),
    )


def _manifest(cases: Sequence[AcceptanceCase]) -> tuple[list[dict[str, object]], str]:
    values = [
        {
            "relativePath": item.relative_path,
            "sha256": item.checksum_sha256,
            "sizeBytes": item.size_bytes,
            "sourceIndex": item.source_index,
        }
        for item in cases
    ]
    checksum = hashlib.sha256(
        json.dumps(values, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    return values, checksum


def _report_integer(value: object, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context} must be an integer.")
    return value


def run_acceptance(
    *,
    source_root: Path,
    cases: Sequence[AcceptanceCase],
    bounds: SemiAutomaticSequenceBounds,
    model_root: Path,
    warmup_count: int,
    selected_reviews: Mapping[str, SelectedReview],
    recognizer_factory: RecognizerFactory = build_middle_row_paddle_adapter,
    locator_factory: LocatorFactory = RowFirstTripleLocator,
) -> dict[str, object]:
    """Evaluate v5 without writing source, job, staging or database state."""

    if not cases:
        raise ValueError("Acceptance requires at least one source.")
    if warmup_count < 0:
        raise ValueError("Warmup count cannot be negative.")
    expected_ranges = RowExpectedRangeTable.from_bounds(bounds)
    model_initialization_started = perf_counter()
    recognizer = recognizer_factory(model_root.resolve(strict=True))
    model_initialization_seconds = perf_counter() - model_initialization_started
    manifest, manifest_sha256 = _manifest(cases)
    batch_size = DEFAULT_ROW_FIRST_RUNTIME_POLICY.batch.source_batch_size

    warmup_cases = tuple(cases[: min(warmup_count, len(cases))])
    warmup_started = perf_counter()
    if warmup_cases:
        warmup_runtime = RowFirstBatchRuntime(
            run_id=uuid5(NAMESPACE_URL, "row-first-v5-warmup"),
            expected_ranges=expected_ranges,
            locator=locator_factory(),
            recognizer=recognizer,
        )
        for offset in range(0, len(warmup_cases), batch_size):
            warmup_runtime.process_batch(
                tuple(
                    _payload(item, source_root)
                    for item in warmup_cases[offset : offset + batch_size]
                )
            )
    warmup_seconds = perf_counter() - warmup_started

    runtime = RowFirstBatchRuntime(
        run_id=uuid5(NAMESPACE_URL, manifest_sha256),
        expected_ranges=expected_ranges,
        locator=locator_factory(),
        recognizer=recognizer,
    )
    grouping = MiddleRowGroupingAccumulator(
        algorithm_version=ROW_FIRST_GROUPING_VERSION,
        selector_version=ROW_FIRST_EVIDENCE_SELECTOR_VERSION,
    )
    results: list[tuple[AcceptanceCase, RangeEvidenceResult]] = []
    selected: list[dict[str, object]] = []
    batch_seconds: list[float] = []
    source_seconds: list[float] = []
    source_read_seconds = 0.0
    grouping_seconds = 0.0
    scan_started = perf_counter()
    for offset in range(0, len(cases), batch_size):
        page = cases[offset : offset + batch_size]
        read_started = perf_counter()
        payloads = tuple(_payload(item, source_root) for item in page)
        source_read_seconds += perf_counter() - read_started
        started = perf_counter()
        evidence_page = runtime.process_batch(payloads)
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
    readable_groups = {
        case.human_label.expected_range
        for case, _ in results
        if case.human_label is not None
        and case.human_label.kind == "human_readable_exact"
        and case.human_label.expected_range is not None
    }
    selected_ranges = {
        (
            _report_integer(item.get("rangeStart"), "selected.rangeStart"),
            _report_integer(item.get("rangeEnd"), "selected.rangeEnd"),
        )
        for item in selected
    }
    captured_groups = sum((value.start, value.end) in selected_ranges for value in readable_groups)
    range_capture = None if not readable_groups else captured_groups / len(readable_groups)
    rejected_before_ocr = len(cases) - int(runtime.counters.values.get("locatedSources", 0))

    return {
        "contract": _REPORT_CONTRACT,
        "gateEvaluation": {
            "challengeOrGoldenPrecisionPassed": (
                None if quality["falseExactCount"] is None else quality["falseExactCount"] == 0
            ),
            "coveragePassed": quality["readableFrameCoverage"] is not None
            and float(cast(float, quality["readableFrameCoverage"])) >= 0.50,
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
        "manifest": {"cases": manifest, "sha256": manifest_sha256},
        "orientation": {
            "policy": "exif_canonical_only",
            "rotationDegrees": 0,
            "version": DEFAULT_ROW_FIRST_RUNTIME_POLICY.orientation.version,
        },
        "quality": quality,
        "recognizer": {
            "contractFingerprint": ROW_FIRST_RECOGNIZER_CONTRACT_FINGERPRINT_V5,
            "runtimeFingerprint": runtime.runtime_fingerprint,
            **recognizer.identity,
        },
        "results": [_result_payload(case, evidence) for case, evidence in results],
        "sample": {
            "firstOriginalSourceIndex": cases[0].source_index,
            "lastOriginalSourceIndex": cases[-1].source_index,
            "size": len(cases),
        },
        "timing": {
            "batchP50Seconds": _percentile(batch_seconds, 0.50),
            "batchP95Seconds": _percentile(batch_seconds, 0.95),
            "checkpointSeconds": 0.0,
            "groupingSeconds": grouping_seconds,
            "locatorSeconds": sum(
                float(evidence.runtime_diagnostics.get("locatorSeconds", 0.0))
                for _, evidence in results
            ),
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
            "scanSeconds": scan_seconds,
            "sourceReadSeconds": source_read_seconds,
            "sourcesPerSecond": len(cases) / scan_seconds,
            "totalSeconds": model_initialization_seconds + warmup_seconds + scan_seconds,
            "warmupSeconds": warmup_seconds,
        },
        "diagnostics": {
            "exactSources": sum(
                evidence.status is RangeEvidenceStatus.EXACT_RANGE for _, evidence in results
            ),
            "ocrBatchFillRatio": recognizer.metrics.batch_fill_ratio,
            "reasonCounts": dict(sorted(reason_counts.items())),
            "rejectedBeforeOcrCount": rejected_before_ocr,
            "rejectedBeforeOcrRatio": rejected_before_ocr / len(cases),
            "runtimeCounters": dict(sorted(runtime.counters.values.items())),
        },
        "versions": {
            "batchPolicy": DEFAULT_ROW_FIRST_RUNTIME_POLICY.batch.as_dict(),
            "harness": _HARNESS_VERSION,
            "report": _REPORT_CONTRACT,
        },
    }


def _result_payload(
    case: AcceptanceCase,
    evidence: RangeEvidenceResult,
) -> dict[str, object]:
    return {
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


def main() -> int:
    args = _arguments()
    report = args.report.resolve()
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
    selected_review_sha256, reviews = _load_selected_reviews(args.selected_review)
    payload = run_acceptance(
        source_root=source_root,
        cases=cases,
        bounds=SemiAutomaticSequenceBounds(args.first_sequence, args.last_sequence),
        model_root=args.ocr_model_root,
        warmup_count=args.warmup_count,
        selected_reviews=reviews,
    )
    payload["corpusManifestSha256"] = corpus_manifest_sha256
    payload["selectedReviewSha256"] = selected_review_sha256
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "exactSources": payload["diagnostics"]["exactSources"],  # type: ignore[index]
                "falseExactCount": payload["quality"]["falseExactCount"],  # type: ignore[index]
                "report": str(report),
                "sampleSize": payload["sample"]["size"],  # type: ignore[index]
                "selectedRanges": len(payload["grouping"]["selected"]),  # type: ignore[index]
                "sourcesPerSecond": payload["timing"]["sourcesPerSecond"],  # type: ignore[index]
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
