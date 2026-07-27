"""OpenAPI schemas for dataset staging."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from game_predictor_api.domain.datasets import (
    MAX_GENERATOR_SEED,
    DatasetVersionStatus,
)
from game_predictor_api.schemas.catalog import ApiModel


class MockDatasetCreate(ApiModel):
    rules_version_id: UUID
    seed: int = Field(ge=0, le=MAX_GENERATOR_SEED)


class DatasetVersionResponse(ApiModel):
    id: UUID
    game_id: UUID
    version: int
    rows: int
    columns: int
    signature_cell_width: int
    layout_count: int
    status: DatasetVersionStatus
    generation_seed: int
    generator_version: str
    source_job_id: UUID | None
    created_at: datetime
    published_at: datetime | None
