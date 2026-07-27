"""Validate the deterministic M3.5 benchmark dataset."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.benchmarks import (  # noqa: E402
    BenchmarkProgress,
    validate_benchmark_dataset,
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
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = validate_benchmark_dataset(
        args.output_directory,
        progress=_progress,
    )
    print(
        json.dumps(
            {
                "duplicateGroupCount": report.duplicate_group_count,
                "layoutCount": report.layout_count,
                "logicalContentSha256": report.logical_content_sha256,
                "maximumValidationBatchSize": (report.maximum_validation_batch_size),
                "snapshotFileSha256": report.snapshot_file_sha256,
                "snapshotSizeBytes": report.snapshot_size_bytes,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
