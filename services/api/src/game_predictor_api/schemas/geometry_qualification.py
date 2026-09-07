"""Shared HTTP payload for explicit manual geometry qualification."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, model_validator

from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.schemas.catalog import ApiModel


class GeometryQualificationPayload(ApiModel):
    version: Literal["manual-geometry-qualification-v1"]
    completeness_status: Literal["complete", "pending_partial"]
    unavailable_cell_indices: list[Annotated[StrictInt, Field(ge=0, le=14)]] = Field(max_length=15)
    exclude_from_geometry_training: StrictBool
    exclusion_reason: Literal["missing_pixels", "manual_exclusion"] | None

    @model_validator(mode="after")
    def validate_decision(self) -> GeometryQualificationPayload:
        self.to_domain()
        return self

    def to_domain(self) -> GeometryQualification:
        return GeometryQualification(
            completeness_status=self.completeness_status,
            unavailable_cell_indices=tuple(self.unavailable_cell_indices),
            exclude_from_geometry_training=self.exclude_from_geometry_training,
            exclusion_reason=self.exclusion_reason,
        )
