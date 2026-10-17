"""OpenAPI schemas of source crop and original-deletion runs (TASK-1047, D-562)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from game_predictor_api.application.source_crop_runs import (
    MAX_SCOPE_CHECKSUMS,
    SourceCropRun,
    SourceCropScope,
)
from game_predictor_api.schemas.catalog import ApiModel

SHA256_PATTERN = r"^[0-9a-f]{64}$"


class SourceCropScopeModel(ApiModel):
    game_id: UUID | None = None
    only_checksums: list[str] | None = Field(
        default=None, min_length=1, max_length=MAX_SCOPE_CHECKSUMS
    )
    limit: int | None = Field(default=None, ge=1, le=1_000_000)

    def to_domain(self) -> SourceCropScope:
        return SourceCropScope(
            game_id=self.game_id,
            only_checksums=None if self.only_checksums is None else tuple(self.only_checksums),
            limit=self.limit,
        )


class SourceCropPreviewCreate(ApiModel):
    kind: Literal["crop", "original_deletion"] = "crop"
    scope: SourceCropScopeModel = Field(default_factory=SourceCropScopeModel)


class SourceCropRunStart(ApiModel):
    manifest_checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    preview_token: str = Field(pattern=SHA256_PATTERN)
    confirmed: bool
    acknowledge_irreversible: bool = False


class SourceCropFailureResponse(ApiModel):
    checksum_sha256: str
    code: str
    message: str


class SourceCropRunResponse(ApiModel):
    id: UUID
    kind: Literal["crop", "original_deletion"]
    status: Literal[
        "planning", "previewed", "created", "processing", "completed", "failed", "cancelled"
    ]
    scope: SourceCropScopeModel
    plan_job_id: UUID
    job_id: UUID | None
    manifest_checksum_sha256: str | None
    preview_token: str | None
    eligible_count: int
    excluded_count: int
    exclusion_counts: dict[str, int]
    candidate_bytes: int
    estimated_saved_bytes: int
    processed_count: int
    succeeded_count: int
    skipped_count: int
    failed_count: int
    saved_bytes: int
    checkpoint_index: int
    outcome_counts: dict[str, int]
    failures: list[SourceCropFailureResponse]
    error_code: str | None
    error_message: str | None
    created_at: datetime | None
    updated_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_domain(cls, value: SourceCropRun) -> SourceCropRunResponse:
        return cls(
            id=value.id,
            kind=value.kind,  # type: ignore[arg-type]
            status=value.status,  # type: ignore[arg-type]
            scope=SourceCropScopeModel(
                game_id=value.scope.game_id,
                only_checksums=None
                if value.scope.only_checksums is None
                else list(value.scope.only_checksums),
                limit=value.scope.limit,
            ),
            plan_job_id=value.plan_job_id,
            job_id=value.job_id,
            manifest_checksum_sha256=value.manifest_checksum_sha256,
            preview_token=value.preview_token,
            eligible_count=value.eligible_count,
            excluded_count=value.excluded_count,
            exclusion_counts=dict(value.exclusion_counts),
            candidate_bytes=value.candidate_bytes,
            estimated_saved_bytes=value.estimated_saved_bytes,
            processed_count=value.processed_count,
            succeeded_count=value.succeeded_count,
            skipped_count=value.skipped_count,
            failed_count=value.failed_count,
            saved_bytes=value.saved_bytes,
            checkpoint_index=value.checkpoint_index,
            outcome_counts=dict(value.outcome_counts),
            failures=[
                SourceCropFailureResponse(
                    checksum_sha256=str(item.get("checksumSha256", "")),
                    code=str(item.get("code", "")),
                    message=str(item.get("message", "")),
                )
                for item in value.failures
            ],
            error_code=value.error_code,
            error_message=value.error_message,
            created_at=value.created_at,
            updated_at=value.updated_at,
            started_at=value.started_at,
            finished_at=value.finished_at,
        )


class SourceCropRunListResponse(ApiModel):
    runs: list[SourceCropRunResponse]


__all__ = [
    "SourceCropPreviewCreate",
    "SourceCropRunListResponse",
    "SourceCropRunResponse",
    "SourceCropRunStart",
    "SourceCropScopeModel",
]
