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
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.selection.adapters import (  # noqa: E402
    AccuracyFirstVisibleSequenceLabelRangeRecognizer,
    AnchoredSequenceRangeRecognizer,
    build_default_adapters,
)
from game_predictor_worker.images.selection.contracts import (  # noqa: E402
    CandidateVerification,
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
    ACCURACY_FIRST_SELECTOR_MANIFEST_V10,
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


class _ProgressVerifier:
    def __init__(self, inner: CandidateVerifier) -> None:
        self._inner = inner

    def verify(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        return self._inner.verify(
            observation,
            expected_board_count=expected_board_count,
        )


class _TimingSink:
    def __init__(self, started_at: float) -> None:
        self._started_at = started_at
        self._previous_group_at = started_at
        self._groups: dict[int, _FinalizedGroupTiming] = {}
        self._next_source_index = 0

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
    parser.add_argument("--scan-workers", type=int, default=4)
    parser.add_argument("--max-seconds", type=float, default=1_800.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--ocr-model-root",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts" / "m5-models" / "sequence-number-ocr-v1",
    )
    return parser.parse_args()


def _round(value: float) -> float:
    return round(value, 6)


def main() -> None:
    global _STARTED_AT
    args = _arguments()
    if not 1 <= args.limit <= 10_000:
        raise ValueError("--limit must be between 1 and 10000")
    if not 1 <= args.scan_workers <= 8:
        raise ValueError("--scan-workers must be between 1 and 8")
    if not 1 <= args.max_seconds <= 21_600:
        raise ValueError("--max-seconds must be between 1 and 21600")

    source_root = args.source_root.resolve(strict=True)
    sources, manifest_sha256 = load_browser_selection_manifest(
        source_root / "_browser_manifest.json"
    )
    selected_sources = sources[: args.limit]
    if len(selected_sources) != args.limit:
        raise ValueError(f"Staging contains only {len(sources)} images")
    expected_order = tuple(range(args.limit))
    if tuple(source.order_index for source in selected_sources) != expected_order:
        raise ValueError("Selected source slice does not preserve natural zero-based order")

    telemetry = StageTimingCollector()
    ocr = PaddleSequenceNumberRecognizer(args.ocr_model_root.resolve(strict=True))
    analyzer, verifier = build_default_adapters(
        source_root,
        range_recognizer=AnchoredSequenceRangeRecognizer(ocr, telemetry=telemetry),
        fallback_range_recognizer=AccuracyFirstVisibleSequenceLabelRangeRecognizer(
            ocr,
            telemetry=telemetry,
        ),
        manifest=ACCURACY_FIRST_SELECTOR_MANIFEST_V10,
        telemetry=telemetry,
    )

    _STARTED_AT = perf_counter()
    sink = _TimingSink(_STARTED_AT)
    result = FastImageSelector(
        ACCURACY_FIRST_SELECTOR_MANIFEST_V10,
        scan_workers=args.scan_workers,
        scan_prefetch=min(args.scan_workers * 2, 64),
    ).select(
        selected_sources,
        analyzer=_ProgressAnalyzer(analyzer, total=args.limit),
        verifier=_ProgressVerifier(verifier),
        audit_sink=sink,
    )
    elapsed = perf_counter() - _STARTED_AT
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
            "firstOrderIndex": 0,
            "lastOrderIndex": args.limit - 1,
            "cachePolicy": "disabled-cold-analysis",
            "publicationPolicy": "disabled-read-only-profile",
        },
        "selector": {
            "version": result.selector_version,
            "fingerprint": result.selector_fingerprint,
            "scanWorkers": args.scan_workers,
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
            }
            for group in groups
        ],
        "stageTiming": telemetry.snapshot(),
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
