"""Application boundary for image-job operations and statistics."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ImageJobStageCount:
    stage: str
    count: int


@dataclass(frozen=True, slots=True)
class ImageJobFile:
    file_execution_key: str
    order_index: int
    source_relative_path: str
    status: str
    next_stage: str | None
    failed_stage: str | None
    error_code: str | None
    error_message: str | None
    retry_count: int
    review_required: bool
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ImageJobOperations:
    job_id: UUID
    pipeline_fingerprint: str
    total: int
    current: int
    succeeded: int
    failed: int
    review: int
    waiting: int
    elapsed_seconds: float | None
    files_per_minute: float | None
    stage_counts: Sequence[ImageJobStageCount]
    files: Sequence[ImageJobFile]
    file_limit: int
    has_more_files: bool


class ImageJobOperationsRepository(Protocol):
    def get_operations(
        self,
        job_id: UUID,
        *,
        file_limit: int,
    ) -> ImageJobOperations: ...

    def retry_file(
        self,
        job_id: UUID,
        *,
        file_execution_key: str,
        expected_stage: str,
        retried_at: datetime,
        file_limit: int,
    ) -> ImageJobOperations: ...


class ImageJobOperationsService:
    def __init__(
        self,
        repository: ImageJobOperationsRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(UTC))

    def get_operations(
        self,
        job_id: UUID,
        *,
        file_limit: int,
    ) -> ImageJobOperations:
        return self._repository.get_operations(job_id, file_limit=file_limit)

    def retry_file(
        self,
        job_id: UUID,
        *,
        file_execution_key: str,
        expected_stage: str,
        file_limit: int,
    ) -> ImageJobOperations:
        return self._repository.retry_file(
            job_id,
            file_execution_key=file_execution_key,
            expected_stage=expected_stage,
            retried_at=self._clock(),
            file_limit=file_limit,
        )


__all__ = [
    "ImageJobFile",
    "ImageJobOperations",
    "ImageJobOperationsRepository",
    "ImageJobOperationsService",
    "ImageJobStageCount",
]
