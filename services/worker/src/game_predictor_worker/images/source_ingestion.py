"""Resumable ingestion of selected image folders into managed originals."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

from game_predictor_api.domain.jobs import Job

from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError

from .discovery import ImageDiscoveryError, SourceManifest, discover_images
from .image_file import ImageFileError, sha256_file

SOURCE_INGESTION_CONTRACT = "image-source-ingestion-v1"
COPY_CHECKPOINT_BATCH_SIZE = 25
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ManagedOriginal:
    checksum_sha256: str
    source_relative_path: str
    managed_relative_path: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ManagedSourceManifest:
    source_directory: Path
    originals: tuple[ManagedOriginal, ...]
    content: bytes
    relative_path: str
    checksum_sha256: str


class ManagedOriginalStore:
    """Own immutable manifests and content-addressed original JPEG blobs."""

    def __init__(self, artifact_root: Path) -> None:
        self._artifact_root = artifact_root.resolve()
        self._data_root = self._artifact_root / "data"
        self._originals_root = self._data_root / "originals"

    def load_or_create_manifest(
        self,
        job: Job,
        *,
        source_directory: Path,
    ) -> ManagedSourceManifest:
        relative_path = f"data/originals/manifests/{job.id}.json"
        destination = self._safe_path(relative_path)
        if destination.exists():
            return self._load_manifest(destination, relative_path, job)
        try:
            discovered = discover_images(source_directory)
        except ImageDiscoveryError as error:
            raise JobHandlerError(error.code, str(error)) from error
        if discovered.issues:
            first = discovered.issues[0]
            raise JobHandlerError(
                "IMAGE_DISCOVERY_REQUIRES_REVIEW",
                "Image discovery rejected "
                f"{len(discovered.issues)} source file(s); "
                f"first issue: {first.code}.",
            )
        if not discovered.images:
            raise JobHandlerError(
                "IMAGE_BATCH_EMPTY",
                "The image directory contains no supported source images.",
            )
        content = _manifest_bytes(job, source_directory, discovered)
        self._write_immutable(destination, content)
        return self._load_manifest(destination, relative_path, job)

    def ensure_original(
        self,
        manifest: ManagedSourceManifest,
        original: ManagedOriginal,
    ) -> bool:
        destination = self._safe_path(original.managed_relative_path)
        if destination.exists():
            self._verify_existing(destination, original)
            return False
        source = _safe_source_path(
            manifest.source_directory,
            original.source_relative_path,
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=".tmp-original-",
        )
        temporary = Path(temporary_name)
        digest = hashlib.sha256()
        size = 0
        try:
            with source.open("rb") as source_file, os.fdopen(descriptor, "wb") as target:
                for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
                    digest.update(chunk)
                    size += len(chunk)
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
            if digest.hexdigest() != original.checksum_sha256 or size != original.size_bytes:
                raise JobHandlerError(
                    "IMAGE_SOURCE_CHANGED",
                    "A source image changed after folder selection.",
                )
            try:
                os.link(temporary, destination)
            except FileExistsError:
                self._verify_existing(destination, original)
                return False
            return True
        except OSError as error:
            raise JobHandlerError(
                "IMAGE_ORIGINAL_COPY_FAILED",
                "A source image could not be copied into managed storage.",
            ) from error
        finally:
            temporary.unlink(missing_ok=True)

    def _load_manifest(
        self,
        path: Path,
        relative_path: str,
        job: Job,
    ) -> ManagedSourceManifest:
        if path.is_symlink() or not path.is_file():
            raise JobHandlerError(
                "IMAGE_SOURCE_MANIFEST_INVALID",
                "The managed source manifest path is invalid.",
            )
        content = path.read_bytes()
        try:
            value = json.loads(content)
        except json.JSONDecodeError as error:
            raise JobHandlerError(
                "IMAGE_SOURCE_MANIFEST_INVALID",
                "The managed source manifest is not valid JSON.",
            ) from error
        if not isinstance(value, Mapping):
            raise JobHandlerError(
                "IMAGE_SOURCE_MANIFEST_INVALID",
                "The managed source manifest must be an object.",
            )
        if value.get("contractVersion") != SOURCE_INGESTION_CONTRACT or value.get("jobId") != str(
            job.id
        ):
            raise JobHandlerError(
                "IMAGE_SOURCE_MANIFEST_INVALID",
                "The managed source manifest has different provenance.",
            )
        source_value = value.get("sourceDirectory")
        items = value.get("originals")
        if not isinstance(source_value, str) or not isinstance(items, Sequence):
            raise JobHandlerError(
                "IMAGE_SOURCE_MANIFEST_INVALID",
                "The managed source manifest is incomplete.",
            )
        originals = tuple(_parse_original(item) for item in items)
        if not originals:
            raise JobHandlerError(
                "IMAGE_SOURCE_MANIFEST_INVALID",
                "The managed source manifest has no originals.",
            )
        return ManagedSourceManifest(
            source_directory=Path(source_value),
            originals=originals,
            content=content,
            relative_path=relative_path,
            checksum_sha256=hashlib.sha256(content).hexdigest(),
        )

    def _verify_existing(self, path: Path, original: ManagedOriginal) -> None:
        if path.is_symlink() or not path.is_file():
            raise JobHandlerError(
                "IMAGE_ORIGINAL_STORAGE_INVALID",
                "A managed original path is invalid.",
            )
        try:
            size = path.stat().st_size
            checksum = sha256_file(path)
        except (OSError, ImageFileError) as error:
            raise JobHandlerError(
                "IMAGE_ORIGINAL_STORAGE_INVALID",
                "A managed original cannot be verified.",
            ) from error
        if size != original.size_bytes or checksum != original.checksum_sha256:
            raise JobHandlerError(
                "IMAGE_ORIGINAL_STORAGE_COLLISION",
                "A managed original has unexpected content.",
            )

    def _write_immutable(self, destination: Path, content: bytes) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=".tmp-manifest-",
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as target:
                target.write(content)
                target.flush()
                os.fsync(target.fileno())
            try:
                os.link(temporary, destination)
            except FileExistsError as error:
                if destination.read_bytes() != content:
                    raise JobHandlerError(
                        "IMAGE_SOURCE_MANIFEST_COLLISION",
                        "An existing managed source manifest has different content.",
                    ) from error
        finally:
            temporary.unlink(missing_ok=True)

    def _safe_path(self, relative_path: str) -> Path:
        relative = PurePosixPath(relative_path)
        if (
            relative.is_absolute()
            or any(part in {"", ".", ".."} for part in relative.parts)
            or not relative.parts
            or relative.parts[0] != "data"
        ):
            raise JobHandlerError(
                "IMAGE_ORIGINAL_STORAGE_INVALID",
                "Managed image storage requires a safe relative path.",
            )
        destination = self._artifact_root / Path(*relative.parts)
        if not destination.resolve().is_relative_to(self._data_root):
            raise JobHandlerError(
                "IMAGE_ORIGINAL_STORAGE_INVALID",
                "Managed image storage path escapes the data root.",
            )
        return destination


class ImageSourceIngestionHandler:
    def __init__(self, store: ManagedOriginalStore) -> None:
        self._store = store

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        self.ingest(context, job)

    def ingest(
        self,
        context: JobExecutionContext,
        job: Job,
    ) -> ManagedSourceManifest:
        """Copy managed originals and return their immutable manifest to the pipeline."""

        payload = job.input_payload
        if payload.get("import_kind") != "image_directory":
            raise JobHandlerError(
                "IMAGE_IMPORT_PAYLOAD_INVALID",
                "Image source ingestion requires an image_directory import job.",
            )
        source_value = payload.get("source_directory")
        fingerprint = payload.get("pipeline_fingerprint")
        if (
            not isinstance(source_value, str)
            or not source_value
            or not isinstance(fingerprint, str)
            or not SHA256_PATTERN.fullmatch(fingerprint)
        ):
            raise JobHandlerError(
                "IMAGE_IMPORT_PAYLOAD_INVALID",
                "Image source ingestion payload is incomplete.",
            )
        source = Path(source_value)
        manifest = self._store.load_or_create_manifest(
            job,
            source_directory=source,
        )
        total = len(manifest.originals)
        copied = 0
        for index, original in enumerate(manifest.originals, start=1):
            self._store.ensure_original(manifest, original)
            copied = index
            if index % COPY_CHECKPOINT_BATCH_SIZE == 0 or index == total:
                context.checkpoint(
                    checkpoint_payload={
                        "schema_version": 1,
                        "contractVersion": SOURCE_INGESTION_CONTRACT,
                        "manifestChecksumSha256": manifest.checksum_sha256,
                        "manifestRelativePath": manifest.relative_path,
                        "managedOriginalCount": copied,
                        "pipelineFingerprint": fingerprint,
                    },
                    stage="image_originals_copied",
                    current=copied,
                    total=total,
                    success_count=copied,
                    failure_count=0,
                    review_count=0,
                )
        return manifest


def _manifest_bytes(job: Job, source: Path, manifest: SourceManifest) -> bytes:
    originals = []
    for image in manifest.images:
        source_file = image.files[0]
        originals.append(
            {
                "checksumSha256": image.checksum_sha256,
                "managedRelativePath": (
                    f"data/originals/{image.checksum_sha256[:2]}/{image.checksum_sha256}.jpg"
                ),
                "sizeBytes": source_file.size_bytes,
                "sourceRelativePath": source_file.relative_path,
                "sourceRelativePaths": [item.relative_path for item in image.files],
            }
        )
    payload = {
        "contractVersion": SOURCE_INGESTION_CONTRACT,
        "discovery": manifest.to_dict(),
        "gameId": None if job.game_id is None else str(job.game_id),
        "jobId": str(job.id),
        "originals": originals,
        "schemaVersion": 1,
        "sourceDirectory": str(source.resolve(strict=True)),
    }
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _parse_original(value: object) -> ManagedOriginal:
    if not isinstance(value, Mapping):
        _invalid_manifest()
    item = cast(Mapping[str, object], value)
    checksum = item.get("checksumSha256")
    source_path = item.get("sourceRelativePath")
    managed_path = item.get("managedRelativePath")
    size = item.get("sizeBytes")
    if (
        not isinstance(checksum, str)
        or not SHA256_PATTERN.fullmatch(checksum)
        or not isinstance(source_path, str)
        or not source_path
        or not isinstance(managed_path, str)
        or managed_path != f"data/originals/{checksum[:2]}/{checksum}.jpg"
        or not isinstance(size, int)
        or isinstance(size, bool)
        or size < 1
    ):
        _invalid_manifest()
    return ManagedOriginal(
        cast(str, checksum),
        cast(str, source_path),
        cast(str, managed_path),
        cast(int, size),
    )


def _safe_source_path(root: Path, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise JobHandlerError(
            "IMAGE_SOURCE_MANIFEST_INVALID",
            "A source image path is unsafe.",
        )
    try:
        resolved_root = root.resolve(strict=True)
        path = (resolved_root / Path(*relative.parts)).resolve(strict=True)
    except OSError as error:
        raise JobHandlerError(
            "IMAGE_SOURCE_UNAVAILABLE",
            "A source image is no longer available for ingestion.",
        ) from error
    if not path.is_relative_to(resolved_root) or not path.is_file() or path.is_symlink():
        raise JobHandlerError(
            "IMAGE_SOURCE_PATH_ESCAPE",
            "A source image path escapes the selected folder.",
        )
    return path


def _invalid_manifest() -> None:
    raise JobHandlerError(
        "IMAGE_SOURCE_MANIFEST_INVALID",
        "The managed source manifest contains an invalid original entry.",
    )


__all__ = [
    "ImageSourceIngestionHandler",
    "ManagedOriginal",
    "ManagedOriginalStore",
    "ManagedSourceManifest",
    "SOURCE_INGESTION_CONTRACT",
]
