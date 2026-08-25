from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from game_predictor_worker.images.board_cell_geometry_contract import canonical_json_bytes
from game_predictor_worker.images.v19_symbol_residuals import (
    COHORT_VERSION,
    PREPROCESSING_VERSION,
)
from game_predictor_worker.symbols.v19_candidate import (
    V19_DATASET_VERSION,
    V19SymbolCandidateError,
    load_v19_candidate_dataset,
)
from PIL import Image


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _fixture(root: Path) -> tuple[Path, str, Path, dict[str, str]]:
    crop_root = root / "quality"
    class_codes = ("cherries", "grapes", "lemon", "orange", "plum", "seven", "star", "watermelon")
    assets: dict[str, tuple[str, str]] = {}
    for index, code in enumerate(class_codes):
        temporary = crop_root / f"{code}.png"
        temporary.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (4, 4), (index * 25, 20, 220 - index * 20)).save(temporary)
        content = temporary.read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        relative = f"crops/{checksum[:2]}/{checksum}.png"
        destination = crop_root.joinpath(*Path(relative).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        temporary.unlink()
        assets[code] = (relative, checksum)
    sources = tuple(_sha(f"source-{index}") for index in range(41))
    assignments = {
        source: (
            "validation"
            if index == 38
            else "test"
            if index == 39
            else "regression"
            if index == 40
            else "train"
        )
        for index, source in enumerate(sources)
    }
    boards = []
    for board_index in range(300):
        source = sources[board_index % len(sources)]
        cells = []
        for cell_index in range(15):
            code = class_codes[(board_index + cell_index) % len(class_codes)]
            relative, checksum = assets[code]
            cells.append(
                {
                    "cellIndex": cell_index,
                    "columnIndex": cell_index % 5,
                    "cropChecksumSha256": checksum,
                    "cropRelativePath": relative,
                    "cropSampleId": _sha(f"sample-{board_index}-{cell_index}-{code}"),
                    "rowIndex": cell_index // 5,
                    "symbolCode": code,
                }
            )
        boards.append(
            {
                "boardId": f"board-{board_index}",
                "cells": cells,
                "decisionStatus": "corrected",
                "sequenceNumber": board_index + 1,
                "source": {
                    "checksumSha256": source,
                    "id": f"source-id-{board_index % len(sources)}",
                    "relativePath": f"originals/{source}.jpg",
                },
                "sourceFamily": source,
                "split": assignments[source],
                "stagingLabel": f"staging-{board_index % 6}",
            }
        )
    document = {
        "boards": boards,
        "cropCount": 4500,
        "preprocessingVersion": PREPROCESSING_VERSION,
        "scope": {
            "boardCount": 300,
            "sourceFamilyCount": 41,
            "stagingCount": 6,
        },
        "split": {
            "assignments": assignments,
            "policyVersion": "source-family-balanced-split-v2",
            "seed": "test-seed",
        },
        "version": COHORT_VERSION,
    }
    content = canonical_json_bytes(document)
    checksum = hashlib.sha256(content).hexdigest()
    cohort_path = root / f"{checksum}.json"
    cohort_path.write_bytes(content)
    return cohort_path, checksum, crop_root, {code: f"id-{code}" for code in class_codes}


def test_v19_dataset_preserves_frozen_source_split_and_preprocessing(tmp_path: Path) -> None:
    cohort_path, checksum, crop_root, catalog = _fixture(tmp_path)

    result = load_v19_candidate_dataset(
        cohort_path=cohort_path,
        expected_cohort_checksum_sha256=checksum,
        crop_root=crop_root,
        class_ids_by_code=catalog,
    )

    assert result.board_count == 300
    assert result.crop_count == 4500
    assert result.source_family_count == 41
    assert result.staging_count == 6
    assert len(result.prepared.train) == 4185
    assert len({sample.source_image_checksum for sample in result.prepared.train}) == 38
    assert len({sample.source_image_checksum for sample in result.prepared.validation}) == 1
    assert len({sample.source_image_checksum for sample in result.prepared.test}) == 1
    assert len({sample.source_image_checksum for sample in result.prepared.regression}) == 1
    assert result.prepared.class_codes == tuple(sorted(catalog))
    expected_dataset_sha = hashlib.sha256(
        canonical_json_bytes(
            {
                "cohortChecksumSha256": checksum,
                "datasetVersion": V19_DATASET_VERSION,
                "preprocessingVersion": PREPROCESSING_VERSION,
                "splitChecksumSha256": result.prepared.split_sha256,
            }
        )
    ).hexdigest()
    assert result.prepared.dataset_sha256 == expected_dataset_sha


def test_v19_dataset_rejects_source_family_split_leakage(tmp_path: Path) -> None:
    cohort_path, checksum, crop_root, catalog = _fixture(tmp_path)
    document = json.loads(cohort_path.read_text(encoding="utf-8"))
    document["boards"][0]["split"] = "test"
    content = canonical_json_bytes(document)
    drifted_path = tmp_path / "drifted.json"
    drifted_path.write_bytes(content)

    with pytest.raises(V19SymbolCandidateError) as captured:
        load_v19_candidate_dataset(
            cohort_path=drifted_path,
            expected_cohort_checksum_sha256=hashlib.sha256(content).hexdigest(),
            crop_root=crop_root,
            class_ids_by_code=catalog,
        )

    assert captured.value.code == "V19_CANDIDATE_BOARD_INVALID"
    assert checksum != hashlib.sha256(content).hexdigest()


def test_v19_dataset_rejects_incomplete_board(tmp_path: Path) -> None:
    cohort_path, _checksum, crop_root, catalog = _fixture(tmp_path)
    document = json.loads(cohort_path.read_text(encoding="utf-8"))
    document["boards"][0]["cells"].pop()
    document["cropCount"] -= 1
    content = canonical_json_bytes(document)
    drifted_path = tmp_path / "incomplete.json"
    drifted_path.write_bytes(content)

    with pytest.raises(V19SymbolCandidateError) as captured:
        load_v19_candidate_dataset(
            cohort_path=drifted_path,
            expected_cohort_checksum_sha256=hashlib.sha256(content).hexdigest(),
            crop_root=crop_root,
            class_ids_by_code=catalog,
        )

    assert captured.value.code == "V19_CANDIDATE_BOARD_INCOMPLETE"
