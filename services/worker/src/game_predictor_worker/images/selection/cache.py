"""Reconstructable, checksum-addressed cache for cheap scan observations."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Lock
from time import perf_counter
from uuid import uuid4

from .contracts import (
    CheapImageAnalyzer,
    CheapImageObservation,
    ImageSelectionSource,
    SelectionContractError,
)

IMAGE_SCAN_CACHE_CONTRACT = "image-selection-scan-cache-v1"
IMAGE_SCAN_CACHE_SCHEMA_VERSION = 1
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


__all__ = [
    "CachedCheapImageAnalyzer",
    "FileImageScanObservationCache",
    "IMAGE_SCAN_CACHE_CONTRACT",
    "IMAGE_SCAN_CACHE_SCHEMA_VERSION",
    "ImageScanCacheLookup",
]
