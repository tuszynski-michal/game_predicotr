"""OpenAPI schemas for image-job operational details."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from game_predictor_api.application.image_jobs import ImageJobOperations
from game_predictor_api.schemas.catalog import ApiModel


class ImageJobStageCountResponse(ApiModel):
    stage: str
    count: int


class ImageJobFileErrorResponse(ApiModel):
    code: str
    message: str


class ImageJobFileResponse(ApiModel):
    file_execution_key: str
    order_index: int
    source_relative_path: str
    status: str
    next_stage: str | None
    failed_stage: str | None
    error: ImageJobFileErrorResponse | None
    retry_count: int
    review_required: bool
    updated_at: datetime


class ImageJobOperationsResponse(ApiModel):
    job_id: UUID
    pipeline_fingerprint: str
    total: int
    current: int
    succeeded: int
    failed: int
    review: int
    waiting: int
    elapsed_seconds: float | None
    files_per_minute: float | None
    stage_counts: list[ImageJobStageCountResponse]
    files: list[ImageJobFileResponse]
    file_limit: int
    has_more_files: bool

    @classmethod
    def from_domain(
        cls,
        value: ImageJobOperations,
    ) -> ImageJobOperationsResponse:
        return cls(
            job_id=value.job_id,
            pipeline_fingerprint=value.pipeline_fingerprint,
            total=value.total,
            current=value.current,
            succeeded=value.succeeded,
            failed=value.failed,
            review=value.review,
            waiting=value.waiting,
            elapsed_seconds=value.elapsed_seconds,
            files_per_minute=value.files_per_minute,
            stage_counts=[
                ImageJobStageCountResponse(stage=item.stage, count=item.count)
                for item in value.stage_counts
            ],
            files=[
                ImageJobFileResponse(
                    file_execution_key=item.file_execution_key,
                    order_index=item.order_index,
                    source_relative_path=item.source_relative_path,
                    status=item.status,
                    next_stage=item.next_stage,
                    failed_stage=item.failed_stage,
                    error=(
                        None
                        if item.error_code is None or item.error_message is None
                        else ImageJobFileErrorResponse(
                            code=item.error_code,
                            message=item.error_message,
                        )
                    ),
                    retry_count=item.retry_count,
                    review_required=item.review_required,
                    updated_at=item.updated_at,
                )
                for item in value.files
            ],
            file_limit=value.file_limit,
            has_more_files=value.has_more_files,
        )


class ImageJobFileRetryRequest(ApiModel):
    expected_stage: str = Field(min_length=1, max_length=40)


__all__ = [
    "ImageJobFileRetryRequest",
    "ImageJobOperationsResponse",
]
