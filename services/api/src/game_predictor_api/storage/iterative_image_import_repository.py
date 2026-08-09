"""SQLAlchemy persistence for ordered curated-image import batches."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from game_predictor_api.application.iterative_image_imports import (
    IterativeImageImportRepository,
)
from game_predictor_api.domain.iterative_image_imports import (
    CuratedImageImportBatch,
    CuratedImageImportSource,
    IterativeImageImportConflictError,
)
from game_predictor_api.storage.job_repository import job_from_record
from game_predictor_api.storage.models import (
    CuratedImageImportBatchModel,
    CuratedImageImportSourceModel,
    JobModel,
)


class SqlAlchemyIterativeImageImportRepository(IterativeImageImportRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_source_by_run(
        self,
        image_selection_run_id: UUID,
    ) -> CuratedImageImportSource | None:
        record = self._session.scalar(
            select(CuratedImageImportSourceModel).where(
                CuratedImageImportSourceModel.image_selection_run_id == image_selection_run_id
            )
        )
        return None if record is None else _source_from_record(record)

    def get_source(self, source_id: UUID) -> CuratedImageImportSource | None:
        record = self._session.get(CuratedImageImportSourceModel, source_id)
        return None if record is None else _source_from_record(record)

    def get_source_for_update(self, source_id: UUID) -> CuratedImageImportSource | None:
        record = self._session.scalar(
            select(CuratedImageImportSourceModel)
            .where(CuratedImageImportSourceModel.id == source_id)
            .with_for_update()
        )
        return None if record is None else _source_from_record(record)

    def list_sources(self, *, game_id: UUID) -> list[CuratedImageImportSource]:
        records = self._session.scalars(
            select(CuratedImageImportSourceModel)
            .where(CuratedImageImportSourceModel.game_id == game_id)
            .order_by(
                CuratedImageImportSourceModel.created_at.desc(),
                CuratedImageImportSourceModel.id,
            )
        )
        return [_source_from_record(record) for record in records]

    def add_source(self, source: CuratedImageImportSource) -> CuratedImageImportSource:
        record = CuratedImageImportSourceModel(
            id=source.id,
            game_id=source.game_id,
            image_selection_run_id=source.image_selection_run_id,
            manifest_relative_path=source.manifest_relative_path,
            manifest_checksum_sha256=source.manifest_checksum_sha256,
            total_entries=source.total_entries,
            next_entry_index=source.next_entry_index,
            created_at=source.created_at,
            updated_at=source.updated_at,
        )
        self._session.add(record)
        self._flush()
        return _source_from_record(record)

    def save_source(self, source: CuratedImageImportSource) -> CuratedImageImportSource:
        record = self._session.get(CuratedImageImportSourceModel, source.id)
        if record is None:
            raise IterativeImageImportConflictError(
                "CURATED_IMAGE_IMPORT_SOURCE_NOT_FOUND",
                "The curated import source no longer exists.",
            )
        record.next_entry_index = source.next_entry_index
        record.updated_at = source.updated_at
        self._flush()
        return _source_from_record(record)

    def add_batch(self, batch: CuratedImageImportBatch) -> CuratedImageImportBatch:
        record = CuratedImageImportBatchModel(
            id=batch.id,
            source_id=batch.source_id,
            batch_number=batch.batch_number,
            start_index=batch.start_index,
            end_index=batch.end_index,
            job_id=batch.job.id,
            created_at=batch.created_at,
        )
        self._session.add(record)
        self._flush()
        return batch

    def list_batches(self, *, source_id: UUID) -> list[CuratedImageImportBatch]:
        rows = self._session.execute(
            select(CuratedImageImportBatchModel, JobModel)
            .join(JobModel, JobModel.id == CuratedImageImportBatchModel.job_id)
            .where(CuratedImageImportBatchModel.source_id == source_id)
            .order_by(
                CuratedImageImportBatchModel.batch_number,
                CuratedImageImportBatchModel.id,
            )
        )
        return [_batch_from_records(batch, job) for batch, job in rows]

    def next_batch_number(self, *, source_id: UUID) -> int:
        value = self._session.scalar(
            select(func.max(CuratedImageImportBatchModel.batch_number)).where(
                CuratedImageImportBatchModel.source_id == source_id
            )
        )
        return 1 if value is None else int(value) + 1

    def _flush(self) -> None:
        try:
            self._session.flush()
        except IntegrityError as error:
            raise IterativeImageImportConflictError(
                "CURATED_IMAGE_IMPORT_PERSISTENCE_CONFLICT",
                "Curated image import data conflicts with persisted state.",
            ) from error


def _source_from_record(record: CuratedImageImportSourceModel) -> CuratedImageImportSource:
    return CuratedImageImportSource(
        id=record.id,
        game_id=record.game_id,
        image_selection_run_id=record.image_selection_run_id,
        manifest_relative_path=record.manifest_relative_path,
        manifest_checksum_sha256=record.manifest_checksum_sha256,
        total_entries=record.total_entries,
        next_entry_index=record.next_entry_index,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _batch_from_records(
    batch: CuratedImageImportBatchModel,
    job: JobModel,
) -> CuratedImageImportBatch:
    return CuratedImageImportBatch(
        id=batch.id,
        source_id=batch.source_id,
        batch_number=batch.batch_number,
        start_index=batch.start_index,
        end_index=batch.end_index,
        job=job_from_record(job),
        created_at=batch.created_at,
    )


__all__ = ["SqlAlchemyIterativeImageImportRepository"]
