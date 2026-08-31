"""Range-only OCR adapter for independent semi-automatic image selection.

The adapter deliberately accepts only an RGB image and source identity. It has
no ports for board detection, geometry, crop quality, or symbol inference.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

import numpy as np
from numpy.typing import NDArray

from .contracts import (
    RangeEvidenceGate,
    RangeEvidenceObservation,
    RangeEvidenceResult,
    SemiAutomaticSelectionRange,
    SemiAutomaticSelectionSource,
    SemiAutomaticSequenceBounds,
)

RANGE_ONLY_OCR_ADAPTER_VERSION = "semi-automatic-range-only-ocr-v1"
RANGE_ONLY_PROOF_POLICY_VERSION = "proof-first-local-lattice-v1"
RANGE_ONLY_GAP_POLICY_VERSION = "real-corpus-unproven-gap-v1"
RANGE_ONLY_MINIMUM_PROOF_CONFIDENCE = 0.90

_AMBIGUOUS_REASON_MARKERS = ("AMBIGUOUS", "CONFLICT")


@dataclass(frozen=True, slots=True)
class RangeOnlyLabelEvidence:
    """One OCR label tied to its expected zero-based page position."""

    position_index: int
    sequence_number: int
    confidence: float
    route: str

    def __post_init__(self) -> None:
        if self.position_index < 0 or self.sequence_number < 1:
            raise ValueError("Range-only label evidence has invalid coordinates.")
        if not 0 <= self.confidence <= 1 or not self.route:
            raise ValueError("Range-only label evidence has invalid OCR provenance.")


@dataclass(frozen=True, slots=True)
class RangeOnlyRecognition:
    """Versioned OCR result before expected-range classification."""

    observed_range: SemiAutomaticSelectionRange | None
    confidence: float | None
    has_strong_local_proof: bool
    reason_codes: tuple[str, ...]
    label_evidence: tuple[RangeOnlyLabelEvidence, ...] = ()

    @property
    def is_ambiguous(self) -> bool:
        return any(
            marker in reason for reason in self.reason_codes for marker in _AMBIGUOUS_REASON_MARKERS
        )


class RangeOnlyRecognizer(Protocol):
    """Recognition port that cannot receive board or quality information."""

    version: str
    fingerprint: str

    def recognize(self, rgb_image: NDArray[np.uint8]) -> RangeOnlyRecognition:
        """Recognize only local sequence-label evidence from one RGB image."""


class _LegacyProofFirstRecognizer(Protocol):
    version: str

    def recognize(
        self,
        rgb_image: NDArray[np.uint8],
        boards: tuple[object, ...],
    ) -> object:
        """Legacy recognizer called with an intentionally empty board tuple."""


StrongProofClassifier = Callable[[object, tuple[str, ...], tuple[object, ...]], bool]


class ExistingProofFirstRangeOnlyBridge:
    """Adapt the existing proof-first lattice recognizer without geometry input."""

    version = RANGE_ONLY_OCR_ADAPTER_VERSION

    def __init__(
        self,
        recognizer: _LegacyProofFirstRecognizer,
        *,
        strong_proof_classifier: StrongProofClassifier,
        identity: Mapping[str, object],
    ) -> None:
        self._recognizer = recognizer
        self._strong_proof_classifier = strong_proof_classifier
        self.fingerprint = _canonical_sha256(
            {
                "adapterVersion": self.version,
                "legacyRecognizerVersion": recognizer.version,
                "proofPolicyVersion": RANGE_ONLY_PROOF_POLICY_VERSION,
                "identity": dict(identity),
            }
        )

    def recognize(self, rgb_image: NDArray[np.uint8]) -> RangeOnlyRecognition:
        _validate_rgb_image(rgb_image)
        raw_result = self._recognizer.recognize(rgb_image, ())
        recognized_range, reason_codes, raw_labels = _legacy_result_parts(raw_result)
        label_evidence = tuple(_map_label_evidence(value) for value in raw_labels)
        strong = self._strong_proof_classifier(
            recognized_range,
            reason_codes,
            raw_labels,
        )
        mapped_range = (
            None
            if recognized_range is None
            else SemiAutomaticSelectionRange(
                start=int(cast(Any, recognized_range).start),
                end=int(cast(Any, recognized_range).end),
            )
        )
        confidence = (
            None if recognized_range is None else float(cast(Any, recognized_range).confidence)
        )
        return RangeOnlyRecognition(
            observed_range=mapped_range,
            confidence=confidence,
            has_strong_local_proof=strong,
            reason_codes=reason_codes,
            label_evidence=label_evidence,
        )


class RangeOnlyOcrAdapter:
    """Apply OCR proof and expected-range classification to one RGB source."""

    version = RANGE_ONLY_OCR_ADAPTER_VERSION

    def __init__(
        self,
        *,
        bounds: SemiAutomaticSequenceBounds,
        recognizer: RangeOnlyRecognizer,
    ) -> None:
        self._bounds = bounds
        self._recognizer = recognizer
        self._gate = RangeEvidenceGate(bounds)
        self.fingerprint = _canonical_sha256(
            {
                "adapterVersion": self.version,
                "boundsIndependentRecognizerFingerprint": recognizer.fingerprint,
                "proofPolicyVersion": RANGE_ONLY_PROOF_POLICY_VERSION,
            }
        )

    def recognize(
        self,
        *,
        source: SemiAutomaticSelectionSource,
        rgb_image: NDArray[np.uint8],
    ) -> RangeEvidenceResult:
        try:
            _validate_rgb_image(rgb_image)
        except ValueError:
            return self._gate.evaluate(
                RangeEvidenceObservation(
                    source=source,
                    observed_range=None,
                    confidence=None,
                    has_strong_local_proof=False,
                    source_decodable=False,
                    diagnostic_reason_codes=("SOURCE_DECODE_FAILED",),
                )
            )

        try:
            recognition = self._recognizer.recognize(rgb_image)
        except (RuntimeError, ValueError):
            return self._gate.evaluate(
                RangeEvidenceObservation(
                    source=source,
                    observed_range=None,
                    confidence=None,
                    has_strong_local_proof=False,
                    diagnostic_reason_codes=("RANGE_OCR_FAILED",),
                )
            )

        observed_range, strong = self._canonical_expected_range(recognition)
        return self._gate.evaluate(
            RangeEvidenceObservation(
                source=source,
                observed_range=observed_range,
                confidence=recognition.confidence,
                has_strong_local_proof=strong,
                is_ambiguous=recognition.is_ambiguous,
                diagnostic_reason_codes=recognition.reason_codes,
            )
        )

    def _canonical_expected_range(
        self,
        recognition: RangeOnlyRecognition,
    ) -> tuple[SemiAutomaticSelectionRange | None, bool]:
        observed = recognition.observed_range
        if observed is None or not recognition.has_strong_local_proof:
            return observed, False
        if self._bounds.expected_index_for_range(observed) is not None:
            return observed, True

        expected = next(
            (
                value
                for value in self._bounds.expected_ranges()
                if value.start == observed.start and value.board_count < observed.board_count
            ),
            None,
        )
        if expected is None:
            return observed, True
        positions = {item.position_index for item in recognition.label_evidence}
        if (
            len(positions) < 3
            or any(position >= expected.board_count for position in positions)
            or any(
                item.sequence_number != expected.start + item.position_index
                for item in recognition.label_evidence
            )
        ):
            return observed, False
        return expected, True


@dataclass(frozen=True, slots=True)
class RangeOnlyGapPolicy:
    version: str
    maximum_consecutive_unproven_sources: int
    corpus_manifest_sha256: str

    def __post_init__(self) -> None:
        if self.maximum_consecutive_unproven_sources < 0:
            raise ValueError("Unproven source gap cannot be negative.")
        if len(self.corpus_manifest_sha256) != 64:
            raise ValueError("Gap policy corpus manifest must be a SHA-256 value.")


def calibrate_unproven_gap_policy(
    *,
    source_count: int,
    proof_source_indexes: Iterable[int],
    corpus_manifest_sha256: str,
) -> RangeOnlyGapPolicy:
    """Derive the only grouping-related limit owned by TASK-0351.

    TASK-0353 will consume the result. This function does not group sources and
    does not inspect images; it only measures bounded gaps in an annotated,
    checksum-bound real corpus.
    """

    if source_count < 1:
        raise ValueError("Calibration corpus must contain at least one source.")
    proof_indexes = tuple(sorted(set(proof_source_indexes)))
    if any(index < 0 or index >= source_count for index in proof_indexes):
        raise ValueError("Calibration proof index is outside the corpus.")
    boundaries = (-1, *proof_indexes, source_count)
    maximum_gap = max(
        right - left - 1 for left, right in zip(boundaries, boundaries[1:], strict=False)
    )
    return RangeOnlyGapPolicy(
        version=RANGE_ONLY_GAP_POLICY_VERSION,
        maximum_consecutive_unproven_sources=maximum_gap,
        corpus_manifest_sha256=corpus_manifest_sha256,
    )


def build_paddle_range_only_recognizer(model_root: Path) -> RangeOnlyRecognizer:
    """Build the current local Paddle OCR bridge without importing geometry callers."""

    from game_predictor_worker.images.selection.adapters import (
        ProofFirstVisibleSequenceLabelRangeRecognizer,
    )
    from game_predictor_worker.images.selection.manifest import (
        PROOF_FIRST_SELECTOR_MANIFEST_V1019,
    )
    from game_predictor_worker.images.selection.range_proof import (
        has_strong_local_range_proof,
    )
    from game_predictor_worker.images.sequence_ocr import PaddleSequenceNumberRecognizer

    manifest = PROOF_FIRST_SELECTOR_MANIFEST_V1019
    progressive = manifest.progressive_visible_label_fallback_policy
    layout = manifest.layout_anchor_policy
    window = manifest.contiguous_sequence_window_policy
    if progressive is None or layout is None or window is None:
        raise RuntimeError("Proof-first selector manifest is incomplete.")
    paddle = PaddleSequenceNumberRecognizer(model_root)
    legacy = ProofFirstVisibleSequenceLabelRangeRecognizer(
        paddle,
        progressive,
        layout,
        window,
    )

    def classify(
        recognized_range: object,
        reason_codes: tuple[str, ...],
        labels: tuple[object, ...],
    ) -> bool:
        return has_strong_local_range_proof(
            cast(Any, recognized_range),
            reason_codes,
            minimum_confidence=RANGE_ONLY_MINIMUM_PROOF_CONFIDENCE,
            label_observations=cast(Any, labels),
            require_position_evidence=True,
        )

    return ExistingProofFirstRangeOnlyBridge(
        cast(_LegacyProofFirstRecognizer, legacy),
        strong_proof_classifier=classify,
        identity={
            "modelFingerprint": paddle.model_fingerprint,
            "modelName": paddle.model_name,
            "modelFiles": dict(paddle.model_files),
            "ocrVersion": paddle.version,
            "runtimeName": paddle.runtime_name,
            "runtimeVersion": paddle.runtime_version,
        },
    )


def _legacy_result_parts(
    value: object,
) -> tuple[object | None, tuple[str, ...], tuple[object, ...]]:
    recognized = getattr(value, "recognized_range", None)
    reasons = getattr(value, "reason_codes", None)
    labels = getattr(value, "label_observations", ())
    if reasons is None:
        try:
            recognized, reasons = cast(tuple[object | None, Sequence[str]], value)
        except (TypeError, ValueError) as error:
            raise ValueError("Legacy range recognizer returned an invalid result.") from error
    if not isinstance(reasons, Sequence) or isinstance(reasons, str | bytes):
        raise ValueError("Legacy range reason codes must be a sequence.")
    return (
        recognized,
        tuple(str(reason) for reason in reasons),
        tuple(cast(Iterable[object], labels)),
    )


def _map_label_evidence(value: object) -> RangeOnlyLabelEvidence:
    legacy = cast(Any, value)
    return RangeOnlyLabelEvidence(
        position_index=int(legacy.position_index),
        sequence_number=int(legacy.sequence_number),
        confidence=float(legacy.confidence),
        route=str(legacy.route),
    )


def _validate_rgb_image(value: NDArray[np.uint8]) -> None:
    if value.dtype != np.uint8 or value.ndim != 3 or value.shape[2] != 3 or value.size == 0:
        raise ValueError("Range-only OCR requires a non-empty RGB uint8 image.")


def _canonical_sha256(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(dict(payload), separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


__all__ = [
    "RANGE_ONLY_GAP_POLICY_VERSION",
    "RANGE_ONLY_MINIMUM_PROOF_CONFIDENCE",
    "RANGE_ONLY_OCR_ADAPTER_VERSION",
    "RANGE_ONLY_PROOF_POLICY_VERSION",
    "ExistingProofFirstRangeOnlyBridge",
    "RangeOnlyGapPolicy",
    "RangeOnlyLabelEvidence",
    "RangeOnlyOcrAdapter",
    "RangeOnlyRecognition",
    "RangeOnlyRecognizer",
    "build_paddle_range_only_recognizer",
    "calibrate_unproven_gap_policy",
]
