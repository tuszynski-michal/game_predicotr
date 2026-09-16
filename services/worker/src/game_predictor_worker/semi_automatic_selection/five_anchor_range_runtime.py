"""Recognition-only runtime for the five-anchor range OCR v6 contract.

This module deliberately stops at one source-local ``RangeEvidenceResult``.
It does not group sources, write checkpoints, create jobs or use filenames as
range evidence.  The only path to ``EXACT_RANGE`` is the v6 proof resolver.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from statistics import mean
from time import perf_counter
from typing import cast
from uuid import UUID

import cv2
import numpy as np
from numpy.typing import NDArray

from .contracts import RangeEvidenceResult, RangeEvidenceStatus, SemiAutomaticSelectionSource
from .five_anchor_range_label_locator import (
    FIVE_ANCHOR_RANGE_LABEL_LOCATOR_VERSION,
    FiveAnchorLabelCrop,
    FiveAnchorRangeLabelLocator,
)
from .five_anchor_range_proof import (
    FIVE_ANCHOR_PROOF_POLICY_VERSION,
    FIVE_ANCHOR_PROOF_TYPE,
    FIVE_ANCHOR_RANGE_VARIANT,
    FiveAnchorExactRangeObservation,
    FiveAnchorExactResolver,
    FiveAnchorExpectedRangeTable,
    FiveAnchorProofPosition,
    FiveAnchorProofUnknownReason,
    FiveAnchorRecognition,
    FiveAnchorRecognitionProof,
    FiveAnchorUnknownRangeObservation,
)
from .middle_row_locator import CanonicalSourceImage, canonicalize_source_image
from .middle_row_runtime import MiddleRowPaddleRecognitionAdapter

FIVE_ANCHOR_BATCH_POLICY_VERSION = "five-anchor-source-batches-v1"
FIVE_ANCHOR_READABILITY_POLICY_VERSION = "five-anchor-local-readability-v1"
FIVE_ANCHOR_RUNTIME_FINGERPRINT_VERSION = "five-anchor-range-runtime-v1"
FIVE_ANCHOR_OBSERVATION_KEY_VERSION = "five-anchor-observation-key-v1"


@dataclass(frozen=True, slots=True)
class FiveAnchorBatchPolicy:
    """Bounded source and Paddle batch sizes for runtime v6."""

    version: str = FIVE_ANCHOR_BATCH_POLICY_VERSION
    source_batch_size: int = 6
    internal_ocr_batch_size: int = 9
    cpu_math_library_num_threads: int = 1
    checkpoint_interval_batches: int = 1

    def __post_init__(self) -> None:
        if self.source_batch_size != 6:
            raise ValueError("V6 source batches must contain exactly six sources.")
        if self.internal_ocr_batch_size != 9 or self.cpu_math_library_num_threads != 1:
            raise ValueError("V6 Paddle execution must retain the bounded CPU contract.")
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
class FiveAnchorReadabilityPolicy:
    """Cheap fail-closed gate for the direct label crops before Paddle OCR."""

    version: str = FIVE_ANCHOR_READABILITY_POLICY_VERSION
    minimum_tenengrad: float = 7.0
    minimum_contrast: float = 18.0
    minimum_edge_density: float = 0.004
    maximum_dark_ratio: float = 0.96
    maximum_bright_ratio: float = 0.96

    def __post_init__(self) -> None:
        values = (
            self.minimum_tenengrad,
            self.minimum_contrast,
            self.minimum_edge_density,
            self.maximum_dark_ratio,
            self.maximum_bright_ratio,
        )
        if (
            self.minimum_tenengrad <= 0
            or self.minimum_contrast <= 0
            or not 0 < self.minimum_edge_density <= 1
            or not 0 < self.maximum_dark_ratio <= 1
            or not 0 < self.maximum_bright_ratio <= 1
            or any(not np.isfinite(value) for value in values)
        ):
            raise ValueError("Five-anchor readability policy is invalid.")

    def as_dict(self) -> dict[str, object]:
        return {
            "maximumBrightRatio": self.maximum_bright_ratio,
            "maximumDarkRatio": self.maximum_dark_ratio,
            "minimumContrast": self.minimum_contrast,
            "minimumEdgeDensity": self.minimum_edge_density,
            "minimumTenengrad": self.minimum_tenengrad,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class FiveAnchorRuntimePolicy:
    batch: FiveAnchorBatchPolicy = FiveAnchorBatchPolicy()
    readability: FiveAnchorReadabilityPolicy = FiveAnchorReadabilityPolicy()

    def contract_dict(self) -> dict[str, object]:
        return {
            "batchPolicy": self.batch.as_dict(),
            "exifPolicy": "pillow-imageops-exif-transpose-once-v1",
            "proofPolicy": FIVE_ANCHOR_PROOF_POLICY_VERSION,
            "readabilityPolicy": self.readability.as_dict(),
            "variantId": FIVE_ANCHOR_RANGE_VARIANT,
        }


DEFAULT_FIVE_ANCHOR_RUNTIME_POLICY = FiveAnchorRuntimePolicy()
FIVE_ANCHOR_RECOGNIZER_CONTRACT_FINGERPRINT_V6 = hashlib.sha256(
    json.dumps(
        DEFAULT_FIVE_ANCHOR_RUNTIME_POLICY.contract_dict(),
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
).hexdigest()


@dataclass(frozen=True, slots=True)
class FiveAnchorSourcePayload:
    source: SemiAutomaticSelectionSource
    content: bytes


@dataclass(frozen=True, slots=True)
class FiveAnchorLocalQuality:
    tenengrad: float
    contrast: float
    edge_density: float
    dark_ratio: float
    bright_ratio: float

    def as_dict(self) -> dict[str, object]:
        return {
            "brightRatio": self.bright_ratio,
            "contrast": self.contrast,
            "darkRatio": self.dark_ratio,
            "edgeDensity": self.edge_density,
            "tenengrad": self.tenengrad,
        }


@dataclass(slots=True)
class FiveAnchorRuntimeCounters:
    values: dict[str, int] = field(default_factory=dict)

    def increment(self, key: str, amount: int = 1) -> None:
        self.values[key] = self.values.get(key, 0) + amount


@dataclass(frozen=True, slots=True)
class _LocatedSource:
    offset: int
    source: SemiAutomaticSelectionSource
    canonical: CanonicalSourceImage
    crops: tuple[
        FiveAnchorLabelCrop,
        FiveAnchorLabelCrop,
        FiveAnchorLabelCrop,
        FiveAnchorLabelCrop,
        FiveAnchorLabelCrop,
    ]
    qualities: tuple[
        FiveAnchorLocalQuality,
        FiveAnchorLocalQuality,
        FiveAnchorLocalQuality,
        FiveAnchorLocalQuality,
        FiveAnchorLocalQuality,
    ]
    locator_seconds: float
    locator_diagnostics: Mapping[str, object]


class FiveAnchorBatchRuntime:
    """Map one fixed batch to source-ordered, v6 proof-bound evidence."""

    def __init__(
        self,
        *,
        run_id: UUID,
        expected_ranges: FiveAnchorExpectedRangeTable,
        locator: FiveAnchorRangeLabelLocator,
        recognizer: MiddleRowPaddleRecognitionAdapter,
        policy: FiveAnchorRuntimePolicy | None = None,
    ) -> None:
        self.run_id = run_id
        self.expected_ranges = expected_ranges
        self.locator = locator
        self.recognizer = recognizer
        self.policy = policy or DEFAULT_FIVE_ANCHOR_RUNTIME_POLICY
        if recognizer.internal_batch_size != self.policy.batch.internal_ocr_batch_size:
            raise ValueError("The v6 runtime and recognizer have incompatible OCR batch sizes.")
        self.resolver = FiveAnchorExactResolver(expected_ranges)
        self.runtime_fingerprint = _canonical_sha256(
            {
                "componentFingerprint": locator.fingerprint,
                "expectedRangeTable": expected_ranges.fingerprint,
                "recognitionAdapter": recognizer.identity,
                "runtimePolicy": self.policy.contract_dict(),
                "runtimeVersion": FIVE_ANCHOR_RUNTIME_FINGERPRINT_VERSION,
            }
        )
        self.counters = FiveAnchorRuntimeCounters()

    def process_batch(
        self,
        payloads: Sequence[FiveAnchorSourcePayload],
    ) -> tuple[RangeEvidenceResult, ...]:
        if not payloads or len(payloads) > self.policy.batch.source_batch_size:
            raise ValueError("Source batch is empty or exceeds its pinned size.")
        ordered: list[RangeEvidenceResult | None] = [None] * len(payloads)
        pending: list[_LocatedSource] = []
        for offset, payload in enumerate(payloads):
            try:
                canonical = canonicalize_source_image(payload.content)
            except ValueError:
                ordered[offset] = self._unknown(
                    payload.source,
                    "SOURCE_DECODE_ERROR",
                    {"runOrientation": "exif_canonical"},
                    status=RangeEvidenceStatus.SOURCE_ERROR,
                )
                self.counters.increment("sourceDecodeErrors")
                continue
            started = perf_counter()
            located = self.locator.locate(canonical.rgb)
            locator_seconds = perf_counter() - started
            if located.location is None:
                reason = (
                    located.reason_code.value
                    if located.reason_code is not None
                    else "UNKNOWN_LOCATION"
                )
                ordered[offset] = self._unknown(
                    payload.source,
                    reason,
                    _source_diagnostics(
                        canonical,
                        {
                            **dict(located.diagnostics),
                            "locatorSeconds": locator_seconds,
                            "locatorVersion": FIVE_ANCHOR_RANGE_LABEL_LOCATOR_VERSION,
                        },
                    ),
                )
                self.counters.increment("unknownLocator")
                continue
            crops = located.location.crops
            qualities = tuple(_quality(crop.rgb) for crop in crops)
            unreadable = next(
                (
                    crop.position
                    for crop, quality in zip(crops, qualities, strict=True)
                    if not _is_readable(quality, self.policy.readability)
                ),
                None,
            )
            if unreadable is not None:
                ordered[offset] = self._unknown(
                    payload.source,
                    FiveAnchorProofUnknownReason.LOCAL_BLUR.value,
                    _source_diagnostics(
                        canonical,
                        {
                            **dict(located.diagnostics),
                            "cropBoxes": [crop.box.as_dict() for crop in crops],
                            "localQualityScores": [quality.as_dict() for quality in qualities],
                            "locatorSeconds": locator_seconds,
                            "locatorVersion": FIVE_ANCHOR_RANGE_LABEL_LOCATOR_VERSION,
                            "unreadableAnchor": unreadable.value,
                        },
                    ),
                )
                self.counters.increment("unknownLocalBlur")
                continue
            pending.append(
                _LocatedSource(
                    offset=offset,
                    source=payload.source,
                    canonical=canonical,
                    crops=crops,
                    qualities=cast(
                        tuple[
                            FiveAnchorLocalQuality,
                            FiveAnchorLocalQuality,
                            FiveAnchorLocalQuality,
                            FiveAnchorLocalQuality,
                            FiveAnchorLocalQuality,
                        ],
                        qualities,
                    ),
                    locator_seconds=locator_seconds,
                    locator_diagnostics=located.diagnostics,
                )
            )
            self.counters.increment("locatedSources")

        recognition_started = perf_counter()
        recognized = self.recognizer.recognize_many(
            tuple(crop.rgb for item in pending for crop in item.crops)
        )
        recognition_seconds = perf_counter() - recognition_started
        if len(recognized) != len(pending) * 5:
            raise ValueError("Five-anchor OCR results lost their source mapping.")
        for index, item in enumerate(pending):
            values = recognized[index * 5 : index * 5 + 5]
            proof = FiveAnchorRecognitionProof(
                observations=cast(
                    tuple[
                        FiveAnchorRecognition,
                        FiveAnchorRecognition,
                        FiveAnchorRecognition,
                        FiveAnchorRecognition,
                        FiveAnchorRecognition,
                    ],
                    tuple(
                        FiveAnchorRecognition(
                            position=FiveAnchorProofPosition(crop.position.value),
                            recognized_text=value.raw_text,
                            recognition_confidence=value.confidence,
                            crop_complete=crop.complete,
                            crop_readable=True,
                        )
                        for crop, value in zip(item.crops, values, strict=True)
                    ),
                )
            )
            resolved = self.resolver.resolve(proof)
            diagnostics = _source_diagnostics(
                item.canonical,
                {
                    **dict(item.locator_diagnostics),
                    "cropBoxes": [crop.box.as_dict() for crop in item.crops],
                    "cropCompleteness": [crop.complete for crop in item.crops],
                    "cropModes": [crop.mode.value for crop in item.crops],
                    "localQualityScores": [quality.as_dict() for quality in item.qualities],
                    "locatorSeconds": item.locator_seconds,
                    "locatorVersion": FIVE_ANCHOR_RANGE_LABEL_LOCATOR_VERSION,
                    "ocrBatchSeconds": recognition_seconds,
                    "paddleAdapterVersion": self.recognizer.version,
                    "recognizedTexts": [entry.recognized_text for entry in proof.observations],
                    "recognitionConfidences": [
                        entry.recognition_confidence for entry in proof.observations
                    ],
                    "runtimeFingerprint": self.runtime_fingerprint,
                },
            )
            result = self._result_from_proof(item, proof, resolved, diagnostics)
            ordered[item.offset] = result

        self.counters.values["ocrCalls"] = self.recognizer.metrics.calls
        self.counters.values["ocrInternalBatches"] = self.recognizer.metrics.internal_batches
        self.counters.values["ocrCrops"] = self.recognizer.metrics.crops
        if any(item is None for item in ordered):
            raise ValueError("A source batch produced an incomplete ordered result.")
        return tuple(
            self._with_observation_key(cast(RangeEvidenceResult, item)) for item in ordered
        )

    def _result_from_proof(
        self,
        item: _LocatedSource,
        proof: FiveAnchorRecognitionProof,
        resolved: FiveAnchorExactRangeObservation | FiveAnchorUnknownRangeObservation,
        diagnostics: dict[str, object],
    ) -> RangeEvidenceResult:
        readability = float(
            mean(quality.tenengrad + quality.contrast for quality in item.qualities)
        )
        if isinstance(resolved, FiveAnchorExactRangeObservation):
            self.counters.increment("exactSources")
            diagnostics.update(
                {
                    "confirmingAnchors": [position.value for position in resolved.confirmations],
                    "matchedExpectedRange": (
                        resolved.matched_expected_range.sequence_range.as_dict()
                    ),
                    "proofType": resolved.proof_type,
                }
            )
            return RangeEvidenceResult(
                source=item.source,
                status=RangeEvidenceStatus.EXACT_RANGE,
                observed_range=resolved.matched_expected_range.sequence_range,
                expected_index=resolved.matched_expected_range.expected_index,
                confidence=resolved.average_confidence,
                reason_codes=(FIVE_ANCHOR_PROOF_TYPE,),
                local_readability_score=readability,
                minimum_ocr_confidence=min(
                    entry.recognition_confidence for entry in proof.observations
                ),
                runtime_diagnostics=diagnostics,
            )
        self._increment_proof_unknown(resolved.reason_code)
        return self._unknown(
            item.source,
            resolved.reason_code.value,
            diagnostics,
            status=(
                RangeEvidenceStatus.RANGE_AMBIGUOUS
                if resolved.reason_code
                in {
                    FiveAnchorProofUnknownReason.AMBIGUOUS_EXPECTED_RANGE,
                    FiveAnchorProofUnknownReason.CONFLICTING_ANCHOR_VALUES,
                }
                else RangeEvidenceStatus.RANGE_UNREADABLE
            ),
            confidence=(
                float(mean(entry.recognition_confidence for entry in proof.observations))
                if proof.observations
                else None
            ),
        )

    def _unknown(
        self,
        source: SemiAutomaticSelectionSource,
        reason: str,
        diagnostics: Mapping[str, object],
        *,
        status: RangeEvidenceStatus = RangeEvidenceStatus.RANGE_UNREADABLE,
        confidence: float | None = None,
    ) -> RangeEvidenceResult:
        return RangeEvidenceResult(
            source=source,
            status=status,
            observed_range=None,
            expected_index=None,
            confidence=confidence,
            reason_codes=(reason,),
            runtime_diagnostics={
                "paddleAdapterVersion": self.recognizer.version,
                "runtimeFingerprint": self.runtime_fingerprint,
                **dict(diagnostics),
            },
        )

    def _with_observation_key(self, value: RangeEvidenceResult) -> RangeEvidenceResult:
        return replace(
            value,
            observation_key=five_anchor_observation_key(
                run_id=self.run_id,
                source=value.source,
                runtime_fingerprint=self.runtime_fingerprint,
            ),
        )

    def _increment_proof_unknown(self, reason: FiveAnchorProofUnknownReason) -> None:
        self.counters.increment(
            {
                FiveAnchorProofUnknownReason.CROP_POSSIBLY_CLIPPED: "unknownCropCompleteness",
                FiveAnchorProofUnknownReason.LOCAL_BLUR: "unknownLocalBlur",
                FiveAnchorProofUnknownReason.INCOMPLETE_OCR: "unknownIncompleteOcr",
                FiveAnchorProofUnknownReason.NON_NUMERIC_OCR: "unknownNonNumeric",
                FiveAnchorProofUnknownReason.LOW_OCR_CONFIDENCE: "unknownConfidence",
                FiveAnchorProofUnknownReason.INSUFFICIENT_SPANNED_EVIDENCE: (
                    "unknownInsufficientSpan"
                ),
                FiveAnchorProofUnknownReason.CONFLICTING_ANCHOR_VALUES: "unknownConflictingAnchors",
                FiveAnchorProofUnknownReason.NO_EXPECTED_RANGE_MATCH: "unknownExpectedRange",
                FiveAnchorProofUnknownReason.AMBIGUOUS_EXPECTED_RANGE: "unknownExpectedRange",
                FiveAnchorProofUnknownReason.OUTSIDE_RUN_RANGE: "unknownExpectedRange",
                FiveAnchorProofUnknownReason.PARTIAL_RANGE_REQUIRES_MANUAL_REVIEW: (
                    "unknownPartialRange"
                ),
            }[reason]
        )


def five_anchor_observation_key(
    *,
    run_id: UUID,
    source: SemiAutomaticSelectionSource,
    runtime_fingerprint: str,
) -> str:
    return _canonical_sha256(
        {
            "keyVersion": FIVE_ANCHOR_OBSERVATION_KEY_VERSION,
            "runId": str(run_id),
            "runtimeFingerprint": runtime_fingerprint,
            "source": source.as_dict(),
        }
    )


def _quality(rgb: NDArray[np.uint8]) -> FiveAnchorLocalQuality:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    horizontal = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    vertical = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    low, high = np.percentile(gray, (10, 98))
    edges = cv2.Canny(gray, 50, 150)
    return FiveAnchorLocalQuality(
        tenengrad=float(np.mean(np.sqrt(horizontal * horizontal + vertical * vertical))),
        contrast=float(high - low),
        edge_density=float(np.count_nonzero(edges) / edges.size),
        dark_ratio=float(np.count_nonzero(gray <= 8) / gray.size),
        bright_ratio=float(np.count_nonzero(gray >= 247) / gray.size),
    )


def _is_readable(quality: FiveAnchorLocalQuality, policy: FiveAnchorReadabilityPolicy) -> bool:
    return (
        quality.tenengrad >= policy.minimum_tenengrad
        and quality.contrast >= policy.minimum_contrast
        and quality.edge_density >= policy.minimum_edge_density
        and quality.dark_ratio <= policy.maximum_dark_ratio
        and quality.bright_ratio <= policy.maximum_bright_ratio
    )


def _source_diagnostics(
    canonical: CanonicalSourceImage,
    values: Mapping[str, object],
) -> dict[str, object]:
    return {
        "coordinateSpace": canonical.coordinate_space,
        "exifOrientation": canonical.exif_orientation,
        "orientedHeight": canonical.oriented_dimensions.height,
        "orientedWidth": canonical.oriented_dimensions.width,
        "rawHeight": canonical.raw_dimensions.height,
        "rawWidth": canonical.raw_dimensions.width,
        "runOrientation": "exif_canonical",
        **dict(values),
    }


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


__all__ = [
    "DEFAULT_FIVE_ANCHOR_RUNTIME_POLICY",
    "FIVE_ANCHOR_RECOGNIZER_CONTRACT_FINGERPRINT_V6",
    "FIVE_ANCHOR_RUNTIME_FINGERPRINT_VERSION",
    "FiveAnchorBatchPolicy",
    "FiveAnchorBatchRuntime",
    "FiveAnchorLocalQuality",
    "FiveAnchorReadabilityPolicy",
    "FiveAnchorRuntimeCounters",
    "FiveAnchorRuntimePolicy",
    "FiveAnchorSourcePayload",
    "five_anchor_observation_key",
]
