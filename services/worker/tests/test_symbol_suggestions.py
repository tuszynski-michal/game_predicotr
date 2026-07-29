from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import torch
from game_predictor_worker.images.symbol_classifier import (
    CLASSIFIER_VERSION,
    PreparedTrainingData,
    SmallSymbolCnn,
)
from game_predictor_worker.images.symbol_dataset import SymbolCropSample
from game_predictor_worker.images.symbol_suggestions import (
    FrozenSymbolSuggestionService,
    ReferenceEmbedding,
    SymbolSuggestionError,
    rank_symbol_suggestions,
    validate_classifier_provenance,
)
from PIL import Image
from torch.nn import functional


def _reference(
    sample_id: str,
    source: str,
    symbol: str,
    embedding: list[float],
) -> ReferenceEmbedding:
    return ReferenceEmbedding(
        sample_id=sample_id,
        source_image_checksum=source,
        symbol_code=symbol,
        embedding=functional.normalize(torch.tensor(embedding), dim=0),
    )


def test_ranking_is_deterministic_unique_by_symbol_and_stably_tied() -> None:
    references = (
        _reference("z-ref", "source-z", "zebra", [1.0, 0.0]),
        _reference("a-ref", "source-a", "alpha", [1.0, 0.0]),
        _reference("alpha-worse", "source-b", "alpha", [0.8, 0.2]),
    )
    arguments = {
        "target_embedding": torch.tensor([1.0, 0.0]),
        "classifier_probabilities": torch.tensor([0.6, 0.4]),
        "class_codes": ("alpha", "zebra"),
        "references": references,
        "target_sample_id": "target",
        "target_source_image_checksum": "target-source",
        "minimum_similarity": 0.5,
    }

    first = rank_symbol_suggestions(**arguments)
    second = rank_symbol_suggestions(**arguments)

    assert first == second
    assert [value.symbol_code for value in first] == ["alpha", "zebra"]
    assert first[0].reference_sample_id == "a-ref"


def test_same_source_and_self_references_are_never_candidates() -> None:
    ranked = rank_symbol_suggestions(
        target_embedding=torch.tensor([1.0, 0.0]),
        classifier_probabilities=torch.tensor([0.5, 0.5]),
        class_codes=("leak", "safe"),
        references=(
            _reference("target", "other", "leak", [1.0, 0.0]),
            _reference("same-source", "source-a", "leak", [1.0, 0.0]),
            _reference("safe", "source-b", "safe", [0.9, 0.1]),
        ),
        target_sample_id="target",
        target_source_image_checksum="source-a",
        minimum_similarity=0.5,
    )

    assert [value.symbol_code for value in ranked] == ["safe"]


def test_empty_or_low_similarity_references_yield_no_suggestion() -> None:
    common = {
        "target_embedding": torch.tensor([1.0, 0.0]),
        "classifier_probabilities": torch.tensor([1.0]),
        "class_codes": ("symbol",),
        "target_sample_id": "target",
        "target_source_image_checksum": "target-source",
        "minimum_similarity": 0.8,
    }

    assert rank_symbol_suggestions(references=(), **common) == ()
    assert (
        rank_symbol_suggestions(
            references=(_reference("far", "source-b", "symbol", [0.0, 1.0]),),
            **common,
        )
        == ()
    )


def test_crop_drift_stops_inference(tmp_path: Path) -> None:
    crop_root = tmp_path / "crops"
    crop_path = crop_root / "cells" / "sample.png"
    crop_path.parent.mkdir(parents=True)
    Image.new("RGB", (64, 64), (10, 20, 30)).save(crop_path)
    expected_checksum = hashlib.sha256(crop_path.read_bytes()).hexdigest()
    sample = SymbolCropSample(
        sample_id="sample",
        source_image_id="source-id",
        source_image_checksum_sha256="a" * 64,
        source_image_relative_path="source.jpg",
        source_group="fixture",
        sequence_number=1,
        board_index=0,
        cell_index=0,
        row_index=0,
        column_index=0,
        crop_relative_path="cells/sample.png",
        crop_checksum_sha256=expected_checksum,
        observation_id="observation",
    )
    service = FrozenSymbolSuggestionService(
        model=SmallSymbolCnn(1),
        class_codes=("symbol",),
        input_size=64,
        references=(_reference("reference", "b" * 64, "symbol", [1.0] + [0.0] * 63),),
        crop_root=crop_root,
        previous_labels_by_observation={},
        minimum_similarity=0.0,
    )
    Image.new("RGB", (64, 64), (200, 20, 30)).save(crop_path)

    with pytest.raises(SymbolSuggestionError) as error:
        service.for_sample(sample)

    assert error.value.code == "SYMBOL_SUGGESTION_CROP_DRIFT"


def test_previous_geometry_label_is_separate_read_only_evidence(
    tmp_path: Path,
) -> None:
    crop_root = tmp_path / "crops"
    crop_path = crop_root / "sample.png"
    crop_root.mkdir()
    Image.new("RGB", (64, 64), (10, 20, 30)).save(crop_path)
    sample = SymbolCropSample(
        sample_id="current",
        source_image_id="source-id",
        source_image_checksum_sha256="a" * 64,
        source_image_relative_path="source.jpg",
        source_group="fixture",
        sequence_number=1,
        board_index=0,
        cell_index=0,
        row_index=0,
        column_index=0,
        crop_relative_path="sample.png",
        crop_checksum_sha256=hashlib.sha256(crop_path.read_bytes()).hexdigest(),
        observation_id="stable-observation",
    )
    service = FrozenSymbolSuggestionService(
        model=SmallSymbolCnn(1),
        class_codes=("current-model-code",),
        input_size=64,
        references=(),
        crop_root=crop_root,
        previous_labels_by_observation={"stable-observation": ("previous-code", "previous-sample")},
    )

    payload = service.for_sample(sample)

    assert payload["suggestionStatus"] == "no_suggestion"
    assert payload["previousGeometryLabel"] == {
        "previousSampleId": "previous-sample",
        "source": "previous_crop_version",
        "symbolCode": "previous-code",
    }


def test_classifier_provenance_drift_is_rejected(tmp_path: Path) -> None:
    artifact = tmp_path / "model.pt"
    artifact.write_bytes(b"immutable-model")
    data = PreparedTrainingData(
        dataset_sha256="a" * 64,
        split_sha256="b" * 64,
        split_seed="seed",
        class_codes=("symbol",),
        class_ids=("symbol-id",),
        train=(),
        validation=(),
        test=(),
    )
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "artifact": {"sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()},
                "classifierVersion": CLASSIFIER_VERSION,
                "datasetSha256": data.dataset_sha256,
                "splitSha256": data.split_sha256,
            }
        ),
        encoding="utf-8",
    )
    validate_classifier_provenance(report, artifact, data)
    artifact.write_bytes(b"changed-model")

    with pytest.raises(SymbolSuggestionError) as error:
        validate_classifier_provenance(report, artifact, data)

    assert error.value.code == "SYMBOL_SUGGESTION_CLASSIFIER_PROVENANCE_DRIFT"
