"""Public, generated geometry-comparison contracts; pinned inputs are response-only."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from game_predictor_api.domain.grid_shadow import GridShadowResultPage, GridShadowResultView
from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.schemas.image_grid_reviews import (
    ImageGridReviewItemResponse,
    to_image_grid_review_item_response,
)

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class GridShadowJobCreate(ApiModel):
    request_id: UUID
    source_image_ids: tuple[UUID, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique_sources(self) -> GridShadowJobCreate:
        if len(set(self.source_image_ids)) != len(self.source_image_ids):
            raise ValueError("Source image IDs must be unique.")
        return self


class GridShadowPointResponse(ApiModel):
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)


GridNodes24 = Annotated[tuple[GridShadowPointResponse, ...], Field(min_length=24, max_length=24)]


class GridShadowSlotResponse(ApiModel):
    position_index: int = Field(ge=0, le=8)
    sequence_number: int = Field(ge=1)
    baseline_engine_name: str | None = None
    baseline_engine_version: str | None = None
    baseline_nodes24: GridNodes24 | None = None
    neural_nodes24: GridNodes24 | None = None
    state: Literal["needs_review", "missing", "invalid"]
    reason_codes: tuple[str, ...] = ()
    cell_visibility: tuple[Literal["full", "partial", "outside", "unknown"], ...] = Field(
        min_length=15, max_length=15
    )
    review_item: ImageGridReviewItemResponse | None = None


class GridShadowUnassignedDetectionResponse(ApiModel):
    detection_index: int = Field(ge=0)
    nodes24: GridNodes24 | None = None
    reason_codes: tuple[str, ...] = ()


class GridShadowOutputResponse(ApiModel):
    schema_version: Literal[1]
    status: Literal["needs_review", "failed", "unsupported"]
    reasons: tuple[str, ...] = ()
    slots: tuple[GridShadowSlotResponse, ...] = Field(min_length=1, max_length=9)
    unassigned_detections: tuple[GridShadowUnassignedDetectionResponse, ...] = ()


class GridShadowResultSummaryResponse(ApiModel):
    id: UUID
    game_id: UUID
    job_id: UUID
    source_image_id: UUID
    source_checksum_sha256: Sha256
    source_width: int = Field(gt=0)
    source_height: int = Field(gt=0)
    source_geometry_revision_id: UUID
    source_geometry_revision: int = Field(ge=0)
    source_asset_review_item_id: UUID | None = None
    model_profile: str
    model_version: str
    baseline_engine_name: str | None = None
    baseline_engine_version: str | None = None
    baseline_geometry_source: str | None = None
    model_manifest_checksum_sha256: Sha256
    output_checksum_sha256: Sha256
    status: Literal["needs_review", "failed", "unsupported"]
    reasons: tuple[str, ...]
    stale: bool
    created_at: datetime


class GridShadowResultResponse(GridShadowResultSummaryResponse):
    output: GridShadowOutputResponse


class GridShadowResultPageResponse(ApiModel):
    items: tuple[GridShadowResultSummaryResponse, ...]
    next_cursor: str | None


class GridShadowJobPayloadResponse(ApiModel):
    schema_version: Literal[1]
    validation_kind: Literal["grid_geometry_shadow_v3"]
    request_id: UUID
    request_fingerprint_sha256: Sha256
    # These are immutable, backend-generated response data. This type never
    # appears in the public generic JobCreate request union.
    model: dict[str, object]
    sources: tuple[dict[str, object], ...] = Field(min_length=1, max_length=20)
    input_digest_sha256: Sha256


def to_grid_shadow_summary(view: GridShadowResultView) -> GridShadowResultSummaryResponse:
    value = view.result
    return GridShadowResultSummaryResponse(
        id=value.id,
        game_id=value.game_id,
        job_id=value.job_id,
        source_image_id=value.source_image_id,
        source_checksum_sha256=value.source_checksum_sha256,
        source_width=value.source_width,
        source_height=value.source_height,
        source_geometry_revision_id=value.source_geometry_revision_id,
        source_geometry_revision=value.source_geometry_revision,
        source_asset_review_item_id=view.source_asset_review_item_id,
        model_profile=value.model_profile,
        model_version=value.model_version,
        baseline_engine_name=(
            None
            if value.source_binding.get("baseline_engine_name") is None
            else str(value.source_binding["baseline_engine_name"])
        ),
        baseline_engine_version=(
            None
            if value.source_binding.get("baseline_engine_version") is None
            else str(value.source_binding["baseline_engine_version"])
        ),
        baseline_geometry_source=(
            None
            if value.source_binding.get("baseline_geometry_source") is None
            else str(value.source_binding["baseline_geometry_source"])
        ),
        model_manifest_checksum_sha256=value.model_manifest_checksum_sha256,
        output_checksum_sha256=value.output_checksum_sha256,
        status=value.status,
        reasons=value.reasons,
        stale=view.stale,
        created_at=value.created_at,
    )


def to_grid_shadow_result(view: GridShadowResultView) -> GridShadowResultResponse:
    output = GridShadowOutputResponse.model_validate(dict(view.result.output))
    reviews = {item.position_index: item for item in view.review_items}
    raw_baseline = view.result.source_binding.get("baseline_slots", [])
    baseline = (
        {int(str(slot["position_index"])): slot for slot in raw_baseline if isinstance(slot, dict)}
        if isinstance(raw_baseline, list)
        else {}
    )
    slots = tuple(
        slot.model_copy(
            update={
                "baseline_engine_name": baseline.get(slot.position_index, {}).get(
                    "geometry_engine_name"
                ),
                "baseline_engine_version": baseline.get(slot.position_index, {}).get(
                    "geometry_engine_version"
                ),
                "review_item": None
                if slot.position_index not in reviews
                else to_image_grid_review_item_response(reviews[slot.position_index]),
            }
        )
        for slot in output.slots
    )
    output = output.model_copy(update={"slots": slots})
    return GridShadowResultResponse(**to_grid_shadow_summary(view).model_dump(), output=output)


def to_grid_shadow_page(page: GridShadowResultPage) -> GridShadowResultPageResponse:
    return GridShadowResultPageResponse(
        items=tuple(to_grid_shadow_summary(item) for item in page.items),
        next_cursor=page.next_cursor,
    )
