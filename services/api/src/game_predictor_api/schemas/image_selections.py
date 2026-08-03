"""OpenAPI contracts for image-selection runs and bounded group pages."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from game_predictor_api.domain.image_selections import (
    ImageSelectionGroup,
    ImageSelectionGroupPage,
    ImageSelectionGroupStatus,
    ImageSelectionRun,
)
from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.schemas.jobs import JobResponse

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ImageSelectionCreate(ApiModel):
    game_id: UUID
    selection_token: str = Field(min_length=32, max_length=200)
    contract_version: Literal[1] = 1


class ImageSelectionRunResponse(ApiModel):
    id: UUID
    game_id: UUID
    job: JobResponse
    source_selection_id: UUID
    input_manifest_sha256: Sha256
    selector_fingerprint: Sha256
    ordering_policy: str = Field(pattern=r"^natural_relative_path_v1$")
    contract_version: int = Field(ge=1, le=1)
    output_manifest_sha256: Sha256 | None
    output_manifest_relative_path: str | None
    created_at: datetime
    updated_at: datetime


class ImageSelectionCreateResponse(ApiModel):
    run: ImageSelectionRunResponse
    created: bool


class ImageSelectionGroupResponse(ApiModel):
    id: UUID
    run_id: UUID
    group_order: int = Field(ge=0)
    range_start: int | None = Field(default=None, ge=1)
    range_end: int | None = Field(default=None, ge=1)
    fingerprint_sha256: Sha256 | None
    board_count_consensus: int | None = Field(default=None, ge=1, le=9)
    status: ImageSelectionGroupStatus
    selected_candidate_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ImageSelectionGroupPageResponse(ApiModel):
    items: list[ImageSelectionGroupResponse]
    next_after_group_order: int | None = Field(default=None, ge=0)


def to_image_selection_run_response(
    run: ImageSelectionRun,
) -> ImageSelectionRunResponse:
    return ImageSelectionRunResponse(
        id=run.id,
        game_id=run.game_id,
        job=JobResponse.from_domain(run.job),
        source_selection_id=run.source_selection_id,
        input_manifest_sha256=run.input_manifest_sha256,
        selector_fingerprint=run.selector_fingerprint,
        ordering_policy=run.ordering_policy,
        contract_version=run.contract_version,
        output_manifest_sha256=run.output_manifest_sha256,
        output_manifest_relative_path=run.output_manifest_relative_path,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def to_image_selection_group_response(
    group: ImageSelectionGroup,
) -> ImageSelectionGroupResponse:
    return ImageSelectionGroupResponse(
        id=group.id,
        run_id=group.run_id,
        group_order=group.group_order,
        range_start=group.range_start,
        range_end=group.range_end,
        fingerprint_sha256=group.fingerprint_sha256,
        board_count_consensus=group.board_count_consensus,
        status=group.status,
        selected_candidate_id=group.selected_candidate_id,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


def to_image_selection_group_page_response(
    page: ImageSelectionGroupPage,
) -> ImageSelectionGroupPageResponse:
    return ImageSelectionGroupPageResponse(
        items=[to_image_selection_group_response(item) for item in page.items],
        next_after_group_order=page.next_after_group_order,
    )


__all__ = [
    "ImageSelectionCreate",
    "ImageSelectionCreateResponse",
    "ImageSelectionGroupPageResponse",
    "ImageSelectionGroupResponse",
    "ImageSelectionRunResponse",
    "to_image_selection_group_page_response",
    "to_image_selection_run_response",
]
