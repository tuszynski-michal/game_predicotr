from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from game_predictor_worker.symbols import (
    TrainingDatasetBuildError,
    TrainingDatasetConfig,
    TrainingSymbol,
    build_cumulative_training_dataset,
)


@pytest.fixture
def work_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("d")


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode()


def _cohort(
    artifact_root: Path,
    *,
    source_count: int = 12,
    unknown_symbol: bool = False,
) -> tuple[Path, str]:
    boards: list[dict[str, object]] = []
    data_root = artifact_root / "data"
    for source_index in range(source_count):
        source_checksum = hashlib.sha256(f"source-{source_index}".encode()).hexdigest()
        cells: list[dict[str, object]] = []
        for cell_index in range(15):
            content = f"crop-{source_index}-{cell_index}".encode()
            checksum = hashlib.sha256(content).hexdigest()
            relative = f"working/crops/{checksum}.png"
            destination = data_root / Path(*relative.split("/"))
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            code = (
                "UNKNOWN"
                if unknown_symbol and source_index == 0 and cell_index == 0
                else ("A" if cell_index % 2 == 0 else "B")
            )
            cells.append(
                {
                    "cellIndex": cell_index,
                    "columnIndex": cell_index % 5,
                    "cropChecksumSha256": checksum,
                    "cropRelativePath": relative,
                    "cropSampleId": hashlib.sha256(
                        f"sample-{source_index}-{cell_index}".encode()
                    ).hexdigest(),
                    "observationId": f"observation-{source_index}-{cell_index}",
                    "rowIndex": cell_index // 5,
                    "symbolCode": code,
                }
            )
        boards.append(
            {
                "board": {
                    "checksumSha256": hashlib.sha256(f"board-{source_index}".encode()).hexdigest(),
                    "relativePath": f"working/boards/{source_index}.png",
                },
                "cells": cells,
                "decisionStatus": "accepted" if source_index % 2 == 0 else "corrected",
                "gameId": "00000000-0000-0000-0000-000000000001",
                "geometry": {"corners": []},
                "geometryRevision": 1,
                "importJobId": f"import-{source_index // 2}",
                "pipelineFingerprint": "pipeline-v1",
                "positionIndex": source_index % 9,
                "recognizedBoardId": f"board-{source_index}",
                "resolutionRevision": 1,
                "resolvedAt": "2026-08-08T10:00:00+00:00",
                "resolvedBy": "owner",
                "reviewItemId": f"review-{source_index}",
                "sequenceNumber": source_index + 1,
                "source": {
                    "checksumSha256": source_checksum,
                    "relativePath": f"originals/{source_checksum}.jpg",
                },
                "sourceImageId": f"source-image-{source_index}",
                "sourceOrderIndex": source_index,
            }
        )
    payload = {
        "boards": boards,
        "counts": {
            "cellSamples": source_count * 15,
            "incompleteItems": 1,
            "pendingItems": 1,
            "rejectedItems": 1,
            "resolvedLayouts": source_count,
            "sourceImages": source_count,
        },
        "datasetKind": "verified-training-cohort-v1",
        "gameId": "00000000-0000-0000-0000-000000000001",
        "reviewState": [
            {
                "exclusionReason": "pending",
                "included": False,
                "reviewItemId": "pending-review",
            },
            {
                "exclusionReason": "human_rejected",
                "included": False,
                "reviewItemId": "rejected-review",
            },
        ],
        "schemaVersion": 1,
    }
    content = _canonical(payload)
    path = artifact_root / "data" / "training" / "fixture-cohort.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path, hashlib.sha256(content).hexdigest()


def _symbols() -> tuple[TrainingSymbol, ...]:
    return (
        TrainingSymbol(id="symbol-a", code="A"),
        TrainingSymbol(id="symbol-b", code="B"),
    )


