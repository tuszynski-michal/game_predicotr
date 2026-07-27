"""Small deterministic helpers shared by local performance benchmarks."""

from __future__ import annotations

import ctypes
import math
import os
import threading
import tracemalloc
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from time import perf_counter_ns


@dataclass(frozen=True, slots=True)
class TimingSummary:
    iterations: int
    first_ms: float
    minimum_ms: float
    p50_ms: float
    p95_ms: float
    maximum_ms: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "firstMs": self.first_ms,
            "iterations": self.iterations,
            "maxMs": self.maximum_ms,
            "minMs": self.minimum_ms,
            "p50Ms": self.p50_ms,
            "p95Ms": self.p95_ms,
        }


@dataclass(frozen=True, slots=True)
class MemorySummary:
    baseline_rss_bytes: int | None
    peak_rss_bytes: int | None
    peak_rss_delta_bytes: int | None
    peak_traced_python_bytes: int

    def to_dict(self) -> dict[str, int | None]:
        return {
            "baselineRssBytes": self.baseline_rss_bytes,
            "peakRssBytes": self.peak_rss_bytes,
            "peakRssDeltaBytes": self.peak_rss_delta_bytes,
            "peakTracedPythonBytes": self.peak_traced_python_bytes,
        }


def percentile(values: Sequence[float], percentile_value: float) -> float:
    if not values:
        raise ValueError("At least one measurement is required.")
    if percentile_value < 0 or percentile_value > 1:
        raise ValueError("Percentile must be between zero and one.")
    ordered = sorted(values)
    index = max(0, math.ceil(percentile_value * len(ordered)) - 1)
    return ordered[index]


def summarize_timings(values: Sequence[float]) -> TimingSummary:
    if not values:
        raise ValueError("At least one measurement is required.")
    return TimingSummary(
        iterations=len(values),
        first_ms=round(values[0], 4),
        minimum_ms=round(min(values), 4),
        p50_ms=round(percentile(values, 0.50), 4),
        p95_ms=round(percentile(values, 0.95), 4),
        maximum_ms=round(max(values), 4),
    )


def measure[T](
    operation: Callable[[], T],
    *,
    iterations: int,
    warmups: int = 0,
) -> tuple[TimingSummary, T]:
    if iterations < 1 or warmups < 0:
        raise ValueError("Iterations must be positive and warmups non-negative.")
    for _ in range(warmups):
        operation()

    values: list[float] = []
    last_result: T | None = None
    for _ in range(iterations):
        started_at = perf_counter_ns()
        last_result = operation()
        values.append((perf_counter_ns() - started_at) / 1_000_000)
    if last_result is None:
        raise RuntimeError("Benchmark operation did not produce a result.")
    return summarize_timings(values), last_result


def _windows_working_set_bytes() -> int | None:
    if os.name != "nt":
        return None

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("page_fault_count", ctypes.c_ulong),
            ("peak_working_set_size", ctypes.c_size_t),
            ("working_set_size", ctypes.c_size_t),
            ("quota_peak_paged_pool_usage", ctypes.c_size_t),
            ("quota_paged_pool_usage", ctypes.c_size_t),
            ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
            ("quota_non_paged_pool_usage", ctypes.c_size_t),
            ("pagefile_usage", ctypes.c_size_t),
            ("peak_pagefile_usage", ctypes.c_size_t),
        ]

    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return None
    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    get_current_process = windll.kernel32.GetCurrentProcess
    get_current_process.restype = ctypes.c_void_p
    get_process_memory_info = windll.psapi.GetProcessMemoryInfo
    get_process_memory_info.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(ProcessMemoryCounters),
        ctypes.c_ulong,
    )
    get_process_memory_info.restype = ctypes.c_int
    process = get_current_process()
    success = get_process_memory_info(
        process,
        ctypes.byref(counters),
        counters.cb,
    )
    return int(counters.working_set_size) if success else None


class PeakMemorySampler:
    """Sample process RSS while tracemalloc records Python allocations."""

    def __init__(self, *, interval_seconds: float = 0.05) -> None:
        if interval_seconds <= 0:
            raise ValueError("Memory sampling interval must be positive.")
        self._interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._baseline_rss_bytes: int | None = None
        self._peak_rss_bytes: int | None = None

    def __enter__(self) -> PeakMemorySampler:
        self._baseline_rss_bytes = _windows_working_set_bytes()
        self._peak_rss_bytes = self._baseline_rss_bytes
        tracemalloc.start()
        self._thread = threading.Thread(
            target=self._sample,
            name="benchmark-memory-sampler",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self._interval_seconds * 4))

    def _sample(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            current = _windows_working_set_bytes()
            if current is not None and (
                self._peak_rss_bytes is None or current > self._peak_rss_bytes
            ):
                self._peak_rss_bytes = current

    def summary(self) -> MemorySummary:
        if tracemalloc.is_tracing():
            _, peak_traced = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        else:
            peak_traced = 0
        peak_delta = (
            None
            if self._baseline_rss_bytes is None or self._peak_rss_bytes is None
            else max(0, self._peak_rss_bytes - self._baseline_rss_bytes)
        )
        return MemorySummary(
            baseline_rss_bytes=self._baseline_rss_bytes,
            peak_rss_bytes=self._peak_rss_bytes,
            peak_rss_delta_bytes=peak_delta,
            peak_traced_python_bytes=peak_traced,
        )
