"""Application workflow for ordered imports from curated image-selection output."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import UUID, uuid4

from game_predictor_worker.images.pipeline_contract import (
    current_pipeline_manifest,
    pipeline_fingerprint,
)
from game_predictor_worker.images.selection.output import (
    verify_curated_image_manifest,
)

from game_predictor_api.application.image_selections import ImageSelectionService
from game_predictor_api.application.jobs import JobService
from game_predictor_api.domain.iterative_image_imports import (
    CuratedImageImportBatch,
    CuratedImageImportSource,
    IterativeImageImportConflictError,
    IterativeImageImportNotFoundError,
    batch_allows_following_reservation,
    create_curated_source,
    reserve_source_entries,
)


class IterativeImageImportRepository(Protocol):
    def find_source_by_run(
        self,
        image_selection_run_id: UUID,
    ) -> CuratedImageImportSource | None: ...

    def get_source(self, source_id: UUID) -> CuratedImageImportSource | None: ...

    def get_source_for_update(
        self,
        source_id: UUID,
    ) -> CuratedImageImportSource | None: ...

    def list_sources(self, *, game_id: UUID) -> Sequence[CuratedImageImportSource]: ...

    def add_source(self, source: CuratedImageImportSource) -> CuratedImageImportSource: ...

    def save_source(self, source: CuratedImageImportSource) -> CuratedImageImportSource: ...

    def add_batch(self, batch: CuratedImageImportBatch) -> CuratedImageImportBatch: ...

    def list_batches(self, *, source_id: UUID) -> Sequence[CuratedImageImportBatch]: ...

    def next_batch_number(self, *, source_id: UUID) -> int: ...


@dataclass(frozen=True, slots=True)
class CuratedImageImportProgress:
    source: CuratedImageImportSource
    batches: tuple[CuratedImageImportBatch, ...]
    processed_entries: int
    failed_entries: int
    reserved_entries: int
    remaining_entries: int


class IterativeImageImportService:
    def __init__(
        self,
        repository: IterativeImageImportRepository,
        image_selection_service: ImageSelectionService,
        job_service: JobService,
        *,
        artifact_root: Path,
    ) -> None:
        self._repository = repository
        self._image_selection_service = image_selection_service
        self._job_service = job_service
        self._artifact_root = artifact_root.resolve()

    def register_source(
        self,
        *,
        game_id: UUID,
        image_selection_run_id: UUID,
    ) -> CuratedImageImportProgress:
        handoff = self._image_selection_service.prepare_handoff(image_selection_run_id)
        if handoff.run.game_id != game_id:
            raise IterativeImageImportConflictError(
                "CURATED_IMAGE_IMPORT_GAME_MISMATCH",
                "The image-selection output belongs to another game.",
            )
        manifest_checksum = handoff.run.output_manifest_sha256
        manifest_relative_path = handoff.run.output_manifest_relative_path
        if manifest_checksum is None or manifest_relative_path is None:
            raise IterativeImageImportConflictError(
                "CURATED_IMAGE_IMPORT_NOT_READY",
                "The image-selection output has no verified manifest.",
            )
        existing = self._repository.find_source_by_run(image_selection_run_id)
        if existing is not None:
            if (
                existing.game_id != game_id
                or existing.manifest_checksum_sha256 != manifest_checksum
                or existing.manifest_relative_path != manifest_relative_path
                or existing.total_entries != handoff.supported_file_count
            ):
                raise IterativeImageImportConflictError(
                    "CURATED_IMAGE_IMPORT_SOURCE_DRIFT",
                    "The registered curated source differs from the verified selection output.",
                )
            return self._progress(existing)
        source = create_curated_source(
            game_id=game_id,
            image_selection_run_id=image_selection_run_id,
            manifest_relative_path=manifest_relative_path,
            manifest_checksum_sha256=manifest_checksum,
            total_entries=handoff.supported_file_count,
        )
        return self._progress(self._repository.add_source(source))

    def list_sources(self, *, game_id: UUID) -> tuple[CuratedImageImportProgress, ...]:
        return tuple(
            self._progress(source) for source in self._repository.list_sources(game_id=game_id)
        )

    def get_source(self, source_id: UUID) -> CuratedImageImportProgress:
        source = self._repository.get_source(source_id)
        if source is None:
            raise IterativeImageImportNotFoundError(
                "CURATED_IMAGE_IMPORT_SOURCE_NOT_FOUND",
                "The curated image import source does not exist.",
            )
        return self._progress(source)

    def create_next_batch(
        self,
        source_id: UUID,
        *,
        requested_count: int,
    ) -> CuratedImageImportProgress:
        source = self._repository.get_source_for_update(source_id)
        if source is None:
            raise IterativeImageImportNotFoundError(
                "CURATED_IMAGE_IMPORT_SOURCE_NOT_FOUND",
                "The curated image import source does not exist.",
            )
        batches = tuple(self._repository.list_batches(source_id=source.id))
        if batches and not batch_allows_following_reservation(batches[-1]):
            raise IterativeImageImportConflictError(
                "CURATED_IMAGE_IMPORT_BATCH_BLOCKED",
                "Finish or retry the current image batch before reserving the next one.",
                details={
                    "jobId": str(batches[-1].job.id),
                    "status": batches[-1].job.status.value,
                },
            )
        remaining = source.total_entries - source.next_entry_index
        if remaining < 1:
            raise IterativeImageImportConflictError(
                "CURATED_IMAGE_IMPORT_COMPLETE",
                "All curated images have already been reserved.",
            )
        count = min(requested_count, remaining)
        batch_id = uuid4()
        batch_number = self._repository.next_batch_number(source_id=source.id)
        output_directory = self._verified_output_directory(
            source,
            entry_start=source.next_entry_index,
            entry_count=count,
        )
        job = self._job_service.create_curated_image_import_job(
            game_id=source.game_id,
            source_id=source.id,
            batch_id=batch_id,
            source_directory=output_directory,
            source_display_name=(
                f"Selekcja zdjęć {str(source.image_selection_run_id)[:8]} "
                f"· zdjęcia {source.next_entry_index + 1}–{source.next_entry_index + count}"
            ),
            manifest_relative_path=source.manifest_relative_path,
            manifest_checksum_sha256=source.manifest_checksum_sha256,
            entry_start=source.next_entry_index,
            entry_count=count,
            image_selection_run_id=source.image_selection_run_id,
            pipeline_fingerprint=pipeline_fingerprint(current_pipeline_manifest()),
        )
        updated, batch = reserve_source_entries(
            source,
            requested_count=count,
            batch_number=batch_number,
            batch_id=batch_id,
            job=job,
        )
        self._repository.add_batch(batch)
        self._repository.save_source(updated)
        return self._progress(updated)

    def _verified_output_directory(
        self,
        source: CuratedImageImportSource,
        *,
        entry_start: int,
        entry_count: int,
    ) -> Path:
        relative = PurePosixPath(source.manifest_relative_path)
        manifest_path = (self._artifact_root / Path(*relative.parts)).resolve()
        if not manifest_path.is_relative_to(self._artifact_root):
            raise IterativeImageImportConflictError(
                "CURATED_IMAGE_IMPORT_MANIFEST_PATH_INVALID",
                "The curated manifest escapes managed artifact storage.",
            )
        try:
            verify_curated_image_manifest(
                manifest_path.parent,
                expected_manifest_sha256=source.manifest_checksum_sha256,
                expected_run_id=source.image_selection_run_id,
                verify_entry_indexes=range(entry_start, entry_start + entry_count),
            )
        except (OSError, ValueError) as error:
            raise IterativeImageImportConflictError(
                "CURATED_IMAGE_IMPORT_MANIFEST_MISMATCH",
                "The curated manifest or one of its images changed.",
            ) from error
        return manifest_path.parent

    def _progress(self, source: CuratedImageImportSource) -> CuratedImageImportProgress:
        batches = tuple(self._repository.list_batches(source_id=source.id))
        processed = sum(
            batch.image_count for batch in batches if batch_allows_following_reservation(batch)
        )
        failed = sum(
            batch.image_count
            for batch in batches
            if batch.job.status.value in {"failed", "cancelled"}
        )
        return CuratedImageImportProgress(
            source=source,
            batches=batches,
            processed_entries=processed,
            failed_entries=failed,
            reserved_entries=source.next_entry_index,
            remaining_entries=source.total_entries - source.next_entry_index,
        )


__all__ = [
    "CuratedImageImportProgress",
    "IterativeImageImportRepository",
    "IterativeImageImportService",
]
