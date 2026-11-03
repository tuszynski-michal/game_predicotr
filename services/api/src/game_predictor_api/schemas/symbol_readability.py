"""Typed contract for the independent, human-labelled quality workflow."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from game_predictor_api.schemas.catalog import ApiModel

ReadabilityState = Literal["pending", "readable", "unreadable", "skipped", "stale", "error"]


class ReadabilityStartRequest(ApiModel):
    idempotency_key: UUID
    kind: Literal["pilot", "scan"]
    model_id: UUID | None = None
    seed: str = Field(default="quality-pilot-v1", min_length=1, max_length=100)


class ReadabilityCommandRequest(ApiModel):
    idempotency_key: UUID
    expected_revision: int = Field(ge=0)


class ReadabilityLabelTarget(ApiModel):
    cell_id: UUID
    expected_identity: str = Field(pattern="^[0-9a-f]{64}$")
    expected_revision: int = Field(ge=0)


class ReadabilityLabelRequest(ApiModel):
    idempotency_key: UUID
    targets: list[ReadabilityLabelTarget] = Field(min_length=1, max_length=250)
    state: Literal["pending", "readable", "unreadable", "skipped"]
    overlap: bool | None
    sharp: bool = False
    similar_readable: bool = False


class ReadabilityRunResponse(ApiModel):
    id: UUID
    kind: Literal["pilot", "scan"]
    status: str
    revision: int
    job_id: UUID | None
    model_id: UUID | None
    inventory_fingerprint: str | None
    item_count: int
    processed_count: int
    error_code: str | None
    error_message: str | None


class ReadabilityModelResponse(ApiModel):
    id: UUID
    pilot_run_id: UUID
    status: str
    revision: int
    job_id: UUID
    fingerprint: str | None
    report: dict[str, object]
    accepted: bool
    error_code: str | None
    error_message: str | None


class ReadabilityWorkspaceResponse(ApiModel):
    runs: list[ReadabilityRunResponse]
    models: list[ReadabilityModelResponse]


class ReadabilityItemResponse(ApiModel):
    cell_id: UUID
    review_item_id: UUID
    recognized_board_id: UUID
    import_job_id: UUID
    source_id: UUID
    sequence_number: int
    cell_index: int
    row_index: int
    column_index: int
    geometry_revision: int
    crop_checksum_sha256: str | None
    render_spec_checksum_sha256: str | None
    identity: str
    revision: int
    state: ReadabilityState
    overlap: bool | None
    sharp: bool
    similar_readable: bool
    historical_unreadable: bool
    sample_kind: Literal["pilot", "audit", "scan"]
    overlap_score: float | None
    unreadable_score: float | None
    candidate: bool
    reasons: list[str]


class ReadabilityPageResponse(ApiModel):
    items: list[ReadabilityItemResponse]
    next_offset: int | None
    fields: int
    boards: int
    sources: int
    confirmed_fields: int
    confirmed_boards: int
    confirmed_sources: int
