from __future__ import annotations

from pathlib import Path

from game_predictor_worker.images.real_workbench_fixture import (
    REAL_WORKBENCH_GAME_CODE,
    load_real_workbench_source,
)


def test_real_workbench_source_joins_checksum_bound_corpus() -> None:
    root = Path(__file__).resolve().parents[3]

    source = load_real_workbench_source(root)

    assert REAL_WORKBENCH_GAME_CODE == "blazing-hot-7-deluxe"
    assert len(source.images) == 43
    assert len(source.boards) == 387
    assert sum(len(rows) for rows in source.samples_by_sequence.values()) == 5805
    assert len(source.samples_by_sequence[1]) == 15
    assert [row["cellIndex"] for row in source.samples_by_sequence[1]] == list(range(15))
    assert len(source.class_codes) == 8
    assert len(source.pipeline_fingerprint) == 64
    assert sum(len(values) for values in source.labels_by_sequence.values()) == 1316
    assert sum(len(values) == 15 for values in source.labels_by_sequence.values()) == 84
