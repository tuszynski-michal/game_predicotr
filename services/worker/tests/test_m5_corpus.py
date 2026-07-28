from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from game_predictor_worker.images import CorpusValidationError, validate_corpus


def _jpeg(width: int = 16, height: int = 12) -> bytes:
    payload = b"\x08" + height.to_bytes(2, "big") + width.to_bytes(2, "big") + b"\x01\x01\x11\x00"
    return b"\xff\xd8\xff\xc0" + (len(payload) + 2).to_bytes(2, "big") + payload + b"\xff\xd9"


def _write_contract(
    root: Path,
    *,
    checksum_override: str | None = None,
    complete: bool = False,
) -> tuple[Path, Path]:
    image_root = root / "images"
    image_root.mkdir()
    image_bytes = _jpeg()
    (image_root / "source.jpg").write_bytes(image_bytes)
    manifest = {
        "schemaVersion": 1,
        "corpusId": "test-corpus",
        "status": "accepted" if complete else "provisional",
        "rootPath": "images",
        "imageCount": 1,
        "sourceGroupCount": 1,
        "images": [
            {
                "id": "m5-img-001",
                "relativePath": "source.jpg",
                "sha256": checksum_override or hashlib.sha256(image_bytes).hexdigest(),
                "sizeBytes": len(image_bytes),
                "width": 16,
                "height": 12,
                "sourceGroup": "source-1",
                "split": "golden",
                "expectedBoardCount": 9,
                "expectedSequenceStart": 1,
                "expectedSequenceEnd": 9,
            }
        ],
    }
    annotation: dict[str, object] = {
        "imageId": "m5-img-001",
        "status": "complete" if complete else "sequence_only",
        "sequenceNumbers": list(range(1, 10)),
    }
    if complete:
        annotation["pageQuad"] = [
            {"x": 0, "y": 0},
            {"x": 16, "y": 0},
            {"x": 16, "y": 12},
            {"x": 0, "y": 12},
        ]
        annotation["boards"] = [
            {
                "positionIndex": position,
                "sequenceNumber": position + 1,
                "boardQuad": [
                    {"x": 0, "y": 0},
                    {"x": 8, "y": 0},
                    {"x": 8, "y": 6},
                    {"x": 0, "y": 6},
                ],
                "numberBox": {"x": 0, "y": 6, "width": 4, "height": 2},
            }
            for position in range(9)
        ]
    annotations = {
        "schemaVersion": 1,
        "corpusId": "test-corpus",
        "coordinateSystem": "source-image-pixels-before-normalization",
        "images": [annotation],
    }
    manifest_path = root / "manifest.json"
    annotations_path = root / "annotations.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    annotations_path.write_text(json.dumps(annotations), encoding="utf-8")
    return manifest_path, annotations_path


def test_validates_provisional_sequence_only_corpus(tmp_path: Path) -> None:
    manifest, annotations = _write_contract(tmp_path)

    report = validate_corpus(tmp_path, manifest, annotations)

    assert report.image_count == 1
    assert report.pending_annotation_ids == ("m5-img-001",)
    assert report.ready_for_geometry_benchmark is False


def test_accepts_complete_geometry_and_marks_ready(tmp_path: Path) -> None:
    manifest, annotations = _write_contract(tmp_path, complete=True)

    report = validate_corpus(tmp_path, manifest, annotations)

    assert report.complete_annotation_count == 1
    assert report.pending_annotation_ids == ()
    assert report.ready_for_geometry_benchmark is True


def test_rejects_changed_source_bytes(tmp_path: Path) -> None:
    manifest, annotations = _write_contract(tmp_path, checksum_override="0" * 64)

    with pytest.raises(CorpusValidationError) as error:
        validate_corpus(tmp_path, manifest, annotations)

    assert error.value.code == "M5_CORPUS_CHECKSUM_MISMATCH"


def test_rejects_geometry_outside_source_image(tmp_path: Path) -> None:
    manifest, annotations = _write_contract(tmp_path, complete=True)
    contract = json.loads(annotations.read_text(encoding="utf-8"))
    contract["images"][0]["boards"][0]["numberBox"]["x"] = 15
    annotations.write_text(json.dumps(contract), encoding="utf-8")

    with pytest.raises(CorpusValidationError) as error:
        validate_corpus(tmp_path, manifest, annotations)

    assert error.value.code == "M5_CORPUS_GEOMETRY_OUT_OF_BOUNDS"


def test_rejects_sequence_annotation_mismatch(tmp_path: Path) -> None:
    manifest, annotations = _write_contract(tmp_path)
    contract = json.loads(annotations.read_text(encoding="utf-8"))
    contract["images"][0]["sequenceNumbers"][-1] = 10
    annotations.write_text(json.dumps(contract), encoding="utf-8")

    with pytest.raises(CorpusValidationError) as error:
        validate_corpus(tmp_path, manifest, annotations)

    assert error.value.code == "M5_CORPUS_SEQUENCE_MISMATCH"
