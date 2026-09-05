"""Fail-closed evidence resolver for managed v0.10 image reprocessing."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast
from uuid import UUID

from game_predictor_api.domain.jobs import Job, JobStatus, JobType

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_LINEAGE_DEPTH = 64
_SOURCE_MANIFEST_CONTRACT = "image-source-ingestion-v1"
_PAGE_MANIFEST_VERSIONS = {
    (1, "page-geometry-preflight-v1"),
    (2, "page-geometry-preflight-v2-auto-anchor"),
    (2, "page-geometry-preflight-v3-board-area-mask"),
}


class ManagedReprocessEvidenceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class ManagedReprocessEvidence:
    managed_source_manifest_checksum_sha256: str
    source_manifest_sha256: str
    source_selection_id: UUID
    page_geometry_manifest: dict[str, object]


@dataclass(frozen=True, slots=True)
class _ManagedOriginalEvidence:
    checksum_sha256: str
    source_relative_path: str
    expected_board_count: int


def resolve_managed_reprocess_evidence(
    source: Job,
    *,
    artifact_root: Path,
    get_job: Callable[[UUID], Job | None],
) -> ManagedReprocessEvidence:
    """Resolve immutable source and page manifests without heuristic fallback."""

    root = artifact_root.resolve()
    managed_checksum, originals = _load_managed_source_manifest(root, source)
    lineage_job = source
    visited: set[UUID] = set()
    for _depth in range(_MAX_LINEAGE_DEPTH):
        if lineage_job.id in visited:
            raise _incompatible("The managed reprocess lineage contains a cycle.")
        visited.add(lineage_job.id)
        if lineage_job.game_id != source.game_id:
            raise _incompatible("The managed reprocess lineage crosses a game boundary.")

        descriptor = lineage_job.input_payload.get("page_geometry_manifest")
        if descriptor is not None:
            return _validate_page_geometry_evidence(
                root,
                source=source,
                lineage_job=lineage_job,
                descriptor=descriptor,
                originals=originals,
                managed_checksum=managed_checksum,
                get_job=get_job,
            )

        next_id = _lineage_parent_id(lineage_job)
        if next_id is None:
            raise _required()
        parent = get_job(next_id)
        if parent is None:
            raise _incompatible("A referenced source job in the lineage is unavailable.")
        lineage_job = parent
    raise _incompatible("The managed reprocess lineage exceeds the supported depth.")


def _load_managed_source_manifest(
    artifact_root: Path,
    source: Job,
) -> tuple[str, tuple[_ManagedOriginalEvidence, ...]]:
    relative = PurePosixPath("data", "originals", "manifests", f"{source.id}.json")
    path = _managed_path(artifact_root, relative)
    content = _read_bytes(path, "The managed-original manifest is unavailable.")
    checksum = hashlib.sha256(content).hexdigest()
    value = _json_object(content, "The managed-original manifest is invalid.")
    if (
        value.get("contractVersion") != _SOURCE_MANIFEST_CONTRACT
        or value.get("jobId") != str(source.id)
        or value.get("gameId") != (None if source.game_id is None else str(source.game_id))
    ):
        raise _incompatible("The managed-original manifest has different provenance.")
    raw_originals = value.get("originals")
    if not isinstance(raw_originals, Sequence) or isinstance(raw_originals, str | bytes):
        raise _incompatible("The managed-original manifest has no source inventory.")
    originals = tuple(_managed_original(item) for item in raw_originals)
    if not originals:
        raise _incompatible("The managed-original manifest has no source inventory.")
    checksums = [item.checksum_sha256 for item in originals]
    relative_paths = [item.source_relative_path for item in originals]
    if len(set(checksums)) != len(checksums) or len(set(relative_paths)) != len(relative_paths):
        raise _incompatible("The managed-original manifest contains duplicate sources.")
    return checksum, originals


def _managed_original(value: object) -> _ManagedOriginalEvidence:
    if not isinstance(value, Mapping):
        raise _incompatible("The managed-original source inventory is invalid.")
    checksum = value.get("checksumSha256")
    relative_path = value.get("sourceRelativePath")
    if (
        not isinstance(checksum, str)
        or _SHA256.fullmatch(checksum) is None
        or not isinstance(relative_path, str)
        or not relative_path.strip()
    ):
        raise _incompatible("The managed-original source identity is invalid.")
    start = value.get("sequenceRangeStart")
    end = value.get("sequenceRangeEnd")
    if start is None and end is None:
        expected_board_count = 9
    elif (
        not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or start < 1
        or end < start
        or end - start + 1 > 9
    ):
        raise _incompatible("The managed-original attested sequence range is invalid.")
    else:
        expected_board_count = end - start + 1
    return _ManagedOriginalEvidence(checksum, relative_path, expected_board_count)


def _validate_page_geometry_evidence(
    artifact_root: Path,
    *,
    source: Job,
    lineage_job: Job,
    descriptor: object,
    originals: tuple[_ManagedOriginalEvidence, ...],
    managed_checksum: str,
    get_job: Callable[[UUID], Job | None],
) -> ManagedReprocessEvidence:
    if not isinstance(descriptor, Mapping):
        raise _incompatible("The page-geometry manifest descriptor is invalid.")
    checksum = descriptor.get("checksumSha256")
    relative_path = descriptor.get("relativePath")
    raw_preflight_id = descriptor.get("preflightJobId")
    try:
        preflight_id = UUID(str(raw_preflight_id))
    except (TypeError, ValueError) as error:
        raise _incompatible("The page-geometry preflight identity is invalid.") from error
    if (
        not isinstance(checksum, str)
        or _SHA256.fullmatch(checksum) is None
        or not isinstance(relative_path, str)
    ):
        raise _incompatible("The page-geometry manifest descriptor is incomplete.")
    relative = PurePosixPath(relative_path)
    if relative.parts[:2] != ("data", "page-geometry-manifests"):
        raise _incompatible("The page-geometry manifest path is outside managed storage.")
    content = _read_bytes(
        _managed_path(artifact_root, relative),
        "The page-geometry manifest is unavailable.",
    )
    if hashlib.sha256(content).hexdigest() != checksum:
        raise _incompatible("The page-geometry manifest checksum changed.")
    manifest = _json_object(content, "The page-geometry manifest is invalid.")

    source_selection_id = _required_uuid(
        lineage_job.input_payload.get("source_selection_id"),
        "The source selection identity is unavailable in the manifest lineage.",
    )
    source_manifest_sha256 = lineage_job.input_payload.get("source_manifest_sha256")
    if (
        not isinstance(source_manifest_sha256, str)
        or _SHA256.fullmatch(source_manifest_sha256) is None
    ):
        raise _incompatible("The browser source manifest checksum is unavailable in the lineage.")
    if (
        manifest.get("gameId") != str(source.game_id)
        or manifest.get("sourceSelectionId") != str(source_selection_id)
        or manifest.get("sourceManifestChecksumSha256") != source_manifest_sha256
        or (manifest.get("schemaVersion"), manifest.get("version"))
        not in _PAGE_MANIFEST_VERSIONS
    ):
        raise _incompatible("The page-geometry manifest has different source provenance.")

    preflight = get_job(preflight_id)
    checkpoint = None if preflight is None else preflight.checkpoint_payload
    if (
        preflight is None
        or preflight.game_id != source.game_id
        or preflight.job_type is not JobType.VALIDATE
        or preflight.status is not JobStatus.COMPLETED
        or preflight.input_payload.get("validation_kind") != "page_geometry_preflight"
        or str(preflight.input_payload.get("source_selection_id")) != str(source_selection_id)
        or not isinstance(checkpoint, Mapping)
        or checkpoint.get("complete") is not True
        or checkpoint.get("geometry_manifest_checksum_sha256") != checksum
        or checkpoint.get("geometry_manifest_relative_path") != relative_path
    ):
        raise _incompatible("The page-geometry manifest is not backed by its completed preflight.")

    entries = manifest.get("entries")
    source_count = manifest.get("sourceCount")
    if (
        not isinstance(entries, Mapping)
        or source_count != len(originals)
        or len(entries) != len(originals)
    ):
        raise _incompatible("The page-geometry manifest does not cover every managed source.")
    by_checksum = {item.checksum_sha256: item for item in originals}
    if set(entries) != set(by_checksum):
        raise _incompatible("The page-geometry manifest source inventory is incompatible.")
    counts = {"registered": 0, "review_required": 0, "skipped_human_resolved": 0}
    for source_checksum, raw_entry in entries.items():
        original = by_checksum[cast(str, source_checksum)]
        if not isinstance(raw_entry, Mapping):
            raise _incompatible("A page-geometry manifest entry is invalid.")
        status = raw_entry.get("status")
        if (
            status not in counts
            or raw_entry.get("sourceRelativePath") != original.source_relative_path
        ):
            raise _incompatible("A page-geometry manifest entry has incompatible provenance.")
        counts[cast(str, status)] += 1
        if status == "registered":
            quads = raw_entry.get("quads")
            width = raw_entry.get("imageWidth")
            height = raw_entry.get("imageHeight")
            if (
                not isinstance(quads, Sequence)
                or isinstance(quads, str | bytes)
                or len(quads) != original.expected_board_count
                or not isinstance(width, int)
                or isinstance(width, bool)
                or width < 1
                or not isinstance(height, int)
                or isinstance(height, bool)
                or height < 1
            ):
                raise _incompatible("A registered page-geometry entry is incomplete.")
    expected_counts = {
        "registered": manifest.get("registeredSourceCount"),
        "review_required": manifest.get("reviewRequiredSourceCount"),
        "skipped_human_resolved": manifest.get("skippedHumanResolvedSourceCount"),
    }
    if counts != expected_counts:
        raise _incompatible("The page-geometry manifest disposition counts are inconsistent.")

    return ManagedReprocessEvidence(
        managed_source_manifest_checksum_sha256=managed_checksum,
        source_manifest_sha256=source_manifest_sha256,
        source_selection_id=source_selection_id,
        page_geometry_manifest={
            "checksumSha256": checksum,
            "preflightJobId": str(preflight_id),
            "relativePath": relative_path,
        },
    )


def _lineage_parent_id(job: Job) -> UUID | None:
    for field in ("managed_source_job_id", "previous_job_id"):
        raw = job.input_payload.get(field)
        if raw is None:
            continue
        try:
            return UUID(str(raw))
        except ValueError as error:
            raise _incompatible(
                "The managed reprocess lineage contains an invalid job ID."
            ) from error
    return None


def _managed_path(artifact_root: Path, relative: PurePosixPath) -> Path:
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise _incompatible("An evidence manifest path is unsafe.")
    path = artifact_root.joinpath(*relative.parts).resolve()
    data_root = (artifact_root / "data").resolve()
    if not path.is_relative_to(data_root):
        raise _incompatible("An evidence manifest path escapes managed storage.")
    return path


def _read_bytes(path: Path, message: str) -> bytes:
    try:
        if path.is_symlink() or not path.is_file():
            raise OSError
        return path.read_bytes()
    except OSError as error:
        raise _incompatible(message) from error


def _json_object(content: bytes, message: str) -> Mapping[str, object]:
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _incompatible(message) from error
    if not isinstance(value, Mapping):
        raise _incompatible(message)
    return cast(Mapping[str, object], value)


def _required_uuid(value: object, message: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as error:
        raise _incompatible(message) from error


def _required() -> ManagedReprocessEvidenceError:
    return ManagedReprocessEvidenceError(
        "IMAGE_REPROCESS_PAGE_GEOMETRY_MANIFEST_REQUIRED",
        "Managed v0.10 reprocessing requires an exact page-geometry preflight manifest.",
    )


def _incompatible(message: str) -> ManagedReprocessEvidenceError:
    return ManagedReprocessEvidenceError(
        "IMAGE_REPROCESS_PAGE_GEOMETRY_MANIFEST_INCOMPATIBLE",
        message,
    )


__all__ = [
    "ManagedReprocessEvidence",
    "ManagedReprocessEvidenceError",
    "resolve_managed_reprocess_evidence",
]
