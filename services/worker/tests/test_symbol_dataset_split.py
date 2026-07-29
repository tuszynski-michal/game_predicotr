from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from game_predictor_worker.images.dataset_split import (
    DATASET_SPLIT_VERSION,
    SymbolDatasetSplitError,
    build_symbol_dataset_split,
)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _dataset(
    tmp_path: Path,
    *,
    source_count: int = 9,
    rare_symbol_sources: set[int] | None = None,
) -> Path:
    symbols = [
        {"symbolCode": "A", "symbolId": "symbol-a"},
        {"symbolCode": "B", "symbolId": "symbol-b"},
        {"symbolCode": "C", "symbolId": "symbol-c"},
    ]
    samples: list[dict[str, object]] = []
    for source_index in range(source_count):
        source_checksum = hashlib.sha256(f"source-{source_index}".encode()).hexdigest()
        codes = ("A", "B", "C")
        if rare_symbol_sources is not None and source_index not in rare_symbol_sources:
            codes = ("A", "B")
        for sample_index, code in enumerate(codes):
            identity = f"{source_index}:{sample_index}:{code}"
            samples.append(
                {
                    "cropChecksumSha256": hashlib.sha256(
                        f"crop:{identity}".encode()
                    ).hexdigest(),
                    "sampleId": hashlib.sha256(f"sample:{identity}".encode()).hexdigest(),
                    "sourceGroup": f"group-{source_index % 2}",
                    "sourceImageChecksumSha256": source_checksum,
                    "sourceImageId": f"image-{source_index}",
                    "sourceImageRelativePath": f"images/{source_index}.jpg",
                    "symbolCode": code,
                    "symbolId": f"symbol-{code.lower()}",
                }
            )
    payload = {
        "corpusId": "fixture-corpus",
        "datasetVersion": "labeled-symbol-dataset-v1",
        "gameCode": "fixture-game",
        "gameId": "fixture-game-id",
        "sampleCount": len(samples),
        "samples": samples,
        "schemaVersion": 1,
        "status": "ready",
        "symbols": symbols,
    }
    path = tmp_path / "dataset.json"
    path.write_bytes(_json_bytes(payload))
    return path


def test_split_is_deterministic_source_disjoint_and_complete(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path)

    first = build_symbol_dataset_split(dataset)
    second = build_symbol_dataset_split(dataset)
    payload = first.to_dict()

    assert first.to_json_bytes() == second.to_json_bytes()
    assert payload["datasetSplitVersion"] == DATASET_SPLIT_VERSION
    assert payload["status"] == "ready"
    assert payload["qualityGate"] == {
        "assetLeakageCount": 0,
        "minimumSourcesPerSplit": 2,
        "missingSymbolsBySplit": {"test": [], "train": [], "validation": []},
        "sourceImageLeakageCount": 0,
        "status": "passed",
    }

    split_sources: list[set[str]] = []
    split_samples: list[set[str]] = []
    for split in payload["splits"]:
        assert isinstance(split, dict)
        assert split["sourceImageCount"] >= 2
        split_sources.append(
            {
                str(source["sourceImageChecksumSha256"])
                for source in split["sources"]
            }
        )
        split_samples.append(set(split["sampleIds"]))
    assert not split_sources[0] & split_sources[1]
    assert not split_sources[0] & split_sources[2]
    assert not split_sources[1] & split_sources[2]
    assert not split_samples[0] & split_samples[1]
    assert not split_samples[0] & split_samples[2]
    assert not split_samples[1] & split_samples[2]
    assert all(
        split["sampleCount"] > 0
        for symbol in payload["symbols"]
        for split in symbol["splits"].values()
    )


def test_split_seed_changes_assignment_but_remains_deterministic(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path, source_count=12)

    first = build_symbol_dataset_split(dataset, seed="first").to_json_bytes()
    repeated = build_symbol_dataset_split(dataset, seed="first").to_json_bytes()
    other = build_symbol_dataset_split(dataset, seed="second").to_json_bytes()

    assert first == repeated
    assert first != other


def test_split_rejects_symbol_without_three_source_images(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path, rare_symbol_sources={0, 1})

    with pytest.raises(SymbolDatasetSplitError) as error:
        build_symbol_dataset_split(dataset)

    assert error.value.code == "SYMBOL_DATASET_SPLIT_COVERAGE_INSUFFICIENT"


def test_split_rejects_identical_asset_from_different_sources(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path)
    payload = json.loads(dataset.read_text(encoding="utf-8"))
    payload["samples"][3]["cropChecksumSha256"] = payload["samples"][0][
        "cropChecksumSha256"
    ]
    dataset.write_bytes(_json_bytes(payload))

    with pytest.raises(SymbolDatasetSplitError) as error:
        build_symbol_dataset_split(dataset)

    assert error.value.code == "SYMBOL_DATASET_SPLIT_ASSET_SOURCE_CONFLICT"


def test_split_rejects_symbol_catalog_drift(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path)
    payload = json.loads(dataset.read_text(encoding="utf-8"))
    payload["samples"][0]["symbolId"] = "different-symbol"
    dataset.write_bytes(_json_bytes(payload))

    with pytest.raises(SymbolDatasetSplitError) as error:
        build_symbol_dataset_split(dataset)

    assert error.value.code == "SYMBOL_DATASET_SPLIT_SYMBOL_MISMATCH"
