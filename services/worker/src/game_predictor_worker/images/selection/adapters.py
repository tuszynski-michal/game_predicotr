"""Pillow/OpenCV adapters for the versioned fast image selector."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from statistics import StatisticsError
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
    CandidateVerifier,
    CheapImageAnalyzer,
    CheapImageObservation,
    ImageQualityMetrics,
    ImageSelectionSource,
    RangeEvidence,
    RepresentativeAssessment,
    SelectionContractError,
    SequenceRange,
)
from .manifest import (
    ACCURACY_FIRST_SELECTOR_VERSIONS,
    ADAPTIVE_ACCURACY_SELECTOR_VERSION,
    APPEARANCE_GROUPING_SELECTOR_VERSIONS,
    APPEARANCE_ONLY_SELECTOR_VERSIONS,
    DEFAULT_SELECTOR_MANIFEST,
    LEGACY_THUMBNAIL_ADAPTER_VERSION,
    ORDERED_SELECTOR_VERSIONS,
    REDUCED_JPEG_THUMBNAIL_ADAPTER_VERSION,
    AppearanceDescriptorConfig,
    FullGeometryPolicy,
    ProgressiveVisibleLabelFallbackPolicy,
    QualityWeights,
    SelectorManifest,
)
from .ports import (
    ImageQualityAnalyzer,
    LatticeFingerprint,
    LatticeFingerprintAnalyzer,
    SequenceRangeRecognizer,
    ThumbnailFrame,
    ThumbnailLoader,
)
from .telemetry import StageTimingCollector

OPENCV_INTERNAL_THREAD_BUDGET = 1


def configure_opencv_thread_budget(
    thread_count: int = OPENCV_INTERNAL_THREAD_BUDGET,
) -> int:
    """Bound OpenCV's global pool before external scan workers are created."""

    if thread_count != OPENCV_INTERNAL_THREAD_BUDGET:
        raise ValueError("Image selection requires exactly one internal OpenCV thread.")
    cv2.setNumThreads(thread_count)
    return cv2.getNumThreads()


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


def _load_verified_rgb(
    path: Path,
    expected_checksum: str,
    telemetry: StageTimingCollector | None = None,
) -> NDArray[np.uint8]:
    try:
        if telemetry is None:
            actual_checksum = sha256_file(path)
        else:
            telemetry.increment("checksumReads")
            with telemetry.measure("checksum"):
                actual_checksum = sha256_file(path)
        if actual_checksum != expected_checksum:
            raise SelectionContractError(
                "IMAGE_SELECTION_SCAN_CHECKSUM_MISMATCH",
                "A staged selection source differs from its input manifest.",
            )
        if telemetry is not None:
            telemetry.increment("decoderCalls")
        timing = telemetry.measure("decode") if telemetry is not None else nullcontext()
        with timing, Image.open(path) as source:
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
    version = LEGACY_THUMBNAIL_ADAPTER_VERSION

    def __init__(
        self,
        source_root: Path,
        *,
        max_edge: int,
        adapter_version: str = LEGACY_THUMBNAIL_ADAPTER_VERSION,
        telemetry: StageTimingCollector | None = None,
    ) -> None:
        self._source_root = source_root.resolve(strict=True)
        self._max_edge = max_edge
        self.version = adapter_version
        self._reduced_decode = adapter_version == REDUCED_JPEG_THUMBNAIL_ADAPTER_VERSION
        self._telemetry = telemetry

    def load(self, source: ImageSelectionSource) -> ThumbnailFrame:
        path = _safe_source_path(self._source_root, source.stored_relative_path)
        try:
            if self._telemetry is None:
                actual_checksum = sha256_file(path)
            else:
                self._telemetry.increment("checksumReads")
                with self._telemetry.measure("checksum"):
                    actual_checksum = sha256_file(path)
            if actual_checksum != source.checksum_sha256:
                raise SelectionContractError(
                    "IMAGE_SELECTION_SCAN_CHECKSUM_MISMATCH",
                    "A staged selection source differs from its input manifest.",
                )
            if self._telemetry is not None:
                self._telemetry.increment("decoderCalls")
            timing = (
                self._telemetry.measure("decode") if self._telemetry is not None else nullcontext()
            )
            with timing, Image.open(path) as image:
                source_width, source_height = _normalized_source_dimensions(image)
                if self._reduced_decode:
                    image.draft("RGB", (self._max_edge, self._max_edge))
                image.load()
                normalized = ImageOps.exif_transpose(image).convert("RGB")
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


def _normalized_source_dimensions(image: Image.Image) -> tuple[int, int]:
    width, height = image.size
    orientation = int(image.getexif().get(274, 1))
    if orientation in {5, 6, 7, 8}:
        return height, width
    return width, height


