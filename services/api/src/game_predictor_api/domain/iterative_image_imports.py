"""Domain contracts for ordered, incremental imports from curated images."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from game_predictor_api.domain.jobs import Job, JobStatus


class IterativeImageImportError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class IterativeImageImportNotFoundError(IterativeImageImportError):
    """A curated source or referenced selection run does not exist."""


class IterativeImageImportConflictError(IterativeImageImportError):
    """A reservation conflicts with durable source state."""


@dataclass(frozen=True, slots=True)
class CuratedImageImportSource:
    id: UUID
    game_id: UUID
    image_selection_run_id: UUID
    manifest_relative_path: str
    manifest_checksum_sha256: str
    total_entries: int
    next_entry_index: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CuratedImageImportBatch:
    id: UUID
    source_id: UUID
    batch_number: int
    start_index: int
    end_index: int
    job: Job
    created_at: datetime

    @property
    def image_count(self) -> int:
        return self.end_index - self.start_index


def create_curated_source(
    *,
    game_id: UUID,
    image_selection_run_id: UUID,
    manifest_relative_path: str,
    manifest_checksum_sha256: str,
    total_entries: int,
    created_at: datetime | None = None,
) -> CuratedImageImportSource:
    if total_entries < 1:
        raise IterativeImageImportError(
            "CURATED_IMAGE_IMPORT_EMPTY",
            "The curated image manifest has no importable entries.",
        )
    now = created_at or datetime.now(UTC)
    return CuratedImageImportSource(
        id=uuid4(),
        game_id=game_id,
        image_selection_run_id=image_selection_run_id,
        manifest_relative_path=manifest_relative_path,
        manifest_checksum_sha256=manifest_checksum_sha256,
        total_entries=total_entries,
        next_entry_index=0,
        created_at=now,
        updated_at=now,
    )


def reserve_source_entries(
    source: CuratedImageImportSource,
    *,
    requested_count: int,
    batch_number: int,
    batch_id: UUID,
    job: Job,
    created_at: datetime | None = None,
) -> tuple[CuratedImageImportSource, CuratedImageImportBatch]:
    if requested_count < 1:
        raise IterativeImageImportError(
            "CURATED_IMAGE_IMPORT_COUNT_INVALID",
            "The image count must be at least one.",
        )
    remaining = source.total_entries - source.next_entry_index
    if remaining < 1:
        raise IterativeImageImportConflictError(
            "CURATED_IMAGE_IMPORT_COMPLETE",
            "All curated images have already been reserved.",
        )
    count = min(requested_count, remaining)
    now = created_at or datetime.now(UTC)
    batch = CuratedImageImportBatch(
        id=batch_id,
        source_id=source.id,
        batch_number=batch_number,
        start_index=source.next_entry_index,
        end_index=source.next_entry_index + count,
        job=job,
        created_at=now,
    )
    return (
        replace(
            source,
            next_entry_index=batch.end_index,
            updated_at=now,
        ),
        batch,
    )


def batch_allows_following_reservation(batch: CuratedImageImportBatch) -> bool:
    """Review is intentionally outside the import execution critical path."""

    return batch.job.status in {
        JobStatus.WAITING_FOR_REVIEW,
        JobStatus.COMPLETED,
    }


__all__ = [
    "CuratedImageImportBatch",
    "CuratedImageImportSource",
    "IterativeImageImportConflictError",
    "IterativeImageImportError",
    "IterativeImageImportNotFoundError",
    "batch_allows_following_reservation",
    "create_curated_source",
    "reserve_source_entries",
]
