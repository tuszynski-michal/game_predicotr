"""Shared HTTP payload for explicit manual geometry qualification."""

from __future__ import annotations

from typing import Annotated, Literal

from game_predictor_worker.images.lateral_partial_contract import LateralPartialGeometrySnapshot
from pydantic import Field, StrictBool, StrictInt, model_validator

from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.schemas.catalog import ApiModel


class ManualSourceGeometryPoint(ApiModel):
    """Signed coordinates; enclosing commands enforce qualified source bounds."""

    x: StrictInt
    y: StrictInt


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


class AutomaticPartialGeometryProposalPayload(ApiModel):
    """Machine provenance wraps existing availability, never a human decision."""

    version: Literal["automatic-lateral-partial-proposal-v1"]
    origin: Literal["automatic_proposal"]
    source_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    position_index: Annotated[StrictInt, Field(ge=1, le=9)]
    policy_version: Literal["structured-lattice-v4-lateral-partial-v1"]
    policy_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    requires_manual_confirmation: Literal[True]
    geometry_qualification: GeometryQualificationPayload

    @model_validator(mode="after")
    def validate_proposal(self) -> AutomaticPartialGeometryProposalPayload:
        if self.policy_checksum_sha256 != LateralPartialGeometrySnapshot().checksum_sha256:
            raise ValueError("The automatic partial policy checksum changed.")
        if self.geometry_qualification.completeness_status != "pending_partial":
            raise ValueError("An automatic partial proposal requires the existing partial mask.")
        return self
