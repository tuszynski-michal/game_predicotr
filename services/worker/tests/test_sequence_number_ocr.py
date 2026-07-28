from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

import cv2
import numpy as np
import pytest
from game_predictor_worker.images.geometry import DETECTOR_VERSION, Point, Quad
from game_predictor_worker.images.sequence_ocr import (
    NUMBER_CROP_HEIGHT,
    NUMBER_CROP_WIDTH,
    PaddleSequenceNumberRecognizer,
    Recognition,
    SequenceArtifact,
    SequenceOcrError,
    extract_sequence_number_crop,
    run_sequence_ocr_corpus,
    validate_sequence_continuity,
)
from numpy.typing import NDArray
from PIL import Image


class FakeRecognizer:
    version = "fake-sequence-ocr-v1"
    model_name = "fake-digits"
    model_fingerprint = "a" * 64
    model_files: Mapping[str, str] = {"model.bin": "b" * 64}
    runtime_name = "fake-cpu"
    runtime_version = "1.0"

    def __init__(self, values: list[str]) -> None:
        self._values = iter(values)

    def recognize(self, rgb_image: NDArray[np.uint8]) -> Recognition:
        assert rgb_image.ndim == 3
        return Recognition(next(self._values), 0.9)


def _board_quad() -> Quad:
    return (
        Point(80, 80),
        Point(280, 80),
        Point(280, 180),
        Point(80, 180),
    )


def _artifact(number: int | None, *, raw_text: str | None = None) -> SequenceArtifact:
    text = str(number) if raw_text is None and number is not None else raw_text or ""
    return SequenceArtifact(
        image_id="image",
        source_checksum_sha256="a" * 64,
        position_index=0,
        expected_number=number or 0,
        crop_quad=((0.0, 0.0),) * 4,
        raw_crop_relative_path="raw.png",
        raw_crop_checksum_sha256="b" * 64,
        processed_crop_relative_path="foreground.png",
        processed_crop_checksum_sha256="c" * 64,
        processed_crop_width=20,
        processed_crop_height=10,
        raw_text=text,
        normalized_number=number,
        confidence=0.8,
        exact_match=True,
        review_reasons=(),
    )


def _write_json(path: Path, value: object) -> bytes:
    content = (json.dumps(value, sort_keys=True) + "\n").encode()
    path.write_bytes(content)
    return content


