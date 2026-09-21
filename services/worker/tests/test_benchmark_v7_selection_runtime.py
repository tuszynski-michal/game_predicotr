from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_benchmark_module() -> object:
    path = Path(__file__).resolve().parents[3] / "scripts" / "benchmark_v7_selection_runtime.py"
    spec = importlib.util.spec_from_file_location("v7_selection_runtime_benchmark", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


benchmark = _load_benchmark_module()


def test_inventory_drift_blocks_source_selection_before_jpeg_enumeration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DriftedManifest:
        cases: tuple[object, ...] = ()

        def fingerprint(self) -> str:
            return "actual-manifest"

        def freeze_inventory(self) -> tuple[object, ...]:
            return ()

    monkeypatch.setattr(benchmark, "load_v7_corpus_manifest", lambda _path: DriftedManifest())
    monkeypatch.setattr(benchmark, "_frozen_inventory", lambda _path: ("frozen-manifest", ()))
    monkeypatch.setattr(
        benchmark,
        "_direct_jpegs",
        lambda _directory: (_ for _ in ()).throw(AssertionError("JPEG enumeration must not run")),
    )

    with pytest.raises(ValueError, match="drifted"):
        benchmark._select_sources(
            manifest_path=Path("manifest.json"),
            inventory_path=Path("inventory.json"),
            samples_per_case=1,
            splits=set(),
        )


def test_observation_digest_ignores_timing_and_memory_fields() -> None:
    logical = {
        "case": "case-a",
        "recognizedLabels": [{"confidence": 0.9, "positionIndex": 0, "rawText": "1"}],
        "relativePath": "case-a/0001.jpg",
        "sourceSha256": "source-one",
        "sourceIndex": 0,
    }
    faster = {**logical, "decodeMilliseconds": 1.0}
    slower = {**logical, "decodeMilliseconds": 999.0}

    assert benchmark._observation_digest([faster]) == benchmark._observation_digest([slower])


def test_observation_digest_includes_source_and_non_numeric_ocr() -> None:
    base = {
        "case": "case-a",
        "recognizedLabels": [{"confidence": 0.9, "positionIndex": 0, "rawText": "abc"}],
        "relativePath": "case-a/0001.jpg",
        "sourceSha256": "source-one",
        "sourceIndex": 0,
    }
    changed_ocr = {**base, "recognizedLabels": [{**base["recognizedLabels"][0], "rawText": "xyz"}]}
    changed_source = {**base, "sourceSha256": "source-two"}

    assert benchmark._observation_digest([base]) != benchmark._observation_digest([changed_ocr])
    assert benchmark._observation_digest([base]) != benchmark._observation_digest([changed_source])


def test_recommendation_selects_fastest_deterministic_profile() -> None:
    profiles = (
        {
            "observationDigest": "stable",
            "policy": {"maxInFlight": 2, "prepareWorkers": 1},
            "stages": {"totalMilliseconds": 12.0},
        },
        {
            "observationDigest": "stable",
            "policy": {"maxInFlight": 8, "prepareWorkers": 4},
            "stages": {"totalMilliseconds": 9.0},
        },
    )

    assert benchmark._recommended_profile(profiles) == {
        "deterministic": True,
        "maxInFlight": 8,
        "selectedPrepareWorkers": 4,
    }


def test_recommendation_fails_closed_for_non_deterministic_profiles() -> None:
    profiles = (
        {
            "observationDigest": "first",
            "policy": {"maxInFlight": 2, "prepareWorkers": 1},
            "stages": {"totalMilliseconds": 1.0},
        },
        {
            "observationDigest": "different",
            "policy": {"maxInFlight": 4, "prepareWorkers": 2},
            "stages": {"totalMilliseconds": 0.5},
        },
    )

    assert benchmark._recommended_profile(profiles) == {
        "deterministic": False,
        "reason": "V7_ORDERED_RUNTIME_DIGEST_MISMATCH",
        "selectedPrepareWorkers": 1,
    }


def test_scale_benchmark_does_not_duplicate_an_undersized_corpus() -> None:
    sources = tuple(
        benchmark.BenchmarkSource(
            case_id="case-a",
            path=Path(f"{index}.jpg"),
            relative_path=f"case-a/{index}.jpg",
            source_index=index,
            source_sha256=f"{index:064x}",
        )
        for index in range(7)
    )

    report = benchmark._scale_report(
        available_sources=sources,
        manifest_validation_milliseconds=1.25,
        model_root=Path("models"),
        policies=(),
        target_source_count=100,
    )

    assert report == {
        "availablePathCount": 7,
        "availableSourceCount": 7,
        "profiles": [],
        "reason": "V7_BENCHMARK_INSUFFICIENT_INDEPENDENT_SOURCES",
        "stages": {
            "decodeMilliseconds": None,
            "finalizationMilliseconds": None,
            "locatorMilliseconds": None,
            "manifestValidationMilliseconds": 1.25,
            "ocrMilliseconds": None,
            "writeMilliseconds": 0.0,
            "writeStatus": "not_run_read_only_v7_inactive",
        },
        "status": "not_evaluable",
        "targetSourceCount": 100,
    }


def test_scale_benchmark_rejects_renamed_copies_as_independent_sources() -> None:
    sources = tuple(
        benchmark.BenchmarkSource(
            case_id="case-a",
            path=Path(f"{index}.jpg"),
            relative_path=f"case-a/{index}.jpg",
            source_index=index,
            source_sha256="a" * 64,
        )
        for index in range(100)
    )

    report = benchmark._scale_report(
        available_sources=sources,
        manifest_validation_milliseconds=1.25,
        model_root=Path("models"),
        policies=(),
        target_source_count=100,
    )

    assert report["availablePathCount"] == 100
    assert report["availableSourceCount"] == 1
    assert report["status"] == "not_evaluable"
    assert report["profiles"] == []


def test_independent_sources_renumber_after_duplicate_removal() -> None:
    sources = (
        benchmark.BenchmarkSource(
            case_id="case-a",
            path=Path("0.jpg"),
            relative_path="case-a/0.jpg",
            source_index=0,
            source_sha256="a" * 64,
        ),
        benchmark.BenchmarkSource(
            case_id="case-a",
            path=Path("1-copy.jpg"),
            relative_path="case-a/1-copy.jpg",
            source_index=1,
            source_sha256="a" * 64,
        ),
        benchmark.BenchmarkSource(
            case_id="case-a",
            path=Path("2.jpg"),
            relative_path="case-a/2.jpg",
            source_index=2,
            source_sha256="b" * 64,
        ),
        benchmark.BenchmarkSource(
            case_id="case-a",
            path=Path("3.jpg"),
            relative_path="case-a/3.jpg",
            source_index=3,
            source_sha256="c" * 64,
        ),
    )

    assert [source.source_index for source in benchmark._independent_sources(sources)] == [0, 1, 2]
