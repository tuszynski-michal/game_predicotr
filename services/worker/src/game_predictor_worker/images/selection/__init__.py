"""Fast, fail-closed representative image selection."""

from .contracts import (
    CandidateDecision,
    CandidateVerification,
    CheapImageObservation,
    ImageQualityMetrics,
    ImageSelectionResult,
    ImageSelectionSource,
    SelectionGroupResult,
    SelectionGroupStatus,
    SequenceRange,
)
from .engine import FastImageSelector
from .manifest import (
    BEST_AVAILABLE_SELECTOR_MANIFEST_V4,
    CONTINUITY_SELECTOR_MANIFEST_V3,
    DEFAULT_SELECTOR_MANIFEST,
    DIGIT_AWARE_SELECTOR_MANIFEST_V5,
    LEGACY_SELECTOR_MANIFEST_V2,
    SelectorManifest,
    selector_manifest_for_fingerprint,
)
from .output import (
    CuratedImageManifest,
    CuratedImageOutputPublisher,
    PublishedImageSelection,
    verify_curated_image_manifest,
)

__all__ = [
    "CandidateDecision",
    "CandidateVerification",
    "CheapImageObservation",
    "CuratedImageManifest",
    "CuratedImageOutputPublisher",
    "BEST_AVAILABLE_SELECTOR_MANIFEST_V4",
    "DEFAULT_SELECTOR_MANIFEST",
    "DIGIT_AWARE_SELECTOR_MANIFEST_V5",
    "CONTINUITY_SELECTOR_MANIFEST_V3",
    "LEGACY_SELECTOR_MANIFEST_V2",
    "FastImageSelector",
    "ImageQualityMetrics",
    "ImageSelectionResult",
    "ImageSelectionSource",
    "PublishedImageSelection",
    "SelectionGroupResult",
    "SelectionGroupStatus",
    "SelectorManifest",
    "SequenceRange",
    "selector_manifest_for_fingerprint",
    "verify_curated_image_manifest",
]
