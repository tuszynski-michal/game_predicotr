"""Domain contracts for canonical, incrementally imported image sequences."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol, cast
from uuid import UUID

from .image_geometry_v2 import (
    ImageGeometryContractError,
    is_sequence_range_filename_candidate,
    parse_attested_sequence_range_filename,
)
from .jobs import JobConflictError

_STORED_NAME = re.compile(r"^[0-9]{8}\.(?:jpg|jpeg)$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class BrowserSequenceSource:
    """One file from the durable browser staging manifest.

    ``relative_path`` is the user-facing logical name (for example
    ``seq_1-9.jpg``), while ``stored_file_name`` is the controlled physical
    name used by the upload service (for example ``00000001.jpg``).
    """

    order_index: int
    relative_path: str
    stored_file_name: str
    size_bytes: int
    checksum_sha256: str
    sequence_range: tuple[int, int] | None


@dataclass(frozen=True, slots=True)
class BrowserSequenceManifest:
    files: tuple[BrowserSequenceSource, ...]
    warnings: tuple[str, ...]
    checksum_sha256: str


@dataclass(frozen=True, slots=True)
class ImageSequenceImportPreflight:
    game_id: UUID
    source_file_count: int
    attested_file_count: int
    new_sequence_count: int
    reused_sequence_count: int
    skipped_source_count: int
    partial_source_count: int
    alternative_source_count: int
    first_unresolved_sequence: int | None
    last_unresolved_sequence: int | None
    warnings: tuple[str, ...]


class ImageSequenceCanonicalRepository(Protocol):
    def canonical_numbers(self, game_id: UUID) -> set[int]: ...

    def canonical_source_checksums(self, game_id: UUID) -> Mapping[int, str]: ...

    def expected_layout_count(self, game_id: UUID) -> int | None: ...


class ImageSequenceCanonicalService:
    def __init__(self, repository: ImageSequenceCanonicalRepository) -> None:
        self._repository = repository

    def canonical_numbers(self, game_id: UUID) -> set[int]:
        """Return the immutable sequence snapshot used when an import starts."""

        return set(self._repository.canonical_numbers(game_id))

    def canonical_source_checksums(self, game_id: UUID) -> Mapping[int, str]:
        method = getattr(self._repository, "canonical_source_checksums", None)
        if not callable(method):
            return {}
        return cast(Mapping[int, str], method(game_id))

    def expected_layout_count(self, game_id: UUID) -> int | None:
        method = getattr(self._repository, "expected_layout_count", None)
        if not callable(method):
            return None
        return cast(int | None, method(game_id))

    def preflight(
        self,
        *,
        game_id: UUID,
        source_directory: Path | None = None,
        manifest: BrowserSequenceManifest | None = None,
    ) -> ImageSequenceImportPreflight:
        if manifest is not None:
            source_file_count = len(manifest.files)
            ranges: list[tuple[str | Path, int, int, str]] = [
                (
                    item.relative_path,
                    item.sequence_range[0],
                    item.sequence_range[1],
                    item.checksum_sha256,
                )
                for item in manifest.files
                if item.sequence_range is not None
            ]
        else:
            if source_directory is None:
                raise ValueError("source_directory or manifest is required")
            file_paths = tuple(
                sorted(
                    (
                        path
                        for path in source_directory.rglob("*")
                        if path.is_file() and path.suffix.casefold() in {".jpg", ".jpeg"}
                    ),
                    key=lambda path: PurePosixPath(path.relative_to(source_directory))
                    .as_posix()
                    .casefold(),
                )
            )
            source_file_count = len(file_paths)
            ranges = []
            for path in file_paths:
                if not is_sequence_range_filename_candidate(path.name):
                    continue
                try:
                    sequence_range = parse_attested_sequence_range_filename(path.name)
                except ImageGeometryContractError as error:
                    raise JobConflictError(
                        "IMAGE_SEQUENCE_PREFLIGHT_RANGE_INVALID",
                        "A seq_* filename contains an invalid inclusive range.",
                        details={"fileName": path.name},
                    ) from error
                ranges.append((path, sequence_range.start, sequence_range.end, ""))
        warnings: list[str] = list(manifest.warnings) if manifest is not None else []
        if manifest is not None and any(item.sequence_range is None for item in manifest.files):
            warnings.append("IMAGE_SEQUENCE_FILENAME_NOT_ATTESTED")
        elif manifest is None:
            for path in file_paths:
                if not is_sequence_range_filename_candidate(path.name):
                    warnings.append("IMAGE_SEQUENCE_FILENAME_NOT_ATTESTED")
        if not ranges:
            warnings.append("IMAGE_SEQUENCE_RANGE_NOT_ATTESTED")
            return ImageSequenceImportPreflight(
                game_id=game_id,
                source_file_count=source_file_count,
                attested_file_count=0,
                new_sequence_count=0,
                reused_sequence_count=0,
                skipped_source_count=0,
                partial_source_count=0,
                alternative_source_count=0,
                first_unresolved_sequence=None,
                last_unresolved_sequence=None,
                warnings=tuple(dict.fromkeys(warnings)),
            )
        ranges.sort(key=lambda value: (value[1], value[2], str(value[0]).casefold()))
        previous_end = 0
        for _path, start, end, _checksum in ranges:
            if start <= previous_end:
                raise JobConflictError(
                    "IMAGE_SEQUENCE_PREFLIGHT_RANGE_OVERLAP",
                    "The seq_* import contains duplicate or overlapping ranges.",
                )
            if previous_end and start > previous_end + 1:
                warnings.append("IMAGE_SEQUENCE_RANGE_GAP")
            previous_end = end
        expected_layout_count = self.expected_layout_count(game_id)
        if expected_layout_count is not None:
            out_of_bounds = next(
                (
                    (path, start, end)
                    for path, start, end, _checksum in ranges
                    if end > expected_layout_count
                ),
                None,
            )
            if out_of_bounds is not None:
                out_of_bounds_path, start, end = out_of_bounds
                raise JobConflictError(
                    "IMAGE_SEQUENCE_PREFLIGHT_OUT_OF_BOUNDS",
                    "A seq_* range exceeds the expected layout count for the game.",
                    details={
                        "expectedLayoutCount": expected_layout_count,
                        "fileName": PurePosixPath(str(out_of_bounds_path).replace("\\", "/")).name,
                        "rangeStart": start,
                        "rangeEnd": end,
                    },
                )
        canonical = self._repository.canonical_numbers(game_id)
        canonical_sources = self.canonical_source_checksums(game_id)
        unresolved: list[int] = []
        new_count = 0
        reused_count = 0
        skipped_sources = 0
        partial_sources = 0
        alternative_sources = 0
        for _path, start, end, checksum in ranges:
            numbers = range(start, end + 1)
            existing = sum(number in canonical for number in numbers)
            count = end - start + 1
            reused_count += existing
            new_count += count - existing
            if existing == count:
                skipped_sources += 1
            elif existing:
                partial_sources += 1
            if checksum and any(
                canonical_sources.get(number) not in {None, checksum}
                for number in numbers
                if number in canonical
            ):
                alternative_sources += 1
            unresolved.extend(number for number in numbers if number not in canonical)
        return ImageSequenceImportPreflight(
            game_id=game_id,
            source_file_count=source_file_count,
            attested_file_count=len(ranges),
            new_sequence_count=new_count,
            reused_sequence_count=reused_count,
            skipped_source_count=skipped_sources,
            partial_source_count=partial_sources,
            alternative_source_count=alternative_sources,
            first_unresolved_sequence=min(unresolved) if unresolved else None,
            last_unresolved_sequence=max(unresolved) if unresolved else None,
            warnings=tuple(dict.fromkeys(warnings)),
        )


__all__ = [
    "ImageSequenceCanonicalRepository",
    "ImageSequenceCanonicalService",
    "ImageSequenceImportPreflight",
    "BrowserSequenceManifest",
    "BrowserSequenceSource",
    "parse_browser_sequence_manifest",
]


def parse_browser_sequence_manifest(
    value: object,
    *,
    checksum_sha256: str,
) -> BrowserSequenceManifest:
    """Validate a finalized browser manifest and attest its logical ranges."""

    if not isinstance(value, Mapping):
        raise JobConflictError(
            "IMAGE_SEQUENCE_MANIFEST_INVALID", "The browser manifest must be an object."
        )
    if value.get("schemaVersion") != 1 or value.get("purpose") != "layout_import":
        raise JobConflictError(
            "IMAGE_SEQUENCE_MANIFEST_INVALID", "The browser manifest has an unsupported contract."
        )
    if value.get("orderingPolicy") != "natural_relative_path_v1":
        raise JobConflictError(
            "IMAGE_SEQUENCE_MANIFEST_INVALID",
            "The browser manifest has an unsupported ordering policy.",
        )
    raw_files = value.get("files")
    if not isinstance(raw_files, Sequence) or isinstance(raw_files, str | bytes) or not raw_files:
        raise JobConflictError(
            "IMAGE_SEQUENCE_MANIFEST_INVALID", "The browser manifest has no files."
        )
    parsed: list[BrowserSequenceSource] = []
    seen_indexes: set[int] = set()
    seen_stored: set[str] = set()
    any_attested = False
    any_unattested = False
    for raw in raw_files:
        if not isinstance(raw, Mapping):
            raise JobConflictError(
                "IMAGE_SEQUENCE_MANIFEST_INVALID", "A browser manifest file is invalid."
            )
        order = raw.get("orderIndex")
        relative = raw.get("relativePath")
        stored = raw.get("storedFileName")
        size = raw.get("sizeBytes")
        checksum = raw.get("checksumSha256")
        if (
            not isinstance(order, int)
            or isinstance(order, bool)
            or order < 0
            or not isinstance(relative, str)
            or not relative
            or not isinstance(stored, str)
            or not _STORED_NAME.fullmatch(stored)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 1
            or not isinstance(checksum, str)
            or not re.fullmatch(r"[0-9a-f]{64}", checksum)
            or order in seen_indexes
            or stored.casefold() in seen_stored
        ):
            raise JobConflictError(
                "IMAGE_SEQUENCE_MANIFEST_INVALID", "A browser manifest file has invalid metadata."
            )
        logical = PurePosixPath(relative.replace("\\", "/"))
        if logical.is_absolute() or any(part in {"", ".", ".."} for part in logical.parts):
            raise JobConflictError(
                "IMAGE_SEQUENCE_MANIFEST_INVALID", "A browser manifest path is unsafe."
            )
        sequence_range: tuple[int, int] | None
        if is_sequence_range_filename_candidate(logical.name):
            try:
                parsed_range = parse_attested_sequence_range_filename(logical.name)
            except ImageGeometryContractError as error:
                raise JobConflictError(
                    "IMAGE_SEQUENCE_PREFLIGHT_RANGE_INVALID",
                    "A seq_* filename contains an invalid inclusive range.",
                ) from error
            sequence_range = (parsed_range.start, parsed_range.end)
        else:
            sequence_range = None
        any_attested = any_attested or sequence_range is not None
        any_unattested = any_unattested or sequence_range is None
        parsed.append(
            BrowserSequenceSource(order, logical.as_posix(), stored, size, checksum, sequence_range)
        )
        seen_indexes.add(order)
        seen_stored.add(stored.casefold())
    expected_indexes = set(range(len(parsed)))
    if seen_indexes != expected_indexes or any_attested and any_unattested:
        raise JobConflictError(
            "IMAGE_SEQUENCE_MANIFEST_INVALID",
            "The browser manifest has non-contiguous or mixed sequence names.",
        )
    ordered = tuple(sorted(parsed, key=lambda item: item.order_index))
    ranges = sorted(
        (item.sequence_range[0], item.sequence_range[1], item.relative_path)
        for item in ordered
        if item.sequence_range is not None
    )
    previous_end = 0
    warnings: list[str] = []
    for start, end, _path in ranges:
        if start <= previous_end:
            raise JobConflictError(
                "IMAGE_SEQUENCE_PREFLIGHT_RANGE_OVERLAP",
                "The seq_* import contains duplicate or overlapping ranges.",
            )
        if previous_end and start > previous_end + 1:
            warnings.append("IMAGE_SEQUENCE_RANGE_GAP")
        previous_end = end
    return BrowserSequenceManifest(ordered, tuple(dict.fromkeys(warnings)), checksum_sha256)