def _layout_color_hash(rgb: NDArray[np.uint8]) -> str:
    """Hash the screen layout without depending on a variable board count."""

    height, width = rgb.shape[:2]
    roi = rgb[
        int(round(height * 0.22)) : int(round(height * 0.48)),
        int(round(width * 0.12)) : int(round(width * 0.88)),
    ]
    if roi.size == 0:
        roi = rgb
    hsv = cv2.cvtColor(
        cv2.resize(roi, (16, 16), interpolation=cv2.INTER_AREA),
        cv2.COLOR_RGB2HSV,
    )
    value = 0
    for hue, saturation, brightness in hsv.reshape(-1, 3):
        quantized = (int(hue) // 45) << 2 | (int(saturation) >= 100) << 1 | (int(brightness) >= 100)
        value = (value << 4) | quantized
    return f"{value:0256x}"


def _appearance_roi(
    rgb: NDArray[np.uint8],
    config: AppearanceDescriptorConfig,
) -> NDArray[np.uint8]:
    height, width = rgb.shape[:2]
    left = max(0, min(width - 1, int(round(width * config.crop_left))))
    right = max(left + 1, min(width, int(round(width * config.crop_right))))
    top = max(0, min(height - 1, int(round(height * config.crop_top))))
    bottom = max(top + 1, min(height, int(round(height * config.crop_bottom))))
    roi = rgb[top:bottom, left:right]
    return rgb if roi.size == 0 else roi


def _normalized_histogram(
    values: NDArray[np.uint8] | NDArray[np.float32],
    *,
    bins: int,
    upper: float,
    weights: NDArray[np.float32] | None = None,
) -> tuple[float, ...]:
    histogram, _ = np.histogram(values, bins=bins, range=(0.0, upper), weights=weights)
    total = float(histogram.sum())
    if total <= 0:
        return (0.0,) * bins
    return tuple(round(float(value / total), 6) for value in histogram)


def _appearance_descriptor(
    rgb: NDArray[np.uint8],
    config: AppearanceDescriptorConfig,
) -> tuple[float, ...]:
    roi = _appearance_roi(rgb, config)
    gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
    hsv = np.asarray(cv2.cvtColor(roi, cv2.COLOR_RGB2HSV), dtype=np.uint8)

    phash_input = cv2.resize(
        gray,
        (config.phash_input_size, config.phash_input_size),
        interpolation=cv2.INTER_AREA,
    ).astype(np.float32)
    low_frequency = cv2.dct(phash_input)[: config.phash_size, : config.phash_size]
    low_frequency[0, 0] = 0.0
    frequency_norm = max(float(np.linalg.norm(low_frequency)), 1e-6)
    # Keep a continuous perceptual DCT signature instead of thresholding every
    # coefficient into a bit.  Binary pHash was unstable around a coefficient's
    # median: nearly identical consecutive photos flipped a bit and looked as
    # different as a real page transition.  Mapping the normalized coefficients
    # to [0, 1] keeps cache/checkpoint serialization compact and deterministic.
    phash = np.clip((low_frequency / frequency_norm + 1.0) * 0.5, 0.0, 1.0).reshape(-1)
    phash[0] = 0.5

    hue = _normalized_histogram(hsv[:, :, 0], bins=config.hue_bins, upper=180.0)
    saturation = _normalized_histogram(
        hsv[:, :, 1],
        bins=config.saturation_bins,
        upper=256.0,
    )
    value = _normalized_histogram(
        hsv[:, :, 2],
        bins=config.value_bins,
        upper=256.0,
    )

    gradient_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gradient_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(gradient_x, gradient_y)
    robust_scale = max(1.0, float(np.percentile(magnitude, 95)))
    normalized_magnitude = np.clip(magnitude / robust_scale, 0.0, 1.0)
    edge_grid: list[float] = []
    for row in np.array_split(normalized_magnitude, config.edge_grid_rows, axis=0):
        for cell in np.array_split(row, config.edge_grid_columns, axis=1):
            edge_grid.append(0.0 if cell.size == 0 else round(float(np.mean(cell)), 6))
    orientation = np.mod(cv2.phase(gradient_x, gradient_y, angleInDegrees=True), 180.0)
    edge_orientation = _normalized_histogram(
        orientation.astype(np.float32),
        bins=config.edge_orientation_bins,
        upper=180.0,
        weights=magnitude.astype(np.float32),
    )
    return tuple(float(value) for value in phash) + (
        *hue,
        *saturation,
        *value,
        *edge_grid,
        *edge_orientation,
    )


def _appearance_fingerprint(signature: tuple[float, ...]) -> str:
    quantized = np.rint(np.asarray(signature, dtype=np.float32) * 255.0).astype(np.uint8)
    return hashlib.sha256(quantized.tobytes()).hexdigest()


class OpenCvAppearanceFingerprintAnalyzer:
    version = "opencv-appearance-descriptor-v2"

    def __init__(
        self,
        config: AppearanceDescriptorConfig,
        *,
        telemetry: StageTimingCollector | None = None,
    ) -> None:
        self._config = config
        self._telemetry = telemetry

    def analyze(self, frame: ThumbnailFrame) -> LatticeFingerprint:
        timing = (
            self._telemetry.measure("appearance") if self._telemetry is not None else nullcontext()
        )
        with timing:
            signature = _appearance_descriptor(frame.rgb, self._config)
        return LatticeFingerprint(
            fingerprint_hex=_appearance_fingerprint(signature),
            geometry_signature=(),
            board_count=None,
            geometry_confidence=0.0,
            boards=(),
            reason_codes=(),
            appearance_signature=signature,
        )


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
    allow_grid_recovery: bool = False,
    telemetry: StageTimingCollector | None = None,
) -> DetectionResult:
    def detect(board_count: int) -> DetectionResult:
        if telemetry is not None:
            telemetry.increment("detectorCalls")
        return detector.detect(
            rgb,
            expected_board_count=board_count,
            allow_grid_recovery=allow_grid_recovery,
        )

    if expected_board_count is not None:
        return detect(expected_board_count)
    full = detect(9)
    if full.status == "detected" or not 1 <= full.candidate_count <= 8:
        return full
    partial = detect(full.candidate_count)
    return partial if partial.status == "detected" else full


class OpenCvLatticeFingerprintAnalyzer:
    version = "opencv-lattice-fingerprint-v1"

    def __init__(
        self,
        detector: PageBoardDetector | None = None,
        *,
        telemetry: StageTimingCollector | None = None,
    ) -> None:
        self._detector = detector or ClassicalPageBoardDetector()
        self._telemetry = telemetry

    def analyze(self, frame: ThumbnailFrame) -> LatticeFingerprint:
        geometry_timing = (
            self._telemetry.measure("geometry") if self._telemetry is not None else nullcontext()
        )
        with geometry_timing:
            detection = _best_supported_detection(
                self._detector,
                frame.rgb,
                telemetry=self._telemetry,
            )
            boards = detection.boards
            geometry_signature = _geometry_signature(
                boards,
                width=frame.rgb.shape[1],
                height=frame.rgb.shape[0],
            )
        appearance_timing = (
            self._telemetry.measure("appearance") if self._telemetry is not None else nullcontext()
        )
        with appearance_timing:
            fingerprint_hex = _layout_color_hash(frame.rgb)
        return LatticeFingerprint(
            fingerprint_hex=fingerprint_hex,
            geometry_signature=geometry_signature,
            board_count=(len(boards) if detection.status == "detected" else None),
            geometry_confidence=detection.confidence,
            boards=boards,
            reason_codes=tuple(detection.review_reasons),
        )


