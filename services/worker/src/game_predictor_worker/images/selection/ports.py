"""Replaceable image-processing ports for the selector adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from game_predictor_worker.images.geometry import BoardDetection

from .contracts import ImageQualityMetrics, ImageSelectionSource, SequenceRange


@dataclass(frozen=True, slots=True)
class ThumbnailFrame:
    rgb: NDArray[np.uint8]
    source_width: int
    source_height: int


@dataclass(frozen=True, slots=True)
class LatticeFingerprint:
    fingerprint_hex: str
    geometry_signature: tuple[float, ...]
    board_count: int | None
    geometry_confidence: float
    boards: tuple[BoardDetection, ...]
    reason_codes: tuple[str, ...]


class ThumbnailLoader(Protocol):
    version: str

    def load(self, source: ImageSelectionSource) -> ThumbnailFrame:
        """Verify, EXIF-transpose and downscale one JPEG."""


class ImageQualityAnalyzer(Protocol):
    version: str

    def measure(
        self,
        frame: ThumbnailFrame,
        lattice: LatticeFingerprint,
    ) -> ImageQualityMetrics:
        """Return normalized, deterministic quality metrics."""


class LatticeFingerprintAnalyzer(Protocol):
    version: str

    def analyze(self, frame: ThumbnailFrame) -> LatticeFingerprint:
        """Return cheap page geometry and a visual fingerprint."""


class SequenceRangeRecognizer(Protocol):
    version: str

    def recognize(
        self,
        rgb_image: NDArray[np.uint8],
        boards: tuple[BoardDetection, ...],
    ) -> tuple[SequenceRange | None, tuple[str, ...]]:
        """Recognize bounded first/middle/last sequence anchors."""


__all__ = [
    "ImageQualityAnalyzer",
    "LatticeFingerprint",
    "LatticeFingerprintAnalyzer",
    "SequenceRangeRecognizer",
    "ThumbnailFrame",
    "ThumbnailLoader",
]
