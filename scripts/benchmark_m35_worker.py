"""Measure bounded synthetic payout plus production snapshot worker throughput."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.benchmarks import (  # noqa: E402
    DEFAULT_BENCHMARK_BATCH_SIZE,
    DEFAULT_BENCHMARK_LAYOUT_COUNT,
    DEFAULT_BENCHMARK_SEED,
    BenchmarkDatasetSpec,
    PeakMemorySampler,
)
from game_predictor_worker.benchmarks.dataset import (  # noqa: E402
    BENCHMARK_CREATED_AT,
    BENCHMARK_RELEASE_VERSION,
    BenchmarkSnapshotRepository,
)
from game_predictor_worker.snapshots import (  # noqa: E402
    ProductionSnapshotArtifactPublisher,
    ProductionSnapshotGenerator,
    ProductionSnapshotSpec,
    validate_snapshot_artifact,
)

DEFAULT_OUTPUT = REPOSITORY_ROOT / "ai_docs" / "quality" / "m35-worker-benchmark.json"


def _throughput(layout_count: int, elapsed_seconds: float) -> float:
    return round(layout_count / elapsed_seconds, 2)


def run_benchmark(
    *,
    layout_count: int = DEFAULT_BENCHMARK_LAYOUT_COUNT,
    seed: int = DEFAULT_BENCHMARK_SEED,
    batch_size: int = DEFAULT_BENCHMARK_BATCH_SIZE,
) -> dict[str, object]:
    spec = BenchmarkDatasetSpec(
        layout_count=layout_count,
        seed=seed,
        batch_size=batch_size,
    )
    repository = BenchmarkSnapshotRepository(spec)
    artifacts_root = REPOSITORY_ROOT / "artifacts"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(
        tempfile.mkdtemp(
            prefix="m35-worker-benchmark-",
            dir=artifacts_root,
        )
    )
    try:
        generator = ProductionSnapshotGenerator(
            repository,
            batch_size=batch_size,
        )
        publisher = ProductionSnapshotArtifactPublisher(
            generator,
            temporary_root,
        )
        with PeakMemorySampler() as generation_memory_sampler:
            generation_started_at = perf_counter()
            artifact = publisher.publish(
                ProductionSnapshotSpec(
                    release_version=BENCHMARK_RELEASE_VERSION,
                    created_at=BENCHMARK_CREATED_AT,
                    games=(repository.selection,),
                )
            )
            generation_seconds = perf_counter() - generation_started_at
        generation_memory = generation_memory_sampler.summary()

        with PeakMemorySampler() as validation_memory_sampler:
            validation_started_at = perf_counter()
            validate_snapshot_artifact(artifact.directory)
            validation_seconds = perf_counter() - validation_started_at
        validation_memory = validation_memory_sampler.summary()

        return {
            "capturedAt": datetime.now(UTC).isoformat(),
            "dataset": {
                "algorithmVersion": artifact.manifest.algorithm_version,
                "batchSize": batch_size,
                "layoutCount": layout_count,
                "logicalContentSha256": artifact.manifest.logical_content_sha256,
                "seed": seed,
                "snapshotFileSha256": artifact.manifest.snapshot_file_sha256,
                "snapshotSizeBytes": artifact.database_path.stat().st_size,
            },
            "environment": {
                "machine": platform.machine(),
                "operatingSystem": platform.platform(),
                "python": platform.python_version(),
            },
            "generation": {
                "elapsedSeconds": round(generation_seconds, 4),
                "maximumGeneratedBatchSize": repository.maximum_generated_batch_size,
                "memory": generation_memory.to_dict(),
                "throughputLayoutsPerSecond": _throughput(
                    layout_count,
                    generation_seconds,
                ),
            },
            "scope": (
                "Synthetic bounded source evaluates payout-v2 on demand and writes "
                "the production SQLite snapshot. PostgreSQL transport and JSONL audit "
                "I/O are not included in this baseline."
            ),
            "validation": {
                "elapsedSeconds": round(validation_seconds, 4),
                "memory": validation_memory.to_dict(),
                "throughputLayoutsPerSecond": _throughput(
                    layout_count,
                    validation_seconds,
                ),
            },
        }
    finally:
        resolved_temporary = temporary_root.resolve()
        resolved_artifacts = artifacts_root.resolve()
        if resolved_artifacts not in resolved_temporary.parents:
            raise RuntimeError("Refusing to remove a path outside artifacts.")
        shutil.rmtree(resolved_temporary)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--layout-count", type=int, default=DEFAULT_BENCHMARK_LAYOUT_COUNT)
    parser.add_argument("--seed", type=int, default=DEFAULT_BENCHMARK_SEED)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BENCHMARK_BATCH_SIZE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = run_benchmark(
        layout_count=args.layout_count,
        seed=args.seed,
        batch_size=args.batch_size,
    )
    output = cast(Path, args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"Saved worker benchmark to {output}.")


if __name__ == "__main__":
    main()
