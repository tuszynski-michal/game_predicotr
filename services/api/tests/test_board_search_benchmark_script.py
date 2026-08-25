from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import pytest


def _script_module() -> ModuleType:
    path = Path(__file__).parents[3] / "scripts" / "benchmark_board_search.py"
    spec = spec_from_file_location("benchmark_board_search", path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_board_search_benchmark_uses_nearest_rank_latency_percentiles() -> None:
    script = _script_module()
    summary = script.summarize_latencies_ms((10.0, 20.0, 30.0, 40.0, 50.0))

    assert summary == {
        "minMs": 10.0,
        "p50Ms": 30.0,
        "p95Ms": 50.0,
        "maxMs": 50.0,
    }


def test_board_search_benchmark_derives_three_active_known_cells() -> None:
    script = _script_module()

    query = script.derive_benchmark_query(
        (("?", "retired", None, "bell", "seven", "lemon"),),
        active_symbol_codes={"bell", "seven", "lemon"},
    )

    assert [(cell.cell_index, cell.symbol_code) for cell in query] == [
        (3, "bell"),
        (4, "seven"),
        (5, "lemon"),
    ]


def test_board_search_benchmark_derives_a_requested_partial_pattern_size() -> None:
    script = _script_module()

    query = script.derive_benchmark_query(
        (("bell", "seven", "lemon", "orange"),),
        active_symbol_codes={"bell", "seven", "lemon", "orange"},
        query_size=4,
    )

    assert [(cell.cell_index, cell.symbol_code) for cell in query] == [
        (0, "bell"),
        (1, "seven"),
        (2, "lemon"),
        (3, "orange"),
    ]


def test_board_search_benchmark_rejects_projection_without_three_active_cells() -> None:
    script = _script_module()

    with pytest.raises(RuntimeError, match="no current board"):
        script.derive_benchmark_query(
            (("?", "retired", None),),
            active_symbol_codes={"bell"},
        )
