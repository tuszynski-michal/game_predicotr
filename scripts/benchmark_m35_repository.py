"""Benchmark production SQLite query shapes on the 500k M3.5 snapshot."""

from __future__ import annotations

import argparse
import json
import platform
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.benchmarks import (  # noqa: E402
    PeakMemorySampler,
    measure,
)
from game_predictor_worker.snapshots import validate_snapshot_artifact  # noqa: E402

DEFAULT_DATASET_DIRECTORY = REPOSITORY_ROOT / "artifacts" / "m35-benchmark"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "ai_docs" / "quality" / "m35-repository-benchmark.json"

EXACT_QUERY = """
    SELECT COUNT(*) AS candidate_count
    FROM layouts INDEXED BY idx_layouts_game_signature
    WHERE game_id = ? AND signature = ?
"""
PREFIX_QUERY = """
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


def _load_benchmark_manifest(directory: Path) -> dict[str, Any]:
    value = json.loads((directory / "benchmark-manifest.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("Benchmark manifest root must be an object.")
    return cast(dict[str, Any], value)


def _artifact_directory(directory: Path, manifest: dict[str, Any]) -> Path:
    artifact = cast(dict[str, Any], manifest["artifact"])
    return directory / cast(str, artifact["relativeDirectory"])


def _query_plan(
    connection: sqlite3.Connection,
    query: str,
    parameters: tuple[object, ...],
) -> list[str]:
    return [
        cast(str, row[3])
        for row in connection.execute(
            f"EXPLAIN QUERY PLAN {query}",
            parameters,
        ).fetchall()
    ]


def run_benchmark(
    dataset_directory: Path,
    *,
    exact_iterations: int = 1_000,
    prefix_iterations: int = 500,
    cyclic_iterations: int = 10,
) -> dict[str, object]:
    dataset_directory = dataset_directory.resolve()
    benchmark_manifest = _load_benchmark_manifest(dataset_directory)
    artifact = validate_snapshot_artifact(
        _artifact_directory(dataset_directory, benchmark_manifest)
    )
    database_path = artifact.database_path
    uri = f"{database_path.resolve().as_uri()}?mode=ro&immutable=1"

    def open_database() -> int:
        with closing(sqlite3.connect(uri, uri=True)) as opened:
            row = opened.execute("SELECT COUNT(*) FROM metadata").fetchone()
            return cast(int, row[0] if row is not None else -1)

    open_measurement, metadata_count = measure(
        open_database,
        iterations=50,
        warmups=2,
    )
    if metadata_count < 1:
        raise RuntimeError("SQLite metadata is empty.")

    duplicate_group = cast(list[dict[str, Any]], benchmark_manifest["duplicateGroups"])[0]
    duplicate_signature = cast(str, duplicate_group["signature"])
    duplicate_sequence_numbers = cast(list[int], duplicate_group["sequenceNumbers"])
    start_sequence_number = duplicate_sequence_numbers[0]

    with closing(sqlite3.connect(uri, uri=True)) as connection:
        unique_row = connection.execute(
            """
            SELECT sequence_number, signature
            FROM layouts
            WHERE game_id = 1
              AND signature NOT IN (
                SELECT signature
                FROM layouts
                WHERE game_id = 1
                GROUP BY signature
                HAVING COUNT(*) > 1
              )
            ORDER BY sequence_number
            LIMIT 1
            """
        ).fetchone()
        if unique_row is None:
            raise RuntimeError("A unique benchmark signature was not found.")
        unique_sequence_number = cast(int, unique_row[0])
        unique_signature = cast(str, unique_row[1])
        absent_signature = "01" * 15
        if connection.execute(
            EXACT_QUERY,
            (1, absent_signature),
        ).fetchone() != (0,):
            raise RuntimeError("The selected not-found signature exists.")

        def exact(signature: str) -> int:
            row = connection.execute(EXACT_QUERY, (1, signature)).fetchone()
            return cast(int, row[0] if row is not None else -1)

        exact_unique, unique_count = measure(
            lambda: exact(unique_signature),
            iterations=exact_iterations,
            warmups=20,
        )
        exact_duplicate, duplicate_count = measure(
            lambda: exact(duplicate_signature),
            iterations=exact_iterations,
            warmups=20,
        )
        exact_not_found, not_found_count = measure(
            lambda: exact(absent_signature),
            iterations=exact_iterations,
            warmups=20,
        )
        if (unique_count, duplicate_count, not_found_count) != (1, 2, 0):
            raise RuntimeError("Exact benchmark references are invalid.")

        prefix_measurements: dict[str, object] = {}
        prefix_plans: dict[str, list[str]] = {}
        for cell_count in (1, 3, 5, 6):
            prefix = unique_signature[: cell_count * 2]
            parameters = (1, prefix, f"{prefix}:")

            def prefix_count(
                query_parameters: tuple[object, ...] = parameters,
            ) -> int:
                row = connection.execute(
                    PREFIX_QUERY,
                    query_parameters,
                ).fetchone()
                return cast(int, row[0] if row is not None else -1)

            timing, candidate_count = measure(
                prefix_count,
                iterations=prefix_iterations,
                warmups=20,
            )
            prefix_measurements[str(cell_count)] = {
                "candidateCount": candidate_count,
                "timing": timing.to_dict(),
            }
            prefix_plans[str(cell_count)] = _query_plan(
                connection,
                PREFIX_QUERY,
                parameters,
            )

        cyclic_parameters = (
            1,
            start_sequence_number,
            1,
            start_sequence_number,
        )

        def cyclic_read() -> tuple[int, int]:
            rows = connection.execute(
                CYCLIC_QUERY,
                cyclic_parameters,
            ).fetchall()
            return len(rows), sum(cast(int, row[1]) for row in rows)

        with PeakMemorySampler() as memory_sampler:
            cyclic_timing, cyclic_result = measure(
                cyclic_read,
                iterations=cyclic_iterations,
                warmups=1,
            )
        cyclic_memory = memory_sampler.summary()
        expected_cycle_count = cast(int, benchmark_manifest["layoutCount"]) - 1
        if cyclic_result[0] != expected_cycle_count:
            raise RuntimeError("Cyclic benchmark did not read N - 1 rows.")

        plans = {
            "cyclic": _query_plan(
                connection,
                CYCLIC_QUERY,
                cyclic_parameters,
            ),
            "exact": _query_plan(
                connection,
                EXACT_QUERY,
                (1, unique_signature),
            ),
            "prefixByCellCount": prefix_plans,
        }

    budgets = {
        "cyclicP95Ms": 5_000,
        "exactP95Ms": 200,
        "prefixP95Ms": 300,
    }
    typical_prefix = cast(
        dict[str, Any],
        cast(dict[str, object], prefix_measurements["5"])["timing"],
    )
    budget_results = {
        "cyclic": cyclic_timing.p95_ms < budgets["cyclicP95Ms"],
        "exact": exact_unique.p95_ms < budgets["exactP95Ms"],
        "prefix": cast(float, typical_prefix["p95Ms"]) < budgets["prefixP95Ms"],
    }

    return {
        "budgets": budgets,
        "budgetResults": budget_results,
        "capturedAt": datetime.now(UTC).isoformat(),
        "dataset": {
            "databasePath": database_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "layoutCount": benchmark_manifest["layoutCount"],
            "logicalContentSha256": artifact.manifest.logical_content_sha256,
            "snapshotFileSha256": artifact.manifest.snapshot_file_sha256,
            "snapshotSizeBytes": database_path.stat().st_size,
        },
        "environment": {
            "machine": platform.machine(),
            "operatingSystem": platform.platform(),
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
        },
        "measurements": {
            "cyclicNMinusOne": {
                "memory": cyclic_memory.to_dict(),
                "payoutSumLastIteration": cyclic_result[1],
                "rowCount": cyclic_result[0],
                "timing": cyclic_timing.to_dict(),
            },
            "exactDuplicate": exact_duplicate.to_dict(),
            "exactNotFound": exact_not_found.to_dict(),
            "exactUnique": exact_unique.to_dict(),
            "openAndReadMetadata": open_measurement.to_dict(),
            "prefixByCellCount": prefix_measurements,
        },
        "plans": plans,
        "references": {
            "cycleStartSequenceNumber": start_sequence_number,
            "duplicateSequenceNumbers": duplicate_sequence_numbers,
            "uniqueSequenceNumber": unique_sequence_number,
        },
        "scope": (
            "Warm-cache Windows/Python SQLite baseline. Android Expo SQLite, "
            "Hermes Target and UI measurements are reported separately."
        ),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset-directory",
        type=Path,
        default=DEFAULT_DATASET_DIRECTORY,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--exact-iterations", type=int, default=1_000)
    parser.add_argument("--prefix-iterations", type=int, default=500)
    parser.add_argument("--cyclic-iterations", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = run_benchmark(
        args.dataset_directory,
        exact_iterations=args.exact_iterations,
        prefix_iterations=args.prefix_iterations,
        cyclic_iterations=args.cyclic_iterations,
    )
    output = cast(Path, args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"Saved repository benchmark to {output}.")


if __name__ == "__main__":
    main()
