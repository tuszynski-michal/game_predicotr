"""Durable worker handler for full managed-storage inventory scans."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from game_predictor_api.application.image_storage import ImageArtifactStore
from game_predictor_api.domain.jobs import Job
from game_predictor_api.storage.models import StorageUsageSnapshotModel
from sqlalchemy import func, select
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
        inventory = self._store.inventory(
            database_size_bytes=None if database_size is None else int(database_size)
        )
        measured_at = context.now()
        with self._session_factory.begin() as session:
            for item in inventory.namespaces:
                session.add(
                    StorageUsageSnapshotModel(
                        id=uuid4(),
                        root_kind="import" if item.name == "staging" else "artifact",
                        namespace=item.name,
                        volume_id=next(
                            volume.key
                            for volume in inventory.volumes
                            if ("imports" if item.name == "staging" else "artifacts")
                            in volume.roots
                        ),
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
            for volume in inventory.volumes:
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
            if inventory.database_size_bytes is not None:
                session.add(
                    StorageUsageSnapshotModel(
                        id=uuid4(),
                        root_kind="database",
                        namespace="postgresql",
                        volume_id="postgresql",
                        measurement_source="database",
                        file_count=0,
                        size_bytes=inventory.database_size_bytes,
                        free_bytes=None,
                        total_bytes=None,
                        details={},
                        measured_at=measured_at,
                    )
                )
        context.checkpoint(
            checkpoint_payload={
                "checkpoint_kind": "storage-inventory-v1",
                "measured_at": measured_at.isoformat(),
                "schema_version": 1,
            },
            stage="storage_inventory_completed",
            current=len(inventory.namespaces),
            total=len(inventory.namespaces),
            success_count=len(inventory.namespaces),
            failure_count=0,
            review_count=0,
        )


__all__ = ["StorageInventoryHandler"]
