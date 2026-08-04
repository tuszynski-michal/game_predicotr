"""Versioned manifest and fingerprint for the fast image selector."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

LEGACY_SELECTOR_VERSION = "fast-image-selector-v2"
CONTINUITY_SELECTOR_VERSION = "fast-image-selector-v3"
BEST_AVAILABLE_SELECTOR_VERSION = "fast-image-selector-v4"
DIGIT_AWARE_SELECTOR_VERSION = "fast-image-selector-v5"
EXACT_GAP_SELECTOR_VERSION = "fast-image-selector-v6"
BEST_EFFORT_SELECTOR_VERSION = "fast-image-selector-v7"
FIRST_USABLE_SELECTOR_VERSION = "fast-image-selector-v8"
SELECTOR_VERSION = FIRST_USABLE_SELECTOR_VERSION
BEST_AVAILABLE_SELECTOR_VERSIONS = frozenset(
    {
        BEST_AVAILABLE_SELECTOR_VERSION,
        DIGIT_AWARE_SELECTOR_VERSION,
        EXACT_GAP_SELECTOR_VERSION,
        BEST_EFFORT_SELECTOR_VERSION,
        SELECTOR_VERSION,
    }
)
ORDERED_SELECTOR_VERSIONS = frozenset(
    {
        DIGIT_AWARE_SELECTOR_VERSION,
        EXACT_GAP_SELECTOR_VERSION,
        BEST_EFFORT_SELECTOR_VERSION,
        SELECTOR_VERSION,
    }
)
SUPPORTED_SELECTOR_VERSIONS = frozenset(
    {
        LEGACY_SELECTOR_VERSION,
        CONTINUITY_SELECTOR_VERSION,
        BEST_AVAILABLE_SELECTOR_VERSION,
        DIGIT_AWARE_SELECTOR_VERSION,
        EXACT_GAP_SELECTOR_VERSION,
        BEST_EFFORT_SELECTOR_VERSION,
        SELECTOR_VERSION,
    }
)

LEGACY_RANGE_ADAPTER_VERSION = (
    "sequence-anchor-range-v1+visible-sequence-label-range-v1:"
    "sequence-number-ocr-v1:en_PP-OCRv5_mobile_rec"
)
ADAPTIVE_RANGE_ADAPTER_VERSION = (
    "sequence-anchor-range-v1+visible-sequence-label-range-v2:"
    "sequence-number-ocr-v1:en_PP-OCRv5_mobile_rec"
)
BEST_EFFORT_RANGE_ADAPTER_VERSION = (
    "sequence-anchor-range-v1+visible-sequence-label-range-v3:"
    "sequence-number-ocr-v1:en_PP-OCRv5_mobile_rec"
)
BEST_EFFORT_SELECTOR_VERSIONS = frozenset({BEST_EFFORT_SELECTOR_VERSION, SELECTOR_VERSION})
FIRST_USABLE_SELECTOR_VERSIONS = frozenset({FIRST_USABLE_SELECTOR_VERSION})
EXACT_MULTI_GAP_SELECTOR_VERSIONS = frozenset(
    {EXACT_GAP_SELECTOR_VERSION, BEST_EFFORT_SELECTOR_VERSION, SELECTOR_VERSION}
)


@dataclass(frozen=True, slots=True)
class QualityWeights:
    sharpness: float = 0.24
    exposure: float = 0.13
    highlight_retention: float = 0.10
    glare_resistance: float = 0.10
    perspective: float = 0.13
    border_margin: float = 0.10
    board_visibility: float = 0.20


@dataclass(frozen=True, slots=True)
class SelectorThresholds:
    fingerprint_change_distance: float = 0.035
    strong_fingerprint_change_distance: float = 0.055
    same_group_fingerprint_distance: float = 0.030
    duplicate_fingerprint_distance: float = 0.020
    geometry_change_distance: float = 0.14
    minimum_geometry_confidence: float = 0.64
    minimum_quality_score: float = 0.62
    minimum_sharpness: float = 0.18
    minimum_exposure: float = 0.45
    minimum_highlight_retention: float = 0.88
    minimum_glare_resistance: float = 0.72
    minimum_border_margin: float = 0.45
    minimum_range_confidence: float = 0.90


@dataclass(frozen=True, slots=True)
class FirstUsablePolicy:
    minimum_quality_score: float = 0.30
    minimum_sharpness: float = 0.10


FIRST_USABLE_POLICY = FirstUsablePolicy()


@dataclass(frozen=True, slots=True)
class SelectorManifest:
    algorithm_version: str = SELECTOR_VERSION
    contract_version: int = 1
    thumbnail_max_edge: int = 960
    scan_batch_size: int = 32
    top_k: int = 3
    boundary_confirmation_count: int = 2
    quality_adapter_version: str = "opencv-thumbnail-quality-v1"
    geometry_adapter_version: str = "page-board-detector-v2"
    fingerprint_adapter_version: str = "screen-layout-hsv-hash-v2"
    range_adapter_version: str = BEST_EFFORT_RANGE_ADAPTER_VERSION
    quality_weights: QualityWeights = QualityWeights()
    thresholds: SelectorThresholds = SelectorThresholds()

    def __post_init__(self) -> None:
        if self.algorithm_version not in SUPPORTED_SELECTOR_VERSIONS or self.contract_version != 1:
            raise ValueError("Unsupported image selector manifest version.")
        if not 320 <= self.thumbnail_max_edge <= 2048:
            raise ValueError("thumbnail_max_edge must be between 320 and 2048.")
        if not 1 <= self.scan_batch_size <= 256:
            raise ValueError("scan_batch_size must be between 1 and 256.")
        if not 1 <= self.top_k <= 10:
            raise ValueError("top_k must be between 1 and 10.")
        if not 1 <= self.boundary_confirmation_count <= 10:
            raise ValueError("boundary_confirmation_count must be between 1 and 10.")
        weight_sum = sum(asdict(self.quality_weights).values())
        if abs(weight_sum - 1.0) > 1e-9:
            raise ValueError("Image selector quality weights must sum to 1.0.")
        for value in asdict(self.thresholds).values():
            if not 0 <= value <= 1:
                raise ValueError("Image selector thresholds must be between 0 and 1.")

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "adapters": {
                "fingerprint": self.fingerprint_adapter_version,
                "geometry": self.geometry_adapter_version,
                "quality": self.quality_adapter_version,
                "range": self.range_adapter_version,
            },
            "algorithmVersion": self.algorithm_version,
            "boundaryConfirmationCount": self.boundary_confirmation_count,
            "contractVersion": self.contract_version,
            "qualityWeights": {
                "boardVisibility": self.quality_weights.board_visibility,
                "borderMargin": self.quality_weights.border_margin,
                "exposure": self.quality_weights.exposure,
                "glareResistance": self.quality_weights.glare_resistance,
                "highlightRetention": self.quality_weights.highlight_retention,
                "perspective": self.quality_weights.perspective,
                "sharpness": self.quality_weights.sharpness,
            },
            "scanBatchSize": self.scan_batch_size,
            "thresholds": {
                "duplicateFingerprintDistance": (self.thresholds.duplicate_fingerprint_distance),
                "fingerprintChangeDistance": self.thresholds.fingerprint_change_distance,
                "geometryChangeDistance": self.thresholds.geometry_change_distance,
                "minimumBorderMargin": self.thresholds.minimum_border_margin,
                "minimumExposure": self.thresholds.minimum_exposure,
                "minimumGeometryConfidence": (self.thresholds.minimum_geometry_confidence),
                "minimumGlareResistance": self.thresholds.minimum_glare_resistance,
                "minimumHighlightRetention": (self.thresholds.minimum_highlight_retention),
                "minimumQualityScore": self.thresholds.minimum_quality_score,
                "minimumRangeConfidence": self.thresholds.minimum_range_confidence,
                "minimumSharpness": self.thresholds.minimum_sharpness,
                "sameGroupFingerprintDistance": (self.thresholds.same_group_fingerprint_distance),
                "strongFingerprintChangeDistance": (
                    self.thresholds.strong_fingerprint_change_distance
                ),
            },
            "thumbnailMaxEdge": self.thumbnail_max_edge,
            "topK": self.top_k,
        }
        if self.algorithm_version in FIRST_USABLE_SELECTOR_VERSIONS:
            payload["firstUsablePolicy"] = {
                "minimumQualityScore": FIRST_USABLE_POLICY.minimum_quality_score,
                "minimumSharpness": FIRST_USABLE_POLICY.minimum_sharpness,
            }
        return payload

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


LEGACY_SELECTOR_MANIFEST_V2 = SelectorManifest(
    algorithm_version=LEGACY_SELECTOR_VERSION,
    range_adapter_version=LEGACY_RANGE_ADAPTER_VERSION,
)
CONTINUITY_SELECTOR_MANIFEST_V3 = SelectorManifest(
    algorithm_version=CONTINUITY_SELECTOR_VERSION,
    range_adapter_version=LEGACY_RANGE_ADAPTER_VERSION,
)
BEST_AVAILABLE_SELECTOR_MANIFEST_V4 = SelectorManifest(
    algorithm_version=BEST_AVAILABLE_SELECTOR_VERSION,
    range_adapter_version=LEGACY_RANGE_ADAPTER_VERSION,
)
DIGIT_AWARE_SELECTOR_MANIFEST_V5 = SelectorManifest(
    algorithm_version=DIGIT_AWARE_SELECTOR_VERSION,
    range_adapter_version=ADAPTIVE_RANGE_ADAPTER_VERSION,
)
EXACT_GAP_SELECTOR_MANIFEST_V6 = SelectorManifest(
    algorithm_version=EXACT_GAP_SELECTOR_VERSION,
    range_adapter_version=ADAPTIVE_RANGE_ADAPTER_VERSION,
)
BEST_EFFORT_SELECTOR_MANIFEST_V7 = SelectorManifest(
    algorithm_version=BEST_EFFORT_SELECTOR_VERSION,
    range_adapter_version=BEST_EFFORT_RANGE_ADAPTER_VERSION,
)
DEFAULT_SELECTOR_MANIFEST = SelectorManifest()
SUPPORTED_SELECTOR_MANIFESTS = (
    DEFAULT_SELECTOR_MANIFEST,
    BEST_EFFORT_SELECTOR_MANIFEST_V7,
    EXACT_GAP_SELECTOR_MANIFEST_V6,
    DIGIT_AWARE_SELECTOR_MANIFEST_V5,
    BEST_AVAILABLE_SELECTOR_MANIFEST_V4,
    CONTINUITY_SELECTOR_MANIFEST_V3,
    LEGACY_SELECTOR_MANIFEST_V2,
)


def selector_manifest_for_fingerprint(fingerprint: str) -> SelectorManifest | None:
    """Resolve immutable selector behavior for a persisted durable run."""

    return next(
        (
            manifest
            for manifest in SUPPORTED_SELECTOR_MANIFESTS
            if manifest.fingerprint == fingerprint
        ),
        None,
    )


__all__ = [
    "ADAPTIVE_RANGE_ADAPTER_VERSION",
    "BEST_EFFORT_RANGE_ADAPTER_VERSION",
    "BEST_EFFORT_SELECTOR_MANIFEST_V7",
    "BEST_EFFORT_SELECTOR_VERSION",
    "BEST_EFFORT_SELECTOR_VERSIONS",
    "BEST_AVAILABLE_SELECTOR_MANIFEST_V4",
    "BEST_AVAILABLE_SELECTOR_VERSION",
    "BEST_AVAILABLE_SELECTOR_VERSIONS",
    "DEFAULT_SELECTOR_MANIFEST",
    "CONTINUITY_SELECTOR_MANIFEST_V3",
    "CONTINUITY_SELECTOR_VERSION",
    "DIGIT_AWARE_SELECTOR_MANIFEST_V5",
    "DIGIT_AWARE_SELECTOR_VERSION",
    "EXACT_GAP_SELECTOR_MANIFEST_V6",
    "EXACT_GAP_SELECTOR_VERSION",
    "EXACT_MULTI_GAP_SELECTOR_VERSIONS",
    "FIRST_USABLE_POLICY",
    "FIRST_USABLE_SELECTOR_VERSION",
    "FIRST_USABLE_SELECTOR_VERSIONS",
    "LEGACY_RANGE_ADAPTER_VERSION",
    "LEGACY_SELECTOR_MANIFEST_V2",
    "LEGACY_SELECTOR_VERSION",
    "ORDERED_SELECTOR_VERSIONS",
    "SELECTOR_VERSION",
    "SUPPORTED_SELECTOR_MANIFESTS",
    "SUPPORTED_SELECTOR_VERSIONS",
    "QualityWeights",
    "FirstUsablePolicy",
    "SelectorManifest",
    "SelectorThresholds",
    "selector_manifest_for_fingerprint",
]
