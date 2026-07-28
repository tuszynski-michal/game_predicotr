from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from game_predictor_worker.images.symbol_dataset import (
    INVENTORY_VERSION,
    load_reviewed_label_source,
)
from game_predictor_worker.images.symbol_review import (
    BootstrapSymbolReview,
    SymbolReviewError,
)
from PIL import Image


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _sample_id(
    *,
    source_checksum: str,
    sequence_number: int,
    board_index: int,
    row_index: int,
    column_index: int,
    crop_checksum: str,
) -> str:
    logical = "\0".join(
        (
            INVENTORY_VERSION,
            "review-fixture",
            source_checksum,
            str(sequence_number),
            str(board_index),
            str(row_index),
            str(column_index),
            crop_checksum,
        )
    )
    return hashlib.sha256(logical.encode()).hexdigest()


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, list[dict[str, object]]]:
    crop_root = tmp_path / "crops"
    crop_root.mkdir()
    source_checksum = "a" * 64
    samples: list[dict[str, object]] = []
    contents: list[bytes] = []
    for index, color in enumerate(((200, 20, 20), (200, 20, 20), (20, 20, 200))):
        row, column = divmod(index, 5)
        relative = f"cells/cell-{index}.png"
        path = crop_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (90, 90), color).save(path, format="PNG")
        content = path.read_bytes()
        contents.append(content)
        checksum = hashlib.sha256(content).hexdigest()
        samples.append(
            {
                "boardIndex": 0,
                "cellIndex": index,
                "columnIndex": column,
                "cropChecksumSha256": checksum,
                "cropRelativePath": relative,
                "rowIndex": row,
                "sampleId": _sample_id(
                    source_checksum=source_checksum,
                    sequence_number=1,
                    board_index=0,
                    row_index=row,
                    column_index=column,
                    crop_checksum=checksum,
                ),
                "sequenceNumber": 1,
                "sourceGroup": "fixture-group",
                "sourceImageChecksumSha256": source_checksum,
                "sourceImageId": "fixture-image",
                "sourceImageRelativePath": "source.jpg",
            }
        )
    assert contents[0] == contents[1]
    inventory = {
        "boardCount": 1,
        "cellHeight": 90,
        "cellWidth": 90,
        "corpusId": "review-fixture",
        "corpusManifestSha256": "b" * 64,
        "cropReportSha256": "c" * 64,
        "cropperVersion": "board-cell-crops-v1",
        "goldenAnnotationsSha256": "d" * 64,
        "inventoryVersion": INVENTORY_VERSION,
        "sampleCount": 3,
        "samples": samples,
        "schemaVersion": 1,
        "sourceGroupCount": 1,
        "sourceGroups": ["fixture-group"],
        "status": "ready",
    }
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_bytes(_json_bytes(inventory))
    labels_path = tmp_path / "labels" / "reviewed.json"
    return inventory_path, crop_root, labels_path, samples


def _configured(
    tmp_path: Path,
) -> tuple[BootstrapSymbolReview, Path, list[dict[str, object]]]:
    inventory, crop_root, labels, samples = _fixture(tmp_path)
    review = BootstrapSymbolReview(inventory, crop_root, labels)
    changed = review.configure(
        game_code="blazing-hot",
        reviewed_by="owner",
        symbol_codes=["seven", "star"],
    )
    assert changed
    return review, labels, samples


def test_configuration_persists_valid_deterministic_source(tmp_path: Path) -> None:
    review, labels_path, _ = _configured(tmp_path)
    first = labels_path.read_bytes()
    configuration = review.state()["configuration"]

    assert (
        review.configure(
            game_code="blazing-hot",
            reviewed_by="owner",
            symbol_codes=["star", "seven"],
        )
        is False
    )
    assert labels_path.read_bytes() == first
    _, source = load_reviewed_label_source(labels_path)
    assert source.game_code == "blazing-hot"
    assert source.review_revision == 1
    assert [symbol.symbol_code for symbol in source.symbols] == ["seven", "star"]
    assert configuration["gameId"].startswith("bootstrap-")


