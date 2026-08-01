"""HTTP schemas for controlled local image-folder imports."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from game_predictor_api.application.image_imports import SelectedImageFolder
from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.schemas.jobs import JobResponse


class ImageFolderSelectionResponse(ApiModel):
    status: Literal["selected", "cancelled"]
    selection_token: str | None = None
    path: str | None = None
    supported_file_count: int = 0
    expires_at: datetime | None = None

    @classmethod
    def selected(cls, value: SelectedImageFolder) -> "ImageFolderSelectionResponse":
        return cls(
            status="selected",
            selection_token=value.selection_token,
            path=str(value.path),
            supported_file_count=value.supported_file_count,
            expires_at=value.expires_at,
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


class BrowserImageSelectionUploadResponse(ApiModel):
    upload_id: UUID
    expected_file_count: int
    uploaded_file_count: int
    expected_total_bytes: int
    uploaded_bytes: int
