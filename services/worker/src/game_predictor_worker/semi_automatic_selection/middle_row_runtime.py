"""Recognition-only, batch-oriented runtime for middle-row OCR v4.1."""

from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from statistics import mean, median
from time import perf_counter
from typing import Protocol, cast
from uuid import UUID

import numpy as np
from numpy.typing import NDArray

from .contracts import (
    RangeEvidenceResult,
    RangeEvidenceStatus,
    SemiAutomaticSelectionSource,
)
from .middle_row_grouping import (
    MIDDLE_ROW_EVIDENCE_SELECTOR_VERSION,
    MIDDLE_ROW_GROUPING_VERSION,
    MIDDLE_ROW_MAXIMUM_UNKNOWN_GAP,
)
from .middle_row_locator import (
    MIDDLE_ROW_COORDINATE_SPACE,
    MIDDLE_ROW_LOCATOR_VERSION,
    MIDDLE_ROW_OCR_PREPROCESSING_VERSION,
    CanonicalSourceImage,
    ImageDimensions,
    MiddleRowLatticePrior,
    MiddleRowLocation,
    MiddleRowLocatorMode,
    MiddleRowTripleLocator,
    canonicalize_source_image,
)
from .middle_row_range import (
    MIDDLE_ROW_PROOF_POLICY_VERSION,
    MIDDLE_ROW_RANGE_VARIANT,
    ExactRangeObservation,
    ExpectedRangeTable,
    MiddleRowExactResolver,
    MiddleRowTripleProof,
    MiddleRowUnknownReason,
)

MIDDLE_ROW_PADDLE_ADAPTER_VERSION = "middle-row-paddle-recognition-only-v1"
MIDDLE_ROW_ORIENTATION_POLICY_VERSION = "middle-row-run-orientation-v1"
MIDDLE_ROW_ORIENTATION_PROBE_POLICY_VERSION = "middle-row-orientation-probes-v1"
MIDDLE_ROW_PRIOR_POLICY_VERSION = "middle-row-run-lattice-prior-v1"
MIDDLE_ROW_BATCH_POLICY_VERSION = "middle-row-source-batches-v1"
MIDDLE_ROW_RUNTIME_FINGERPRINT_VERSION = "middle-row-range-runtime-v1"
MIDDLE_ROW_OBSERVATION_KEY_VERSION = "middle-row-observation-key-v1"


class MiddleRowRunOrientation(StrEnum):
    AUTO = "auto"
    DEG_0 = "0"
    DEG_90 = "90"
    DEG_180 = "180"
    DEG_270 = "270"

    @property
    def degrees(self) -> int:
        if self is MiddleRowRunOrientation.AUTO:
            raise ValueError("Automatic orientation has no fixed rotation.")
        return int(self.value)


class MiddleRowOrientationSource(StrEnum):
    AUTOMATIC = "automatic"
    MANUAL_OVERRIDE = "manual_override"
    CHECKPOINT = "checkpoint"


