"""Range-only OCR adapter for independent semi-automatic image selection.

The adapter deliberately accepts only an RGB image and source identity. It has
no ports for board detection, geometry, crop quality, or symbol inference.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
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
from .five_anchor_range_runtime import FIVE_ANCHOR_RECOGNIZER_CONTRACT_FINGERPRINT_V6
from .middle_row_runtime import MIDDLE_ROW_RECOGNIZER_CONTRACT_FINGERPRINT_V4
from .row_first_runtime_v5 import ROW_FIRST_RECOGNIZER_CONTRACT_FINGERPRINT_V5

RANGE_ONLY_OCR_ADAPTER_VERSION_V1 = "semi-automatic-range-only-ocr-v1"
RANGE_ONLY_OCR_ADAPTER_VERSION_V2 = "semi-automatic-range-only-ocr-v2"
RANGE_ONLY_OCR_ADAPTER_VERSION_V3 = "semi-automatic-range-only-ocr-v3"
RANGE_ONLY_PROOF_POLICY_VERSION_V1 = "proof-first-local-lattice-v1"
RANGE_ONLY_PROOF_POLICY_VERSION_V2 = "proof-first-wide-dynamic-lattice-v2"
# V3 changes when OCR is scheduled, not what constitutes a valid proof.
RANGE_ONLY_PROOF_POLICY_VERSION_V3 = RANGE_ONLY_PROOF_POLICY_VERSION_V2
RANGE_ONLY_OCR_ADAPTER_VERSION = RANGE_ONLY_OCR_ADAPTER_VERSION_V3
RANGE_ONLY_PROOF_POLICY_VERSION = RANGE_ONLY_PROOF_POLICY_VERSION_V3
RANGE_ONLY_GAP_POLICY_VERSION = "real-corpus-unproven-gap-v1"
RANGE_ONLY_MINIMUM_PROOF_CONFIDENCE = 0.90

_AMBIGUOUS_REASON_MARKERS = ("AMBIGUOUS", "CONFLICT")

RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V1 = hashlib.sha256(
    json.dumps(
        {
            "adapterVersion": RANGE_ONLY_OCR_ADAPTER_VERSION_V1,
            "proofPolicyVersion": RANGE_ONLY_PROOF_POLICY_VERSION_V1,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
).hexdigest()


@dataclass(frozen=True, slots=True)
class RangeOnlyCandidatePolicy:
    """Versioned, range-only viewport for local sequence labels."""

    version: str = "range-only-wide-label-candidates-v1"
    minimum_x_ratio: float = 0.20
    maximum_x_ratio: float = 0.82
    minimum_y_ratio: float = 0.24
    maximum_y_ratio: float = 0.48
    minimum_width_ratio: float = 0.025
    minimum_aspect_ratio: float = 1.20
    candidate_levels: tuple[int, ...] = (12, 24, 36)

    def __post_init__(self) -> None:
        if (
            not 0 <= self.minimum_x_ratio < self.maximum_x_ratio <= 1
            or not 0 <= self.minimum_y_ratio < self.maximum_y_ratio <= 1
            or not 0 < self.minimum_width_ratio <= 1
            or self.minimum_aspect_ratio <= 0
            or not self.candidate_levels
            or any(level < 1 for level in self.candidate_levels)
            or tuple(sorted(set(self.candidate_levels))) != self.candidate_levels
        ):
            raise ValueError("Range-only candidate policy is invalid.")

    def as_dict(self) -> dict[str, object]:
        return {
            "candidateLevels": list(self.candidate_levels),
            "maximumXRatio": self.maximum_x_ratio,
            "maximumYRatio": self.maximum_y_ratio,
            "minimumAspectRatio": self.minimum_aspect_ratio,
            "minimumWidthRatio": self.minimum_width_ratio,
            "minimumXRatio": self.minimum_x_ratio,
            "minimumYRatio": self.minimum_y_ratio,
            "version": self.version,
        }

    def accepts(
        self,
        *,
        center: tuple[float, float],
        crop_shape: tuple[int, int],
        image_shape: tuple[int, int],
    ) -> bool:
        image_height, image_width = image_shape
        crop_height, crop_width = crop_shape
        if min(image_height, image_width, crop_height, crop_width) < 1:
            return False
        x_ratio = center[0] / image_width
        y_ratio = center[1] / image_height
        return (
            self.minimum_x_ratio <= x_ratio <= self.maximum_x_ratio
            and self.minimum_y_ratio <= y_ratio <= self.maximum_y_ratio
            and crop_width / image_width >= self.minimum_width_ratio
            and crop_width / crop_height >= self.minimum_aspect_ratio
        )


RANGE_ONLY_CANDIDATE_POLICY_V2 = RangeOnlyCandidatePolicy()
RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V2 = hashlib.sha256(
    json.dumps(
        {
            "adapterVersion": RANGE_ONLY_OCR_ADAPTER_VERSION_V2,
            "candidatePolicy": RANGE_ONLY_CANDIDATE_POLICY_V2.as_dict(),
            "proofPolicyVersion": RANGE_ONLY_PROOF_POLICY_VERSION_V2,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
).hexdigest()


@dataclass(frozen=True, slots=True)
class RangeOnlyExecutionPolicy:
    """Immutable Paddle execution identity retained in the v3 fingerprint."""

    version: str = "range-only-compatible-execution-v1"
    ocr_batch_size: int = 9
    cpu_math_library_num_threads: int = 1

    def __post_init__(self) -> None:
        if self.ocr_batch_size != 9 or self.cpu_math_library_num_threads != 1:
            raise ValueError("Range-only execution policy is invalid.")

    def as_dict(self) -> dict[str, object]:
        return {
            "cpuMathLibraryNumThreads": self.cpu_math_library_num_threads,
            "ocrBatchSize": self.ocr_batch_size,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class RangeOnlyOcrSchedulingPolicy:
    """Bounded visual probe policy; it never supplies range evidence itself."""

    version: str = "range-only-adaptive-probes-v1"
    appearance_descriptor_version: str = "opencv-appearance-descriptor-v2"
    thumbnail_max_edge: int = 640
    maximum_probe_interval: int = 5
    strong_boundary_distance: float = 0.08
    checkpoint_interval_sources: int = 10

    def __post_init__(self) -> None:
        if (
            self.thumbnail_max_edge < 64
            or self.maximum_probe_interval < 1
            or self.checkpoint_interval_sources < 1
            or not 0 < self.strong_boundary_distance <= 1
            or not self.appearance_descriptor_version
        ):
            raise ValueError("Range-only OCR scheduling policy is invalid.")

    def as_dict(self) -> dict[str, object]:
        return {
            "appearanceDescriptorVersion": self.appearance_descriptor_version,
            "checkpointIntervalSources": self.checkpoint_interval_sources,
            "maximumProbeInterval": self.maximum_probe_interval,
            "strongBoundaryDistance": self.strong_boundary_distance,
            "thumbnailMaxEdge": self.thumbnail_max_edge,
            "version": self.version,
        }


RANGE_ONLY_CANDIDATE_POLICY_V3 = RangeOnlyCandidatePolicy(
    version="range-only-wide-label-candidates-v1",
    candidate_levels=(12, 24, 36),
)
RANGE_ONLY_EXECUTION_POLICY_V3 = RangeOnlyExecutionPolicy()
RANGE_ONLY_OCR_SCHEDULING_POLICY_V3 = RangeOnlyOcrSchedulingPolicy()
RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V3 = hashlib.sha256(
    json.dumps(
        {
            "adapterVersion": RANGE_ONLY_OCR_ADAPTER_VERSION_V3,
            "candidatePolicy": RANGE_ONLY_CANDIDATE_POLICY_V3.as_dict(),
            "executionPolicy": RANGE_ONLY_EXECUTION_POLICY_V3.as_dict(),
            "ocrSchedulingPolicy": RANGE_ONLY_OCR_SCHEDULING_POLICY_V3.as_dict(),
            "proofPolicyVersion": RANGE_ONLY_PROOF_POLICY_VERSION_V3,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
).hexdigest()
RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT = RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V3
SUPPORTED_RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINTS = frozenset(
    {
        RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V1,
        RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V2,
        RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V3,
        MIDDLE_ROW_RECOGNIZER_CONTRACT_FINGERPRINT_V4,
        ROW_FIRST_RECOGNIZER_CONTRACT_FINGERPRINT_V5,
        FIVE_ANCHOR_RECOGNIZER_CONTRACT_FINGERPRINT_V6,
    }
)


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

    version = RANGE_ONLY_OCR_ADAPTER_VERSION_V1

    def __init__(
        self,
        recognizer: _LegacyProofFirstRecognizer,
        *,
        strong_proof_classifier: StrongProofClassifier,
        identity: Mapping[str, object],
        adapter_version: str = RANGE_ONLY_OCR_ADAPTER_VERSION_V1,
        proof_policy_version: str = RANGE_ONLY_PROOF_POLICY_VERSION_V1,
    ) -> None:
        self._recognizer = recognizer
        self._strong_proof_classifier = strong_proof_classifier
        self.version = adapter_version
        self.proof_policy_version = proof_policy_version
        self._last_diagnostics: dict[str, object] = {}
        self.fingerprint = _canonical_sha256(
            {
                "adapterVersion": self.version,
                "legacyRecognizerVersion": recognizer.version,
                "proofPolicyVersion": proof_policy_version,
                "identity": dict(identity),
            }
        )

    @property
    def last_diagnostics(self) -> Mapping[str, object]:
        return dict(self._last_diagnostics)

    def recognize(self, rgb_image: NDArray[np.uint8]) -> RangeOnlyRecognition:
        _validate_rgb_image(rgb_image)
        raw_result = self._recognizer.recognize(rgb_image, ())
        diagnostics = getattr(self._recognizer, "last_diagnostics", {})
        self._last_diagnostics = dict(diagnostics) if isinstance(diagnostics, Mapping) else {}
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
        self.version = recognizer.version
        proof_policy_version = str(
            getattr(recognizer, "proof_policy_version", RANGE_ONLY_PROOF_POLICY_VERSION)
        )
        self.fingerprint = _canonical_sha256(
            {
                "adapterVersion": self.version,
                "boundsIndependentRecognizerFingerprint": recognizer.fingerprint,
                "proofPolicyVersion": proof_policy_version,
            }
        )

    @property
    def last_diagnostics(self) -> Mapping[str, object]:
        value = getattr(self._recognizer, "last_diagnostics", {})
        return dict(value) if isinstance(value, Mapping) else {}

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
        result = self._gate.evaluate(
            RangeEvidenceObservation(
                source=source,
                observed_range=observed_range,
                confidence=recognition.confidence,
                has_strong_local_proof=strong,
                is_ambiguous=recognition.is_ambiguous,
                diagnostic_reason_codes=recognition.reason_codes,
            )
        )
        diagnostics = dict(self.last_diagnostics)
        if recognition.label_evidence:
            diagnostics["labelEvidence"] = [
                {
                    "confidence": item.confidence,
                    "positionIndex": item.position_index,
                    "route": item.route,
                    "sequenceNumber": item.sequence_number,
                }
                for item in recognition.label_evidence
            ]
        return replace(
            result,
            runtime_diagnostics=diagnostics or None,
        )

    def unproven(
        self,
        *,
        source: SemiAutomaticSelectionSource,
        reason_codes: tuple[str, ...],
        source_decodable: bool = True,
    ) -> RangeEvidenceResult:
        """Record a source without OCR proof; this can never select a range."""

        return self._gate.evaluate(
            RangeEvidenceObservation(
                source=source,
                observed_range=None,
                confidence=None,
                has_strong_local_proof=False,
                source_decodable=source_decodable,
                diagnostic_reason_codes=reason_codes,
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


def build_paddle_range_only_recognizer_v1(model_root: Path) -> RangeOnlyRecognizer:
    """Rebuild the immutable historical v1 recognizer for durable retries."""

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
        identity=_paddle_identity(paddle),
        adapter_version=RANGE_ONLY_OCR_ADAPTER_VERSION_V1,
        proof_policy_version=RANGE_ONLY_PROOF_POLICY_VERSION_V1,
    )


def build_paddle_range_only_recognizer_v2(model_root: Path) -> RangeOnlyRecognizer:
    """Build the wide, progressive range-only recognizer without geometry callers."""

    return _build_progressive_range_only_recognizer(
        model_root,
        candidate_policy=RANGE_ONLY_CANDIDATE_POLICY_V2,
        recognizer_version="visible-sequence-label-range-v15+range-only-wide-lattice-v2",
        adapter_version=RANGE_ONLY_OCR_ADAPTER_VERSION_V2,
        proof_policy_version=RANGE_ONLY_PROOF_POLICY_VERSION_V2,
    )


def build_paddle_range_only_recognizer_v3(model_root: Path) -> RangeOnlyRecognizer:
    """Build v2-equivalent proof OCR for adaptively scheduled v3 probes."""

    return _build_progressive_range_only_recognizer(
        model_root,
        candidate_policy=RANGE_ONLY_CANDIDATE_POLICY_V3,
        recognizer_version=("visible-sequence-label-range-v15+range-only-adaptive-probes-v3"),
        adapter_version=RANGE_ONLY_OCR_ADAPTER_VERSION_V3,
        proof_policy_version=RANGE_ONLY_PROOF_POLICY_VERSION_V3,
        execution_policy=RANGE_ONLY_EXECUTION_POLICY_V3,
    )


def _build_progressive_range_only_recognizer(
    model_root: Path,
    *,
    candidate_policy: RangeOnlyCandidatePolicy,
    recognizer_version: str,
    adapter_version: str,
    proof_policy_version: str,
    execution_policy: RangeOnlyExecutionPolicy | None = None,
) -> RangeOnlyRecognizer:
    """Build the shared v2 proof engine without changing its OCR semantics."""

    from game_predictor_worker.images.geometry import BoardDetection
    from game_predictor_worker.images.selection.adapters import (
        ProofFirstVisibleSequenceLabelRangeRecognizer,
    )
    from game_predictor_worker.images.selection.contracts import SequenceRange
    from game_predictor_worker.images.selection.manifest import (
        PROOF_FIRST_SELECTOR_MANIFEST_V1019,
        ProgressiveVisibleLabelFallbackPolicy,
    )
    from game_predictor_worker.images.selection.range_proof import (
        has_strong_local_range_proof,
    )
    from game_predictor_worker.images.sequence_ocr import PaddleSequenceNumberRecognizer

    manifest = PROOF_FIRST_SELECTOR_MANIFEST_V1019
    layout = manifest.layout_anchor_policy
    window = manifest.contiguous_sequence_window_policy
    if layout is None or window is None:
        raise RuntimeError("Proof-first selector manifest is incomplete.")
    layout_policy = layout
    window_policy = window

    runtime_recognizer_version = recognizer_version

    class _ProgressiveRangeOnlyRecognizer(ProofFirstVisibleSequenceLabelRangeRecognizer):
        version = runtime_recognizer_version

        def __init__(self, recognizer: object) -> None:
            super().__init__(
                cast(Any, recognizer),
                ProgressiveVisibleLabelFallbackPolicy(
                    candidate_levels=candidate_policy.candidate_levels
                ),
                layout_policy,
                window_policy,
            )
            self._last_diagnostics: dict[str, object] = {}
            self._attempted_levels: list[int] = []
            self._added_candidates_by_level: list[dict[str, int]] = []
            self._candidate_count = 0
            self._ocr_batch_calls = 0
            self._ocr_crop_count = 0
            self._resolved_level: int | None = None

        @property
        def last_diagnostics(self) -> Mapping[str, object]:
            return dict(self._last_diagnostics)

        def recognize(
            self,
            rgb_image: NDArray[np.uint8],
            boards: tuple[BoardDetection, ...],
        ) -> tuple[SequenceRange | None, tuple[str, ...]]:
            self._attempted_levels = []
            self._added_candidates_by_level = []
            self._candidate_count = 0
            self._ocr_batch_calls = 0
            self._ocr_crop_count = 0
            self._resolved_level = None
            result = super().recognize(rgb_image, boards)
            self._last_diagnostics = {
                "attemptedCandidateCount": self._candidate_count,
                "attemptedLevels": list(self._attempted_levels),
                "candidatesByLevel": list(self._added_candidates_by_level),
                "candidatePolicyVersion": candidate_policy.version,
                "ocrBatchCalls": self._ocr_batch_calls,
                "ocrCropCount": self._ocr_crop_count,
                "resolvedLevel": self._resolved_level,
            }
            if execution_policy is not None:
                self._last_diagnostics.update(
                    {
                        "executionPolicyVersion": execution_policy.version,
                        "ocrBatchSize": execution_policy.ocr_batch_size,
                        "ocrCpuThreads": execution_policy.cpu_math_library_num_threads,
                    }
                )
            return result

        @staticmethod
        def _is_likely_lattice_label(
            label: object,
            *,
            image_shape: tuple[int, int],
        ) -> bool:
            visible = cast(Any, label)
            return candidate_policy.accepts(
                center=(float(visible.center[0]), float(visible.center[1])),
                crop_shape=(int(visible.crop.shape[0]), int(visible.crop.shape[1])),
                image_shape=image_shape,
            )

        def _record_level_attempt(self, configured_level: int, added_crops: int) -> None:
            self._attempted_levels.append(configured_level)
            self._added_candidates_by_level.append(
                {"addedCandidates": added_crops, "level": configured_level}
            )
            self._candidate_count += added_crops
            super()._record_level_attempt(configured_level, added_crops)

        def _record_level_resolution(self, configured_level: int, crop_count: int) -> None:
            self._resolved_level = configured_level
            super()._record_level_resolution(configured_level, crop_count)

        def _recognize_many(
            self,
            crops: tuple[NDArray[np.uint8], ...],
        ) -> tuple[Any, ...]:
            self._ocr_batch_calls += (len(crops) + 8) // 9
            self._ocr_crop_count += len(crops)
            return cast(tuple[Any, ...], super()._recognize_many(crops))

    paddle = PaddleSequenceNumberRecognizer(model_root)
    legacy = _ProgressiveRangeOnlyRecognizer(paddle)

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

    identity: dict[str, object] = {
        **_paddle_identity(paddle),
        "candidatePolicy": candidate_policy.as_dict(),
    }
    if execution_policy is not None:
        identity["executionPolicy"] = execution_policy.as_dict()
    return ExistingProofFirstRangeOnlyBridge(
        cast(_LegacyProofFirstRecognizer, legacy),
        strong_proof_classifier=classify,
        identity=identity,
        adapter_version=adapter_version,
        proof_policy_version=proof_policy_version,
    )


def build_paddle_range_only_recognizer(model_root: Path) -> RangeOnlyRecognizer:
    """Build the current v3 range-only recognizer for new runs and acceptance."""

    return build_paddle_range_only_recognizer_v3(model_root)


def build_paddle_range_only_recognizer_for_contract(
    model_root: Path,
    contract_fingerprint: str,
) -> RangeOnlyRecognizer:
    """Resolve a durable run to its immutable recognizer implementation."""

    if contract_fingerprint == RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V1:
        return build_paddle_range_only_recognizer_v1(model_root)
    if contract_fingerprint == RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V2:
        return build_paddle_range_only_recognizer_v2(model_root)
    if contract_fingerprint == RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V3:
        return build_paddle_range_only_recognizer_v3(model_root)
    raise ValueError("Unsupported range-only recognizer contract fingerprint.")


def _paddle_identity(paddle: object) -> dict[str, object]:
    value = cast(Any, paddle)
    return {
        "modelFingerprint": value.model_fingerprint,
        "modelName": value.model_name,
        "modelFiles": dict(value.model_files),
        "ocrVersion": value.version,
        "runtimeName": value.runtime_name,
        "runtimeVersion": value.runtime_version,
    }


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
    "RANGE_ONLY_CANDIDATE_POLICY_V2",
    "RANGE_ONLY_CANDIDATE_POLICY_V3",
    "RANGE_ONLY_EXECUTION_POLICY_V3",
    "RANGE_ONLY_OCR_SCHEDULING_POLICY_V3",
    "RANGE_ONLY_GAP_POLICY_VERSION",
    "RANGE_ONLY_MINIMUM_PROOF_CONFIDENCE",
    "RANGE_ONLY_OCR_ADAPTER_VERSION",
    "RANGE_ONLY_OCR_ADAPTER_VERSION_V1",
    "RANGE_ONLY_OCR_ADAPTER_VERSION_V2",
    "RANGE_ONLY_OCR_ADAPTER_VERSION_V3",
    "RANGE_ONLY_PROOF_POLICY_VERSION",
    "RANGE_ONLY_PROOF_POLICY_VERSION_V1",
    "RANGE_ONLY_PROOF_POLICY_VERSION_V2",
    "RANGE_ONLY_PROOF_POLICY_VERSION_V3",
    "RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT",
    "RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V1",
    "RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V2",
    "RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V3",
    "MIDDLE_ROW_RECOGNIZER_CONTRACT_FINGERPRINT_V4",
    "SUPPORTED_RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINTS",
    "ExistingProofFirstRangeOnlyBridge",
    "RangeOnlyCandidatePolicy",
    "RangeOnlyExecutionPolicy",
    "RangeOnlyGapPolicy",
    "RangeOnlyLabelEvidence",
    "RangeOnlyOcrAdapter",
    "RangeOnlyOcrSchedulingPolicy",
    "RangeOnlyRecognition",
    "RangeOnlyRecognizer",
    "build_paddle_range_only_recognizer",
    "build_paddle_range_only_recognizer_for_contract",
    "build_paddle_range_only_recognizer_v1",
    "build_paddle_range_only_recognizer_v2",
    "build_paddle_range_only_recognizer_v3",
    "calibrate_unproven_gap_policy",
]
