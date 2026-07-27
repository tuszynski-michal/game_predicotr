from __future__ import annotations

import json
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

import pytest
from game_predictor_worker.benchmarks.dataset import (
    BENCHMARK_SIGNATURE_CELL_WIDTH,
    BenchmarkDatasetError,
    BenchmarkDatasetSpec,
    BenchmarkSnapshotRepository,
    benchmark_cells,
    generate_benchmark_dataset,
    validate_benchmark_dataset,
)
from game_predictor_worker.domain import encode_signature
from game_predictor_worker.snapshots import SnapshotArtifactError


def test_generator_is_bounded_and_has_only_controlled_duplicates() -> None:
    spec = BenchmarkDatasetSpec(layout_count=120, seed=1234, batch_size=17)
    repository = BenchmarkSnapshotRepository(spec)
    signatures: list[str] = []
    after_sequence_number = 0

    while after_sequence_number < spec.layout_count:
        batch = repository.list_snapshot_layout_batch(
            repository.selection,
            after_sequence_number=after_sequence_number,
            limit=spec.batch_size,
        )
        assert batch
        signatures.extend(layout.signature for layout in batch)
        after_sequence_number = batch[-1].sequence_number

    duplicate_groups = {
        signature: count for signature, count in Counter(signatures).items() if count > 1
    }
    expected_signatures = {
        encode_signature(
            benchmark_cells(source_sequence, spec),
            BENCHMARK_SIGNATURE_CELL_WIDTH,
        )
        for source_sequence in spec.duplicate_source_sequences
    }

    assert repository.maximum_generated_batch_size == 17
    assert set(duplicate_groups) == expected_signatures
    assert set(duplicate_groups.values()) == {2}
    assert len(signatures) == spec.layout_count


def test_two_small_artifacts_have_identical_logical_checksum(
    tmp_path: Path,
) -> None:
    spec = BenchmarkDatasetSpec(layout_count=120, seed=7654, batch_size=19)

    first = generate_benchmark_dataset(tmp_path / "first", spec)
    second = generate_benchmark_dataset(tmp_path / "second", spec)
    first_report = validate_benchmark_dataset(first.output_directory)
    second_report = validate_benchmark_dataset(second.output_directory)

    assert first_report.logical_content_sha256 == second_report.logical_content_sha256
    assert first_report.layout_count == 120
    assert first_report.duplicate_group_count == 6
    assert first_report.maximum_validation_batch_size == 19


def test_validator_rejects_manifest_corruption(tmp_path: Path) -> None:
    result = generate_benchmark_dataset(
        tmp_path / "dataset",
        BenchmarkDatasetSpec(layout_count=24, seed=55, batch_size=7),
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    manifest["seed"] = 56
    result.manifest_path.write_bytes(
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )

    with pytest.raises(
        BenchmarkDatasetError,
        match="does not match its deterministic specification",
    ):
        validate_benchmark_dataset(result.output_directory)


def test_validator_rejects_snapshot_corruption(tmp_path: Path) -> None:
    result = generate_benchmark_dataset(
        tmp_path / "dataset",
        BenchmarkDatasetSpec(layout_count=24, seed=55, batch_size=7),
    )
    with (
        closing(sqlite3.connect(result.artifact.database_path)) as connection,
        connection,
    ):
        connection.execute(
            "UPDATE layouts SET signature = ? WHERE sequence_number = 1",
            ("01" * 15,),
        )

    with pytest.raises(
        SnapshotArtifactError,
        match="checksum does not match",
    ):
        validate_benchmark_dataset(result.output_directory)
