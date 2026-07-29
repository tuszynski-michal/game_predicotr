"""OpenAPI schemas for immutable verified review cohort exports."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import Field

from game_predictor_api.domain.image_review_cohorts import ImageVerifiedCohortExport
from game_predictor_api.schemas.catalog import ApiModel

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class VerifiedCohortFreezeCommand(ApiModel):
    created_by: str = Field(min_length=1, max_length=200)


class VerifiedCohortExportResponse(ApiModel):
    id: UUID
    game_id: UUID
    import_job_id: UUID
    version: int = Field(ge=1)
    input_state_sha256: Sha256
    payload_sha256: Sha256
    artifact_relative_path: str
    board_count: int = Field(ge=1)
    sample_count: int = Field(ge=15)
    pending_item_count: int = Field(ge=0)
    rejected_item_count: int = Field(ge=0)
    created_by: str
    created_at: datetime


class VerifiedCohortFreezeResponse(ApiModel):
    export: VerifiedCohortExportResponse
    created: bool


def to_verified_cohort_response(
    value: ImageVerifiedCohortExport,
) -> VerifiedCohortExportResponse:
    return VerifiedCohortExportResponse(
        id=value.id,
        game_id=value.game_id,
        import_job_id=value.import_job_id,
        version=value.version,
        input_state_sha256=value.input_state_sha256,
        payload_sha256=value.payload_sha256,
        artifact_relative_path=value.artifact_relative_path,
        board_count=value.board_count,
        sample_count=value.sample_count,
        pending_item_count=value.pending_item_count,
        rejected_item_count=value.rejected_item_count,
        created_by=value.created_by,
        created_at=value.created_at,
    )


__all__ = [
    "VerifiedCohortExportResponse",
    "VerifiedCohortFreezeCommand",
    "VerifiedCohortFreezeResponse",
    "to_verified_cohort_response",
]
