from __future__ import annotations

from game_predictor_worker.benchmarks.performance import (
    PeakMemorySampler,
    measure,
    percentile,
    summarize_timings,
)


def test_percentile_uses_nearest_rank() -> None:
    values = [5.0, 1.0, 4.0, 2.0, 3.0]

    assert percentile(values, 0.0) == 1.0
    assert percentile(values, 0.5) == 3.0
    assert percentile(values, 0.95) == 5.0
    assert percentile(values, 1.0) == 5.0


def test_measure_excludes_warmups_and_preserves_last_result() -> None:
    calls = 0

    def operation() -> int:
        nonlocal calls
        calls += 1
        return calls

    summary, result = measure(operation, iterations=3, warmups=2)

    assert calls == 5
    assert result == 5
    assert summary.iterations == 3
    assert summary.minimum_ms >= 0
    assert summary.p95_ms >= summary.p50_ms


def test_timing_summary_rounds_and_serializes_stably() -> None:
    summary = summarize_timings([1.23456, 2.34567, 9.87654])

    assert summary.to_dict() == {
        "firstMs": 1.2346,
        "iterations": 3,
        "maxMs": 9.8765,
        "minMs": 1.2346,
        "p50Ms": 2.3457,
        "p95Ms": 9.8765,
    }


def test_memory_sampler_reports_non_negative_python_peak() -> None:
    with PeakMemorySampler() as sampler:
        allocation = bytearray(64 * 1024)
        assert len(allocation) == 64 * 1024

    summary = sampler.summary()

    assert summary.peak_traced_python_bytes >= 64 * 1024
    if summary.peak_rss_delta_bytes is not None:
        assert summary.peak_rss_delta_bytes >= 0