def _runner_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    normalization_root = tmp_path / "normalization"
    relative = "image-normalization-v1/aa/source/normalized.png"
    normalized_path = normalization_root / Path(*PurePosixPath(relative).parts)
    normalized_path.parent.mkdir(parents=True)
    image = np.full((400, 400, 3), (20, 40, 120), dtype=np.uint8)
    cv2.putText(
        image,
        "123",
        (135, 210),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    Image.fromarray(image).save(normalized_path, format="PNG")
    normalized_bytes = normalized_path.read_bytes()
    source_checksum = "a" * 64
    normalization = {
        "images": [
            {
                "normalizedChecksumSha256": hashlib.sha256(normalized_bytes).hexdigest(),
                "normalizedRelativePath": relative,
                "sourceChecksumSha256": source_checksum,
            }
        ],
        "normalizationVersion": "image-normalization-v1",
        "status": "clean",
    }
    normalization_path = tmp_path / "normalization-report.json"
    normalization_bytes = _write_json(normalization_path, normalization)
    boards = [
        {
            "positionIndex": index,
            "quad": [
                {"x": 80, "y": 80},
                {"x": 280, "y": 80},
                {"x": 280, "y": 180},
                {"x": 80, "y": 180},
            ],
        }
        for index in range(9)
    ]
    detection = {
        "detectorVersion": DETECTOR_VERSION,
        "normalizationReportSha256": hashlib.sha256(normalization_bytes).hexdigest(),
        "detections": [
            {
                "normalizedRelativePath": relative,
                "sourceChecksumSha256": source_checksum,
                "result": {"boards": boards, "status": "detected"},
            }
        ],
    }
    detection_path = tmp_path / "detection-report.json"
    _write_json(detection_path, detection)
    corpus_path = tmp_path / "corpus.json"
    _write_json(
        corpus_path,
        {
            "corpusId": "test-corpus",
            "images": [{"id": "image-1", "sha256": source_checksum}],
        },
    )
    golden_path = tmp_path / "golden.json"
    _write_json(
        golden_path,
        {
            "corpusId": "test-corpus",
            "images": [{"imageId": "image-1", "sequenceNumbers": list(range(1, 10))}],
        },
    )
    return (
        corpus_path,
        golden_path,
        normalization_path,
        detection_path,
        normalization_root,
    )


@pytest.mark.parametrize(
    ("raw_text", "expected"),
    [("123", 123), ("", None), ("12a", None), (" 12", None)],
)
def test_recognition_normalizes_only_complete_digit_text(
    raw_text: str,
    expected: int | None,
) -> None:
    assert Recognition(raw_text, 0.5).normalized_number == expected


def test_sequence_crop_is_deterministic_and_does_not_mutate_source() -> None:
    image = np.full((400, 400, 3), (20, 40, 120), dtype=np.uint8)
    cv2.putText(
        image,
        "17",
        (145, 210),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    before = image.copy()

    first = extract_sequence_number_crop(image, _board_quad())
    second = extract_sequence_number_crop(image, _board_quad())

    assert first[0].shape == (NUMBER_CROP_HEIGHT, NUMBER_CROP_WIDTH, 3)
    assert first[1].ndim == 3 and first[1].size > 0
    assert np.array_equal(first[0], second[0])
    assert np.array_equal(first[1], second[1])
    assert np.array_equal(first[2], second[2])
    assert np.array_equal(image, before)


def test_sequence_crop_rejects_geometry_outside_image() -> None:
    image = np.zeros((190, 300, 3), dtype=np.uint8)

    with pytest.raises(SequenceOcrError) as raised:
        extract_sequence_number_crop(image, _board_quad())

    assert raised.value.code == "SEQUENCE_CROP_OUT_OF_BOUNDS"


def test_continuity_flags_errors_without_changing_recognition() -> None:
    original = (
        _artifact(10),
        _artifact(10),
        _artifact(13),
        _artifact(12),
        _artifact(None, raw_text="x"),
    )

    validated = validate_sequence_continuity(original)

    assert validated[1].review_reasons == ("OCR_CONTINUITY_DUPLICATE",)
    assert validated[2].review_reasons == ("OCR_CONTINUITY_GAP",)
    assert validated[3].review_reasons == ("OCR_CONTINUITY_CONFLICT",)
    assert validated[4].review_reasons == ("OCR_UNRECOGNIZED",)
    assert [item.raw_text for item in validated] == [item.raw_text for item in original]
    assert [item.normalized_number for item in validated] == [
        item.normalized_number for item in original
    ]


def test_missing_local_model_has_stable_error_without_runtime_initialization(
    tmp_path: Path,
) -> None:
    with pytest.raises(SequenceOcrError) as raised:
        PaddleSequenceNumberRecognizer(tmp_path / "missing-model")

    assert raised.value.code == "SEQUENCE_OCR_MODEL_NOT_FOUND"


def test_corpus_runner_is_complete_and_reuses_identical_artifacts(
    tmp_path: Path,
) -> None:
    inputs = _runner_inputs(tmp_path)
    artifacts = tmp_path / "ocr"
    first = run_sequence_ocr_corpus(
        *inputs,
        tmp_path / "unused-model",
        artifacts,
        recognizer=FakeRecognizer([str(value) for value in range(1, 10)]),
    )
    referenced = [
        artifacts / Path(*PurePosixPath(path).parts)
        for result in first.results
        for path in (
            result.raw_crop_relative_path,
            result.processed_crop_relative_path,
        )
    ]
    mtimes = [path.stat().st_mtime_ns for path in referenced]

    second = run_sequence_ocr_corpus(
        *inputs,
        tmp_path / "unused-model",
        artifacts,
        recognizer=FakeRecognizer([str(value) for value in range(1, 10)]),
    )
    payload = first.to_dict()

    assert first.to_json_bytes() == second.to_json_bytes()
    assert payload["positionCount"] == 9
    assert payload["exactAccuracy"] == 1.0
    assert payload["reviewCount"] == 0
    assert payload["continuityConflictCount"] == 0
    assert all(path.is_file() for path in referenced)
    assert [path.stat().st_mtime_ns for path in referenced] == mtimes


def test_corpus_runner_blocks_normalized_checksum_drift(tmp_path: Path) -> None:
    inputs = _runner_inputs(tmp_path)
    normalization_root = inputs[-1]
    normalized_path = next(normalization_root.rglob("normalized.png"))
    normalized_path.write_bytes(b"drift")

    with pytest.raises(SequenceOcrError) as raised:
        run_sequence_ocr_corpus(
            *inputs,
            tmp_path / "unused-model",
            tmp_path / "ocr",
            recognizer=FakeRecognizer([str(value) for value in range(1, 10)]),
        )

    assert raised.value.code == "SEQUENCE_OCR_NORMALIZED_CHECKSUM_MISMATCH"
