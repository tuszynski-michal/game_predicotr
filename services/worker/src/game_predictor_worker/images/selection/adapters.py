"""Pillow/OpenCV adapters for ``fast-image-selector-v1``."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageOps, UnidentifiedImageError

from game_predictor_worker.images.geometry import (
    BoardDetection,
    ClassicalPageBoardDetector,
    DetectionResult,
    PageBoardDetector,
)
from game_predictor_worker.images.image_file import ImageFileError, sha256_file
from game_predictor_worker.images.sequence_ocr import (
    Recognition,
    SequenceNumberRecognizer,
    SequenceOcrError,
    extract_sequence_number_crop,
)

from .contracts import (
    CandidateVerification,
    CheapImageObservation,
    ImageQualityMetrics,
    ImageSelectionSource,
    SelectionContractError,
    SequenceRange,
)
from .manifest import DEFAULT_SELECTOR_MANIFEST, QualityWeights, SelectorManifest
from .ports import (
    ImageQualityAnalyzer,
    LatticeFingerprint,
    LatticeFingerprintAnalyzer,
    SequenceRangeRecognizer,
    ThumbnailFrame,
    ThumbnailLoader,
)


def _safe_source_path(root: Path, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path)
    try:
        resolved = (root / Path(*relative.parts)).resolve(strict=True)
    except OSError as error:
        raise SelectionContractError(
            "IMAGE_SELECTION_SCAN_SOURCE_UNREADABLE",
            "A staged selection source cannot be read.",
        ) from error
    if not resolved.is_relative_to(root):
        raise SelectionContractError(
            "IMAGE_SELECTION_SCAN_SOURCE_UNSAFE",
            "A staged selection source escapes its managed root.",
        )
    return resolved


def _load_verified_rgb(path: Path, expected_checksum: str) -> NDArray[np.uint8]:
    try:
        if sha256_file(path) != expected_checksum:
            raise SelectionContractError(
                "IMAGE_SELECTION_SCAN_CHECKSUM_MISMATCH",
                "A staged selection source differs from its input manifest.",
            )
        with Image.open(path) as source:
            source.load()
            normalized = ImageOps.exif_transpose(source).convert("RGB")
            return np.asarray(normalized, dtype=np.uint8)
    except SelectionContractError:
        raise
    except (ImageFileError, OSError, UnidentifiedImageError, ValueError) as error:
        raise SelectionContractError(
            "IMAGE_SELECTION_SCAN_DECODE_FAILED",
            "A staged selection source is not a readable JPEG.",
        ) from error


class PillowThumbnailLoader:
    version = "pillow-exif-thumbnail-v1"

    def __init__(self, source_root: Path, *, max_edge: int) -> None:
        self._source_root = source_root.resolve(strict=True)
        self._max_edge = max_edge

    def load(self, source: ImageSelectionSource) -> ThumbnailFrame:
        path = _safe_source_path(self._source_root, source.stored_relative_path)
        try:
            if sha256_file(path) != source.checksum_sha256:
                raise SelectionContractError(
                    "IMAGE_SELECTION_SCAN_CHECKSUM_MISMATCH",
                    "A staged selection source differs from its input manifest.",
                )
            with Image.open(path) as image:
                image.load()
                normalized = ImageOps.exif_transpose(image).convert("RGB")
                source_width, source_height = normalized.size
                normalized.thumbnail(
                    (self._max_edge, self._max_edge),
                    resample=Image.Resampling.LANCZOS,
                )
                rgb = np.asarray(normalized, dtype=np.uint8)
        except SelectionContractError:
            raise
        except (ImageFileError, OSError, UnidentifiedImageError, ValueError) as error:
            raise SelectionContractError(
                "IMAGE_SELECTION_SCAN_DECODE_FAILED",
                "A staged selection source is not a readable JPEG.",
            ) from error
        return ThumbnailFrame(
            rgb=rgb,
            source_width=source_width,
            source_height=source_height,
        )


def _median_hash(rgb: NDArray[np.uint8]) -> str:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    resized = cv2.resize(gray, (16, 16), interpolation=cv2.INTER_AREA)
    median = float(np.median(resized))
    bits = (resized > median).reshape(-1)
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return f"{value:064x}"


def _board_composite(
    rgb: NDArray[np.uint8],
    boards: tuple[BoardDetection, ...],
) -> NDArray[np.uint8]:
    if not boards:
        height, width = rgb.shape[:2]
        return rgb[height // 8 : height * 7 // 8, width // 8 : width * 7 // 8]
    canvas: NDArray[np.uint8] = np.zeros((3 * 20, 3 * 32, 3), dtype=np.uint8)
    for board in boards:
        x, y, width, height = board.bounding_box
        crop = rgb[max(0, y) : max(0, y + height), max(0, x) : max(0, x + width)]
        if crop.size == 0:
            continue
        tile = cv2.resize(crop, (32, 20), interpolation=cv2.INTER_AREA)
        row, column = divmod(board.position_index, 3)
        if row < 3 and column < 3:
            canvas[row * 20 : (row + 1) * 20, column * 32 : (column + 1) * 32] = tile
    return canvas


def _geometry_signature(
    boards: tuple[BoardDetection, ...],
    *,
    width: int,
    height: int,
) -> tuple[float, ...]:
    values: list[float] = []
    for board in boards:
        x, y, board_width, board_height = board.bounding_box
        values.extend(
            (
                round((x + board_width / 2) / width, 4),
                round((y + board_height / 2) / height, 4),
                round(board_width / width, 4),
                round(board_height / height, 4),
            )
        )
    return tuple(values)


def _best_supported_detection(
    detector: PageBoardDetector,
    rgb: NDArray[np.uint8],
    *,
    expected_board_count: int | None = None,
) -> DetectionResult:
    if expected_board_count is not None:
        return detector.detect(
            rgb,
            expected_board_count=expected_board_count,
            allow_grid_recovery=False,
        )
    full = detector.detect(rgb, expected_board_count=9, allow_grid_recovery=False)
    if full.status == "detected" or not 1 <= full.candidate_count <= 8:
        return full
    partial = detector.detect(
        rgb,
        expected_board_count=full.candidate_count,
        allow_grid_recovery=False,
    )
    return partial if partial.status == "detected" else full


class OpenCvLatticeFingerprintAnalyzer:
    version = "opencv-lattice-fingerprint-v1"

    def __init__(self, detector: PageBoardDetector | None = None) -> None:
        self._detector = detector or ClassicalPageBoardDetector()

    def analyze(self, frame: ThumbnailFrame) -> LatticeFingerprint:
        detection = _best_supported_detection(self._detector, frame.rgb)
        boards = detection.boards
        return LatticeFingerprint(
            fingerprint_hex=_median_hash(_board_composite(frame.rgb, boards)),
            geometry_signature=_geometry_signature(
                boards,
                width=frame.rgb.shape[1],
                height=frame.rgb.shape[0],
            ),
            board_count=(len(boards) if detection.status == "detected" else None),
            geometry_confidence=detection.confidence,
            boards=boards,
            reason_codes=tuple(detection.review_reasons),
        )


class OpenCvImageQualityAnalyzer:
    version = "opencv-thumbnail-quality-v1"

    def __init__(self, weights: QualityWeights) -> None:
        self._weights = weights

    def measure(
        self,
        frame: ThumbnailFrame,
        lattice: LatticeFingerprint,
    ) -> ImageQualityMetrics:
        rgb = frame.rgb
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        laplacian_variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        sharpness = laplacian_variance / (laplacian_variance + 500.0)
        mean_luminance = float(np.mean(gray))
        exposure = max(0.0, 1.0 - abs(mean_luminance - 127.5) / 127.5)
        clipped_fraction = float(np.mean((gray <= 4) | (gray >= 251)))
        highlight_retention = max(0.0, 1.0 - clipped_fraction * 2.5)
        glare_fraction = float(np.mean((hsv[:, :, 2] >= 242) & (hsv[:, :, 1] <= 45)))
        glare_resistance = max(0.0, 1.0 - glare_fraction * 6.0)
        perspective = lattice.geometry_confidence
        border_margin = self._border_margin(lattice.boards, rgb.shape[1], rgb.shape[0])
        board_visibility = (
            1.0
            if lattice.board_count is not None
            else min(
                1.0,
                len(lattice.boards) / 9,
            )
        )
        components = {
            "board_visibility": board_visibility,
            "border_margin": border_margin,
            "exposure": exposure,
            "glare_resistance": glare_resistance,
            "highlight_retention": highlight_retention,
            "perspective": perspective,
            "sharpness": sharpness,
        }
        overall = sum(components[name] * getattr(self._weights, name) for name in components)
        return ImageQualityMetrics(
            sharpness=round(sharpness, 6),
            exposure=round(exposure, 6),
            highlight_retention=round(highlight_retention, 6),
            glare_resistance=round(glare_resistance, 6),
            perspective=round(perspective, 6),
            border_margin=round(border_margin, 6),
            board_visibility=round(board_visibility, 6),
            overall_score=round(max(0.0, min(1.0, overall)), 6),
        )

    @staticmethod
    def _border_margin(
        boards: tuple[BoardDetection, ...],
        width: int,
        height: int,
    ) -> float:
        if not boards:
            return 0.0
        left = min(board.bounding_box[0] for board in boards)
        top = min(board.bounding_box[1] for board in boards)
        right = max(board.bounding_box[0] + board.bounding_box[2] for board in boards)
        bottom = max(board.bounding_box[1] + board.bounding_box[3] for board in boards)
        normalized = min(
            left / width,
            top / height,
            (width - right) / width,
            (height - bottom) / height,
        )
        return float(max(0.0, min(1.0, normalized / 0.025)))


class ComposedCheapImageAnalyzer:
    """Compose explicit thumbnail, lattice/fingerprint and quality ports."""

    def __init__(
        self,
        thumbnail_loader: ThumbnailLoader,
        lattice_analyzer: LatticeFingerprintAnalyzer,
        quality_analyzer: ImageQualityAnalyzer,
    ) -> None:
        self._thumbnail_loader = thumbnail_loader
        self._lattice_analyzer = lattice_analyzer
        self._quality_analyzer = quality_analyzer

    def analyze(self, source: ImageSelectionSource) -> CheapImageObservation:
        try:
            frame = self._thumbnail_loader.load(source)
            lattice = self._lattice_analyzer.analyze(frame)
            quality = self._quality_analyzer.measure(frame, lattice)
            return CheapImageObservation(
                source=source,
                width=frame.source_width,
                height=frame.source_height,
                fingerprint_hex=lattice.fingerprint_hex,
                geometry_signature=lattice.geometry_signature,
                board_count=lattice.board_count,
                geometry_confidence=lattice.geometry_confidence,
                quality=quality,
                reason_codes=lattice.reason_codes,
            )
        except SelectionContractError as error:
            zero = ImageQualityMetrics(*(0.0 for _ in range(8)))
            return CheapImageObservation(
                source=source,
                width=1,
                height=1,
                fingerprint_hex=source.checksum_sha256,
                geometry_signature=(),
                board_count=None,
                geometry_confidence=0.0,
                quality=zero,
                reason_codes=(error.code,),
            )


class AnchoredSequenceRangeRecognizer:
    version = "sequence-anchor-range-v1"

    def __init__(self, recognizer: SequenceNumberRecognizer) -> None:
        self._recognizer = recognizer

    def recognize(
        self,
        rgb_image: NDArray[np.uint8],
        boards: tuple[BoardDetection, ...],
    ) -> tuple[SequenceRange | None, tuple[str, ...]]:
        if not boards:
            return None, ("RANGE_GEOMETRY_MISSING",)
        indexes = tuple(sorted({0, len(boards) // 2, len(boards) - 1}))
        try:
            crops = tuple(
                extract_sequence_number_crop(rgb_image, boards[index].quad)[1] for index in indexes
            )
            recognize_many = getattr(self._recognizer, "recognize_many", None)
            if callable(recognize_many):
                recognitions = tuple(recognize_many(crops))
            else:
                recognitions = tuple(self._recognizer.recognize(crop) for crop in crops)
        except (SequenceOcrError, ValueError):
            return None, ("RANGE_ANCHOR_CROP_FAILED",)
        return self._validate_anchors(indexes, recognitions, len(boards))

    @staticmethod
    def _validate_anchors(
        indexes: tuple[int, ...],
        recognitions: tuple[Recognition, ...],
        board_count: int,
    ) -> tuple[SequenceRange | None, tuple[str, ...]]:
        if len(recognitions) != len(indexes):
            return None, ("RANGE_RECOGNIZER_RESULT_INVALID",)
        values = tuple(result.normalized_number for result in recognitions)
        if any(value is None or value < 1 for value in values):
            return None, ("RANGE_ANCHOR_UNREADABLE",)
        start = cast(int, values[0])
        if any(value != start + index for value, index in zip(values, indexes, strict=True)):
            return None, ("RANGE_ANCHOR_INCONSISTENT",)
        end = start + board_count - 1
        confidence = round(min(result.confidence for result in recognitions), 6)
        return SequenceRange(start=start, end=end, confidence=confidence), ()


class NoRangeRecognizer:
    version = "no-range-recognizer-v1"

    def recognize(
        self,
        rgb_image: NDArray[np.uint8],
        boards: tuple[BoardDetection, ...],
    ) -> tuple[SequenceRange | None, tuple[str, ...]]:
        del rgb_image, boards
        return None, ("RANGE_RECOGNIZER_UNAVAILABLE",)


class FullCandidateVerifier:
    """Verify only one top-k candidate with full geometry and sparse OCR."""

    def __init__(
        self,
        source_root: Path,
        range_recognizer: SequenceRangeRecognizer,
        detector: PageBoardDetector | None = None,
    ) -> None:
        self._source_root = source_root.resolve(strict=True)
        self._range_recognizer = range_recognizer
        self._detector = detector or ClassicalPageBoardDetector()

    def verify(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        if expected_board_count is None:
            return CandidateVerification(
                recognized_range=None,
                board_count=None,
                geometry_complete=False,
                full_frame_visible=False,
                reason_codes=("BOARD_COUNT_CONSENSUS_UNKNOWN",),
            )
        try:
            path = _safe_source_path(
                self._source_root,
                observation.source.stored_relative_path,
            )
            rgb = _load_verified_rgb(path, observation.source.checksum_sha256)
            detection = _best_supported_detection(
                self._detector,
                rgb,
                expected_board_count=expected_board_count,
            )
        except SelectionContractError as error:
            return CandidateVerification(
                recognized_range=None,
                board_count=None,
                geometry_complete=False,
                full_frame_visible=False,
                reason_codes=(error.code,),
            )
        geometry_complete = (
            detection.status == "detected" and len(detection.boards) == expected_board_count
        )
        if not geometry_complete:
            return CandidateVerification(
                recognized_range=None,
                board_count=(len(detection.boards) or None),
                geometry_complete=False,
                full_frame_visible=False,
                reason_codes=tuple(detection.review_reasons) or ("GEOMETRY_INCOMPLETE",),
            )
        full_frame_visible = self._full_frame_visible(detection, rgb.shape[1], rgb.shape[0])
        recognized_range, range_reasons = self._range_recognizer.recognize(
            rgb,
            detection.boards,
        )
        return CandidateVerification(
            recognized_range=recognized_range,
            board_count=len(detection.boards),
            geometry_complete=True,
            full_frame_visible=full_frame_visible,
            reason_codes=range_reasons,
        )

    @staticmethod
    def _full_frame_visible(detection: DetectionResult, width: int, height: int) -> bool:
        if detection.page_quad is None:
            return False
        margin = max(1, int(round(min(width, height) * 0.002)))
        return all(
            margin <= point.x < width - margin and margin <= point.y < height - margin
            for point in detection.page_quad
        )


def build_default_adapters(
    source_root: Path,
    *,
    range_recognizer: SequenceRangeRecognizer | None = None,
    manifest: SelectorManifest = DEFAULT_SELECTOR_MANIFEST,
) -> tuple[ComposedCheapImageAnalyzer, FullCandidateVerifier]:
    detector = ClassicalPageBoardDetector()
    analyzer = ComposedCheapImageAnalyzer(
        PillowThumbnailLoader(source_root, max_edge=manifest.thumbnail_max_edge),
        OpenCvLatticeFingerprintAnalyzer(detector),
        OpenCvImageQualityAnalyzer(manifest.quality_weights),
    )
    verifier = FullCandidateVerifier(
        source_root,
        range_recognizer or NoRangeRecognizer(),
        detector,
    )
    return analyzer, verifier


__all__ = [
    "AnchoredSequenceRangeRecognizer",
    "ComposedCheapImageAnalyzer",
    "FullCandidateVerifier",
    "NoRangeRecognizer",
    "OpenCvImageQualityAnalyzer",
    "OpenCvLatticeFingerprintAnalyzer",
    "PillowThumbnailLoader",
    "build_default_adapters",
]
