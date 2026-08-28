"""OpenAPI schemas for managed image storage and diagnostic exports."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from game_predictor_api.application.image_storage import (
    ImageDiagnosticExport,
    ImageDiagnosticExportCreation,
    ImageStorageInventory,
)
from game_predictor_api.application.storage_gc import StorageGcPreview, StorageGcRun
from game_predictor_api.schemas.catalog import ApiModel


class ImageStorageNamespaceResponse(ApiModel):
    name: str
    retention_policy: str
    protected: bool
    exists: bool
    file_count: int
    size_bytes: int
    ignored_symlink_count: int


class ImageStorageInventoryResponse(ApiModel):
    root_name: str
    automatic_deletion: bool
    total_file_count: int
    total_size_bytes: int
    namespaces: list[ImageStorageNamespaceResponse]
    measured_at: datetime
    volumes: list[ImageStorageVolumeResponse]
    database_size_bytes: int | None
    wal_size_bytes: int | None

    @classmethod
    def from_domain(
        cls,
        value: ImageStorageInventory,
    ) -> ImageStorageInventoryResponse:
        return cls(
            root_name=value.root_name,
            automatic_deletion=value.automatic_deletion,
            total_file_count=value.total_file_count,
            total_size_bytes=value.total_size_bytes,
            namespaces=[
                ImageStorageNamespaceResponse(
                    name=item.name,
                    retention_policy=item.retention_policy,
                    protected=item.protected,
                    exists=item.exists,
                    file_count=item.file_count,
                    size_bytes=item.size_bytes,
                    ignored_symlink_count=item.ignored_symlink_count,
                )
                for item in value.namespaces
            ],
            measured_at=value.measured_at,
            volumes=[
                ImageStorageVolumeResponse(
                    key=item.key,
                    roots=list(item.roots),
                    total_bytes=item.total_bytes,
                    free_bytes=item.free_bytes,
                )
                for item in value.volumes
            ],
            database_size_bytes=value.database_size_bytes,
            wal_size_bytes=value.wal_size_bytes,
        )


class ImageStorageVolumeResponse(ApiModel):
    key: str
    roots: list[str]
    total_bytes: int
    free_bytes: int


class StorageGcPreviewResponse(ApiModel):
    id: UUID
    status: str
    mode: str
    policy_version: str
    retention_hours: int
    manifest_relative_path: str
    manifest_checksum_sha256: str
    preview_token: str
    candidate_count: int
    candidate_bytes: int
    protected_count: int
    protected_bytes: int
    predicted_free_bytes: int
    category_counts: dict[str, dict[str, int]]
    protection_reason_counts: dict[str, dict[str, int]]
    created_at: datetime

    @classmethod
    def from_domain(cls, value: StorageGcPreview) -> StorageGcPreviewResponse:
        return (
            cls(**value.__dict__)
            if hasattr(value, "__dict__")
            else cls(**{field: getattr(value, field) for field in cls.model_fields})
        )


class StorageGcRunCreate(ApiModel):
    preview_id: UUID
    manifest_checksum_sha256: str
    preview_token: str
    confirmed: bool


class StorageGcRunResponse(ApiModel):
    id: UUID
    job_id: UUID | None
    status: str
    mode: str
    candidate_count: int
    candidate_bytes: int
    protected_count: int
    protected_bytes: int
    deleted_count: int
    deleted_bytes: int
    conflict_count: int
    failed_count: int
    checkpoint_index: int
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_domain(cls, value: StorageGcRun) -> StorageGcRunResponse:
        return cls(**{field: getattr(value, field) for field in cls.model_fields})


class ImageDiagnosticExportResponse(ApiModel):
    job_id: UUID
    checksum_sha256: str
    relative_path: str
    size_bytes: int
    source_updated_at: datetime
    error_count: int
    exported_error_count: int
    truncated: bool

    @classmethod
    def from_domain(
        cls,
        value: ImageDiagnosticExport,
    ) -> ImageDiagnosticExportResponse:
        return cls(
            job_id=value.job_id,
            checksum_sha256=value.checksum_sha256,
            relative_path=value.relative_path,
            size_bytes=value.size_bytes,
            source_updated_at=value.source_updated_at,
            error_count=value.error_count,
            exported_error_count=value.exported_error_count,
            truncated=value.truncated,
        )


class ImageDiagnosticExportCreationResponse(ApiModel):
    created: bool
    export: ImageDiagnosticExportResponse

    @classmethod
    def from_domain(
        cls,
        value: ImageDiagnosticExportCreation,
    ) -> ImageDiagnosticExportCreationResponse:
        return cls(
            created=value.created,
            export=ImageDiagnosticExportResponse.from_domain(value.export),
        )


__all__ = [
    "ImageDiagnosticExportCreationResponse",
    "ImageDiagnosticExportResponse",
    "ImageStorageInventoryResponse",
    "StorageGcPreviewResponse",
    "StorageGcRunCreate",
    "StorageGcRunResponse",
]
