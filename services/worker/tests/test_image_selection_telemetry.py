from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from game_predictor_worker.images.selection.telemetry import (
    IMAGE_SELECTION_STAGES,
    StageTimingCollector,
)


def test_stage_timing_collector_keeps_bounded_histograms_across_threads() -> None:
    collector = StageTimingCollector()

    def record(index: int) -> None:
        collector.record("appearance", (index + 1) * 1_000_000)
        collector.increment("decoderCalls")

    with ThreadPoolExecutor(max_workers=4) as executor:
        tuple(executor.map(record, range(100)))

    snapshot = collector.snapshot()
    stages = snapshot["stages"]
    assert isinstance(stages, dict)
    assert tuple(stages) == IMAGE_SELECTION_STAGES
    assert stages["appearance"]["count"] == 100
    assert stages["appearance"]["maxMs"] == 100.0
    assert stages["appearance"]["p95Ms"] >= 64.0
    assert snapshot["counters"] == {"decoderCalls": 100}
    assert 1 <= snapshot["usedThreadCount"] <= 4


def test_stage_timing_snapshot_keeps_unobserved_stages_explicit() -> None:
    snapshot = StageTimingCollector().snapshot()
    stages = snapshot["stages"]

    assert isinstance(stages, dict)
    assert all(stage["count"] == 0 for stage in stages.values())
    assert snapshot["percentileMethod"] == "log2-upper-bound"
