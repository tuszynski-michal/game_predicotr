"""Profile a read-only natural-order slice of a browser image selection.

This operator tool intentionally skips persistence and output publication.  It
measures only the selector work: cheap scans, grouping, candidate ranking and
full verification.  The source staging is opened read-only and no production
scan cache is used, so repeated runs do not hide cold-analysis cost.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.benchmarks.performance import (  # noqa: E402
    PeakMemorySampler,
)
from game_predictor_worker.images.selection.adapters import (  # noqa: E402
    AnchoredSequenceRangeRecognizer,
    DeterministicParallelCandidateVerifier,
    IndependentEndpointVisibleSequenceLabelRangeRecognizer,
    build_default_adapters,
    configure_opencv_thread_budget,
)
from game_predictor_worker.images.selection.contracts import (  # noqa: E402
    CandidateVerifier,
    CheapImageAnalyzer,
    CheapImageObservation,
    ImageSelectionSource,
    SelectionGroupResult,
    SelectorCheckpoint,
)
from game_predictor_worker.images.selection.engine import FastImageSelector  # noqa: E402
from game_predictor_worker.images.selection.io import (  # noqa: E402
    load_browser_selection_manifest,
)
from game_predictor_worker.images.selection.manifest import (  # noqa: E402
    ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101_INDEPENDENT_RANGE,
)
from game_predictor_worker.images.selection.telemetry import (  # noqa: E402
    StageTimingCollector,
)
from game_predictor_worker.images.sequence_ocr import (  # noqa: E402
    PaddleSequenceNumberRecognizer,
)


@dataclass(frozen=True, slots=True)
class _FinalizedGroupTiming:
    group_order: int
    source_count: int
    first_source_index: int
    last_source_index: int
    elapsed_since_previous_group_seconds: float
    elapsed_since_start_seconds: float
    status: str
    recognized_range: str | None
    selected_checksum_sha256: str | None
    selected_source_relative_path: str | None
    top_candidates: tuple[dict[str, object], ...]


class _ProgressAnalyzer:
    def __init__(self, inner: CheapImageAnalyzer, *, total: int) -> None:
        self._inner = inner
        self._total = total
        self._completed = 0
        self._lock = Lock()

    def analyze(self, source: ImageSelectionSource) -> CheapImageObservation:
        result = self._inner.analyze(source)
        with self._lock:
            self._completed += 1
            completed = self._completed
            if completed == 1 or completed % 10 == 0 or completed == self._total:
                print(
                    f"SCAN {completed}/{self._total} elapsed={perf_counter() - _STARTED_AT:.1f}s",
                    flush=True,
                )
        return result


class _TimingSink:
    def __init__(self, started_at: float, *, first_source_index: int = 0) -> None:
        self._started_at = started_at
        self._previous_group_at = started_at
        self._groups: dict[int, _FinalizedGroupTiming] = {}
        self._source_index_offset = first_source_index
        self._next_source_index = first_source_index

    def candidate_scanned(
        self,
        observation: CheapImageObservation,
        *,
        group_order: int,
    ) -> None:
        del observation, group_order

    def checkpoint_saved(self, checkpoint: SelectorCheckpoint) -> None:
        print(
            f"CHECKPOINT {checkpoint.processed_count} groups={checkpoint.finalized_group_count}",
            flush=True,
        )

    def group_finalized(self, group: SelectionGroupResult) -> None:
        # Recovery may publish a revised decision for an already finalized
        # group.  Keep the original wall-clock boundary for timing purposes.
        if group.group_order in self._groups:
            return
        now = perf_counter()
        first_source_index = self._next_source_index
        last_source_index = first_source_index + group.source_count - 1
        recognized = None if group.range is None else f"{group.range.start}-{group.range.end}"
        timing = _FinalizedGroupTiming(
            group_order=group.group_order,
            source_count=group.source_count,
            first_source_index=first_source_index,
            last_source_index=last_source_index,
            elapsed_since_previous_group_seconds=now - self._previous_group_at,
            elapsed_since_start_seconds=now - self._started_at,
            status=group.status.value,
            recognized_range=recognized,
            selected_checksum_sha256=(
                None
                if group.selected_candidate is None
                else group.selected_candidate.source.checksum_sha256
            ),
            selected_source_relative_path=(
                None
                if group.selected_candidate is None
                else group.selected_candidate.source.relative_path
            ),
            top_candidates=tuple(
                {
                    "checksumSha256": candidate.source.checksum_sha256,
                    "decision": candidate.decision.value,
                    "orderIndex": candidate.source.order_index + self._source_index_offset,
                    "recognizedRange": (
                        None
                        if candidate.recognized_range is None
                        else (
                            f"{candidate.recognized_range.start}-{candidate.recognized_range.end}"
                        )
                    ),
                    "reasonCodes": list(candidate.reason_codes),
                    "sourceRelativePath": candidate.source.relative_path,
                }
                for candidate in group.top_candidates
            ),
        )
        self._groups[group.group_order] = timing
        self._next_source_index = last_source_index + 1
        self._previous_group_at = now
        print(
            "GROUP "
            f"{timing.group_order + 1} sources={timing.source_count} "
            f"range={timing.recognized_range or 'unknown'} "
            f"seconds={timing.elapsed_since_previous_group_seconds:.3f}",
            flush=True,
        )

    @property
    def groups(self) -> tuple[_FinalizedGroupTiming, ...]:
        return tuple(self._groups[index] for index in sorted(self._groups))


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--scan-workers", type=int, default=4)
    parser.add_argument("--verification-workers", type=int, default=2)
    parser.add_argument("--max-seconds", type=float, default=1_800.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--baseline",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts" / "image-selection-v10-first-200-timing.json",
    )
    parser.add_argument(
        "--ocr-model-root",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts" / "m5-models" / "sequence-number-ocr-v1",
    )
    return parser.parse_args()


def _round(value: float) -> float:
    return round(value, 6)


def _build_verification_adapters(
    source_root: Path,
    model_root: Path,
    telemetry: StageTimingCollector,
) -> tuple[CheapImageAnalyzer, CandidateVerifier]:
    manifest = ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101_INDEPENDENT_RANGE
    fallback_policy = manifest.progressive_visible_label_fallback_policy
    if fallback_policy is None:
        raise RuntimeError("The v10.1 profile requires progressive fallback policy.")
    ocr = PaddleSequenceNumberRecognizer(model_root)
    return build_default_adapters(
        source_root,
        range_recognizer=AnchoredSequenceRangeRecognizer(ocr, telemetry=telemetry),
        fallback_range_recognizer=IndependentEndpointVisibleSequenceLabelRangeRecognizer(
            ocr,
            fallback_policy,
            telemetry=telemetry,
        ),
        manifest=manifest,
        telemetry=telemetry,
    )


def _baseline_comparison(
    baseline_path: Path,
    *,
    manifest_sha256: str,
    image_count: int,
    elapsed_seconds: float,
    groups: tuple[_FinalizedGroupTiming, ...],
) -> dict[str, object]:
    if not baseline_path.is_file():
        return {"available": False, "reason": "baseline_report_missing"}
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {"available": False, "reason": "baseline_report_invalid"}
    source = baseline.get("source")
    summary = baseline.get("summary")
    baseline_groups = baseline.get("groups")
    if (
        not isinstance(source, dict)
        or not isinstance(summary, dict)
        or not isinstance(baseline_groups, list)
    ):
        return {"available": False, "reason": "baseline_contract_invalid"}
    comparable_source = (
        source.get("manifestSha256") == manifest_sha256
        and source.get("analyzedImageCount") == image_count
    )
    baseline_boundaries = [
        (item.get("firstSourceIndex"), item.get("lastSourceIndex"))
        for item in baseline_groups
        if isinstance(item, dict)
    ]
    current_boundaries = [(item.first_source_index, item.last_source_index) for item in groups]
    baseline_ranges = [
        item.get("recognizedRange") for item in baseline_groups if isinstance(item, dict)
    ]
    current_ranges = [item.recognized_range for item in groups]
    baseline_checksums = [
        item.get("selectedChecksumSha256") for item in baseline_groups if isinstance(item, dict)
    ]
    representative_comparison_available = len(baseline_checksums) == len(baseline_groups) and all(
        isinstance(value, str) for value in baseline_checksums
    )
    changed_representatives = (
        [
            {
                "group": item.group_order + 1,
                "baselineChecksumSha256": baseline_checksums[index],
                "currentChecksumSha256": item.selected_checksum_sha256,
                "currentSourceRelativePath": item.selected_source_relative_path,
            }
            for index, item in enumerate(groups)
            if baseline_checksums[index] != item.selected_checksum_sha256
        ]
        if representative_comparison_available and len(baseline_checksums) == len(groups)
        else []
    )
    baseline_seconds_value = summary.get("totalSeconds")
    baseline_seconds = (
        float(baseline_seconds_value) if isinstance(baseline_seconds_value, int | float) else None
    )
    reduction = (
        None
        if baseline_seconds is None or baseline_seconds <= 0
        else (baseline_seconds - elapsed_seconds) / baseline_seconds * 100
    )
    return {
        "available": True,
        "comparableSource": comparable_source,
        "baselineTotalSeconds": baseline_seconds,
        "timeReductionPercent": None if reduction is None else _round(reduction),
        "firstTargetMet": elapsed_seconds <= 151,
        "firstTargetBand": 113 <= elapsed_seconds <= 151,
        "extendedTargetMet": elapsed_seconds < 113,
        "boundaryMatch": baseline_boundaries == current_boundaries,
        "rangeMatch": baseline_ranges == current_ranges,
        "representativeComparisonAvailable": representative_comparison_available,
        "changedRepresentatives": changed_representatives,
    }


def main() -> None:
    global _STARTED_AT
    args = _arguments()
    if not 1 <= args.limit <= 10_000:
        raise ValueError("--limit must be between 1 and 10000")
    if args.start_index < 0:
        raise ValueError("--start-index cannot be negative")
    if not 1 <= args.scan_workers <= 8:
        raise ValueError("--scan-workers must be between 1 and 8")
    if not 1 <= args.verification_workers <= 2:
        raise ValueError("--verification-workers must be one or two")
    if not 1 <= args.max_seconds <= 21_600:
        raise ValueError("--max-seconds must be between 1 and 21600")

    source_root = args.source_root.resolve(strict=True)
    sources, manifest_sha256 = load_browser_selection_manifest(
        source_root / "_browser_manifest.json"
    )
    source_slice = sources[args.start_index : args.start_index + args.limit]
    if len(source_slice) != args.limit:
        raise ValueError(f"Staging contains only {len(sources)} images")
    expected_order = tuple(range(args.start_index, args.start_index + args.limit))
    if tuple(source.order_index for source in source_slice) != expected_order:
        raise ValueError("Selected source slice does not preserve natural zero-based order")
    # The production selector contract intentionally starts each run at zero.
    # Rebase this read-only slice locally while retaining the original source
    # indexes in timing and candidate diagnostics.
    selected_sources = tuple(
        replace(source, order_index=local_index) for local_index, source in enumerate(source_slice)
    )

    telemetry = StageTimingCollector()
    configure_opencv_thread_budget(1)
    model_root = args.ocr_model_root.resolve(strict=True)
    analyzer, primary_verifier = _build_verification_adapters(
        source_root,
        model_root,
        telemetry,
    )
    verifier: CandidateVerifier = primary_verifier
    if args.verification_workers == 2:
        _, secondary_verifier = _build_verification_adapters(
            source_root,
            model_root,
            telemetry,
        )
        verifier = DeterministicParallelCandidateVerifier(
            (primary_verifier, secondary_verifier),
            telemetry=telemetry,
        )

    _STARTED_AT = perf_counter()
    sink = _TimingSink(_STARTED_AT, first_source_index=args.start_index)
    with PeakMemorySampler(interval_seconds=0.1) as memory_sampler:
        result = FastImageSelector(
            ADAPTIVE_ACCURACY_SELECTOR_MANIFEST_V101_INDEPENDENT_RANGE,
            scan_workers=args.scan_workers,
            scan_prefetch=min(args.scan_workers * 2, 64),
        ).select(
            selected_sources,
            analyzer=_ProgressAnalyzer(analyzer, total=args.limit),
            verifier=verifier,
            audit_sink=sink,
        )
        elapsed = perf_counter() - _STARTED_AT
    memory = memory_sampler.summary()
    if elapsed > args.max_seconds:
        raise TimeoutError(f"Profile exceeded its declared {args.max_seconds:.0f}s time budget")

    groups = sink.groups
    durations = [group.elapsed_since_previous_group_seconds for group in groups]
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "profile": "image-selection-natural-order-slice-v1",
        "source": {
            "manifestSha256": manifest_sha256,
            "stagingImageCount": len(sources),
            "analyzedImageCount": args.limit,
            "firstOrderIndex": args.start_index,
            "lastOrderIndex": args.start_index + args.limit - 1,
            "cachePolicy": "disabled-cold-analysis",
            "publicationPolicy": "disabled-read-only-profile",
        },
        "selector": {
            "version": result.selector_version,
            "fingerprint": result.selector_fingerprint,
            "scanWorkers": args.scan_workers,
            "verificationWorkers": args.verification_workers,
            "verificationCount": result.verification_count,
            "scanFailureCount": result.scan_failure_count,
        },
        "summary": {
            "totalSeconds": _round(elapsed),
            "groupCount": len(groups),
            "imagesPerSecond": _round(args.limit / elapsed),
            "meanSecondsPerImage": _round(elapsed / args.limit),
            "meanSecondsPerGroup": _round(statistics.fmean(durations)),
            "medianSecondsPerGroup": _round(statistics.median(durations)),
            "minimumSecondsPerGroup": _round(min(durations)),
            "maximumSecondsPerGroup": _round(max(durations)),
        },
        "groups": [
            {
                "group": group.group_order + 1,
                "sourceCount": group.source_count,
                "firstSourceIndex": group.first_source_index,
                "lastSourceIndex": group.last_source_index,
                "elapsedSeconds": _round(group.elapsed_since_previous_group_seconds),
                "elapsedSinceStartSeconds": _round(group.elapsed_since_start_seconds),
                "status": group.status,
                "recognizedRange": group.recognized_range,
                "selectedChecksumSha256": group.selected_checksum_sha256,
                "selectedSourceRelativePath": group.selected_source_relative_path,
                "topCandidates": list(group.top_candidates),
            }
            for group in groups
        ],
        "stageTiming": telemetry.snapshot(),
        "memory": memory.to_dict(),
        "baselineComparison": _baseline_comparison(
            args.baseline.resolve(),
            manifest_sha256=manifest_sha256,
            image_count=args.limit,
            elapsed_seconds=elapsed,
            groups=groups,
        ),
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = output.with_suffix(output.suffix + ".pending")
    pending.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    pending.replace(output)
    print(json.dumps(report["summary"], indent=2, sort_keys=True), flush=True)
    print(f"REPORT {output}", flush=True)


_STARTED_AT = 0.0


if __name__ == "__main__":
    main()
