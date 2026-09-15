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
    version: Literal["manual-geometry-qualification-v1", "manual-geometry-qualification-v2"]
    completeness_status: Literal["complete", "pending_partial"]
    unavailable_cell_indices: list[Annotated[StrictInt, Field(ge=0, le=14)]] = Field(max_length=15)
    exclude_from_geometry_training: StrictBool
    exclusion_reason: Literal["missing_pixels", "manual_exclusion"] | None
    include_in_partial_grid_training: StrictBool | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def validate_decision(self) -> GeometryQualificationPayload:
        if self.version == "manual-geometry-qualification-v1" and (
            self.include_in_partial_grid_training is not None
        ):
            raise ValueError("Geometry qualification v1 cannot contain the v2 training field.")
        if self.version == "manual-geometry-qualification-v2" and (
            self.include_in_partial_grid_training is None
        ):
            raise ValueError("Geometry qualification v2 requires the partial training field.")
        self.to_domain()
        return self

    def to_domain(self) -> GeometryQualification:
        return GeometryQualification(
            completeness_status=self.completeness_status,
            unavailable_cell_indices=tuple(self.unavailable_cell_indices),
            exclude_from_geometry_training=self.exclude_from_geometry_training,
            exclusion_reason=self.exclusion_reason,
            include_in_partial_grid_training=(self.include_in_partial_grid_training is True),
            version=self.version,
        )


class AutomaticPartialGeometryProposalPayload(ApiModel):
    """Machine provenance wraps existing availability, never a human decision."""

    version: Literal[
        "automatic-lateral-partial-proposal-v1",
        "automatic-lateral-partial-proposal-v2",
        "automatic-lateral-partial-proposal-v3",
    ]
    origin: Literal["automatic_proposal"]
    source_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    position_index: Annotated[StrictInt, Field(ge=1, le=9)]
    policy_version: Literal[
        "structured-lattice-v4-lateral-partial-v1",
        "structured-lattice-v4-lateral-partial-v2",
        "structured-lattice-v4-lateral-partial-v3",
    ]
    policy_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    requires_manual_confirmation: Literal[True]
    geometry_qualification: GeometryQualificationPayload
    training_profile_checksum_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_proposal(self) -> AutomaticPartialGeometryProposalPayload:
        modern = self.policy_version == "structured-lattice-v4-lateral-partial-v3"
        learned = self.training_profile_checksum_sha256 is not None
        expected_proposal_version = (
            "automatic-lateral-partial-proposal-v3"
            if modern
            else (
                "automatic-lateral-partial-proposal-v2"
                if learned
                else "automatic-lateral-partial-proposal-v1"
            )
        )
        expected_qualification_version = (
            "manual-geometry-qualification-v2"
            if modern or learned
            else "manual-geometry-qualification-v1"
        )
        if self.version != expected_proposal_version:
            raise ValueError("The automatic partial proposal version does not match its policy.")
        if self.geometry_qualification.version != expected_qualification_version:
            raise ValueError("The geometry qualification version does not match its policy.")
        if (
            self.policy_version == "structured-lattice-v4-lateral-partial-v1"
            and self.policy_checksum_sha256
            != LateralPartialGeometrySnapshot(frame_support_review=False).checksum_sha256
        ):
            raise ValueError("The automatic partial policy checksum changed.")
        if self.policy_version == "structured-lattice-v4-lateral-partial-v2" and not learned:
            raise ValueError("The learned partial proposal requires its profile checksum.")
        if self.policy_version == "structured-lattice-v4-lateral-partial-v1" and learned:
            raise ValueError("The legacy partial proposal cannot contain a profile checksum.")
        if self.geometry_qualification.completeness_status != "pending_partial":
            raise ValueError("An automatic partial proposal requires the existing partial mask.")
        return self


class AutomaticFrameGeometryProposalPayload(ApiModel):
    """A complete local grid retained because its decorative frame is weak."""

    version: Literal["automatic-frame-geometry-proposal-v1"]
    origin: Literal["automatic_proposal"]
    source_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    position_index: Annotated[StrictInt, Field(ge=1, le=9)]
    policy_version: Literal["structured-lattice-v4-lateral-partial-v3"]
    policy_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    requires_manual_confirmation: Literal[True]
    reason_code: Literal["board_frame_support_incomplete"]
    geometry_qualification: GeometryQualificationPayload
    training_profile_checksum_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )

    @model_validator(mode="after")
    def validate_proposal(self) -> AutomaticFrameGeometryProposalPayload:
        qualification = self.geometry_qualification
        if (
            qualification.version != "manual-geometry-qualification-v2"
            or qualification.completeness_status != "complete"
            or qualification.unavailable_cell_indices
            or not qualification.exclude_from_geometry_training
            or qualification.exclusion_reason != "manual_exclusion"
            or qualification.include_in_partial_grid_training is not False
        ):
            raise ValueError("A frame proposal requires excluded complete geometry.")
        return self
