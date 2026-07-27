"""Deterministic datasets and verification helpers for performance benchmarks."""

from game_predictor_worker.benchmarks.acceptance import (
    AcceptanceCheck,
    M35AcceptanceResult,
    evaluate_m35_acceptance,
)
from game_predictor_worker.benchmarks.dataset import (
    DEFAULT_BENCHMARK_BATCH_SIZE,
    DEFAULT_BENCHMARK_LAYOUT_COUNT,
    DEFAULT_BENCHMARK_SEED,
    BenchmarkDatasetError,
    BenchmarkDatasetResult,
    BenchmarkDatasetSpec,
    BenchmarkDatasetValidationReport,
    BenchmarkProgress,
    generate_benchmark_dataset,
    validate_benchmark_dataset,
)
from game_predictor_worker.benchmarks.performance import (
    MemorySummary,
    PeakMemorySampler,
    TimingSummary,
    measure,
    percentile,
    summarize_timings,
)

__all__ = [
    "AcceptanceCheck",
    "DEFAULT_BENCHMARK_BATCH_SIZE",
    "DEFAULT_BENCHMARK_LAYOUT_COUNT",
    "DEFAULT_BENCHMARK_SEED",
    "BenchmarkDatasetError",
    "BenchmarkDatasetResult",
    "BenchmarkDatasetSpec",
    "BenchmarkDatasetValidationReport",
    "BenchmarkProgress",
    "MemorySummary",
    "M35AcceptanceResult",
    "PeakMemorySampler",
    "TimingSummary",
    "generate_benchmark_dataset",
    "evaluate_m35_acceptance",
    "measure",
    "percentile",
    "summarize_timings",
    "validate_benchmark_dataset",
]
