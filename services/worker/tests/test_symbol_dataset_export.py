from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from game_predictor_worker.images.symbol_dataset import (
    DATASET_VERSION,
    INVENTORY_VERSION,
    LABEL_SOURCE_VERSION,
    SymbolDatasetError,
    build_symbol_crop_inventory,
    export_reviewed_symbol_dataset,
)
from PIL import Image


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _write_json(path: Path, value: object) -> None:
    path.write_bytes(_json_bytes(value))


def _fixture(tmp_path: Path) -> dict[str, Path]:
    crop_root = tmp_path / "crops"
    crop_root.mkdir()
    source_checksum = "a" * 64
    cells: list[dict[str, object]] = []
    for cell_index in range(15):
        row, column = divmod(cell_index, 5)
        relative = (
            f"board-cell-crops-v1/aa/{source_checksum}/board-00/cells/r{row:02d}-c{column:02d}.png"
        )
        path = crop_root / Path(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        color_index = 0 if cell_index < 2 else cell_index
        Image.new(
            "RGB",
            (90, 90),
            (20 + color_index, 40 + color_index, 60 + color_index),
        ).save(path, format="PNG")
        content = path.read_bytes()
        cells.append(
            {
                "checksumSha256": hashlib.sha256(content).hexdigest(),
                "columnIndex": column,
                "height": 90,
                "relativePath": relative,
                "rowIndex": row,
                "width": 90,
            }
        )

    corpus = {
        "corpusId": "fixture-corpus",
        "images": [
            {
                "expectedBoardCount": 1,
                "id": "fixture-image",
                "relativePath": "source.jpg",
                "sha256": source_checksum,
                "sourceGroup": "fixture-source",
            }
        ],
    }
    golden = {
        "annotationProvenance": {
            "method": "algorithm-assisted-visual-review",
            "reviewedImageCount": 1,
        },
        "corpusId": "fixture-corpus",
        "images": [
            {
                "boards": [{"positionIndex": 0, "sequenceNumber": 1}],
                "imageId": "fixture-image",
                "status": "complete",
            }
        ],
    }
    crops = {
        "cropperVersion": "board-cell-crops-v1",
        "images": [
            {
                "boards": [
                    {
                        "cells": cells,
                        "positionIndex": 0,
                    }
                ],
                "sourceChecksumSha256": source_checksum,
                "status": "cropped",
            }
        ],
        "status": "cropped",
    }
    corpus_path = tmp_path / "corpus.json"
    golden_path = tmp_path / "golden.json"
    crops_path = tmp_path / "crops.json"
    _write_json(corpus_path, corpus)
    _write_json(golden_path, golden)
    _write_json(crops_path, crops)
    return {
        "corpus": corpus_path,
        "crop_report": crops_path,
        "crop_root": crop_root,
        "golden": golden_path,
    }


def _inventory(tmp_path: Path) -> tuple[Path, dict[str, Path], dict[str, object]]:
    fixture = _fixture(tmp_path)
    inventory = build_symbol_crop_inventory(
        fixture["corpus"],
        fixture["golden"],
        fixture["crop_report"],
        fixture["crop_root"],
    )
    path = tmp_path / "inventory.json"
    path.write_bytes(inventory.to_json_bytes())
    return path, fixture, inventory.to_dict()


def _label_source(
    inventory: dict[str, object],
    *,
    decisions: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "corpusId": "fixture-corpus",
        "gameCode": "fixture-game",
        "gameId": "game-1",
        "labelSourceVersion": LABEL_SOURCE_VERSION,
        "labels": decisions,
        "reviewRevision": 1,
        "reviewedBy": "fixture-reviewer",
        "schemaVersion": 1,
        "symbols": [
            {"symbolCode": "S1", "symbolId": "symbol-1"},
            {"symbolCode": "S2", "symbolId": "symbol-2"},
        ],
    }


def test_inventory_verifies_all_cells_and_is_deterministic(tmp_path: Path) -> None:
    path, fixture, payload = _inventory(tmp_path)

    second = build_symbol_crop_inventory(
        fixture["corpus"],
        fixture["golden"],
        fixture["crop_report"],
        fixture["crop_root"],
    )

    assert payload["inventoryVersion"] == INVENTORY_VERSION
    assert payload["sampleCount"] == 15
    assert payload["boardCount"] == 1
    assert second.to_json_bytes() == path.read_bytes()
    assert [sample["cellIndex"] for sample in payload["samples"]] == list(range(15))
    assert all("ocr" not in key.lower() for key in payload)


def test_inventory_rejects_crop_checksum_drift(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    crop_report = json.loads(fixture["crop_report"].read_text(encoding="utf-8"))
    crop_report["images"][0]["boards"][0]["cells"][0]["checksumSha256"] = "f" * 64
    _write_json(fixture["crop_report"], crop_report)

    with pytest.raises(SymbolDatasetError) as error:
        build_symbol_crop_inventory(
            fixture["corpus"],
            fixture["golden"],
            fixture["crop_report"],
            fixture["crop_root"],
        )

    assert error.value.code == "SYMBOL_DATASET_CROP_CHECKSUM_MISMATCH"


def test_inventory_rejects_unsafe_crop_path(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    crop_report = json.loads(fixture["crop_report"].read_text(encoding="utf-8"))
    crop_report["images"][0]["boards"][0]["cells"][0]["relativePath"] = "../cell.png"
    _write_json(fixture["crop_report"], crop_report)

    with pytest.raises(SymbolDatasetError) as error:
        build_symbol_crop_inventory(
            fixture["corpus"],
            fixture["golden"],
            fixture["crop_report"],
            fixture["crop_root"],
        )

    assert error.value.code == "SYMBOL_DATASET_UNSAFE_CROP_PATH"


def test_reviewed_export_deduplicates_assets_and_keeps_occurrences(
    tmp_path: Path,
) -> None:
    inventory_path, fixture, inventory = _inventory(tmp_path)
    samples = inventory["samples"]
    assert isinstance(samples, list)
    labels = _label_source(
        inventory,
        decisions=[
            {
                "decision": "accepted",
                "sampleId": samples[0]["sampleId"],
                "symbolCode": "S1",
                "symbolId": "symbol-1",
            },
            {
                "decision": "accepted",
                "sampleId": samples[1]["sampleId"],
                "symbolCode": "S1",
                "symbolId": "symbol-1",
            },
            {
                "decision": "accepted",
                "sampleId": samples[2]["sampleId"],
                "symbolCode": "S2",
                "symbolId": "symbol-2",
            },
        ],
    )
    labels_path = tmp_path / "labels.json"
    _write_json(labels_path, labels)
    output_root = tmp_path / "dataset"

    report = export_reviewed_symbol_dataset(
        inventory_path,
        labels_path,
        fixture["crop_root"],
        output_root,
    )
    repeated = export_reviewed_symbol_dataset(
        inventory_path,
        labels_path,
        fixture["crop_root"],
        output_root,
    )
    payload = report.to_dict()

    assert payload["datasetVersion"] == DATASET_VERSION
    assert payload["status"] == "ready"
    assert payload["sampleCount"] == 3
    assert payload["assetCount"] == 2
    assert payload["pendingCount"] == 12
    assert len({sample["sampleId"] for sample in payload["samples"]}) == 3
    assert repeated.to_json_bytes() == report.to_json_bytes()
    assert len(list(output_root.rglob("*.png"))) == 2


def test_empty_review_is_waiting_for_labels(tmp_path: Path) -> None:
    inventory_path, fixture, inventory = _inventory(tmp_path)
    labels_path = tmp_path / "labels.json"
    _write_json(labels_path, _label_source(inventory, decisions=[]))

    report = export_reviewed_symbol_dataset(
        inventory_path,
        labels_path,
        fixture["crop_root"],
        tmp_path / "dataset",
    ).to_dict()

    assert report["status"] == "waiting_for_labels"
    assert report["sampleCount"] == 0
    assert report["pendingCount"] == 15


def test_duplicate_review_decision_is_rejected(tmp_path: Path) -> None:
    inventory_path, fixture, inventory = _inventory(tmp_path)
    samples = inventory["samples"]
    assert isinstance(samples, list)
    decision = {
        "decision": "accepted",
        "sampleId": samples[0]["sampleId"],
        "symbolCode": "S1",
        "symbolId": "symbol-1",
    }
    labels_path = tmp_path / "labels.json"
    _write_json(
        labels_path,
        _label_source(inventory, decisions=[decision, decision]),
    )

    with pytest.raises(SymbolDatasetError) as error:
        export_reviewed_symbol_dataset(
            inventory_path,
            labels_path,
            fixture["crop_root"],
            tmp_path / "dataset",
        )

    assert error.value.code == "SYMBOL_DATASET_LABEL_DUPLICATE"


def test_unknown_sample_is_rejected(tmp_path: Path) -> None:
    inventory_path, fixture, inventory = _inventory(tmp_path)
    labels_path = tmp_path / "labels.json"
    _write_json(
        labels_path,
        _label_source(
            inventory,
            decisions=[
                {
                    "decision": "accepted",
                    "sampleId": "f" * 64,
                    "symbolCode": "S1",
                    "symbolId": "symbol-1",
                }
            ],
        ),
    )

    with pytest.raises(SymbolDatasetError) as error:
        export_reviewed_symbol_dataset(
            inventory_path,
            labels_path,
            fixture["crop_root"],
            tmp_path / "dataset",
        )

    assert error.value.code == "SYMBOL_DATASET_LABEL_SAMPLE_UNKNOWN"


def test_tampered_inventory_identity_is_rejected(tmp_path: Path) -> None:
    inventory_path, fixture, inventory = _inventory(tmp_path)
    samples = inventory["samples"]
    assert isinstance(samples, list)
    samples[0]["cellIndex"] = 14
    _write_json(inventory_path, inventory)
    labels_path = tmp_path / "labels.json"
    _write_json(labels_path, _label_source(inventory, decisions=[]))

    with pytest.raises(SymbolDatasetError) as error:
        export_reviewed_symbol_dataset(
            inventory_path,
            labels_path,
            fixture["crop_root"],
            tmp_path / "dataset",
        )

    assert error.value.code == "SYMBOL_DATASET_INVENTORY_DRIFT"


def test_identical_crop_cannot_have_conflicting_labels(tmp_path: Path) -> None:
    inventory_path, fixture, inventory = _inventory(tmp_path)
    samples = inventory["samples"]
    assert isinstance(samples, list)
    assert samples[0]["cropChecksumSha256"] == samples[1]["cropChecksumSha256"]
    labels_path = tmp_path / "labels.json"
    _write_json(
        labels_path,
        _label_source(
            inventory,
            decisions=[
                {
                    "decision": "accepted",
                    "sampleId": samples[0]["sampleId"],
                    "symbolCode": "S1",
                    "symbolId": "symbol-1",
                },
                {
                    "decision": "accepted",
                    "sampleId": samples[1]["sampleId"],
                    "symbolCode": "S2",
                    "symbolId": "symbol-2",
                },
            ],
        ),
    )

    with pytest.raises(SymbolDatasetError) as error:
        export_reviewed_symbol_dataset(
            inventory_path,
            labels_path,
            fixture["crop_root"],
            tmp_path / "dataset",
        )

    assert error.value.code == "SYMBOL_DATASET_ASSET_LABEL_CONFLICT"
