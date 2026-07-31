"""OpenAPI contracts for symbol-catalog bootstrap."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from game_predictor_api.domain.symbol_bootstrap import (
    MAX_EXPECTED_SYMBOL_COUNT,
    SymbolBootstrapRun,
    SymbolBootstrapStatus,
    SymbolImageCandidatePage,
)
from game_predictor_api.schemas.catalog import ApiModel


class SymbolBootstrapStartCommand(ApiModel):
    expected_symbol_count: int = Field(ge=1, le=MAX_EXPECTED_SYMBOL_COUNT)
    created_by: str = Field(min_length=1, max_length=200)


class SymbolBootstrapCandidateResponse(ApiModel):
    candidate_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicted_symbol_code: str
    proposed_code: str
    proposed_name: str
    sample_count: int = Field(ge=1)
    mean_confidence: float = Field(ge=0, le=1)
    representative_crop_relative_path: str
    representative_crop_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SymbolBootstrapDefinitionCommand(ApiModel):
    mobile_code: int = Field(ge=1, le=MAX_EXPECTED_SYMBOL_COUNT)
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    candidate_ids: tuple[str, ...] = Field(min_length=1)


class SymbolBootstrapResolveCommand(ApiModel):
    symbols: tuple[SymbolBootstrapDefinitionCommand, ...] = Field(min_length=1)


class SymbolBootstrapDefinitionResponse(ApiModel):
    mobile_code: int
    code: str
    name: str
    candidate_ids: tuple[str, ...]
    image_path: str


class SymbolBootstrapRunResponse(ApiModel):
    id: UUID
    game_id: UUID
    expected_symbol_count: int
    detected_cluster_count: int
    source_state_sha256: str
    status: SymbolBootstrapStatus
    candidates: tuple[SymbolBootstrapCandidateResponse, ...]
    resolution: tuple[SymbolBootstrapDefinitionResponse, ...]
    created_by: str
    created_at: datetime
    applied_at: datetime | None


class SymbolImageCandidateResponse(ApiModel):
    observation_id: UUID
    crop_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confidence: float = Field(ge=0, le=1)


class SymbolImageCandidatePageResponse(ApiModel):
    items: tuple[SymbolImageCandidateResponse, ...] = Field(max_length=10)
    next_cursor: str | None


class SymbolImageSelectionCommand(ApiModel):
    name: str = Field(min_length=1, max_length=200)


def to_symbol_bootstrap_response(run: SymbolBootstrapRun) -> SymbolBootstrapRunResponse:
    return SymbolBootstrapRunResponse.model_validate(run)


def to_symbol_image_candidate_page_response(
    page: SymbolImageCandidatePage,
) -> SymbolImageCandidatePageResponse:
    return SymbolImageCandidatePageResponse(
        items=tuple(SymbolImageCandidateResponse.model_validate(item) for item in page.items),
        next_cursor=page.next_cursor,
    )


__all__ = [
    "SymbolBootstrapResolveCommand",
    "SymbolBootstrapRunResponse",
    "SymbolBootstrapStartCommand",
    "SymbolImageCandidatePageResponse",
    "SymbolImageSelectionCommand",
    "to_symbol_bootstrap_response",
    "to_symbol_image_candidate_page_response",
]
