"""Reconstructable, checksum-addressed cache for cheap scan observations."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import cast
from uuid import uuid4

from .contracts import (
    CandidateVerification,
    CandidateVerifier,
    CheapImageAnalyzer,
    CheapImageObservation,
    ImageSelectionSource,
    RangeEvidence,
    RangeLabelObservation,
    RepresentativeAssessment,
    SelectionContractError,
    SequenceRange,
)

IMAGE_SCAN_CACHE_CONTRACT = "image-selection-scan-cache-v1"
IMAGE_SCAN_CACHE_SCHEMA_VERSION = 1
IMAGE_VERIFICATION_CACHE_CONTRACT = "image-selection-verification-cache-v1"
IMAGE_VERIFICATION_CACHE_SCHEMA_VERSION = 1
_SHA256_LENGTH = 64
_MAX_BASELINE_SECONDS = 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class ImageScanCacheLookup:
    observation: CheapImageObservation | None
    baseline_scan_seconds: float = 0.0
    invalid: bool = False


class FileImageScanObservationCache:
    """Store one bounded canonical JSON artifact per JPEG and scan adapter."""

    def __init__(self, artifact_root: Path) -> None:
        self._root = artifact_root.resolve() / "data" / "cache" / "image-selection-scan"

    @property
    def root(self) -> Path:
        return self._root

    def get(
        self,
        source: ImageSelectionSource,
        *,
        scan_adapter_fingerprint: str,
    ) -> ImageScanCacheLookup:
        target = self._entry_path(
            source.checksum_sha256,
            scan_adapter_fingerprint=scan_adapter_fingerprint,
        )
        if not target.is_file():
            return ImageScanCacheLookup(None)
        try:
            value = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("Cache payload must be an object.")
            if (
                value.get("contract") != IMAGE_SCAN_CACHE_CONTRACT
                or value.get("schemaVersion") != IMAGE_SCAN_CACHE_SCHEMA_VERSION
                or value.get("scanAdapterFingerprint") != scan_adapter_fingerprint
                or value.get("sourceChecksumSha256") != source.checksum_sha256
            ):
                raise ValueError("Cache identity does not match its key.")
            baseline = float(value["baselineScanSeconds"])
            if not 0 <= baseline <= _MAX_BASELINE_SECONDS:
                raise ValueError("Cache baseline is outside its bounded range.")
            observation_value = value["observation"]
            if not isinstance(observation_value, dict) or "source" in observation_value:
                raise ValueError("Cache observation has an invalid shape.")
            restored_value = dict(observation_value)
            restored_value["source"] = source.to_dict()
            observation = CheapImageObservation.from_checkpoint_dict(restored_value)
            return ImageScanCacheLookup(
                replace(observation, source=source),
                baseline_scan_seconds=baseline,
            )
        except (OSError, UnicodeError, ValueError, TypeError, SelectionContractError):
            return ImageScanCacheLookup(None, invalid=True)

    def put(
        self,
        observation: CheapImageObservation,
        *,
        scan_adapter_fingerprint: str,
        baseline_scan_seconds: float,
    ) -> int:
        bounded_baseline = round(
            min(_MAX_BASELINE_SECONDS, max(0.0, baseline_scan_seconds)),
            6,
        )
        observation_value = observation.to_checkpoint_dict()
        observation_value.pop("source")
        payload = {
            "baselineScanSeconds": bounded_baseline,
            "contract": IMAGE_SCAN_CACHE_CONTRACT,
            "observation": observation_value,
            "scanAdapterFingerprint": scan_adapter_fingerprint,
            "schemaVersion": IMAGE_SCAN_CACHE_SCHEMA_VERSION,
            "sourceChecksumSha256": observation.source.checksum_sha256,
        }
        content = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        target = self._entry_path(
            observation.source.checksum_sha256,
            scan_adapter_fingerprint=scan_adapter_fingerprint,
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        # Keep the atomic-write helper name deliberately short. Repeating the
        # 64-character cache key and a full UUID here can cross the legacy
        # Windows MAX_PATH limit even though the final cache path is valid.
        temporary = target.parent / f".tmp-{uuid4().hex[:12]}.part"
        try:
            with temporary.open("xb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return len(content)

    def _entry_path(
        self,
        source_checksum: str,
        *,
        scan_adapter_fingerprint: str,
    ) -> Path:
        for value in (source_checksum, scan_adapter_fingerprint):
            if len(value) != _SHA256_LENGTH or any(
                character not in "0123456789abcdef" for character in value
            ):
                raise ValueError("Image scan cache keys must be lowercase SHA-256 values.")
        combined_key = hashlib.sha256(
            f"{scan_adapter_fingerprint}:{source_checksum}".encode("ascii")
        ).hexdigest()
        return self._root / combined_key[:2] / f"{combined_key}.json"


class CachedCheapImageAnalyzer:
    """Reuse cached scans while keeping all selector decisions outside the cache."""

    def __init__(
        self,
        delegate: CheapImageAnalyzer,
        cache: FileImageScanObservationCache,
        *,
        scan_adapter_fingerprint: str,
    ) -> None:
        self._delegate = delegate
        self._cache = cache
        self._scan_adapter_fingerprint = scan_adapter_fingerprint
        self._lock = Lock()
        self._hits = 0
        self._misses = 0
        self._invalid = 0
        self._writes = 0
        self._write_errors = 0
        self._written_bytes = 0
        self._estimated_saved_seconds = 0.0

    def analyze(self, source: ImageSelectionSource) -> CheapImageObservation:
        lookup = self._cache.get(
            source,
            scan_adapter_fingerprint=self._scan_adapter_fingerprint,
        )
        if lookup.observation is not None:
            with self._lock:
                self._hits += 1
                self._estimated_saved_seconds += lookup.baseline_scan_seconds
            return lookup.observation

        with self._lock:
            self._misses += 1
            if lookup.invalid:
                self._invalid += 1
        started_at = perf_counter()
        observation = self._delegate.analyze(source)
        baseline = perf_counter() - started_at
        try:
            written_bytes = self._cache.put(
                observation,
                scan_adapter_fingerprint=self._scan_adapter_fingerprint,
                baseline_scan_seconds=baseline,
            )
        except OSError:
            with self._lock:
                self._write_errors += 1
            return observation
        with self._lock:
            self._writes += 1
            self._written_bytes += written_bytes
        return observation

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "contract": IMAGE_SCAN_CACHE_CONTRACT,
                "estimatedSavedSeconds": round(self._estimated_saved_seconds, 6),
                "hitCount": self._hits,
                "invalidEntryCount": self._invalid,
                "missCount": self._misses,
                "scanAdapterFingerprint": self._scan_adapter_fingerprint,
                "schemaVersion": IMAGE_SCAN_CACHE_SCHEMA_VERSION,
                "writeCount": self._writes,
                "writeErrorCount": self._write_errors,
                "writtenBytes": self._written_bytes,
            }


@dataclass(frozen=True, slots=True)
class ImageVerificationCacheLookup:
    verification: CandidateVerification | None
    invalid: bool = False


class FileImageVerificationCache:
    """Store exact verification results for immutable JPEG/configuration pairs."""

    def __init__(self, artifact_root: Path) -> None:
        self._root = artifact_root.resolve() / "data" / "cache" / "image-selection-verification"

    @property
    def root(self) -> Path:
        return self._root

    def get(
        self,
        source_checksum: str,
        *,
        selector_fingerprint: str,
        expected_board_count: int | None,
        include_range_evidence: bool,
    ) -> ImageVerificationCacheLookup:
        target = self._entry_path(
            source_checksum,
            selector_fingerprint=selector_fingerprint,
            expected_board_count=expected_board_count,
            include_range_evidence=include_range_evidence,
        )
        if not target.is_file():
            return ImageVerificationCacheLookup(None)
        try:
            value = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("Verification cache payload must be an object.")
            if (
                value.get("contract") != IMAGE_VERIFICATION_CACHE_CONTRACT
                or value.get("schemaVersion") != IMAGE_VERIFICATION_CACHE_SCHEMA_VERSION
                or value.get("selectorFingerprint") != selector_fingerprint
                or value.get("sourceChecksumSha256") != source_checksum
                or value.get("expectedBoardCount") != expected_board_count
                or value.get("includeRangeEvidence") is not include_range_evidence
            ):
                raise ValueError("Verification cache identity does not match its key.")
            return ImageVerificationCacheLookup(_verification_from_dict(value["verification"]))
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, SelectionContractError):
            return ImageVerificationCacheLookup(None, invalid=True)

    def put(
        self,
        source_checksum: str,
        verification: CandidateVerification,
        *,
        selector_fingerprint: str,
        expected_board_count: int | None,
        include_range_evidence: bool,
    ) -> int:
        payload = {
            "contract": IMAGE_VERIFICATION_CACHE_CONTRACT,
            "expectedBoardCount": expected_board_count,
            "includeRangeEvidence": include_range_evidence,
            "schemaVersion": IMAGE_VERIFICATION_CACHE_SCHEMA_VERSION,
            "selectorFingerprint": selector_fingerprint,
            "sourceChecksumSha256": source_checksum,
            "verification": _verification_to_dict(verification),
        }
        content = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        target = self._entry_path(
            source_checksum,
            selector_fingerprint=selector_fingerprint,
            expected_board_count=expected_board_count,
            include_range_evidence=include_range_evidence,
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.parent / f".tmp-{uuid4().hex[:12]}.part"
        try:
            with temporary.open("xb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return len(content)

    def _entry_path(
        self,
        source_checksum: str,
        *,
        selector_fingerprint: str,
        expected_board_count: int | None,
        include_range_evidence: bool,
    ) -> Path:
        for value in (source_checksum, selector_fingerprint):
            if len(value) != _SHA256_LENGTH or any(
                character not in "0123456789abcdef" for character in value
            ):
                raise ValueError("Image verification cache keys must be lowercase SHA-256 values.")
        mode = "range" if include_range_evidence else "representative"
        board_count = "unknown" if expected_board_count is None else str(expected_board_count)
        combined_key = hashlib.sha256(
            f"{selector_fingerprint}:{source_checksum}:{board_count}:{mode}".encode("ascii")
        ).hexdigest()
        return self._root / combined_key[:2] / f"{combined_key}.json"


class CachedCandidateVerifier:
    """Reuse exact full-verification results without changing selector decisions."""

    def __init__(
        self,
        delegate: CandidateVerifier,
        cache: FileImageVerificationCache,
        *,
        selector_fingerprint: str,
        compatible_selector_fingerprints: tuple[str, ...] = (),
    ) -> None:
        self._delegate = delegate
        self._cache = cache
        self._selector_fingerprint = selector_fingerprint
        self._compatible_selector_fingerprints = tuple(
            fingerprint
            for fingerprint in dict.fromkeys(compatible_selector_fingerprints)
            if fingerprint != selector_fingerprint
        )
        self._lock = Lock()
        self._hits = 0
        self._compatible_hits = 0
        self._misses = 0
        self._invalid = 0
        self._writes = 0
        self._write_errors = 0
        self._written_bytes = 0

    def verify(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        return self._one(
            observation,
            expected_board_count=expected_board_count,
            include_range_evidence=True,
        )

    def verify_expected(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
        expected_range: SequenceRange,
    ) -> CandidateVerification:
        """Forward order-guided verification without polluting normal cache keys."""

        verify_expected = getattr(self._delegate, "verify_expected", None)
        if callable(verify_expected):
            return cast(
                CandidateVerification,
                verify_expected(
                    observation,
                    expected_board_count=expected_board_count,
                    expected_range=expected_range,
                ),
            )
        return self._delegate.verify(
            observation,
            expected_board_count=expected_board_count,
        )

    def assess_representative(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        return self._one(
            observation,
            expected_board_count=expected_board_count,
            include_range_evidence=False,
        )

    def verify_many(
        self,
        observations: tuple[CheapImageObservation, ...],
        *,
        expected_board_count: int | None,
        include_range_evidence: bool,
    ) -> tuple[CandidateVerification, ...]:
        resolved: dict[int, CandidateVerification] = {}
        missing_indexes: list[int] = []
        missing_observations: list[CheapImageObservation] = []
        for index, observation in enumerate(observations):
            lookup = self._lookup(
                observation,
                expected_board_count=expected_board_count,
                include_range_evidence=include_range_evidence,
            )
            if lookup.verification is not None:
                resolved[index] = lookup.verification
                with self._lock:
                    self._hits += 1
                continue
            missing_indexes.append(index)
            missing_observations.append(observation)
            with self._lock:
                self._misses += 1
                if lookup.invalid:
                    self._invalid += 1

        if missing_observations:
            verify_many = getattr(self._delegate, "verify_many", None)
            if callable(verify_many):
                calculated = tuple(
                    verify_many(
                        tuple(missing_observations),
                        expected_board_count=expected_board_count,
                        include_range_evidence=include_range_evidence,
                    )
                )
            elif include_range_evidence:
                calculated = tuple(
                    self._delegate.verify(
                        observation,
                        expected_board_count=expected_board_count,
                    )
                    for observation in missing_observations
                )
            else:
                assess = getattr(self._delegate, "assess_representative", None)
                calculated = tuple(
                    (
                        assess(observation, expected_board_count=expected_board_count)
                        if callable(assess)
                        else self._delegate.verify(
                            observation,
                            expected_board_count=expected_board_count,
                        )
                    )
                    for observation in missing_observations
                )
            if len(calculated) != len(missing_observations):
                raise SelectionContractError(
                    "IMAGE_SELECTION_VERIFY_RESULT_INVALID",
                    "Candidate batch verification returned an invalid result.",
                )
            for index, observation, verification in zip(
                missing_indexes,
                missing_observations,
                calculated,
                strict=True,
            ):
                if not isinstance(verification, CandidateVerification):
                    raise SelectionContractError(
                        "IMAGE_SELECTION_VERIFY_RESULT_INVALID",
                        "Candidate batch verification returned an invalid result.",
                    )
                resolved[index] = verification
                self._store(
                    observation,
                    verification,
                    expected_board_count=expected_board_count,
                    include_range_evidence=include_range_evidence,
                )
        return tuple(resolved[index] for index in range(len(observations)))

    def verify_fast_many(
        self,
        observations: tuple[CheapImageObservation, ...],
        *,
        expected_board_count: int | None,
    ) -> tuple[CandidateVerification, ...]:
        verify_fast_many = getattr(self._delegate, "verify_fast_many", None)
        if callable(verify_fast_many):
            results = tuple(
                verify_fast_many(
                    observations,
                    expected_board_count=expected_board_count,
                )
            )
        else:
            verify_fast = getattr(self._delegate, "verify_fast", None)
            results = tuple(
                (
                    verify_fast(observation, expected_board_count=expected_board_count)
                    if callable(verify_fast)
                    else self._delegate.verify(
                        observation,
                        expected_board_count=expected_board_count,
                    )
                )
                for observation in observations
            )
        if len(results) != len(observations) or any(
            not isinstance(result, CandidateVerification) for result in results
        ):
            raise SelectionContractError(
                "IMAGE_SELECTION_VERIFY_RESULT_INVALID",
                "Fast candidate batch verification returned an invalid result.",
            )
        return results

    def record_adaptive_range_stop(
        self,
        reason: str,
        *,
        evidence_count: int,
        candidate_count: int,
    ) -> None:
        recorder = getattr(self._delegate, "record_adaptive_range_stop", None)
        if callable(recorder):
            recorder(
                reason,
                evidence_count=evidence_count,
                candidate_count=candidate_count,
            )

    def record_staged_fast_outcome(
        self,
        outcome: str,
        *,
        evidence_count: int,
    ) -> None:
        recorder = getattr(self._delegate, "record_staged_fast_outcome", None)
        if callable(recorder):
            recorder(outcome, evidence_count=evidence_count)

    def _one(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
        include_range_evidence: bool,
    ) -> CandidateVerification:
        lookup = self._lookup(
            observation,
            expected_board_count=expected_board_count,
            include_range_evidence=include_range_evidence,
        )
        if lookup.verification is not None:
            with self._lock:
                self._hits += 1
            return lookup.verification
        with self._lock:
            self._misses += 1
            if lookup.invalid:
                self._invalid += 1
        if include_range_evidence:
            result = self._delegate.verify(
                observation,
                expected_board_count=expected_board_count,
            )
        else:
            assess = getattr(self._delegate, "assess_representative", None)
            result = (
                assess(observation, expected_board_count=expected_board_count)
                if callable(assess)
                else self._delegate.verify(
                    observation,
                    expected_board_count=expected_board_count,
                )
            )
        self._store(
            observation,
            result,
            expected_board_count=expected_board_count,
            include_range_evidence=include_range_evidence,
        )
        return result

    def _lookup(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
        include_range_evidence: bool,
    ) -> ImageVerificationCacheLookup:
        invalid = False
        fingerprints = (
            self._selector_fingerprint,
            *self._compatible_selector_fingerprints,
        )
        for index, fingerprint in enumerate(fingerprints):
            lookup = self._cache.get(
                observation.source.checksum_sha256,
                selector_fingerprint=fingerprint,
                expected_board_count=expected_board_count,
                include_range_evidence=include_range_evidence,
            )
            invalid = invalid or lookup.invalid
            if lookup.verification is None:
                continue
            if index > 0:
                with self._lock:
                    self._compatible_hits += 1
                self._store(
                    observation,
                    lookup.verification,
                    expected_board_count=expected_board_count,
                    include_range_evidence=include_range_evidence,
                )
            return lookup
        return ImageVerificationCacheLookup(None, invalid=invalid)

    def _store(
        self,
        observation: CheapImageObservation,
        verification: CandidateVerification,
        *,
        expected_board_count: int | None,
        include_range_evidence: bool,
    ) -> None:
        try:
            written = self._cache.put(
                observation.source.checksum_sha256,
                verification,
                selector_fingerprint=self._selector_fingerprint,
                expected_board_count=expected_board_count,
                include_range_evidence=include_range_evidence,
            )
        except OSError:
            with self._lock:
                self._write_errors += 1
            return
        with self._lock:
            self._writes += 1
            self._written_bytes += written

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "contract": IMAGE_VERIFICATION_CACHE_CONTRACT,
                "hitCount": self._hits,
                "compatibleHitCount": self._compatible_hits,
                "compatibleSelectorFingerprints": list(self._compatible_selector_fingerprints),
                "invalidEntryCount": self._invalid,
                "missCount": self._misses,
                "schemaVersion": IMAGE_VERIFICATION_CACHE_SCHEMA_VERSION,
                "selectorFingerprint": self._selector_fingerprint,
                "writeCount": self._writes,
                "writeErrorCount": self._write_errors,
                "writtenBytes": self._written_bytes,
            }


def _verification_to_dict(value: CandidateVerification) -> dict[str, object]:
    recognized = value.range_evidence.recognized_range
    return {
        "rangeEvidence": {
            "labelObservations": [
                observation.to_dict() for observation in value.range_evidence.label_observations
            ],
            "range": None if recognized is None else recognized.to_dict(),
            "reasonCodes": list(value.range_evidence.reason_codes),
        },
        "representative": {
            "boardCount": value.representative.board_count,
            "fullFrameVisible": value.representative.full_frame_visible,
            "geometryComplete": value.representative.geometry_complete,
            "reasonCodes": list(value.representative.reason_codes),
        },
    }


def _verification_from_dict(value: object) -> CandidateVerification:
    if not isinstance(value, dict):
        raise ValueError("Cached verification must be an object.")
    representative = value["representative"]
    range_evidence = value["rangeEvidence"]
    if not isinstance(representative, dict) or not isinstance(range_evidence, dict):
        raise ValueError("Cached verification sections must be objects.")
    recognized_value = range_evidence.get("range")
    recognized = None
    if recognized_value is not None:
        if not isinstance(recognized_value, dict):
            raise ValueError("Cached range must be an object.")
        recognized = SequenceRange(
            int(recognized_value["start"]),
            int(recognized_value["end"]),
            float(recognized_value["confidence"]),
        )
    board_count = representative.get("boardCount")
    return CandidateVerification(
        representative=RepresentativeAssessment(
            board_count=None if board_count is None else int(board_count),
            geometry_complete=_strict_bool(representative["geometryComplete"]),
            full_frame_visible=_strict_bool(representative["fullFrameVisible"]),
            reason_codes=_reason_codes(representative.get("reasonCodes")),
        ),
        range_evidence=RangeEvidence(
            recognized_range=recognized,
            reason_codes=_reason_codes(range_evidence.get("reasonCodes")),
            label_observations=tuple(
                RangeLabelObservation.from_dict(item)
                for item in _observation_values(range_evidence.get("labelObservations", []))
            ),
        ),
    )


def _strict_bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("Cached boolean field is invalid.")
    return value


def _reason_codes(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("Cached reason codes are invalid.")
    return tuple(value)


def _observation_values(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("Cached range-label observations are invalid.")
    return value


__all__ = [
    "CachedCandidateVerifier",
    "CachedCheapImageAnalyzer",
    "FileImageScanObservationCache",
    "FileImageVerificationCache",
    "IMAGE_SCAN_CACHE_CONTRACT",
    "IMAGE_SCAN_CACHE_SCHEMA_VERSION",
    "ImageScanCacheLookup",
    "ImageVerificationCacheLookup",
]