class OpenCvImageQualityAnalyzer:
    version = "opencv-thumbnail-quality-v1"

    def __init__(
        self,
        weights: QualityWeights,
        *,
        telemetry: StageTimingCollector | None = None,
    ) -> None:
        self._weights = weights
        self._telemetry = telemetry

    def measure(
        self,
        frame: ThumbnailFrame,
        lattice: LatticeFingerprint,
    ) -> ImageQualityMetrics:
        timing = (
            self._telemetry.measure("quality") if self._telemetry is not None else nullcontext()
        )
        with timing:
            return self._measure(frame, lattice)

    def _measure(
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


class OpenCvAppearanceQualityAnalyzer:
    version = "opencv-appearance-quality-v1"

    def __init__(
        self,
        weights: QualityWeights,
        config: AppearanceDescriptorConfig,
        *,
        telemetry: StageTimingCollector | None = None,
    ) -> None:
        self._weights = weights
        self._config = config
        self._telemetry = telemetry

    def measure(
        self,
        frame: ThumbnailFrame,
        lattice: LatticeFingerprint,
    ) -> ImageQualityMetrics:
        del lattice
        timing = (
            self._telemetry.measure("quality") if self._telemetry is not None else nullcontext()
        )
        with timing:
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
            screen_gray = cv2.cvtColor(
                _appearance_roi(rgb, self._config),
                cv2.COLOR_RGB2GRAY,
            )
            screen_contrast = float(np.std(screen_gray))
            screen_edges = float(np.mean(np.abs(cv2.Laplacian(screen_gray, cv2.CV_32F))))
            central_visibility = max(
                0.0,
                min(
                    1.0,
                    0.65 * (screen_contrast / (screen_contrast + 32.0))
                    + 0.35 * (screen_edges / (screen_edges + 20.0)),
                ),
            )
            components = {
                "board_visibility": central_visibility,
                "border_margin": central_visibility,
                "exposure": exposure,
                "glare_resistance": glare_resistance,
                "highlight_retention": highlight_retention,
                "perspective": central_visibility,
                "sharpness": sharpness,
            }
            overall = sum(components[name] * getattr(self._weights, name) for name in components)
            return ImageQualityMetrics(
                sharpness=round(sharpness, 6),
                exposure=round(exposure, 6),
                highlight_retention=round(highlight_retention, 6),
                glare_resistance=round(glare_resistance, 6),
                perspective=round(central_visibility, 6),
                border_margin=round(central_visibility, 6),
                board_visibility=round(central_visibility, 6),
                overall_score=round(max(0.0, min(1.0, overall)), 6),
            )


class OpenCvAccuracyFirstQualityAnalyzer(OpenCvAppearanceQualityAnalyzer):
    """Board-area quality proxy used to shortlist every frame in a v10 group."""

    version = "opencv-appearance-quality-v2"

    def measure(
        self,
        frame: ThumbnailFrame,
        lattice: LatticeFingerprint,
    ) -> ImageQualityMetrics:
        del lattice
        timing = (
            self._telemetry.measure("quality") if self._telemetry is not None else nullcontext()
        )
        with timing:
            return self._measure(frame)

    def _measure(
        self,
        frame: ThumbnailFrame,
    ) -> ImageQualityMetrics:
        rgb = frame.rgb
        height, width = rgb.shape[:2]
        top = int(round(height * 0.16))
        bottom = int(round(height * 0.82))
        left = int(round(width * 0.08))
        right = int(round(width * 0.92))
        region = rgb[top:bottom, left:right]
        if region.size == 0:
            region = rgb
        gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
        hsv = cv2.cvtColor(region, cv2.COLOR_RGB2HSV)
        laplacian_variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        sharpness = laplacian_variance / (laplacian_variance + 420.0)
        mean_luminance = float(np.mean(gray))
        exposure = max(0.0, 1.0 - abs(mean_luminance - 127.5) / 127.5)
        clipped_fraction = float(np.mean((gray <= 4) | (gray >= 251)))
        highlight_retention = max(0.0, 1.0 - clipped_fraction * 2.5)
        glare_fraction = float(np.mean((hsv[:, :, 2] >= 242) & (hsv[:, :, 1] <= 45)))
        glare_resistance = max(0.0, 1.0 - glare_fraction * 6.0)
        edge_map = np.abs(cv2.Laplacian(gray, cv2.CV_32F))
        edge_strength = float(np.mean(edge_map))
        contrast = float(np.std(gray))
        board_visibility = max(
            0.0,
            min(
                1.0,
                0.55 * contrast / (contrast + 30.0) + 0.45 * edge_strength / (edge_strength + 18.0),
            ),
        )
        border_band = max(2, int(round(min(region.shape[:2]) * 0.035)))
        border_values = np.concatenate(
            (
                edge_map[:border_band, :].reshape(-1),
                edge_map[-border_band:, :].reshape(-1),
                edge_map[:, :border_band].reshape(-1),
                edge_map[:, -border_band:].reshape(-1),
            )
        )
        border_activity = float(np.mean(border_values)) if border_values.size else 0.0
        border_margin = max(0.0, min(1.0, 1.0 - border_activity / (border_activity + 24.0)))
        perspective = board_visibility
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
                appearance_signature=lattice.appearance_signature,
            )
        except (SelectionContractError, StatisticsError) as error:
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
                reason_codes=(
                    error.code
                    if isinstance(error, SelectionContractError)
                    else "IMAGE_SELECTION_SCAN_GEOMETRY_FAILED",
                ),
                appearance_signature=(),
            )