def _cell_cohort(artifact_root: Path) -> tuple[Path, str]:
    data_root = artifact_root / "data"
    cells: list[dict[str, object]] = []
    for index, code in enumerate(("A", "B", "A", "B")):
        content = f"approved-cell-{index}".encode()
        crop_checksum = hashlib.sha256(content).hexdigest()
        crop_relative = f"working/crops/{crop_checksum}.png"
        destination = data_root / Path(*crop_relative.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        source_checksum = hashlib.sha256(f"source-{index // 2}".encode()).hexdigest()
        cells.append(
            {
                "cellIndex": index,
                "cellReviewId": f"cell-review-{index}",
                "cellRevision": 2,
                "cropChecksumSha256": crop_checksum,
                "cropRelativePath": crop_relative,
                "cropSampleId": hashlib.sha256(f"sample-v2-{index}".encode()).hexdigest(),
                "cropperVersion": "cropper-v2",
                "geometryRevision": 1,
                "importJobId": "import-v2",
                "recognizedBoardId": f"board-{index // 2}",
                "reviewItemId": f"review-{index // 2}",
                "selectionReason": "human_correction" if index == 0 else "diverse_approval",
                "sequenceNumber": index // 2 + 1,
                "source": {
                    "checksumSha256": source_checksum,
                    "relativePath": f"originals/{source_checksum}.jpg",
                },
                "sourceImageId": f"source-image-{index // 2}",
                "symbolCode": code,
            }
        )
    payload = {
        "cells": cells,
        "counts": {"cellSamples": 4, "sourceImages": 2},
        "datasetKind": "verified-symbol-cell-training-cohort-v2",
        "gameId": "00000000-0000-0000-0000-000000000001",
        "schemaVersion": 2,
    }
    content = _canonical(payload)
    path = data_root / "training" / "fixture-cell-cohort.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path, hashlib.sha256(content).hexdigest()


def test_cell_cohort_trains_without_a_complete_board(work_root: Path) -> None:
    cohort_path, cohort_checksum = _cell_cohort(work_root)

    result = build_cumulative_training_dataset(
        cohort_path=cohort_path,
        expected_cohort_checksum_sha256=cohort_checksum,
        artifact_root=work_root,
        game_code="fixture-game-v2",
        symbols=_symbols(),
    )

    assert result.sample_count == 4
    assert result.source_family_count == 2
    assert {sample["symbolCode"] for sample in result.manifest["samples"]} == {"A", "B"}


def test_v3_cell_cohort_requires_matching_approved_crop_provenance(
    work_root: Path,
) -> None:
    cohort_path, _cohort_checksum = _cell_cohort(work_root)
    payload = json.loads(cohort_path.read_text(encoding="utf-8"))
    payload["schemaVersion"] = 3
    payload["datasetKind"] = "verified-symbol-cell-training-cohort-v3-crop-provenance"
    payload["trainingEligibilityVersion"] = "symbol-cell-training-eligible-v1"
    payload["exclusions"] = {
        "changedCrop": 0,
        "gridIssue": 0,
        "missingAsset": 0,
        "unknown": 0,
        "unreadable": 0,
    }
    for cell in payload["cells"]:
        cell["approvedCrop"] = {
            "cropChecksumSha256": cell["cropChecksumSha256"],
            "cropSampleId": cell["cropSampleId"],
            "geometryRevision": cell["geometryRevision"],
        }
    content = _canonical(payload)
    cohort_path.write_bytes(content)

    result = build_cumulative_training_dataset(
        cohort_path=cohort_path,
        expected_cohort_checksum_sha256=hashlib.sha256(content).hexdigest(),
        artifact_root=work_root,
        game_code="fixture-game-v3",
        symbols=_symbols(),
    )
    assert result.sample_count == 4

    payload["cells"][0]["approvedCrop"]["geometryRevision"] = 0
    changed = _canonical(payload)
    cohort_path.write_bytes(changed)
    with pytest.raises(TrainingDatasetBuildError) as error:
        build_cumulative_training_dataset(
            cohort_path=cohort_path,
            expected_cohort_checksum_sha256=hashlib.sha256(changed).hexdigest(),
            artifact_root=work_root,
            game_code="fixture-game-v3-changed",
            symbols=_symbols(),
        )
    assert error.value.code == "TRAINING_DATASET_CROP_PROVENANCE_INVALID"


def test_build_is_deterministic_content_addressed_and_source_disjoint(
    work_root: Path,
) -> None:
    tmp_path = work_root
    cohort_path, cohort_checksum = _cohort(tmp_path)

    first = build_cumulative_training_dataset(
        cohort_path=cohort_path,
        expected_cohort_checksum_sha256=cohort_checksum,
        artifact_root=tmp_path,
        game_code="fixture-game",
        symbols=_symbols(),
    )
    second = build_cumulative_training_dataset(
        cohort_path=cohort_path,
        expected_cohort_checksum_sha256=cohort_checksum,
        artifact_root=tmp_path,
        game_code="fixture-game",
        symbols=tuple(reversed(_symbols())),
    )

    assert first.manifest_checksum_sha256 == second.manifest_checksum_sha256
    assert first.manifest == second.manifest
    assert first.reused is False
    assert second.reused is True
    assert first.sample_count == 180
    assert first.source_family_count == 12
    assert first.manifest_relative_path == (
        f"training/fixture-game/{cohort_checksum}/manifests/{first.manifest_checksum_sha256}.json"
    )

    split_sources: list[set[str]] = []
    split_samples: dict[str, set[str]] = {}
    samples = first.manifest["samples"]
    assert isinstance(samples, list)
    for split in first.manifest["splits"]:
        assert isinstance(split, dict)
        split_sources.append(set(split["sourceFamilies"]))
        split_samples[str(split["name"])] = {
            str(sample["cropSampleId"]) for sample in samples if sample["split"] == split["name"]
        }
    for index, current in enumerate(split_sources):
        assert not any(current & other for other in split_sources[index + 1 :])
    assert not split_samples["regression"] & split_samples["train"]
    assert first.manifest["exclusions"] == [
        {"count": 1, "reason": "human_rejected"},
        {"count": 1, "reason": "pending"},
    ]


def test_existing_source_assignments_stay_stable_when_cohort_grows(
    work_root: Path,
) -> None:
    tmp_path = work_root
    small_path, small_checksum = _cohort(tmp_path / "small", source_count=8)
    large_path, large_checksum = _cohort(tmp_path / "large", source_count=14)
    config = TrainingDatasetConfig(seed="stable-across-iterations")

    small = build_cumulative_training_dataset(
        cohort_path=small_path,
        expected_cohort_checksum_sha256=small_checksum,
        artifact_root=tmp_path / "small",
        game_code="fixture-game",
        symbols=_symbols(),
        config=config,
    )
    large = build_cumulative_training_dataset(
        cohort_path=large_path,
        expected_cohort_checksum_sha256=large_checksum,
        artifact_root=tmp_path / "large",
        game_code="fixture-game",
        symbols=_symbols(),
        config=config,
    )
    small_assignment = {
        sample["sourceFamily"]: sample["split"] for sample in small.manifest["samples"]
    }
    large_assignment = {
        sample["sourceFamily"]: sample["split"] for sample in large.manifest["samples"]
    }
    assert all(large_assignment[source] == split for source, split in small_assignment.items())


def test_build_stops_on_crop_checksum_mismatch(work_root: Path) -> None:
    tmp_path = work_root
    cohort_path, cohort_checksum = _cohort(tmp_path, source_count=1)
    payload = json.loads(cohort_path.read_text(encoding="utf-8"))
    relative = payload["boards"][0]["cells"][0]["cropRelativePath"]
    (tmp_path / "data" / Path(*relative.split("/"))).write_bytes(b"changed")

    with pytest.raises(TrainingDatasetBuildError) as error:
        build_cumulative_training_dataset(
            cohort_path=cohort_path,
            expected_cohort_checksum_sha256=cohort_checksum,
            artifact_root=tmp_path,
            game_code="fixture-game",
            symbols=_symbols(),
        )

    assert error.value.code == "TRAINING_DATASET_CROP_CHECKSUM_MISMATCH"


def test_build_stops_on_unknown_human_symbol(work_root: Path) -> None:
    tmp_path = work_root
    cohort_path, cohort_checksum = _cohort(tmp_path, source_count=1, unknown_symbol=True)

    with pytest.raises(TrainingDatasetBuildError) as error:
        build_cumulative_training_dataset(
            cohort_path=cohort_path,
            expected_cohort_checksum_sha256=cohort_checksum,
            artifact_root=tmp_path,
            game_code="fixture-game",
            symbols=_symbols(),
        )

    assert error.value.code == "TRAINING_DATASET_SYMBOL_UNKNOWN"


def test_different_source_records_with_same_material_stay_in_one_family(
    work_root: Path,
) -> None:
    cohort_path, _ = _cohort(work_root, source_count=2)
    payload = json.loads(cohort_path.read_text(encoding="utf-8"))
    payload["boards"][1]["source"]["checksumSha256"] = payload["boards"][0]["source"][
        "checksumSha256"
    ]
    content = _canonical(payload)
    cohort_path.write_bytes(content)

    artifact = build_cumulative_training_dataset(
        cohort_path=cohort_path,
        expected_cohort_checksum_sha256=hashlib.sha256(content).hexdigest(),
        artifact_root=work_root,
        game_code="fixture-game",
        symbols=_symbols(),
    )

    assert artifact.source_family_count == 1
    assert len({sample["split"] for sample in artifact.manifest["samples"]}) == 1


def test_build_stops_on_incomplete_verified_board(work_root: Path) -> None:
    cohort_path, _ = _cohort(work_root, source_count=1)
    payload = json.loads(cohort_path.read_text(encoding="utf-8"))
    payload["boards"][0]["cells"].pop()
    payload["counts"]["cellSamples"] = 14
    content = _canonical(payload)
    cohort_path.write_bytes(content)

    with pytest.raises(TrainingDatasetBuildError) as error:
        build_cumulative_training_dataset(
            cohort_path=cohort_path,
            expected_cohort_checksum_sha256=hashlib.sha256(content).hexdigest(),
            artifact_root=work_root,
            game_code="fixture-game",
            symbols=_symbols(),
        )

    assert error.value.code == "TRAINING_DATASET_BOARD_INCOMPLETE"


def test_build_stops_when_cohort_manifest_changed(work_root: Path) -> None:
    tmp_path = work_root
    cohort_path, cohort_checksum = _cohort(tmp_path, source_count=1)
    cohort_path.write_bytes(cohort_path.read_bytes() + b" ")

    with pytest.raises(TrainingDatasetBuildError) as error:
        build_cumulative_training_dataset(
            cohort_path=cohort_path,
            expected_cohort_checksum_sha256=cohort_checksum,
            artifact_root=tmp_path,
            game_code="fixture-game",
            symbols=_symbols(),
        )

    assert error.value.code == "TRAINING_DATASET_COHORT_CHECKSUM_MISMATCH"
