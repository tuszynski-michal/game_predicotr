"""Managed image storage inventory and immutable diagnostic exports."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Protocol, cast
from uuid import UUID

from game_predictor_api.application.storage_gc import (
    StorageGcPreview,
    StorageGcRun,
    StorageGcService,
)
from game_predictor_api.domain.jobs import (
    Job,
    JobConflictError,
    JobNotFoundError,
    JobType,
    create_job,
)

DIAGNOSTIC_EXPORT_SCHEMA = "image-job-diagnostics-v1"
DIAGNOSTIC_ERROR_LIMIT = 10_000
MANAGED_STORAGE_NAMESPACES = (
    "staging",
    "originals",
    "working",
    "crops",
    "training",
    "models",
    "exports",
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_RETENTION_POLICIES = {
    "staging": ("verified-handoff-derived", False),
    "originals": ("preserve", True),
    "working": ("versioned-derived", False),
    "crops": ("versioned-derived", True),
    "training": ("versioned-derived", True),
    "models": ("preserve", True),
    "exports": ("versioned", True),
}


@dataclass(frozen=True, slots=True)
class ImageStorageNamespace:
    name: str
    retention_policy: str
    protected: bool
    exists: bool
    file_count: int
    size_bytes: int
    ignored_symlink_count: int


@dataclass(frozen=True, slots=True)
class ImageStorageInventory:
    root_name: str
    automatic_deletion: bool
    total_file_count: int
    total_size_bytes: int
    namespaces: Sequence[ImageStorageNamespace]
    measured_at: datetime
    volumes: Sequence[ImageStorageVolume]
    database_size_bytes: int | None
    wal_size_bytes: int | None


@dataclass(frozen=True, slots=True)
class ImageStorageVolume:
    key: str
    roots: tuple[str, ...]
    total_bytes: int
    free_bytes: int


@dataclass(frozen=True, slots=True)
class ImageDiagnosticFailure:
    file_execution_key: str
    order_index: int
    source_relative_path: str
    failed_stage: str
    error_code: str
    error_message: str
    retry_count: int
    last_failed_at: datetime


@dataclass(frozen=True, slots=True)
class ImageDiagnosticSnapshot:
    job_id: UUID
    status: str
    pipeline_fingerprint: str
    source_updated_at: datetime
    total: int
    current: int
    succeeded: int
    failed: int
    review: int
    waiting: int
    failures: Sequence[ImageDiagnosticFailure]
    error_limit: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class ImageDiagnosticExport:
    job_id: UUID
    checksum_sha256: str
    relative_path: str
    size_bytes: int
    source_updated_at: datetime
    error_count: int
    exported_error_count: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class ImageDiagnosticExportCreation:
    created: bool
    export: ImageDiagnosticExport


class ImageDiagnosticRepository(Protocol):
    def diagnostic_snapshot(
        self,
        job_id: UUID,
        *,
        error_limit: int,
    ) -> ImageDiagnosticSnapshot: ...

    def database_storage_sizes(self) -> tuple[int | None, int | None]: ...

    def active_storage_inventory_job(self) -> Job | None: ...

    def add_job(self, job: Job) -> Job: ...

    def get_or_create_storage_inventory_job(self, *, requested_at: datetime) -> Job: ...

    def latest_storage_inventory(self) -> ImageStorageInventory | None: ...


class ImageArtifactStore:
    """Filesystem boundary restricted to ``<artifact-root>/data``."""

    def __init__(self, artifact_root: Path, import_root: Path | None = None) -> None:
        self._artifact_root = artifact_root.resolve()
        self._managed_root = self._artifact_root / "data"
        self._import_root = (import_root or artifact_root).resolve()

    def inventory(
        self,
        *,
        database_size_bytes: int | None = None,
        wal_size_bytes: int | None = None,
    ) -> ImageStorageInventory:
        namespaces = tuple(self._namespace_inventory(name) for name in MANAGED_STORAGE_NAMESPACES)
        return ImageStorageInventory(
            root_name="data",
            automatic_deletion=False,
            total_file_count=sum(item.file_count for item in namespaces),
            total_size_bytes=sum(item.size_bytes for item in namespaces),
            namespaces=namespaces,
            measured_at=datetime.now().astimezone(),
            volumes=self._volumes(),
            database_size_bytes=database_size_bytes,
            wal_size_bytes=wal_size_bytes,
        )

    def inventory_metadata_only(
        self,
        *,
        database_size_bytes: int | None,
        wal_size_bytes: int | None,
    ) -> ImageStorageInventory:
        return ImageStorageInventory(
            root_name="data",
            automatic_deletion=False,
            total_file_count=0,
            total_size_bytes=0,
            namespaces=(),
            measured_at=datetime.now().astimezone(),
            volumes=self._volumes(),
            database_size_bytes=database_size_bytes,
            wal_size_bytes=wal_size_bytes,
        )

    def _volumes(self) -> tuple[ImageStorageVolume, ...]:
        grouped: dict[str, tuple[Path, list[str]]] = {}
        for name, root in (("artifacts", self._artifact_root), ("imports", self._import_root)):
            key = (root.drive or root.anchor).casefold()
            if key not in grouped:
                grouped[key] = (root, [])
            grouped[key][1].append(name)
        result = []
        for key, (root, names) in sorted(grouped.items()):
            usage = shutil.disk_usage(root)
            result.append(ImageStorageVolume(key, tuple(names), usage.total, usage.free))
        return tuple(result)

    def create_diagnostic_export(
        self,
        snapshot: ImageDiagnosticSnapshot,
    ) -> ImageDiagnosticExportCreation:
        content = _diagnostic_bytes(snapshot)
        checksum = hashlib.sha256(content).hexdigest()
        relative_path = _diagnostic_relative_path(snapshot.job_id, checksum)
        destination = self._safe_managed_path(relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        created = False
        if destination.exists():
            if destination.is_symlink() or destination.read_bytes() != content:
                raise JobConflictError(
                    "IMAGE_DIAGNOSTIC_EXPORT_COLLISION",
                    "An existing diagnostic export has different content.",
                )
        else:
            descriptor, temporary_name = tempfile.mkstemp(
                dir=destination.parent,
                prefix=".tmp-",
            )
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "wb") as file:
                    file.write(content)
                    file.flush()
                    os.fsync(file.fileno())
                os.link(temporary, destination)
                created = True
            except FileExistsError as error:
                if not destination.exists() or destination.read_bytes() != content:
                    raise JobConflictError(
                        "IMAGE_DIAGNOSTIC_EXPORT_COLLISION",
                        "An existing diagnostic export has different content.",
                    ) from error
            finally:
                temporary.unlink(missing_ok=True)
        return ImageDiagnosticExportCreation(
            created=created,
            export=_export_from_bytes(
                snapshot.job_id,
                relative_path,
                content,
                expected_checksum=checksum,
            ),
        )

    def list_diagnostic_exports(
        self,
        job_id: UUID,
    ) -> tuple[ImageDiagnosticExport, ...]:
        root = self._safe_managed_path(f"data/exports/image-jobs/{job_id}")
        if not root.exists():
            return ()
        if root.is_symlink() or not root.is_dir():
            raise JobConflictError(
                "IMAGE_DIAGNOSTIC_EXPORT_STORAGE_INVALID",
                "The diagnostic export directory is invalid.",
            )
        exports: list[ImageDiagnosticExport] = []
        for child in root.iterdir():
            if (
                child.is_symlink()
                or not child.is_dir()
                or not _SHA256_PATTERN.fullmatch(child.name)
            ):
                continue
            relative_path = _diagnostic_relative_path(job_id, child.name)
            path = self._safe_managed_path(relative_path)
            if not path.is_file() or path.is_symlink():
                raise JobConflictError(
                    "IMAGE_DIAGNOSTIC_EXPORT_CORRUPT",
                    "A diagnostic export is incomplete or unreadable.",
                )
            exports.append(
                _export_from_bytes(
                    job_id,
                    relative_path,
                    path.read_bytes(),
                    expected_checksum=child.name,
                )
            )
        return tuple(
            sorted(
                exports,
                key=lambda item: (item.source_updated_at, item.checksum_sha256),
                reverse=True,
            )
        )

    def resolve_diagnostic_export(
        self,
        job_id: UUID,
        checksum_sha256: str,
    ) -> tuple[Path, ImageDiagnosticExport]:
        if not _SHA256_PATTERN.fullmatch(checksum_sha256):
            raise JobNotFoundError(
                "IMAGE_DIAGNOSTIC_EXPORT_NOT_FOUND",
                "The diagnostic export does not exist.",
            )
        relative_path = _diagnostic_relative_path(job_id, checksum_sha256)
        path = self._safe_managed_path(relative_path)
        if not path.is_file() or path.is_symlink():
            raise JobNotFoundError(
                "IMAGE_DIAGNOSTIC_EXPORT_NOT_FOUND",
                "The diagnostic export does not exist.",
            )
        content = path.read_bytes()
        export = _export_from_bytes(
            job_id,
            relative_path,
            content,
            expected_checksum=checksum_sha256,
        )
        return path, export

    def _namespace_inventory(self, name: str) -> ImageStorageNamespace:
        path = (
            self._import_root / "browser-selections"
            if name == "staging"
            else self._managed_root / name
        )
        policy, protected = _RETENTION_POLICIES[name]
        if not path.exists():
            return ImageStorageNamespace(
                name=name,
                retention_policy=policy,
                protected=protected,
                exists=False,
                file_count=0,
                size_bytes=0,
                ignored_symlink_count=0,
            )
        if path.is_symlink() or not path.is_dir():
            return ImageStorageNamespace(
                name=name,
                retention_policy=policy,
                protected=protected,
                exists=False,
                file_count=0,
                size_bytes=0,
                ignored_symlink_count=1,
            )
        file_count, size_bytes, ignored_symlinks = _scan_tree(path)
        return ImageStorageNamespace(
            name=name,
            retention_policy=policy,
            protected=protected,
            exists=True,
            file_count=file_count,
            size_bytes=size_bytes,
            ignored_symlink_count=ignored_symlinks,
        )

    def _safe_managed_path(self, relative_path: str) -> Path:
        relative = _safe_relative_path(relative_path)
        destination = self._artifact_root / Path(*relative.parts)
        current = self._artifact_root
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise JobConflictError(
                    "IMAGE_STORAGE_PATH_UNSAFE",
                    "The managed storage path is invalid.",
                )
        if not destination.resolve().is_relative_to(self._managed_root):
            raise JobConflictError(
                "IMAGE_STORAGE_PATH_UNSAFE",
                "The managed storage path is invalid.",
            )
        return destination


class ImageStorageService:
    def __init__(
        self,
        repository: ImageDiagnosticRepository,
        artifact_store: ImageArtifactStore,
        storage_gc_service: StorageGcService | None = None,
    ) -> None:
        self._repository = repository
        self._artifact_store = artifact_store
        self._storage_gc_service = storage_gc_service

    def inventory(self) -> ImageStorageInventory:
        cached_reader = getattr(self._repository, "latest_storage_inventory", None)
        if cached_reader is None:
            return self._artifact_store.inventory()
        cached = cast(ImageStorageInventory | None, cached_reader())
        if cached is not None:
            return cached
        sizes = self._repository.database_storage_sizes()
        empty = self._artifact_store.inventory_metadata_only(
            database_size_bytes=sizes[0],
            wal_size_bytes=sizes[1],
        )
        return empty

    def refresh_inventory(self) -> Job:
        atomic_creator = getattr(
            self._repository,
            "get_or_create_storage_inventory_job",
            None,
        )
        now = datetime.now().astimezone()
        if atomic_creator is not None:
            return cast(Job, atomic_creator(requested_at=now))
        active = self._repository.active_storage_inventory_job()
        if active is not None:
            return active
        return self._repository.add_job(
            create_job(
                JobType.STORAGE_INVENTORY,
                game_id=None,
                input_payload={
                    "schema_version": 1,
                    "inventory_kind": "managed_image_storage",
                    "requested_at": now.isoformat(),
                },
                created_at=now,
            )
        )

    def create_gc_preview(self) -> StorageGcPreview:
        return self._require_gc().preview()

    def start_gc(
        self,
        *,
        preview_id: UUID,
        manifest_checksum_sha256: str,
        preview_token: str,
        confirmed: bool,
    ) -> StorageGcRun:
        return self._require_gc().start(
            preview_id=preview_id,
            manifest_checksum_sha256=manifest_checksum_sha256,
            preview_token=preview_token,
            confirmed=confirmed,
        )

    def get_gc_run(self, run_id: UUID) -> StorageGcRun:
        return self._require_gc().get_run(run_id)

    def _require_gc(self) -> StorageGcService:
        if self._storage_gc_service is None:
            raise JobConflictError(
                "STORAGE_GC_UNAVAILABLE", "Managed storage cleanup is not configured."
            )
        return self._storage_gc_service

    def create_diagnostic_export(
        self,
        job_id: UUID,
    ) -> ImageDiagnosticExportCreation:
        snapshot = self._repository.diagnostic_snapshot(
            job_id,
            error_limit=DIAGNOSTIC_ERROR_LIMIT,
        )
        return self._artifact_store.create_diagnostic_export(snapshot)

    def list_diagnostic_exports(
        self,
        job_id: UUID,
    ) -> tuple[ImageDiagnosticExport, ...]:
        self._repository.diagnostic_snapshot(job_id, error_limit=1)
        return self._artifact_store.list_diagnostic_exports(job_id)

    def resolve_diagnostic_export(
        self,
        job_id: UUID,
        checksum_sha256: str,
    ) -> tuple[Path, ImageDiagnosticExport]:
        self._repository.diagnostic_snapshot(job_id, error_limit=1)
        return self._artifact_store.resolve_diagnostic_export(job_id, checksum_sha256)


def _scan_tree(root: Path) -> tuple[int, int, int]:
    file_count = 0
    size_bytes = 0
    ignored_symlinks = 0
    pending = [root]
    while pending:
        current = pending.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                if entry.is_symlink():
                    ignored_symlinks += 1
                elif entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    file_count += 1
                    size_bytes += entry.stat(follow_symlinks=False).st_size
    return file_count, size_bytes, ignored_symlinks


def _safe_relative_path(value: str) -> PurePosixPath:
    candidate = value.strip()
    path = PurePosixPath(candidate)
    if (
        not candidate
        or path.is_absolute()
        or "\\" in candidate
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise JobConflictError(
            "IMAGE_STORAGE_PATH_UNSAFE",
            "The managed storage path is invalid.",
        )
    return path


def _diagnostic_relative_path(job_id: UUID, checksum: str) -> str:
    return f"data/exports/image-jobs/{job_id}/{checksum}/diagnostics.json"


def _diagnostic_bytes(snapshot: ImageDiagnosticSnapshot) -> bytes:
    failures = [
        {
            "error": {
                "code": item.error_code,
                "message": item.error_message,
            },
            "failedStage": item.failed_stage,
            "fileExecutionKey": item.file_execution_key,
            "lastFailedAt": item.last_failed_at.isoformat(),
            "orderIndex": item.order_index,
            "retryCount": item.retry_count,
            "sourceRelativePath": _safe_relative_path(item.source_relative_path).as_posix(),
        }
        for item in snapshot.failures
    ]
    payload = {
        "aggregates": {
            "current": snapshot.current,
            "failed": snapshot.failed,
            "review": snapshot.review,
            "succeeded": snapshot.succeeded,
            "total": snapshot.total,
            "waiting": snapshot.waiting,
        },
        "errorLimit": snapshot.error_limit,
        "errors": failures,
        "exportedErrorCount": len(failures),
        "jobId": str(snapshot.job_id),
        "jobStatus": snapshot.status,
        "pipelineFingerprint": snapshot.pipeline_fingerprint,
        "schemaVersion": DIAGNOSTIC_EXPORT_SCHEMA,
        "sourceUpdatedAt": snapshot.source_updated_at.isoformat(),
        "truncated": snapshot.truncated,
    }
    return (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _export_from_bytes(
    job_id: UUID,
    relative_path: str,
    content: bytes,
    *,
    expected_checksum: str,
) -> ImageDiagnosticExport:
    actual_checksum = hashlib.sha256(content).hexdigest()
    if actual_checksum != expected_checksum:
        raise JobConflictError(
            "IMAGE_DIAGNOSTIC_EXPORT_CHECKSUM_MISMATCH",
            "The diagnostic export checksum does not match its version.",
        )
    try:
        payload = json.loads(content)
        source_updated_at = datetime.fromisoformat(payload["sourceUpdatedAt"])
        if (
            payload["schemaVersion"] != DIAGNOSTIC_EXPORT_SCHEMA
            or payload["jobId"] != str(job_id)
            or not isinstance(payload["errors"], list)
            or not isinstance(payload["aggregates"]["failed"], int)
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise JobConflictError(
            "IMAGE_DIAGNOSTIC_EXPORT_CORRUPT",
            "The diagnostic export is not valid canonical JSON.",
        ) from error
    canonical = (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")
    if canonical != content:
        raise JobConflictError(
            "IMAGE_DIAGNOSTIC_EXPORT_CORRUPT",
            "The diagnostic export is not canonical.",
        )
    return ImageDiagnosticExport(
        job_id=job_id,
        checksum_sha256=actual_checksum,
        relative_path=relative_path,
        size_bytes=len(content),
        source_updated_at=source_updated_at,
        error_count=payload["aggregates"]["failed"],
        exported_error_count=len(payload["errors"]),
        truncated=payload["truncated"],
    )


__all__ = [
    "DIAGNOSTIC_ERROR_LIMIT",
    "DIAGNOSTIC_EXPORT_SCHEMA",
    "ImageArtifactStore",
    "ImageDiagnosticExport",
    "ImageDiagnosticExportCreation",
    "ImageDiagnosticFailure",
    "ImageDiagnosticRepository",
    "ImageDiagnosticSnapshot",
    "ImageStorageInventory",
    "ImageStorageNamespace",
    "ImageStorageService",
    "MANAGED_STORAGE_NAMESPACES",
]
