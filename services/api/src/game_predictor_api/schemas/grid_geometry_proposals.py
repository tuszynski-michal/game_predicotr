"""OpenAPI contracts for candidate decisions and retained command receipts."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from game_predictor_api.schemas.image_reviews import OperationalImageReviewGeometryPreviewCommand


class ProposalCreateCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    target_result_id: UUID = Field(alias="targetResultId")
    idempotency_key: UUID = Field(alias="idempotencyKey")


class ProposalAcceptCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    idempotency_key: UUID = Field(alias="idempotencyKey")
    expected_proposal_revision: int = Field(alias="expectedProposalRevision", ge=1)
    expected_geometry_revision: int = Field(alias="expectedGeometryRevision", ge=0)
    expected_resolution_revision: int = Field(alias="expectedResolutionRevision", ge=0)
    mode: Literal["model", "edited"]
    original_candidate_sha256: str = Field(
        alias="originalCandidateSha256", pattern="^[0-9a-f]{64}$"
    )
    geometry: OperationalImageReviewGeometryPreviewCommand | None = None

    @model_validator(mode="after")
    def require_edited_geometry(self) -> "ProposalAcceptCommand":
        if (self.mode == "edited") != (self.geometry is not None):
            raise ValueError("Only edited acceptance requires complete geometry.")
        if self.geometry is not None and (
            self.geometry.lattice_nodes is None or self.geometry.geometry_qualification is None
        ):
            raise ValueError("Edited acceptance requires all 24 nodes and explicit qualification.")
        return self


class ProposalRejectCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    idempotency_key: UUID = Field(alias="idempotencyKey")
    expected_proposal_revision: int = Field(alias="expectedProposalRevision", ge=1)
    note: str | None = Field(default=None, max_length=1000)


class ProposalCandidateResponse(BaseModel):
    schemaVersion: Literal["grid-geometry-proposal-v1"]
    result: dict[str, Any]
    resultSha256: str
    originalGeometry: OperationalImageReviewGeometryPreviewCommand
    originalCandidateSha256: str
    modelSnapshot: dict[str, Any]
    sourceImageId: UUID
    positionIndex: int
    sequenceNumber: int | None
    expectedGeometryRevision: int
    expectedResolutionRevision: int
    targetFence: dict[str, Any]
    sourceFence: dict[str, Any]


class ProposalDiscoveryResponse(BaseModel):
    targetResultId: UUID
    originalGeometry: OperationalImageReviewGeometryPreviewCommand
    modelSnapshot: dict[str, Any]
    applicable: bool
    reasons: list[str]


class GridGeometryProposalResponse(BaseModel):
    """Candidate evidence stays separate from human geometry and applicability."""

    id: UUID
    revision: int
    state: Literal["pending", "accepted", "rejected", "stale"]
    candidate: ProposalCandidateResponse
    accepted: dict[str, Any] | None
    applicable: bool
    reasons: list[str]


class ProposalCommandResponse(BaseModel):
    receipt: dict[str, Any]
    current: GridGeometryProposalResponse | None


class ProposalCandidatesResponse(BaseModel):
    proposals: list[GridGeometryProposalResponse]
    candidates: list[ProposalDiscoveryResponse]
