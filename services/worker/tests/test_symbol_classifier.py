from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from game_predictor_worker.images.dataset_split import build_symbol_dataset_split
from game_predictor_worker.images.normalization import rgb_pixel_checksum_sha256
from game_predictor_worker.images.symbol_classifier import (
    SymbolClassifierError,
    TrainingConfig,
    evaluate_classifier,
    logical_state_sha256,
    prepare_training_data,
    train_classifier,
)
from PIL import Image


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    asset_root = tmp_path / "assets"
    samples: list[dict[str, object]] = []
    symbols = [
        {"symbolCode": "dark", "symbolId": "symbol-dark"},
        {"symbolCode": "light", "symbolId": "symbol-light"},
    ]
    for source_index in range(9):
        source_checksum = hashlib.sha256(f"source-{source_index}".encode()).hexdigest()
        for class_index, symbol in enumerate(symbols):
            relative = f"dataset/assets/{source_index}-{class_index}.png"
            asset_path = asset_root.joinpath(*relative.split("/"))
            asset_path.parent.mkdir(parents=True, exist_ok=True)
            color = 20 + class_index * 210
            Image.new(
                "RGB",
                (32, 32),
                (color, source_index, 255 - source_index),
            ).save(asset_path)
            content = asset_path.read_bytes()
            identity = f"{source_index}:{class_index}"
            samples.append(
                {
                    "assetRelativePath": relative,
                    "cropChecksumSha256": hashlib.sha256(content).hexdigest(),
                    "sampleId": hashlib.sha256(f"sample:{identity}".encode()).hexdigest(),
                    "sourceGroup": f"group-{source_index % 2}",
                    "sourceImageChecksumSha256": source_checksum,
                    "sourceImageId": f"image-{source_index}",
                    "sourceImageRelativePath": f"images/{source_index}.jpg",
                    "symbolCode": symbol["symbolCode"],
                    "symbolId": symbol["symbolId"],
                }
            )
    dataset = {
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
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_bytes(_json_bytes(dataset))
    split_path = tmp_path / "split.json"
    split_path.write_bytes(build_symbol_dataset_split(dataset_path).to_json_bytes())
    return dataset_path, split_path, asset_root


def test_training_is_logically_deterministic_and_reports_all_classes(
    tmp_path: Path,
) -> None:
    dataset, split, asset_root = _fixture(tmp_path)
    data = prepare_training_data(dataset, split, asset_root)
    config = TrainingConfig(seed=7, epochs=3, batch_size=4, input_size=32)

    first = train_classifier(data, config)
    second = train_classifier(data, config)
    test_metrics = evaluate_classifier(
        first.state_dict,
        data.test,
        config,
        data.class_codes,
    )

    assert logical_state_sha256(first.state_dict) == logical_state_sha256(second.state_dict)
    assert first.history == second.history
    assert len(test_metrics.confusion_matrix) == 2
    assert all(len(row) == 2 for row in test_metrics.confusion_matrix)
    assert [row["symbolCode"] for row in test_metrics.per_class] == [
        "dark",
        "light",
    ]


def test_prepared_data_preserves_disjoint_split_membership(tmp_path: Path) -> None:
    dataset, split, asset_root = _fixture(tmp_path)

    data = prepare_training_data(dataset, split, asset_root)

    train_ids = {sample.sample_id for sample in data.train}
    validation_ids = {sample.sample_id for sample in data.validation}
    test_ids = {sample.sample_id for sample in data.test}
    assert not train_ids & validation_ids
    assert not train_ids & test_ids
    assert not validation_ids & test_ids
    assert len(train_ids | validation_ids | test_ids) == 18


def test_split_drift_is_rejected_before_training(tmp_path: Path) -> None:
    dataset, split, asset_root = _fixture(tmp_path)
    payload = json.loads(split.read_text(encoding="utf-8"))
    payload["splits"][0]["sampleIds"].reverse()
    split.write_bytes(_json_bytes(payload))

    with pytest.raises(SymbolClassifierError) as error:
        prepare_training_data(dataset, split, asset_root)

    assert error.value.code == "SYMBOL_CLASSIFIER_SPLIT_DRIFT"


def test_asset_checksum_drift_is_rejected(tmp_path: Path) -> None:
    dataset, split, asset_root = _fixture(tmp_path)
    payload = json.loads(dataset.read_text(encoding="utf-8"))
    relative = payload["samples"][0]["assetRelativePath"]
    Image.new("RGB", (32, 32), (123, 123, 123)).save(asset_root.joinpath(*relative.split("/")))

    with pytest.raises(SymbolClassifierError) as error:
        prepare_training_data(dataset, split, asset_root)

    assert error.value.code == "SYMBOL_CLASSIFIER_ASSET_DRIFT"


def test_prepared_data_accepts_explicit_rgb_pixel_checksum(tmp_path: Path) -> None:
    dataset, split, asset_root = _fixture(tmp_path)
    payload = json.loads(dataset.read_text(encoding="utf-8"))
    for sample in payload["samples"]:
        path = asset_root.joinpath(*sample["assetRelativePath"].split("/"))
        with Image.open(path) as image:
            sample["cropChecksumSha256"] = rgb_pixel_checksum_sha256(
                np.asarray(image.convert("RGB"), dtype=np.uint8)
            )
        sample["assetChecksumKind"] = "rgb-pixel-v1"
    dataset.write_bytes(_json_bytes(payload))
    split.write_bytes(build_symbol_dataset_split(dataset).to_json_bytes())

    data = prepare_training_data(dataset, split, asset_root)

    assert all(sample.asset_checksum_kind == "rgb-pixel-v1" for sample in data.train)


def test_test_samples_are_not_an_input_to_checkpoint_selection(tmp_path: Path) -> None:
    dataset, split, asset_root = _fixture(tmp_path)
    data = prepare_training_data(dataset, split, asset_root)
    config = TrainingConfig(seed=11, epochs=2, batch_size=4, input_size=32)

    outcome = train_classifier(data, config)
    outcome_without_test = train_classifier(replace(data, test=()), config)

    assert logical_state_sha256(outcome.state_dict) == logical_state_sha256(
        outcome_without_test.state_dict
    )
    assert outcome.history == outcome_without_test.history
    assert outcome.best_epoch in {1, 2}