def test_decision_is_idempotent_and_resumes(tmp_path: Path) -> None:
    review, labels_path, samples = _configured(tmp_path)
    sample_id = str(samples[0]["sampleId"])

    assert (
        review.decide(
            sample_id=sample_id,
            decision="accepted",
            symbol_code="seven",
        )
        == 1
    )
    revision = review.state()["configuration"]["reviewRevision"]
    assert (
        review.decide(
            sample_id=sample_id,
            decision="accepted",
            symbol_code="seven",
        )
        == 0
    )
    assert review.state()["configuration"]["reviewRevision"] == revision

    resumed = BootstrapSymbolReview(review.inventory_path, review.crop_root, labels_path)
    assert resumed.progress() == {
        "accepted": 1,
        "pending": 2,
        "perSymbol": [
            {"sampleCount": 1, "symbolCode": "seven"},
            {"sampleCount": 0, "symbolCode": "star"},
        ],
        "rejected": 0,
        "total": 3,
    }


def test_decision_can_apply_to_identical_bytes(tmp_path: Path) -> None:
    review, _, samples = _configured(tmp_path)

    changed = review.decide(
        sample_id=str(samples[0]["sampleId"]),
        decision="accepted",
        symbol_code="seven",
        apply_to_identical=True,
    )

    assert changed == 2
    assert review.progress()["accepted"] == 2
    accepted = review.state(status="accepted")
    assert accepted["totalFiltered"] == 2
    assert {sample["symbolCode"] for sample in accepted["samples"]} == {"seven"}


def test_conflicting_label_for_identical_bytes_is_blocked(tmp_path: Path) -> None:
    review, _, samples = _configured(tmp_path)
    review.decide(
        sample_id=str(samples[0]["sampleId"]),
        decision="accepted",
        symbol_code="seven",
    )

    with pytest.raises(SymbolReviewError) as error:
        review.decide(
            sample_id=str(samples[1]["sampleId"]),
            decision="accepted",
            symbol_code="star",
        )

    assert error.value.code == "SYMBOL_REVIEW_IDENTICAL_CONFLICT"


def test_used_symbol_cannot_be_removed(tmp_path: Path) -> None:
    review, _, samples = _configured(tmp_path)
    review.decide(
        sample_id=str(samples[0]["sampleId"]),
        decision="accepted",
        symbol_code="seven",
    )

    with pytest.raises(SymbolReviewError) as error:
        review.configure(
            game_code="blazing-hot",
            reviewed_by="owner",
            symbol_codes=["star"],
        )

    assert error.value.code == "SYMBOL_REVIEW_SYMBOL_IN_USE"


def test_reject_clear_and_filters_preserve_pending(tmp_path: Path) -> None:
    review, _, samples = _configured(tmp_path)
    sample_id = str(samples[2]["sampleId"])

    assert review.decide(sample_id=sample_id, decision="rejected") == 1
    assert review.state(status="rejected")["totalFiltered"] == 1
    assert review.clear(sample_id=sample_id) == 1
    assert review.clear(sample_id=sample_id) == 0
    assert review.state(status="pending")["totalFiltered"] == 3


def test_crop_is_reverified_and_drift_is_blocked(tmp_path: Path) -> None:
    review, _, samples = _configured(tmp_path)
    sample_id = str(samples[2]["sampleId"])
    path, checksum = review.resolve_crop(sample_id)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == checksum
    Image.new("RGB", (90, 90), (1, 2, 3)).save(path, format="PNG")

    with pytest.raises(SymbolReviewError) as error:
        review.resolve_crop(sample_id)

    assert error.value.code == "SYMBOL_REVIEW_CROP_DRIFT"


def test_output_cannot_modify_crop_root(tmp_path: Path) -> None:
    inventory, crop_root, _, _ = _fixture(tmp_path)

    with pytest.raises(SymbolReviewError) as error:
        BootstrapSymbolReview(
            inventory,
            crop_root,
            crop_root / "labels.json",
        )

    assert error.value.code == "SYMBOL_REVIEW_OUTPUT_IN_CROP_ROOT"