@dataclass(frozen=True, slots=True)
class MiddleRowBatchPolicy:
    version: str = MIDDLE_ROW_BATCH_POLICY_VERSION
    source_batch_size: int = 6
    internal_ocr_batch_size: int = 9
    cpu_math_library_num_threads: int = 1
    checkpoint_interval_batches: int = 1

    def __post_init__(self) -> None:
        if self.source_batch_size not in {1, 3, 6, 12}:
            raise ValueError("V4.1 source batch size must be one of 1, 3, 6 or 12.")
        if self.internal_ocr_batch_size != 9 or self.cpu_math_library_num_threads != 1:
            raise ValueError("V4.1 Paddle execution must retain the measured CPU contract.")
        if self.checkpoint_interval_batches < 1:
            raise ValueError("Checkpoint interval must be positive.")

    def as_dict(self) -> dict[str, object]:
        return {
            "checkpointIntervalBatches": self.checkpoint_interval_batches,
            "cpuMathLibraryNumThreads": self.cpu_math_library_num_threads,
            "internalOcrBatchSize": self.internal_ocr_batch_size,
            "sourceBatchSize": self.source_batch_size,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class MiddleRowOrientationPolicy:
    version: str = MIDDLE_ROW_ORIENTATION_POLICY_VERSION
    probe_policy_version: str = MIDDLE_ROW_ORIENTATION_PROBE_POLICY_VERSION
    calibration_source_count: int = 8
    early_stop_exact_proofs: int = 2
    additional_probe_budget: int = 4

    def as_dict(self) -> dict[str, object]:
        return {
            "additionalProbeBudget": self.additional_probe_budget,
            "calibrationSourceCount": self.calibration_source_count,
            "earlyStopExactProofs": self.early_stop_exact_proofs,
            "probePolicyVersion": self.probe_policy_version,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class MiddleRowPriorPolicy:
    version: str = MIDDLE_ROW_PRIOR_POLICY_VERSION
    history_size: int = 7
    reset_after_failures: int = 3
    full_search_interval: int = 10

    def as_dict(self) -> dict[str, object]:
        return {
            "fullSearchInterval": self.full_search_interval,
            "historySize": self.history_size,
            "resetAfterFailures": self.reset_after_failures,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class MiddleRowRuntimePolicy:
    batch: MiddleRowBatchPolicy = MiddleRowBatchPolicy()
    orientation: MiddleRowOrientationPolicy = MiddleRowOrientationPolicy()
    prior: MiddleRowPriorPolicy = MiddleRowPriorPolicy()
    orientation_override: MiddleRowRunOrientation = MiddleRowRunOrientation.AUTO

    def contract_dict(self) -> dict[str, object]:
        return {
            "batchPolicy": self.batch.as_dict(),
            "coordinateSpace": MIDDLE_ROW_COORDINATE_SPACE,
            "evidenceSelector": MIDDLE_ROW_EVIDENCE_SELECTOR_VERSION,
            "exifPolicy": "pillow-imageops-exif-transpose-once-v1",
            "groupingPolicy": MIDDLE_ROW_GROUPING_VERSION,
            "maximumUnknownGap": MIDDLE_ROW_MAXIMUM_UNKNOWN_GAP,
            "orientationOverride": self.orientation_override.value,
            "orientationPolicy": self.orientation.as_dict(),
            "priorPolicy": self.prior.as_dict(),
            "proofPolicy": MIDDLE_ROW_PROOF_POLICY_VERSION,
            "variantId": MIDDLE_ROW_RANGE_VARIANT,
        }


DEFAULT_MIDDLE_ROW_RUNTIME_POLICY = MiddleRowRuntimePolicy()
MIDDLE_ROW_RECOGNIZER_CONTRACT_FINGERPRINT_V4 = hashlib.sha256(
    json.dumps(
        DEFAULT_MIDDLE_ROW_RUNTIME_POLICY.contract_dict(),
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
).hexdigest()


@dataclass(frozen=True, slots=True)
class MiddleRowSourcePayload:
    source: SemiAutomaticSelectionSource
    content: bytes


@dataclass(frozen=True, slots=True)
class MiddleRowRecognition:
    raw_text: str
    confidence: float


class MiddleRowRecognitionBackend(Protocol):
    version: str
    model_name: str
    model_fingerprint: str
    model_files: Mapping[str, str]
    runtime_name: str
    runtime_version: str

    def recognize_many(
        self,
        rgb_images: Sequence[NDArray[np.uint8]],
    ) -> Sequence[object]: ...


@dataclass(slots=True)
class MiddleRowOcrMetrics:
    calls: int = 0
    internal_batches: int = 0
    crops: int = 0
    recognition_seconds: float = 0.0
    preprocessing_seconds: float = 0.0
    inference_seconds: float = 0.0

    @property
    def batch_fill_ratio(self) -> float:
        if not self.internal_batches:
            return 0.0
        return self.crops / (self.internal_batches * 9)


class MiddleRowPaddleRecognitionAdapter:
    """Pinned adapter over the public recognition-only Paddle batch method."""

    version = MIDDLE_ROW_PADDLE_ADAPTER_VERSION

    def __init__(
        self,
        backend: MiddleRowRecognitionBackend,
        *,
        internal_batch_size: int = 9,
    ) -> None:
        if internal_batch_size != 9:
            raise ValueError("The pinned Paddle recognizer supports batches up to nine crops.")
        if not callable(getattr(backend, "recognize_many", None)):
            raise TypeError("The Paddle backend must expose recognition-only recognize_many().")
        self._backend = backend
        self.internal_batch_size = internal_batch_size
        self.metrics = MiddleRowOcrMetrics()
        self.identity = {
            "adapterVersion": self.version,
            "internalBatchSize": internal_batch_size,
            "modelFiles": dict(backend.model_files),
            "modelFingerprint": backend.model_fingerprint,
            "modelName": backend.model_name,
            "ocrVersion": backend.version,
            "runtimeName": backend.runtime_name,
            "runtimeVersion": backend.runtime_version,
        }
        self.fingerprint = _canonical_sha256(self.identity)

    def recognize_many(
        self,
        crops: Sequence[NDArray[np.uint8]],
    ) -> tuple[MiddleRowRecognition, ...]:
        if not crops:
            return ()
        output: list[MiddleRowRecognition] = []
        self.metrics.calls += 1
        started = perf_counter()
        for offset in range(0, len(crops), self.internal_batch_size):
            page = tuple(crops[offset : offset + self.internal_batch_size])
            preprocessing_before = float(getattr(self._backend, "preprocessing_seconds", 0.0))
            inference_before = float(getattr(self._backend, "inference_seconds", 0.0))
            values = tuple(self._backend.recognize_many(page))
            self.metrics.preprocessing_seconds += max(
                0.0,
                float(getattr(self._backend, "preprocessing_seconds", 0.0)) - preprocessing_before,
            )
            self.metrics.inference_seconds += max(
                0.0,
                float(getattr(self._backend, "inference_seconds", 0.0)) - inference_before,
            )
            if len(values) != len(page):
                raise ValueError("Paddle batch result count differs from its crop count.")
            self.metrics.internal_batches += 1
            self.metrics.crops += len(page)
            for value in values:
                raw_text = getattr(value, "raw_text", None)
                confidence = getattr(value, "confidence", None)
                if (
                    not isinstance(raw_text, str)
                    or isinstance(confidence, bool)
                    or not isinstance(confidence, int | float)
                ):
                    raise ValueError("Paddle recognition result has an invalid contract.")
                output.append(MiddleRowRecognition(raw_text=raw_text, confidence=float(confidence)))
        self.metrics.recognition_seconds += perf_counter() - started
        return tuple(output)


def build_middle_row_paddle_adapter(model_root: Path) -> MiddleRowPaddleRecognitionAdapter:
    from game_predictor_worker.images.sequence_ocr import PaddleSequenceNumberRecognizer

    return MiddleRowPaddleRecognitionAdapter(PaddleSequenceNumberRecognizer(model_root))


@dataclass(frozen=True, slots=True)
class MiddleRowOrientationCalibration:
    orientation: MiddleRowRunOrientation | None
    orientation_source: MiddleRowOrientationSource
    orientation_override: MiddleRowRunOrientation
    sample_indexes: tuple[int, ...]
    proof_counts: Mapping[str, int]
    unresolved: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "orientation": None if self.orientation is None else self.orientation.value,
            "orientationCalibrationProofs": dict(self.proof_counts),
            "orientationCalibrationSamples": list(self.sample_indexes),
            "orientationOverride": self.orientation_override.value,
            "orientationSource": self.orientation_source.value,
            "orientationUnresolved": self.unresolved,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> MiddleRowOrientationCalibration:
        orientation_raw = value.get("orientation")
        samples = value.get("orientationCalibrationSamples", [])
        proofs = value.get("orientationCalibrationProofs", {})
        if not isinstance(samples, list) or not isinstance(proofs, Mapping):
            raise ValueError("Orientation checkpoint has invalid calibration data.")
        return cls(
            orientation=(
                None if orientation_raw is None else MiddleRowRunOrientation(str(orientation_raw))
            ),
            orientation_source=MiddleRowOrientationSource(str(value["orientationSource"])),
            orientation_override=MiddleRowRunOrientation(str(value["orientationOverride"])),
            sample_indexes=tuple(int(item) for item in samples),
            proof_counts={str(key): int(count) for key, count in proofs.items()},
            unresolved=bool(value.get("orientationUnresolved", False)),
        )


class MiddleRowLatticePriorTracker:
    """Median, position-only prior with bounded history and drift reset."""

    def __init__(
        self,
        policy: MiddleRowPriorPolicy | None = None,
        *,
        checkpoint: Mapping[str, object] | None = None,
    ) -> None:
        self.policy = policy or MiddleRowPriorPolicy()
        self._history: deque[MiddleRowLatticePrior] = deque(maxlen=self.policy.history_size)
        self._consecutive_failures = 0
        if checkpoint is not None:
            self._restore(checkpoint)

    def prior_for(self, source_index: int) -> MiddleRowLatticePrior | None:
        if source_index % self.policy.full_search_interval == 0 or not self._history:
            return None
        return self.current

    @property
    def current(self) -> MiddleRowLatticePrior | None:
        if not self._history:
            return None
        return MiddleRowLatticePrior(
            column_axes=cast(
                tuple[float, float, float],
                tuple(
                    float(median(item.column_axes[index] for item in self._history))
                    for index in range(3)
                ),
            ),
            row_axes=cast(
                tuple[float, float, float],
                tuple(
                    float(median(item.row_axes[index] for item in self._history))
                    for index in range(3)
                ),
            ),
            local_scale=float(median(item.local_scale for item in self._history)),
            local_slant=float(median(item.local_slant for item in self._history)),
        )

    def record_success(self, location: MiddleRowLocation, dimensions: ImageDimensions) -> None:
        if location.locator_mode is MiddleRowLocatorMode.FULL_LATTICE:
            self._history.append(location.as_prior(dimensions))
        self._consecutive_failures = 0

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.policy.reset_after_failures:
            self._history.clear()
            self._consecutive_failures = 0

    def checkpoint(self) -> dict[str, object]:
        return {
            "consecutiveFailures": self._consecutive_failures,
            "history": [
                {
                    "columnAxes": list(value.column_axes),
                    "localScale": value.local_scale,
                    "localSlant": value.local_slant,
                    "rowAxes": list(value.row_axes),
                }
                for value in self._history
            ],
            "policy": self.policy.as_dict(),
        }

    def _restore(self, checkpoint: Mapping[str, object]) -> None:
        if checkpoint.get("policy") != self.policy.as_dict():
            raise ValueError("Lattice-prior checkpoint policy differs from runtime.")
        history = checkpoint.get("history", [])
        if not isinstance(history, list):
            raise ValueError("Lattice-prior checkpoint history is invalid.")
        for item in history:
            if not isinstance(item, Mapping):
                raise ValueError("Lattice-prior checkpoint item is invalid.")
            columns = tuple(
                _checkpoint_float(value) for value in cast(Sequence[object], item["columnAxes"])
            )
            rows = tuple(
                _checkpoint_float(value) for value in cast(Sequence[object], item["rowAxes"])
            )
            if len(columns) != 3 or len(rows) != 3:
                raise ValueError("Lattice-prior checkpoint axes are invalid.")
            self._history.append(
                MiddleRowLatticePrior(
                    column_axes=(columns[0], columns[1], columns[2]),
                    row_axes=(rows[0], rows[1], rows[2]),
                    local_scale=_checkpoint_float(item["localScale"]),
                    local_slant=_checkpoint_float(item["localSlant"]),
                )
            )
        self._consecutive_failures = _checkpoint_int(checkpoint.get("consecutiveFailures", 0))


@dataclass(slots=True)
class MiddleRowRuntimeCounters:
    values: dict[str, int] = field(default_factory=dict)

    def increment(self, key: str, amount: int = 1) -> None:
        self.values[key] = self.values.get(key, 0) + amount


class MiddleRowBatchRuntime:
    """Map one fixed source batch to ordered exact-or-unknown observations."""

    def __init__(
        self,
        *,
        run_id: UUID,
        expected_ranges: ExpectedRangeTable,
        rotation: MiddleRowRunOrientation,
        locator: MiddleRowTripleLocator,
        recognizer: MiddleRowPaddleRecognitionAdapter,
        policy: MiddleRowRuntimePolicy | None = None,
        prior_tracker: MiddleRowLatticePriorTracker | None = None,
    ) -> None:
        if rotation is MiddleRowRunOrientation.AUTO:
            raise ValueError("Batch runtime requires a calibrated fixed orientation.")
        self.run_id = run_id
        self.expected_ranges = expected_ranges
        self.rotation = rotation
        self.locator = locator
        self.recognizer = recognizer
        self.policy = policy or DEFAULT_MIDDLE_ROW_RUNTIME_POLICY
        self.prior_tracker = prior_tracker or MiddleRowLatticePriorTracker(self.policy.prior)
        self.resolver = MiddleRowExactResolver(expected_ranges)
        self.runtime_fingerprint = _canonical_sha256(
            {
                "componentFingerprint": locator.fingerprint,
                "expectedRangeTable": expected_ranges.fingerprint,
                "recognitionAdapter": recognizer.identity,
                "rotation": rotation.value,
                "runtimePolicy": self.policy.contract_dict(),
                "runtimeVersion": MIDDLE_ROW_RUNTIME_FINGERPRINT_VERSION,
            }
        )
        self.counters = MiddleRowRuntimeCounters()

    def process_batch(
        self,
        payloads: Sequence[MiddleRowSourcePayload],
    ) -> tuple[RangeEvidenceResult, ...]:
        if not payloads or len(payloads) > self.policy.batch.source_batch_size:
            raise ValueError("Source batch is empty or exceeds its pinned size.")
        pending: list[
            tuple[int, SemiAutomaticSelectionSource, CanonicalSourceImage, MiddleRowLocation]
        ] = []
        ordered: list[RangeEvidenceResult | None] = [None] * len(payloads)
        locator_seconds: dict[int, float] = {}
        rotation_seconds: dict[int, float] = {}
        for offset, payload in enumerate(payloads):
            try:
                canonical = canonicalize_source_image(payload.content)
                rotation_started = perf_counter()
                oriented = rotate_canonical_source(canonical, self.rotation)
                rotation_seconds[offset] = perf_counter() - rotation_started
            except ValueError:
                ordered[offset] = self._unknown(
                    payload.source,
                    MiddleRowUnknownReason.SOURCE_DECODE_ERROR,
                    {"orientation": self.rotation.value},
                )
                self.counters.increment("sourceDecodeErrors")
                continue
            prior = self.prior_tracker.prior_for(payload.source.source_index)
            locator_started = perf_counter()
            located = self.locator.locate(oriented, prior=prior)
            locator_seconds[offset] = perf_counter() - locator_started
            if located.location is None:
                self.prior_tracker.record_failure()
                reason = located.reason_code or MiddleRowUnknownReason.UNKNOWN_LATTICE
                ordered[offset] = self._unknown(
                    payload.source,
                    reason,
                    _source_diagnostics(
                        canonical,
                        self.rotation,
                        {
                            **dict(located.diagnostics),
                            "locatorVersion": MIDDLE_ROW_LOCATOR_VERSION,
                            "processingTimes": {
                                "decodeSeconds": canonical.decode_seconds,
                                "exifSeconds": canonical.exif_seconds,
                                "locatorSeconds": locator_seconds[offset],
                                "ocrBatchSeconds": 0.0,
                                "rotationSeconds": rotation_seconds[offset],
                            },
                        },
                    ),
                )
                self._increment_unknown(reason)
                continue
            location = located.location
            self.prior_tracker.record_success(location, oriented.oriented_dimensions)
            self.counters.increment("locatedSources")
            self.counters.increment(
                "locatorFullLattice"
                if location.locator_mode is MiddleRowLocatorMode.FULL_LATTICE
                else "locatorPriorFallback"
            )
            pending.append((offset, payload.source, canonical, location))

        crops = tuple(crop.rgb for _, _, _, location in pending for crop in location.crops)
        recognition_started = perf_counter()
        recognized = self.recognizer.recognize_many(crops)
        recognition_seconds = perf_counter() - recognition_started
        if len(recognized) != len(pending) * 3:
            raise ValueError("Middle-row OCR results lost their source mapping.")
        for pending_index, (offset, source, canonical, location) in enumerate(pending):
            triple = recognized[pending_index * 3 : pending_index * 3 + 3]
            proof = MiddleRowTripleProof(
                recognized_texts=cast(
                    tuple[str, str, str], tuple(item.raw_text for item in triple)
                ),
                recognition_confidences=cast(
                    tuple[float, float, float], tuple(item.confidence for item in triple)
                ),
                crop_completeness=cast(
                    tuple[bool, bool, bool], tuple(crop.complete for crop in location.crops)
                ),
                crop_readability=cast(
                    tuple[bool, bool, bool], tuple(crop.readable for crop in location.crops)
                ),
            )
            resolved = self.resolver.resolve(proof)
            diagnostics = _source_diagnostics(
                canonical,
                self.rotation,
                {
                    "cropCompleteness": [crop.complete for crop in location.crops],
                    "cropBoxes": [crop.box.as_dict() for crop in location.crops],
                    "localQualityScores": [
                        {
                            "brightRatio": crop.quality.bright_ratio,
                            "contrast": crop.quality.contrast,
                            "darkRatio": crop.quality.dark_ratio,
                            "directionalBlurRatio": crop.quality.directional_blur_ratio,
                            "edgeDensity": crop.quality.edge_density,
                            "readable": crop.readable,
                            "tenengrad": crop.quality.tenengrad,
                        }
                        for crop in location.crops
                    ],
                    "locatorAmbiguityMargin": location.ambiguity_margin,
                    "locatorMode": location.locator_mode.value,
                    "locatorScore": location.best_score,
                    "locatorVersion": MIDDLE_ROW_LOCATOR_VERSION,
                    "ocrPreprocessingVersion": MIDDLE_ROW_OCR_PREPROCESSING_VERSION,
                    "paddleAdapterVersion": self.recognizer.version,
                    "processingTimes": {
                        "decodeSeconds": canonical.decode_seconds,
                        "exifSeconds": canonical.exif_seconds,
                        "locatorSeconds": locator_seconds[offset],
                        "ocrBatchSeconds": recognition_seconds,
                        "rotationSeconds": rotation_seconds[offset],
                    },
                    "recognizedTexts": list(proof.recognized_texts),
                    "recognitionConfidences": list(proof.recognition_confidences),
                    "runtimeFingerprint": self.runtime_fingerprint,
                },
            )
            readability = float(
                mean(crop.quality.tenengrad + crop.quality.contrast for crop in location.crops)
            )
            if isinstance(resolved, ExactRangeObservation):
                diagnostics.update(
                    {
                        "matchedExpectedRange": (
                            resolved.matched_expected_range.sequence_range.as_dict()
                        ),
                        "proofType": resolved.proof_type,
                    }
                )
                self.counters.increment("exactSources")
                result = RangeEvidenceResult(
                    source=source,
                    status=RangeEvidenceStatus.EXACT_RANGE,
                    observed_range=resolved.matched_expected_range.sequence_range,
                    expected_index=resolved.matched_expected_range.expected_index,
                    confidence=resolved.average_confidence,
                    reason_codes=(resolved.proof_type,),
                    local_readability_score=readability,
                    minimum_ocr_confidence=min(resolved.recognition_confidences),
                    runtime_diagnostics=diagnostics,
                )
            else:
                self._increment_unknown(resolved.reason_code)
                result = self._unknown(
                    source,
                    resolved.reason_code,
                    diagnostics,
                    confidence=(
                        float(mean(resolved.recognition_confidences))
                        if resolved.recognition_confidences
                        else None
                    ),
                )
            ordered[offset] = result
        self.counters.values["ocrCalls"] = self.recognizer.metrics.calls
        self.counters.values["ocrInternalBatches"] = self.recognizer.metrics.internal_batches
        self.counters.values["ocrCrops"] = self.recognizer.metrics.crops
        if any(item is None for item in ordered):
            raise ValueError("A source batch produced an incomplete ordered result.")
        completed = tuple(cast(RangeEvidenceResult, item) for item in ordered)
        return tuple(self._with_observation_key(item) for item in completed)

    def _unknown(
        self,
        source: SemiAutomaticSelectionSource,
        reason: MiddleRowUnknownReason,
        diagnostics: Mapping[str, object],
        *,
        confidence: float | None = None,
    ) -> RangeEvidenceResult:
        status = (
            RangeEvidenceStatus.RANGE_AMBIGUOUS
            if reason
            in {
                MiddleRowUnknownReason.AMBIGUOUS_LATTICE,
                MiddleRowUnknownReason.AMBIGUOUS_EXPECTED_RANGE,
            }
            else (
                RangeEvidenceStatus.SOURCE_ERROR
                if reason is MiddleRowUnknownReason.SOURCE_DECODE_ERROR
                else RangeEvidenceStatus.RANGE_UNREADABLE
            )
        )
        return RangeEvidenceResult(
            source=source,
            status=status,
            observed_range=None,
            expected_index=None,
            confidence=confidence,
            reason_codes=(reason.value,),
            runtime_diagnostics={
                "ocrPreprocessingVersion": MIDDLE_ROW_OCR_PREPROCESSING_VERSION,
                "paddleAdapterVersion": self.recognizer.version,
                "runtimeFingerprint": self.runtime_fingerprint,
                **dict(diagnostics),
            },
        )

    def _with_observation_key(self, value: RangeEvidenceResult) -> RangeEvidenceResult:
        return replace(
            value,
            observation_key=middle_row_observation_key(
                run_id=self.run_id,
                source=value.source,
                runtime_fingerprint=self.runtime_fingerprint,
            ),
        )

    def _increment_unknown(self, reason: MiddleRowUnknownReason) -> None:
        key = {
            MiddleRowUnknownReason.UNKNOWN_ORIENTATION: "unknownOrientation",
            MiddleRowUnknownReason.UNKNOWN_LATTICE: "unknownLattice",
            MiddleRowUnknownReason.AMBIGUOUS_LATTICE: "unknownAmbiguousLattice",
            MiddleRowUnknownReason.INCOMPLETE_MIDDLE_ROW: "unknownLattice",
            MiddleRowUnknownReason.CROP_OUT_OF_BOUNDS: "unknownCropCompleteness",
            MiddleRowUnknownReason.CROP_POSSIBLY_CLIPPED: "unknownCropCompleteness",
            MiddleRowUnknownReason.LOCAL_BLUR: "unknownLocalBlur",
            MiddleRowUnknownReason.LOW_LOCAL_CONTRAST: "unknownLowContrast",
            MiddleRowUnknownReason.INCOMPLETE_OCR: "unknownIncompleteOcr",
            MiddleRowUnknownReason.NON_NUMERIC_OCR: "unknownNonNumeric",
            MiddleRowUnknownReason.LOW_OCR_CONFIDENCE: "unknownConfidence",
            MiddleRowUnknownReason.INCONSISTENT_TRIPLE: "unknownInconsistentTriple",
            MiddleRowUnknownReason.NO_EXPECTED_RANGE_MATCH: "unknownExpectedRange",
            MiddleRowUnknownReason.AMBIGUOUS_EXPECTED_RANGE: "unknownExpectedRange",
            MiddleRowUnknownReason.OUTSIDE_RUN_RANGE: "unknownExpectedRange",
            MiddleRowUnknownReason.SOURCE_DECODE_ERROR: "sourceDecodeErrors",
        }[reason]
        self.counters.increment(key)


def deterministic_orientation_sample_indexes(
    source_count: int,
    *,
    sample_count: int = 8,
) -> tuple[int, ...]:
    if source_count < 1 or sample_count < 1:
        return ()
    count = min(source_count, sample_count)
    if count == 1:
        return (0,)
    return tuple(
        sorted({round(index * (source_count - 1) / (count - 1)) for index in range(count)})
    )


def calibrate_middle_row_orientation(
    *,
    payloads: Sequence[MiddleRowSourcePayload],
    expected_ranges: ExpectedRangeTable,
    locator: MiddleRowTripleLocator,
    recognizer: MiddleRowPaddleRecognitionAdapter,
    override: MiddleRowRunOrientation = MiddleRowRunOrientation.AUTO,
    policy: MiddleRowOrientationPolicy | None = None,
) -> MiddleRowOrientationCalibration:
    resolved_policy = policy or MiddleRowOrientationPolicy()
    if len(payloads) > resolved_policy.calibration_source_count:
        raise ValueError("Orientation calibration received more than its bounded sample count.")
    indexes = tuple(payload.source.source_index for payload in payloads)
    if override is not MiddleRowRunOrientation.AUTO:
        return MiddleRowOrientationCalibration(
            orientation=override,
            orientation_source=MiddleRowOrientationSource.MANUAL_OVERRIDE,
            orientation_override=override,
            sample_indexes=(),
            proof_counts={override.value: 0},
            unresolved=False,
        )
    resolver = MiddleRowExactResolver(expected_ranges)
    candidates = [MiddleRowRunOrientation.DEG_0, MiddleRowRunOrientation.DEG_180]
    proof_counts = {candidate.value: 0 for candidate in candidates}
    canonical_samples: list[tuple[int, CanonicalSourceImage]] = []
    for payload in payloads:
        try:
            canonical_samples.append(
                (payload.source.source_index, canonicalize_source_image(payload.content))
            )
        except ValueError:
            continue
    for _, canonical in canonical_samples:
        for candidate in tuple(candidates):
            rotated = rotate_canonical_source(canonical, candidate)
            located = locator.locate(rotated)
            if located.location is None:
                continue
            recognized = recognizer.recognize_many(
                tuple(crop.rgb for crop in located.location.crops)
            )
            proof = MiddleRowTripleProof(
                recognized_texts=cast(
                    tuple[str, str, str], tuple(item.raw_text for item in recognized)
                ),
                recognition_confidences=cast(
                    tuple[float, float, float], tuple(item.confidence for item in recognized)
                ),
            )
            if isinstance(resolver.resolve(proof), ExactRangeObservation):
                proof_counts[candidate.value] += 1
        winner = _orientation_winner(
            candidates,
            proof_counts,
            minimum=resolved_policy.early_stop_exact_proofs,
        )
        if winner is not None:
            return MiddleRowOrientationCalibration(
                orientation=winner,
                orientation_source=MiddleRowOrientationSource.AUTOMATIC,
                orientation_override=override,
                sample_indexes=indexes,
                proof_counts=proof_counts,
                unresolved=False,
            )
    requires_quarter_turn = bool(
        canonical_samples
        and all(proof_counts[value.value] == 0 for value in candidates)
        and (
            all(item.exif_orientation == 1 for _, item in canonical_samples)
            or any(
                item.oriented_dimensions.width > item.oriented_dimensions.height
                for _, item in canonical_samples
            )
        )
    )
    if requires_quarter_turn:
        quarter = [MiddleRowRunOrientation.DEG_90, MiddleRowRunOrientation.DEG_270]
        candidates.extend(quarter)
        proof_counts.update({candidate.value: 0 for candidate in quarter})
        for _, canonical in canonical_samples[: resolved_policy.additional_probe_budget]:
            for candidate in quarter:
                located = locator.locate(rotate_canonical_source(canonical, candidate))
                if located.location is None:
                    continue
                recognized = recognizer.recognize_many(
                    tuple(crop.rgb for crop in located.location.crops)
                )
                proof = MiddleRowTripleProof(
                    recognized_texts=cast(
                        tuple[str, str, str], tuple(item.raw_text for item in recognized)
                    ),
                    recognition_confidences=cast(
                        tuple[float, float, float], tuple(item.confidence for item in recognized)
                    ),
                )
                if isinstance(resolver.resolve(proof), ExactRangeObservation):
                    proof_counts[candidate.value] += 1
    winner = _orientation_winner(candidates, proof_counts, minimum=1)
    return MiddleRowOrientationCalibration(
        orientation=winner,
        orientation_source=MiddleRowOrientationSource.AUTOMATIC,
        orientation_override=override,
        sample_indexes=indexes,
        proof_counts=proof_counts,
        unresolved=winner is None,
    )


def rotate_canonical_source(
    source: CanonicalSourceImage,
    orientation: MiddleRowRunOrientation,
) -> CanonicalSourceImage:
    if orientation is MiddleRowRunOrientation.AUTO:
        raise ValueError("A canonical source cannot be rotated by auto.")
    rotation = orientation.degrees
    k = {0: 0, 90: 3, 180: 2, 270: 1}[rotation]
    rgb = source.rgb if k == 0 else np.ascontiguousarray(np.rot90(source.rgb, k=k))
    dimensions = ImageDimensions(width=int(rgb.shape[1]), height=int(rgb.shape[0]))
    return CanonicalSourceImage(
        rgb=rgb,
        raw_dimensions=source.raw_dimensions,
        oriented_dimensions=dimensions,
        exif_orientation=source.exif_orientation,
    )


def middle_row_observation_key(
    *,
    run_id: UUID,
    source: SemiAutomaticSelectionSource,
    runtime_fingerprint: str,
) -> str:
    return _canonical_sha256(
        {
            "keyVersion": MIDDLE_ROW_OBSERVATION_KEY_VERSION,
            "runId": str(run_id),
            "runtimeFingerprint": runtime_fingerprint,
            "source": source.as_dict(),
        }
    )


def _orientation_winner(
    candidates: Sequence[MiddleRowRunOrientation],
    proof_counts: Mapping[str, int],
    *,
    minimum: int,
) -> MiddleRowRunOrientation | None:
    ordered = sorted(
        ((proof_counts.get(candidate.value, 0), candidate) for candidate in candidates),
        key=lambda item: (-item[0], int(item[1].value)),
    )
    if not ordered or ordered[0][0] < minimum:
        return None
    if len(ordered) > 1 and ordered[0][0] == ordered[1][0]:
        return None
    return ordered[0][1]


def _source_diagnostics(
    canonical: CanonicalSourceImage,
    rotation: MiddleRowRunOrientation,
    values: Mapping[str, object],
) -> dict[str, object]:
    rotated = rotate_canonical_source(canonical, rotation)
    return {
        "coordinateSpace": canonical.coordinate_space,
        "exifOrientation": canonical.exif_orientation,
        "orientedHeight": rotated.oriented_dimensions.height,
        "orientedWidth": rotated.oriented_dimensions.width,
        "rawHeight": canonical.raw_dimensions.height,
        "rawWidth": canonical.raw_dimensions.width,
        "runRotation": rotation.value,
        **dict(values),
    }


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _checkpoint_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise TypeError("checkpoint value is not numeric")
    return float(value)


def _checkpoint_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise TypeError("checkpoint value is not an integer")
    return int(value)


__all__ = [
    "DEFAULT_MIDDLE_ROW_RUNTIME_POLICY",
    "MIDDLE_ROW_PADDLE_ADAPTER_VERSION",
    "MIDDLE_ROW_RECOGNIZER_CONTRACT_FINGERPRINT_V4",
    "MIDDLE_ROW_RUNTIME_FINGERPRINT_VERSION",
    "MiddleRowBatchPolicy",
    "MiddleRowBatchRuntime",
    "MiddleRowLatticePriorTracker",
    "MiddleRowOrientationCalibration",
    "MiddleRowOrientationPolicy",
    "MiddleRowOrientationSource",
    "MiddleRowPaddleRecognitionAdapter",
    "MiddleRowPriorPolicy",
    "MiddleRowRecognition",
    "MiddleRowRunOrientation",
    "MiddleRowRuntimePolicy",
    "MiddleRowSourcePayload",
    "build_middle_row_paddle_adapter",
    "calibrate_middle_row_orientation",
    "deterministic_orientation_sample_indexes",
    "middle_row_observation_key",
    "rotate_canonical_source",
]
