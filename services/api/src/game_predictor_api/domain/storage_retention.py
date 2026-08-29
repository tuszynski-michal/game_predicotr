"""Deterministic retention policy for managed image-storage artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import PurePosixPath

STORAGE_RETENTION_POLICY_VERSION = "storage-retention-v1"


class StorageArtifactClass(StrEnum):
    NORMALIZATION_WORKING_BITMAP = "normalization_working_bitmap"
    TEMPORARY_FILE = "temporary_file"
    BROWSER_STAGING = "browser_staging"
    PIPELINE_STAGE_RESULT = "pipeline_stage_result"
    PROTECTED_NAMESPACE = "protected_namespace"


class StorageRootKind(StrEnum):
    ARTIFACT = "artifact"
    IMPORT = "import"


class StorageProtectionReason(StrEnum):
    ACTIVE_JOB_DEPENDENCY = "active_job_dependency"
    RETENTION_NOT_ELAPSED = "retention_not_elapsed"
    PROTECTED_NAMESPACE = "protected_namespace"
    STAGING_IMPORT_MISSING = "staging_import_missing"
    MANAGED_ORIGINALS_INCOMPLETE = "managed_originals_incomplete"
    PATH_UNSAFE = "path_unsafe"
    SYMBOLIC_LINK = "symbolic_link"


class BrowserStagingRetentionState(StrEnum):
    READY = "ready"
    IN_USE = "in_use"
    INGESTED = "ingested"
    CLEANUP_ELIGIBLE = "cleanup_eligible"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class StorageRetentionPolicy:
    version: str = STORAGE_RETENTION_POLICY_VERSION
    retention: timedelta = timedelta(hours=24)
    warning_free_bytes: int = 80 * 1024**3
    automatic_gc_free_bytes: int = 60 * 1024**3
    target_free_bytes: int = 80 * 1024**3
    hard_reserve_bytes: int = 30 * 1024**3

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("Storage retention policy version must not be empty.")
        if self.retention <= timedelta(0):
            raise ValueError("Storage retention must be positive.")
        thresholds = (
            self.hard_reserve_bytes,
            self.automatic_gc_free_bytes,
            self.warning_free_bytes,
            self.target_free_bytes,
        )
        if any(value < 0 for value in thresholds):
            raise ValueError("Storage thresholds must not be negative.")
        if thresholds != tuple(sorted(thresholds)):
            raise ValueError("Storage thresholds must be monotonically increasing.")


@dataclass(frozen=True, slots=True)
class StorageArtifactObservation:
    relative_path: str
    size_bytes: int
    modified_at: datetime
    artifact_class: StorageArtifactClass
    dependency_job_statuses: tuple[str, ...] = ()
    linked_import_exists: bool = False
    managed_originals_verified: bool = False
    last_dependency_at: datetime | None = None
    is_symlink: bool = False
    root_kind: StorageRootKind = StorageRootKind.ARTIFACT
    observation_checksum_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.size_bytes < 0:
            raise ValueError("Storage artifact size must not be negative.")
        if self.modified_at.tzinfo is None:
            raise ValueError("Storage artifact modified_at must be timezone-aware.")
        if self.last_dependency_at is not None and self.last_dependency_at.tzinfo is None:
            raise ValueError("Storage artifact last_dependency_at must be timezone-aware.")
        if self.observation_checksum_sha256 is not None and (
            len(self.observation_checksum_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.observation_checksum_sha256
            )
        ):
            raise ValueError("Storage observation checksum must be lowercase SHA-256.")


@dataclass(frozen=True, slots=True)
class StorageRetentionDecision:
    observation: StorageArtifactObservation
    eligible: bool
    eligible_at: datetime | None
    protection_reasons: tuple[StorageProtectionReason, ...]


@dataclass(frozen=True, slots=True)
class StorageGcManifestEntry:
    relative_path: str
    size_bytes: int
    modified_at: datetime
    artifact_class: StorageArtifactClass
    eligibility_basis: str
    dependency_job_statuses: tuple[str, ...]
    root_kind: StorageRootKind = StorageRootKind.ARTIFACT
    observation_checksum_sha256: str | None = None


def is_safe_managed_relative_path(relative_path: str) -> bool:
    if (
        not relative_path
        or "\\" in relative_path
        or ":" in relative_path
        or "\x00" in relative_path
    ):
        return False
    path = PurePosixPath(relative_path)
    if path.is_absolute() or not path.parts:
        return False
    return all(part not in {"", ".", ".."} for part in path.parts)


def evaluate_storage_retention(
    observation: StorageArtifactObservation,
    *,
    policy: StorageRetentionPolicy,
    now: datetime,
) -> StorageRetentionDecision:
    """Classify one observed path without reading mutable external state."""

    if now.tzinfo is None:
        raise ValueError("Storage retention evaluation time must be timezone-aware.")
    reasons: list[StorageProtectionReason] = []
    if not is_safe_managed_relative_path(observation.relative_path):
        reasons.append(StorageProtectionReason.PATH_UNSAFE)
    if observation.is_symlink:
        reasons.append(StorageProtectionReason.SYMBOLIC_LINK)
    if observation.artifact_class is StorageArtifactClass.PROTECTED_NAMESPACE:
        reasons.append(StorageProtectionReason.PROTECTED_NAMESPACE)
    if any(status in {"created", "processing"} for status in observation.dependency_job_statuses):
        reasons.append(StorageProtectionReason.ACTIVE_JOB_DEPENDENCY)
    if observation.artifact_class is StorageArtifactClass.BROWSER_STAGING:
        if not observation.linked_import_exists:
            reasons.append(StorageProtectionReason.STAGING_IMPORT_MISSING)
        if not observation.managed_originals_verified:
            reasons.append(StorageProtectionReason.MANAGED_ORIGINALS_INCOMPLETE)

    retention_anchor = max(
        value
        for value in (observation.modified_at, observation.last_dependency_at)
        if value is not None
    )
    eligible_at = retention_anchor.astimezone(UTC) + policy.retention
    if now.astimezone(UTC) < eligible_at:
        reasons.append(StorageProtectionReason.RETENTION_NOT_ELAPSED)
    ordered_reasons = tuple(sorted(set(reasons), key=lambda item: item.value))
    return StorageRetentionDecision(
        observation=observation,
        eligible=not ordered_reasons,
        eligible_at=eligible_at if not ordered_reasons else None,
        protection_reasons=ordered_reasons,
    )


def manifest_entry_from_decision(
    decision: StorageRetentionDecision,
) -> StorageGcManifestEntry:
    if not decision.eligible or decision.eligible_at is None:
        raise ValueError("Only eligible artifacts may enter a GC candidate manifest.")
    observation = decision.observation
    return StorageGcManifestEntry(
        relative_path=observation.relative_path,
        size_bytes=observation.size_bytes,
        modified_at=observation.modified_at,
        artifact_class=observation.artifact_class,
        eligibility_basis=f"retention_elapsed_at:{decision.eligible_at.isoformat()}",
        dependency_job_statuses=tuple(sorted(observation.dependency_job_statuses)),
        root_kind=observation.root_kind,
        observation_checksum_sha256=observation.observation_checksum_sha256,
    )


def canonical_gc_manifest_bytes(
    entries: tuple[StorageGcManifestEntry, ...],
    *,
    policy: StorageRetentionPolicy,
) -> bytes:
    ordered = sorted(
        entries,
        key=lambda entry: (entry.artifact_class.value, entry.relative_path),
    )
    payload = {
        "schemaVersion": 1,
        "policy": {
            "version": policy.version,
            "retentionSeconds": int(policy.retention.total_seconds()),
            "warningFreeBytes": policy.warning_free_bytes,
            "automaticGcFreeBytes": policy.automatic_gc_free_bytes,
            "targetFreeBytes": policy.target_free_bytes,
            "hardReserveBytes": policy.hard_reserve_bytes,
        },
        "candidates": [
            {
                "relativePath": entry.relative_path,
                "sizeBytes": entry.size_bytes,
                "modifiedAt": entry.modified_at.astimezone(UTC).isoformat(),
                "artifactClass": entry.artifact_class.value,
                "eligibilityBasis": entry.eligibility_basis,
                "dependencyJobStatuses": list(entry.dependency_job_statuses),
                "rootKind": entry.root_kind.value,
                "observationChecksumSha256": entry.observation_checksum_sha256,
            }
            for entry in ordered
        ],
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def gc_manifest_checksum_sha256(manifest_bytes: bytes) -> str:
    return hashlib.sha256(manifest_bytes).hexdigest()


def gc_preview_token(
    manifest_bytes: bytes,
    *,
    policy: StorageRetentionPolicy,
) -> str:
    digest = hashlib.sha256()
    digest.update(b"storage-gc-preview-v1\0")
    digest.update(policy.version.encode("utf-8"))
    digest.update(b"\0")
    digest.update(manifest_bytes)
    return digest.hexdigest()
