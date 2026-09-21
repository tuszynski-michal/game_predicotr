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
