"""Domain contracts for canonical, incrementally imported image sequences."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import UUID

from .jobs import JobConflictError

_SEQ_NAME = re.compile(
    r"^seq_(?P<start>[1-9][0-9]*)-(?P<end>[1-9][0-9]*)\.(?:jpg|jpeg)$", re.IGNORECASE
)


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


class ImageSequenceCanonicalService:
    def __init__(self, repository: ImageSequenceCanonicalRepository) -> None:
        self._repository = repository

    def canonical_numbers(self, game_id: UUID) -> set[int]:
        """Return the immutable sequence snapshot used when an import starts."""

        return set(self._repository.canonical_numbers(game_id))

    def preflight(
        self,
        *,
        game_id: UUID,
        source_directory: Path,
    ) -> ImageSequenceImportPreflight:
        files = tuple(
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
        ranges: list[tuple[Path, int, int]] = []
        warnings: list[str] = []
        for path in files:
            match = _SEQ_NAME.fullmatch(path.name)
            if match is None:
                warnings.append("IMAGE_SEQUENCE_FILENAME_NOT_ATTESTED")
                continue
            start = int(match.group("start"))
            end = int(match.group("end"))
            if end < start or end - start > 8:
                raise JobConflictError(
                    "IMAGE_SEQUENCE_PREFLIGHT_RANGE_INVALID",
                    "A seq_* filename contains an invalid inclusive range.",
                    details={"fileName": path.name},
                )
            ranges.append((path, start, end))
        if not ranges:
            warnings.append("IMAGE_SEQUENCE_RANGE_NOT_ATTESTED")
            return ImageSequenceImportPreflight(
                game_id=game_id,
                source_file_count=len(files),
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
        ranges.sort(key=lambda value: (value[1], value[2], value[0].name.casefold()))
        previous_end = 0
        for _path, start, end in ranges:
            if start <= previous_end:
                raise JobConflictError(
                    "IMAGE_SEQUENCE_PREFLIGHT_RANGE_OVERLAP",
                    "The seq_* import contains duplicate or overlapping ranges.",
                )
            if previous_end and start > previous_end + 1:
                warnings.append("IMAGE_SEQUENCE_RANGE_GAP")
            previous_end = end
        canonical = self._repository.canonical_numbers(game_id)
        unresolved: list[int] = []
        new_count = 0
        reused_count = 0
        skipped_sources = 0
        partial_sources = 0
        for _path, start, end in ranges:
            numbers = range(start, end + 1)
            existing = sum(number in canonical for number in numbers)
            count = end - start + 1
            reused_count += existing
            new_count += count - existing
            if existing == count:
                skipped_sources += 1
            elif existing:
                partial_sources += 1
            unresolved.extend(number for number in numbers if number not in canonical)
        return ImageSequenceImportPreflight(
            game_id=game_id,
            source_file_count=len(files),
            attested_file_count=len(ranges),
            new_sequence_count=new_count,
            reused_sequence_count=reused_count,
            skipped_source_count=skipped_sources,
            partial_source_count=partial_sources,
            alternative_source_count=0,
            first_unresolved_sequence=min(unresolved) if unresolved else None,
            last_unresolved_sequence=max(unresolved) if unresolved else None,
            warnings=tuple(dict.fromkeys(warnings)),
        )


__all__ = [
    "ImageSequenceCanonicalRepository",
    "ImageSequenceCanonicalService",
    "ImageSequenceImportPreflight",
]
