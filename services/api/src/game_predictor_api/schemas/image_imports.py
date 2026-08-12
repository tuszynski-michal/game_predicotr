"""HTTP schemas for controlled local image-folder imports."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from game_predictor_api.application.image_imports import (
    ImageSelectionPurpose,
    SelectedImageFolder,
)
from game_predictor_api.application.iterative_image_imports import (
    CuratedImageImportProgress,
)
from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.schemas.jobs import JobResponse


class ImageFolderSelectionResponse(ApiModel):
    status: Literal["selected", "cancelled"]
    selection_token: str | None = None
    path: str | None = None
    supported_file_count: int = 0
    expires_at: datetime | None = None
    purpose: ImageSelectionPurpose | None = None
    input_manifest_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )

    @classmethod
    def selected(cls, value: SelectedImageFolder) -> "ImageFolderSelectionResponse":
        return cls(
            status="selected",
            selection_token=value.selection_token,
            path=None if value.managed else str(value.path),
            supported_file_count=value.supported_file_count,
            expires_at=value.expires_at,
            purpose=value.purpose,
            input_manifest_sha256=value.input_manifest_sha256,
        )

    @classmethod
    def cancelled(cls) -> "ImageFolderSelectionResponse":
        return cls(status="cancelled")


class ImageFolderImportCreate(ApiModel):
    game_id: UUID
    selection_token: str = Field(min_length=32, max_length=200)


class ImageFolderImportResponse(ApiModel):
    job: JobResponse


class BrowserImageSelectionCreate(ApiModel):
    display_name: str = Field(min_length=1, max_length=200)
    expected_file_count: int = Field(ge=1, le=1_000_000)
    expected_total_bytes: int = Field(ge=1)
    purpose: ImageSelectionPurpose = ImageSelectionPurpose.LAYOUT_IMPORT
    game_id: UUID | None = None


class BrowserImageSelectionUploadResponse(ApiModel):
    upload_id: UUID
    expected_file_count: int
    uploaded_file_count: int
    uploaded_file_indexes: list[int]
    expected_total_bytes: int
    uploaded_bytes: int
    purpose: ImageSelectionPurpose
    game_id: UUID | None


class BrowserImageSelectionFileUploadResponse(ApiModel):
    upload_id: UUID
    expected_file_count: int
    uploaded_file_count: int
    expected_total_bytes: int
    uploaded_bytes: int


class CuratedImageImportSourceCreate(ApiModel):
    game_id: UUID
    image_selection_run_id: UUID


class CuratedImageImportBatchCreate(ApiModel):
    image_count: int = Field(default=10, ge=1, le=100_000)


class CuratedImageImportBatchResponse(ApiModel):
    id: UUID
    batch_number: int
    start_index: int
    end_index: int
    image_count: int
    job: JobResponse
    created_at: datetime


class CuratedImageImportSourceResponse(ApiModel):
    id: UUID
    game_id: UUID
    image_selection_run_id: UUID
    manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    total_entries: int
    reserved_entries: int
    processed_entries: int
    failed_entries: int
    remaining_entries: int
    next_entry_index: int
    batches: list[CuratedImageImportBatchResponse]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(
        cls,
        progress: CuratedImageImportProgress,
    ) -> "CuratedImageImportSourceResponse":
        source = progress.source
        return cls(
            id=source.id,
            game_id=source.game_id,
            image_selection_run_id=source.image_selection_run_id,
            manifest_checksum_sha256=source.manifest_checksum_sha256,
            total_entries=source.total_entries,
            reserved_entries=progress.reserved_entries,
            processed_entries=progress.processed_entries,
            failed_entries=progress.failed_entries,
            remaining_entries=progress.remaining_entries,
            next_entry_index=source.next_entry_index,
            batches=[
                CuratedImageImportBatchResponse(
                    id=batch.id,
                    batch_number=batch.batch_number,
                    start_index=batch.start_index,
                    end_index=batch.end_index,
                    image_count=batch.image_count,
                    job=JobResponse.from_domain(batch.job),
                    created_at=batch.created_at,
                )
                for batch in progress.batches
            ],
            created_at=source.created_at,
            updated_at=source.updated_at,
        )
