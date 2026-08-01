"""Local sequence-number crops, OCR port, and continuity validation."""

from __future__ import annotations

import hashlib
import importlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from importlib.metadata import version
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, cast

import cv2
import numpy as np
import yaml  # type: ignore[import-untyped]
from numpy.typing import NDArray

from .geometry import DETECTOR_VERSION, Point, Quad

OCR_VERSION = "sequence-number-ocr-v1"
MODEL_NAME = "en_PP-OCRv5_mobile_rec"
MAX_BOARD_COUNT = 9
NUMBER_CROP_WIDTH = 192
NUMBER_CROP_HEIGHT = 64
NUMBER_X_START = 0.25
NUMBER_X_END = 0.75
NUMBER_Y_START = 0.02
NUMBER_Y_END = 0.38
MODEL_INPUT_HEIGHT = 48
MODEL_INPUT_WIDTH = 320
MODEL_FILES = ("inference.json", "inference.pdiparams", "inference.yml")
PREPROCESSING_VERSION = "bright-component-tight-v1"
RAW_WARP_PREPROCESSING_VERSION = "raw-warp-v1"
DIGITS = re.compile(r"^[0-9]+$")


class SequenceOcrError(ValueError):
    """Stable fatal error for OCR orchestration."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class Recognition:
    raw_text: str
    confidence: float

    @property
    def normalized_number(self) -> int | None:
        if not DIGITS.fullmatch(self.raw_text):
            return None
        return int(self.raw_text)


class SequenceNumberRecognizer(Protocol):
    """Replaceable recognition-only OCR port."""

    version: str
    model_name: str
    model_fingerprint: str
    model_files: Mapping[str, str]
    runtime_name: str
    runtime_version: str

    def recognize(self, rgb_image: NDArray[np.uint8]) -> Recognition:
        """Recognize a single pre-cropped text line without using continuity."""


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _model_identity(model_root: Path) -> tuple[dict[str, str], str]:
    try:
        root = model_root.resolve(strict=True)
    except OSError as error:
        raise SequenceOcrError(
            "SEQUENCE_OCR_MODEL_NOT_FOUND",
            "Local OCR model directory does not exist.",
        ) from error
    if not root.is_dir():
        raise SequenceOcrError(
            "SEQUENCE_OCR_MODEL_NOT_DIRECTORY",
            "Local OCR model path must be a directory.",
        )
    checksums: dict[str, str] = {}
    fingerprint = hashlib.sha256()
    for name in MODEL_FILES:
        path = root / name
        try:
            content = path.read_bytes()
        except OSError as error:
            raise SequenceOcrError(
                "SEQUENCE_OCR_MODEL_INCOMPLETE",
                f"Local OCR model is missing {name}.",
            ) from error
        checksum = _sha256_bytes(content)
        checksums[name] = checksum
        fingerprint.update(name.encode())
        fingerprint.update(b"\0")
        fingerprint.update(bytes.fromhex(checksum))
    return checksums, fingerprint.hexdigest()


def _characters_from_model(model_root: Path) -> tuple[str, ...]:
    try:
        config_value: Any = yaml.safe_load((model_root / "inference.yml").read_text("utf-8"))
        config = cast(Mapping[str, object], config_value)
        post_process = cast(Mapping[str, object], config["PostProcess"])
        characters = post_process["character_dict"]
    except (OSError, KeyError, TypeError, yaml.YAMLError) as error:
        raise SequenceOcrError(
            "SEQUENCE_OCR_MODEL_CONFIG_INVALID",
            "OCR model character dictionary cannot be read.",
        ) from error
    if not isinstance(characters, Sequence) or isinstance(characters, str | bytes):
        raise SequenceOcrError(
            "SEQUENCE_OCR_MODEL_CONFIG_INVALID",
            "OCR character dictionary must be an array.",
        )
    result = tuple(str(character) for character in characters)
    if result[:10] != tuple("0123456789"):
        raise SequenceOcrError(
            "SEQUENCE_OCR_MODEL_CONFIG_INVALID",
            "OCR character dictionary must begin with digits 0-9.",
        )
    return (*result, " ")


class PaddleSequenceNumberRecognizer:
    """Recognition-only PP-OCRv5 adapter using local Paddle Inference files."""

    version = OCR_VERSION
    runtime_name = "paddlepaddle-cpu"

    def __init__(self, model_root: Path, *, model_name: str = MODEL_NAME) -> None:
        if not model_name or model_name.strip() != model_name:
            raise SequenceOcrError(
                "SEQUENCE_OCR_MODEL_NAME_INVALID",
                "OCR model name must be a non-empty trimmed string.",
            )
        self.model_name = model_name
        self.runtime_version = version("paddlepaddle")
        self._model_root = model_root.resolve()
        model_files, self.model_fingerprint = _model_identity(self._model_root)
        self.model_files: Mapping[str, str] = model_files
        self._characters = _characters_from_model(self._model_root)
        try:
            inference = importlib.import_module("paddle.inference")
            config = inference.Config(
                str(self._model_root / "inference.json"),
                str(self._model_root / "inference.pdiparams"),
            )
            config.disable_gpu()
            config.set_cpu_math_library_num_threads(1)
            config.disable_glog_info()
            self._predictor: Any = inference.create_predictor(config)
        except (ImportError, RuntimeError) as error:
            raise SequenceOcrError(
                "SEQUENCE_OCR_RUNTIME_UNAVAILABLE",
                "PaddlePaddle CPU inference cannot initialize the local model.",
            ) from error
        input_names = self._predictor.get_input_names()
        output_names = self._predictor.get_output_names()
        if len(input_names) != 1 or len(output_names) != 1:
            raise SequenceOcrError(
                "SEQUENCE_OCR_MODEL_IO_UNSUPPORTED",
                "OCR model must expose exactly one input and one output.",
            )
        self._input_name = str(input_names[0])
        self._output_name = str(output_names[0])

    def recognize(self, rgb_image: NDArray[np.uint8]) -> Recognition:
        return self.recognize_many((rgb_image,))[0]

    def recognize_many(
        self,
        rgb_images: Sequence[NDArray[np.uint8]],
    ) -> tuple[Recognition, ...]:
        """Recognize one page of sequence crops in one CPU inference call."""

        if not rgb_images or len(rgb_images) > MAX_BOARD_COUNT:
            raise SequenceOcrError(
                "SEQUENCE_OCR_BATCH_INVALID",
                "Recognizer batch must contain between one and nine images.",
            )
        batch: NDArray[np.float32] = np.zeros(
            (len(rgb_images), 3, MODEL_INPUT_HEIGHT, MODEL_INPUT_WIDTH),
            dtype=np.float32,
        )
        for batch_index, rgb_image in enumerate(rgb_images):
            if rgb_image.ndim != 3 or rgb_image.shape[2] != 3 or rgb_image.dtype != np.uint8:
                raise SequenceOcrError(
                    "SEQUENCE_OCR_INVALID_IMAGE",
                    "Recognizer input must be an RGB uint8 image.",
                )
            height, width = rgb_image.shape[:2]
            resized_width = min(
                MODEL_INPUT_WIDTH,
                max(1, int(np.ceil(MODEL_INPUT_HEIGHT * width / height))),
            )
            bgr = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)
            resized = cv2.resize(
                bgr,
                (resized_width, MODEL_INPUT_HEIGHT),
                interpolation=cv2.INTER_LINEAR,
            )
            normalized = resized.astype(np.float32).transpose((2, 0, 1)) / 255.0
            batch[batch_index, :, :, :resized_width] = (normalized - 0.5) / 0.5
        input_handle = self._predictor.get_input_handle(self._input_name)
        input_handle.reshape(batch.shape)
        input_handle.copy_from_cpu(batch)
        self._predictor.run()
        output = cast(
            NDArray[np.float32],
            self._predictor.get_output_handle(self._output_name).copy_to_cpu(),
        )
        if output.ndim != 3 or output.shape[0] != len(rgb_images):
            raise SequenceOcrError(
                "SEQUENCE_OCR_MODEL_OUTPUT_INVALID",
                "OCR model output must have shape [batch, time, classes].",
            )
        if output.shape[2] != len(self._characters) + 1:
            raise SequenceOcrError(
                "SEQUENCE_OCR_MODEL_OUTPUT_INVALID",
                "OCR model class count differs from its character dictionary.",
            )
        return tuple(self._decode_output(item) for item in output)

    def _decode_output(self, output: NDArray[np.float32]) -> Recognition:
        digit_classes = output[:, :11]
        indices = np.argmax(digit_classes, axis=1)
        probabilities = np.max(digit_classes, axis=1)
        text: list[str] = []
        confidence_values: list[float] = []
        previous = -1
        for index, probability in zip(indices, probabilities, strict=True):
            class_index = int(index)
            if class_index != 0 and class_index != previous:
                character_index = class_index - 1
                if not 0 <= character_index < len(self._characters):
                    raise SequenceOcrError(
                        "SEQUENCE_OCR_MODEL_OUTPUT_INVALID",
                        "OCR model returned a class outside its dictionary.",
                    )
                text.append(self._characters[character_index])
                confidence_values.append(float(probability))
            previous = class_index
        return Recognition(
            raw_text="".join(text),
            confidence=round(
                float(np.mean(confidence_values)) if confidence_values else 0.0,
                6,
            ),
        )


def _interpolate(first: Point, second: Point, ratio: float) -> NDArray[np.float32]:
    return np.array(
        [
            first.x + (second.x - first.x) * ratio,
            first.y + (second.y - first.y) * ratio,
        ],
        dtype=np.float32,
    )


def sequence_number_quad(board_quad: Quad) -> NDArray[np.float32]:
    """Return TL/TR/BR/BL crop points below a detected board."""

    top_left, top_right, bottom_right, bottom_left = board_quad
    left_down = np.array(
        [bottom_left.x - top_left.x, bottom_left.y - top_left.y],
        dtype=np.float32,
    )
    right_down = np.array(
        [bottom_right.x - top_right.x, bottom_right.y - top_right.y],
        dtype=np.float32,
    )
    points: list[NDArray[np.float32]] = []
    for x_ratio, y_ratio in (
        (NUMBER_X_START, NUMBER_Y_START),
        (NUMBER_X_END, NUMBER_Y_START),
        (NUMBER_X_END, NUMBER_Y_END),
        (NUMBER_X_START, NUMBER_Y_END),
    ):
        base = _interpolate(bottom_left, bottom_right, x_ratio)
        down = left_down + (right_down - left_down) * np.float32(x_ratio)
        points.append(
            cast(
                NDArray[np.float32],
                (base + down * np.float32(y_ratio)).astype(np.float32),
            )
        )
    return np.stack(points)


def extract_sequence_number_crop(
    rgb_image: NDArray[np.uint8],
    board_quad: Quad,
) -> tuple[NDArray[np.uint8], NDArray[np.uint8], NDArray[np.float32]]:
    """Warp and preprocess one number line without mutating the source."""

    if rgb_image.ndim != 3 or rgb_image.shape[2] != 3 or rgb_image.dtype != np.uint8:
        raise SequenceOcrError(
            "SEQUENCE_CROP_INVALID_IMAGE",
            "Sequence crop input must be an RGB uint8 image.",
        )
    source = sequence_number_quad(board_quad)
    image_height, image_width = rgb_image.shape[:2]
    if (
        np.min(source[:, 0]) < 0
        or np.min(source[:, 1]) < 0
        or np.max(source[:, 0]) >= image_width
        or np.max(source[:, 1]) >= image_height
    ):
        raise SequenceOcrError(
            "SEQUENCE_CROP_OUT_OF_BOUNDS",
            "Sequence number crop extends outside the normalized image.",
        )
    destination = np.array(
        [
            [0, 0],
            [NUMBER_CROP_WIDTH - 1, 0],
            [NUMBER_CROP_WIDTH - 1, NUMBER_CROP_HEIGHT - 1],
            [0, NUMBER_CROP_HEIGHT - 1],
        ],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(source, destination)
    if not np.isfinite(matrix).all():
        raise SequenceOcrError(
            "SEQUENCE_CROP_TRANSFORM_INVALID",
            "Sequence number perspective transform is invalid.",
        )
    raw = cast(
        NDArray[np.uint8],
        cv2.warpPerspective(
            rgb_image,
            matrix,
            (NUMBER_CROP_WIDTH, NUMBER_CROP_HEIGHT),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        ),
    )
    gray = cv2.cvtColor(raw, cv2.COLOR_RGB2GRAY)
    _, bright = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )
    bright[:5, :] = 0
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(
        bright,
        connectivity=8,
    )
    foreground = np.zeros(bright.shape, dtype=np.uint8)
    for component in range(1, component_count):
        _, y, _, height, area = map(int, stats[component])
        if area >= 12 and height >= 5 and y > 2:
            foreground[labels == component] = 255
    y_values, x_values = np.nonzero(foreground)
    if len(x_values):
        left = max(0, int(np.min(x_values)) - 5)
        right = min(NUMBER_CROP_WIDTH, int(np.max(x_values)) + 6)
        top = max(0, int(np.min(y_values)) - 5)
        bottom = min(NUMBER_CROP_HEIGHT, int(np.max(y_values)) + 6)
        processed = raw[top:bottom, left:right].copy()
    else:
        processed = raw.copy()
    return raw, processed, source


@dataclass(frozen=True, slots=True)
class SequenceArtifact:
    image_id: str
    source_checksum_sha256: str
    position_index: int
    expected_number: int
    crop_quad: tuple[tuple[float, float], ...]
    raw_crop_relative_path: str
    raw_crop_checksum_sha256: str
    processed_crop_relative_path: str
    processed_crop_checksum_sha256: str
    processed_crop_width: int
    processed_crop_height: int
    raw_text: str
    normalized_number: int | None
    confidence: float
    exact_match: bool
    review_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "confidence": self.confidence,
            "cropQuad": [
                {"x": round(point[0], 6), "y": round(point[1], 6)} for point in self.crop_quad
            ],
            "exactMatch": self.exact_match,
            "expectedNumber": self.expected_number,
            "imageId": self.image_id,
            "normalizedNumber": self.normalized_number,
            "positionIndex": self.position_index,
            "processedCropChecksumSha256": self.processed_crop_checksum_sha256,
            "processedCropHeight": self.processed_crop_height,
            "processedCropRelativePath": self.processed_crop_relative_path,
            "processedCropWidth": self.processed_crop_width,
            "rawCropChecksumSha256": self.raw_crop_checksum_sha256,
            "rawCropHeight": NUMBER_CROP_HEIGHT,
            "rawCropRelativePath": self.raw_crop_relative_path,
            "rawCropWidth": NUMBER_CROP_WIDTH,
            "rawText": self.raw_text,
            "reviewReasons": list(self.review_reasons),
            "sourceChecksumSha256": self.source_checksum_sha256,
            "status": "recognized" if not self.review_reasons else "needs_review",
        }


@dataclass(frozen=True, slots=True)
class SequenceOcrReport:
    corpus_manifest_sha256: str
    golden_annotations_sha256: str
    normalization_report_sha256: str
    detection_report_sha256: str
    recognizer: SequenceNumberRecognizer
    preprocessing_version: str
    results: tuple[SequenceArtifact, ...]

    def to_dict(self) -> dict[str, object]:
        exact_count = sum(result.exact_match for result in self.results)
        review_count = sum(bool(result.review_reasons) for result in self.results)
        continuity_count = sum(
            any(reason.startswith("OCR_CONTINUITY_") for reason in result.review_reasons)
            for result in self.results
        )
        total = len(self.results)
        return {
            "continuityConflictCount": continuity_count,
            "corpusManifestSha256": self.corpus_manifest_sha256,
            "detectionReportSha256": self.detection_report_sha256,
            "exactAccuracy": round(exact_count / total, 6) if total else 0.0,
            "exactCount": exact_count,
            "goldenAnnotationsSha256": self.golden_annotations_sha256,
            "imageCount": len({result.image_id for result in self.results}),
            "modelFiles": dict(self.recognizer.model_files),
            "modelFingerprint": self.recognizer.model_fingerprint,
            "modelName": self.recognizer.model_name,
            "normalizationReportSha256": self.normalization_report_sha256,
            "positionCount": total,
            "preprocessingVersion": self.preprocessing_version,
            "proposedThresholdEvaluated": False,
            "recognizerVersion": self.recognizer.version,
            "runtimeName": self.recognizer.runtime_name,
            "runtimeVersion": self.recognizer.runtime_version,
            "decoderPolicy": "ctc-blank-plus-digits-0-9",
            "results": [result.to_dict() for result in self.results],
            "reviewCount": review_count,
            "schemaVersion": 1,
            "status": "measured",
            "unresolvedContinuityConflictRate": (
                round(continuity_count / total, 6) if total else 0.0
            ),
        }

    def to_json_bytes(self) -> bytes:
        return (
            json.dumps(
                self.to_dict(),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SequenceOcrError("SEQUENCE_OCR_REPORT_INVALID", f"{label} must be an object.")
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise SequenceOcrError("SEQUENCE_OCR_REPORT_INVALID", f"{label} must be an array.")
    return cast(Sequence[object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise SequenceOcrError(
            "SEQUENCE_OCR_REPORT_INVALID",
            f"{label} must be a non-empty string.",
        )
    return value


def _sha256(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise SequenceOcrError(
            "SEQUENCE_OCR_REPORT_INVALID",
            f"{label} must be a lowercase SHA-256.",
        )
    return text


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise SequenceOcrError(
            "SEQUENCE_OCR_REPORT_INVALID",
            f"{label} must be an integer.",
        )
    return value


def _load_json(path: Path, code: str, message: str) -> tuple[bytes, Mapping[str, object]]:
    try:
        content = path.read_bytes()
        value: Any = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise SequenceOcrError(code, message) from error
    return content, _mapping(value, path.name)


def _safe_path(root: Path, value: object, label: str) -> tuple[str, Path]:
    text = _text(value, label)
    relative = PurePosixPath(text)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise SequenceOcrError(
            "SEQUENCE_OCR_UNSAFE_ARTIFACT_PATH",
            f"{label} must be a safe relative POSIX path.",
        )
    try:
        resolved = (root / Path(*relative.parts)).resolve(strict=True)
    except OSError as error:
        raise SequenceOcrError(
            "SEQUENCE_OCR_NORMALIZED_IMAGE_UNREADABLE",
            f"{label} cannot be resolved.",
        ) from error
    if not resolved.is_relative_to(root):
        raise SequenceOcrError(
            "SEQUENCE_OCR_UNSAFE_ARTIFACT_PATH",
            f"{label} escapes its artifact root.",
        )
    return text, resolved


def _point(value: object, label: str) -> Point:
    item = _mapping(value, label)
    return Point(
        _integer(item.get("x"), f"{label}.x"),
        _integer(item.get("y"), f"{label}.y"),
    )


def _boards(
    value: Mapping[str, object],
    label: str,
) -> tuple[tuple[int, Quad], ...]:
    if value.get("status") != "detected":
        raise SequenceOcrError(
            "SEQUENCE_OCR_DETECTION_NEEDS_REVIEW",
            "Sequence OCR requires a complete page detection.",
        )
    result: list[tuple[int, Quad]] = []
    for index, board_value in enumerate(_sequence(value.get("boards"), f"{label}.boards")):
        board = _mapping(board_value, f"{label}.boards[{index}]")
        points = _sequence(board.get("quad"), f"{label}.boards[{index}].quad")
        if len(points) != 4:
            raise SequenceOcrError(
                "SEQUENCE_OCR_REPORT_INVALID",
                "Every board quad must contain four points.",
            )
        result.append(
            (
                _integer(
                    board.get("positionIndex"),
                    f"{label}.boards[{index}].positionIndex",
                ),
                cast(
                    Quad,
                    tuple(
                        _point(point, f"{label}.boards[{index}].quad[{point_index}]")
                        for point_index, point in enumerate(points)
                    ),
                ),
            )
        )
    if not 1 <= len(result) <= MAX_BOARD_COUNT or [item[0] for item in result] != list(
        range(len(result))
    ):
        raise SequenceOcrError(
            "SEQUENCE_OCR_BOARD_SEQUENCE_INVALID",
            "Sequence OCR requires 1-9 contiguous row-major board indices from zero.",
        )
    return tuple(result)


def _encode_png(rgb: NDArray[np.uint8]) -> bytes:
    encoded, buffer = cv2.imencode(
        ".png",
        cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
        [cv2.IMWRITE_PNG_COMPRESSION, 6],
    )
    if not encoded:
        raise SequenceOcrError(
            "SEQUENCE_OCR_CROP_ENCODE_FAILED",
            "Sequence crop cannot be encoded.",
        )
    return bytes(buffer)


def _write_immutable(path: Path, content: bytes) -> None:
    if path.exists():
        try:
            existing = path.read_bytes()
        except OSError as error:
            raise SequenceOcrError(
                "SEQUENCE_OCR_ARTIFACT_UNREADABLE",
                "Existing OCR artifact cannot be read.",
            ) from error
        if existing != content:
            raise SequenceOcrError(
                "SEQUENCE_OCR_ARTIFACT_COLLISION",
                "Existing OCR artifact has different content.",
            )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    except OSError as error:
        raise SequenceOcrError(
            "SEQUENCE_OCR_ARTIFACT_WRITE_FAILED",
            "OCR artifact cannot be written.",
        ) from error
    finally:
        if temporary.exists():
            temporary.unlink()


def _artifact(root: Path, relative: str, rgb: NDArray[np.uint8]) -> str:
    content = _encode_png(rgb)
    _write_immutable(root / Path(*PurePosixPath(relative).parts), content)
    return _sha256_bytes(content)


def validate_sequence_continuity(
    results: Sequence[SequenceArtifact],
) -> tuple[SequenceArtifact, ...]:
    validated: list[SequenceArtifact] = []
    previous: SequenceArtifact | None = None
    for result in results:
        reasons = list(result.review_reasons)
        if result.normalized_number is None:
            reasons.append("OCR_UNRECOGNIZED")
        if (
            previous is not None
            and previous.normalized_number is not None
            and result.normalized_number is not None
            and result.normalized_number != previous.normalized_number + 1
        ):
            if result.normalized_number == previous.normalized_number:
                reasons.append("OCR_CONTINUITY_DUPLICATE")
            elif result.normalized_number > previous.normalized_number + 1:
                reasons.append("OCR_CONTINUITY_GAP")
            else:
                reasons.append("OCR_CONTINUITY_CONFLICT")
        validated.append(replace(result, review_reasons=tuple(reasons)))
        previous = result
    return tuple(validated)


def run_sequence_ocr_corpus(
    corpus_manifest_path: Path,
    golden_annotations_path: Path,
    normalization_report_path: Path,
    detection_report_path: Path,
    normalization_root: Path,
    model_root: Path,
    artifact_root: Path,
    *,
    recognizer: SequenceNumberRecognizer | None = None,
    recognition_input_policy: str = PREPROCESSING_VERSION,
) -> SequenceOcrReport:
    """Run recognition in corpus order and measure against independent labels."""

    if recognition_input_policy not in {
        PREPROCESSING_VERSION,
        RAW_WARP_PREPROCESSING_VERSION,
    }:
        raise SequenceOcrError(
            "SEQUENCE_OCR_PREPROCESSING_UNSUPPORTED",
            "Recognition input policy is not supported.",
        )
    corpus_bytes, corpus = _load_json(
        corpus_manifest_path,
        "SEQUENCE_OCR_CORPUS_INVALID",
        "Corpus manifest cannot be read.",
    )
    golden_bytes, golden = _load_json(
        golden_annotations_path,
        "SEQUENCE_OCR_GOLDEN_INVALID",
        "Golden annotations cannot be read.",
    )
    normalization_bytes, normalization = _load_json(
        normalization_report_path,
        "SEQUENCE_OCR_NORMALIZATION_INVALID",
        "Normalization report cannot be read.",
    )
    detection_bytes, detection = _load_json(
        detection_report_path,
        "SEQUENCE_OCR_DETECTION_INVALID",
        "Detection report cannot be read.",
    )
    corpus_id = _text(corpus.get("corpusId"), "corpusId")
    if golden.get("corpusId") != corpus_id:
        raise SequenceOcrError(
            "SEQUENCE_OCR_GOLDEN_MISMATCH",
            "Golden annotations use a different corpus.",
        )
    if (
        normalization.get("normalizationVersion") != "image-normalization-v1"
        or normalization.get("status") != "clean"
    ):
        raise SequenceOcrError(
            "SEQUENCE_OCR_NORMALIZATION_INVALID",
            "A clean image-normalization-v1 report is required.",
        )
    normalization_sha = _sha256_bytes(normalization_bytes)
    if (
        detection.get("detectorVersion") != DETECTOR_VERSION
        or detection.get("normalizationReportSha256") != normalization_sha
    ):
        raise SequenceOcrError(
            "SEQUENCE_OCR_DETECTION_DRIFT",
            "Detection report does not match normalization input.",
        )
    try:
        normalization_base = normalization_root.resolve(strict=True)
    except OSError as error:
        raise SequenceOcrError(
            "SEQUENCE_OCR_NORMALIZATION_ROOT_NOT_FOUND",
            "Normalization artifact root does not exist.",
        ) from error
    if not normalization_base.is_dir():
        raise SequenceOcrError(
            "SEQUENCE_OCR_NORMALIZATION_ROOT_NOT_DIRECTORY",
            "Normalization artifact root must be a directory.",
        )
    output_base = artifact_root.resolve()
    if output_base == normalization_base or output_base.is_relative_to(normalization_base):
        raise SequenceOcrError(
            "SEQUENCE_OCR_OUTPUT_IN_NORMALIZATION_ROOT",
            "OCR artifacts must use a separate root.",
        )

    normalization_by_source: dict[str, Mapping[str, object]] = {}
    for index, value in enumerate(_sequence(normalization.get("images"), "images")):
        item = _mapping(value, f"images[{index}]")
        checksum = _sha256(
            item.get("sourceChecksumSha256"),
            f"images[{index}].sourceChecksumSha256",
        )
        if checksum in normalization_by_source:
            raise SequenceOcrError(
                "SEQUENCE_OCR_REPORT_INVALID",
                "Normalization report contains a duplicate source checksum.",
            )
        normalization_by_source[checksum] = item
    detection_by_source: dict[str, Mapping[str, object]] = {}
    for index, value in enumerate(_sequence(detection.get("detections"), "detections")):
        item = _mapping(value, f"detections[{index}]")
        checksum = _sha256(
            item.get("sourceChecksumSha256"),
            f"detections[{index}].sourceChecksumSha256",
        )
        if checksum in detection_by_source:
            raise SequenceOcrError(
                "SEQUENCE_OCR_REPORT_INVALID",
                "Detection report contains a duplicate source checksum.",
            )
        detection_by_source[checksum] = item
    golden_by_id: dict[str, Mapping[str, object]] = {}
    for index, value in enumerate(_sequence(golden.get("images"), "golden.images")):
        item = _mapping(value, f"golden.images[{index}]")
        image_id = _text(item.get("imageId"), f"golden.images[{index}].imageId")
        if image_id in golden_by_id:
            raise SequenceOcrError(
                "SEQUENCE_OCR_REPORT_INVALID",
                "Golden annotations contain a duplicate image ID.",
            )
        golden_by_id[image_id] = item
    implementation = recognizer or PaddleSequenceNumberRecognizer(model_root)
    results: list[SequenceArtifact] = []
    for image_index, value in enumerate(_sequence(corpus.get("images"), "corpus.images")):
        corpus_image = _mapping(value, f"corpus.images[{image_index}]")
        image_id = _text(corpus_image.get("id"), f"corpus.images[{image_index}].id")
        source_checksum = _sha256(
            corpus_image.get("sha256"),
            f"corpus.images[{image_index}].sha256",
        )
        if (
            source_checksum not in normalization_by_source
            or source_checksum not in detection_by_source
        ):
            raise SequenceOcrError(
                "SEQUENCE_OCR_UPSTREAM_IMAGE_MISSING",
                "Corpus image is missing from an upstream report.",
            )
        normalized = normalization_by_source[source_checksum]
        relative_path, normalized_path = _safe_path(
            normalization_base,
            normalized.get("normalizedRelativePath"),
            f"corpus.images[{image_index}].normalizedRelativePath",
        )
        expected_checksum = _sha256(
            normalized.get("normalizedChecksumSha256"),
            f"corpus.images[{image_index}].normalizedChecksumSha256",
        )
        try:
            normalized_bytes = normalized_path.read_bytes()
        except OSError as error:
            raise SequenceOcrError(
                "SEQUENCE_OCR_NORMALIZED_IMAGE_UNREADABLE",
                "Normalized image cannot be read.",
            ) from error
        if _sha256_bytes(normalized_bytes) != expected_checksum:
            raise SequenceOcrError(
                "SEQUENCE_OCR_NORMALIZED_CHECKSUM_MISMATCH",
                "Normalized image checksum differs from its report.",
            )
        detection_item = detection_by_source[source_checksum]
        if detection_item.get("normalizedRelativePath") != relative_path:
            raise SequenceOcrError(
                "SEQUENCE_OCR_DETECTION_DRIFT",
                "Detection normalized path differs from normalization report.",
            )
        bgr = cv2.imdecode(np.frombuffer(normalized_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if bgr is None:
            raise SequenceOcrError(
                "SEQUENCE_OCR_NORMALIZED_DECODE_FAILED",
                "Normalized image cannot be decoded.",
            )
        rgb = cast(NDArray[np.uint8], cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        boards = _boards(
            _mapping(detection_item.get("result"), f"detections[{image_index}].result"),
            f"detections[{image_index}].result",
        )
        if image_id not in golden_by_id:
            raise SequenceOcrError(
                "SEQUENCE_OCR_GOLDEN_MISMATCH",
                "Corpus image is missing from golden annotations.",
            )
        expected_values = tuple(
            _integer(number, f"golden.{image_id}.sequenceNumbers[{index}]")
            for index, number in enumerate(
                _sequence(golden_by_id[image_id].get("sequenceNumbers"), "sequenceNumbers")
            )
        )
        if len(expected_values) != len(boards):
            raise SequenceOcrError(
                "SEQUENCE_OCR_GOLDEN_MISMATCH",
                "Golden sequence count must match the detected page.",
            )
        for (position_index, board_quad), expected in zip(
            boards,
            expected_values,
            strict=True,
        ):
            raw_crop, processed_crop, crop_quad = extract_sequence_number_crop(
                rgb,
                board_quad,
            )
            recognition_input = (
                raw_crop
                if recognition_input_policy == RAW_WARP_PREPROCESSING_VERSION
                else processed_crop
            )
            recognition = implementation.recognize(recognition_input)
            artifact_root_path = PurePosixPath(
                implementation.version,
                source_checksum[:2],
                source_checksum,
                f"position-{position_index:02d}",
            )
            raw_relative = (artifact_root_path / "raw.png").as_posix()
            processed_relative = (artifact_root_path / "foreground.png").as_posix()
            normalized_number = recognition.normalized_number
            results.append(
                SequenceArtifact(
                    image_id=image_id,
                    source_checksum_sha256=source_checksum,
                    position_index=position_index,
                    expected_number=expected,
                    crop_quad=tuple((float(point[0]), float(point[1])) for point in crop_quad),
                    raw_crop_relative_path=raw_relative,
                    raw_crop_checksum_sha256=_artifact(
                        output_base,
                        raw_relative,
                        raw_crop,
                    ),
                    processed_crop_relative_path=processed_relative,
                    processed_crop_checksum_sha256=_artifact(
                        output_base,
                        processed_relative,
                        processed_crop,
                    ),
                    processed_crop_width=int(processed_crop.shape[1]),
                    processed_crop_height=int(processed_crop.shape[0]),
                    raw_text=recognition.raw_text,
                    normalized_number=normalized_number,
                    confidence=recognition.confidence,
                    exact_match=normalized_number == expected,
                    review_reasons=(),
                )
            )
    return SequenceOcrReport(
        corpus_manifest_sha256=_sha256_bytes(corpus_bytes),
        golden_annotations_sha256=_sha256_bytes(golden_bytes),
        normalization_report_sha256=normalization_sha,
        detection_report_sha256=_sha256_bytes(detection_bytes),
        recognizer=implementation,
        preprocessing_version=recognition_input_policy,
        results=validate_sequence_continuity(results),
    )
