"""Generate the deterministic 500k-layout M3.5 benchmark dataset."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.benchmarks import (  # noqa: E402
    DEFAULT_BENCHMARK_BATCH_SIZE,
    DEFAULT_BENCHMARK_LAYOUT_COUNT,
    DEFAULT_BENCHMARK_SEED,
    BenchmarkDatasetSpec,
    BenchmarkProgress,
    generate_benchmark_dataset,
)

DEFAULT_OUTPUT_DIRECTORY = REPOSITORY_ROOT / "artifacts" / "m35-benchmark"


def _progress(progress: BenchmarkProgress) -> None:
    if (
        progress.processed_layout_count == progress.total_layout_count
        or progress.processed_layout_count % 25_000 == 0
    ):
        print(
            f"{progress.phase}: {progress.processed_layout_count:,}/{progress.total_layout_count:,}"
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY,
    )
    parser.add_argument(
        "--layout-count",
        type=int,
        default=DEFAULT_BENCHMARK_LAYOUT_COUNT,
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_BENCHMARK_SEED)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BENCHMARK_BATCH_SIZE,
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = generate_benchmark_dataset(
        args.output_directory,
        BenchmarkDatasetSpec(
            layout_count=args.layout_count,
            seed=args.seed,
            batch_size=args.batch_size,
        ),
        progress=_progress,
    )
    print(f"Manifest: {result.manifest_path}")
    print(f"Snapshot: {result.artifact.database_path}")
    print(f"Logical SHA-256: {result.artifact.manifest.logical_content_sha256}")
    print(f"Snapshot size: {result.artifact.database_path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
