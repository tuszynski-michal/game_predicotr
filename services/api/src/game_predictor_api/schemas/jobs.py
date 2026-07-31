"""OpenAPI schemas for durable administrative jobs."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from game_predictor_api.domain.jobs import Job, JobStatus, JobType
from game_predictor_api.schemas.catalog import ApiModel


class ImportJobCreatePayload(ApiModel):
    schema_version: Literal[1] = 1
    source_path: str = Field(min_length=1, max_length=500)
    contract_version: Literal[1] = 1


class ImportJobPayload(ApiModel):
    schema_version: Literal[1] = 1
    import_kind: Literal["layout_file"]
    source_path: str = Field(min_length=1, max_length=500)
    source_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_size_bytes: int = Field(ge=1)
    file_format: Literal["csv", "jsonl"]
    contract_version: Literal[1]


class ImageImportJobPayload(ApiModel):
    schema_version: Literal[1] = 1
    import_kind: Literal["image_directory"]
    source_selection_id: UUID | None = None
    source_directory: str | None = Field(default=None, min_length=1, max_length=2048)
    source_display_name: str | None = Field(default=None, min_length=1, max_length=255)
    pipeline_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ValidateJobPayload(ApiModel):
    schema_version: Literal[1] = 1
    dataset_version_id: UUID


class LayoutImportValidateJobPayload(ApiModel):
    schema_version: Literal[1] = 1
    validation_kind: Literal["layout_import"]
    import_job_id: UUID
    rules_version_id: UUID


class PayoutJobPayload(ApiModel):
    schema_version: Literal[1] = 1
    dataset_version_id: UUID
    rules_version_id: UUID
    algorithm_version: str = Field(min_length=1, max_length=100)


class SnapshotJobPayload(ApiModel):
    schema_version: Literal[1] = 1
    mobile_release_id: UUID


class AndroidBuildJobPayload(ApiModel):
    schema_version: Literal[1] = 1
    mobile_release_id: UUID


class ImportJobCreate(ApiModel):
    job_type: Literal[JobType.IMPORT]
    game_id: UUID
    input_payload: ImportJobCreatePayload


class ValidateJobCreate(ApiModel):
    job_type: Literal[JobType.VALIDATE]
    game_id: UUID
    input_payload: ValidateJobPayload | LayoutImportValidateJobPayload


class PayoutJobCreate(ApiModel):
    job_type: Literal[JobType.PAYOUT]
    game_id: UUID
    input_payload: PayoutJobPayload


class SnapshotJobCreate(ApiModel):
    job_type: Literal[JobType.SNAPSHOT]
    game_id: UUID | None = None
    input_payload: SnapshotJobPayload


class AndroidBuildJobCreate(ApiModel):
    job_type: Literal[JobType.ANDROID_BUILD]
    game_id: UUID | None = None
    input_payload: AndroidBuildJobPayload


JobCreateRequest = Annotated[
    ImportJobCreate
    | ValidateJobCreate
    | PayoutJobCreate
    | SnapshotJobCreate
    | AndroidBuildJobCreate,
    Field(discriminator="job_type"),
]

JobPayloadResponse = (
    ImportJobPayload
    | ImageImportJobPayload
    | ValidateJobPayload
    | LayoutImportValidateJobPayload
    | PayoutJobPayload
    | SnapshotJobPayload
    | AndroidBuildJobPayload
)


class JobProgressResponse(ApiModel):
    current: int
    total: int | None
    stage: str | None
    succeeded: int
    failed: int
    review: int


class JobErrorResponse(ApiModel):
    code: str
    message: str


class JobResponse(ApiModel):
    id: UUID
    job_type: JobType
    game_id: UUID | None
    status: JobStatus
    input_payload: JobPayloadResponse
    progress: JobProgressResponse
    error: JobErrorResponse | None
    worker_version: str | None
    attempt_count: int
    heartbeat_at: datetime | None
    lease_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    cancel_requested_at: datetime | None

    @classmethod
    def from_domain(cls, job: Job) -> JobResponse:
        error = None
        if job.error_code is not None and job.error_message is not None:
            error = JobErrorResponse(
                code=job.error_code,
                message=job.error_message,
            )
        return cls(
            id=job.id,
            job_type=job.job_type,
            game_id=job.game_id,
            status=job.status,
            input_payload=_payload_from_domain(job),
            progress=JobProgressResponse(
                current=job.progress_current,
                total=job.progress_total,
                stage=job.stage,
                succeeded=job.success_count,
                failed=job.failure_count,
                review=job.review_count,
            ),
            error=error,
            worker_version=job.worker_version,
            attempt_count=job.attempt_count,
            heartbeat_at=job.heartbeat_at,
            lease_expires_at=job.lease_expires_at,
            created_at=job.created_at,
            updated_at=job.updated_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            cancel_requested_at=job.cancel_requested_at,
        )


def _payload_from_domain(job: Job) -> JobPayloadResponse:
    if job.job_type is JobType.IMPORT:
        if job.input_payload.get("import_kind") == "image_directory":
            return ImageImportJobPayload.model_validate(job.input_payload)
        return ImportJobPayload.model_validate(job.input_payload)
    if job.job_type is JobType.VALIDATE:
        if job.input_payload.get("validation_kind") == "layout_import":
            return LayoutImportValidateJobPayload.model_validate(job.input_payload)
        return ValidateJobPayload.model_validate(job.input_payload)
    if job.job_type is JobType.PAYOUT:
        return PayoutJobPayload.model_validate(job.input_payload)
    if job.job_type is JobType.SNAPSHOT:
        return SnapshotJobPayload.model_validate(job.input_payload)
    return AndroidBuildJobPayload.model_validate(job.input_payload)
