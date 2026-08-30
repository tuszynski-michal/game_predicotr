"""HTTP schemas for controlled local image-folder imports."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from game_predictor_api.application.image_imports import (
    BrowserReadySelection,
    ImageSelectionPurpose,
    SelectedImageFolder,
)
from game_predictor_api.application.iterative_image_imports import (
    CuratedImageImportProgress,
)
from game_predictor_api.domain.image_import_engine_policy import ImageImportEnginePolicy
from game_predictor_api.domain.image_sequence_canonical import ImageSequenceImportPreflight
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


class ImageSequenceImportPreflightResponse(ApiModel):
    game_id: UUID
    source_file_count: int = Field(ge=0)
    attested_file_count: int = Field(ge=0)
    new_sequence_count: int = Field(ge=0)
    reused_sequence_count: int = Field(ge=0)
    skipped_source_count: int = Field(ge=0)
    partial_source_count: int = Field(ge=0)
    alternative_source_count: int = Field(ge=0)
    first_unresolved_sequence: int | None = Field(default=None, ge=1)
    last_unresolved_sequence: int | None = Field(default=None, ge=1)
    warnings: list[str]

    @classmethod
    def from_domain(
        cls,
        value: ImageSequenceImportPreflight,
    ) -> "ImageSequenceImportPreflightResponse":
        return cls(
            game_id=value.game_id,
            source_file_count=value.source_file_count,
            attested_file_count=value.attested_file_count,
            new_sequence_count=value.new_sequence_count,
            reused_sequence_count=value.reused_sequence_count,
            skipped_source_count=value.skipped_source_count,
            partial_source_count=value.partial_source_count,
            alternative_source_count=value.alternative_source_count,
            first_unresolved_sequence=value.first_unresolved_sequence,
            last_unresolved_sequence=value.last_unresolved_sequence,
            warnings=list(value.warnings),
        )


class BrowserReadySelectionResponse(ApiModel):
    upload_id: UUID
    display_name: str
    expected_file_count: int = Field(ge=1)
    expected_total_bytes: int = Field(ge=1)
    uploaded_file_count: int = Field(ge=0)
    uploaded_bytes: int = Field(ge=0)
    purpose: ImageSelectionPurpose
    game_id: UUID | None
    created_at: datetime
    completed_at: datetime | None
    manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def from_domain(cls, value: BrowserReadySelection) -> "BrowserReadySelectionResponse":
        upload = value.upload
        return cls(
            upload_id=upload.upload_id,
            display_name=upload.display_name,
            expected_file_count=upload.expected_file_count,
            expected_total_bytes=upload.expected_total_bytes,
            uploaded_file_count=len(upload.uploaded_indexes),
            uploaded_bytes=upload.uploaded_bytes,
            purpose=upload.purpose,
            game_id=upload.game_id,
            created_at=upload.created_at,
            completed_at=value.completed_at,
            manifest_checksum_sha256=value.manifest.checksum_sha256,
        )


class BrowserImageImportPreflightCreate(ApiModel):
    game_id: UUID


class BrowserImageImportPreflightResponse(ImageSequenceImportPreflightResponse):
    upload_id: UUID
    display_name: str
    manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    preflight_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    symbol_model_inference_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    grid_profile_inference_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    image_engine_policy: ImageImportEnginePolicy
    image_engine_policy_revision: int = Field(ge=0)
    geometry_preflight_required: bool


class BrowserPageGeometryPreflightResponse(ApiModel):
    created: bool
    job: JobResponse


class BrowserPageGeometryReviewSourceResponse(ApiModel):
    source_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_relative_path: str = Field(min_length=1, max_length=2048)
    sequence_range_start: int | None = Field(default=None, ge=1)
    sequence_range_end: int | None = Field(default=None, ge=1)


class BrowserPageGeometryReviewSourcesResponse(ApiModel):
    job: JobResponse
    geometry_manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    registered_source_count: int = Field(ge=0)
    review_required_source_count: int = Field(ge=0)
    skipped_human_resolved_source_count: int = Field(ge=0)
    sources: list[BrowserPageGeometryReviewSourceResponse]


class PageGeometryPoint(ApiModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class BrowserPageGeometryOverrideCreate(ApiModel):
    game_id: UUID
    source_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    image_width: int = Field(ge=1)
    image_height: int = Field(ge=1)
    final_quads: tuple[
        tuple[PageGeometryPoint, PageGeometryPoint, PageGeometryPoint, PageGeometryPoint],
        tuple[PageGeometryPoint, PageGeometryPoint, PageGeometryPoint, PageGeometryPoint],
        tuple[PageGeometryPoint, PageGeometryPoint, PageGeometryPoint, PageGeometryPoint],
        tuple[PageGeometryPoint, PageGeometryPoint, PageGeometryPoint, PageGeometryPoint],
        tuple[PageGeometryPoint, PageGeometryPoint, PageGeometryPoint, PageGeometryPoint],
        tuple[PageGeometryPoint, PageGeometryPoint, PageGeometryPoint, PageGeometryPoint],
        tuple[PageGeometryPoint, PageGeometryPoint, PageGeometryPoint, PageGeometryPoint],
        tuple[PageGeometryPoint, PageGeometryPoint, PageGeometryPoint, PageGeometryPoint],
        tuple[PageGeometryPoint, PageGeometryPoint, PageGeometryPoint, PageGeometryPoint],
    ]
    actor: str = Field(min_length=1, max_length=200)


class BrowserPageGeometryOverrideResponse(ApiModel):
    created: bool
    id: UUID
    revision: int = Field(ge=1)
    decision_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class BrowserImageImportStart(ApiModel):
    game_id: UUID
    manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    preflight_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    start_mode: Literal["reuse_exact", "rerun_current_models"] = "reuse_exact"
    symbol_model_inference_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    grid_profile_inference_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    geometry_preflight_job_id: UUID | None = None
    geometry_manifest_checksum_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    board_cell_processing_mode: Literal["verified_v19", "structured_shadow"] | None = None
    image_engine_policy: ImageImportEnginePolicy | None = None
    image_engine_policy_revision: int | None = Field(default=None, ge=0)


class BrowserImageImportStartResponse(ApiModel):
    created: bool
    job: JobResponse
    preflight: BrowserImageImportPreflightResponse


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
