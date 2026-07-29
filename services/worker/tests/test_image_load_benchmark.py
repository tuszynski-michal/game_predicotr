from __future__ import annotations

from pathlib import Path

import pytest
from game_predictor_worker.images.load_benchmark import (
    BenchmarkDeadline,
    ImageLoadBenchmarkError,
    ImageLoadProfile,
    build_load_report,
    load_profile,
    run_storage_load,
    source_checksum,
    source_relative_path,
    validate_load_report,
)


def _profile() -> ImageLoadProfile:
    return ImageLoadProfile(
        name="test",
        file_count=37,
        layouts_per_image=9,
        shard_count=4,
        query_iterations=2,
    )


def _database_measurement(file_count: int) -> dict[str, object]:
    timing = {
        "firstMs": 1.0,
        "iterations": 2,
        "maxMs": 2.0,
        "minMs": 1.0,
        "p50Ms": 1.0,
        "p95Ms": 2.0,
    }
    return {
        "databaseSizeBytes": 4096,
        "migrationElapsedSeconds": 0.2,
        "postgresVersion": "18.4",
        "queries": {
            "batchStats": timing,
            "countJobFiles": timing,
            "nextProcessingFile": timing,
        },
        "registration": {
            "clientCpuSeconds": 0.1,
            "clientCpuToWallRatio": 0.5,
            "elapsedSeconds": 0.2,
            "memory": {
                "baselineRssBytes": 1,
                "peakRssBytes": 2,
                "peakRssDeltaBytes": 1,
                "peakTracedPythonBytes": 1,
            },
            "throughputPerSecond": 185.0,
        },
        "relations": {
            "image_file_executions": {
                "indexSizeBytes": 1024,
                "rowCount": file_count,
                "totalSizeBytes": 2048,
            },
            "image_import_job_files": {
                "indexSizeBytes": 1024,
                "rowCount": file_count,
                "totalSizeBytes": 2048,
            },
        },
    }


def test_full_profile_represents_at_least_half_a_million_layouts() -> None:
    profile = load_profile("full")

    assert profile.file_count == 55_556
    assert profile.represented_layout_capacity == 500_004
    assert source_checksum(740_074, 12) == source_checksum(740_074, 12)
    assert source_checksum(740_074, 12) != source_checksum(740_074, 13)
    assert source_relative_path(profile, 740_074, 12).startswith("load/full/012/")


def test_storage_load_is_sharded_bounded_and_exact(tmp_path: Path) -> None:
    profile = _profile()

    storage = run_storage_load(
        tmp_path,
        profile,
        seed=17,
        deadline=BenchmarkDeadline(30),
    )

    assert storage["workingFileCount"] == profile.file_count
    assert storage["totalFileCount"] == profile.file_count
    assert storage["workingSizeBytes"] == profile.file_count * 32
    assert storage["automaticDeletion"] is False
    shard_directories = sorted(
        path.name for path in (tmp_path / "data" / "working" / "load" / "test").iterdir()
    )
    assert shard_directories == ["000", "001", "002", "003"]


def test_report_validation_preserves_cardinality_and_rejects_secrets(
    tmp_path: Path,
) -> None:
    profile = _profile()
    storage = run_storage_load(
        tmp_path,
        profile,
        seed=19,
        deadline=BenchmarkDeadline(30),
    )
    report = build_load_report(
        profile,
        _database_measurement(profile.file_count),
        storage,
    )

    validate_load_report(report, expected_profile=profile)

    cast_database = report["database"]
    assert isinstance(cast_database, dict)
    cast_database["databaseUrl"] = "postgresql+psycopg://user:password@127.0.0.1/example"
    with pytest.raises(ImageLoadBenchmarkError, match="database URL"):
        validate_load_report(report, expected_profile=profile)


def test_deadline_and_invalid_profiles_fail_closed() -> None:
    with pytest.raises(ImageLoadBenchmarkError, match="Unknown load profile"):
        load_profile("large")
    with pytest.raises(ImageLoadBenchmarkError, match="positive"):
        BenchmarkDeadline(0)
