"""SQL persistence and dependency queries for managed storage GC."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_api.application.storage_gc import (
    BrowserStagingGcSource,
    StorageGcPreview,
    StorageGcRun,
)
from game_predictor_api.domain.jobs import (
    JobConflictError,
    JobNotFoundError,
    JobType,
    create_job,
)
from game_predictor_api.domain.storage_retention import StorageRetentionPolicy

from .job_repository import SqlAlchemyJobRepository
from .models import (
    BrowserSelectionRetentionModel,
    ImageImportJobFileModel,
    JobModel,
    StorageGcRunModel,
)


class SqlAlchemyStorageGcRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def normalization_dependency_statuses(
        self, execution_keys: Sequence[str]
    ) -> Mapping[str, tuple[str, ...]]:
        if not execution_keys:
            return {}
        grouped: dict[str, set[str]] = defaultdict(set)
        with self._session_factory() as session:
            for offset in range(0, len(execution_keys), 5_000):
                batch = execution_keys[offset : offset + 5_000]
                rows = session.execute(
                    select(
                        ImageImportJobFileModel.file_execution_key,
                        JobModel.status,
                    )
                    .join(JobModel, JobModel.id == ImageImportJobFileModel.job_id)
                    .where(ImageImportJobFileModel.file_execution_key.in_(batch))
                )
                for key, status in rows:
                    grouped[key].add(status.value)
        return {
            key: tuple(sorted(statuses))
            for key, statuses in grouped.items()
        }

    def browser_staging_sources(self) -> Sequence[BrowserStagingGcSource]:
        with self._session_factory() as session:
            states = session.scalars(select(BrowserSelectionRetentionModel)).all()
            jobs = session.scalars(
                select(JobModel).where(
                    JobModel.job_type.in_((JobType.IMPORT, JobType.VALIDATE))
                )
            ).all()
        by_upload: dict[str, set[str]] = defaultdict(set)
        for job in jobs:
            upload_id = job.input_payload.get("source_selection_id")
            if isinstance(upload_id, str):
                by_upload[upload_id].add(job.status.value)
        return tuple(
            BrowserStagingGcSource(
                upload_id=row.upload_id,
                relative_path=f"browser-selections/{row.upload_id}",
                finalized_at=row.finalized_at,
                last_dependency_at=row.last_dependency_at,
                linked_import_exists=row.import_job_id is not None,
                managed_originals_verified=(
                    row.managed_manifest_relative_path is not None
                    and row.managed_manifest_checksum_sha256 is not None
                ),
                dependency_job_statuses=tuple(
                    sorted(by_upload.get(str(row.upload_id), set()))
                ),
                managed_manifest_relative_path=row.managed_manifest_relative_path,
                managed_manifest_checksum_sha256=row.managed_manifest_checksum_sha256,
            )
            for row in states
        )

    def create_preview(
        self,
        *,
        preview_id: UUID,
        mode: str,
        policy: StorageRetentionPolicy,
        manifest_relative_path: str,
        manifest_checksum_sha256: str,
        preview_token: str,
        candidate_count: int,
        candidate_bytes: int,
        protected_count: int,
        protected_bytes: int,
        inventory_before: Mapping[str, object],
        created_at: datetime,
    ) -> StorageGcPreview:
        with self._session_factory.begin() as session:
            row = StorageGcRunModel(
                id=preview_id,
                job_id=None,
                mode=mode,
                status="previewed",
                policy_version=policy.version,
                retention_hours=int(policy.retention.total_seconds() // 3600),
                manifest_relative_path=manifest_relative_path,
                manifest_checksum_sha256=manifest_checksum_sha256,
                preview_token=preview_token,
                candidate_count=candidate_count,
                candidate_bytes=candidate_bytes,
                protected_count=protected_count,
                protected_bytes=protected_bytes,
                deleted_count=0,
                deleted_bytes=0,
                conflict_count=0,
                failed_count=0,
                checkpoint_index=0,
                inventory_before=dict(inventory_before),
                inventory_after=None,
                error_code=None,
                error_message=None,
                created_at=created_at,
                updated_at=created_at,
            )
            session.add(row)
        return _preview(row)

    def start_run(
        self,
        *,
        preview_id: UUID,
        expected_manifest_checksum_sha256: str,
        expected_preview_token: str,
        mode: str,
    ) -> StorageGcRun:
        with self._session_factory.begin() as session:
            row = session.get(StorageGcRunModel, preview_id, with_for_update=True)
            if row is None:
                raise JobNotFoundError(
                    "STORAGE_GC_PREVIEW_NOT_FOUND", "The storage GC preview does not exist."
                )
            if (
                row.manifest_checksum_sha256 != expected_manifest_checksum_sha256
                or row.preview_token != expected_preview_token
            ):
                raise JobConflictError(
                    "STORAGE_GC_PREVIEW_STALE",
                    "The storage GC preview token or checksum is stale.",
                )
            if row.job_id is not None:
                return _run(row)
            if row.status != "previewed" or row.mode != mode:
                raise JobConflictError(
                    "STORAGE_GC_PREVIEW_STALE", "The storage GC preview is no longer startable."
                )
            job = create_job(
                JobType.STORAGE_GC,
                game_id=None,
                input_payload={
                    "schema_version": 1,
                    "storage_gc_run_id": str(row.id),
                    "policy_version": row.policy_version,
                    "manifest_checksum_sha256": row.manifest_checksum_sha256,
                    "mode": row.mode,
                },
                created_at=row.created_at,
            )
            SqlAlchemyJobRepository(session).add_job(job)
            row.job_id = job.id
            row.status = "created"
            row.updated_at = job.created_at
        return _run(row)

    def get_run(self, run_id: UUID) -> StorageGcRun:
        with self._session_factory() as session:
            row = session.get(StorageGcRunModel, run_id)
            if row is None:
                raise JobNotFoundError(
                    "STORAGE_GC_RUN_NOT_FOUND", "The storage GC run does not exist."
                )
            return _run(row)


def _preview(row: StorageGcRunModel) -> StorageGcPreview:
    free = 0
    if row.inventory_before is not None:
        value = row.inventory_before.get("freeBytes")
        if isinstance(value, int):
            free = value
    return StorageGcPreview(
        id=row.id,
        status=row.status,
        mode=row.mode,
        policy_version=row.policy_version,
        retention_hours=row.retention_hours,
        manifest_relative_path=row.manifest_relative_path,
        manifest_checksum_sha256=row.manifest_checksum_sha256,
        preview_token=row.preview_token,
        candidate_count=row.candidate_count,
        candidate_bytes=row.candidate_bytes,
        protected_count=row.protected_count,
        protected_bytes=row.protected_bytes,
        predicted_free_bytes=free + row.candidate_bytes,
        category_counts=_nested_counters(row.inventory_before, "categoryCounts"),
        protection_reason_counts=_nested_counters(
            row.inventory_before, "protectionReasonCounts"
        ),
        created_at=row.created_at,
    )


def _nested_counters(
    payload: Mapping[str, object] | None, key: str
) -> dict[str, dict[str, int]]:
    if payload is None:
        return {}
    raw_counters = payload.get(key)
    if not isinstance(raw_counters, Mapping):
        return {}
    result: dict[str, dict[str, int]] = {}
    for name, raw in raw_counters.items():
        if not isinstance(name, str) or not isinstance(raw, Mapping):
            continue
        count = raw.get("count")
        size = raw.get("bytes")
        if isinstance(count, int) and isinstance(size, int):
            result[name] = {"count": count, "bytes": size}
    return result


def _run(row: StorageGcRunModel) -> StorageGcRun:
    return StorageGcRun(
        id=row.id,
        job_id=row.job_id,
        status=row.status,
        mode=row.mode,
        candidate_count=row.candidate_count,
        candidate_bytes=row.candidate_bytes,
        protected_count=row.protected_count,
        protected_bytes=row.protected_bytes,
        deleted_count=row.deleted_count,
        deleted_bytes=row.deleted_bytes,
        conflict_count=row.conflict_count,
        failed_count=row.failed_count,
        checkpoint_index=row.checkpoint_index,
        error_code=row.error_code,
        error_message=row.error_message,
        created_at=row.created_at,
        updated_at=row.updated_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


__all__ = ["SqlAlchemyStorageGcRepository"]
