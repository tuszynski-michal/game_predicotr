"""OpenAPI schemas for human-approved symbol reference images."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from game_predictor_api.domain.symbol_references import ApprovedSymbolReferenceCandidatePage
from game_predictor_api.schemas.catalog import ApiModel


class ApprovedSymbolReferenceCandidateResponse(ApiModel):
    observation_id: UUID
    crop_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sequence_number: int = Field(gt=0)
    cell_index: int = Field(ge=0, le=14)
    geometry_revision: int = Field(ge=0)
    status: str


class ApprovedSymbolReferenceCandidatePageResponse(ApiModel):
    items: tuple[ApprovedSymbolReferenceCandidateResponse, ...] = Field(max_length=20)
    next_cursor: str | None


def to_approved_symbol_reference_candidate_page_response(
    page: ApprovedSymbolReferenceCandidatePage,
) -> ApprovedSymbolReferenceCandidatePageResponse:
    return ApprovedSymbolReferenceCandidatePageResponse(
        items=tuple(
            ApprovedSymbolReferenceCandidateResponse.model_validate(item)
            for item in page.items
        ),
        next_cursor=page.next_cursor,
    )


__all__ = [
    "ApprovedSymbolReferenceCandidatePageResponse",
    "to_approved_symbol_reference_candidate_page_response",
]
