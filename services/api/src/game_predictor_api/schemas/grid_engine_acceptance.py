"""The status-only historical acceptance API contract."""

from dataclasses import asdict
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from game_predictor_api.application.grid_engine_acceptance import HistoricalAcceptanceReport
from game_predictor_api.schemas.catalog import ApiModel


class HistoricalAcceptanceCreateCommand(ApiModel):
    idempotency_key: UUID


class HistoricalAcceptancePreviewCommand(ApiModel):
    expected_cursor: int = Field(ge=0)


class HistoricalAcceptanceConfirmCommand(ApiModel):
    idempotency_key: UUID
    confirmed: Literal[True]


class HistoricalAcceptanceRunCommand(ApiModel):
    idempotency_key: UUID
    expected_cursor: int = Field(ge=0)


class HistoricalAcceptanceItemResponse(ApiModel):
    ordinal: int
    source_image_id: UUID
    revision_id: UUID | None
    previous_status: str | None
    reasons: list[str]
    outcome: Literal["accepted", "skipped"] | None


class HistoricalAcceptanceResponse(ApiModel):
    game_id: UUID
    operation_id: UUID
    phase: Literal["previewing", "previewed", "running", "done"]
    preparation_state: str | None
    status_only: Literal[True] = True
    materializes_new_cells: Literal[False] = False
    started_at: datetime
    preview_cursor: int
    run_cursor: int
    source_count: int
    revision_count: int
    eligible_count: int
    accepted_count: int
    skipped_count: int
    preview_reasons: dict[str, int]
    run_reasons: dict[str, int]
    items: list[HistoricalAcceptanceItemResponse]
    next_item_cursor: int | None


def historical_acceptance_response(
    report: HistoricalAcceptanceReport,
) -> HistoricalAcceptanceResponse:
    return HistoricalAcceptanceResponse.model_validate(asdict(report))
