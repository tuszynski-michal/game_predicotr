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
from .manifest import DEFAULT_SELECTOR_MANIFEST, SelectorManifest
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
    "DEFAULT_SELECTOR_MANIFEST",
    "FastImageSelector",
    "ImageQualityMetrics",
    "ImageSelectionResult",
    "ImageSelectionSource",
    "PublishedImageSelection",
    "SelectionGroupResult",
    "SelectionGroupStatus",
    "SelectorManifest",
    "SequenceRange",
    "verify_curated_image_manifest",
]
