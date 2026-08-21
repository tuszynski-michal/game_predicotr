"""Bounded, thread-safe timing telemetry for image selection.

The collector is deliberately outside the selector manifest.  It observes work
that already happens, but never participates in a domain decision.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock, get_ident
from time import perf_counter_ns

IMAGE_SELECTION_TIMING_CONTRACT = "image-selection-stage-timing-v1"
IMAGE_SELECTION_STAGES = (
    "checksum",
    "decode",
    "appearance",
    "quality",
    "geometry",
    "ocr",
    "persistence",
    "output",
)


@dataclass(slots=True)
class _StageAggregate:
    count: int = 0
    total_ns: int = 0
    max_ns: int = 0
    histogram: list[int] = field(default_factory=lambda: [0] * 64)

    def record(self, duration_ns: int) -> None:
        bounded = max(0, duration_ns)
        self.count += 1
        self.total_ns += bounded
        self.max_ns = max(self.max_ns, bounded)
        bucket = min(63, bounded.bit_length())
        self.histogram[bucket] += 1

    def percentile_upper_bound_ns(self, percentile: float) -> int:
        if self.count == 0:
            return 0
        target = max(1, int(self.count * percentile + 0.999999))
        cumulative = 0
        for bucket, count in enumerate(self.histogram):
            cumulative += count
            if cumulative >= target:
                return 0 if bucket == 0 else 1 << bucket
        return self.max_ns


class StageTimingCollector:
    """Collect bounded timing histograms and exact operation counters."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._stages = {stage: _StageAggregate() for stage in IMAGE_SELECTION_STAGES}
        self._counters: dict[str, int] = {}
        self._thread_ids: set[int] = set()

    @contextmanager
    def measure(self, stage: str) -> Iterator[None]:
        if stage not in self._stages:
            raise ValueError(f"Unknown image-selection timing stage: {stage}")
        started_at = perf_counter_ns()
        try:
            yield
        finally:
            self.record(stage, perf_counter_ns() - started_at)

    def record(self, stage: str, duration_ns: int) -> None:
        if stage not in self._stages:
            raise ValueError(f"Unknown image-selection timing stage: {stage}")
        with self._lock:
            self._stages[stage].record(duration_ns)
            self._thread_ids.add(get_ident())

    def increment(self, counter: str, amount: int = 1) -> None:
        if not counter or amount < 0:
            raise ValueError("Telemetry counters require a name and non-negative amount.")
        with self._lock:
            self._counters[counter] = self._counters.get(counter, 0) + amount
            self._thread_ids.add(get_ident())

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            stages = {
                name: {
                    "count": aggregate.count,
                    "maxMs": _milliseconds(aggregate.max_ns),
                    "meanMs": _milliseconds(
                        aggregate.total_ns // aggregate.count if aggregate.count else 0
                    ),
                    "p50Ms": _milliseconds(aggregate.percentile_upper_bound_ns(0.50)),
                    "p95Ms": _milliseconds(aggregate.percentile_upper_bound_ns(0.95)),
                    "totalSeconds": round(aggregate.total_ns / 1_000_000_000, 6),
                }
                for name, aggregate in self._stages.items()
            }
            return {
                "contract": IMAGE_SELECTION_TIMING_CONTRACT,
                "counters": dict(sorted(self._counters.items())),
                "percentileMethod": "log2-upper-bound",
                "schemaVersion": 1,
                "stages": stages,
                "timingsAreInclusive": True,
                "usedThreadCount": len(self._thread_ids),
            }


def _milliseconds(duration_ns: int) -> float:
    return round(duration_ns / 1_000_000, 6)


__all__ = [
    "IMAGE_SELECTION_STAGES",
    "IMAGE_SELECTION_TIMING_CONTRACT",
    "StageTimingCollector",
]