class AppearanceOnlyCandidateVerifier:
    version = "none-v2"

    def verify(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        del observation, expected_board_count
        raise SelectionContractError(
            "IMAGE_SELECTION_APPEARANCE_VERIFIER_FORBIDDEN",
            "Appearance-only selection cannot invoke geometry or sequence OCR.",
        )


class AnchoredSequenceRangeRecognizer:
    version = "sequence-anchor-range-v1"

    def __init__(
        self,
        recognizer: SequenceNumberRecognizer,
        *,
        telemetry: StageTimingCollector | None = None,
    ) -> None:
        self._recognizer = recognizer
        self._telemetry = telemetry

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
                if self._telemetry is not None:
                    self._telemetry.increment("ocrCalls")
                    self._telemetry.increment("ocrCrops", len(crops))
                recognitions = tuple(recognize_many(crops))
            else:
                if self._telemetry is not None:
                    self._telemetry.increment("ocrCalls", len(crops))
                    self._telemetry.increment("ocrCrops", len(crops))
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


@dataclass(frozen=True, slots=True)
class _VisibleLabel:
    crop: NDArray[np.uint8]
    center: tuple[float, float]


class VisibleSequenceLabelRangeRecognizer:
    """Read the page range from the spatial lattice of visible number labels.

    The arcade cabinet is dark and its red board frames are not stable enough to
    be the sole source of geometry.  Sequence labels are bright, ordered and
    arranged in a 3x3 lattice, so they provide an independent fail-closed
    fallback for full-resolution candidates.
    """

    version = "visible-sequence-label-range-v1"
    _minimum_ocr_confidence = 0.72
    _minimum_inlier_count = 6
    _roi_y_start = 0.25
    _roi_y_end = 0.455
    _roi_x_start = 0.18
    _roi_x_end = 0.80
    _minimum_component_height = 0.006
    _maximum_component_height = 0.0125
    _minimum_component_width = 0.008
    _maximum_component_width = 0.045
    _minimum_component_area = 0.000058
    _minimum_fill_ratio = 0.57
    _maximum_width_to_height_ratio: float | None = None
    _candidate_limit: int | None = None
    _horizontal_padding_ratio = 0.35
    _vertical_padding_ratio = 0.25

    def __init__(
        self,
        recognizer: SequenceNumberRecognizer,
        *,
        telemetry: StageTimingCollector | None = None,
    ) -> None:
        self._recognizer = recognizer
        self._telemetry = telemetry

    def recognize(
        self,
        rgb_image: NDArray[np.uint8],
        boards: tuple[BoardDetection, ...],
    ) -> tuple[SequenceRange | None, tuple[str, ...]]:
        del boards
        labels = self._label_candidates(rgb_image)
        if len(labels) < self._minimum_inlier_count:
            return None, ("RANGE_LABEL_LATTICE_MISSING",)
        try:
            recognitions = self._recognize_many(tuple(label.crop for label in labels))
        except (SequenceOcrError, ValueError):
            return None, ("RANGE_LABEL_OCR_FAILED",)
        return self._resolve_range(labels, recognitions, rgb_image.shape[:2])

    @classmethod
    def _resolve_range(
        cls,
        labels: Sequence[_VisibleLabel],
        recognitions: Sequence[Recognition],
        image_shape: tuple[int, int],
    ) -> tuple[SequenceRange | None, tuple[str, ...]]:
        hypotheses = cls._range_hypotheses(labels, recognitions, image_shape)
        if not hypotheses:
            return None, ("RANGE_LABEL_LATTICE_INCOMPLETE",)
        best_score, best_range = hypotheses[0]
        if len(hypotheses) > 1 and hypotheses[1][0] == best_score:
            return None, ("RANGE_LABEL_LATTICE_AMBIGUOUS",)
        return best_range, ()

    def _recognize_many(
        self,
        crops: tuple[NDArray[np.uint8], ...],
    ) -> tuple[Recognition, ...]:
        recognize_many = getattr(self._recognizer, "recognize_many", None)
        if not callable(recognize_many):
            if self._telemetry is not None:
                self._telemetry.increment("ocrCalls", len(crops))
                self._telemetry.increment("ocrCrops", len(crops))
            return tuple(self._recognizer.recognize(crop) for crop in crops)
        results: list[Recognition] = []
        for offset in range(0, len(crops), 9):
            batch = crops[offset : offset + 9]
            if self._telemetry is not None:
                self._telemetry.increment("ocrCalls")
                self._telemetry.increment("ocrCrops", len(batch))
            results.extend(recognize_many(batch))
        return tuple(results)

    @classmethod
    def _label_candidates(
        cls,
        rgb_image: NDArray[np.uint8],
    ) -> tuple[_VisibleLabel, ...]:
        selected = list(cls._ranked_label_candidates(rgb_image))
        selected.sort(key=lambda value: (value.center[1], value.center[0]))
        return tuple(selected)

    @classmethod
    def _ranked_label_candidates(
        cls,
        rgb_image: NDArray[np.uint8],
    ) -> tuple[_VisibleLabel, ...]:
        height, width = rgb_image.shape[:2]
        hsv = np.asarray(cv2.cvtColor(rgb_image, cv2.COLOR_RGB2HSV), dtype=np.uint8)
        mask = cls._label_mask(hsv)
        y_start = int(round(height * cls._roi_y_start))
        y_end = int(round(height * cls._roi_y_end))
        x_start = int(round(width * cls._roi_x_start))
        x_end = int(round(width * cls._roi_x_end))
        region = np.zeros_like(mask)
        region[y_start:y_end, x_start:x_end] = mask[y_start:y_end, x_start:x_end]
        kernel_width = max(3, int(round(width * 0.0065)) | 1)
        kernel_height = max(1, int(round(height * 0.0016)) | 1)
        closed = cv2.morphologyEx(
            region,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_width, kernel_height)),
        )
        count, _, stats, centroids = cv2.connectedComponentsWithStats(
            closed,
            connectivity=8,
        )
        minimum_area = max(24, int(round(width * height * cls._minimum_component_area)))
        labels: list[tuple[tuple[float, int], _VisibleLabel]] = []
        for index in range(1, count):
            x, y, component_width, component_height, area = (int(value) for value in stats[index])
            if (
                not int(round(height * cls._minimum_component_height))
                <= component_height
                <= int(round(height * cls._maximum_component_height))
            ):
                continue
            if (
                not int(round(width * cls._minimum_component_width))
                <= component_width
                <= int(round(width * cls._maximum_component_width))
            ):
                continue
            if (
                cls._maximum_width_to_height_ratio is not None
                and component_width / component_height > cls._maximum_width_to_height_ratio
            ):
                continue
            fill_ratio = area / (component_width * component_height)
            if area < minimum_area or fill_ratio < cls._minimum_fill_ratio:
                continue
            pad_x = max(2, int(round(component_height * cls._horizontal_padding_ratio)))
            pad_y = max(2, int(round(component_height * cls._vertical_padding_ratio)))
            left = max(0, x - pad_x)
            top = max(0, y - pad_y)
            right = min(width, x + component_width + pad_x)
            bottom = min(height, y + component_height + pad_y)
            crop = rgb_image[top:bottom, left:right]
            if crop.size:
                labels.append(
                    (
                        (fill_ratio, area),
                        _VisibleLabel(
                            crop=crop,
                            center=(float(centroids[index][0]), float(centroids[index][1])),
                        ),
                    )
                )
        labels.sort(
            key=lambda value: (
                -value[0][0],
                -value[0][1],
                value[1].center[1],
                value[1].center[0],
            )
        )
        if cls._candidate_limit is not None:
            labels = labels[: cls._candidate_limit]
        return tuple(value[1] for value in labels)

    @classmethod
    def _label_mask(cls, hsv: NDArray[np.uint8]) -> NDArray[np.uint8]:
        del cls
        return np.asarray(
            cv2.inRange(hsv, np.array((0, 0, 165)), np.array((179, 115, 255))),
            dtype=np.uint8,
        )

    @classmethod
    def _range_hypotheses(
        cls,
        labels: Sequence[_VisibleLabel],
        recognitions: Sequence[Recognition],
        image_shape: tuple[int, int],
    ) -> list[tuple[tuple[int, int], SequenceRange]]:
        if len(labels) != len(recognitions):
            return []
        evidence: list[tuple[int, tuple[float, float], float]] = []
        for label, recognition in zip(labels, recognitions, strict=True):
            number = recognition.normalized_number
            if (
                number is not None
                and number >= 1
                and recognition.confidence >= cls._minimum_ocr_confidence
            ):
                evidence.append((number, label.center, recognition.confidence))
        candidates: list[tuple[tuple[int, int], SequenceRange]] = []
        starts = {number - position for number, _, _ in evidence for position in range(9)}
        height, width = image_shape
        ransac_threshold = max(8.0, min(width, height) * 0.018)
        for start in sorted(value for value in starts if value >= 1):
            by_position: dict[int, tuple[tuple[float, float], float]] = {}
            for number, center, confidence in evidence:
                position = number - start
                if not 0 <= position < 9:
                    continue
                current = by_position.get(position)
                if current is None or confidence > current[1]:
                    by_position[position] = (center, confidence)
            positions = tuple(sorted(by_position))
            if (
                len(positions) < cls._minimum_inlier_count
                or positions[0] != 0
                or positions[-1] != 8
                or len({position // 3 for position in positions}) < 3
                or len({position % 3 for position in positions}) < 3
            ):
                continue
            canonical = np.asarray(
                [(position % 3, position // 3) for position in positions],
                dtype=np.float32,
            )
            observed = np.asarray(
                [by_position[position][0] for position in positions],
                dtype=np.float32,
            )
            _, inlier_mask = cv2.findHomography(
                canonical,
                observed,
                cv2.RANSAC,
                ransac_threshold,
            )
            if inlier_mask is None:
                continue
            inlier_positions = tuple(
                position
                for position, is_inlier in zip(
                    positions,
                    inlier_mask.reshape(-1),
                    strict=True,
                )
                if bool(is_inlier)
            )
            if (
                len(inlier_positions) < cls._minimum_inlier_count
                or 0 not in inlier_positions
                or 8 not in inlier_positions
            ):
                continue
            mean_confidence = sum(by_position[position][1] for position in inlier_positions) / len(
                inlier_positions
            )
            structural_confidence = min(
                1.0,
                0.90 + 0.025 * (len(inlier_positions) - cls._minimum_inlier_count),
            )
            confidence = round(
                min(0.999999, structural_confidence * 0.65 + mean_confidence * 0.35),
                6,
            )
            score = (len(inlier_positions), int(round(mean_confidence * 1000)))
            candidates.append(
                (score, SequenceRange(start=start, end=start + 8, confidence=confidence))
            )
        return sorted(
            candidates,
            key=lambda value: (value[0], -value[1].start),
            reverse=True,
        )


class AdaptiveVisibleSequenceLabelRangeRecognizer(VisibleSequenceLabelRangeRecognizer):
    """Bounded fallback for perspective-shifted labels with up to six digits."""

    version = "visible-sequence-label-range-v2"
    _roi_y_start = 0.22
    _roi_y_end = 0.50
    _roi_x_start = 0.14
    _roi_x_end = 0.86
    _minimum_component_height = 0.005
    _maximum_component_height = 0.0145
    _maximum_component_width = 0.105
    _minimum_component_area = 0.000045
    _minimum_fill_ratio = 0.50
    _maximum_width_to_height_ratio = 7.5
    _candidate_limit = 36


class BestEffortVisibleSequenceLabelRangeRecognizer(AdaptiveVisibleSequenceLabelRangeRecognizer):
    """Read tinted or dim labels when the board image itself is imperfect."""

    version = "visible-sequence-label-range-v3"
    _minimum_ocr_confidence = 0.50
    _roi_y_start = 0.20
    _roi_y_end = 0.52
    _roi_x_start = 0.10
    _roi_x_end = 0.90
    _minimum_component_height = 0.004
    _maximum_component_height = 0.017
    _minimum_component_width = 0.006
    _maximum_component_width = 0.12
    _minimum_component_area = 0.000018
    _minimum_fill_ratio = 0.20
    _candidate_limit = 48

    @classmethod
    def _label_mask(cls, hsv: NDArray[np.uint8]) -> NDArray[np.uint8]:
        del cls
        neutral = cv2.inRange(
            hsv,
            np.array((0, 0, 145)),
            np.array((179, 150, 255)),
        )
        warm = cv2.inRange(
            hsv,
            np.array((5, 151, 145)),
            np.array((40, 255, 255)),
        )
        return np.asarray(cv2.bitwise_or(neutral, warm), dtype=np.uint8)


class AccuracyFirstVisibleSequenceLabelRangeRecognizer(
    BestEffortVisibleSequenceLabelRangeRecognizer
):
    """Preserve complete multi-digit labels for accuracy-first selection."""

    version = "visible-sequence-label-range-v4"
    _roi_y_start = 0.18
    _roi_y_end = 0.55
    _roi_x_start = 0.06
    _roi_x_end = 0.94
    _maximum_component_width = 0.16
    _maximum_width_to_height_ratio = 10.0
    _candidate_limit = 72
    _horizontal_padding_ratio = 0.70
    _vertical_padding_ratio = 0.40


class ProgressiveVisibleSequenceLabelRangeRecognizer(
    AccuracyFirstVisibleSequenceLabelRangeRecognizer
):
    """Evaluate the same bounded label set in progressively larger OCR stages."""

    version = "visible-sequence-label-range-v5"

    def __init__(
        self,
        recognizer: SequenceNumberRecognizer,
        policy: ProgressiveVisibleLabelFallbackPolicy,
        *,
        telemetry: StageTimingCollector | None = None,
    ) -> None:
        super().__init__(recognizer, telemetry=telemetry)
        self._candidate_levels = policy.candidate_levels

    def recognize(
        self,
        rgb_image: NDArray[np.uint8],
        boards: tuple[BoardDetection, ...],
    ) -> tuple[SequenceRange | None, tuple[str, ...]]:
        del boards
        labels = self._ranked_label_candidates(rgb_image)
        if len(labels) < self._minimum_inlier_count:
            return None, ("RANGE_LABEL_LATTICE_MISSING",)

        recognitions: list[Recognition] = []
        last_reasons: tuple[str, ...] = ("RANGE_LABEL_LATTICE_INCOMPLETE",)
        previous_count = 0
        for configured_level in self._candidate_levels:
            candidate_count = min(configured_level, len(labels))
            if candidate_count <= previous_count:
                continue
            batch_labels = labels[previous_count:candidate_count]
            self._record_level_attempt(configured_level, len(batch_labels))
            try:
                recognitions.extend(
                    self._recognize_many(tuple(label.crop for label in batch_labels))
                )
            except (SequenceOcrError, ValueError):
                return None, ("RANGE_LABEL_OCR_FAILED",)
            recognized_range, last_reasons = self._resolve_range(
                labels[:candidate_count],
                recognitions,
                rgb_image.shape[:2],
            )
            if recognized_range is not None:
                self._record_level_resolution(configured_level, candidate_count)
                return recognized_range, ()
            previous_count = candidate_count
            if candidate_count == len(labels):
                break

        if self._telemetry is not None:
            self._telemetry.increment("progressiveFallbackExhausted")
        return None, last_reasons

    def _record_level_attempt(self, configured_level: int, added_crops: int) -> None:
        if self._telemetry is None:
            return
        self._telemetry.increment("progressiveFallbackLevelsAttempted")
        self._telemetry.increment(f"progressiveFallbackLevel{configured_level}Attempts")
        self._telemetry.increment("progressiveFallbackCrops", added_crops)

    def _record_level_resolution(self, configured_level: int, crop_count: int) -> None:
        if self._telemetry is None:
            return
        self._telemetry.increment(f"progressiveFallbackResolvedAtLevel{configured_level}")
        self._telemetry.increment("progressiveFallbackResolvedCropCount", crop_count)


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
        fallback_range_recognizer: SequenceRangeRecognizer | None = None,
        detector: PageBoardDetector | None = None,
        *,
        allow_grid_recovery: bool = False,
        couple_fallback_to_representative: bool = True,
        full_geometry_policy: FullGeometryPolicy | None = None,
        telemetry: StageTimingCollector | None = None,
    ) -> None:
        self._source_root = source_root.resolve(strict=True)
        self._range_recognizer = range_recognizer
        self._fallback_range_recognizer = fallback_range_recognizer
        self._detector = detector or ClassicalPageBoardDetector()
        self._allow_grid_recovery = allow_grid_recovery
        self._couple_fallback_to_representative = couple_fallback_to_representative
        self._full_geometry_policy = full_geometry_policy
        self._telemetry = telemetry

    def verify(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        return self._verify(
            observation,
            expected_board_count=expected_board_count,
            include_range_evidence=True,
        )

    def assess_representative(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        return self._verify(
            observation,
            expected_board_count=expected_board_count,
            include_range_evidence=False,
        )

    def _verify(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
        include_range_evidence: bool,
    ) -> CandidateVerification:
        if include_range_evidence and self._telemetry is not None:
            self._telemetry.increment("rangeEvidenceVerifications")
        try:
            path = _safe_source_path(
                self._source_root,
                observation.source.stored_relative_path,
            )
            rgb = _load_verified_rgb(
                path,
                observation.source.checksum_sha256,
                self._telemetry,
            )
            timing = (
                self._telemetry.measure("geometry")
                if self._telemetry is not None
                else nullcontext()
            )
            with timing:
                detection = _best_supported_detection(
                    self._detector,
                    rgb,
                    expected_board_count=expected_board_count,
                    allow_grid_recovery=self._allow_grid_recovery,
                    telemetry=self._telemetry,
                )
        except (SelectionContractError, StatisticsError) as error:
            return CandidateVerification(
                representative=RepresentativeAssessment(
                    board_count=None,
                    geometry_complete=False,
                    full_frame_visible=False,
                    reason_codes=(
                        error.code
                        if isinstance(error, SelectionContractError)
                        else "IMAGE_SELECTION_VERIFY_GEOMETRY_FAILED",
                    ),
                ),
                range_evidence=RangeEvidence(recognized_range=None),
            )
        detected_board_count = len(detection.boards)
        expected_geometry_complete = (
            expected_board_count is not None and detected_board_count == expected_board_count
        )
        local_geometry_complete = self._is_stable_local_geometry(
            detection,
            expected_board_count=expected_board_count,
        )
        geometry_complete = detection.status == "detected" and (
            expected_geometry_complete or local_geometry_complete
        )
        full_frame_visible = geometry_complete and self._full_frame_visible(
            detection, rgb.shape[1], rgb.shape[0]
        )
        recognized_range: SequenceRange | None = None
        range_reasons: tuple[str, ...] = ()
        if include_range_evidence and geometry_complete:
            if self._telemetry is not None:
                self._telemetry.increment("anchoredOcrAttempts")
            timing = (
                self._telemetry.measure("ocr") if self._telemetry is not None else nullcontext()
            )
            with timing:
                recognized_range, range_reasons = self._range_recognizer.recognize(
                    rgb,
                    detection.boards,
                )
            if self._telemetry is not None:
                self._telemetry.increment(
                    "anchoredOcrSuccesses"
                    if recognized_range is not None
                    else "anchoredOcrFailures"
                )
        if (
            include_range_evidence
            and recognized_range is None
            and self._fallback_range_recognizer is not None
        ):
            if self._telemetry is not None:
                self._telemetry.increment("fallbackOcrAttempts")
            timing = (
                self._telemetry.measure("ocr") if self._telemetry is not None else nullcontext()
            )
            with timing:
                fallback_range, fallback_reasons = self._fallback_range_recognizer.recognize(
                    rgb,
                    detection.boards,
                )
            if fallback_range is not None:
                recognized_range = fallback_range
                if self._couple_fallback_to_representative:
                    geometry_complete = True
                    full_frame_visible = True
                range_reasons = ()
                if self._telemetry is not None:
                    self._telemetry.increment("fallbackOcrSuccesses")
            else:
                range_reasons = tuple(dict.fromkeys((*range_reasons, *fallback_reasons)))
                if self._telemetry is not None:
                    self._telemetry.increment("fallbackOcrFailures")
        if not include_range_evidence:
            range_reasons = ("RANGE_EVIDENCE_NOT_REQUESTED",)
        elif recognized_range is None:
            detection_reasons = tuple(detection.review_reasons) or (
                "BOARD_COUNT_CONSENSUS_UNKNOWN"
                if expected_board_count is None
                else "GEOMETRY_INCOMPLETE",
            )
            range_reasons = tuple(dict.fromkeys((*detection_reasons, *range_reasons)))
        return CandidateVerification(
            representative=RepresentativeAssessment(
                board_count=(
                    recognized_range.board_count
                    if self._couple_fallback_to_representative and recognized_range is not None
                    else (len(detection.boards) or None)
                ),
                geometry_complete=geometry_complete,
                full_frame_visible=full_frame_visible,
            ),
            range_evidence=RangeEvidence(
                recognized_range=recognized_range,
                reason_codes=range_reasons,
            ),
        )

    def record_adaptive_range_stop(
        self,
        reason: str,
        *,
        evidence_count: int,
        candidate_count: int,
    ) -> None:
        if self._telemetry is None:
            return
        counter = {
            "confirmed": "rangeConsensusConfirmed",
            "conflict_exhausted": "rangeConsensusConflictExhausted",
            "no_consensus_exhausted": "rangeConsensusNoConsensusExhausted",
        }.get(reason)
        if counter is None:
            raise ValueError(f"Unsupported adaptive range stop reason: {reason}")
        self._telemetry.increment(counter)
        self._telemetry.increment("rangeConsensusEvidenceCount", evidence_count)
        self._telemetry.increment("rangeConsensusCandidateCount", candidate_count)

    @staticmethod
    def _full_frame_visible(detection: DetectionResult, width: int, height: int) -> bool:
        if detection.page_quad is None:
            return False
        margin = max(1, int(round(min(width, height) * 0.002)))
        return all(
            margin <= point.x < width - margin and margin <= point.y < height - margin
            for point in detection.page_quad
        )

    def _is_stable_local_geometry(
        self,
        detection: DetectionResult,
        *,
        expected_board_count: int | None,
    ) -> bool:
        policy = self._full_geometry_policy
        if policy is None or expected_board_count is not None:
            return False
        board_count = len(detection.boards)
        return (
            detection.status == "detected"
            and policy.minimum_board_count <= board_count <= policy.maximum_board_count
            and detection.confidence >= policy.minimum_confidence
        )


class DeterministicParallelCandidateVerifier:
    """Run bounded candidate batches on isolated verifier instances."""

    def __init__(
        self,
        verifiers: tuple[CandidateVerifier, ...],
        *,
        telemetry: StageTimingCollector | None = None,
    ) -> None:
        if not 1 <= len(verifiers) <= 2:
            raise ValueError("Candidate verification supports one or two isolated workers.")
        if len({id(verifier) for verifier in verifiers}) != len(verifiers):
            raise ValueError("Parallel candidate workers must use distinct verifier instances.")
        self._verifiers = verifiers
        self._telemetry = telemetry

    @property
    def worker_count(self) -> int:
        return len(self._verifiers)

    def verify(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        return self._verifiers[0].verify(
            observation,
            expected_board_count=expected_board_count,
        )

    def assess_representative(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        return self._assess(
            self._verifiers[0],
            observation,
            expected_board_count=expected_board_count,
        )

    def verify_many(
        self,
        observations: tuple[CheapImageObservation, ...],
        *,
        expected_board_count: int | None,
        include_range_evidence: bool,
    ) -> tuple[CandidateVerification, ...]:
        if not observations:
            return ()
        worker_count = min(len(self._verifiers), len(observations))
        if self._telemetry is not None:
            self._telemetry.increment("parallelVerificationBatches")
            self._telemetry.increment("parallelVerificationItems", len(observations))
            self._telemetry.increment("parallelVerificationWorkerSlots", worker_count)
        partitions: list[list[tuple[int, CheapImageObservation]]] = [
            [] for _ in range(worker_count)
        ]
        for index, observation in enumerate(observations):
            partitions[index % worker_count].append((index, observation))
        ordered: list[CandidateVerification | None] = [None] * len(observations)
        partition_results: tuple[tuple[tuple[int, CandidateVerification], ...], ...]
        if worker_count == 1:
            partition_results = (
                self._verify_partition(
                    self._verifiers[0],
                    tuple(partitions[0]),
                    expected_board_count=expected_board_count,
                    include_range_evidence=include_range_evidence,
                ),
            )
        else:
            with ThreadPoolExecutor(
                max_workers=worker_count,
                thread_name_prefix="candidate-verifier",
            ) as executor:
                futures = tuple(
                    executor.submit(
                        self._verify_partition,
                        self._verifiers[worker_index],
                        tuple(partition),
                        expected_board_count=expected_board_count,
                        include_range_evidence=include_range_evidence,
                    )
                    for worker_index, partition in enumerate(partitions)
                )
                partition_results = tuple(future.result() for future in futures)
        for partition in partition_results:
            for index, verification in partition:
                ordered[index] = verification
        if any(verification is None for verification in ordered):
            raise SelectionContractError(
                "IMAGE_SELECTION_VERIFY_RESULT_INVALID",
                "Parallel candidate verification returned an incomplete batch.",
            )
        return tuple(cast(CandidateVerification, verification) for verification in ordered)

    @classmethod
    def _verify_partition(
        cls,
        verifier: CandidateVerifier,
        partition: tuple[tuple[int, CheapImageObservation], ...],
        *,
        expected_board_count: int | None,
        include_range_evidence: bool,
    ) -> tuple[tuple[int, CandidateVerification], ...]:
        results: list[tuple[int, CandidateVerification]] = []
        for index, observation in partition:
            verification = (
                verifier.verify(
                    observation,
                    expected_board_count=expected_board_count,
                )
                if include_range_evidence
                else cls._assess(
                    verifier,
                    observation,
                    expected_board_count=expected_board_count,
                )
            )
            if not isinstance(verification, CandidateVerification):
                raise SelectionContractError(
                    "IMAGE_SELECTION_VERIFY_RESULT_INVALID",
                    "Parallel candidate verification returned an invalid result.",
                )
            results.append((index, verification))
        return tuple(results)

    @staticmethod
    def _assess(
        verifier: CandidateVerifier,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        assess = getattr(verifier, "assess_representative", None)
        result = (
            assess(observation, expected_board_count=expected_board_count)
            if callable(assess)
            else verifier.verify(
                observation,
                expected_board_count=expected_board_count,
            )
        )
        if not isinstance(result, CandidateVerification):
            raise SelectionContractError(
                "IMAGE_SELECTION_VERIFY_RESULT_INVALID",
                "Representative assessment returned an invalid result.",
            )
        return CandidateVerification(
            representative=result.representative,
            range_evidence=RangeEvidence(
                recognized_range=None,
                reason_codes=("RANGE_EVIDENCE_NOT_REQUESTED",),
            ),
        )

    def record_adaptive_range_stop(
        self,
        reason: str,
        *,
        evidence_count: int,
        candidate_count: int,
    ) -> None:
        record = getattr(self._verifiers[0], "record_adaptive_range_stop", None)
        if callable(record):
            record(
                reason,
                evidence_count=evidence_count,
                candidate_count=candidate_count,
            )


def build_default_adapters(
    source_root: Path,
    *,
    range_recognizer: SequenceRangeRecognizer | None = None,
    fallback_range_recognizer: SequenceRangeRecognizer | None = None,
    manifest: SelectorManifest = DEFAULT_SELECTOR_MANIFEST,
    telemetry: StageTimingCollector | None = None,
) -> tuple[CheapImageAnalyzer, CandidateVerifier]:
    thumbnail_loader = PillowThumbnailLoader(
        source_root,
        max_edge=manifest.thumbnail_max_edge,
        adapter_version=manifest.thumbnail_adapter_version,
        telemetry=telemetry,
    )
    if manifest.algorithm_version in APPEARANCE_GROUPING_SELECTOR_VERSIONS:
        analyzer = ComposedCheapImageAnalyzer(
            thumbnail_loader,
            OpenCvAppearanceFingerprintAnalyzer(
                manifest.appearance_descriptor,
                telemetry=telemetry,
            ),
            (
                OpenCvAccuracyFirstQualityAnalyzer(
                    manifest.quality_weights,
                    manifest.appearance_descriptor,
                    telemetry=telemetry,
                )
                if manifest.algorithm_version in ACCURACY_FIRST_SELECTOR_VERSIONS
                else OpenCvAppearanceQualityAnalyzer(
                    manifest.quality_weights,
                    manifest.appearance_descriptor,
                    telemetry=telemetry,
                )
            ),
        )
        if manifest.algorithm_version in APPEARANCE_ONLY_SELECTOR_VERSIONS:
            return analyzer, AppearanceOnlyCandidateVerifier()
        detector = ClassicalPageBoardDetector()
        return (
            analyzer,
            FullCandidateVerifier(
                source_root,
                range_recognizer or NoRangeRecognizer(),
                fallback_range_recognizer,
                detector,
                allow_grid_recovery=True,
                couple_fallback_to_representative=(
                    manifest.algorithm_version != ADAPTIVE_ACCURACY_SELECTOR_VERSION
                ),
                full_geometry_policy=manifest.full_geometry_policy,
                telemetry=telemetry,
            ),
        )
    detector = ClassicalPageBoardDetector()
    analyzer = ComposedCheapImageAnalyzer(
        thumbnail_loader,
        OpenCvLatticeFingerprintAnalyzer(detector, telemetry=telemetry),
        OpenCvImageQualityAnalyzer(manifest.quality_weights, telemetry=telemetry),
    )
    verifier = FullCandidateVerifier(
        source_root,
        range_recognizer or NoRangeRecognizer(),
        fallback_range_recognizer,
        detector,
        allow_grid_recovery=manifest.algorithm_version in ORDERED_SELECTOR_VERSIONS,
        telemetry=telemetry,
    )
    return analyzer, verifier


__all__ = [
    "AdaptiveVisibleSequenceLabelRangeRecognizer",
    "AccuracyFirstVisibleSequenceLabelRangeRecognizer",
    "AnchoredSequenceRangeRecognizer",
    "AppearanceOnlyCandidateVerifier",
    "BestEffortVisibleSequenceLabelRangeRecognizer",
    "ComposedCheapImageAnalyzer",
    "DeterministicParallelCandidateVerifier",
    "FullCandidateVerifier",
    "NoRangeRecognizer",
    "OpenCvImageQualityAnalyzer",
    "OpenCvAppearanceFingerprintAnalyzer",
    "OpenCvAppearanceQualityAnalyzer",
    "OpenCvAccuracyFirstQualityAnalyzer",
    "OpenCvLatticeFingerprintAnalyzer",
    "OPENCV_INTERNAL_THREAD_BUDGET",
    "PillowThumbnailLoader",
    "ProgressiveVisibleSequenceLabelRangeRecognizer",
    "VisibleSequenceLabelRangeRecognizer",
    "build_default_adapters",
    "configure_opencv_thread_budget",
]
