"""Resumable ingestion of selected image folders into managed originals."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast
from uuid import UUID

from game_predictor_api.domain.image_geometry_v2 import (
    ImageGeometryContractError,
    is_sequence_range_filename_candidate,
    parse_attested_sequence_range_filename,
)
from game_predictor_api.domain.image_sequence_canonical import (
    parse_browser_sequence_manifest,
)
from game_predictor_api.domain.jobs import Job, JobConflictError

from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError

from .discovery import (
    ImageDiscoveryError,
    SourceFile,
    SourceImage,
    SourceManifest,
    discover_images,
)
from .image_file import ImageFileError, read_jpeg_dimensions, sha256_file
from .selection.output import (
    CuratedImageEntry,
    CuratedImageManifest,
    verify_curated_image_manifest,
)

SOURCE_INGESTION_CONTRACT = "image-source-ingestion-v1"
BROWSER_SELECTION_MANIFEST = "_browser_manifest.json"
COPY_CHECKPOINT_BATCH_SIZE = 25
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ManagedOriginal:
    checksum_sha256: str
    source_relative_path: str
    managed_relative_path: str
    size_bytes: int
    source_storage_relative_path: str | None = None
    sequence_range_start: int | None = None
    sequence_range_end: int | None = None
    sequence_range_source: str | None = None


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
        if job.input_payload.get("schema_version") in {4, 6}:
            content = self._managed_reprocess_manifest_bytes(job)
            self._write_immutable(destination, content)
            return self._load_manifest(destination, relative_path, job)
        if job.input_payload.get("schema_version") == 3:
            content = _curated_manifest_bytes(job, source_directory)
            self._write_immutable(destination, content)
            return self._load_manifest(destination, relative_path, job)
        browser_manifest = source_directory / BROWSER_SELECTION_MANIFEST
        if browser_manifest.is_file():
            try:
                content = _browser_manifest_bytes(job, source_directory)
            except (OSError, ImageFileError, ValueError) as error:
                if isinstance(error, JobHandlerError):
                    raise
                raise JobHandlerError(
                    "IMAGE_SEQUENCE_MANIFEST_INVALID",
                    "The finalized browser sequence manifest is invalid.",
                ) from error
            self._write_immutable(destination, content)
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

    def _managed_reprocess_manifest_bytes(self, job: Job) -> bytes:
        raw_source_job_id = job.input_payload.get("managed_source_job_id")
        try:
            source_job_id = UUID(str(raw_source_job_id))
        except (TypeError, ValueError) as error:
            raise JobHandlerError(
                "IMAGE_REPROCESS_SOURCE_INVALID",
                "The managed reprocess source job is invalid.",
            ) from error
        if source_job_id == job.id:
            raise JobHandlerError(
                "IMAGE_REPROCESS_SOURCE_INVALID",
                "An image import cannot reprocess itself.",
            )
        source_relative = f"data/originals/manifests/{source_job_id}.json"
        source_path = self._safe_path(source_relative)
        try:
            source_content = source_path.read_bytes()
            value = json.loads(source_content)
        except FileNotFoundError as error:
            raise JobHandlerError(
                "IMAGE_REPROCESS_SOURCE_MANIFEST_MISSING",
                "The source import no longer has a managed-original manifest.",
            ) from error
        except (OSError, json.JSONDecodeError) as error:
            raise JobHandlerError(
                "IMAGE_REPROCESS_SOURCE_MANIFEST_INVALID",
                "The source import managed-original manifest is invalid.",
            ) from error
        if (
            not isinstance(value, Mapping)
            or value.get("contractVersion") != SOURCE_INGESTION_CONTRACT
            or value.get("jobId") != str(source_job_id)
            or value.get("gameId") != (None if job.game_id is None else str(job.game_id))
        ):
            raise JobHandlerError(
                "IMAGE_REPROCESS_SOURCE_MANIFEST_INVALID",
                "The source import manifest has different provenance.",
            )
        if job.input_payload.get("schema_version") == 6:
            expected_checksum = job.input_payload.get(
                "managed_source_manifest_checksum_sha256"
            )
            if (
                not isinstance(expected_checksum, str)
                or not SHA256_PATTERN.fullmatch(expected_checksum)
                or hashlib.sha256(source_content).hexdigest() != expected_checksum
            ):
                raise JobHandlerError(
                    "IMAGE_REPROCESS_PAGE_GEOMETRY_MANIFEST_INCOMPATIBLE",
                    "The managed-original manifest changed after reprocess creation.",
                )
        originals = value.get("originals")
        if not isinstance(originals, Sequence) or isinstance(originals, str | bytes):
            raise JobHandlerError(
                "IMAGE_REPROCESS_SOURCE_MANIFEST_INVALID",
                "The source import manifest has no managed originals.",
            )
        parsed = tuple(_parse_original(item) for item in originals)
        if not parsed:
            raise JobHandlerError(
                "IMAGE_REPROCESS_SOURCE_MANIFEST_INVALID",
                "The source import manifest has no managed originals.",
            )
        cloned = dict(value)
        cloned["jobId"] = str(job.id)
        cloned["reprocessedFromJobId"] = str(source_job_id)
        return json.dumps(
            cloned,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        ).encode("ascii")

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
            original.source_storage_relative_path or original.source_relative_path,
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
    def __init__(
        self,
        store: ManagedOriginalStore,
        *,
        before_original: Callable[[Job], bool] | None = None,
    ) -> None:
        self._store = store
        self._before_original = before_original

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        self.ingest(context, job)

    def ingest(
        self,
        context: JobExecutionContext,
        job: Job,
        *,
        originals: Sequence[ManagedOriginal] | None = None,
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
        selected = manifest.originals if originals is None else tuple(originals)
        known = {original.checksum_sha256 for original in manifest.originals}
        if any(original.checksum_sha256 not in known for original in selected):
            raise JobHandlerError(
                "IMAGE_SOURCE_SELECTION_INVALID",
                "The selected managed originals do not belong to this immutable manifest.",
            )
        total = len(selected)
        copied = 0
        for index, original in enumerate(selected, start=1):
            if self._before_original is not None and not self._before_original(context.job):
                context.wait_for_storage(
                    checkpoint_payload={
                        "checkpoint_kind": "image-storage-wait-v1",
                        "managed_original_count": copied,
                        "schema_version": 1,
                    }
                )
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
    all_source_paths = [file.relative_path for image in manifest.images for file in image.files]
    has_attested_names = any(
        is_sequence_range_filename_candidate(path) for path in all_source_paths
    )
    attested_ranges: dict[str, tuple[int, int]] = {}
    sequence_range_warnings: list[dict[str, int | str]] = []
    if has_attested_names:
        parsed_ranges: list[tuple[str, int, int]] = []
        for relative_path in all_source_paths:
            try:
                sequence_range = parse_attested_sequence_range_filename(relative_path)
            except ImageGeometryContractError as error:
                raise JobHandlerError(
                    "IMAGE_SEQUENCE_FILENAME_INVALID",
                    f"The seq_* import contains an invalid filename: {relative_path}.",
                ) from error
            parsed_ranges.append((relative_path, sequence_range.start, sequence_range.end))
        ordered_ranges = sorted(parsed_ranges, key=lambda item: (item[1], item[2], item[0]))
        for index, (relative_path, start, end) in enumerate(ordered_ranges):
            if index and start > ordered_ranges[index - 1][2] + 1:
                sequence_range_warnings.append(
                    {
                        "code": "IMAGE_SEQUENCE_RANGE_GAP",
                        "from": ordered_ranges[index - 1][2] + 1,
                        "to": start - 1,
                    }
                )
            if index and start <= ordered_ranges[index - 1][2]:
                raise JobHandlerError(
                    "IMAGE_SEQUENCE_FILENAME_CONFLICT",
                    "The seq_* import contains duplicate or overlapping ranges.",
                )
            attested_ranges[relative_path] = (start, end)

    originals = []
    for image in manifest.images:
        source_file = image.files[0]
        entry: dict[str, object] = {
            "checksumSha256": image.checksum_sha256,
            "managedRelativePath": (
                f"data/originals/{image.checksum_sha256[:2]}/{image.checksum_sha256}.jpg"
            ),
            "sizeBytes": source_file.size_bytes,
            "sourceRelativePath": source_file.relative_path,
            "sourceRelativePaths": [item.relative_path for item in image.files],
        }
        if has_attested_names:
            start, end = attested_ranges[source_file.relative_path]
            entry.update(
                {
                    "sequenceRangeEnd": end,
                    "sequenceRangeStart": start,
                    "sequenceRangeSource": "filename",
                }
            )
        originals.append(entry)
    if has_attested_names:
        originals.sort(
            key=lambda item: (
                cast(int, item["sequenceRangeStart"]),
                cast(int, item["sequenceRangeEnd"]),
            )
        )
    payload = {
        "contractVersion": SOURCE_INGESTION_CONTRACT,
        "discovery": manifest.to_dict(),
        "gameId": None if job.game_id is None else str(job.game_id),
        "jobId": str(job.id),
        "originals": originals,
        "sequenceRangeSource": "filename" if has_attested_names else None,
        "sequenceRangeWarnings": sequence_range_warnings,
        "schemaVersion": 1,
        "sourceDirectory": str(source.resolve(strict=True)),
    }
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _curated_manifest_bytes(job: Job, source: Path) -> bytes:
    payload = job.input_payload
    checksum = payload.get("curated_manifest_checksum_sha256")
    start = payload.get("curated_manifest_entry_start")
    count = payload.get("curated_manifest_entry_count")
    run_value = payload.get("image_selection_run_id")
    if (
        not isinstance(checksum, str)
        or not SHA256_PATTERN.fullmatch(checksum)
        or not isinstance(start, int)
        or isinstance(start, bool)
        or start < 0
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count < 1
        or not isinstance(run_value, str)
    ):
        raise JobHandlerError(
            "CURATED_IMAGE_IMPORT_PAYLOAD_INVALID",
            "The curated manifest slice payload is incomplete.",
        )
    try:
        run_id = UUID(run_value)
        manifest = verify_curated_image_manifest(
            source,
            expected_manifest_sha256=checksum,
            expected_run_id=run_id,
            verify_entry_indexes=range(start, start + count),
        )
    except (OSError, ValueError) as error:
        raise JobHandlerError(
            "CURATED_IMAGE_IMPORT_MANIFEST_MISMATCH",
            "The curated manifest or one of the selected JPEG files changed.",
        ) from error
    ordered = _ordered_curated_entries(manifest)
    selected = ordered[start : start + count]
    if len(selected) != count:
        raise JobHandlerError(
            "CURATED_IMAGE_IMPORT_RANGE_INVALID",
            "The curated manifest slice exceeds the available entries.",
        )
    originals = [
        {
            "checksumSha256": entry.output_checksum_sha256,
            "curatedGroupOrder": entry.group_order,
            "curatedRangeEnd": entry.range_end,
            "curatedRangeStart": entry.range_start,
            "sequenceRangeEnd": entry.range_end,
            "sequenceRangeSource": "filename",
            "sequenceRangeStart": entry.range_start,
            "managedRelativePath": (
                "data/originals/"
                f"{entry.output_checksum_sha256[:2]}/{entry.output_checksum_sha256}.jpg"
            ),
            "sizeBytes": entry.size_bytes,
            "sourceRelativePath": entry.output_relative_path,
            "sourceRelativePaths": [entry.output_relative_path],
        }
        for entry in selected
    ]
    managed_payload = {
        "contractVersion": SOURCE_INGESTION_CONTRACT,
        "curatedSource": {
            "batchId": payload.get("curated_image_import_batch_id"),
            "entryCount": count,
            "entryStart": start,
            "manifestChecksumSha256": checksum,
            "runId": run_value,
            "sourceId": payload.get("curated_image_import_source_id"),
        },
        "gameId": None if job.game_id is None else str(job.game_id),
        "jobId": str(job.id),
        "originals": originals,
        "schemaVersion": 1,
        "sourceDirectory": str(source.resolve(strict=True)),
    }
    return (
        json.dumps(managed_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _browser_manifest_bytes(job: Job, source: Path) -> bytes:
    """Build a managed manifest while preserving browser logical filenames."""

    manifest_path = source / BROWSER_SELECTION_MANIFEST
    manifest_bytes = manifest_path.read_bytes()
    try:
        browser_manifest = parse_browser_sequence_manifest(
            json.loads(manifest_bytes),
            checksum_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        )
    except JobConflictError as error:
        raise JobHandlerError(error.code, error.message) from error
    except (json.JSONDecodeError, ValueError) as error:
        raise JobHandlerError(
            "IMAGE_SEQUENCE_MANIFEST_INVALID",
            "The finalized browser sequence manifest is invalid.",
        ) from error
    source_selection_id = job.input_payload.get("source_selection_id")
    if source_selection_id is not None and str(source_selection_id) != source.name:
        raise JobHandlerError(
            "IMAGE_SEQUENCE_MANIFEST_INVALID",
            "The browser staging folder does not match the job source selection.",
        )
    originals: list[dict[str, object]] = []
    images: list[SourceImage] = []
    seen_checksums: set[str] = set()
    for item in browser_manifest.files:
        physical = _safe_source_path(source, item.stored_file_name)
        try:
            stat = physical.stat()
            width, height = read_jpeg_dimensions(physical)
            checksum = sha256_file(physical)
        except (OSError, ImageFileError) as error:
            raise JobHandlerError(
                "IMAGE_SOURCE_CHANGED",
                "A browser-staged image is missing or unreadable.",
            ) from error
        if stat.st_size != item.size_bytes or checksum != item.checksum_sha256:
            raise JobHandlerError(
                "IMAGE_SOURCE_CHANGED",
                f"A browser-staged image changed after upload: {item.stored_file_name}.",
            )
        if checksum in seen_checksums:
            raise JobHandlerError(
                "IMAGE_SEQUENCE_DUPLICATE_CHECKSUM",
                f"A seq_* import contains the same JPEG more than once: {item.relative_path}.",
            )
        seen_checksums.add(checksum)
        source_file = SourceFile(
            relative_path=item.relative_path,
            size_bytes=item.size_bytes,
            modified_at_ns=stat.st_mtime_ns,
        )
        images.append(
            SourceImage(
                checksum_sha256=checksum,
                width=width,
                height=height,
                files=(source_file,),
            )
        )
        entry: dict[str, object] = {
            "checksumSha256": checksum,
            "managedRelativePath": f"data/originals/{checksum[:2]}/{checksum}.jpg",
            "sizeBytes": item.size_bytes,
            "sourceRelativePath": item.relative_path,
            "sourceStorageRelativePath": item.stored_file_name,
            "sourceRelativePaths": [item.relative_path],
        }
        if item.sequence_range is not None:
            entry.update(
                {
                    "sequenceRangeEnd": item.sequence_range[1],
                    "sequenceRangeStart": item.sequence_range[0],
                    "sequenceRangeSource": "filename",
                }
            )
        originals.append(entry)
    source_manifest = SourceManifest(
        images=tuple(images),
        issues=(),
        ignored_file_count=0,
    )
    if browser_manifest.files[0].sequence_range is not None:
        originals.sort(
            key=lambda item: (
                cast(int, item["sequenceRangeStart"]),
                cast(int, item["sequenceRangeEnd"]),
            )
        )
    payload = {
        "browserManifestChecksumSha256": browser_manifest.checksum_sha256,
        "contractVersion": SOURCE_INGESTION_CONTRACT,
        "discovery": source_manifest.to_dict(),
        "gameId": None if job.game_id is None else str(job.game_id),
        "jobId": str(job.id),
        "originals": originals,
        "sequenceRangeSource": (
            "filename" if browser_manifest.files[0].sequence_range is not None else None
        ),
        "sequenceRangeWarnings": [{"code": warning} for warning in browser_manifest.warnings],
        "schemaVersion": 1,
        "sourceDirectory": str(source.resolve(strict=True)),
    }
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _ordered_curated_entries(
    manifest: CuratedImageManifest,
) -> tuple[CuratedImageEntry, ...]:
    ordered = tuple(sorted(manifest.entries, key=lambda entry: entry.group_order))
    if tuple(entry.group_order for entry in manifest.entries) != tuple(
        entry.group_order for entry in ordered
    ):
        raise JobHandlerError(
            "CURATED_IMAGE_IMPORT_ORDER_INVALID",
            "The curated manifest is not ordered by groupOrder.",
        )
    return ordered


def _parse_original(value: object) -> ManagedOriginal:
    if not isinstance(value, Mapping):
        _invalid_manifest()
    item = cast(Mapping[str, object], value)
    checksum = item.get("checksumSha256")
    source_path = item.get("sourceRelativePath")
    managed_path = item.get("managedRelativePath")
    size = item.get("sizeBytes")
    range_start = item.get("sequenceRangeStart")
    range_end = item.get("sequenceRangeEnd")
    range_source = item.get("sequenceRangeSource")
    storage_path = item.get("sourceStorageRelativePath")
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
        or (
            range_start is not None
            and (
                not isinstance(range_start, int) or isinstance(range_start, bool) or range_start < 1
            )
        )
        or (
            range_end is not None
            and (not isinstance(range_end, int) or isinstance(range_end, bool) or range_end < 1)
        )
        or ((range_start is None) != (range_end is None))
        or (range_start is not None and range_end is not None and range_end < range_start)
        or (range_start is not None and range_end is not None and range_end - range_start > 8)
        or (range_source is not None and range_source != "filename")
        or (storage_path is not None and (not isinstance(storage_path, str) or not storage_path))
    ):
        _invalid_manifest()
    return ManagedOriginal(
        cast(str, checksum),
        cast(str, source_path),
        cast(str, managed_path),
        cast(int, size),
        cast(str | None, storage_path),
        cast(int | None, range_start),
        cast(int | None, range_end),
        cast(str | None, range_source),
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
