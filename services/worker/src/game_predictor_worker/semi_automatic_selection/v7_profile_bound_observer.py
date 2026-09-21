"""Profile-bound, recognition-only V7 source observer.

This adapter determines only what one JPEG itself proves. It does not keep a
cross-source hypothesis: the checkpointable occurrence tracker owns 3+3
confirmation, occurrence boundaries and visual-independence decisions.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .middle_row_locator import canonicalize_source_image
from .v7_calibration import (
    V7_STANDARD_GEOMETRY_FAMILY_ID,
    V7EvaluationStatus,
    V7GeometryProfile,
)
from .v7_label_locator import V7GridLabelLocator, V7LabelRecognitionBackend, recognize_grid_labels
from .v7_quality import (
    V7BlurSeverity,
    V7BoardQuality,
    V7BoardReadability,
    V7BoardVisibility,
    V7DecorationVisibility,
    V7FrameQuality,
    V7OcclusionSeverity,
    V7SymbolContentLoss,
)
from .v7_range_proof import (
    V7FrameEvidence,
    V7RangeProofKind,
    V7RangeProofResolver,
    V7RangeProofResult,
    V7WeakFrameEvidence,
)
from .v7_run_state import V7PinnedSource, V7ScanObservation
from .v7_worker_runtime import (
    V7SourceObservationRequest,
    V7WorkerConfiguration,
    V7WorkerRuntimeError,
)

V7_PROFILE_BOUND_OBSERVER_VERSION = "v7-profile-bound-observer-v1"
V7_VISUAL_CLUSTER_HASH_SIZE = 8


class V7ProfileBoundObserverFactory:
    """Construct one observer only for the exact passed immutable profile."""

    def __init__(
        self,
        profile: V7GeometryProfile,
        recognizer_factory: Callable[[], V7LabelRecognitionBackend],
    ) -> None:
        self._profile = profile
        self._recognizer_factory = recognizer_factory

    def create(
        self,
        configuration: V7WorkerConfiguration,
        _manifest: object,
    ) -> V7ProfileBoundObserver:
        _require_profile_matches_configuration(self._profile, configuration)
        recognizer = self._recognizer_factory()
        if not callable(getattr(recognizer, "recognize_many", None)):
            _fail("V7_OCR_BACKEND_INVALID", "The V7 numeric-label recognizer is invalid.")
        return V7ProfileBoundObserver(self._profile, configuration, recognizer)


class V7ProfileBoundObserver:
    """Map verified source bytes to one source-local V7 observation."""

    requires_config_bound_checkpoint = True

    def __init__(
        self,
        profile: V7GeometryProfile,
        configuration: V7WorkerConfiguration,
        recognizer: V7LabelRecognitionBackend,
    ) -> None:
        _require_profile_matches_configuration(profile, configuration)
        self._recognizer = recognizer
        self._locator = V7GridLabelLocator(profile.calibration.locator_config)
        self._resolver = V7RangeProofResolver(configuration.expected_ranges)

    def observe(self, request: V7SourceObservationRequest) -> V7ScanObservation:
        """Decode exactly the runtime-verified bytes and return local evidence.

        An exact three-label hypothesis is intentionally carried as bounded
        evidence only. V7OccurrenceTracker is the single owner of the pending
        hypothesis and may combine it with a later source.
        """

        try:
            canonical = canonicalize_source_image(request.source_content)
        except ValueError:
            return _source_error_observation(request.source.source_index)

        labels = recognize_grid_labels(canonical.rgb, self._recognizer, locator=self._locator)
        frame = V7FrameEvidence(
            source_id=request.source.source_id,
            occurrence_id="source-local",
            visual_cluster_id="source-local",
            labels=labels,
        )
        proof = self._resolver.resolve_frame(frame)
        if proof.kind is V7RangeProofKind.STRONG_FIVE_LABEL:
            return _decoded_observation(request.source, proof)

        weak_hypotheses = self._resolver.weak_hypotheses(frame)
        visual_hash, visual_signature = _visual_features(canonical.rgb)
        weak_evidence = (
            None
            if len(weak_hypotheses) != 1
            else V7WeakFrameEvidence(
                source_id=request.source.source_id,
                labels=labels,
                visual_hash=visual_hash,
                visual_signature=visual_signature,
            )
        )
        return _decoded_observation(request.source, proof, weak_evidence=weak_evidence)


def v7_profile_bound_localizer_fingerprint(profile: V7GeometryProfile) -> str:
    """Fingerprint every adapter input controlling numeric-label crop geometry."""

    return _canonical_sha256(
        {
            "geometryFamilyId": profile.calibration.geometry_family_id,
            "locatorConfig": profile.calibration.locator_config.as_dict(),
            "profileFingerprint": profile.profile_fingerprint,
            "version": V7_PROFILE_BOUND_OBSERVER_VERSION,
        }
    )


def build_paddle_v7_profile_bound_observer_factory(
    profile: V7GeometryProfile,
    model_root: Path,
) -> V7ProfileBoundObserverFactory:
    """Build the real recognition-only Paddle dependency lazily per V7 run."""

    def create_recognizer() -> V7LabelRecognitionBackend:
        from game_predictor_worker.images.sequence_ocr import PaddleSequenceNumberRecognizer

        return PaddleSequenceNumberRecognizer(model_root)

    return V7ProfileBoundObserverFactory(profile, create_recognizer)


def _require_profile_matches_configuration(
    profile: V7GeometryProfile,
    configuration: V7WorkerConfiguration,
) -> None:
    if profile.calibration.status is not V7EvaluationStatus.PASSED:
        _fail(
            "V7_CALIBRATION_PROFILE_REJECTED",
            "The V7 geometry profile did not pass calibration.",
        )
    if profile.calibration.geometry_family_id != V7_STANDARD_GEOMETRY_FAMILY_ID:
        _fail("V7_CALIBRATION_FAMILY_UNSUPPORTED", "The V7 geometry family is unsupported.")
    if configuration.calibration_fingerprint != profile.profile_fingerprint:
        _fail(
            "V7_CALIBRATION_FINGERPRINT_MISMATCH",
            "The V7 run does not pin the requested geometry profile.",
        )
    if configuration.localizer_fingerprint != v7_profile_bound_localizer_fingerprint(profile):
        _fail(
            "V7_LOCALIZER_FINGERPRINT_MISMATCH",
            "The V7 run does not pin the requested numeric-label locator.",
        )


def _decoded_observation(
    source: V7PinnedSource,
    proof: V7RangeProofResult,
    *,
    weak_evidence: V7WeakFrameEvidence | None = None,
) -> V7ScanObservation:
    return V7ScanObservation(
        source_index=source.source_index,
        proof=proof,
        weak_evidence=weak_evidence,
        quality=V7FrameQuality(
            source_id=source.source_id,
            source_index=source.source_index,
            boards=tuple(
                V7BoardQuality(
                    position_index=position_index,
                    symbol_content_loss=V7SymbolContentLoss.UNKNOWN,
                    readability=V7BoardReadability.UNKNOWN,
                    visibility=V7BoardVisibility.UNKNOWN,
                    blur=V7BlurSeverity.UNKNOWN,
                    occlusion=V7OcclusionSeverity.UNKNOWN,
                    decoration=V7DecorationVisibility.UNKNOWN,
                )
                for position_index in range(9)
            ),
        ),
    )


def _source_error_observation(source_index: int) -> V7ScanObservation:
    return V7ScanObservation(
        source_index=source_index,
        proof=V7RangeProofResult(
            kind=V7RangeProofKind.NONE,
            sequence_range=None,
            supporting_source_ids=(),
            reason_codes=("SOURCE_DECODE_ERROR",),
        ),
        quality=None,
        source_error_code="SOURCE_DECODE_ERROR",
    )


def _visual_features(rgb: np.ndarray) -> tuple[int, bytes]:
    """Return two bounded, compression-tolerant descriptors of an RGB image."""

    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("V7 visual hash requires RGB.")
    height, width = rgb.shape[:2]
    if min(height, width) < 2:
        return 0, bytes(64)
    grayscale = rgb.mean(axis=2, dtype=np.float32)
    sample = np.empty(
        (V7_VISUAL_CLUSTER_HASH_SIZE, V7_VISUAL_CLUSTER_HASH_SIZE),
        dtype=np.float32,
    )
    for row in range(V7_VISUAL_CLUSTER_HASH_SIZE):
        row_start = row * height // V7_VISUAL_CLUSTER_HASH_SIZE
        row_end = (row + 1) * height // V7_VISUAL_CLUSTER_HASH_SIZE
        for column in range(V7_VISUAL_CLUSTER_HASH_SIZE):
            column_start = column * width // V7_VISUAL_CLUSTER_HASH_SIZE
            column_end = (column + 1) * width // V7_VISUAL_CLUSTER_HASH_SIZE
            sample[row, column] = grayscale[row_start:row_end, column_start:column_end].mean()
    signature = bytes(np.clip(np.rint(sample / 32), 0, 7).astype(np.uint8).ravel())
    threshold = float(sample.mean())
    value = 0
    for comparison in (sample >= threshold).ravel():
        value = (value << 1) | int(comparison)
    return value, signature


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _fail(code: str, message: str) -> None:
    raise V7WorkerRuntimeError(code, message)


__all__ = [
    "V7_PROFILE_BOUND_OBSERVER_VERSION",
    "V7_VISUAL_CLUSTER_HASH_SIZE",
    "V7ProfileBoundObserver",
    "V7ProfileBoundObserverFactory",
    "build_paddle_v7_profile_bound_observer_factory",
    "v7_profile_bound_localizer_fingerprint",
]
