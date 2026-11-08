"""Closed requests; source identity and authenticated actor are resolved server-side."""

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field, StrictBool, field_validator, model_validator

from game_predictor_api.domain.grid_cell_content import (
    ContentCells,
    ContentRevision,
    ContentSource,
    GeometryNodes,
)
from game_predictor_api.domain.grid_visibility_contract import Sha, VisibilityClosed


class ContentWriteCommand(VisibilityClosed):
    idempotencyKey: UUID
    sourceId: UUID
    expectedSourceSha256: Sha
    expectedPixelSha256: Sha
    positionIndex: Annotated[int, Field(strict=True, ge=0, le=8)]
    sequenceNumber: Annotated[int, Field(strict=True, ge=1)]
    expectedRevision: Annotated[int, Field(strict=True, ge=0)]
    cells: ContentCells
    origin: Literal["manual", "ai_proposal"] = "manual"
    humanApproval: StrictBool = False
    proposalSha256: Sha | None = None

    @model_validator(mode="after")
    def origin_proof(self) -> "ContentWriteCommand":
        if (self.origin == "ai_proposal") != (self.proposalSha256 is not None):
            raise ValueError("CONTENT_PROPOSAL_PROVENANCE_REQUIRED")
        return self


class ContentSessionTargetSelection(VisibilityClosed):
    sourceId: UUID
    positionIndices: Annotated[
        list[Annotated[int, Field(strict=True, ge=0, le=8)]], Field(min_length=1, max_length=9)
    ]


class ContentSessionCreate(VisibilityClosed):
    idempotencyKey: UUID
    cohortId: UUID
    expectedManifestSha256: Sha
    sourceIds: Annotated[list[UUID], Field(min_length=1, max_length=100)]
    targetSelection: (
        Annotated[list[ContentSessionTargetSelection], Field(max_length=100)] | None
    ) = None

    @model_validator(mode="after")
    def exact_target_selection(self) -> "ContentSessionCreate":
        if self.targetSelection is not None:
            selected = [entry.sourceId for entry in self.targetSelection]
            if len(selected) != len(set(selected)) or set(selected) != set(self.sourceIds):
                raise ValueError("CONTENT_EXACT_SOURCE_SELECTION_REQUIRED")
            if any(
                len(entry.positionIndices) != len(set(entry.positionIndices))
                for entry in self.targetSelection
            ):
                raise ValueError("CONTENT_TARGET_DUPLICATE")
        return self


class ContentBlindWrite(VisibilityClosed):
    idempotencyKey: UUID
    expectedSessionRevision: Annotated[int, Field(strict=True, ge=1)]
    passNumber: Literal[1, 2]
    sourceId: UUID
    positionIndex: Annotated[int, Field(strict=True, ge=0, le=8)]
    cells: ContentCells
    measuredNodes: GeometryNodes
    humanApproval: Literal[True]

    @field_validator("humanApproval", mode="before")
    @classmethod
    def explicit_human_approval(cls, value: Any) -> Any:
        if value is not True:
            raise ValueError("CONTENT_EXPLICIT_HUMAN_APPROVAL_REQUIRED")
        return value

    @field_validator("passNumber", mode="before")
    @classmethod
    def exact_pass_number(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("CONTENT_PASS_NUMBER_INVALID")
        return value


class ContentSessionAdvance(VisibilityClosed):
    idempotencyKey: UUID
    expectedSessionRevision: Annotated[int, Field(strict=True, ge=1)]


class ContentReferenceResponse(VisibilityClosed):
    annotation: ContentRevision | None
    contentReferenceSha256: Sha | None
    revision: Annotated[int, Field(ge=0)]


class ContentWriteResponse(ContentReferenceResponse):
    idempotencyKey: UUID


class ContentBlindTarget(VisibilityClosed):
    source: ContentSource
    positionIndex: int
    sequenceNumber: int
    completed: bool
    # Deliberately no prior nodes, cells, predictions, reference hash or grid revision.


class ContentSessionStatus(VisibilityClosed):
    sessionId: UUID
    gameId: UUID
    revision: int
    phase: Literal["pass1", "pass2", "frozen"]
    completed: int
    total: int
    report: dict[str, Any] | None = None


class ContentSessionResponse(ContentSessionStatus):
    targets: list[ContentBlindTarget]


class ContentSessionCommandResponse(VisibilityClosed):
    idempotencyKey: UUID
    session: ContentSessionStatus


class ContentSessionList(VisibilityClosed):
    items: list[ContentSessionStatus]


class ContentSamplingPreview(VisibilityClosed):
    baseVersionId: UUID
    familyId: UUID
    importJobIds: Annotated[list[UUID], Field(min_length=1, max_length=100)]
    trainingMode: Literal["grid-only", "screen+grid"] = "grid-only"
    validationAssignments: dict[UUID, Literal["A", "B", "BUFFER"]] = Field(default_factory=dict)


class ContentRoleReadiness(VisibilityClosed):
    state: Literal["evaluable", "not_evaluable"]
    reasonCodes: list[str]
    boards: int
    slots: int
    unapprovedSlots: int
    unresolvedPhotos: int
    states: dict[Literal["visible", "occluded", "out_of_frame", "unknown"], int]
    fullPhotos: int
    missingFullPhotos: int


class ContentReadinessSummary(VisibilityClosed):
    version: Literal["source-cell-content-v1"]
    state: Literal["evaluable", "not_evaluable"]
    games: dict[UUID, dict[Literal["TRAIN", "A", "B", "REGRESSION"], ContentRoleReadiness]]


class ContentReadinessResponse(ContentReadinessSummary):
    basis: Literal["frozen_content_pins"]
    annotationProgress: ContentReadinessSummary
    frozenPinCoverage: ContentReadinessSummary


class ContentSamplingResponse(VisibilityClosed):
    state: Literal["selection_ready", "not_evaluable"]
    qualificationState: Literal["not_evaluated"] = "not_evaluated"
    policy: Literal["full-symbol-content-sampling-v1"] = "full-symbol-content-sampling-v1"
    selection: dict[str, Any] | None = None
    split: dict[str, Any] | None = None
    reasonCodes: list[str] = Field(default_factory=list)
    roleWrites: Literal[False]
