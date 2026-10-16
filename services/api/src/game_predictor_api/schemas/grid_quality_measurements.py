"""Closed commands and schema-owned measurement views for D-555."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QualityCaptureCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    idempotency_key: UUID = Field(alias="idempotencyKey")
    seed: str = Field(min_length=1, max_length=200)
    sample_size: int = Field(default=100, alias="sampleSize", ge=1, le=100)
    hard_source_ids: list[UUID] = Field(default_factory=list, alias="hardSourceIds", max_length=100)

    @model_validator(mode="after")
    def unique_hard_sources(self) -> "QualityCaptureCommand":
        if len(set(self.hard_source_ids)) != len(self.hard_source_ids):
            raise ValueError("Hard sample source IDs must be unique.")
        return self


class QualityPositionJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    position_index: int = Field(alias="positionIndex", ge=0, le=8)
    geometry: Literal["correct", "incorrect", "not_assessable", "unreviewed"]
    detection: Literal["correct", "incorrect", "unknown", "unreviewed"]
    sequence: Literal["correct", "incorrect", "unknown", "unreviewed"]


class QualityUnexpectedJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    index: int = Field(ge=0)
    verdict: Literal["correct", "incorrect", "unknown", "unreviewed"]


class QualityAssessCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    idempotency_key: UUID = Field(alias="idempotencyKey")
    source_id: UUID = Field(alias="sourceId")
    sample_kind: Literal["random", "hard"] = Field(alias="sampleKind")
    expected_revision: int = Field(alias="expectedRevision", ge=0)
    manifest_sha256: str = Field(alias="manifestSha256", pattern="^[0-9a-f]{64}$")
    positions: list[QualityPositionJudgment] = Field(min_length=9, max_length=9)
    unexpected: list[QualityUnexpectedJudgment] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def all_physical_positions(self) -> "QualityAssessCommand":
        if sorted(item.position_index for item in self.positions) != list(range(9)):
            raise ValueError("All nine distinct physical positions are required.")
        if len({item.index for item in self.unexpected}) != len(self.unexpected):
            raise ValueError("Unexpected detection judgments must be unique.")
        return self


class GeometryApprovalCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    idempotency_key: UUID = Field(alias="idempotencyKey")
    measurement_id: UUID = Field(alias="measurementId")
    source_id: UUID = Field(alias="sourceId")
    sample_kind: Literal["random", "hard"] = Field(alias="sampleKind")
    position_index: int = Field(alias="positionIndex", ge=0, le=8)
    manifest_sha256: str = Field(alias="manifestSha256", pattern="^[0-9a-f]{64}$")
    target_sha256: str = Field(alias="targetSha256", pattern="^[0-9a-f]{64}$")


class QualityPoint(BaseModel):
    x: float
    y: float


class QualityObservation(BaseModel):
    available: bool
    reason: str | None
    nodes: list[list[QualityPoint]] | None
    geometry: dict[str, Any] | None
    producer: dict[str, Any] | None


class QualityPositionResponse(BaseModel):
    positionIndex: int
    sequenceNumber: int | None
    original: QualityObservation
    current: QualityObservation
    reviewItemId: UUID | None
    targetSha256: str
    ownership: Literal["own", "foreign", "unknown"]
    currentManualSymbolCount: int
    currentSymbolCellCount: int
    approvalEligible: bool
    approvalBlocker: str | None = None


class QualityMemberResponse(BaseModel):
    sourceId: UUID
    importJobId: UUID
    sampleKind: Literal["random", "hard"]
    revision: int
    source: dict[str, Any]
    available: bool
    unavailableReason: str | None
    recordingStatus: Literal["declared", "unresolved"]
    positions: list[QualityPositionResponse]
    judgments: list[QualityPositionJudgment]
    unexpectedDetections: list[dict[str, Any]]
    unexpectedJudgments: list[QualityUnexpectedJudgment]


class QualityMeasurementResponse(BaseModel):
    measurementId: UUID
    gameId: UUID
    policy: str
    populationPolicy: str
    seed: str
    capturedAt: str
    frozenPopulationCount: int
    excludedSupersededCount: int
    populationSha256: str
    manifestSha256: str
    manifestAvailable: bool
    manifestBlocker: str | None
    report: dict[str, Any]
    members: list[QualityMemberResponse]


class QualityMeasurementSummary(BaseModel):
    measurementId: UUID
    capturedAt: str
    seed: str
    frozenPopulationCount: int
    randomSampleCount: int
    hardSampleCount: int
    manifestSha256: str


class QualityMeasurementPage(BaseModel):
    items: list[QualityMeasurementSummary]
    nextCursor: UUID | None


class QualityCommandResponse(BaseModel):
    receipt: dict[str, Any]
    current: QualityMeasurementResponse | None


class GeometryApprovalResponse(BaseModel):
    receipt: dict[str, Any]
