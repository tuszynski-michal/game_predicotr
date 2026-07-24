"""Benchmark the repository query shapes against the bundled M1 snapshot."""

from __future__ import annotations

import argparse
import json
import math
import platform
import sqlite3
import sys
from collections.abc import Callable, Sequence
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter_ns
from typing import Any, cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.snapshot import validate_snapshot  # noqa: E402

ASSET_DIRECTORY = REPOSITORY_ROOT / "apps" / "mobile" / "assets" / "snapshot"
DATABASE_PATH = ASSET_DIRECTORY / "m1-snapshot.db"
MANIFEST_PATH = ASSET_DIRECTORY / "manifest.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "ai_docs" / "quality" / "m1-repository-benchmark.json"

EXACT_COUNT_QUERY = """
    SELECT COUNT(*) AS candidate_count
    FROM layouts INDEXED BY idx_layouts_game_signature
    WHERE game_id = ? AND signature = ?
"""
PREFIX_COUNT_QUERY = """
    SELECT COUNT(*) AS candidate_count
    FROM layouts INDEXED BY idx_layouts_game_signature
    WHERE game_id = ? AND signature >= ? AND signature < ?
"""
CYCLIC_QUERY = """
    SELECT sequence_number, payout, cycle_segment
    FROM (
        SELECT sequence_number, payout, 0 AS cycle_segment
        FROM layouts
        WHERE game_id = ? AND sequence_number > ?

        UNION ALL

        SELECT sequence_number, payout, 1 AS cycle_segment
        FROM layouts
        WHERE game_id = ? AND sequence_number < ?
    )
    ORDER BY cycle_segment, sequence_number
"""


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _measure(operation: Callable[[], object], iterations: int) -> dict[str, float | int]:
    for _ in range(min(20, iterations)):
        operation()

    elapsed_ms: list[float] = []
    for _ in range(iterations):
        started_at = perf_counter_ns()
        operation()
        elapsed_ms.append((perf_counter_ns() - started_at) / 1_000_000)

    return {
        "iterations": iterations,
        "maxMs": round(max(elapsed_ms), 4),
        "p50Ms": round(_percentile(elapsed_ms, 0.50), 4),
        "p95Ms": round(_percentile(elapsed_ms, 0.95), 4),
    }


def _query_plan(
    connection: sqlite3.Connection,
    query: str,
    parameters: tuple[object, ...],
) -> list[str]:
    rows = connection.execute(
        f"EXPLAIN QUERY PLAN {query}",
        parameters,
    ).fetchall()
    return [cast(str, row[3]) for row in rows]


def _load_manifest() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(MANIFEST_PATH.read_text(encoding="utf-8")),
    )


def run_benchmark() -> dict[str, object]:
    manifest = validate_snapshot(DATABASE_PATH, MANIFEST_PATH)
    manifest_data = _load_manifest()
    game = cast(dict[str, Any], manifest_data["games"][0])
    game_id = cast(int, game["id"])
    layout_count = cast(int, game["layoutCount"])
    unique_reference = cast(
        dict[str, Any],
        game["uniquePrefixFixture"],
    )
    unique_prefix = cast(str, unique_reference["signaturePrefix"])
    start_sequence = 99
    database_open_count = 0

    uri = f"{DATABASE_PATH.resolve().as_uri()}?mode=ro"
    database_open_count += 1
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        unique_signature_row = connection.execute(
            """
            SELECT signature
            FROM layouts
            WHERE game_id = ? AND sequence_number = ?
            """,
            (game_id, unique_reference["sequenceNumber"]),
        ).fetchone()
        if unique_signature_row is None:
            raise RuntimeError("Golden unique layout is missing.")
        unique_signature = cast(str, unique_signature_row[0])

        exact_parameters = (game_id, unique_signature)
        prefix_parameters = (
            game_id,
            unique_prefix,
            f"{unique_prefix}:",
        )
        cyclic_parameters = (
            game_id,
            start_sequence,
            game_id,
            start_sequence,
        )

        def exact_operation() -> object:
            return connection.execute(
                EXACT_COUNT_QUERY,
                exact_parameters,
            ).fetchone()

        def prefix_operation() -> object:
            return connection.execute(
                PREFIX_COUNT_QUERY,
                prefix_parameters,
            ).fetchone()

        def cyclic_operation() -> object:
            return connection.execute(
                CYCLIC_QUERY,
                cyclic_parameters,
            ).fetchall()

        exact_measurement = _measure(exact_operation, 1_000)
        prefix_measurement = _measure(prefix_operation, 1_000)
        cyclic_measurement = _measure(cyclic_operation, 100)
        cyclic_rows = cast(list[tuple[int, int, int]], cyclic_operation())
        if len(cyclic_rows) != layout_count - 1:
            raise RuntimeError("Cyclic query did not return N - 1 rows.")

        plans = {
            "cyclic": _query_plan(
                connection,
                CYCLIC_QUERY,
                cyclic_parameters,
            ),
            "exact": _query_plan(
                connection,
                EXACT_COUNT_QUERY,
                exact_parameters,
            ),
            "prefix": _query_plan(
                connection,
                PREFIX_COUNT_QUERY,
                prefix_parameters,
            ),
        }

    working_budgets_ms = {
        "cyclicP95": 5_000,
        "exactP95": 200,
        "prefixP95": 300,
    }
    working_budgets_passed = (
        cast(float, exact_measurement["p95Ms"]) < working_budgets_ms["exactP95"]
        and cast(float, prefix_measurement["p95Ms"]) < working_budgets_ms["prefixP95"]
        and cast(float, cyclic_measurement["p95Ms"]) < working_budgets_ms["cyclicP95"]
    )

    return {
        "capturedAt": datetime.now(UTC).isoformat(),
        "database": {
            "file": str(DATABASE_PATH.relative_to(REPOSITORY_ROOT)),
            "layoutCountInGame": layout_count,
            "repositoryOpenCount": database_open_count,
            "sizeBytes": DATABASE_PATH.stat().st_size,
            "snapshotFileSha256": manifest["snapshotFileSha256"],
        },
        "environment": {
            "machine": platform.machine(),
            "operatingSystem": platform.platform(),
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
        },
        "measurements": {
            "cyclicNMinusOne": cyclic_measurement,
            "exactUnique": exact_measurement,
            "prefixUnique": prefix_measurement,
        },
        "plans": plans,
        "scope": (
            "Development-machine evidence for the 1,000-layout M1 fixture; "
            "not the M3 500,000-layout Android device benchmark."
        ),
        "workingBudgetsMs": working_budgets_ms,
        "workingBudgetsPassed": working_budgets_passed,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path for the JSON benchmark evidence.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = run_benchmark()
    output = cast(Path, args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"Saved benchmark evidence to {output}.")


if __name__ == "__main__":
    main()
