"""Durable worker handler for full managed-storage inventory scans."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from game_predictor_api.application.image_storage import (
    MANAGED_STORAGE_NAMESPACES,
    ImageArtifactStore,
    ImageStorageNamespace,
)
from game_predictor_api.domain.jobs import Job
from game_predictor_api.storage.models import StorageUsageSnapshotModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError


class StorageInventoryHandler:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        artifact_root: Path,
        import_root: Path,
    ) -> None:
        self._session_factory = session_factory
        self._store = ImageArtifactStore(artifact_root, import_root)

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        if job.input_payload.get("inventory_kind") != "managed_image_storage":
            raise JobHandlerError(
                "STORAGE_INVENTORY_PAYLOAD_INVALID",
                "The storage inventory payload is invalid.",
            )
        with self._session_factory() as session:
            database_size = session.scalar(select(func.pg_database_size(func.current_database())))
        checkpoint = job.checkpoint_payload or {}
        measured_at_value = checkpoint.get("measured_at")
        measured_at = (
            datetime.fromisoformat(measured_at_value)
            if isinstance(measured_at_value, str)
            else context.now()
        )
        next_index_value = checkpoint.get("next_namespace_index", 0)
        next_index = next_index_value if isinstance(next_index_value, int) else 0
        if not 0 <= next_index <= len(MANAGED_STORAGE_NAMESPACES):
            raise JobHandlerError(
                "STORAGE_INVENTORY_CHECKPOINT_INVALID",
                "The storage inventory checkpoint is invalid.",
            )
        volumes = self._store.volumes()
        for index in range(next_index, len(MANAGED_STORAGE_NAMESPACES)):
            item = self._store.namespace_inventory(MANAGED_STORAGE_NAMESPACES[index])
            self._save_namespace(
                item,
                measured_at=measured_at,
                volume_id=next(
                    volume.key
                    for volume in volumes
                    if ("imports" if item.name == "staging" else "artifacts") in volume.roots
                ),
            )
            context.checkpoint(
                checkpoint_payload={
                    "checkpoint_kind": "storage-inventory-v2",
                    "measured_at": measured_at.isoformat(),
                    "next_namespace_index": index + 1,
                    "schema_version": 1,
                },
                stage=f"storage_inventory:{item.name}",
                current=index + 1,
                total=len(MANAGED_STORAGE_NAMESPACES) + 1,
                success_count=index + 1,
                failure_count=0,
                review_count=0,
            )
        with self._session_factory.begin() as session:
            session.execute(
                delete(StorageUsageSnapshotModel).where(
                    StorageUsageSnapshotModel.measured_at == measured_at,
                    StorageUsageSnapshotModel.measurement_source.in_(("filesystem", "database")),
                )
            )
            for volume in volumes:
                session.add(
                    StorageUsageSnapshotModel(
                        id=uuid4(),
                        root_kind="artifact" if "artifacts" in volume.roots else "import",
                        namespace=None,
                        volume_id=volume.key,
                        measurement_source="filesystem",
                        file_count=0,
                        size_bytes=0,
                        free_bytes=volume.free_bytes,
                        total_bytes=volume.total_bytes,
                        details={"roots": list(volume.roots)},
                        measured_at=measured_at,
                    )
                )
            if database_size is not None:
                session.add(
                    StorageUsageSnapshotModel(
                        id=uuid4(),
                        root_kind="database",
                        namespace="postgresql",
                        volume_id="postgresql",
                        measurement_source="database",
                        file_count=0,
                        size_bytes=int(database_size),
                        free_bytes=None,
                        total_bytes=None,
                        details={},
                        measured_at=measured_at,
                    )
                )
        context.checkpoint(
            checkpoint_payload={
                "checkpoint_kind": "storage-inventory-v2",
                "measured_at": measured_at.isoformat(),
                "next_namespace_index": len(MANAGED_STORAGE_NAMESPACES),
                "schema_version": 1,
            },
            stage="storage_inventory_completed",
            current=len(MANAGED_STORAGE_NAMESPACES) + 1,
            total=len(MANAGED_STORAGE_NAMESPACES) + 1,
            success_count=len(MANAGED_STORAGE_NAMESPACES),
            failure_count=0,
            review_count=0,
        )

    def _save_namespace(
        self,
        item: ImageStorageNamespace,
        *,
        measured_at: datetime,
        volume_id: str,
    ) -> None:
        with self._session_factory.begin() as session:
            session.execute(
                delete(StorageUsageSnapshotModel).where(
                    StorageUsageSnapshotModel.measured_at == measured_at,
                    StorageUsageSnapshotModel.measurement_source == "scan",
                    StorageUsageSnapshotModel.namespace == item.name,
                )
            )
            session.add(
                StorageUsageSnapshotModel(
                    id=uuid4(),
                    root_kind="import" if item.name == "staging" else "artifact",
                    namespace=item.name,
                    volume_id=volume_id,
                    measurement_source="scan",
                    file_count=item.file_count,
                    size_bytes=item.size_bytes,
                    free_bytes=None,
                    total_bytes=None,
                    details={
                        "ignoredSymlinkCount": item.ignored_symlink_count,
                        "protected": item.protected,
                        "retentionPolicy": item.retention_policy,
                    },
                    measured_at=measured_at,
                )
            )


__all__ = ["StorageInventoryHandler"]
