"""Preview and durable execution contracts for managed storage GC."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.domain.storage_retention import (
    StorageArtifactClass,
    StorageArtifactObservation,
    StorageGcManifestEntry,
    StorageRetentionDecision,
    StorageRetentionPolicy,
    StorageRootKind,
    canonical_gc_manifest_bytes,
    evaluate_storage_retention,
    gc_manifest_checksum_sha256,
    gc_preview_token,
    manifest_entry_from_decision,
)

GC_EXPORT_SCHEMA = 1


@dataclass(frozen=True, slots=True)
class BrowserStagingGcSource:
    upload_id: UUID
    relative_path: str
    finalized_at: datetime
    last_dependency_at: datetime | None
    linked_import_exists: bool
    managed_originals_verified: bool
    dependency_job_statuses: tuple[str, ...]
    managed_manifest_relative_path: str | None
    managed_manifest_checksum_sha256: str | None


@dataclass(frozen=True, slots=True)
class StorageGcPreview:
    id: UUID
    status: str
    mode: str
    policy_version: str
    retention_hours: int
    manifest_relative_path: str
    manifest_checksum_sha256: str
    preview_token: str
    candidate_count: int
    candidate_bytes: int
    protected_count: int
    protected_bytes: int
    predicted_free_bytes: int
    category_counts: Mapping[str, Mapping[str, int]]
    protection_reason_counts: Mapping[str, Mapping[str, int]]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class StorageGcRun:
    id: UUID
    job_id: UUID | None
    status: str
    mode: str
    candidate_count: int
    candidate_bytes: int
    protected_count: int
    protected_bytes: int
    deleted_count: int
    deleted_bytes: int
    conflict_count: int
    failed_count: int
    checkpoint_index: int
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class StorageGcRepository(Protocol):
    def active_automatic_run(self) -> StorageGcRun | None: ...
    def normalization_dependency_statuses(
        self, execution_keys: Sequence[str]
    ) -> Mapping[str, tuple[str, ...]]: ...

    def browser_staging_sources(self) -> Sequence[BrowserStagingGcSource]: ...

    def create_preview(
        self,
        *,
        preview_id: UUID,
        mode: str,
        policy: StorageRetentionPolicy,
        manifest_relative_path: str,
        manifest_checksum_sha256: str,
        preview_token: str,
        candidate_count: int,
        candidate_bytes: int,
        protected_count: int,
        protected_bytes: int,
        inventory_before: Mapping[str, object],
        created_at: datetime,
    ) -> StorageGcPreview: ...

    def start_run(
        self,
        *,
        preview_id: UUID,
        expected_manifest_checksum_sha256: str,
        expected_preview_token: str,
        mode: str,
    ) -> StorageGcRun: ...

    def get_run(self, run_id: UUID) -> StorageGcRun: ...


@dataclass(frozen=True, slots=True)
class StorageGcScan:
    entries: tuple[StorageGcManifestEntry, ...]
    protected: tuple[StorageRetentionDecision, ...]
    free_bytes: int


class StorageGcArtifactStore:
    """Scan only approved derived namespaces and persist immutable manifests."""

    def __init__(self, artifact_root: Path, import_root: Path) -> None:
        self._artifact_root = artifact_root.resolve()
        self._import_root = import_root.resolve()

    def scan(
        self,
        repository: StorageGcRepository,
        *,
        policy: StorageRetentionPolicy,
        now: datetime,
    ) -> StorageGcScan:
        observations = list(self._normalization_observations(repository))
        observations.extend(self._temporary_observations(repository))
        observations.extend(self._browser_staging_observations(repository))
        decisions = tuple(
            evaluate_storage_retention(item, policy=policy, now=now) for item in observations
        )
        entries = tuple(manifest_entry_from_decision(item) for item in decisions if item.eligible)
        free_bytes = min(
            os.statvfs(root).f_bavail * os.statvfs(root).f_frsize
            if hasattr(os, "statvfs")
            else shutil.disk_usage(root).free
            for root in self._distinct_volume_roots()
        )
        return StorageGcScan(
            entries=entries,
            protected=tuple(item for item in decisions if not item.eligible),
            free_bytes=free_bytes,
        )

    def persist_manifest(
        self,
        entries: tuple[StorageGcManifestEntry, ...],
        *,
        policy: StorageRetentionPolicy,
        run_id: UUID,
    ) -> tuple[str, str, str]:
        content = canonical_gc_manifest_bytes(entries, policy=policy)
        checksum = gc_manifest_checksum_sha256(content)
        token = gc_preview_token(content, policy=policy)
        relative = f"data/exports/storage-gc/{run_id}/{checksum}/manifest.json"
        destination = self._artifact_path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.is_symlink() or destination.read_bytes() != content:
                raise JobConflictError(
                    "STORAGE_GC_SOURCE_CHANGED",
                    "An existing GC manifest has different content.",
                )
            return relative, checksum, token
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=".tmp-storage-gc-",
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as target:
                target.write(content)
                target.flush()
                os.fsync(target.fileno())
            os.link(temporary, destination)
        except FileExistsError as error:
            if destination.read_bytes() != content:
                raise JobConflictError(
                    "STORAGE_GC_SOURCE_CHANGED",
                    "An existing GC manifest has different content.",
                ) from error
        finally:
            temporary.unlink(missing_ok=True)
        return relative, checksum, token

    def _normalization_observations(
        self, repository: StorageGcRepository
    ) -> Iterable[StorageArtifactObservation]:
        root = self._artifact_root / "data" / "working" / "image-normalization-v1"
        if not root.is_dir() or root.is_symlink():
            return ()
        paths = tuple(path for path in root.rglob("normalized.png") if not path.is_symlink())
        keys = tuple(path.parent.name for path in paths if len(path.parent.name) == 64)
        statuses = repository.normalization_dependency_statuses(keys)
        observations: list[StorageArtifactObservation] = []
        for path in paths:
            key = path.parent.name
            stat = path.stat(follow_symlinks=False)
            observations.append(
                StorageArtifactObservation(
                    relative_path=path.relative_to(self._artifact_root).as_posix(),
                    size_bytes=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, UTC),
                    artifact_class=StorageArtifactClass.NORMALIZATION_WORKING_BITMAP,
                    dependency_job_statuses=statuses.get(key, ()),
                    is_symlink=path.is_symlink(),
                    root_kind=StorageRootKind.ARTIFACT,
                    observation_checksum_sha256=_file_observation_checksum(path, stat),
                )
            )
        return observations

    def _temporary_observations(
        self, repository: StorageGcRepository
    ) -> Iterable[StorageArtifactObservation]:
        root = self._artifact_root / "data" / "working"
        if not root.is_dir() or root.is_symlink():
            return ()
        paths = tuple(
            path
            for path in root.rglob("*")
            if path.is_file()
            and not path.is_symlink()
            and (path.name.startswith(".tmp") or path.suffix.casefold() == ".part")
        )
        keys = tuple(filter(None, (_execution_key_from_path(path) for path in paths)))
        statuses = repository.normalization_dependency_statuses(keys)
        observations: list[StorageArtifactObservation] = []
        for path in paths:
            key = _execution_key_from_path(path)
            stat = path.stat(follow_symlinks=False)
            dependency_statuses = ("processing",) if key is None else statuses.get(key, ())
            observations.append(
                StorageArtifactObservation(
                    relative_path=path.relative_to(self._artifact_root).as_posix(),
                    size_bytes=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, UTC),
                    artifact_class=StorageArtifactClass.TEMPORARY_FILE,
                    dependency_job_statuses=dependency_statuses,
                    root_kind=StorageRootKind.ARTIFACT,
                    observation_checksum_sha256=_file_observation_checksum(path, stat),
                )
            )
        return observations

    def _browser_staging_observations(
        self, repository: StorageGcRepository
    ) -> Iterable[StorageArtifactObservation]:
        observations: list[StorageArtifactObservation] = []
        sources = repository.browser_staging_sources()
        tracked_paths = {source.relative_path for source in sources}
        for source in sources:
            path = self._import_path(source.relative_path)
            if not path.exists():
                continue
            size_bytes, modified_at, fingerprint, is_symlink = _tree_observation(path)
            originals_verified = source.managed_originals_verified and self.verify_managed_manifest(
                source
            )
            observations.append(
                StorageArtifactObservation(
                    relative_path=source.relative_path,
                    size_bytes=size_bytes,
                    modified_at=max(modified_at, source.finalized_at),
                    artifact_class=StorageArtifactClass.BROWSER_STAGING,
                    dependency_job_statuses=source.dependency_job_statuses,
                    linked_import_exists=source.linked_import_exists,
                    managed_originals_verified=originals_verified,
                    last_dependency_at=source.last_dependency_at,
                    is_symlink=is_symlink,
                    root_kind=StorageRootKind.IMPORT,
                    observation_checksum_sha256=fingerprint,
                )
            )
        staging_root = self._import_root / "browser-selections"
        if staging_root.is_dir() and not staging_root.is_symlink():
            for path in sorted(staging_root.iterdir(), key=lambda item: item.name.casefold()):
                relative_path = path.relative_to(self._import_root).as_posix()
                if relative_path in tracked_paths:
                    continue
                size_bytes, modified_at, fingerprint, is_symlink = _tree_observation(path)
                observations.append(
                    StorageArtifactObservation(
                        relative_path=relative_path,
                        size_bytes=size_bytes,
                        modified_at=modified_at,
                        artifact_class=StorageArtifactClass.BROWSER_STAGING,
                        linked_import_exists=False,
                        managed_originals_verified=False,
                        is_symlink=is_symlink,
                        root_kind=StorageRootKind.IMPORT,
                        observation_checksum_sha256=fingerprint,
                    )
                )
        return observations

    def verify_managed_manifest(self, source: BrowserStagingGcSource) -> bool:
        relative = source.managed_manifest_relative_path
        expected = source.managed_manifest_checksum_sha256
        if relative is None or expected is None:
            return False
        try:
            manifest_path = self._artifact_path(relative)
            content = manifest_path.read_bytes()
            if hashlib.sha256(content).hexdigest() != expected:
                return False
            payload = __import__("json").loads(content)
            originals = payload.get("originals")
            if not isinstance(originals, list) or not originals:
                return False
            for item in originals:
                managed = self._artifact_path(str(item["managedRelativePath"]))
                if managed.is_symlink() or not managed.is_file():
                    return False
                if managed.stat().st_size != int(item["sizeBytes"]):
                    return False
                digest = hashlib.sha256()
                with managed.open("rb") as source_file:
                    for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != str(item["checksumSha256"]):
                    return False
        except (OSError, KeyError, TypeError, ValueError):
            return False
        return True

    def _artifact_path(self, relative_path: str) -> Path:
        return _safe_path(self._artifact_root, relative_path)

    def _import_path(self, relative_path: str) -> Path:
        return _safe_path(self._import_root, relative_path)

    def _distinct_volume_roots(self) -> tuple[Path, ...]:
        roots: dict[str, Path] = {}
        for root in (self._artifact_root, self._import_root):
            drive = root.drive.casefold() or str(root.anchor).casefold()
            roots.setdefault(drive, root)
        return tuple(roots.values())


class StorageGcService:
    def __init__(
        self,
        repository: StorageGcRepository,
        artifact_store: StorageGcArtifactStore,
        *,
        policy: StorageRetentionPolicy | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._artifact_store = artifact_store
        self._policy = policy or StorageRetentionPolicy()
        self._clock = clock or (lambda: datetime.now(UTC))

    def preview(self, *, mode: str = "manual") -> StorageGcPreview:
        now = self._clock()
        scan = self._artifact_store.scan(self._repository, policy=self._policy, now=now)
        identity = (
            canonical_gc_manifest_bytes(scan.entries, policy=self._policy)
            + now.isoformat().encode()
        )
        run_id = UUID(bytes=hashlib.sha256(identity).digest()[:16])
        relative, checksum, token = self._artifact_store.persist_manifest(
            scan.entries,
            policy=self._policy,
            run_id=run_id,
        )
        protected_bytes = sum(item.observation.size_bytes for item in scan.protected)
        category_counts = _entry_counts(scan.entries)
        protection_reason_counts = _protection_counts(scan.protected)
        return self._repository.create_preview(
            preview_id=run_id,
            mode=mode,
            policy=self._policy,
            manifest_relative_path=relative,
            manifest_checksum_sha256=checksum,
            preview_token=token,
            candidate_count=len(scan.entries),
            candidate_bytes=sum(item.size_bytes for item in scan.entries),
            protected_count=len(scan.protected),
            protected_bytes=protected_bytes,
            inventory_before={
                "freeBytes": scan.free_bytes,
                "categoryCounts": category_counts,
                "protectionReasonCounts": protection_reason_counts,
            },
            created_at=now,
        )

    def start(
        self,
        *,
        preview_id: UUID,
        manifest_checksum_sha256: str,
        preview_token: str,
        confirmed: bool,
    ) -> StorageGcRun:
        if not confirmed:
            raise JobConflictError(
                "STORAGE_GC_CONFIRMATION_REQUIRED",
                "Starting storage cleanup requires explicit confirmation.",
            )
        return self._repository.start_run(
            preview_id=preview_id,
            expected_manifest_checksum_sha256=manifest_checksum_sha256,
            expected_preview_token=preview_token,
            mode="manual",
        )

    def get_run(self, run_id: UUID) -> StorageGcRun:
        return self._repository.get_run(run_id)

    def ensure_automatic_run(self) -> StorageGcRun | None:
        """Create at most one policy-only automatic cleanup run."""

        active = self._repository.active_automatic_run()
        if active is not None:
            return active
        preview = self.preview(mode="automatic")
        if preview.candidate_count == 0:
            return None
        return self._repository.start_run(
            preview_id=preview.id,
            expected_manifest_checksum_sha256=preview.manifest_checksum_sha256,
            expected_preview_token=preview.preview_token,
            mode="automatic",
        )


def _safe_path(root: Path, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or "\\" in relative_path
    ):
        raise JobConflictError("STORAGE_GC_PATH_UNSAFE", "The GC path is unsafe.")
    target = root.joinpath(*relative.parts)
    if not target.resolve().is_relative_to(root):
        raise JobConflictError("STORAGE_GC_PATH_UNSAFE", "The GC path escapes its root.")
    return target


def _file_observation_checksum(path: Path, stat: os.stat_result) -> str:
    payload = f"{path.name}\0{stat.st_size}\0{stat.st_mtime_ns}".encode()
    return hashlib.sha256(payload).hexdigest()


def _execution_key_from_path(path: Path) -> str | None:
    for part in reversed(path.parts):
        if len(part) == 64 and all(character in "0123456789abcdef" for character in part):
            return part
    return None


def _tree_observation(path: Path) -> tuple[int, datetime, str, bool]:
    if path.is_symlink() or not path.is_dir():
        stat = path.lstat()
        return 0, datetime.fromtimestamp(stat.st_mtime, UTC), "0" * 64, True
    size = 0
    latest_ns = path.stat().st_mtime_ns
    digest = hashlib.sha256()
    for child in sorted(path.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if child.is_symlink():
            return size, datetime.fromtimestamp(latest_ns / 1_000_000_000, UTC), "0" * 64, True
        if not child.is_file():
            continue
        stat = child.stat(follow_symlinks=False)
        relative = child.relative_to(path).as_posix()
        digest.update(f"{relative}\0{stat.st_size}\0{stat.st_mtime_ns}\n".encode())
        size += stat.st_size
        latest_ns = max(latest_ns, stat.st_mtime_ns)
    return (
        size,
        datetime.fromtimestamp(latest_ns / 1_000_000_000, UTC),
        digest.hexdigest(),
        False,
    )


def _entry_counts(
    entries: Sequence[StorageGcManifestEntry],
) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for entry in entries:
        counter = result.setdefault(entry.artifact_class.value, {"count": 0, "bytes": 0})
        counter["count"] += 1
        counter["bytes"] += entry.size_bytes
    return result


def _protection_counts(
    decisions: Sequence[StorageRetentionDecision],
) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for decision in decisions:
        for reason in decision.protection_reasons:
            counter = result.setdefault(reason.value, {"count": 0, "bytes": 0})
            counter["count"] += 1
            counter["bytes"] += decision.observation.size_bytes
    return result


__all__ = [
    "BrowserStagingGcSource",
    "StorageGcArtifactStore",
    "StorageGcPreview",
    "StorageGcRepository",
    "StorageGcRun",
    "StorageGcService",
]
