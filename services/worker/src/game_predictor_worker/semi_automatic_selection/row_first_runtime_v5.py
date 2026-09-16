"""Durable, recognition-only runtime for transition-safe row-first OCR v5.

The runtime intentionally accepts only staged source bytes and range-only
contracts.  It cannot call board detection, board/cell crop pipelines, or
symbol inference.  Each source is EXIF-canonicalized once, then its independent
label rows are located and passed to the pinned recognition-only Paddle port.
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

from .contracts import (
    RangeEvidenceResult,
    RangeEvidenceStatus,
    SemiAutomaticSelectionSource,
)
from .middle_row_locator import CanonicalSourceImage, canonicalize_source_image
from .middle_row_runtime import MiddleRowPaddleRecognitionAdapter
from .range_proof_v5 import (
    ROW_FIRST_PROOF_POLICY_VERSION,
    ROW_FIRST_RANGE_VARIANT,
    ROW_FIRST_VERIFIED_PROOF_TYPE,
    RangeProofUnknownReason,
    RowExpectedRangeTable,
    RowFirstExactResolver,
    RowTripleProof,
    UnknownRowRangeObservation,
    VerifiedRangeCandidate,
    verify_range_candidate,
)
from .row_first_locator_v5 import (
    ROW_FIRST_LOCATOR_COORDINATE_SPACE,
    ROW_FIRST_LOCATOR_VERSION,
    RowFirstLabelCrop,
    RowFirstLocation,
    RowFirstLocatorUnknownReason,
    RowFirstTripleLocator,
)

ROW_FIRST_BATCH_POLICY_VERSION = "row-first-source-batches-v1"
ROW_FIRST_RUNTIME_FINGERPRINT_VERSION = "row-first-range-runtime-v1"
ROW_FIRST_OBSERVATION_KEY_VERSION = "row-first-observation-key-v1"
ROW_FIRST_ORIENTATION_POLICY_VERSION = "row-first-exif-canonical-orientation-v1"


@dataclass(frozen=True, slots=True)
class RowFirstBatchPolicy:
    """Bounded source/crop execution identity for a v5 durable run."""

    version: str = ROW_FIRST_BATCH_POLICY_VERSION
    source_batch_size: int = 6
    internal_ocr_batch_size: int = 9
    cpu_math_library_num_threads: int = 1
    checkpoint_interval_batches: int = 1

    def __post_init__(self) -> None:
        if self.source_batch_size != 6:
            raise ValueError("V5 source batches must contain exactly six sources.")
        if self.internal_ocr_batch_size != 9 or self.cpu_math_library_num_threads != 1:
            raise ValueError("V5 Paddle execution must retain the bounded CPU contract.")
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
class RowFirstOrientationPolicy:
    """EXIF transpose is the only orientation normalization in v5.

    A stored source must not be OCR-probed again merely to guess an additional
    rotation.  The canonical EXIF-oriented RGB source therefore remains in its
    own pixel orientation for the locator and recognizer.
    """

    version: str = ROW_FIRST_ORIENTATION_POLICY_VERSION
    orientation: str = "exif_canonical"

    def __post_init__(self) -> None:
        if self.orientation != "exif_canonical":
            raise ValueError("V5 range OCR supports only EXIF-canonical orientation.")

    def as_dict(self) -> dict[str, str]:
        return {"orientation": self.orientation, "version": self.version}


@dataclass(frozen=True, slots=True)
class RowFirstRuntimePolicy:
    batch: RowFirstBatchPolicy = RowFirstBatchPolicy()
    orientation: RowFirstOrientationPolicy = RowFirstOrientationPolicy()

    def contract_dict(self) -> dict[str, object]:
        return {
            "batchPolicy": self.batch.as_dict(),
            "coordinateSpace": ROW_FIRST_LOCATOR_COORDINATE_SPACE,
            "exifPolicy": "pillow-imageops-exif-transpose-once-v1",
            "orientationPolicy": self.orientation.as_dict(),
            "proofPolicy": ROW_FIRST_PROOF_POLICY_VERSION,
            "variantId": ROW_FIRST_RANGE_VARIANT,
        }


DEFAULT_ROW_FIRST_RUNTIME_POLICY = RowFirstRuntimePolicy()
ROW_FIRST_RECOGNIZER_CONTRACT_FINGERPRINT_V5 = hashlib.sha256(
    json.dumps(
        DEFAULT_ROW_FIRST_RUNTIME_POLICY.contract_dict(),
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
).hexdigest()


@dataclass(frozen=True, slots=True)
class RowFirstSourcePayload:
    source: SemiAutomaticSelectionSource
    content: bytes


@dataclass(slots=True)
class RowFirstRuntimeCounters:
    values: dict[str, int] = field(default_factory=dict)

    def increment(self, key: str, amount: int = 1) -> None:
        self.values[key] = self.values.get(key, 0) + amount


@dataclass(frozen=True, slots=True)
class _LocatedSource:
    offset: int
    source: SemiAutomaticSelectionSource
    canonical: CanonicalSourceImage
    location: RowFirstLocation
    locator_seconds: float


class RowFirstBatchRuntime:
    """Return source-ordered, two-row-proof `exact` or fail-closed unknown."""

    def __init__(
        self,
        *,
        run_id: UUID,
        expected_ranges: RowExpectedRangeTable,
        locator: RowFirstTripleLocator,
        recognizer: MiddleRowPaddleRecognitionAdapter,
        policy: RowFirstRuntimePolicy | None = None,
    ) -> None:
        self.run_id = run_id
        self.expected_ranges = expected_ranges
        self.locator = locator
        self.recognizer = recognizer
        self.policy = policy or DEFAULT_ROW_FIRST_RUNTIME_POLICY
        if recognizer.internal_batch_size != self.policy.batch.internal_ocr_batch_size:
            raise ValueError("The v5 runtime and recognizer have incompatible OCR batch sizes.")
        self.resolver = RowFirstExactResolver(expected_ranges)
        self.runtime_fingerprint = _canonical_sha256(
            {
                "componentFingerprint": locator.fingerprint,
                "expectedRangeTable": expected_ranges.fingerprint,
                "recognitionAdapter": recognizer.identity,
                "runtimePolicy": self.policy.contract_dict(),
                "runtimeVersion": ROW_FIRST_RUNTIME_FINGERPRINT_VERSION,
            }
        )
        self.counters = RowFirstRuntimeCounters()

    def process_batch(
        self,
        payloads: Sequence[RowFirstSourcePayload],
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
                    {"orientation": self.policy.orientation.orientation},
                    status=RangeEvidenceStatus.SOURCE_ERROR,
                )
                self.counters.increment("sourceDecodeErrors")
                continue
            locator_started = perf_counter()
            located = self.locator.locate(canonical)
            locator_seconds = perf_counter() - locator_started
            if located.location is None:
                reason = located.reason_code or RowFirstLocatorUnknownReason.UNKNOWN_ROWS
                ordered[offset] = self._unknown(
                    payload.source,
                    reason.value,
                    _source_diagnostics(
                        canonical,
                        {
                            **dict(located.diagnostics),
                            "locatorSeconds": locator_seconds,
                            "locatorVersion": ROW_FIRST_LOCATOR_VERSION,
                        },
                    ),
                    status=(
                        RangeEvidenceStatus.RANGE_AMBIGUOUS
                        if reason
                        in {
                            RowFirstLocatorUnknownReason.AMBIGUOUS_ROWS,
                            RowFirstLocatorUnknownReason.POSITION_PRIOR_MISMATCH,
                        }
                        else RangeEvidenceStatus.RANGE_UNREADABLE
                    ),
                )
                self._increment_locator_unknown(reason)
                continue
            pending.append(
                _LocatedSource(
                    offset=offset,
                    source=payload.source,
                    canonical=canonical,
                    location=located.location,
                    locator_seconds=locator_seconds,
                )
            )
            self.counters.increment("locatedSources")
            self.counters.increment("locatedRows", len(located.location.rows))

        crops = tuple(
            crop.rgb for item in pending for row in item.location.rows for crop in row.crops
        )
        recognition_started = perf_counter()
        recognized = self.recognizer.recognize_many(crops)
        recognition_seconds = perf_counter() - recognition_started
        expected_crop_count = sum(len(item.location.rows) * 3 for item in pending)
        if len(recognized) != expected_crop_count:
            raise ValueError("Row-first OCR results lost their source or row mapping.")

        cursor = 0
        for item in pending:
            row_observations = []
            row_diagnostics: list[dict[str, object]] = []
            all_crops: list[RowFirstLabelCrop] = []
            for row in item.location.rows:
                triple = recognized[cursor : cursor + 3]
                cursor += 3
                all_crops.extend(row.crops)
                proof = RowTripleProof(
                    row=row.row,
                    recognized_texts=cast(
                        tuple[str, str, str], tuple(value.raw_text for value in triple)
                    ),
                    recognition_confidences=cast(
                        tuple[float, float, float], tuple(value.confidence for value in triple)
                    ),
                    crop_completeness=cast(
                        tuple[bool, bool, bool], tuple(crop.complete for crop in row.crops)
                    ),
                    crop_readability=cast(
                        tuple[bool, bool, bool], tuple(crop.readable for crop in row.crops)
                    ),
                )
                resolved_row = self.resolver.resolve(proof)
                row_observations.append(resolved_row)
                row_diagnostics.append(
                    {
                        "cropBoxes": [crop.box.as_dict() for crop in row.crops],
                        "cropCompleteness": [crop.complete for crop in row.crops],
                        "cropReadability": [crop.readable for crop in row.crops],
                        "recognizedTexts": list(proof.recognized_texts),
                        "recognitionConfidences": list(proof.recognition_confidences),
                        "row": row.row.value,
                        "rowLocatorScore": row.score,
                        "rowSlope": row.baseline_slope,
                    }
                )
            verified = verify_range_candidate(tuple(row_observations))
            diagnostics = _source_diagnostics(
                item.canonical,
                {
                    "locatorSeconds": item.locator_seconds,
                    "locatorVersion": ROW_FIRST_LOCATOR_VERSION,
                    "ocrBatchSeconds": recognition_seconds,
                    "paddleAdapterVersion": self.recognizer.version,
                    "rows": row_diagnostics,
                    "runtimeFingerprint": self.runtime_fingerprint,
                },
            )
            if isinstance(verified, VerifiedRangeCandidate):
                diagnostics.update(
                    {
                        "matchedExpectedRange": (
                            verified.matched_expected_range.sequence_range.as_dict()
                        ),
                        "proofType": verified.proof_type,
                        "verifiedRows": [row.value for row in verified.verified_rows],
                    }
                )
                self.counters.increment("exactSources")
                value = RangeEvidenceResult(
                    source=item.source,
                    status=RangeEvidenceStatus.EXACT_RANGE,
                    observed_range=verified.matched_expected_range.sequence_range,
                    expected_index=verified.matched_expected_range.expected_index,
                    confidence=verified.average_confidence,
                    reason_codes=(ROW_FIRST_VERIFIED_PROOF_TYPE,),
                    local_readability_score=_readability_score(all_crops),
                    minimum_ocr_confidence=_minimum_confidence(row_observations),
                    runtime_diagnostics=diagnostics,
                )
            else:
                self._increment_proof_unknown(verified)
                value = self._unknown(
                    item.source,
                    verified.reason_code.value,
                    diagnostics,
                    status=(
                        RangeEvidenceStatus.RANGE_AMBIGUOUS
                        if verified.reason_code
                        in {
                            RangeProofUnknownReason.CONFLICTING_VISIBLE_ROWS,
                            RangeProofUnknownReason.AMBIGUOUS_EXPECTED_RANGE,
                        }
                        else RangeEvidenceStatus.RANGE_UNREADABLE
                    ),
                    confidence=(
                        float(mean(verified.recognition_confidences))
                        if verified.recognition_confidences
                        else None
                    ),
                )
            ordered[item.offset] = value

        self.counters.values["ocrCalls"] = self.recognizer.metrics.calls
        self.counters.values["ocrInternalBatches"] = self.recognizer.metrics.internal_batches
        self.counters.values["ocrCrops"] = self.recognizer.metrics.crops
        if any(item is None for item in ordered):
            raise ValueError("A source batch produced an incomplete ordered result.")
        return tuple(
            self._with_observation_key(cast(RangeEvidenceResult, item)) for item in ordered
        )

    def _unknown(
        self,
        source: SemiAutomaticSelectionSource,
        reason: str,
        diagnostics: Mapping[str, object],
        *,
        status: RangeEvidenceStatus,
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
            observation_key=row_first_observation_key(
                run_id=self.run_id,
                source=value.source,
                runtime_fingerprint=self.runtime_fingerprint,
            ),
        )

    def _increment_locator_unknown(self, reason: RowFirstLocatorUnknownReason) -> None:
        self.counters.increment(
            {
                RowFirstLocatorUnknownReason.UNKNOWN_ROWS: "unknownRows",
                RowFirstLocatorUnknownReason.AMBIGUOUS_ROWS: "unknownAmbiguousRows",
                RowFirstLocatorUnknownReason.POSITION_PRIOR_MISMATCH: "unknownPriorMismatch",
            }[reason]
        )

    def _increment_proof_unknown(self, value: UnknownRowRangeObservation) -> None:
        self.counters.increment(
            {
                RangeProofUnknownReason.FINAL_PROOF_INSUFFICIENT: "unknownSingleRowProof",
                RangeProofUnknownReason.COMPLETE_ROW_UNVERIFIED: "unknownCompleteRowUnverified",
                RangeProofUnknownReason.CONFLICTING_VISIBLE_ROWS: "unknownConflictingRows",
                RangeProofUnknownReason.CROP_POSSIBLY_CLIPPED: "unknownCropCompleteness",
                RangeProofUnknownReason.LOCAL_BLUR: "unknownLocalBlur",
                RangeProofUnknownReason.INCOMPLETE_OCR: "unknownIncompleteOcr",
                RangeProofUnknownReason.NON_NUMERIC_OCR: "unknownNonNumeric",
                RangeProofUnknownReason.LOW_OCR_CONFIDENCE: "unknownConfidence",
                RangeProofUnknownReason.INCONSISTENT_TRIPLE: "unknownInconsistentTriple",
                RangeProofUnknownReason.NO_EXPECTED_RANGE_MATCH: "unknownExpectedRange",
                RangeProofUnknownReason.AMBIGUOUS_EXPECTED_RANGE: "unknownExpectedRange",
                RangeProofUnknownReason.OUTSIDE_RUN_RANGE: "unknownExpectedRange",
                RangeProofUnknownReason.PARTIAL_RANGE_REQUIRES_MANUAL_REVIEW: "unknownPartialRange",
            }[value.reason_code]
        )


def row_first_observation_key(
    *,
    run_id: UUID,
    source: SemiAutomaticSelectionSource,
    runtime_fingerprint: str,
) -> str:
    return _canonical_sha256(
        {
            "keyVersion": ROW_FIRST_OBSERVATION_KEY_VERSION,
            "runId": str(run_id),
            "runtimeFingerprint": runtime_fingerprint,
            "source": source.as_dict(),
        }
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


def _readability_score(crops: Sequence[RowFirstLabelCrop]) -> float | None:
    if not crops:
        return None
    return float(mean(crop.quality.tenengrad + crop.quality.contrast for crop in crops))


def _minimum_confidence(
    observations: Sequence[object],
) -> float | None:
    values: list[float] = []
    for observation in observations:
        confidences = getattr(observation, "recognition_confidences", ())
        values.extend(float(value) for value in confidences)
    return min(values) if values else None


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


__all__ = [
    "DEFAULT_ROW_FIRST_RUNTIME_POLICY",
    "ROW_FIRST_RECOGNIZER_CONTRACT_FINGERPRINT_V5",
    "ROW_FIRST_RUNTIME_FINGERPRINT_VERSION",
    "RowFirstBatchPolicy",
    "RowFirstBatchRuntime",
    "RowFirstOrientationPolicy",
    "RowFirstRuntimePolicy",
    "RowFirstSourcePayload",
    "row_first_observation_key",
]
